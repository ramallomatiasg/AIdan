"""Siembra `directional_lessons` desde el historico (v3.57.0). READ-ONLY sobre
`trade_archive`; lo unico que escribe son filas nuevas en `directional_lessons`.

POR QUE EXISTE
--------------
La retrospectiva pre-trade lee lecciones direccionales. Si la tabla arranca
vacia, el mecanismo esta tecnicamente vivo pero ciego durante semanas — que es
como se ven, desde afuera, los siete mecanismos de aprendizaje que este proyecto
construyo y nunca conecto. Esto le da estado inicial.

Y cubre un segundo hueco: en el path vivo la leccion la deriva
`analyze_closed_trade`, que **necesita Ollama arriba**. Con Ollama caido el trade
se archiva igual pero la leccion se pierde. Corriendo esto cada tanto se
recuperan.

CRITERIO (identico al del path vivo, `derive_directional_lesson`)
----------------------------------------------------------------
Leccion solo si: perdio plata **y** nunca se puso a favor (<20 % del TP) **y**
pego el SL. Las tres juntas.

LIMITE DECLARADO
----------------
`trade_archive` no guarda el MFE (el maximo a favor), asi que aca se usa
`max(0, pips)` como **cota inferior** — la misma convencion que usa el analyzer
cuando no tiene datos de excursion. Efecto: un trade que subio 60 % del TP y
despues se dio vuelta hasta el SL **puede** entrar como leccion, cuando en
realidad fue un problema de GESTION, no de direccion. Es un falso positivo
posible y esta asumido: sesga hacia MAS lecciones, no menos.
Las filas del path vivo (que si tienen MFE real) no tienen este problema — se
distinguen por `evidence` (las de aca llevan el prefijo `[backfill]`).

USO
---
    python tools/backfill_directional_lessons.py              # dry-run (default)
    python tools/backfill_directional_lessons.py --apply
    python tools/backfill_directional_lessons.py --apply --since 2026-06-20
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer.post_trade_analyzer import derive_directional_lesson  # noqa: E402
from src.analyzer.pre_trade_retrospective import setup_family  # noqa: E402

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='escribe (default: dry-run)')
    ap.add_argument('--since', default='2026-06-20',
                    help='solo trades creados desde esta fecha. Default 2026-06-20 = '
                         'la frontera de "data limpia" del proyecto (post v3.40.18/19).')
    args = ap.parse_args()

    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT strategy_id, direction, setup_type, trigger_type, volatility, session,
               htf_bias, pips, sl_pips, tp_pips, mt5_pnl, created_at
        FROM trade_archive
        WHERE mt5_pnl IS NOT NULL AND created_at >= ?
        ORDER BY created_at ASC
    """, (args.since,)).fetchall()

    existing = {r[0] for r in conn.execute(
        "SELECT strategy_id FROM directional_lessons").fetchall()}

    lessons, skipped_dupe = [], 0
    for r in rows:
        pips = float(r['pips'] or 0)
        sl_pips = float(r['sl_pips'] or 0)
        tp_pips = float(r['tp_pips'] or 0)
        mfe = max(0.0, pips)                      # cota INFERIOR (ver docstring)
        pct_tp = (100.0 * mfe / tp_pips) if tp_pips > 0 else 0.0
        hit_sl = pips < 0 and sl_pips > 0 and abs(pips) >= 0.9 * sl_pips

        lesson = derive_directional_lesson(
            direction=r['direction'], mt5_pnl=r['mt5_pnl'], pct_tp=pct_tp,
            mfe_pips=mfe, pips=pips, sl_pips=sl_pips, hit_sl=hit_sl)
        if not lesson:
            continue
        if r['strategy_id'] in existing:
            skipped_dupe += 1
            continue
        lesson.update({
            'strategy_id': r['strategy_id'],
            'setup_type': r['setup_type'] or r['trigger_type'] or '',
            'trigger_type': r['trigger_type'] or '',
            'volatility': r['volatility'] or '',
            'session': r['session'] or '',
            'htf_bias': r['htf_bias'] or '',
            'evidence': '[backfill] ' + lesson['evidence'],
        })
        lessons.append(lesson)

    print(f"trades revisados : {len(rows)} (desde {args.since})")
    print(f"lecciones nuevas : {len(lessons)}")
    print(f"ya existentes    : {skipped_dupe}")

    # Resumen por familia + direccion: es la vista que consume la retrospectiva.
    agg = {}
    for l in lessons:
        key = (setup_family(l['setup_type']), l['better_direction'])
        agg[key] = agg.get(key, 0) + 1
    if agg:
        print("\npor familia -> direccion que hubiera pagado:")
        for (fam, bd), n in sorted(agg.items(), key=lambda kv: -kv[1]):
            print(f"  {fam:<22} {bd:<5} {n}")

    if not args.apply:
        print("\nDRY-RUN: no se escribio nada. Correr con --apply para persistir.")
        conn.close()
        return 0

    conn.close()
    from src.common.db import add_directional_lesson
    written = sum(add_directional_lesson(l) or 0 for l in lessons)
    print(f"\nescritas: {written}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
