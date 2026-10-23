"""
score_shadow_binaria.py — scorer READ-ONLY del shadow P13b (A1 como binaria sobre el precio de Deriv).

Lee `%APPDATA%/AIdan/state/binary_shadow.db` con mode=ro. No toca MT5 ni la DB de AIdan.
Criterio declarado ANTES de juntar: docs/p13b_shadow_binaria_criterio.md (0aa3233). NO mover.

Uso:
    python tools/score_shadow_binaria.py [--db ruta]
"""
import argparse
import os
import sqlite3
import sys

import numpy as np

MIN_N = 400
OFF_N = 800
BE_PROVISORIO = 1 / 1.90       # payout 90% si todavía no hay payout medido
BOOT = 10000
SEED = 20261023


def default_db():
    return os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state', 'binary_shadow.db')


def wilson(k, n, z=1.96):
    if n == 0:
        return float('nan'), float('nan')
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def evaluate(rows):
    """rows: lista de (symbol, created_utc, outcome, payout, ask). Devuelve el dict del veredicto."""
    res = [r for r in rows if r[2] in ('win', 'loss')]
    n = len(res)
    k = sum(1 for r in res if r[2] == 'win')
    lo, hi = wilson(k, n)
    paid = [r for r in res if r[3] and r[4]]
    out = dict(n=n, wins=k, hit=k / n if n else float('nan'), ci=[lo, hi],
               ties=sum(1 for r in rows if r[2] == 'tie'), voids=sum(1 for r in rows if r[2] == 'void'),
               pending=sum(1 for r in rows if r[2] is None), n_payout=len(paid))
    if paid:
        be = np.array([r[4] / r[3] for r in paid])                  # ask / payout total
        ev = np.array([(r[3] - r[4]) / r[4] if r[2] == 'win' else -1.0 for r in paid])
        rng = np.random.default_rng(SEED)
        bs = np.sort(ev[rng.integers(0, ev.size, (BOOT, ev.size))].mean(axis=1))
        out.update(be_median=float(np.median(be)), payout_pct_median=float(np.median(1 / be - 1)),
                   ev=float(ev.mean()), ev_ci=[float(bs[int(0.025 * BOOT)]), float(bs[int(0.975 * BOOT)])])
        c1 = n > 0 and lo > out['be_median']
        c2 = out['ev_ci'][0] > 0
        out['provisorio'] = False
    else:
        out.update(be_median=BE_PROVISORIO, provisorio=True)
        c1 = n > 0 and lo > BE_PROVISORIO
        c2 = None
    out['criterios'] = {'1_CI_inf>break_even': c1, '2_EV_CI_inf>0': c2}
    if n < MIN_N:
        out['veredicto'] = f'SIN VEREDICTO (n={n} < {MIN_N})'
    elif c1 and (c2 is True):
        out['veredicto'] = 'PASA'
    elif c1 and c2 is None:
        out['veredicto'] = 'PASA PROVISORIO (sin payout medido: cargar DERIV_APP_ID)'
    else:
        out['veredicto'] = 'NO PASA' + (f' — a n>={OFF_N}: apagar la tarea' if n >= OFF_N else '')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=default_db())
    a = ap.parse_args()
    if not os.path.exists(a.db):
        sys.exit(f'No existe {a.db}: el shadow todavía no corrió.')
    conn = sqlite3.connect(f'file:{a.db}?mode=ro', uri=True)
    rows = conn.execute("SELECT symbol, created_utc, outcome, proposal_payout, proposal_ask FROM signals").fetchall()
    first = conn.execute("SELECT MIN(created_utc), MAX(created_utc) FROM signals").fetchone()
    errs = conn.execute("SELECT proposal_error, COUNT(*) FROM signals WHERE proposal_error IS NOT NULL "
                        "GROUP BY proposal_error").fetchall()
    ev = evaluate(rows)
    print('=' * 72)
    print('SHADOW BINARIA (P13b) — A1 sobre el precio de Deriv, expiración 15 min, 07-16 UTC')
    print('=' * 72)
    print(f"señales {len(rows)}  ({first[0]} -> {first[1]})  resueltas {ev['n']}  empates {ev['ties']}  "
          f"void {ev['voids']}  pendientes {ev['pending']}")
    print(f"acierto {ev['hit']:.2%}  CI95 [{ev['ci'][0]:.2%}, {ev['ci'][1]:.2%}]" if ev['n'] else 'acierto: -')
    if ev['n_payout']:
        print(f"payout real: n={ev['n_payout']}  mediana {ev['payout_pct_median']:.1%} sobre el monto  "
              f"=> break-even {ev['be_median']:.2%}  |  EV por $1 {ev['ev']:+.4f}  CI [{ev['ev_ci'][0]:+.4f}, "
              f"{ev['ev_ci'][1]:+.4f}]")
    else:
        print(f"payout real: SIN MEDIR {dict(errs) if errs else ''} -> se compara contra {BE_PROVISORIO:.2%} "
              f"(payout 90%)")
    by = {}
    for r in rows:
        if r[2] in ('win', 'loss'):
            by.setdefault(r[0], []).append(r[2] == 'win')
    for s in sorted(by):
        v = by[s]
        print(f"    {s:10s} n={len(v):4d}  acierto {np.mean(v):.1%}")
    hrs = {}
    for r in rows:
        if r[2] in ('win', 'loss'):
            hrs.setdefault(int(r[1][11:13]), []).append(r[2] == 'win')
    if hrs:
        print('    por hora UTC: ' + '  '.join(f'{h:02d}h {np.mean(v):.0%} (n={len(v)})' for h, v in sorted(hrs.items())))
    for k, v in ev['criterios'].items():
        print(f"    [{'OK ' if v else ('-- ' if v is None else 'NO ')}] {k}")
    print(f">>> {ev['veredicto']}")


if __name__ == '__main__':
    main()
