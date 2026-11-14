"""
backtest_p44_gotobi_fin_de_mes.py — P44: corto CHFJPY/NZDJPY de 00:55 a 03:00 UTC el último día hábil del mes.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000/{CHFJPY,NZDJPY}` (reservados de Fase 4).
Criterio declarado ANTES de medir: docs/p44_gotobi_fin_de_mes_criterio.md (71db919). Leer contra eso.

Uso:
    python tools/backtest_p44_gotobi_fin_de_mes.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_fase4_planes import load_pair  # noqa: E402
from tools.backtest_p34_gotobi import gotobi_days  # noqa: E402

SYMS = ['CHFJPY', 'NZDJPY']
CONTROL_REPS = 2000
MIN_N = 120
PESSIMISTIC_EXTRA = 0.3
SEED = 20261114
OUT = os.path.join(ROOT, 'docs', 'p44_gotobi_fin_de_mes_resultado.json')


def last_business_day(y, m):
    d = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(1)
    while d.weekday() >= 5:
        d -= timedelta(1)
    return d


def run_pair(sym):
    P = load_pair(sym)
    utc = P['utc']
    pos = {int(x): i for i, x in enumerate(utc)}
    pip, comm = P['pip'], P['spec']['commission_pips']
    d0 = datetime.fromtimestamp(int(utc[0]), timezone.utc).date() + timedelta(1)
    d1 = datetime.fromtimestamp(int(utc[-1]), timezone.utc).date() - timedelta(1)
    eom = {last_business_day(y, m) for y in range(d0.year, d1.year + 1) for m in range(1, 13)}
    other_g = gotobi_days(d0.year, d1.year) - eom

    def short(d):
        a = int(datetime(d.year, d.month, d.day, 0, 55, tzinfo=timezone.utc).timestamp())
        b = int(datetime(d.year, d.month, d.day, 3, 0, tzinfo=timezone.utc).timestamp())
        i, j = pos.get(a), pos.get(b)
        if i is None or j is None:
            return None
        g = -(P['o'][j] - P['o'][i]) / pip
        return g, g - comm - P['spr'][i]

    ev, ctrl, other, dropped = [], {}, [], 0
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            w = short(d)
            if d in eom:
                if w is None:
                    dropped += 1
                else:
                    ev.append(dict(d=d, sym=sym, gross=w[0], net=w[1]))
            elif w is not None:
                ctrl.setdefault(d.year, []).append(w[1])
                if d in other_g:
                    other.append(w[1])
        d += timedelta(1)
    return ev, {y: np.array(x) for y, x in ctrl.items()}, dropped, other


def control_p(ev, ctrls, rng):
    tot = np.zeros(CONTROL_REPS)
    for e in ev:
        c = ctrls[e['sym']][e['d'].year]
        tot += c[rng.integers(0, c.size, CONTROL_REPS)]
    cs = np.sort(tot / len(ev))
    return float(cs[CONTROL_REPS // 2]), float(cs[int(0.95 * CONTROL_REPS)])


def summary(ev, ctrls, rng, label):
    ev = sorted(ev, key=lambda e: e['d'])
    v = np.array([e['net'] for e in ev])
    g = np.array([e['gross'] for e in ev])
    lo, hi, _ = bootstrap_ci(v)
    half = v.size // 2
    h1, h2 = float(v[:half].mean()), float(v[half:].mean())
    p50, p95 = control_p(ev, ctrls, rng)
    print(f"{label}: n={v.size}  bruto {g.mean():+.2f}p  neto {v.mean():+.2f}p  ganados {(v > 0).mean():.0%}  "
          f"CI [{lo:+.2f}, {hi:+.2f}]  mitades {h1:+.2f}/{h2:+.2f}  control p50 {p50:+.2f} p95 {p95:+.2f}")
    by_year = {}
    for e in ev:
        by_year.setdefault(e['d'].year, []).append(e['gross'])
    print('   bruto por año: ' + '  '.join(f"{y} {np.mean(x):+.2f}" for y, x in sorted(by_year.items())))
    return dict(n=int(v.size), gross=float(g.mean()), net=float(v.mean()), win=float((v > 0).mean()),
                ci=[lo, hi], halves=[h1, h2], ctrl_p50=p50, ctrl_p95=p95,
                by_year={int(y): float(np.mean(x)) for y, x in by_year.items()})


def main():
    rng = np.random.default_rng(SEED)
    allev, ctrls, per = [], {}, {}
    for s in SYMS:
        ev, c, dr, other = run_pair(s)
        ctrls[s] = c
        allev += ev
        per[s] = summary(ev, ctrls, rng, s)
        per[s]['dropped'] = dr
        per[s]['desc_otros_gotobi'] = dict(n=len(other), net=float(np.mean(other)))
        print(f"   [desc] otros gotobi {s}: n={len(other)} neto {np.mean(other):+.2f}p  (descartados fin de mes: {dr})")
    tot = summary(allev, ctrls, rng, 'CHFJPY+NZDJPY')
    crit = {
        f'1_n>={MIN_N}': tot['n'] >= MIN_N,
        '2_media>0_CI_inf>0': bool(tot['net'] > 0 and tot['ci'][0] is not None and tot['ci'][0] > 0),
        '3_dos_mitades>0': all(h > 0 for h in tot['halves']),
        '4_>control_p95': tot['net'] > tot['ctrl_p95'],
        '5_>0_costo_pesimista': tot['net'] - PESSIMISTIC_EXTRA > 0,
        '6_cada_par>0': all(per[s]['net'] > 0 for s in SYMS),
    }
    for k, ok in crit.items():
        print(f"    [{'OK ' if ok else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p44_gotobi_fin_de_mes_criterio.md (71db919)', total=tot, por_par=per,
                       criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
