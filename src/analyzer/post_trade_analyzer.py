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
# v3.25.0 — modelo dedicado desde Config.LLM_MODELS['post_trade']
# Override: env LLM_MODEL_POST_TRADE
POST_TRADE_MODEL = Config.get_llm_model('post_trade')

# ─────────────────────────────────────────────────────────────────────────────
# v3.53.7 — REDISEÑO. Medido antes de tocar (tools/measure_post_trade_value.py,
# 589 filas) y verificado despues con un A/B offline real contra el prompt viejo
# (tools/ab_post_trade_prompt.py, n=30 trades reales, modelo local => sin
# rate-limit, que es lo que hizo imposible el A/B de news en v3.47.0).
#
# QUE ESTABA MAL: el template JSON de ejemplo del prompt viejo llevaba VALORES
# CONCRETOS y el modelo los copiaba literal — `entry_quality:"good"` 95% de las
# veces (incluido el 93% de los PERDEDORES), `timing_assessment:"acceptable"` el
# 100%, `confidence_was:"accurate"` el 95%. Nunca se le pidio juzgar: se le dio la
# hoja de respuestas. Y la regla del SL empujaba a "widen", que salio 90% en el
# A/B — sobre un sistema donde ensanchar el SL ya se refuto midiendo (v3.51.0).
#
# QUE DIJO EL A/B: con placeholders + rubrica anclada a numeros, el modelo aplica
# bien UN umbral sobre UN numero (entry_quality: 27% -> 77% de adherencia, y marca
# `poor` a 9/9 de los perdedores que nunca se pusieron a favor). Pero cuando la
# regla necesita dos condiciones o un cociente (timing, confidence_was) VUELVE al
# valor por defecto: 23% y 63% de adherencia, dominante 97% y 93%.
#
# DECISION QUE FUERZA ESE RESULTADO: las etiquetas categoricas son mecanicas =>
# se calculan en CODIGO (`derive_quality`, exactas por construccion, gratis,
# auditables y testeables). Al LLM le queda lo unico que solo el puede hacer: la
# leccion en texto — y ahi el prompt nuevo si gano (lecciones que hablaban del SL:
# 90% -> 0%).
# ─────────────────────────────────────────────────────────────────────────────

POST_TRADE_PROMPT = """Sos un analista post-trade de EUR/USD. Ya esta calculado el
diagnostico del trade; tu trabajo es escribir la leccion, NO recalcular nada.

TRADE (cerrado):
- Direccion: {direction} | Trigger: {trigger_type} | Sesion: {session}
- Entrada: {entry_price} -> Salida: {exit_price}
- SL: {sl_pips}p | TP: {tp_pips}p | Resultado: {pips} pips (${mt5_pnl})
- Confianza al abrir: {confidence}% | Duracion: {duration_min} min
- RSI: {rsi} | Tendencia M5: {trend} ({trend_strength}) | HTF: {htf_bias}
- Volatilidad: {volatility} | Noticia/Evento: {news_title}

RECORRIDO — esto define la calidad, no el resultado final:
- Maximo a favor: {mfe_pips} pips = {pct_tp}% del TP
- Del pico devolvio: {devuelto_pips} pips = {pct_devuelto}% del pico

DIAGNOSTICO YA DERIVADO (no lo discutas, escribi la leccion A PARTIR de esto):
- Calidad de ENTRADA: {entry_quality}   (poor = el precio nunca se fue a favor)
- Calidad de GESTION: {exit_quality}    (poor = devolvio casi todo el pico)
- El SL/TP: {sl_action}

COMO ESCRIBIR LA LECCION:
- Si la ENTRADA es "poor", la leccion va sobre la ENTRADA: que condicion del
  contexto (tendencia, HTF, RSI, sesion, volatilidad, noticia) desaconsejaba
  operar. NO hables del stop: el trade nunca se puso a favor, mover el stop no
  lo hubiera salvado.
- Si la ENTRADA fue buena y la GESTION "poor", la leccion va sobre la SALIDA.
- PROHIBIDO recomendar ensanchar o achicar el SL salvo que arriba diga
  explicitamente "widen" o "tighten". El lote se calcula como riesgo$/(SL x 10):
  ensanchar el SL NO reduce la perdida en dolares, solo achica el lote y empeora
  el R:R. Es el consejo equivocado mas repetido y ya se midio que no sirve.
- Concreta y en una oracion. Nada de "monitorear el mercado" ni generalidades.

Responde SOLO este JSON, reemplazando cada <...>:
{{"key_lesson": "<una oracion accionable>", "suggested_adjustment": "<una oracion: que cambiar en la logica o los parametros>", "news_accuracy": "<accurate|neutral|inaccurate>"}}

news_accuracy: si el trigger NO es news ni calendar, poner SIEMPRE "neutral".
"""


def derive_quality(pct_tp, pct_devuelto, mfe_pips, confidence, hit_sl):
    """v3.53.7 — Las etiquetas categoricas, calculadas en CODIGO.

    El A/B probo que el modelo de 7B no las aplica de forma fiable (23-77% de
    adherencia a una rubrica que tenia escrita adelante). Son deterministas, asi
    que no hay razon para pedirselas a un LLM: aca son exactas, instantaneas y
    testeables.

    Umbrales anclados al hallazgo de v3.53.2: el 74% de los trades nunca llega a
    la mitad del TP y ahi vive el 100% de la perdida.
    """
    if pct_tp >= 50:
        entry = 'good'
    elif pct_tp >= 20:
        entry = 'fair'
    else:
        entry = 'poor'          # nunca se puso a favor => problema de ENTRADA

    if mfe_pips < 1:
        exit_q = 'fair'         # no hubo pico: no habia nada que gestionar
    elif pct_devuelto <= 30:
        exit_q = 'good'
    elif pct_devuelto <= 70:
        exit_q = 'fair'
    else:
        exit_q = 'poor'         # devolvio casi todo => problema de GESTION

    if confidence >= 75 and pct_tp < 25:
        conf_was = 'overestimated'
    elif confidence < 65 and pct_tp >= 75:
        conf_was = 'underestimated'
    else:
        conf_was = 'accurate'

    # timing: cuanto del camino al TP se recorrio (el "cuando" del pico se saco:
    # depende del muestreo de 15s del PM y no era estable).
    timing = 'optimal' if pct_tp >= 50 else ('acceptable' if pct_tp >= 20 else 'poor')

    # SL: "keep" por default, a proposito. Solo dos excepciones, ambas medibles.
    if hit_sl and pct_tp >= 40:
        sl_action = 'widen'     # el stop corto un trade que iba bien
    elif pct_tp < 10:
        sl_action = 'tighten'   # murio de entrada, no hacia falta tanto aire
    else:
        sl_action = 'keep'

    return {
        'entry_quality': entry,
        'exit_quality': exit_q,
        'timing_assessment': timing,
        'confidence_was': conf_was,
        'sl_action': sl_action,
    }


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

        # v3.53.7 — el RECORRIDO. Se busca por strategy_id si el caller lo paso;
        # si no hay datos de excursion, `mfe` cae al |pips| final, que es la cota
        # INFERIOR correcta (el trade al menos llego hasta donde cerro).
        _mfe = None
        _mins_peak = 0.0
        _sid = trade_data.get('strategy_id')
        if _sid is not None:
            try:
                from src.common.db import get_trade_excursion
                _exc = get_trade_excursion(_sid)
                if _exc:
                    _mfe = _exc['mfe_pips']
                    _mins_peak = _exc['mins_to_peak']
                    if not ctx['duration_min'] and _exc['duration_min']:
                        ctx['duration_min'] = _exc['duration_min']
            except Exception as _ee:
                logger.debug(f"excursion #{_sid}: {_ee}")
        _pips = float(ctx['pips'] or 0)
        if _mfe is None:
            _mfe = max(0.0, _pips)
            logger.debug(f"Post-trade #{_sid}: sin datos de excursion, mfe={_mfe} (cota inferior)")
        _tp = float(ctx['tp_pips'] or 0)
        ctx['mfe_pips'] = round(_mfe, 1)
        ctx['pct_tp'] = round(100.0 * _mfe / _tp, 0) if _tp > 0 else 0
        _dev = max(0.0, _mfe - _pips)
        ctx['devuelto_pips'] = round(_dev, 1)
        # Cap al 100%: no se puede "devolver" mas que el pico. Sin el cap, un trade
        # con pico 0.1p que cierra en -5.8 daba "devolvio 5900%", que ademas de
        # absurdo confunde al modelo. Mas alla del pico ya no es devolver: es perder.
        ctx['pct_devuelto'] = round(min(100.0, 100.0 * _dev / _mfe), 0) if _mfe > 0 else 0
        ctx['mins_to_peak'] = _mins_peak

        # Etiquetas categoricas: CODIGO, no LLM (ver el bloque de v3.53.7 arriba).
        _hit_sl = bool(trade_data.get('sl_hit')) or (
            _pips < 0 and ctx['sl_pips'] and abs(_pips) >= 0.9 * float(ctx['sl_pips']))
        derived = derive_quality(ctx['pct_tp'], ctx['pct_devuelto'], _mfe,
                                 float(ctx['confidence'] or 0), _hit_sl)
        ctx.update(derived)

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

        # Validar y normalizar campos. v3.53.7: quedo solo `valid_accuracy` —
        # las otras 4 listas validaban campos que el LLM ya no emite (los deriva
        # `derive_quality`), asi que se sacaron para no dejar codigo muerto.
        valid_accuracy = ('accurate', 'neutral', 'inaccurate')

        # v3.53.7 — las categoricas YA vienen derivadas en codigo; el LLM solo
        # aporta el texto y news_accuracy (que si requiere leer el titular).
        sl_action = derived['sl_action']
        # El SL recomendado sale del recorrido REAL, no de un numero que el modelo
        # elija: el A/B mostro que sin esto tiraba multiplos de 5 por costumbre
        # (50% de las recomendaciones eran 10/15/12/5).
        # `widen` es el UNICO que emite un numero, y solo en su caso defendible: el
        # stop corto un trade que ya iba al 40%+ del TP.
        # `tighten` emite 0 A PROPOSITO: la etiqueta sirve como DIAGNOSTICO ("murio
        # de entrada") pero apretar el SL ya se midio y NO reduce la perdida en
        # dolares (el sizing es riesgo$/(SL x 10)) — solo baja el WR (31-jul). Seria
        # incoherente que el lazo de aprendizaje recomiende lo que la data refuto.
        # Con rec_sl=0 el bucket de `sl_tp_advice` no lo acumula (db.py exige >0).
        if sl_action == 'widen':
            rec_sl = round(min(15.0, float(ctx['sl_pips'] or 0) * 1.3), 1)
        else:
            rec_sl = 0.0
        rec_tp = 0.0   # solo tendria sentido con velas posteriores, que no se miden

        analysis = {
            'entry_quality': derived['entry_quality'],
            'exit_quality': derived['exit_quality'],
            'news_accuracy': result.get('news_accuracy', 'neutral') if result.get('news_accuracy') in valid_accuracy else 'neutral',
            'timing_assessment': derived['timing_assessment'],
            'key_lesson': str(result.get('key_lesson', ''))[:300],
            'confidence_was': derived['confidence_was'],
            'suggested_adjustment': str(result.get('suggested_adjustment', ''))[:300],
            'sl_action': sl_action,
            'recommended_sl_pips': rec_sl,
            'recommended_tp_pips': rec_tp,
            # el recorrido, para poder auditar la etiqueta despues
            'mfe_pips': ctx['mfe_pips'],
            'pct_tp_alcanzado': ctx['pct_tp'],
            'pct_pico_devuelto': ctx['pct_devuelto'],
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
