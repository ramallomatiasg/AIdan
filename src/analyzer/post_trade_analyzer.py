"""
Post-Trade Analyzer — Gemma 4 analiza cada trade cerrado para generar insights.

Despues de que un trade se cierra (win/loss/break_even), Gemma evalua:
- Calidad de entrada y salida
- Precision de noticias (si aplica)
- Timing del trade
- Lecciones accionables

Los insights se guardan en DB y alimentan al learning engine.
"""

import logging
import json
import requests
from src.common.config import Config

logger = logging.getLogger("analyzer")

ANALYSIS_TIMEOUT = 60  # v3.22.0: 60s para permitir modelos mas grandes via env override
OLLAMA_URL = Config.OLLAMA_URL or "http://localhost:11434"
GEMMA_MODEL = Config.GEMMA_MODEL or "gemma4"
# v3.22.0 — modelo dedicado para post-trade.
# Default GEMMA_MODEL (qwen2.5:7b) por latencia razonable.
# Para usar deepseek-r1:14b: set POST_TRADE_MODEL=deepseek-r1:14b en .env.
# CAVEAT: deepseek-r1:14b causa OOM cuando AIdan corre en paralelo (qwen 7b + dr1 14b
# = 14GB VRAM, no caben ambos). Usar solo offline (rebuild AIdan stopped).
import os
POST_TRADE_MODEL = os.getenv('POST_TRADE_MODEL', '') or GEMMA_MODEL

POST_TRADE_PROMPT = """Eres un analista post-trade para EUR/USD en timeframe M5.
Analiza este trade completado y genera insights accionables.

Trade completado:
- Resultado: {result} ({pips} pips)
- Direccion: {direction}
- Trigger: {trigger_type}
- Entry: {entry_price}, Exit: {exit_price}
- SL: {stop_loss}, TP: {take_profit}
- SL pips: {sl_pips}p, TP pips: {tp_pips}p
- Sesion: {session}
- RSI al entrar: {rsi}
- Tendencia M5: {trend} ({trend_strength})
- HTF bias: {htf_bias}
- Volatilidad: {volatility}
- Noticia/Evento: {news_title}
- Confianza original: {confidence}%
- Duracion: {duration_min} minutos
- MT5 P&L: ${mt5_pnl}

Responde SOLO en JSON valido, sin texto adicional:
{{"entry_quality": "good", "exit_quality": "good", "news_accuracy": "neutral", "timing_assessment": "acceptable", "key_lesson": "1 linea accionable", "confidence_was": "accurate", "suggested_adjustment": "descripcion corta", "sl_action": "keep", "recommended_sl_pips": 0, "recommended_tp_pips": 0}}

Reglas:
- entry_quality: "good" | "fair" | "poor"
- exit_quality: "good" | "fair" | "poor"
- news_accuracy: "accurate" | "neutral" | "inaccurate" (solo relevante si trigger es news/calendar)
- timing_assessment: "optimal" | "acceptable" | "poor"
- key_lesson: maximo 1 oracion con leccion accionable para mejorar
- confidence_was: "overestimated" | "accurate" | "underestimated"
- suggested_adjustment: que cambiar en parametros o logica (max 1 oracion)
- sl_action: "widen" | "tighten" | "keep" — direccion sugerida para el SL (estructural)
- recommended_sl_pips: numero (0-15) — SL ideal en pips para este tipo de setup. 0 = "keep current"
- recommended_tp_pips: numero (0-30) — TP ideal en pips para este tipo de setup. 0 = "keep current"

Para sl_action y recommended_sl_pips piensa: si el trade perdio por SL muy ajustado (price hizo whipsaw), sugiere "widen" con un valor mayor. Si gano poco porque el TP estaba muy lejos, sugiere "tighten" con valor menor. Si SL/TP estuvieron OK, "keep" y 0.
"""


def analyze_closed_trade(trade_data: dict) -> dict | None:
    """
    Analiza un trade cerrado usando Gemma 4.

    Args:
        trade_data: dict con keys del trade (result, pips, direction, entry_price,
                    exit_price, stop_loss, take_profit, session, rsi, trend, etc.)

    Returns:
        dict con analisis o None si timeout/error
    """
    try:
        # Defaults para campos faltantes
        ctx = {
            'result': trade_data.get('result', 'unknown'),
            'pips': round(trade_data.get('pips', 0), 1),
            'direction': trade_data.get('direction', 'N/A'),
            'trigger_type': trade_data.get('trigger_type', 'unknown'),
            'entry_price': trade_data.get('entry_price', 0),
            'exit_price': trade_data.get('exit_price', 0),
            'stop_loss': trade_data.get('stop_loss', 0),
            'take_profit': trade_data.get('take_profit', 0),
            'sl_pips': round(trade_data.get('sl_pips', 0), 1),
            'tp_pips': round(trade_data.get('tp_pips', 0), 1),
            'session': trade_data.get('session', 'unknown'),
            'rsi': round(trade_data.get('rsi', 50), 1),
            'trend': trade_data.get('trend', 'unknown'),
            'trend_strength': trade_data.get('trend_strength', 'N/A'),
            'htf_bias': trade_data.get('htf_bias', 'neutral'),
            'volatility': trade_data.get('volatility', 'normal'),
            'news_title': trade_data.get('news_title', 'N/A'),
            'confidence': round(trade_data.get('confidence', 50), 1),
            'duration_min': round(trade_data.get('duration_min', 0), 1),
            'mt5_pnl': round(trade_data.get('mt5_pnl', 0), 2),
        }

        prompt = POST_TRADE_PROMPT.format(**ctx)

        # GPU-aware: skip si otro proceso (juego, render) usa GPU pesado
        try:
            from src.common.gpu_monitor import should_pause_llm, get_status_summary
            if should_pause_llm():
                logger.info(f"Post-trade analysis: skipped, {get_status_summary()}")
                return None
        except Exception:
            pass

        # v3.22.0: usa POST_TRADE_MODEL (deepseek-r1:14b) si disponible, fallback a Gemma
        active_model = POST_TRADE_MODEL or GEMMA_MODEL
        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': active_model,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
                'keep_alive': '5m',
                'options': {
                    'temperature': 0.3,
                    'top_p': 0.9,
                    'num_predict': 400,
                    'num_ctx': 2048,  # context limitado para que 14b quepa en RAM
                }
            },
            timeout=ANALYSIS_TIMEOUT
        )

        # Fallback: si deepseek-r1 falla, retry con qwen2.5:7b
        if response.status_code != 200 and active_model != GEMMA_MODEL:
            logger.warning(f"Post-trade {active_model} HTTP {response.status_code}, fallback to {GEMMA_MODEL}")
            response = requests.post(
                f'{OLLAMA_URL}/api/generate',
                json={
                    'model': GEMMA_MODEL, 'prompt': prompt, 'stream': False, 'format': 'json',
                    'keep_alive': '2m',
                    'options': {'temperature': 0.3, 'top_p': 0.9, 'num_predict': 300}
                },
                timeout=ANALYSIS_TIMEOUT
            )

        if response.status_code != 200:
            logger.warning(f"Post-trade analysis HTTP error: {response.status_code}")
            return None

        result_text = response.json().get('response', '')
        logger.debug(f"Post-trade raw: {result_text[:400]}")

        # v3.22.0 — strip DeepSeek-R1 <think> tags si presente
        if '<think>' in result_text:
            # Mantener solo despues de </think>
            after_think = result_text.split('</think>')
            if len(after_think) > 1:
                result_text = after_think[-1].strip()

        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # A veces el JSON está dentro de markdown code blocks ```json ... ```
            import re
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result_text)
            if match:
                result = json.loads(match.group())
            else:
                raise

        # Validar y normalizar campos
        valid_qualities = ('good', 'fair', 'poor')
        valid_accuracy = ('accurate', 'neutral', 'inaccurate')
        valid_timing = ('optimal', 'acceptable', 'poor')
        valid_confidence = ('overestimated', 'accurate', 'underestimated')
        valid_sl_action = ('widen', 'tighten', 'keep')

        # v3.15.0 — campos estructurados de SL/TP recommendation
        try:
            rec_sl = float(result.get('recommended_sl_pips', 0) or 0)
            rec_sl = max(0, min(15, rec_sl))  # clamp 0-15
        except (TypeError, ValueError):
            rec_sl = 0.0
        try:
            rec_tp = float(result.get('recommended_tp_pips', 0) or 0)
            rec_tp = max(0, min(30, rec_tp))  # clamp 0-30
        except (TypeError, ValueError):
            rec_tp = 0.0
        sl_action = result.get('sl_action', 'keep')
        if sl_action not in valid_sl_action:
            sl_action = 'keep'

        analysis = {
            'entry_quality': result.get('entry_quality', 'fair') if result.get('entry_quality') in valid_qualities else 'fair',
            'exit_quality': result.get('exit_quality', 'fair') if result.get('exit_quality') in valid_qualities else 'fair',
            'news_accuracy': result.get('news_accuracy', 'neutral') if result.get('news_accuracy') in valid_accuracy else 'neutral',
            'timing_assessment': result.get('timing_assessment', 'acceptable') if result.get('timing_assessment') in valid_timing else 'acceptable',
            'key_lesson': str(result.get('key_lesson', ''))[:300],
            'confidence_was': result.get('confidence_was', 'accurate') if result.get('confidence_was') in valid_confidence else 'accurate',
            'suggested_adjustment': str(result.get('suggested_adjustment', ''))[:300],
            # v3.15.0 — structured SL/TP feedback for actionable learning
            'sl_action': sl_action,
            'recommended_sl_pips': rec_sl,
            'recommended_tp_pips': rec_tp,
            # Pass trade context for downstream aggregation
            'trigger_type': trade_data.get('trigger_type', ''),
        }

        logger.info(f"Post-trade analysis: entry={analysis['entry_quality']} exit={analysis['exit_quality']} "
                     f"timing={analysis['timing_assessment']} sl_action={sl_action} rec_sl={rec_sl}p rec_tp={rec_tp}p | {analysis['key_lesson']}")
        return analysis

    except requests.exceptions.Timeout:
        logger.warning(f"Post-trade analysis timeout ({ANALYSIS_TIMEOUT}s)")
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Post-trade analysis: Ollama not reachable")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Post-trade analysis: invalid JSON — {e}")
        return None
    except Exception as e:
        logger.error(f"Post-trade analysis error: {e}")
        return None
