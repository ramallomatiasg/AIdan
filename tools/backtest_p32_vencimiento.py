"""
backtest_p32_vencimiento.py — P32: semana del vencimiento trimestral (triple witching) en índices, 2020-2026.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p1/M15`.
Criterio declarado ANTES de medir: docs/p32_vencimiento_trimestral_criterio.md (66c15c4). Leer contra eso.

Largo del cierre del contado 5 días hábiles antes del 3er viernes de mar/jun/sep/dic al cierre de ese viernes.
Control: ventanas de 5 días hábiles al azar del mismo año fuera de la semana del vencimiento y la siguiente.

Uso:
    python tools/backtest_p32_vencimiento.py
"""
import json
import os
import sys
from datetime import date, timedelta

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p24_prima_nocturna import SWAP_PCT, load  # noqa: E402
from tools.backtest_p25_cambio_de_mes import ev, trading_days  # noqa: E402

MAIN = ['US30', 'USTEC']
DESC = ['DE40']
CONTROL_REPS = 2000
MIN_N = 20
HOLD = 5
SEED = 20261110
OUT = os.path.join(ROOT, 'docs', 'p32_vencimiento_resultado.json')


def third_friday(y, m):
    d = date(y, m, 1)
    d += timedelta(days=(4 - d.weekday()) % 7)
    return d + timedelta(days=14)


def run(sym, rng):
    P = load(sym)
    sw = SWAP_PCT[sym]
    days = trading_days(P, sym)
    pos = {d: k for k, (d, _) in enumerate(days)}
    first, last = days[0][0], days[-1][0]
    exp_k = []
    for y in range(first.year, last.year + 1):
        for m in (3, 6, 9, 12):
            d = third_friday(y, m)
            while d not in pos and d >= first:
                d -= timedelta(days=1)
            k = pos.get(d)
            if k is not None and k - HOLD >= 0 and k + HOLD < len(days):
                exp_k.append(k)
    blocked = set()
    for k in exp_k:
        blocked.update(range(k - HOLD, k + HOLD + 1))
    vals, gross, half, after, rows = [], [], [], [], []
    for k in exp_k:
        v, g, nn = ev(P, days, k - HOLD, k, sw)
        vals.append(v)
        gross.append(g)
        half.append(v + nn * sw / 2)
        after.append(ev(P, days, k, k + HOLD, sw)[1])
        rows.append((days[k][0].isoformat(), v))
    vals, gross, half, after = map(np.array, (vals, gross, half, after))
    by_year = {}
    for k in range(len(days) - HOLD):
        if any(m in blocked for m in range(k, k + HOLD + 1)):
            continue
        by_year.setdefault(days[k][0].year, []).append(ev(P, days, k, k + HOLD, sw)[0])
    by_year = {y: np.array(v) for y, v in by_year.items()}
    tot = np.zeros(CONTROL_REPS)
    for k in exp_k:
        c = by_year[days[k][0].year]
        tot += c[rng.integers(0, c.size, CONTROL_REPS)]
    ctrl = np.sort(tot / len(exp_k))
    return dict(sym=sym, n=int(vals.size), mean=float(vals.mean()), median=float(np.median(vals)),
                win=float((vals > 0).mean()), gross_mean=float(gross.mean()), half_swap_mean=float(half.mean()),
                after_gross_mean=float(after.mean()),
                ctrl_p50=float(ctrl[CONTROL_REPS // 2]), ctrl_p95=float(ctrl[int(0.95 * CONTROL_REPS)]),
                ctrl_pool_n=int(sum(v.size for v in by_year.values())), series=rows)


def main():
    rng = np.random.default_rng(SEED)
    res = {s: run(s, rng) for s in MAIN + DESC}
    print(f"{'sym':6}{'n':>4}{'neto%':>8}{'bruto%':>8}{'1/2sw%':>8}{'gan':>5}{'ctl p50':>9}{'ctl p95':>9}"
          f"{'sem.sig bruto%':>16}")
    for s in MAIN + DESC:
        r = res[s]
        print(f"{s:6}{r['n']:>4}{r['mean']:>+8.3f}{r['gross_mean']:>+8.3f}{r['half_swap_mean']:>+8.3f}"
              f"{r['win']:>5.0%}{r['ctrl_p50']:>+9.3f}{r['ctrl_p95']:>+9.3f}{r['after_gross_mean']:>+16.3f}"
              f"{'' if s in MAIN else '  (descriptivo)'}")
    pool = sorted([(d, v) for s in MAIN for d, v in res[s]['series']])
    pv = np.array([v for _, v in pool])
    lo, hi, _ = bootstrap_ci(pv)
    half = pv.size // 2
    h1, h2 = float(pv[:half].mean()), float(pv[half:].mean())
    crit = {
        f'1_n>={MIN_N}_por_instrumento': all(res[s]['n'] >= MIN_N for s in MAIN),
        '2_media>0_CI_inf>0': bool(pv.mean() > 0 and lo is not None and lo > 0),
        '3_dos_mitades>0': h1 > 0 and h2 > 0,
        '4_>control_p95_en_los_dos': all(res[s]['mean'] > res[s]['ctrl_p95'] for s in MAIN),
        '5_US30_y_USTEC>0': all(res[s]['mean'] > 0 for s in MAIN),
    }
    print(f"\nPOOL US30+USTEC: n={pv.size} media {pv.mean():+.3f}%/evento  CI [{lo:+.3f}, {hi:+.3f}]  "
          f"mitades {h1:+.3f} / {h2:+.3f}")
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    for s in res:
        res[s].pop('series')
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p32_vencimiento_trimestral_criterio.md (66c15c4)', por_sym=res, pool=dict(
            n=int(pv.size), mean=float(pv.mean()), ci=[lo, hi], halves=[h1, h2]), criterios=crit, PASA=ok),
            f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
