"""
backtest_p14_carry_solo.py — P14: carry solo (sin tendencia), SOLO en los 6 reservados, una sola corrida.

READ-ONLY. Sin MT5, no toca la DB. Reusa tools/backtest_p11_carry.py (importado).
Criterio declarado ANTES de medir: docs/p14_carry_solo_criterio.md (4d73183).

Uso:
    python tools/backtest_p14_carry_solo.py
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p11_carry import (Pair, load_rates, rule_carry, weekly, control, net,  # noqa: E402
                                      CONTROL_REPS, SEED)

MIN_N = 150
OUT = os.path.join(ROOT, 'docs', 'p14_carry_solo_resultado.json')


def main():
    if os.path.exists(OUT):
        sys.exit('P14 ya se corrió sobre los reservados (una sola vez). No se re-corre.')
    rates = load_rates()
    P = {s: Pair(s, rates) for s in RESERVADOS}
    rows = {s: P[s].weeks(rule_carry) for s in RESERVADOS}
    ws, wr = weekly(rows)
    allx = [x for s in rows for x in rows[s]]
    comp = {k: float(np.mean([x[k] for x in allx])) for k in ('price', 'swap', 'cost')}
    for s in RESERVADOS:
        r = rows[s]
        lg = sum(1 for x in r if x['pos'] > 0)
        print(f"    {s:7s} n={len(r):4d} (largos {lg})  suma neta {sum(net(x) for x in r):+.2f}%  "
              f"precio {sum(x['price'] for x in r):+.2f}  swap {sum(x['swap'] for x in r):+.2f}")
    lo, hi, _ = bootstrap_ci(wr)
    half = wr.size // 2
    h1, h2 = float(wr[:half].mean()), float(wr[half:].mean())
    rng = np.random.default_rng(SEED)
    ctrl = np.sort([control(P, rows, rng) for _ in range(CONTROL_REPS)])
    p95 = float(ctrl[int(0.95 * CONTROL_REPS)])
    crit = {f'1_n>={MIN_N}': len(allx) >= MIN_N,
            '2_media>0_CI_inf>0': bool(wr.mean() > 0 and lo is not None and lo > 0),
            '3_dos_mitades>0': h1 > 0 and h2 > 0,
            '4_>control_p95': bool(wr.mean() > p95)}
    ok = all(crit.values())
    print(f"\nposiciones-semana {len(allx)}  semanas {ws.size}  media semanal {wr.mean():+.4f}% "
          f"(~{wr.mean() * 52:+.2f}%/año)  (precio {comp['price']:+.4f} + swap {comp['swap']:+.4f} - costo "
          f"{comp['cost']:.4f})")
    print(f"CI [{lo:+.4f}, {hi:+.4f}]  mitades {h1:+.4f} / {h2:+.4f}  control mediana "
          f"{ctrl[CONTROL_REPS // 2]:+.4f} p95 {p95:+.4f}")
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p14_carry_solo_criterio.md (4d73183)', n=len(allx), weeks=int(ws.size),
                       mean_week=float(wr.mean()), ci=[lo, hi], halves=[h1, h2], control_p95=p95, comp=comp,
                       criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
