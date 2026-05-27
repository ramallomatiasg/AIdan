"""
exit_advisor.py — Live Exit Advisor (v3.36.0 Fase 2).

Segunda opinion LLM para el Position Manager: dada una posicion abierta en zona
ambigua (soft-expiry, ni claramente ganando ni perdiendo), recomienda
HOLD / CLOSE / TIGHTEN con reasoning.

Es ASESOR, no autoridad:
  - CLOSE siempre se respeta (conservador).
  - HOLD se respeta pero queda capeado por MAX_HOLD (lo enforza el manager).
  - TIGHTEN sugiere mover SL a BE (lo aplica el trailing thread / manager).
  - NO puede ensanchar SL, subir lote, ni pasar MAX_HOLD.

Fallback chain: Gemma local (Ollama) -> Groq llama-3.1-8b -> None (manager usa reglas).
GPU-aware: si GPU ocupada, skip (no es critical-path).
"""
import logging
import json
import requests
from src.common.config import Config

logger = logging.getLogger("exit_advisor")

EXIT_TIMEOUT = 15  # segundos max (warm ~3s)
GROQ_TIMEOUT = 12
OLLAMA_URL = Config.OLLAMA_URL or "http://localhost:11434"
# Reusa el modelo del signal_audit (qwen2.5:7b): JSON breve, tarea de validacion.
GEMMA_MODEL = Config.get_llm_model('signal_audit')

EXIT_PROMPT_TEMPLATE = """Eres un gestor de salidas de trading para EUR/USD M5.
Hay una posicion ABIERTA. Decide si MANTENERLA, CERRARLA o proteger ganancia.

Posicion:
- Direccion: {direction}
- Entrada: {fill_price}
- Precio actual: {current_price}
- P&L actual: {progress_pips:+.1f} pips
- Mejor momento alcanzado (HWM): {hwm_pips:+.1f} pips ({tp_pct:.0%} del TP)
- Distancia al TP: {tp_pips:.1f}p | al SL: {sl_pips:.1f}p
- Tiempo en trade: {time_in_trade_min:.0f} min (expiry base {base_expiry_min:.0f} min)
- Momentum reciente (a favor=+): {momentum_aligned_pips:+.1f} pips
- ATR actual: {atr_pips:.1f}p
- Tendencia M5: {trend} | HTF bias: {htf_bias}
- Ultimas velas (O/H/L/C): {recent_candles}

Responde SOLO JSON valido, sin texto extra:
{{"action": "HOLD", "confidence": 60, "reasoning": "1 linea"}}

Reglas de decision:
- HOLD: el move puede desarrollarse, momentum a favor o neutral, vale esperar.
- CLOSE: el move se agoto / se da vuelta / momentum en contra claro / mejor tomar lo que hay.
- TIGHTEN: va ganando pero quiero proteger (mover SL a break-even).
- action: "HOLD" | "CLOSE" | "TIGHTEN"
- confidence: 0-100 (que tan seguro estas)
- reasoning: maximo 1 oracion
"""

_VALID_ACTIONS = ('HOLD', 'CLOSE', 'TIGHTEN')


def _gpu_busy() -> bool:
    try:
        from src.common.gpu_monitor import should_pause_llm
        return bool(should_pause_llm())
    except Exception:
        return False


def _parse(result_text: str):
    """Parsea y valida el JSON del LLM. Devuelve dict normalizado o None."""
    try:
        txt = result_text.strip()
        if '```' in txt:
            txt = txt.split('```')[1]
            if txt.startswith('json'):
                txt = txt[4:]
        result = json.loads(txt.strip())
        action = str(result.get('action', 'HOLD')).upper().strip()
        if action not in _VALID_ACTIONS:
            # Normalizar variantes
            if 'CLOSE' in action or 'SELL' in action or 'EXIT' in action:
                action = 'CLOSE'
            elif 'TIGHT' in action or 'BE' in action or 'TRAIL' in action:
                action = 'TIGHTEN'
            else:
                action = 'HOLD'
        conf = int(result.get('confidence', 50))
        conf = max(0, min(100, conf))
        reasoning = str(result.get('reasoning', ''))[:200]
        return {'action': action, 'confidence': conf, 'reasoning': reasoning}
    except Exception as e:
        logger.debug(f"exit_advisor parse error: {e} | raw={result_text[:150]}")
        return None


def _ask_gemma(prompt: str):
    try:
        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': GEMMA_MODEL,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
                'keep_alive': '2m',
                'options': {'temperature': 0.2, 'top_p': 0.9, 'num_predict': 150},
            },
            timeout=EXIT_TIMEOUT,
        )
        if response.status_code != 200:
            return None
        return _parse(response.json().get('response', ''))
    except Exception as e:
        logger.debug(f"exit_advisor Gemma error: {e}")
        return None


def _ask_groq(prompt: str):
    try:
        keys = Config.GROQ_API_KEYS if hasattr(Config, 'GROQ_API_KEYS') else [getattr(Config, 'GROQ_API_KEY', '')]
        keys = [k for k in keys if k]
        for i, api_key in enumerate(keys):
            try:
                resp = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    json={
                        'model': getattr(Config, 'GROQ_MODEL_CHAT', None) or 'llama-3.1-8b-instant',
                        'messages': [
                            {'role': 'system', 'content': 'Eres un gestor de salidas de trading EUR/USD. Responde SOLO JSON valido.'},
                            {'role': 'user', 'content': prompt},
                        ],
                        'temperature': 0.2,
                        'max_tokens': 150,
                    },
                    timeout=GROQ_TIMEOUT,
                )
                if resp.status_code == 200:
                    return _parse(resp.json()['choices'][0]['message']['content'])
                elif resp.status_code == 429 and i < len(keys) - 1:
                    continue
                else:
                    return None
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                if i < len(keys) - 1:
                    continue
                return None
    except Exception as e:
        logger.debug(f"exit_advisor Groq error: {e}")
    return None


def get_exit_advice(ctx: dict) -> dict | None:
    """Consulta al LLM una recomendacion de salida.

    Args:
        ctx: dict con keys: direction, fill_price, current_price, progress_pips,
             hwm_pips, tp_pct, tp_pips, sl_pips, time_in_trade_min, base_expiry_min,
             momentum_aligned_pips, atr_pips, trend, htf_bias, recent_candles

    Returns:
        dict {action: HOLD|CLOSE|TIGHTEN, confidence: 0-100, reasoning: str, source: str}
        o None si no disponible (GPU busy / timeout / error) -> caller usa solo reglas.
    """
    if _gpu_busy():
        logger.debug("exit_advisor: skip (GPU busy)")
        return None

    # Defaults para campos faltantes
    safe = {
        'direction': ctx.get('direction', 'N/A'),
        'fill_price': ctx.get('fill_price', 0),
        'current_price': ctx.get('current_price', 0),
        'progress_pips': ctx.get('progress_pips', 0.0),
        'hwm_pips': ctx.get('hwm_pips', 0.0),
        'tp_pct': ctx.get('tp_pct', 0.0),
        'tp_pips': ctx.get('tp_pips', 0.0),
        'sl_pips': ctx.get('sl_pips', 0.0),
        'time_in_trade_min': ctx.get('time_in_trade_min', 0.0),
        'base_expiry_min': ctx.get('base_expiry_min', 15.0),
        'momentum_aligned_pips': ctx.get('momentum_aligned_pips', 0.0),
        'atr_pips': ctx.get('atr_pips', 0.0),
        'trend': ctx.get('trend', 'unknown'),
        'htf_bias': ctx.get('htf_bias', 'neutral'),
        'recent_candles': ctx.get('recent_candles', 'n/a'),
    }
    try:
        prompt = EXIT_PROMPT_TEMPLATE.format(**safe)
    except Exception as e:
        logger.debug(f"exit_advisor prompt format error: {e}")
        return None

    # Gemma local primero, Groq fallback
    advice = _ask_gemma(prompt)
    source = 'gemma'
    if advice is None:
        advice = _ask_groq(prompt)
        source = 'groq'
    if advice is None:
        return None

    advice['source'] = source
    logger.info(f"Exit advice [{source}]: {advice['action']} (conf {advice['confidence']}) — {advice['reasoning']}")
    return advice
