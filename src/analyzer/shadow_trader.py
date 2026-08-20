"""
shadow_trader.py — v3.60.0: "operador" LLM en PAPEL (Groq). Decide, NUNCA opera.

Que es: la forma correcta de probar la idea del user ("un LLM que controle todo,
cierre antes, abra, vea oportunidades") sin repetir los errores ya pagados. El
LLM ve lo mismo que AIdan (numeros del mercado + posiciones abiertas) y toma
decisiones que SOLO se registran en `shadow_trader_log`:

  - kind='open'  : cada SHADOW_TRADER_SCAN_SEC (default 900s) se le pregunta si
                   abriria CALL/PUT/NONE ahora, a evaluarse a +45 min neto de
                   friccion. Se registra TODO, incluido NONE (la frecuencia de
                   accion tambien es dato).
  - kind='manage': cada ciclo (default 300s), por cada posicion AIdan abierta,
                   HOLD o CLOSE con el PnL/pips del momento. El scorer compara
                   despues contra como termino el trade de verdad.

Que NO hace, por construccion: este modulo no importa ni llama NADA que mande
ordenes (no open_position, no close, no order_send — hay un test que lo
verifica sobre el fuente). Lee posiciones con positions_get (read-only).

Por que Groq y no local: gpt-oss-120b (el analitico de v3.56.0) es 4x mas
grande que lo que entra en la GPU del user, gratis, y ya cableado con rotacion
de keys. Volumen: ~100-300 llamadas/dia, dentro del free tier.

Principio anti-loro (leccion v3.53.7/v3.57.0): al modelo se le pasan NUMEROS
(precio, RSI, ATR, tendencia, PnL de la posicion), nunca veredictos propios
que pueda repetir.

Evidencia previa en contra (por que nace en shadow y con gate): cada vez que
se midio a un LLM decidiendo direccion aca, perdio (news anti-skill: hit 53%
vs drift 63%; post-trade "no juzga, etiqueta"). Este experimento existe para
darle al LLM la oportunidad de refutar eso CON registro limpio, no para asumir
que un modelo mas grande es distinto.

Gate pre-declarado (leer con tools/score_shadow_trader.py):
  - open direccionales: n>=25 con outcome; media Y mediana de pips netos > 0.
    A n>=40 sin pasar => SHADOW_TRADER_MODE=off, no buscarle la vuelta.
  - manage CLOSE: n>=15; "ahorro" neto > 0 (pips al decidir vs pips finales).
Perillas (env, sin rebuild): SHADOW_TRADER_MODE=off|shadow,
SHADOW_TRADER_CYCLE_SEC, SHADOW_TRADER_SCAN_SEC.
"""
import json
import logging
import time

import requests

from src.common.config import Config

logger = logging.getLogger('shadow_trader')

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_TIMEOUT = 20
OPEN_HORIZON_MIN = 45   # mismo horizonte que m15/shadow book, para comparar
FRICTION_PIPS = 1.3     # comision round-trip declarada del proyecto
PIP = 0.0001
MAX_TICK_AGE_S = 900    # tick mas viejo que esto = mercado cerrado/finde -> skip

_last_open_scan = 0.0

_SYSTEM = (
    'You are an EUR/USD intraday trader making PAPER decisions that will be '
    'measured against reality. You never execute anything. Be decisive but '
    'honest: NONE/HOLD are valid answers. Respond ONLY with valid JSON, no '
    'markdown, no explanation outside the JSON.'
)


def _ask_groq(prompt):
    """(decision_dict|None, latency_ms, model). Rotacion de keys como pre_planner."""
    keys = [k for k in (getattr(Config, 'GROQ_API_KEYS', None)
                        or [getattr(Config, 'GROQ_API_KEY', '')]) if k]
    if not keys:
        logger.warning("shadow trader: sin API keys de Groq")
        return None, 0, ''
    model = getattr(Config, 'GROQ_MODEL', None) or 'openai/gpt-oss-120b'
    t0 = time.time()
    for i, key in enumerate(keys):
        try:
            resp = requests.post(
                GROQ_URL,
                headers={'Authorization': f'Bearer {key}',
                         'Content-Type': 'application/json'},
                json={
                    'model': model,
                    'messages': [{'role': 'system', 'content': _SYSTEM},
                                 {'role': 'user', 'content': prompt}],
                    'temperature': 0.2,
                    'max_tokens': 1200,
                    'reasoning_effort': getattr(Config, 'GROQ_REASONING_EFFORT', 'low'),
                },
                timeout=GROQ_TIMEOUT)
            if resp.status_code == 200:
                text = resp.json()['choices'][0]['message']['content']
                return _parse_json(text), int((time.time() - t0) * 1000), model
            if resp.status_code == 429 and i < len(keys) - 1:
                continue
            logger.warning(f"shadow trader Groq HTTP {resp.status_code}: {resp.text[:150]}")
            return None, int((time.time() - t0) * 1000), model
        except Exception as e:
            logger.warning(f"shadow trader Groq key {i + 1}: {e}")
    return None, int((time.time() - t0) * 1000), model


def _parse_json(text):
    """Parse defensivo: JSON directo, o envuelto en ```...```, o None (jamas explota)."""
    if not text:
        return None
    t = text.strip()
    if '```' in t:
        parts = t.split('```')
        t = parts[1] if len(parts) > 1 else t
        if t.startswith('json'):
            t = t[4:]
        t = t.strip()
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else None
    except (ValueError, TypeError):
        # ultimo intento: primer {...} del texto
        a, b = t.find('{'), t.rfind('}')
        if 0 <= a < b:
            try:
                out = json.loads(t[a:b + 1])
                return out if isinstance(out, dict) else None
            except (ValueError, TypeError):
                pass
    return None


def _norm_decision(d, valid):
    """Normaliza la respuesta del LLM a (action, confidence, reasoning) o None."""
    if not d:
        return None
    action = str(d.get('action', '')).strip().upper()
    if action not in valid:
        return None
    try:
        conf = max(0.0, min(100.0, float(d.get('confidence', 0))))
    except (TypeError, ValueError):
        conf = 0.0
    reasoning = str(d.get('reasoning', ''))[:250]
    return action, conf, reasoning


def _market_block(ms):
    """Solo NUMEROS del estado de mercado (anti-loro: sin veredictos propios)."""
    keys = ['price', 'trend', 'trend_strength', 'rsi', 'rsi_zone', 'momentum',
            'avg_range_pips', 'volatility', 'session', 'efficiency_ratio']
    lines = []
    for k in keys:
        v = ms.get(k)
        if v is not None and v != '':
            lines.append(f"{k}: {v}")
    return '\n'.join(lines)


def _build_open_prompt(ms):
    return (
        "EUR/USD M5 market state right now:\n" + _market_block(ms) +
        f"\n\nWould you open a trade NOW? It will be evaluated at the price "
        f"{OPEN_HORIZON_MIN} minutes from now, minus {FRICTION_PIPS} pips friction. "
        "Only answer CALL or PUT if you expect the move to beat that friction; "
        "otherwise NONE.\n"
        'Answer JSON: {"action": "CALL"|"PUT"|"NONE", "confidence": 0-100, '
        '"reasoning": "<max 200 chars>"}')


def _build_manage_prompt(pos, ms):
    return (
        "You have an open EUR/USD position (paper review):\n"
        f"direction: {pos['direction']}\n"
        f"age_minutes: {pos['age_min']:.0f}\n"
        f"unrealized_pips: {pos['pips']:+.1f}\n"
        f"distance_to_stop_pips: {pos['sl_dist']}\n"
        f"distance_to_target_pips: {pos['tp_dist']}\n"
        "\nMarket state right now:\n" + _market_block(ms) +
        "\n\nDecide: CLOSE now at the current price, or HOLD and let the "
        "stop/target/expiry play out.\n"
        'Answer JSON: {"action": "CLOSE"|"HOLD", "confidence": 0-100, '
        '"reasoning": "<max 200 chars>"}')


def _aidan_positions(mt5_exec):
    """Posiciones AIdan abiertas, como dicts (read-only). [] si MT5 no esta."""
    out = []
    try:
        if not mt5_exec or not mt5_exec.is_ready() or not mt5_exec._mt5:
            return out
        from src.broker.mt5_executor import MAGIC_NUMBER
        tick = mt5_exec._mt5.symbol_info_tick("EURUSD")
        if not tick:
            return out
        for p in (mt5_exec._mt5.positions_get(group="*") or []):
            if p.magic != MAGIC_NUMBER:
                continue
            is_call = (p.type == 0)  # 0=BUY
            cur = tick.bid if is_call else tick.ask
            pips = (cur - p.price_open) / PIP if is_call else (p.price_open - cur) / PIP
            sl_dist = round(abs(cur - p.sl) / PIP, 1) if p.sl else None
            tp_dist = round(abs(p.tp - cur) / PIP, 1) if p.tp else None
            out.append({
                'ticket': int(p.ticket),
                'direction': 'CALL' if is_call else 'PUT',
                'price': cur,
                'pips': round(pips, 1),
                'pnl': round(float(p.profit), 2),
                'age_min': max(0.0, (tick.time - p.time) / 60.0),
                'sl_dist': sl_dist,
                'tp_dist': tp_dist,
            })
    except Exception as e:
        logger.warning(f"shadow trader positions: {e}")
    return out


def _tick_is_fresh(mt5_exec):
    """False = mercado cerrado/finde o MT5 caido -> no gastar quota en data stale."""
    try:
        if not mt5_exec or not mt5_exec.is_ready() or not mt5_exec._mt5:
            return False
        tick = mt5_exec._mt5.symbol_info_tick("EURUSD")
        if not tick or not getattr(tick, 'time', 0):
            return False
        # tick.time es hora SERVIDOR; compararlo contra time.time() directo
        # daria falsos "stale" por el offset UTC+3 del broker. El truco barato:
        # un tick al dia de hoy con menos de MAX_TICK_AGE_S + 4h de edad aparente
        # cubre cualquier offset de server razonable sin pedirle nada mas a MT5.
        age = abs(time.time() - tick.time)
        return age < (MAX_TICK_AGE_S + 4 * 3600)
    except Exception:
        return False


def run_cycle(market_state, mt5_exec):
    """Un ciclo del shadow trader. Llamar cada SHADOW_TRADER_CYCLE_SEC.
    Devuelve un resumen corto para el log del caller, o None si no hizo nada."""
    global _last_open_scan

    if not market_state or (market_state.get('price') or 0) <= 0:
        return None
    if market_state.get('source') == 'fallback':
        return None
    if not _tick_is_fresh(mt5_exec):
        return None

    from src.common.db import log_shadow_trader_decision

    done = []

    # (1) MANAGE: cada posicion AIdan abierta
    for pos in _aidan_positions(mt5_exec):
        d, lat, model = _ask_groq(_build_manage_prompt(pos, market_state))
        norm = _norm_decision(d, ('CLOSE', 'HOLD'))
        if norm is None:
            logger.warning(f"shadow trader: manage #{pos['ticket']} respuesta invalida")
            continue
        action, conf, why = norm
        log_shadow_trader_decision(
            kind='manage', decision=action, ticket=pos['ticket'],
            direction=pos['direction'], price=pos['price'],
            pips_at_decision=pos['pips'], pnl_at_decision=pos['pnl'],
            age_min=round(pos['age_min'], 1), confidence=conf,
            reasoning=why, model=model, latency_ms=lat)
        done.append(f"manage #{pos['ticket']} {action}")

    # (2) OPEN scan: throttled aparte (default 900s)
    scan_sec = getattr(Config, 'SHADOW_TRADER_SCAN_SEC', 900)
    if (time.time() - _last_open_scan) >= scan_sec:
        _last_open_scan = time.time()
        d, lat, model = _ask_groq(_build_open_prompt(market_state))
        norm = _norm_decision(d, ('CALL', 'PUT', 'NONE'))
        if norm is None:
            logger.warning("shadow trader: open scan respuesta invalida")
        else:
            action, conf, why = norm
            log_shadow_trader_decision(
                kind='open', decision=action,
                direction=action if action in ('CALL', 'PUT') else None,
                price=market_state.get('price'), confidence=conf,
                horizon_min=OPEN_HORIZON_MIN, reasoning=why,
                model=model, latency_ms=lat)
            done.append(f"open {action}")

    return ' | '.join(done) if done else None
