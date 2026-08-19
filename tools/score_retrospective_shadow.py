"""Scorer de la retrospectiva PRE-decision en shadow (v3.57.0). READ-ONLY.

Responde la UNICA pregunta que decide si esto se activa o se apaga:

    ¿los trades que la retrospectiva marco `contrarian` les fue PEOR que a los
    que marco `aligned` / `neutral`?

Si no separa, el veredicto no discrimina y el nudge se apaga — el principio
rector del proyecto es que un fix que no arregla nada empeora.

CRITERIO PRE-DECLARADO (escrito antes de tener numeros, 19-ago)
--------------------------------------------------------------
Para pasar `RETRO_MODE=active` tienen que cumplirse las CUATRO:
  1. n >= 25 trades marcados `contrarian` con resultado cerrado.
  2. WR(contrarian) por DEBAJO del WR de los no-contrarian del MISMO periodo.
  3. El CI95 de Wilson de WR(contrarian) NO cruza el WR del comparador.
  4. El PnL/trade de `contrarian` es negativo Y peor que el del comparador.

Lo que NO alcanza para activar, aunque se vea lindo:
  - `aligned` con buen WR. Que el veredicto acierte del lado bueno es facil
    (arrastra el sesgo de que los setups que venian ganando siguen ganando); lo
    que tiene que demostrar es que detecta lo MALO.
  - una lectura buena con n<25. A ~5 trades/dia y no todas las senales llegando a
    veredicto, n=25 puede tomar semanas. Esperar es la respuesta correcta.

USO
---
    python tools/score_retrospective_shadow.py
    python tools/score_retrospective_shadow.py --since 2026-08-19
"""

import argparse
import math
import os
import sqlite3

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
GATE_MIN_N = 25


def wilson(wins, n, z=1.96):
    """CI95 de Wilson. Mismo metodo que `significance.py` usa en el resto del
    proyecto — no se estrena estadistica nueva para leer este experimento."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(100 * (c - m) / d, 1), round(100 * (c + m) / d, 1))


def _report_missed_factor():
    """v3.57.2 — el otro sentido del lazo: que dice el post-trade que la entrada
    NO estaba mirando.

    Vive en su propia funcion y se llama en TODAS las salidas a proposito: es
    independiente de que haya filas de retrospectiva, y si quedaba dentro del
    flujo principal el early-return de "sin filas todavia" lo dejaba muerto.

    Se lee la ADHERENCIA del modelo antes que el contenido: si un solo valor
    domina, esta contestando por costumbre y el campo no sirve — es el hallazgo
    del A/B de v3.53.7 (timing_assessment constante en el 100%).

    SOLO se cuentan los analisis producidos por v3.57.2+, identificados por que su
    `raw_response` menciona el campo. Las ~210 filas anteriores tienen la columna
    en '' porque la migracion la agrego con DEFAULT '' — contarlas daba "100%
    invalido" y disparaba la alarma sobre data que precede a la feature. Se
    detecta por contenido y no por fecha para no hardcodear un cutover.
    """
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(post_trade_analysis)")]
        if 'missed_factor' not in cols:
            print("\n-- missed_factor --\n  columna todavia no migrada "
                  "(arranca AIdan una vez: init_db la agrega)")
        else:
            mf = conn.execute("""
                SELECT COALESCE(NULLIF(missed_factor,''),'(invalido/vacio)') AS mf, COUNT(*)
                FROM post_trade_analysis
                WHERE raw_response LIKE '%missed_factor%'
                GROUP BY 1 ORDER BY 2 DESC
            """).fetchall()
            tot = sum(n for _, n in mf)
            print("\n-- missed_factor: que NO estaba mirando la entrada (v3.57.2+) --")
            if not tot:
                print("  todavia sin analisis post-trade del codigo nuevo (v3.57.2+).\n"
                      "  Las filas anteriores no tenian el campo y no se cuentan.")
            else:
                for v, n in mf:
                    print(f"  {v:<22} {n:>4}  ({100.0*n/tot:4.1f}%)")
                top = max(n for _, n in mf)
                if top / tot >= 0.80:
                    print(f"\n  !! un solo valor cubre el {100.0*top/tot:.0f}%: el modelo esta "
                          f"contestando por costumbre, no juzgando. Mismo patron que las\n"
                          f"     categoricas que v3.53.7 tuvo que sacar del LLM y pasar a codigo.")
                inval = dict(mf).get('(invalido/vacio)', 0)
                if tot and inval / tot >= 0.30:
                    print(f"\n  !! el {100.0*inval/tot:.0f}% quedo invalido/vacio: el modelo no "
                          f"respeta la lista cerrada. Revisar el prompt antes de usar el campo.")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--since', default='', help='YYYY-MM-DD (default: todo)')
    args = ap.parse_args()

    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row

    if not conn.execute("SELECT name FROM sqlite_master WHERE name='pre_trade_retrospective'").fetchone():
        print("La tabla `pre_trade_retrospective` no existe todavia: arranca AIdan "
              "una vez (init_db la crea) o revisa que RETRO_MODE no este en 'off'.")
        return 1

    where, params = ["r.strategy_id IS NOT NULL"], []
    if args.since:
        where.append("r.created_at >= ?")
        params.append(args.since)

    rows = conn.execute(f"""
        SELECT r.verdict, r.matched_on, r.n_similar, r.conf_delta_suggested,
               r.conf_delta_applied, r.meta_delta_applied, r.lesson_hits,
               r.mode, r.created_at, a.mt5_pnl
        FROM pre_trade_retrospective r
        LEFT JOIN trade_archive a ON a.strategy_id = r.strategy_id
        WHERE {' AND '.join(where)}
        ORDER BY r.created_at ASC
    """, params).fetchall()
    conn.close()

    if not rows:
        print("Sin filas todavia. La retrospectiva escribe una por senal creada.")
        _report_missed_factor()
        return 0

    print(f"=== RETROSPECTIVA PRE-DECISION — shadow ===")
    print(f"filas: {len(rows)}  |  periodo: {rows[0]['created_at']} -> {rows[-1]['created_at']}")
    modos = sorted({r['mode'] for r in rows})
    print(f"modo(s) en el periodo: {', '.join(modos)}")
    if 'active' in modos:
        print("  OJO: hay filas en 'active' => el delta SI se aplico en parte del periodo.")

    # Cobertura: cuantas senales llegaron a veredicto util
    print("\n-- veredictos emitidos --")
    by_v = {}
    for r in rows:
        by_v.setdefault(r['verdict'], []).append(r)
    for v, rs in sorted(by_v.items(), key=lambda kv: -len(kv[1])):
        cerrados = [x for x in rs if x['mt5_pnl'] is not None]
        print(f"  {v:<13} n={len(rs):<4} (cerrados {len(cerrados)})")

    if by_v.get('error'):
        print(f"\n  !! {len(by_v['error'])} veredictos 'error': el subsistema esta "
              f"fallando, no 'no encontrando patron'. Revisar aidan.log (WARNING).")

    # El corazon: contrarian vs el resto, mismo periodo
    closed = [r for r in rows if r['mt5_pnl'] is not None]
    contra = [r for r in closed if r['verdict'] == 'contrarian']
    resto = [r for r in closed if r['verdict'] in ('aligned', 'neutral', 'insufficient')]

    def stats(rs, label):
        n = len(rs)
        if not n:
            print(f"  {label:<24} n=0")
            return None
        w = sum(1 for r in rs if r['mt5_pnl'] > 0)
        pnl = sum(r['mt5_pnl'] for r in rs)
        wr = 100.0 * w / n
        lo, hi = wilson(w, n)
        print(f"  {label:<24} n={n:<4} WR={wr:5.1f}%  CI95=[{lo}-{hi}]  "
              f"PnL=${pnl:+7.2f}  ${pnl/n:+5.2f}/trade")
        return {'n': n, 'wr': wr, 'lo': lo, 'hi': hi, 'pnl': pnl, 'avg': pnl / n}

    print("\n-- LA COMPARACION QUE DECIDE --")
    c = stats(contra, 'contrarian (la marcada)')
    o = stats(resto, 'resto (comparador)')

    print("\n-- gate pre-declarado --")
    if not c or not o:
        print("  n insuficiente en algun lado: no se concluye. Volver a correr mas adelante.")
        _report_missed_factor()
        return 0

    cond = [
        (c['n'] >= GATE_MIN_N, f"n(contrarian) >= {GATE_MIN_N}", f"n={c['n']}"),
        (c['wr'] < o['wr'], "WR(contrarian) < WR(resto)",
         f"{c['wr']:.1f}% vs {o['wr']:.1f}%"),
        (c['hi'] < o['wr'], "CI95 de contrarian NO cruza el WR del resto",
         f"CI hasta {c['hi']}% vs {o['wr']:.1f}%"),
        (c['avg'] < 0 and c['avg'] < o['avg'], "PnL/trade negativo y peor que el resto",
         f"${c['avg']:+.2f} vs ${o['avg']:+.2f}"),
    ]
    for ok, nombre, detalle in cond:
        print(f"  [{'OK ' if ok else 'NO '}] {nombre}  ({detalle})")

    if all(x[0] for x in cond):
        print("\n  => LAS 4 SE CUMPLEN. El veredicto discrimina: recomendable pasar a\n"
              "     RETRO_MODE=active (env, sin rebuild) como UN cambio, y re-medir.")
    else:
        print("\n  => NO pasa. El veredicto todavia no demostro que separe ganar de\n"
              "     perder. Sigue en shadow. Si esto se repite con n>=40, apagarlo\n"
              "     (RETRO_MODE=off) en vez de seguir buscandole la vuelta.")

    # Lecciones acumuladas: si esto no crece, el loop esta muerto
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    n_les = conn.execute("SELECT COUNT(*) FROM directional_lessons").fetchone()[0]
    n_back = conn.execute("SELECT COUNT(*) FROM directional_lessons "
                          "WHERE evidence LIKE '[backfill]%'").fetchone()[0]
    usadas = sum(1 for r in rows if (r['lesson_hits'] or 0) > 0)
    conn.close()
    print(f"\n-- loop de lecciones direccionales --")
    print(f"  lecciones: {n_les} (del backfill {n_back}, nuevas del path vivo {n_les - n_back})")
    print(f"  senales que consultaron al menos 1 leccion: {usadas}/{len(rows)}")
    if usadas == 0:
        print("  !! 0 consultas: el loop esta escrito pero NO se esta usando. Es el "
              "sintoma exacto de los 7 mecanismos de aprendizaje ya construidos y "
              "desconectados. Revisar el match por familia de setup.")

    _report_missed_factor()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
