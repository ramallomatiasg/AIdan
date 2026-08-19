"""¿El track news llega TARDE por construccion? (19 Ago 2026). READ-ONLY.

DE DONDE SALE LA PREGUNTA
-------------------------
Research externo (19-ago): un estudio sobre **993 eventos USD de alto impacto
(2022-2025, calendario de ForexFactory)** midio la deriva post-release y la
encontro **enteramente contenida en las velas +1 a +5** — o sea, en el spike.
Medida desde la vela +6 en adelante, todos los horizontes dan **T entre 0,14 y
0,69**: no hay tendencia sostenida que capturar. Y data de mercado 2025: el par
mayor promedio completa **~80 % del movimiento de la noticia en los primeros
3 minutos**.

Si eso aplica, la razon por la que news no tiene habilidad direccional (medido el
24-jul: discriminacion −1 pp, Fisher p=0,92, **anti-skill** vs el drift) podria no
ser "el LLM lee mal el titular" sino algo bastante mas duro: **el pipeline es mas
lento que la ventana donde vive el movimiento**. RSS -> fetch -> pre-filtro ->
LLM (Groq, red) -> alert -> estrategia -> orden. Y eso explicaria por que v3.47.0
(prompt postura-primero) no movio el edge: un prompt no arregla latencia.

ZONAS HORARIAS — EL POZO EN EL QUE ME CAI PRIMERO
------------------------------------------------
`news.published_at` viene del RSS en **UTC**; `fetched_at` ya esta en **hora AR**
(`now_ar()`). Restarlos crudo da −172 min de mediana y 733 de 871 filas
"negativas". La primera version de este script las descartaba y reportaba una
mediana de **398 min** sobre las 136 sobrevivientes — un artefacto puro, y encima
del signo contrario al real. `db.get_news_fetch_time()` ya documenta y aplica la
conversion correcta; aca se usa la misma. Validacion: tras corregir quedan
**0 negativas** sobre 871 filas y 6 meses, y la mediana por mes se mueve entre
7,7 y 14,0 min — el offset es estable, no es un ajuste ad hoc.

LIMITES DECLARADOS
------------------
1. `published_at` es la hora de la NOTA, no la del release economico: para un CPI
   la nota sale despues del numero ⇒ lo que se mide es una **cota INFERIOR** del
   retraso real contra el evento.
2. El desglose por resultado usa `alerts.alert_result` / `alert_pips`, que es la
   evaluacion del ALERT, **no** `mt5_pnl` de broker. La regla del proyecto es
   validar con broker-truth ⇒ este corte es **indicativo, no concluyente**. Por eso
   v3.57.0 guarda `news_latency_min` en `entry_context` al crear la senal: para
   poder medir esto limpio, contra `mt5_pnl`, hacia adelante.
"""

import math
import os
import sqlite3
import statistics as st
from datetime import datetime, timedelta

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')

#: ~80 % del movimiento de la noticia se completa aca
FAST_WINDOW_MIN = 3.0
#: velas +1..+5 de M5: donde el estudio encuentra TODA la deriva
DRIFT_WINDOW_MIN = 25.0
#: published_at (UTC) -> hora AR. Misma convencion que db.get_news_fetch_time().
AR_OFFSET_H = 3

BUCKETS = [('<=3 min', 0, 3), ('3-10 min', 3, 10), ('10-25 min', 10, 25),
           ('25-180 min', 25, 180), ('>3 h', 180, float('inf'))]


def _parse(v):
    if not v:
        return None
    s = str(v).replace('T', ' ').split('+')[0].split('.')[0].strip()
    for f in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def _latency_min(published_utc, fetched_ar):
    """Minutos entre publicacion y deteccion, con published_at convertido a AR."""
    p, f = _parse(published_utc), _parse(fetched_ar)
    if not p or not f:
        return None
    return (f - (p - timedelta(hours=AR_OFFSET_H))).total_seconds() / 60.0


def wilson(wins, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(100 * (c - m) / d, 1), round(100 * (c + m) / d, 1))


def main():
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT n.published_at, n.fetched_at, a.alert_sent_at, a.alert_result,
               a.alert_pips, a.impact_score
        FROM alerts a JOIN news n ON n.id = a.news_id
        WHERE a.direction IN ('CALL', 'PUT')
    """).fetchall()
    conn.close()

    lats, per_month, negativos = [], {}, 0
    for r in rows:
        v = _latency_min(r['published_at'], r['fetched_at'])
        if v is None:
            continue
        if v < -1:
            negativos += 1
            continue
        lats.append(v)
        per_month.setdefault(str(r['alert_sent_at'])[:7], []).append(v)

    if not lats:
        print("Sin alerts direccionales con timestamps utilizables.")
        return 1

    lats.sort()
    pc = lambda q: lats[min(len(lats) - 1, int(q * len(lats)))]
    print("=== LATENCIA DEL TRACK NEWS (publicacion -> deteccion) ===")
    print(f"n={len(lats)}  mediana={st.median(lats):.1f} min   "
          f"p10={pc(.10):.1f}  p25={pc(.25):.1f}  p75={pc(.75):.1f}  p90={pc(.90):.1f}")

    # Control de sanidad del offset: si esto no es ~0, la conversion esta mal y
    # todo lo de abajo es basura (fue exactamente el bug de la 1ra version).
    print(f"\ncontrol de zona horaria: negativas tras convertir = {negativos} "
          f"({'OK' if negativos <= len(lats) * 0.01 else 'MAL: revisar el offset'})")
    print("mediana por mes (el offset tiene que ser estable):")
    for m in sorted(per_month):
        v = per_month[m]
        print(f"  {m}  n={len(v):<4} mediana={st.median(v):6.1f} min")

    print(f"\n-- contra la ventana donde vive el movimiento --")
    for label, lim in (('~80% del movimiento', FAST_WINDOW_MIN),
                       ('toda la deriva medida (velas +1..+5)', DRIFT_WINDOW_MIN)):
        pct = 100.0 * sum(1 for v in lats if v <= lim) / len(lats)
        print(f"  detectadas dentro de {lim:5.0f} min : {pct:5.1f}%   ({label})")

    # Desglose por resultado. INDICATIVO: es alert_result, no broker-truth.
    ev = [(v, r) for r in rows
          if (v := _latency_min(r['published_at'], r['fetched_at'])) is not None
          and v >= 0 and r['alert_result'] in ('win', 'loss')]
    if ev:
        tot_w = sum(1 for _, r in ev if r['alert_result'] == 'win')
        base = 100.0 * tot_w / len(ev)
        print(f"\n-- WR por latencia (INDICATIVO: alert_result, NO mt5_pnl) --")
        print(f"  baseline: n={len(ev)}  WR={base:.1f}%")
        print(f"  {'latencia':<12}{'n':>5}{'WR':>8}{'CI95':>16}{'pips/ev':>10}  gate")
        for label, lo, hi in BUCKETS:
            sel = [r for v, r in ev if lo <= v < hi]
            if not sel:
                print(f"  {label:<12}{0:>5}")
                continue
            n = len(sel)
            w = sum(1 for r in sel if r['alert_result'] == 'win')
            pips = sum(float(r['alert_pips'] or 0) for r in sel)
            clo, chi = wilson(w, n)
            # El gate del proyecto: n>=25 Y el CI no cruza el baseline.
            cruza = clo <= base <= chi
            gate = 'no pasa (n<25)' if n < 25 else ('NO pasa (CI cruza)' if cruza else 'PASA')
            print(f"  {label:<12}{n:>5}{100*w/n:>7.1f}%{f'[{clo}-{chi}]':>16}{pips/n:>10.2f}  {gate}")
        print("\n  Leer con cuidado: aunque un bucket 'PASE', corre sobre la evaluacion\n"
              "  del ALERT y no sobre P&L de broker. Para accionar hace falta la\n"
              "  medicion limpia hacia adelante (`news_latency_min` en entry_context,\n"
              "  v3.57.0) cruzada contra `mt5_pnl`.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
