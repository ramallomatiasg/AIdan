# -*- coding: utf-8 -*-
"""¿El analisis post-trade del LLM sirve para algo? (READ-ONLY, 11-ago-2026)

CONTEXTO: `post_trade_analysis` tiene 589 filas — un analisis del LLM por cada trade
cerrado. Alimenta `learning_insights` -> `get_learning_adjustments` -> trigger_penalties
(confianza) y sl_tp_advice (SL/TP vivo). Hoy `LEARNING_ADJ_MODE='log'` lo DESCARTA, y la
pregunta del user es correcta: se construyo para que AIdan aprenda de su experiencia.

Antes de encenderlo hay que contestar si TIENE SEÑAL. Se mide igual que se midio el LLM de
news (24-jul), que resulto tener CERO habilidad direccional:

  METRICA TITULAR = DISCRIMINACION. No "¿cuantas veces acierta?" (eso lo infla el base rate:
  si el 62% de los trades pierde, decir siempre "mala entrada" acierta 62% sin saber nada),
  sino:  P(dice 'good' | GANO)  −  P(dice 'good' | PERDIO)
  Si es ~0, el juicio del LLM NO lleva informacion sobre el trade que acaba de leer.

  ⚠️ CAVEAT que hay que tener presente al leer el numero: el analyzer RECIBE el resultado
  del trade en su input (`result`, `pips`, `mt5_pnl`). O sea que ni siquiera tiene que
  predecir nada — le alcanza con ser coherente con un dato que ya tiene en la mano.
  Discriminacion ~0 con la respuesta servida es un piso MUY bajo que no pasa.

Tambien mide:
  - DIVERSIDAD: ¿son juicios distintos o el mismo template repetido?
  - EL CONSEJO DE SL: ¿`recommended_sl_pips` aporta algo, o solo repite el SL del trade?
  - QUE PASARIA si se enciende: cuantos trades caen en cada balde de trigger_penalties.

No necesita MT5. No escribe nada.
"""
import os
import sqlite3
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM post_trade_analysis").fetchone()[0]
    print(f"\n{'='*70}\nANALISIS POST-TRADE — {total} filas\n{'='*70}")

    # ── 1. DIVERSIDAD ────────────────────────────────────────────────────────
    print("\n[1] ¿Son juicios distintos o un template repetido?")
    n_lec = cur.execute("SELECT COUNT(DISTINCT key_lesson) FROM post_trade_analysis").fetchone()[0]
    n_adj = cur.execute("SELECT COUNT(DISTINCT suggested_adjustment) FROM post_trade_analysis").fetchone()[0]
    print(f"  lecciones distintas : {n_lec}/{total} ({pct(n_lec,total):.0f}%)")
    print(f"  ajustes distintos   : {n_adj}/{total} ({pct(n_adj,total):.0f}%)")
    print("  las 5 lecciones mas repetidas:")
    for r in cur.execute("""SELECT key_lesson, COUNT(*) n FROM post_trade_analysis
                            WHERE key_lesson != '' GROUP BY key_lesson
                            ORDER BY n DESC LIMIT 5"""):
        print(f"    {r['n']:>3}x  {(r['key_lesson'] or '')[:72]}")
    # ¿de que habla? (tema dominante)
    temas = Counter()
    for r in cur.execute("SELECT LOWER(key_lesson) k FROM post_trade_analysis WHERE key_lesson != ''"):
        k = r['k'] or ''
        for t in ('sl', 'stop'):
            if t in k:
                temas['habla del SL'] += 1
                break
        else:
            if 'tp' in k or 'take profit' in k:
                temas['habla del TP'] += 1
            elif 'tiempo' in k or 'timing' in k or 'duracion' in k or 'duración' in k:
                temas['habla del timing'] += 1
            else:
                temas['otro'] += 1
    print("  de que habla la leccion:")
    for t, n in temas.most_common():
        print(f"    {t:<20} {n:>4} ({pct(n,total):.0f}%)")

    # ── 2. DISCRIMINACION (la metrica titular) ───────────────────────────────
    print("\n[2] DISCRIMINACION — ¿el juicio separa ganadores de perdedores?")
    print("    (el LLM YA SABE el resultado: es un piso bajisimo)")
    campos = {
        'entry_quality': 'good',
        'exit_quality': 'good',
        'timing_assessment': 'good',
        'confidence_was': 'accurate',
    }
    resumen = []
    for campo, valor_bueno in campos.items():
        rows = cur.execute(f"""SELECT result, {campo} v, COUNT(*) n FROM post_trade_analysis
            WHERE result IN ('win','loss') AND {campo} IS NOT NULL AND {campo} != ''
            GROUP BY result, {campo}""").fetchall()
        tot = defaultdict(int)
        bueno = defaultdict(int)
        for r in rows:
            tot[r['result']] += r['n']
            if (r['v'] or '').lower() == valor_bueno:
                bueno[r['result']] += r['n']
        p_win = pct(bueno['win'], tot['win'])
        p_loss = pct(bueno['loss'], tot['loss'])
        disc = p_win - p_loss
        resumen.append((campo, valor_bueno, p_win, p_loss, disc, tot['win'], tot['loss']))
        print(f"\n  {campo} == '{valor_bueno}'")
        print(f"    en los que GANARON : {p_win:5.1f}%  (n={tot['win']})")
        print(f"    en los que PERDIERON: {p_loss:5.1f}%  (n={tot['loss']})")
        marca = 'RUIDO — no discrimina' if abs(disc) < 10 else ('discrimina' if disc > 0 else '⚠ INVERTIDO')
        print(f"    >>> discriminacion : {disc:+5.1f} pp   [{marca}]")
        # distribucion completa, para ver si colapsa a un solo valor
        dist = Counter()
        for r in rows:
            dist[r['v']] += r['n']
        tot_all = sum(dist.values())
        top_v, top_n = dist.most_common(1)[0]
        print(f"    valor dominante    : '{top_v}' en {pct(top_n, tot_all):.0f}% de los casos")

    # Fisher exacto sobre la tabla 2x2 (juicio × resultado). Es la misma metrica
    # que se uso para el LLM de news el 24-jul. El gate `verify_finding` no aplica
    # bien aca porque compara contra un baseline de WR, no contra otra celda.
    print("\n  Fisher exacto (juicio 'bueno' × resultado):")
    try:
        from scipy.stats import fisher_exact
        for campo, vb, p_win, p_loss, disc, nw, nl in resumen:
            rows = cur.execute(f"""SELECT result, {campo} v FROM post_trade_analysis
                WHERE result IN ('win','loss') AND {campo} IS NOT NULL AND {campo} != ''""").fetchall()
            wb = sum(1 for r in rows if r['result'] == 'win' and (r['v'] or '').lower() == vb)
            wm = sum(1 for r in rows if r['result'] == 'win') - wb
            lb = sum(1 for r in rows if r['result'] == 'loss' and (r['v'] or '').lower() == vb)
            lm = sum(1 for r in rows if r['result'] == 'loss') - lb
            try:
                _, p = fisher_exact([[wb, wm], [lb, lm]])
                veredicto = 'RUIDO' if p >= 0.05 else 'separa'
                print(f"    {campo:<20} p={p:.4f}  [{veredicto}]   "
                      f"(win {wb}/{wb+wm} · loss {lb}/{lb+lm})")
            except Exception as e:
                print(f"    {campo:<20} (fisher: {e})")
    except ImportError:
        print("    scipy no disponible")

    # ── 3. EL CONSEJO DE SL ──────────────────────────────────────────────────
    print("\n[3] El consejo de SL — ¿aporta algo o repite lo que ya tenia el trade?")
    import json as _j
    recs, acciones = [], Counter()
    for r in cur.execute("SELECT raw_response FROM post_trade_analysis WHERE raw_response IS NOT NULL"):
        try:
            d = _j.loads(r['raw_response'])
        except Exception:
            continue
        acciones[d.get('sl_action', '?')] += 1
        v = d.get('recommended_sl_pips')
        if v:
            try:
                recs.append(float(v))
            except (TypeError, ValueError):
                pass
    print(f"  sl_action: {dict(acciones)}")
    if recs:
        cnt = Counter(recs)
        print(f"  {len(recs)} recomendaciones de SL, {len(cnt)} valores distintos")
        print(f"  los 5 mas repetidos: {cnt.most_common(5)}")
        redondos = sum(n for v, n in cnt.items() if float(v).is_integer() and float(v) % 5 == 0)
        print(f"  terminan en multiplo de 5: {redondos}/{len(recs)} ({pct(redondos,len(recs)):.0f}%)"
              f"   <- si es alto, esta eligiendo numeros lindos, no midiendo el trade")

    # ── 4. QUE PASARIA SI SE ENCIENDE ────────────────────────────────────────
    print("\n[4] Si LEARNING_ADJ_MODE pasara a 'active', ¿que moveria?")
    rows = cur.execute("""SELECT raw_response FROM post_trade_analysis
        WHERE analyzed_at > datetime('now','-48 hours')""").fetchall()
    votos = Counter()
    for r in rows:
        try:
            d = _j.loads(r['raw_response'] or '{}')
        except Exception:
            continue
        cw, eq, xq = d.get('confidence_was'), d.get('entry_quality'), d.get('exit_quality')
        if cw == 'overestimated':
            votos['-2 a la confianza'] += 1
        elif cw == 'accurate' and eq == 'good' and xq == 'good':
            votos['+1 a la confianza'] += 1
        elif cw == 'underestimated' and eq in ('good', 'fair'):
            votos['+1 a la confianza'] += 1
    print(f"  ventana de 48h que lee get_learning_adjustments: {len(rows)} analisis")
    print(f"  votos que emitirian: {dict(votos) if votos else 'ninguno'}")

    conn.close()
    print(f"\n{'='*70}\n")


if __name__ == '__main__':
    main()
