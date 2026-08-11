# -*- coding: utf-8 -*-
"""A/B OFFLINE del prompt post-trade: viejo vs nuevo, sobre trades REALES.

POR QUE SE PUEDE HACER ACA Y NO SE PUDO CON NEWS: el modelo de post-trade es
LOCAL (qwen2.5:7b via Ollama) => no hay rate-limit compartido con el exe vivo.
Con news (Groq free tier) el A/B offline era impracticable (v3.47.0).

CAUSA RAIZ DEL PROMPT VIEJO (verificada con datos, no supuesta): el template JSON
de ejemplo lleva VALORES CONCRETOS ("entry_quality": "good", "timing_assessment":
"acceptable", "confidence_was": "accurate") y el modelo los COPIA — 95%, 100% y
95% respectivamente en 589 filas. Nunca se le pidio juzgar; se le dio la hoja de
respuestas. El prompt nuevo usa PLACEHOLDERS y una rubrica anclada a numeros.

CRITERIOS DE EXITO, DECLARADOS ANTES DE MIRAR EL RESULTADO:
  C1 (piso) Ningun campo colapsa: el valor dominante < 80% de los casos.
  C2 (el que importa) ADHERENCIA A LA RUBRICA >= 80%: la etiqueta del modelo
     coincide con la que la rubrica prescribe mecanicamente. Si NO adhiere ni con
     la regla explicita en la mano, el analyzer no se arregla con prompt.
  C3 SEPARACION DENTRO DEL MISMO RESULTADO: entre los PERDEDORES, distinguir los
     que nunca se pusieron a favor de los que estuvieron cerca. Eso es informacion
     que el label win/loss NO tiene, y es la pregunta abierta del proyecto
     (¿entrada o gestion?).
  C4 Se rompe el reflejo del SL: sl_action='widen' baja del 69% a <35%.

Uso:  python tools/ab_post_trade_prompt.py [N]     (default 50, usa la muestra ya armada)
"""
import json
import os
import sqlite3
import statistics
import sys
from collections import Counter

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
OLLAMA = os.getenv('OLLAMA_URL', 'http://localhost:11434')
MODEL = os.getenv('LLM_MODEL_POST_TRADE', 'qwen2.5:7b')

# ── PROMPT VIEJO (copia textual del que corre hoy) ───────────────────────────
PROMPT_VIEJO = """Eres un analista post-trade para EUR/USD en timeframe M5.
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

# ── PROMPT NUEVO ─────────────────────────────────────────────────────────────
# Cambios respecto del viejo, cada uno atacando una causa medida:
#  1. El JSON de salida usa PLACEHOLDERS <a|b|c>, no valores. (mata el copy del template)
#  2. Se le dan los 3 numeros DERIVADOS que definen el trade y una rubrica con
#     umbrales explicitos para cada campo. (mata el "good" por defecto)
#  3. Se le explica el sizing para que deje de recomendar ensanchar el SL como reflejo.
#  4. Primero declara los hechos, despues deriva las etiquetas (mismo patron que el
#     fix de news v3.47.0: postura-primero).
PROMPT_NUEVO = """Sos un analista post-trade de EUR/USD. NO califiques "en general": aplica la
rubrica de abajo al pie de la letra. Cada etiqueta tiene un umbral numerico.

DATOS DEL TRADE (ya cerrado):
- Direccion: {direction} | Trigger: {trigger_type} | Sesion: {session}
- Entrada: {entry_price} -> Salida: {exit_price}
- SL: {sl_pips}p | TP: {tp_pips}p | Resultado final: {pips} pips (${mt5_pnl})
- Confianza que se le puso al abrir: {confidence}%
- RSI al entrar: {rsi} | Tendencia M5: {trend} ({trend_strength}) | HTF: {htf_bias}
- Volatilidad: {volatility} | Duracion: {duration_min} min
- Noticia/Evento: {news_title}

RECORRIDO (esto es lo que define la calidad, no el resultado final):
- Maximo a favor que alcanzo: {mfe_pips} pips = {pct_tp}% del TP
- Del pico a favor devolvio: {devuelto_pips} pips = {pct_devuelto}% del pico
- Tardo {mins_to_peak} min en llegar a ese pico (de {duration_min} min de vida)
YA ESTAN CALCULADOS: usa estos porcentajes tal cual, no rehagas las cuentas.

PASO 1 — declara los hechos (campo "hechos", una linea):
menciona el % del TP alcanzado y cuanto devolvio. Sin opinar.

PASO 2 — deriva cada etiqueta con ESTOS umbrales, sin excepciones:

entry_quality  (mide la ENTRADA: ¿el precio llego a irse a favor?)
  "good" si alcanzo >= 50% del TP
  "fair" si alcanzo 20-49% del TP
  "poor" si alcanzo < 20% del TP   <- nunca se puso a favor: la entrada estuvo mal

exit_quality  (mide la GESTION: mira SOLO "% del pico devuelto")
  "good" si devolvio <= 30% del pico
  "fair" si devolvio 31-70%
  "poor" si devolvio > 70%
  Si el pico fue < 1 pip no hubo nada que gestionar -> "fair"

timing_assessment  (mide CUANDO llego el pico, no cuanto)
  "optimal" si el pico llego en el primer tercio de la vida del trade
  "acceptable" si llego en el segundo tercio
  "poor" si llego en el ultimo tercio o si el trade nunca tuvo pico (0 pips)

confidence_was  (contrasta la confianza declarada contra lo que hizo el precio)
  "overestimated" si la confianza fue >= 75 y alcanzo < 25% del TP
  "underestimated" si la confianza fue < 65 y alcanzo >= 75% del TP
  "accurate" en cualquier otro caso

news_accuracy: "accurate"|"neutral"|"inaccurate". Si el trigger NO es news ni
  calendar, poner SIEMPRE "neutral".

PASO 3 — el consejo de SL/TP. LEE ESTO ANTES DE RESPONDER:
El tamaño del lote se calcula como riesgo$ / (SL x 10). Ensanchar el SL NO reduce
la perdida en dolares: solo achica el lote y empeora el R:R. Recomendar "widen"
por reflejo es el error mas comun y ya se midio que empeora el sistema.
  sl_action = "keep" SALVO que se cumpla una de estas dos, y decilo en "hechos":
    - "widen"  SOLO si alcanzo >= 40% del TP y aun asi termino tocando el SL
               (= el stop corto un trade que iba bien)
    - "tighten" SOLO si nunca supero el 10% del TP (= murio de entrada, no hacia
               falta darle tanto aire)
  recommended_sl_pips: 0 si sl_action es "keep". Si no, un numero derivado del
  recorrido real de ESTE trade. NO uses numeros redondos por costumbre (10, 15, 5).
  recommended_tp_pips: 0 salvo que el trade haya tocado el TP y seguido de largo.

PASO 4 — key_lesson: UNA oracion sobre lo que hay que cambiar. Prohibido decir
"ajustar el SL" salvo que el PASO 3 haya dado widen o tighten. Si la entrada fue
"poor", la leccion va sobre la ENTRADA (que condicion no habia que operar), no
sobre el stop.

Responde SOLO este JSON, reemplazando cada <...> por tu valor:
{{"hechos": "<una linea>", "entry_quality": "<good|fair|poor>", "exit_quality": "<good|fair|poor>", "news_accuracy": "<accurate|neutral|inaccurate>", "timing_assessment": "<optimal|acceptable|poor>", "confidence_was": "<overestimated|accurate|underestimated>", "key_lesson": "<una oracion>", "suggested_adjustment": "<una oracion>", "sl_action": "<widen|tighten|keep>", "recommended_sl_pips": <numero>, "recommended_tp_pips": <numero>}}
"""


def _mins(a, b):
    """Minutos entre dos timestamps de la DB. 0 si no se puede parsear."""
    from datetime import datetime
    def _p(x):
        if not x:
            return None
        x = str(x).split('+')[0].strip().replace('T', ' ')
        for f in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(x, f)
            except ValueError:
                continue
        return None
    ta, tb = _p(a), _p(b)
    return round((tb - ta).total_seconds() / 60.0, 1) if (ta and tb) else 0.0


def rubrica(t):
    """Lo que la rubrica PRESCRIBE mecanicamente. Es la vara de adherencia (C2)."""
    pct_tp = t['pct_tp']
    dev_pct = t['pct_devuelto']
    eq = 'good' if pct_tp >= 50 else ('fair' if pct_tp >= 20 else 'poor')
    if t['mfe_pips'] < 1:
        xq = 'fair'
    else:
        xq = 'good' if dev_pct <= 30 else ('fair' if dev_pct <= 70 else 'poor')
    frac = (t['mins_to_peak'] / t['duration_min']) if t['duration_min'] else 1.0
    tm = 'poor' if t['mfe_pips'] <= 0 else (
        'optimal' if frac <= 1/3 else ('acceptable' if frac <= 2/3 else 'poor'))
    conf = t['confidence']
    cw = 'overestimated' if (conf >= 75 and pct_tp < 25) else (
        'underestimated' if (conf < 65 and pct_tp >= 75) else 'accurate')
    return {'entry_quality': eq, 'exit_quality': xq, 'timing_assessment': tm, 'confidence_was': cw}


def llamar(prompt, ctx):
    try:
        r = requests.post(f'{OLLAMA}/api/generate', json={
            'model': MODEL, 'prompt': prompt.format(**ctx), 'stream': False,
            'format': 'json', 'keep_alive': '10m',
            'options': {'temperature': 0.3, 'top_p': 0.9, 'num_predict': 400, 'num_ctx': 2048},
        }, timeout=90)
        if r.status_code != 200:
            return None
        return json.loads(r.json().get('response', '') or '{}')
    except Exception:
        return None


def main():
    n_max = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT t.*,
               (SELECT MAX(hwm_pips) FROM position_manager_log p
                WHERE p.strategy_id=t.strategy_id) mfe,
               (SELECT MIN(p.created_at) FROM position_manager_log p
                WHERE p.strategy_id=t.strategy_id
                  AND p.hwm_pips = (SELECT MAX(h.hwm_pips) FROM position_manager_log h
                                    WHERE h.strategy_id=t.strategy_id)) peak_at,
               (SELECT MIN(p.created_at) FROM position_manager_log p
                WHERE p.strategy_id=t.strategy_id) first_at,
               (SELECT MAX(p.created_at) FROM position_manager_log p
                WHERE p.strategy_id=t.strategy_id) last_at
        FROM trade_archive t
        WHERE t.mt5_pnl IS NOT NULL AND t.created_at >= '2026-06-20'
          AND t.result IN ('win','loss')
        ORDER BY t.strategy_id DESC""").fetchall()
    rows = [dict(r) for r in rows if r['mfe'] is not None and (r['tp_pips'] or 0) > 0]
    wins = [r for r in rows if r['result'] == 'win'][:n_max // 2]
    loss = [r for r in rows if r['result'] == 'loss'][:n_max // 2]
    muestra = wins + loss
    print(f"Muestra: {len(muestra)} trades ({len(wins)}W/{len(loss)}L) · modelo {MODEL}\n")

    resultados = {'viejo': [], 'nuevo': []}
    for i, t in enumerate(muestra, 1):
        mfe = float(t['mfe'] or 0)
        pips = float(t['pips'] or 0)
        ctx = {
            'result': t['result'], 'pips': round(pips, 1), 'direction': t['direction'],
            'trigger_type': t['trigger_type'], 'entry_price': t['entry_price'],
            'exit_price': t['exit_price'], 'stop_loss': t['stop_loss'],
            'take_profit': t['take_profit'], 'sl_pips': round(t['sl_pips'] or 0, 1),
            'tp_pips': round(t['tp_pips'] or 0, 1), 'session': t['session'] or 'unknown',
            'rsi': round(t['rsi_at_entry'] or 50, 1), 'trend': t['market_trend'] or 'unknown',
            'trend_strength': t['trend_strength'] or 'N/A', 'htf_bias': t['htf_bias'] or 'neutral',
            'volatility': t['volatility'] or 'normal', 'news_title': (t['news_title'] or 'N/A')[:120],
            'confidence': round(t['confidence'] or 50, 1),
            'mt5_pnl': round(t['mt5_pnl'] or 0, 2),
            'mfe_pips': round(mfe, 1),
            'pct_tp': round(100.0 * mfe / t['tp_pips'], 0),
            'devuelto_pips': round(max(0.0, mfe - pips), 1),
            'pct_devuelto': round(100.0 * max(0.0, mfe - pips) / mfe, 0) if mfe > 0 else 0,
            'duration_min': _mins(t['first_at'], t['last_at']),
            'mins_to_peak': _mins(t['first_at'], t['peak_at']),
        }
        ref = rubrica(ctx)
        for etiqueta, prompt in (('viejo', PROMPT_VIEJO), ('nuevo', PROMPT_NUEVO)):
            out = llamar(prompt, ctx)
            if out:
                resultados[etiqueta].append({'trade': ctx, 'ref': ref, 'out': out,
                                             'result': t['result']})
        print(f"\r  {i}/{len(muestra)}", end='', flush=True)
    print("\n")

    campos = ('entry_quality', 'exit_quality', 'timing_assessment', 'confidence_was')
    for etiqueta in ('viejo', 'nuevo'):
        R = resultados[etiqueta]
        print(f"{'='*68}\nPROMPT {etiqueta.upper()}  (n={len(R)})\n{'='*68}")
        for campo in campos:
            vals = Counter((r['out'].get(campo) or '?') for r in R)
            ref_vals = Counter(r['ref'].get(campo) for r in R)
            tot = sum(vals.values())
            dom, dn = vals.most_common(1)[0]
            adh = sum(1 for r in R if r['out'].get(campo) == r['ref'].get(campo))
            print(f"    [rubrica prescribe: {dict(ref_vals)}]")
            # discriminacion dentro de PERDEDORES: ¿marca 'poor' a los que nunca fueron a favor?
            print(f"  {campo:<20} dominante '{dom}' {100*dn/tot:.0f}%  | "
                  f"adherencia rubrica {100*adh/len(R):.0f}%  | dist={dict(vals)}")
        sl = Counter((r['out'].get('sl_action') or '?') for r in R)
        tot = sum(sl.values())
        print(f"  sl_action            {dict(sl)}  (widen {100*sl.get('widen',0)/tot:.0f}%)")
        # C3: separacion dentro de los perdedores
        perd = [r for r in R if r['result'] == 'loss']
        if perd:
            nunca = [r for r in perd if r['trade']['pct_tp'] < 20]
            cerca = [r for r in perd if r['trade']['pct_tp'] >= 20]
            p_nunca = sum(1 for r in nunca if r['out'].get('entry_quality') == 'poor')
            p_cerca = sum(1 for r in cerca if r['out'].get('entry_quality') == 'poor')
            print(f"  C3 — entre PERDEDORES, ¿marca 'poor' la entrada?")
            print(f"     los que nunca fueron a favor (<20% TP): {p_nunca}/{len(nunca)}")
            print(f"     los que estuvieron cerca  (>=20% TP): {p_cerca}/{len(cerca)}")
        # reflejo del SL en la leccion
        sl_talk = sum(1 for r in R if 'sl' in (r['out'].get('key_lesson') or '').lower()
                      or 'stop' in (r['out'].get('key_lesson') or '').lower())
        print(f"  lecciones que hablan del SL: {100*sl_talk/len(R):.0f}%")
        print()


if __name__ == '__main__':
    main()
