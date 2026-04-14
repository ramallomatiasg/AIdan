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

ANALYSIS_TIMEOUT = 30  # mas tiempo que audit (analisis mas complejo)
OLLAMA_URL = Config.OLLAMA_URL or "http://localhost:11434"
GEMMA_MODEL = Config.GEMMA_MODEL or "gemma4"

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
{{"entry_quality": "good", "exit_quality": "good", "news_accuracy": "neutral", "timing_assessment": "acceptable", "key_lesson": "1 linea accionable", "confidence_was": "accurate", "suggested_adjustment": "descripcion corta"}}

Reglas:
- entry_quality: "good" | "fair" | "poor"
- exit_quality: "good" | "fair" | "poor"
- news_accuracy: "accurate" | "neutral" | "inaccurate" (solo relevante si trigger es news/calendar)
- timing_assessment: "optimal" | "acceptable" | "poor"
- key_lesson: maximo 1 oracion con leccion accionable para mejorar
- confidence_was: "overestimated" | "accurate" | "underestimated"
- suggested_adjustment: que cambiar en parametros o logica (max 1 oracion)
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

        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': GEMMA_MODEL,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
                'options': {
                    'temperature': 0.3,
                    'top_p': 0.9,
                    'num_predict': 300,
                }
            },
            timeout=ANALYSIS_TIMEOUT
        )

        if response.status_code != 200:
            logger.warning(f"Post-trade analysis HTTP error: {response.status_code}")
            return None

        result_text = response.json().get('response', '')
        logger.debug(f"Post-trade raw: {result_text[:400]}")

        result = json.loads(result_text)

        # Validar y normalizar campos
        valid_qualities = ('good', 'fair', 'poor')
        valid_accuracy = ('accurate', 'neutral', 'inaccurate')
        valid_timing = ('optimal', 'acceptable', 'poor')
        valid_confidence = ('overestimated', 'accurate', 'underestimated')

        analysis = {
            'entry_quality': result.get('entry_quality', 'fair') if result.get('entry_quality') in valid_qualities else 'fair',
            'exit_quality': result.get('exit_quality', 'fair') if result.get('exit_quality') in valid_qualities else 'fair',
            'news_accuracy': result.get('news_accuracy', 'neutral') if result.get('news_accuracy') in valid_accuracy else 'neutral',
            'timing_assessment': result.get('timing_assessment', 'acceptable') if result.get('timing_assessment') in valid_timing else 'acceptable',
            'key_lesson': str(result.get('key_lesson', ''))[:300],
            'confidence_was': result.get('confidence_was', 'accurate') if result.get('confidence_was') in valid_confidence else 'accurate',
            'suggested_adjustment': str(result.get('suggested_adjustment', ''))[:300],
        }

        logger.info(f"Post-trade analysis: entry={analysis['entry_quality']} exit={analysis['exit_quality']} "
                     f"timing={analysis['timing_assessment']} | {analysis['key_lesson']}")
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
