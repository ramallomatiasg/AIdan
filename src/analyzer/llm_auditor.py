"""
LLM Auditor — Gemma 4 como auditor en paralelo para validar senales de trading.

Corre en paralelo con el analisis principal (Groq). No es fallback,
es segunda opinion que ajusta confianza antes de crear la estrategia.

Logica:
  - Ambos de acuerdo -> conf +10 (max)
  - Gemma en contra  -> conf penalizada (-15 a -20)
  - Timeout/error    -> senal pasa sin auditoria (no bloquea)
"""

import logging
import json
import requests
from src.common.config import Config

logger = logging.getLogger("llm_auditor")

AUDIT_TIMEOUT = 20  # segundos max para respuesta de Gemma (cold start ~15s, warm ~3s)
OLLAMA_URL = Config.OLLAMA_URL or "http://localhost:11434"
# v3.25.0 — modelo dedicado para signal auditor
GEMMA_MODEL = Config.get_llm_model('signal_audit')

AUDIT_PROMPT_TEMPLATE = """Eres un auditor de trading para EUR/USD en timeframe M5.
Analiza esta senal y decide si es buena operacion.

Contexto:
- Direccion: {direction}
- Precio entrada: {price}
- Tendencia M5: {trend} ({strength})
- HTF bias (H1+M15): {htf_bias}
- RSI: {rsi} ({rsi_zone})
- Momentum: {momentum}
- Volatilidad: {volatility}, ATR: {atr}p
- Setup: {setup_type}
- Nivel clave: {key_level}
- Session: {session}
- Confianza algoritmica: {confidence}%
- SL: {sl_pips}p, TP: {tp_pips}p (R:R {rr})
- Fuente de senal: {source}

Responde SOLO en JSON valido, sin texto adicional:
{{"agree": true, "confidence_adjustment": 0, "risk_flag": "none", "reasoning": "1 linea"}}

Reglas:
- agree: true si la operacion tiene sentido, false si no
- confidence_adjustment: entre -20 y +15
- risk_flag: "none" | "high_risk" | "counter_trend" | "low_volatility" | "overextended"
- reasoning: maximo 1 oracion explicando tu decision
"""


def audit_signal(signal_context: dict) -> dict | None:
    """
    Envia el contexto de la senal a Gemma 4 para auditoria.

    Args:
        signal_context: dict con keys: direction, price, trend, strength,
                       htf_bias, rsi, rsi_zone, momentum, volatility, atr,
                       setup_type, key_level, session, confidence, sl_pips,
                       tp_pips, rr, source

    Returns:
        dict con {agree, confidence_adjustment, risk_flag, reasoning} o None si timeout/error
    """
    try:
        # Llenar defaults para campos faltantes
        ctx = {
            'direction': signal_context.get('direction', 'N/A'),
            'price': signal_context.get('price', 0),
            'trend': signal_context.get('trend', 'unknown'),
            'strength': signal_context.get('strength', 'N/A'),
            'htf_bias': signal_context.get('htf_bias', 'neutral'),
            'rsi': signal_context.get('rsi', 50),
            'rsi_zone': signal_context.get('rsi_zone', 'neutral'),
            'momentum': signal_context.get('momentum', 'flat'),
            'volatility': signal_context.get('volatility', 'normal'),
            'atr': signal_context.get('atr', 0),
            'setup_type': signal_context.get('setup_type', 'unknown'),
            'key_level': signal_context.get('key_level', 'none'),
            'session': signal_context.get('session', 'unknown'),
            'confidence': signal_context.get('confidence', 50),
            'sl_pips': signal_context.get('sl_pips', 0),
            'tp_pips': signal_context.get('tp_pips', 0),
            'rr': signal_context.get('rr', '0:0'),
            'source': signal_context.get('source', 'unknown'),
        }

        prompt = AUDIT_PROMPT_TEMPLATE.format(**ctx)

        # GPU-aware: skip audit si GPU ocupada (no es critical-path)
        try:
            from src.common.gpu_monitor import should_pause_llm
            if should_pause_llm():
                logger.info(f"Signal audit: skipped (GPU busy)")
                return None
        except Exception:
            pass

        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': GEMMA_MODEL,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
                'keep_alive': '2m',
                'options': {
                    'temperature': 0.2,
                    'top_p': 0.9,
                    'num_predict': 200,
                }
            },
            timeout=AUDIT_TIMEOUT
        )

        if response.status_code != 200:
            logger.warning(f"Gemma audit HTTP error: {response.status_code}")
            return None

        result_text = response.json().get('response', '')
        logger.debug(f"Gemma audit raw: {result_text[:300]}")

        # Parse JSON
        result = json.loads(result_text)

        # Validar campos requeridos
        agree = bool(result.get('agree', True))
        conf_adj = int(result.get('confidence_adjustment', 0))
        conf_adj = max(-20, min(15, conf_adj))  # clamp
        risk_flag = result.get('risk_flag', 'none')
        reasoning = str(result.get('reasoning', ''))[:200]

        audit_result = {
            'agree': agree,
            'confidence_adjustment': conf_adj,
            'risk_flag': risk_flag,
            'reasoning': reasoning,
        }

        logger.info(f"Gemma audit: {'AGREE' if agree else 'DISAGREE'} | adj={conf_adj:+d} | flag={risk_flag} | {reasoning}")
        return audit_result

    except requests.exceptions.Timeout:
        logger.warning(f"Gemma audit timeout ({AUDIT_TIMEOUT}s) — signal passes without audit")
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Gemma audit: Ollama not reachable — signal passes without audit")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Gemma audit: invalid JSON response — {e}")
        return None
    except Exception as e:
        logger.error(f"Gemma audit error: {e}")
        return None


PRETRADE_STRICT_PROMPT = """Eres un risk manager senior para trading EUR/USD.
Tu trabajo es identificar trades con problemas obvios ANTES de ejecutar.
Razona paso por paso si hay senales rojas.

SETUP A AUDITAR:
- Direccion: {direction} (precio {price:.5f})
- Trigger: {source} setup_type={setup_type}
- SL: {sl_pips}p, TP: {tp_pips}p (R:R {rr})
- Confianza algoritmica: {confidence}%

CONTEXTO DE MERCADO:
- M5 trend: {trend} ({strength}), momentum: {momentum}
- HTF bias (H1+M15): {htf_bias}
- RSI: {rsi} ({rsi_zone})
- ATR: {atr}p ({volatility})
- Session: {session}
- Nivel clave: {key_level}

PATRONES DE FALLO CONOCIDOS DE AIDAN:
1. Counter-HTF entries (CALL en HTF bearish, PUT en HTF bullish) -> historicamente -EV
2. Catch-the-falling-knife (CALL despues de breakdown grande) -> SL hit rapido
3. Exhaustion (RSI extremo + trend strong + entry alineado) -> reversal
4. Late breakout (>7p past nivel) -> ya consumido el move
5. Low volatility (ATR <2.5p) -> commission domina vs win esperado

Responde JSON estricto sin texto extra:
{{
  "veto_recommended": false,
  "risk_score": 30,
  "concerns": ["concern1", "concern2"],
  "reasoning": "1-2 oraciones explicando."
}}

veto_recommended: true SOLO si hay 2+ problemas serios o 1 fatal (ej: counter-HTF + exhausted + low ATR)
risk_score: 0-100 (0=trade limpio, 100=trade con multiples problemas)
concerns: lista de 0-3 patrones detectados (vacio si trade limpio)
reasoning: max 2 oraciones explicando."""


def _ensure_pretrade_audits_table():
    """Lazy create tabla pretrade_audits para logging."""
    try:
        from src.common.db import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pretrade_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                model TEXT,
                veto_recommended INTEGER,
                risk_score INTEGER,
                concerns TEXT,
                reasoning TEXT,
                signal_context_json TEXT,
                outcome TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass


def log_pretrade_audit(strategy_id, model, audit_result, signal_context):
    """Log audit prediction para validar a posteriori contra outcome."""
    try:
        from src.common.db import DB_PATH
        import sqlite3
        _ensure_pretrade_audits_table()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO pretrade_audits
            (strategy_id, model, veto_recommended, risk_score, concerns, reasoning, signal_context_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            strategy_id,
            model,
            1 if audit_result.get('veto_recommended') else 0,
            int(audit_result.get('risk_score', 0)),
            json.dumps(audit_result.get('concerns', []))[:500],
            str(audit_result.get('reasoning', ''))[:300],
            json.dumps(signal_context)[:1000],
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"log_pretrade_audit error: {e}")


def audit_pretrade_strict(signal_context: dict, model: str = None, strategy_id: int = None):
    """v3.22.0 — Pre-trade strict audit usando deepseek-r1 (chain-of-thought).
    v3.25.0 — modelo desde Config.LLM_MODELS['pretrade_strict']

    A diferencia de audit_signal (suave, ajusta conf):
    - Usa modelo razonador (default deepseek-r1:14b) por default
    - Detecta patrones de fallo conocidos de AIdan (counter-HTF, catch-knife, etc)
    - Loguea predicción a tabla pretrade_audits para validación posterior
    - SOLO LOGGEA — NO veta el trade en este momento
      (despues de 30+ trades con logs, decidir si activar veto basado en accuracy)

    Returns: dict con {veto_recommended, risk_score, concerns, reasoning} o None si error.
    """
    audit_model = model or Config.get_llm_model('pretrade_strict')
    try:
        # GPU-aware
        try:
            from src.common.gpu_monitor import should_pause_llm
            if should_pause_llm():
                logger.debug("Pretrade audit: skipped (GPU busy)")
                return None
        except Exception:
            pass

        ctx = {
            'direction': signal_context.get('direction', 'N/A'),
            'price': float(signal_context.get('price', 0) or 0),
            'trend': signal_context.get('trend', 'unknown'),
            'strength': signal_context.get('strength', 'N/A'),
            'htf_bias': signal_context.get('htf_bias', 'neutral'),
            'rsi': signal_context.get('rsi', 50),
            'rsi_zone': signal_context.get('rsi_zone', 'neutral'),
            'momentum': signal_context.get('momentum', 'flat'),
            'volatility': signal_context.get('volatility', 'normal'),
            'atr': signal_context.get('atr', 0),
            'setup_type': signal_context.get('setup_type', 'unknown'),
            'key_level': signal_context.get('key_level', 'none'),
            'session': signal_context.get('session', 'unknown'),
            'confidence': signal_context.get('confidence', 50),
            'sl_pips': signal_context.get('sl_pips', 0),
            'tp_pips': signal_context.get('tp_pips', 0),
            'rr': signal_context.get('rr', '0:0'),
            'source': signal_context.get('source', 'unknown'),
        }
        prompt = PRETRADE_STRICT_PROMPT.format(**ctx)

        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': audit_model,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
                'keep_alive': '5m',  # 14b model: keep cargado mas tiempo
                'options': {
                    'temperature': 0.2,
                    'top_p': 0.9,
                    'num_predict': 400,
                    'num_ctx': 2048,  # context chico - deepseek-r1:14b OOM con default 32K
                }
            },
            timeout=90  # deepseek-r1:14b puede tardar 30-60s en cold start
        )

        if response.status_code != 200:
            logger.warning(f"Pretrade audit HTTP {response.status_code}")
            return None

        result_text = response.json().get('response', '')
        # DeepSeek-R1 puede agregar <think> tags, removerlos
        if '<think>' in result_text:
            result_text = result_text.split('</think>')[-1].strip()

        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            logger.warning(f"Pretrade audit: invalid JSON. Raw: {result_text[:200]}")
            return None

        veto = bool(result.get('veto_recommended', False))
        risk_score = max(0, min(100, int(result.get('risk_score', 0))))
        concerns = result.get('concerns', [])
        if not isinstance(concerns, list):
            concerns = [str(concerns)]
        reasoning = str(result.get('reasoning', ''))[:300]

        audit = {
            'veto_recommended': veto,
            'risk_score': risk_score,
            'concerns': concerns[:3],
            'reasoning': reasoning,
            'model': audit_model,
        }

        # Log to DB
        if strategy_id:
            log_pretrade_audit(strategy_id, audit_model, audit, signal_context)

        log_msg = f"Pretrade audit ({audit_model}): risk={risk_score}/100"
        if veto:
            log_msg += " VETO RECOMMENDED"
        if concerns:
            log_msg += f" concerns={concerns}"
        logger.info(log_msg)
        return audit

    except requests.exceptions.Timeout:
        logger.warning(f"Pretrade audit timeout — signal passes")
        return None
    except Exception as e:
        logger.warning(f"Pretrade audit error: {e}")
        return None


def build_signal_context(direction, price, market_state, adaptive, session_info,
                         confidence, setup_type='unknown', source='unknown',
                         htf_bias='neutral', key_level='none'):
    """
    Helper para construir el dict de contexto desde los datos disponibles en cada scanner.
    """
    ms = market_state or {}
    si = session_info or {}
    ad = adaptive or {}

    rsi_val = ms.get('rsi', 50)
    if rsi_val > 70:
        rsi_zone = 'overbought'
    elif rsi_val < 30:
        rsi_zone = 'oversold'
    else:
        rsi_zone = 'neutral'

    sl_pips = ad.get('sl_pips', 0)
    tp_pips = ad.get('tp_pips', 0)
    rr = f"{tp_pips/sl_pips:.1f}:1" if sl_pips > 0 else "N/A"

    return {
        'direction': direction,
        'price': price,
        'trend': ms.get('trend', 'unknown'),
        'strength': ms.get('trend_strength', 'N/A'),
        'htf_bias': htf_bias or 'neutral',
        'rsi': rsi_val,
        'rsi_zone': rsi_zone,
        'momentum': ms.get('momentum', 'flat'),
        'volatility': ms.get('volatility', 'normal'),
        'atr': round(ms.get('atr_pips', 0), 1),
        'setup_type': setup_type,
        'key_level': key_level,
        'session': si.get('session', 'unknown'),
        'confidence': confidence,
        'sl_pips': round(sl_pips, 1),
        'tp_pips': round(tp_pips, 1),
        'rr': rr,
        'source': source,
    }
