"""Retrospectiva PRE-decision (v3.57.0).

QUE HACE
--------
Antes de que una senal se convierta en trade, mira los ultimos N trades SIMILARES
(mismo setup_type, y si se puede el mismo bucket de volatilidad) y compara como
le fue a esa familia **en la direccion que se esta por tomar** contra **la
direccion opuesta**. Si la historia dice que en este contexto la direccion
opuesta era la que ganaba, emite un veredicto `contrarian` y un delta de
confianza NEGATIVO.

QUE **NO** HACE, A PROPOSITO
----------------------------
1. **No bloquea nunca.** No hay rama que devuelva "skip". La restriccion del user
   es no bajar frecuencia, y un filtro binario sobre n<10 es exactamente el error
   que este proyecto ya cometio 3 veces (hour gate, late breakout, entry gates).
2. **No invierte la direccion.** "La opuesta gano en los ultimos 5" no es
   evidencia para operar al reves; es evidencia para desconfiar. Invertir sobre
   n=5 seria sobreajuste con plata.
3. **No decide con muestra chica.** Debajo de `RETRO_MIN_N` devuelve
   `insufficient` y delta 0. El delta escala con la muestra: n=6 mueve casi nada,
   n>=`RETRO_FULL_N` mueve el maximo.

MODOS (`RETRO_MODE`, env, sin rebuild)
--------------------------------------
- `off`     : no corre nada.
- `shadow`  : **default**. Calcula, persiste el veredicto, NO toca la confianza.
              Sirve para juntar la muestra con la que se decide si discrimina.
- `active`  : ademas aplica `conf_delta` a la confianza guardada.

Por que `shadow` es el default y no `active`: hoy no hay una sola medicion de que
este veredicto separe ganar de perder. Activarlo de entrada seria creer la
hipotesis antes de medirla.

NOTA HONESTA SOBRE EL ALCANCE DEL DELTA (verificado leyendo el codigo, 19-ago)
-----------------------------------------------------------------------------
Todos los gates de `min_confidence` viven DENTRO de los detectores, **antes** de
`add_auto_strategy`; y el lote sale de `sl_pips`, no de la confianza
(`mt5_executor.open_position`). Por eso el delta es frecuencia-neutro y
tamano-neutro: hoy **no cambia ninguna decision de ejecucion**. Su valor es
(a) el registro estructurado y (b) la muestra. Cuando/si el veredicto demuestre
discriminacion, el lever para que ACTUE hay que elegirlo y medirlo aparte.
"""

import logging
import os

logger = logging.getLogger(__name__)

# ── Perillas (todas por env, revertible sin rebuild) ──

def _mode() -> str:
    m = (os.getenv('RETRO_MODE', 'shadow') or 'shadow').strip().lower()
    return m if m in ('off', 'shadow', 'active') else 'shadow'


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning(f"{name} invalido en env -> uso default {default}")
        return default


# n total minimo (misma + opuesta) para emitir cualquier veredicto con delta != 0
RETRO_MIN_N_DEFAULT = 6
# n por lado minimo para hablar de "la opuesta iba mejor"
RETRO_MIN_PER_SIDE_DEFAULT = 3
# a partir de este n el delta va al maximo
RETRO_FULL_N_DEFAULT = 15
# tope absoluto del nudge, en puntos de confianza
RETRO_MAX_DELTA_DEFAULT = 8
# cuantos trades similares se miran hacia atras
RETRO_LOOKBACK_DEFAULT = 40


# ── Familias de setup DIRECCION-NEUTRAS ──
#
# Esto sale de correr la retrospectiva contra la DB real (19-ago) y ver que no
# podia funcionar: `setup_type` **codifica la direccion** en la mayoria de las
# familias (`trend_continuation_bull` es siempre CALL, `breakdown_support` es
# siempre PUT). Comparando por `setup_type` exacto, el lado opuesto tiene n=0
# SIEMPRE, y la pregunta "¿la opuesta pagaba?" es inrespondible por construccion.
#
# La familia agrupa los dos lados del MISMO patron para que la comparacion exista.
# Los pares se leen del catalogo real de `trade_archive`, no se inventan.
SETUP_FAMILIES = {
    'trend_continuation_bull': 'trend_continuation',
    'trend_continuation_bear': 'trend_continuation',
    'breakout_resistance': 'level_break',
    'breakdown_support': 'level_break',
    'breakout': 'level_break',
    'soporte': 'level_break',
    'rsi_reversal_support': 'rsi_reversal',
    'rsi_reversal_resistance': 'rsi_reversal',
    'bb_rejection_lower': 'bb_rejection',
    'bb_rejection_upper': 'bb_rejection',
    'smc_demand': 'smc_zone',
    'smc_supply': 'smc_zone',
}


def setup_family(setup_type: str) -> str:
    """Familia direccion-neutra de un setup. Si no esta en el catalogo, el setup
    es su propia familia (p.ej. `momentum_expansion`, `news_ALTA`, que no traen
    direccion en el nombre)."""
    s = (setup_type or '').strip()
    return SETUP_FAMILIES.get(s, s)


def family_members(family: str) -> list:
    """Todos los `setup_type` que pertenecen a una familia."""
    if not family:
        return []
    members = [k for k, v in SETUP_FAMILIES.items() if v == family]
    return members or [family]


def _scale(n: int, full_n: int) -> float:
    """Peso 0..1 por tamano de muestra. Lineal, sin sorpresas."""
    if full_n <= 0:
        return 1.0
    return max(0.0, min(1.0, float(n) / float(full_n)))


def _side_stats(rows, direction):
    """(n, wins, pnl) de las filas cuya direccion es `direction`."""
    sel = [r for r in rows if (r.get('direction') or '').upper() == direction.upper()]
    n = len(sel)
    wins = sum(1 for r in sel if (r.get('mt5_pnl') or 0) > 0)
    pnl = sum(float(r.get('mt5_pnl') or 0) for r in sel)
    return n, wins, round(pnl, 2)


def _opposite(direction: str) -> str:
    d = (direction or '').upper()
    if d == 'CALL':
        return 'PUT'
    if d == 'PUT':
        return 'CALL'
    return ''


def evaluate(signal: dict) -> dict:
    """Corre la retrospectiva para una senal. NUNCA lanza: devuelve un veredicto
    `error` con delta 0 si algo falla (pero lo loguea a WARNING con stack, no a
    debug: la clase de bug que mas dano hizo en este proyecto es la excepcion
    tragada en silencio).

    Args:
        signal: dict con al menos direction, trigger_type; idealmente tambien
                setup_type, volatility, confidence.

    Returns dict con:
        mode, verdict, conf_delta (0 si no es 'active'), conf_delta_suggested,
        n_similar, n_same, n_opp, wr_same, wr_opp, pnl_same, pnl_opp,
        matched_on, lesson_hits, reason
    """
    out = {
        'mode': _mode(), 'verdict': 'off', 'conf_delta': 0, 'conf_delta_suggested': 0,
        'n_similar': 0, 'n_same': 0, 'n_opp': 0, 'wr_same': None, 'wr_opp': None,
        'pnl_same': 0.0, 'pnl_opp': 0.0, 'matched_on': '', 'lesson_hits': 0,
        'reason': '',
    }
    if out['mode'] == 'off':
        out['reason'] = 'RETRO_MODE=off'
        return out

    try:
        direction = (signal.get('direction') or '').upper()
        opp = _opposite(direction)
        if not opp:
            out['verdict'] = 'error'
            out['reason'] = f"direccion no reconocida: {signal.get('direction')!r}"
            logger.warning(f"retrospectiva: {out['reason']}")
            return out

        min_n = _int_env('RETRO_MIN_N', RETRO_MIN_N_DEFAULT)
        min_side = _int_env('RETRO_MIN_PER_SIDE', RETRO_MIN_PER_SIDE_DEFAULT)
        full_n = _int_env('RETRO_FULL_N', RETRO_FULL_N_DEFAULT)
        max_delta = _int_env('RETRO_MAX_DELTA', RETRO_MAX_DELTA_DEFAULT)
        lookback = _int_env('RETRO_LOOKBACK', RETRO_LOOKBACK_DEFAULT)

        from src.common.db import get_similar_trades, get_directional_lessons

        setup_type = (signal.get('setup_type') or '').strip()
        trigger_type = (signal.get('trigger_type') or '').strip()
        volatility = (signal.get('volatility') or '').strip()

        # Match en 3 escalones, del mas especifico al mas laxo. El escalon que
        # efectivamente se uso queda registrado en `matched_on` para que despues
        # se pueda leer el resultado por nivel de especificidad y no todo junto.
        fam = setup_family(setup_type)
        fam_members = family_members(fam) if setup_type else []
        rows, matched_on = [], ''
        for _members, _vol, _label in (
            (fam_members, volatility, 'family+vol'),
            (fam_members, '', 'family'),
            ([], '', 'trigger'),
        ):
            if _label != 'trigger' and not fam_members:
                continue
            if _label == 'family+vol' and not volatility:
                continue
            rows = get_similar_trades(setup_types=_members, trigger_type=trigger_type,
                                      volatility=_vol, limit=lookback)
            if len(rows) >= min_n:
                matched_on = _label
                break
        if not matched_on:
            # Ningun escalon junto min_n: se queda con el ultimo intento (trigger),
            # que es el mas amplio. El veredicto va a salir `insufficient` y eso es
            # el resultado correcto, no un error.
            matched_on = 'trigger'
        out['matched_on'] = f"{matched_on}:{fam or trigger_type}"

        n_same, w_same, pnl_same = _side_stats(rows, direction)
        n_opp, w_opp, pnl_opp = _side_stats(rows, opp)
        out.update({
            'n_similar': n_same + n_opp, 'n_same': n_same, 'n_opp': n_opp,
            'pnl_same': pnl_same, 'pnl_opp': pnl_opp,
            'wr_same': round(100.0 * w_same / n_same, 1) if n_same else None,
            'wr_opp': round(100.0 * w_opp / n_opp, 1) if n_opp else None,
        })

        # Lecciones direccionales acumuladas por el post-trade para este setup
        # que apuntan a la direccion OPUESTA a la que se esta por tomar.
        try:
            out['lesson_hits'] = len(get_directional_lessons(
                setup_type='' if fam_members else (setup_type or trigger_type),
                setup_types=fam_members, better_direction=opp, limit=20))
        except Exception as _le:
            logger.warning(f"retrospectiva: lecciones no consultables: {_le}", exc_info=True)

        if out['n_similar'] < min_n:
            out['verdict'] = 'insufficient'
            out['reason'] = f"n={out['n_similar']} < min {min_n} (match {matched_on})"
            return out

        # ── Veredicto ──
        suggested = 0
        both_sides = n_same >= min_side and n_opp >= min_side
        if both_sides and pnl_same < 0 and pnl_opp > 0:
            # la familia perdio yendo para este lado y gano para el otro
            w = _scale(min(n_same, n_opp) * 2, full_n)
            suggested = -int(round(max_delta * w)) or -1
            out['verdict'] = 'contrarian'
            out['reason'] = (f"{matched_on}: {direction} n={n_same} pnl={pnl_same} vs "
                             f"{opp} n={n_opp} pnl={pnl_opp} -> la opuesta pagaba")
        elif n_same >= min_side and pnl_same > 0:
            w = _scale(n_same, full_n)
            suggested = int(round(max_delta * 0.5 * w))
            out['verdict'] = 'aligned'
            out['reason'] = f"{matched_on}: {direction} n={n_same} pnl={pnl_same} positivo"
        else:
            out['verdict'] = 'neutral'
            out['reason'] = (f"{matched_on}: sin separacion clara "
                             f"({direction} n={n_same} pnl={pnl_same} | {opp} n={n_opp} pnl={pnl_opp})")

        # Las lecciones del post-trade solo pueden PENALIZAR, y como maximo la
        # mitad del tope. Nunca premian: una leccion dice "esto salio mal", no
        # "esto sale bien".
        if out['lesson_hits'] > 0:
            penalty = -min(max_delta // 2, out['lesson_hits'])
            suggested += penalty
            out['reason'] += f" | {out['lesson_hits']} leccion(es) hacia {opp} ({penalty})"

        suggested = max(-max_delta, min(max_delta, suggested))
        out['conf_delta_suggested'] = suggested
        out['conf_delta'] = suggested if out['mode'] == 'active' else 0
        return out

    except Exception as e:
        out['verdict'] = 'error'
        out['reason'] = str(e)[:200]
        # fail-loud: WARNING con stack. Nunca logger.debug.
        logger.warning(f"retrospectiva pre-trade fallo: {e}", exc_info=True)
        return out
