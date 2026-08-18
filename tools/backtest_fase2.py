"""
backtest_fase2.py — FASE 2: ¿el detector tiene edge en el TIMEFRAME DONDE OPERA?

READ-ONLY. No escribe en la DB de produccion, no manda ordenes, no toca el vivo.
Solo lee velas historicas de MT5 (una vez, a un cache en disco) y calcula.

═══ POR QUE EXISTE ═══════════════════════════════════════════════════════════

Fase 1 (commit 579cc22) midio detect_structure_signals sobre velas D1 en 21 pares
y 7+ anios, no encontro edge, y concluyo que el problema es el GENERADOR — que es
el mismo que alimenta structure/m15/h1 en vivo.

Esa ultima parte es una EXTRAPOLACION, no una medicion: el test corrio sobre D1 y
los tracks vivos corren sobre M5/M15/H1. Fase 2 mide exactamente eso.

El criterio, las 2 enmiendas y las acciones comprometidas para cada resultado
estan en docs/fase2_criterio_declarado.md, COMMITEADOS ANTES de correr esto
(56bbba4, d631703, 2846de6). Si el resultado no se lee contra ese archivo, no
vale nada.

═══ QUE HACE DISTINTO AL DE FASE 1 ═══════════════════════════════════════════

1. TIMEFRAME parametrizable (el de Fase 1 tenia TIMEFRAME_D1 hardcodeado).
2. CACHE de velas en disco: se bajan UNA vez en el proceso padre y los workers
   leen de ahi. Evita 14 procesos peleando por el terminal MT5 y garantiza que
   todos midan sobre exactamente el mismo snapshot.
3. PARALELO: 1 job por (simbolo, sesion). Con 26 simbolos x 4 sesiones son 104
   jobs. Secuencial serian ~75 h; con 14 workers, ~5,3 h.
4. Las 4 sesiones se evaluan POR SEPARADO (ENMIENDA 1). NO se poolean: son 4
   supuestos alternativos sobre la misma realidad, no 4 muestras independientes.
5. CONTROL DE ENTRADAS ALEATORIAS (el que le falto a Fase 1b): mismo n por
   simbolo, mismo ratio long/short, mismo SL/TP/hold, mismos costos.

═══ CAVEATS (heredados, declarados en §10 del criterio) ══════════════════════

  - Solo trigger 'structure' (sin news / smc / pre_planned).
  - Sin los filtros del loop vivo (SIM A, counter-HTF, anti-spam, cooldown,
    warmup, piso de ATR) => la frecuencia real seria MENOR.
  - Sin spread variable, sin slippage, sin latencia.
  - htf_bias = None.
  - El tp_cap de produccion (technical.py:1430) NO se replica (ENMIENDA 2.b).
  - Un backtest tipico INFLA 20-30% vs real con friccion.
  => un "PASA" es permiso para investigar, NUNCA permiso para operar.

Uso:
    python tools/backtest_fase2.py --build-cache      # baja las velas (1 vez)
    python tools/backtest_fase2.py --workers 14       # corre el primario
    python tools/backtest_fase2.py --profile atr      # el secundario
"""
import argparse
import json
import os
import pickle
import random
import statistics as stats
import sys
import time
from copy import deepcopy
from datetime import datetime
from multiprocessing import Pool
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_h4_d1 import (  # noqa: E402
    SESSIONS, assert_sessions_match_prod, load_live_params, setup_logger,
)
from tools.backtest_multi_symbol import (  # noqa: E402
    SYMBOLS_FASE1, symbol_spec, simulate,
)

# ── Universo (ENMIENDA 2.a): union de las DOS listas pre-declaradas ──────────
# 20 de docs/fase1_pares_declarados.md (commit 5a7d57e)
# + 6 out-of-sample de docs/fase1b_prediccion_registrada.md (commit 2269691)
SYMBOLS_FASE1B = ['CHFJPY', 'NZDJPY', 'GBPNZD', 'NZDCHF', 'NZDCAD', 'GBPCAD']
SYMBOLS = list(SYMBOLS_FASE1) + SYMBOLS_FASE1B          # 26

# ── Perfiles (ENMIENDA 2.b) ──────────────────────────────────────────────────
# PRIMARIO: el vivo de M15 (src/analyzer/technical_m15.py:M15_PROFILE).
PROFILE_LIVE = {'kind': 'fixed', 'sl_pips': 15.0, 'tp_pips': 60.0,
                'hold': 3, 'min_confidence': 60}
# SECUNDARIO: el del arnes de Fase 1, para comparabilidad manzana-con-manzana.
PROFILE_ATR = {'kind': 'atr', 'sl_atr_mult': 1.2, 'rr': 2.0,
               'hold': 10, 'min_confidence': 60}
# SECUNDARIO M5: el perfil VIVO de M5, que NO es el de M15. Leido de
# get_active_profile() el 18-ago: min_confidence 60, SL 3,5p, TP 20p, expiry 15min
# (= 3 velas M5). Correr M5 con los numeros de M15 (SL 15 / TP 60) habria medido un
# sistema que no existe — ver ENMIENDA 4 del criterio.
PROFILE_M5_LIVE = {'kind': 'fixed', 'sl_pips': 3.5, 'tp_pips': 20.0,
                   'hold': 3, 'min_confidence': 60}
PROFILES_F2 = {'live': PROFILE_LIVE, 'atr': PROFILE_ATR, 'm5live': PROFILE_M5_LIVE}

TF_MAP = {'M5': 'TIMEFRAME_M5', 'M15': 'TIMEFRAME_M15',
          'H1': 'TIMEFRAME_H1', 'D1': 'TIMEFRAME_D1'}
DEDUP_SEC = {'M5': 1800, 'M15': 2700, 'H1': 10800, 'D1': 172800}
WARMUP = 100
MIN_CANDLES = 100_000            # piso declarado para no excluir en silencio

CONTROL_REPS = 200               # §5 del criterio
BOOTSTRAP_REPS = 10_000          # §4 del criterio
BOOTSTRAP_N_CAP = 250_000        # ver docstring de bootstrap_ci (conservador)

_CACHE = None                    # seteado en main / worker init

# Version de la LOGICA de medicion. Si cambia como se mide (deteccion, costos,
# control, perfiles), hay que subirla: invalida los checkpoints viejos para que no
# se mezclen resultados de dos codigos distintos, que seria peor que perderlos.
LOGIC_VERSION = 1


def set_low_priority():
    """Baja la prioridad del proceso para que el escritorio siga usable.

    Windows le da los cores al programa en foco y el backtest usa lo que sobra.
    Tarda algo mas de reloj pero permite trabajar en la maquina mientras corre.
    """
    try:
        import ctypes
        IDLE_PRIORITY_CLASS = 0x00000040
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), IDLE_PRIORITY_CLASS)
        return True
    except Exception:
        return False


def ckpt_path(cache_dir, sym, session, profile_key, tf):
    """Un archivo por job. La clave incluye TODO lo que cambia el resultado."""
    d = os.path.join(cache_dir, 'ckpt')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f'v{LOGIC_VERSION}_{tf}_{profile_key}_{sym}_{session}.pkl')


# ═══════════════════════════════════════════════════════════════════════════
# FASE A — cache de velas (proceso padre, unica vez que se habla con MT5)
# ═══════════════════════════════════════════════════════════════════════════

def fetch_with_retry(mt5, sym, tf_attr, count, want, logger,
                     tries=30, wait=8):
    """MT5 baja la historia de forma ASINCRONA: el primer pedido de un simbolo
    que todavia no esta en cache devuelve 0 velas (o unas pocas) mientras el
    terminal la descarga en background.

    Sin este reintento, 25 de 26 pares se excluirian por 'falta de historia'
    cuando la historia EXISTE — un artefacto de medicion que habria contaminado
    el universo del test entero. Cada pedido ademas empuja al terminal a seguir
    bajando, asi que reintentar es tambien lo que dispara la descarga.
    """
    best, best_n = None, 0
    for k in range(tries):
        r = mt5.copy_rates_from_pos(sym, tf_attr, 0, count)
        n = 0 if r is None else len(r)
        if n > best_n:
            best, best_n = r, n
        if best_n >= want:
            return best
        if k == 0 or (k + 1) % 5 == 0:
            logger.info(f"  {sym}: esperando descarga... {best_n}/{want} "
                        f"(intento {k+1}/{tries})")
        time.sleep(wait)
    return best


def build_cache(symbols, tf, count, cache_dir, logger):
    import MetaTrader5 as mt5
    import numpy as np
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    os.makedirs(cache_dir, exist_ok=True)
    tf_attr = getattr(mt5, TF_MAP[tf])
    manifest = {}
    for sym in symbols:
        mt5.symbol_select(sym, True)
        spec = symbol_spec(sym)
        if spec is None:
            manifest[sym] = {'error': 'symbol_info None'}
            logger.warning(f"{sym}: symbol_info None -> EXCLUIDO")
            continue
        rates = fetch_with_retry(mt5, sym, tf_attr, count, MIN_CANDLES, logger)
        n = 0 if rates is None else len(rates)
        if n < MIN_CANDLES:
            manifest[sym] = {'error': f'solo {n} velas {tf} (< {MIN_CANDLES}) '
                                      f'tras 30 reintentos'}
            logger.warning(f"{sym}: solo {n} velas {tf} tras reintentar -> EXCLUIDO")
            continue
        np.save(os.path.join(cache_dir, f'{sym}.npy'), rates)
        with open(os.path.join(cache_dir, f'{sym}.spec.json'), 'w') as f:
            json.dump(spec, f)
        d0 = datetime.utcfromtimestamp(int(rates[0]['time']))
        d1 = datetime.utcfromtimestamp(int(rates[-1]['time']))
        manifest[sym] = {'n': n, 'desde': str(d0), 'hasta': str(d1),
                         'anios': round((d1 - d0).days / 365.25, 2),
                         'commission_pips': spec['commission_pips'],
                         'commission_source': spec['commission_source']}
        logger.info(f"{sym}: {n} velas {tf} | {d0:%Y-%m-%d} -> {d1:%Y-%m-%d} "
                    f"({manifest[sym]['anios']} anios)")
    mt5.shutdown()
    with open(os.path.join(cache_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
    return manifest


def load_symbol(sym, cache_dir):
    import numpy as np
    rates = np.load(os.path.join(cache_dir, f'{sym}.npy'))
    with open(os.path.join(cache_dir, f'{sym}.spec.json')) as f:
        spec = json.load(f)
    candles = [{'open': float(r['open']), 'high': float(r['high']),
                'low': float(r['low']), 'close': float(r['close']),
                'time_unix': int(r['time'])} for r in rates]
    return candles, spec


# ═══════════════════════════════════════════════════════════════════════════
# Utilidades de medicion
# ═══════════════════════════════════════════════════════════════════════════

def atr_at(candles, idx, pip, period=14):
    lo = max(0, idx - period + 1)
    rngs = [(c['high'] - c['low']) / pip for c in candles[lo:idx + 1]]
    return stats.mean(rngs) if rngs else 0.0


def sl_tp_for(profile, candles, i, pip):
    """Devuelve (sl_pips, tp_pips) segun el perfil declarado, o None."""
    if profile['kind'] == 'fixed':
        return profile['sl_pips'], profile['tp_pips']
    a = atr_at(candles, i, pip)
    if a <= 0:
        return None
    sl = round(a * profile['sl_atr_mult'], 1)
    return sl, round(sl * profile['rr'], 1)


def net_of_costs(out, entry_i, candles, direction, spec):
    """pips brutos - comision + swap por noche efectivamente mantenida."""
    noches = (candles[out['exit_idx']]['time_unix']
              - candles[entry_i]['time_unix']) / 86400.0
    swap = (spec['swap_long_pips'] if direction == 'CALL'
            else spec['swap_short_pips']) * noches
    return out['pips'] - spec['commission_pips'] + swap


# ═══════════════════════════════════════════════════════════════════════════
# FASE B — un job = (simbolo, sesion). Corre en un worker.
# ═══════════════════════════════════════════════════════════════════════════

def run_job(job):
    sym, session, cache_dir, params, profile_key, tf, low_prio = job
    t0 = time.perf_counter()
    profile = PROFILES_F2[profile_key]

    # CHECKPOINT: si este job ya se calculo con esta misma LOGIC_VERSION, se
    # devuelve tal cual. Es lo que hace que pausar la corrida no cueste horas.
    _cp = ckpt_path(cache_dir, sym, session, profile_key, tf)
    if os.path.exists(_cp):
        try:
            with open(_cp, 'rb') as _f:
                _r = pickle.load(_f)
            _r['from_ckpt'] = True
            return _r
        except Exception:
            pass          # checkpoint corrupto -> se recalcula

    if low_prio:
        set_low_priority()

    import logging
    logging.disable(logging.CRITICAL)
    logger = logging.getLogger('f2')

    candles, spec = load_symbol(sym, cache_dir)
    pip = spec['pip']

    from src.analyzer.technical import TechnicalAnalyzer
    import src.analyzer.technical as tech_mod

    # detect_structure_signals() llama get_setup_win_rates() UNA VEZ POR VELA, y
    # esa funcion abre SQLite y corre 3 consultas contra la DB de PRODUCCION.
    # Con 14 workers x ~180 velas/seg eran miles de conexiones por segundo: los
    # workers pasaban el 66% del tiempo esperando I/O (23,7 min de CPU en 69 de
    # reloj).
    #
    # Pero el problema grave no era la velocidad: AIdan opera y ESCRIBE en esa
    # misma DB mientras el backtest corre => el valor iria cambiando durante las
    # horas de corrida y la medicion no seria reproducible.
    #
    # Se toma UN snapshot al arrancar el job y se congela. Es a la vez mas rapido
    # y mas correcto: un backtest tiene que medir contra un estado fijo.
    import src.common.db as _dbmod
    _wr_snapshot = _dbmod.get_setup_win_rates()
    _dbmod.get_setup_win_rates = lambda: _wr_snapshot

    class _FakeTuner:
        def __init__(self, *a, **k):
            pass

        def get_params(self):
            return dict(params)

    _fixed = dict(SESSIONS[session])
    session_patch = patch.object(TechnicalAnalyzer, 'get_session_info',
                                 staticmethod(lambda: dict(_fixed)))

    analyzer = TechnicalAnalyzer(logger)
    analyzer._cache_ttl = 0
    analyzer._dedup_window_sec = DEDUP_SEC[tf]

    # technical.py razona en 0.0001 por pip (esta escrito para EUR/USD). Para los
    # JPY se re-escalan los precios al espacio "1 pip = 0.0001" ANTES de pasarlos
    # al detector; los pips que salen ya son pips reales. Sin esto el detector
    # veria movimientos 100x mas chicos y casi no dispararia.
    escala = 0.0001 / pip

    # Se acumulan arrays planos, no dicts: a ~24% de velas con senal, 500k velas
    # dan ~120k trades por job y 104 jobs no entran en RAM como list-of-dict.
    tr_t, tr_neto = [], []
    n_long = 0
    n_err, first_err = 0, None
    for i in range(WARMUP, len(candles) - 1):
        sl_ = candles[max(0, i - WARMUP + 1):i + 1]
        if escala != 1.0:
            sl_ = [{**c, 'open': c['open'] * escala, 'high': c['high'] * escala,
                    'low': c['low'] * escala, 'close': c['close'] * escala}
                   for c in sl_]
        analyzer._fetch_candles = lambda s=sl_: deepcopy(s)
        analyzer._cache.clear()
        # NO se limpia _triggered_levels: el dedup tiene que seguir funcionando
        # igual que en Fase 1. Limpiarlo cambiaba la poblacion de senales.
        try:
            with patch('src.optimizer.auto_tuner.AutoTuner', _FakeTuner), \
                 patch.object(tech_mod.time, 'time',
                              return_value=candles[i]['time_unix']), \
                 session_patch:
                sigs = analyzer.detect_structure_signals(
                    min_confidence=profile['min_confidence'])
        except Exception as e:
            # FAIL-LOUD (ver mas abajo). Tragarse esto en silencio devolveria
            # "0 senales", que se leeria como "no hay edge" — es exactamente la
            # clase de bug que ya mato M15 dos semanas y SMC meses en este repo.
            n_err += 1
            if first_err is None:
                first_err = repr(e)
            continue

        for s in sigs:
            st = sl_tp_for(profile, candles, i, pip)
            if st is None:
                continue
            sl_pips, tp_pips = st
            out = simulate(i, candles, s['direction'], sl_pips, tp_pips,
                           profile['hold'], pip)
            tr_t.append(candles[i]['time_unix'])
            tr_neto.append(net_of_costs(out, i, candles, s['direction'], spec))
            n_long += (s['direction'] == 'CALL')

    # FAIL-LOUD: si el detector se rompio en mas del 5% de las velas, este job NO
    # midio nada util. Devolver 0 senales seria indistinguible de "no hay edge".
    bars = max(1, len(candles) - WARMUP - 1)
    if n_err > 0.05 * bars:
        raise RuntimeError(
            f"{sym}/{session}: el detector fallo en {n_err}/{bars} velas "
            f"({n_err/bars:.1%}). Primera excepcion: {first_err}")

    import numpy as np
    n = len(tr_neto)
    p_long = (n_long / n) if n else 0.5
    control = random_control(n, p_long, candles, spec, profile, pip, sym, session)

    _out = {
        'symbol': sym, 'session': session, 'n': n, 'n_err': n_err,
        'netos': np.asarray(tr_neto, dtype=np.float32),
        'times': np.asarray(tr_t, dtype=np.int64),
        'p_long': round(p_long, 4),
        'control': control,
        'commission_pips': spec['commission_pips'],
        'commission_source': spec['commission_source'],
        't_first': candles[WARMUP]['time_unix'],
        't_last': candles[-1]['time_unix'],
        'secs': round(time.perf_counter() - t0, 1),
        'from_ckpt': False,
    }

    try:
        with open(_cp, 'wb') as _f:
            pickle.dump(_out, _f, protocol=4)
    except Exception:
        pass              # no poder cachear no debe tumbar el job

    return _out


# ═══════════════════════════════════════════════════════════════════════════
# §5 — CONTROL DE ENTRADAS ALEATORIAS
# ═══════════════════════════════════════════════════════════════════════════

def random_control(n, p_long, candles, spec, profile, pip, sym, session):
    """Mismo n, mismo ratio long/short, mismo SL/TP/hold, mismos costos.

    Devuelve, por repeticion, (suma_neta, n) para que el padre pueda poolear
    correctamente ENTRE simbolos: pooled_rep_k = sum(sumas)/sum(enes).
    """
    if n == 0:
        return []
    rng = random.Random(f'{sym}|{session}|fase2')
    lo, hi = WARMUP, len(candles) - 2
    out = []
    for _ in range(CONTROL_REPS):
        tot = 0.0
        cnt = 0
        for _ in range(n):
            i = rng.randint(lo, hi)
            st = sl_tp_for(profile, candles, i, pip)
            if st is None:
                continue
            sl_pips, tp_pips = st
            d = 'CALL' if rng.random() < p_long else 'PUT'
            r = simulate(i, candles, d, sl_pips, tp_pips, profile['hold'], pip)
            tot += net_of_costs(r, i, candles, d, spec)
            cnt += 1
        out.append((round(tot, 3), cnt))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# FASE C — agregacion y veredicto (proceso padre)
# ═══════════════════════════════════════════════════════════════════════════

def bootstrap_ci(vals, reps=BOOTSTRAP_REPS, seed=20260817, cap=BOOTSTRAP_N_CAP):
    """CI 95% por percentiles. No aproximacion normal: el P&L es asimetrico.

    Si n > cap se bootstrapea sobre una submuestra aleatoria de tamanio cap. Eso
    ENSANCHA el CI (menos datos ⇒ mas incertidumbre) ⇒ es CONSERVADOR: hace el
    criterio §6.2 mas dificil de cumplir, nunca mas facil. Sin el cap, 10.000
    reps sobre ~3,2 M trades serian 3,2e10 draws por sesion.
    """
    import numpy as np
    v = np.asarray(vals, dtype=np.float64)
    n = v.size
    if n == 0:
        return (None, None, 0)
    rs = np.random.default_rng(seed)
    if n > cap:
        v = v[rs.choice(n, cap, replace=False)]
        n = cap
    means = np.empty(reps, dtype=np.float64)
    chunk = max(1, int(2e7 // n))       # acota memoria del gather
    done = 0
    while done < reps:
        k = min(chunk, reps - done)
        idx = rs.integers(0, n, size=(k, n))
        means[done:done + k] = v[idx].mean(axis=1)
        done += k
    means.sort()
    return (round(float(means[int(0.025 * reps)]), 4),
            round(float(means[int(0.975 * reps)]), 4), int(n))


def evaluate_session(rows):
    """Aplica las 4 condiciones de §6 a UNA sesion."""
    import numpy as np
    rows = [r for r in rows if r['n'] > 0]
    res = {'symbols': len(rows)}
    if not rows:
        res.update({'n': 0, 'veredicto': 'SIN SENALES'})
        return res

    netos = np.concatenate([r['netos'] for r in rows]).astype(np.float64)
    times = np.concatenate([r['times'] for r in rows])
    n = int(netos.size)
    res['n'] = n
    pooled = float(netos.mean())
    ci_lo, ci_hi, ci_n = bootstrap_ci(netos)
    res['ci_bootstrap_n'] = ci_n

    # (3) walk-forward TEMPORAL: corte por FECHA en el punto medio del periodo
    t0 = min(r['t_first'] for r in rows)
    t1 = max(r['t_last'] for r in rows)
    mid = t0 + (t1 - t0) / 2
    m1 = times < mid
    h1 = netos[m1]
    h2 = netos[~m1]

    # (4) control: poolear por repeticion ENTRE simbolos
    reps = min((len(r['control']) for r in rows if r['control']), default=0)
    ctrl_pooled = []
    for k in range(reps):
        tot = sum(r['control'][k][0] for r in rows if r['control'])
        cnt = sum(r['control'][k][1] for r in rows if r['control'])
        if cnt:
            ctrl_pooled.append(tot / cnt)
    ctrl_pooled.sort()
    p95 = ctrl_pooled[int(0.95 * len(ctrl_pooled))] if ctrl_pooled else None

    # bool() explicito: las comparaciones de numpy devuelven np.bool_, que json NO
    # sabe serializar (revento la corrida entera en la ultima linea, con los 84 jobs
    # ya calculados). No se usa default=str en el dump a proposito: eso lo habria
    # escondido convirtiendo el tipo raro en texto.
    c1 = bool(pooled > 0)
    c2 = bool(ci_lo is not None and ci_lo > 0)
    c3 = bool(h1.size > 0 and h2.size > 0 and h1.mean() > 0 and h2.mean() > 0)
    c4 = bool(p95 is not None and pooled > p95)

    res.update({
        'pooled_neto': round(pooled, 4),
        'ci95': [ci_lo, ci_hi],
        'mitad_1': round(float(h1.mean()), 4) if h1.size else None,
        'mitad_2': round(float(h2.mean()), 4) if h2.size else None,
        'n_mitad_1': int(h1.size), 'n_mitad_2': int(h2.size),
        'control_p95': round(p95, 4) if p95 is not None else None,
        'control_mediana': round(ctrl_pooled[len(ctrl_pooled) // 2], 4) if ctrl_pooled else None,
        'cond_1_pooled_pos': c1, 'cond_2_ci_lo_pos': c2,
        'cond_3_dos_mitades': c3, 'cond_4_supera_control': c4,
        'veredicto': 'PASA' if (c1 and c2 and c3 and c4) else 'NO PASA',
        'por_par': sorted(
            [{'symbol': r['symbol'], 'n': r['n'], 'p_long': r['p_long'],
              'avg_neto': round(float(r['netos'].mean()), 3)}
             for r in rows],
            key=lambda x: -x['avg_neto']),
    })
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='M15', choices=list(TF_MAP))
    ap.add_argument('--candles', type=int, default=500_000)
    ap.add_argument('--profile', default='live', choices=list(PROFILES_F2))
    ap.add_argument('--workers', type=int, default=14)
    ap.add_argument('--params', choices=['default', 'live'], default='live')
    ap.add_argument('--sessions', default='london,overlap,ny,off')
    ap.add_argument('--symbols', default=','.join(SYMBOLS))
    ap.add_argument('--cache-dir', default=os.path.join(ROOT, '.cache_fase2'))
    ap.add_argument('--build-cache', action='store_true')
    ap.add_argument('--low-priority', action='store_true',
                    help='corre en prioridad IDLE para poder usar la maquina')
    ap.add_argument('--reset-ckpt', action='store_true',
                    help='borra los checkpoints de esta combinacion y recalcula todo')
    ap.add_argument('--out', default=os.path.join(ROOT, 'docs', 'fase2_resultado'))
    a = ap.parse_args()

    # setup_logger() deja el logger en CRITICAL + NullHandler (el de Fase 1 no
    # queria ruido). Aca la corrida dura horas => hace falta ver el progreso.
    import logging
    logger = setup_logger()
    logger.setLevel(logging.INFO)
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%H:%M:%S'))
    logger.addHandler(_h)

    assert_sessions_match_prod()           # falla fuerte si prod cambio la tabla

    cache_dir = os.path.join(a.cache_dir, f'{a.tf}_{a.candles}')
    syms = [s.strip().upper() for s in a.symbols.split(',') if s.strip()]

    if a.build_cache or not os.path.exists(os.path.join(cache_dir, 'manifest.json')):
        logger.info(f"FASE A — bajando velas {a.tf} x{a.candles} a {cache_dir}")
        build_cache(syms, a.tf, a.candles, cache_dir, logger)

    with open(os.path.join(cache_dir, 'manifest.json')) as f:
        manifest = json.load(f)
    usables = [s for s in syms if 'error' not in manifest.get(s, {'error': 'sin cache'})]
    excluidos = {s: manifest.get(s, {}).get('error', 'sin cache')
                 for s in syms if s not in usables}

    # §2: las exclusiones se reportan ANTES de mirar cualquier resultado
    logger.info(f"UNIVERSO: {len(usables)} de {len(syms)} pares usables")
    for s, why in excluidos.items():
        logger.info(f"  EXCLUIDO {s}: {why}")

    sessions = [s.strip() for s in a.sessions.split(',') if s.strip()]
    # OJO: load_live_params devuelve (params, diff), no el dict pelado.
    if a.params == 'live':
        params, params_diff = load_live_params(logger)
        logger.info(f"params live: {len(params_diff)} claves distintas del default")
    else:
        from src.optimizer.auto_tuner import DEFAULT_PARAMS
        params, params_diff = dict(DEFAULT_PARAMS), {}

    if a.reset_ckpt:
        import glob as _glob
        _pat = os.path.join(cache_dir, 'ckpt',
                            f'v{LOGIC_VERSION}_{a.tf}_{a.profile}_*.pkl')
        _n = 0
        for _f in _glob.glob(_pat):
            os.remove(_f); _n += 1
        logger.info(f"--reset-ckpt: {_n} checkpoints borrados")

    if a.low_priority:
        logger.info("prioridad IDLE (se puede usar la maquina; tarda mas de reloj)"
                    if set_low_priority() else "no pude bajar la prioridad")

    _hechos = sum(1 for ses in sessions for sym in usables
                  if os.path.exists(ckpt_path(cache_dir, sym, ses, a.profile, a.tf)))
    jobs = [(sym, ses, cache_dir, params, a.profile, a.tf, a.low_priority)
            for ses in sessions for sym in usables]
    if _hechos:
        logger.info(f"CHECKPOINT: {_hechos} de {len(jobs)} jobs ya calculados "
                    f"-> se reusan, no se recalculan")
    logger.info(f"FASE B — {len(jobs)} jobs ({len(usables)} pares x {len(sessions)} "
                f"sesiones), {a.workers} workers, perfil={a.profile}")

    t0 = time.perf_counter()
    results = []
    with Pool(processes=a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(run_job, jobs), 1):
            results.append(r)
            el = time.perf_counter() - t0
            eta = el / i * (len(jobs) - i)
            _tag = 'ckpt' if r.get('from_ckpt') else f"{r['secs']}s"
            logger.info(f"[{i}/{len(jobs)}] {r['symbol']}/{r['session']} "
                        f"n={r['n']} ({_tag}) | ETA {eta/3600:.1f} h")

    logger.info("FASE C — agregando y evaluando")
    por_sesion = {}
    for ses in sessions:
        rows = [r for r in results if r['session'] == ses]
        por_sesion[ses] = evaluate_session(rows)

    veredictos = [v['veredicto'] for v in por_sesion.values()]
    if all(v == 'PASA' for v in veredictos):
        final = 'PASA'
    elif any(v == 'PASA' for v in veredictos):
        final = 'NO CONCLUYENTE (no pasa en las 4 sesiones)'
    else:
        final = 'NO PASA'

    out = {
        'criterio': 'docs/fase2_criterio_declarado.md (56bbba4, d631703, 2846de6)',
        'corrida': {'tf': a.tf, 'candles': a.candles, 'perfil': a.profile,
                    'params': a.params, 'workers': a.workers,
                    'sesiones': sessions, 'pares_usables': len(usables),
                    'horas': round((time.perf_counter() - t0) / 3600, 2)},
        'excluidos': excluidos,
        'manifest': manifest,
        'por_sesion': por_sesion,
        'veredicto_final': final,
    }
    path = f'{a.out}_{a.tf}_{a.profile}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print('\n' + '=' * 72)
    print(f'FASE 2 — {a.tf} / perfil {a.profile} / {len(usables)} pares')
    print('=' * 72)
    for ses, v in por_sesion.items():
        if v.get('n', 0) == 0:
            print(f'{ses:9} SIN SENALES')
            continue
        print(f'{ses:9} n={v["n"]:>7}  pooled={v["pooled_neto"]:+.3f}p  '
              f'CI95=[{v["ci95"][0]:+.3f}, {v["ci95"][1]:+.3f}]  '
              f'ctrl_p95={v["control_p95"]:+.3f}  -> {v["veredicto"]}')
        print(f'{"":9}   mitades: {v["mitad_1"]:+.3f} / {v["mitad_2"]:+.3f}   '
              f'cond: {int(v["cond_1_pooled_pos"])}{int(v["cond_2_ci_lo_pos"])}'
              f'{int(v["cond_3_dos_mitades"])}{int(v["cond_4_supera_control"])}')
    print('-' * 72)
    print(f'VEREDICTO FINAL: {final}')
    print(f'json: {path}')
    print('=' * 72)


if __name__ == '__main__':
    main()
