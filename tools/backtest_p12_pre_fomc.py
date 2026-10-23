"""
backtest_p12_pre_fomc.py — P12: drift pre-FOMC (Lucca & Moench 2015) en índices, 2020-2026.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p1/M15`.
Criterio declarado ANTES de medir: docs/p12_pre_fomc_criterio.md (c1671b6). Leer contra eso.

Largo 21:00 server del día hábil anterior al comunicado (14:00 ET) → salida 20:45 server del día del comunicado
(13:45 ET). Server = NY+7h todo el año. Neto en % del precio.

Uso:
    python tools/backtest_p12_pre_fomc.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_p1', 'M15')
MAIN = ['USTEC', 'US30']
DESC = ['DE40', 'XAUUSD', 'EURUSD']
FIN_PCT = 0.02            # financiación por la noche, % del precio
CONTROL_REPS = 5000
MIN_N = 35
SEED = 20261023
OUT = os.path.join(ROOT, 'docs', 'p12_pre_fomc_resultado.json')

FOMC = """2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16""".split()
FOMC_DATES = {date.fromisoformat(x) for x in FOMC}


def load(sym):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.meta.json')) as f:
        meta = json.load(f)
    t = r['time'].astype(np.int64)
    idx = {int(x): i for i, x in enumerate(t)}
    return dict(sym=sym, t=t, o=r['open'].astype(np.float64), spr=r['spread'].astype(np.float64) * meta['point'],
                idx=idx)


def prev_bday(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def window(P, d):
    """Neto % del largo 21:00 server de prev_bday(d) → 20:45 server de d. None si falta una vela."""
    e = datetime(*prev_bday(d).timetuple()[:3], 21, 0, tzinfo=timezone.utc).timestamp()
    x = datetime(*d.timetuple()[:3], 20, 45, tzinfo=timezone.utc).timestamp()
    i, j = P['idx'].get(int(e)), P['idx'].get(int(x))
    if i is None or j is None:
        return None
    pe, px = P['o'][i], P['o'][j]
    cost = (P['spr'][i] + P['spr'][j]) / pe * 100 + FIN_PCT
    return (px - pe) / pe * 100 - cost


def run(sym, rng):
    P = load(sym)
    first = datetime.fromtimestamp(int(P['t'][0]), timezone.utc).date()
    last = datetime.fromtimestamp(int(P['t'][-1]), timezone.utc).date()
    ev, missing = [], 0
    for d in sorted(FOMC_DATES):
        if d <= first + timedelta(days=2) or d > last:
            continue
        v = window(P, d)
        if v is None:
            missing += 1
        else:
            ev.append((d.isoformat(), v))
    ctrl_days = []
    d = first + timedelta(days=3)
    while d <= last:
        if d.weekday() < 5 and d not in FOMC_DATES:
            v = window(P, d)
            if v is not None:
                ctrl_days.append(v)
        d += timedelta(days=1)
    vals = np.array([v for _, v in ev])
    cd = np.array(ctrl_days)
    ctrl = np.sort([rng.choice(cd, vals.size, replace=False).mean() for _ in range(CONTROL_REPS)])
    return dict(sym=sym, n=int(vals.size), missing=missing, events=ev, mean=float(vals.mean()),
                median=float(np.median(vals)), win=float((vals > 0).mean()),
                ctrl_days=int(cd.size), ctrl_day_mean=float(cd.mean()),
                ctrl_p50=float(ctrl[CONTROL_REPS // 2]), ctrl_p95=float(ctrl[int(0.95 * CONTROL_REPS)]))


def main():
    rng = np.random.default_rng(SEED)
    res = {s: run(s, rng) for s in MAIN + DESC}
    print(f"{'sym':7}{'n':>4}{'falt':>5}{'media%':>9}{'mediana%':>10}{'gan':>6}{'dias normales media%':>22}{'ctrl p95':>10}")
    for s in MAIN + DESC:
        r = res[s]
        tag = '' if s in MAIN else '  (descriptivo)'
        print(f"{s:7}{r['n']:>4}{r['missing']:>5}{r['mean']:>+9.3f}{r['median']:>+10.3f}{r['win']:>6.0%}"
              f"{r['ctrl_day_mean']:>+22.3f}{r['ctrl_p95']:>+10.3f}{tag}")
    pool = sorted([(d, v) for s in MAIN for d, v in res[s]['events']])
    pv = np.array([v for _, v in pool])
    lo, hi, _ = bootstrap_ci(pv)
    half = pv.size // 2
    h1, h2 = float(pv[:half].mean()), float(pv[half:].mean())
    crit = {
        f'1_n>={MIN_N}_por_instrumento': all(res[s]['n'] >= MIN_N for s in MAIN),
        '2_media>0_CI_inf>0': bool(pv.mean() > 0 and lo is not None and lo > 0),
        '3_dos_mitades>0': h1 > 0 and h2 > 0,
        '4_>control_p95_en_los_dos': all(res[s]['mean'] > res[s]['ctrl_p95'] for s in MAIN),
        '5_USTEC_y_US30>0': all(res[s]['mean'] > 0 for s in MAIN),
    }
    print(f"\nPOOL USTEC+US30: n={pv.size} media {pv.mean():+.4f}%  CI [{lo:+.4f}, {hi:+.4f}]  "
          f"mitades {h1:+.3f} / {h2:+.3f}")
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p12_pre_fomc_criterio.md (c1671b6)', por_sym=res, pool=dict(
            n=int(pv.size), mean=float(pv.mean()), ci=[lo, hi], halves=[h1, h2]), criterios=crit, PASA=ok),
            f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
