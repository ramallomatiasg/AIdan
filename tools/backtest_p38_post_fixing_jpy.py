"""
backtest_p38_post_fixing_jpy.py — P38: corto EURJPY/AUDJPY de 00:55 a 03:00 UTC los días gotobi.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000/{EURJPY,AUDJPY,USDJPY}`.
Criterio declarado ANTES de medir: docs/p38_post_fixing_jpy_criterio.md (e1fe1b0). Leer contra eso.

Uso:
    python tools/backtest_p38_post_fixing_jpy.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_fase4_planes import load_pair  # noqa: E402
from tools.backtest_p34_gotobi import gotobi_days  # noqa: E402

SYMS = ['EURJPY', 'AUDJPY']
REF = 'USDJPY'          # descriptivo: ya mirado en P34
CONTROL_REPS = 2000
MIN_N = 600
PESSIMISTIC_EXTRA = 0.3
SEED = 20261112
OUT = os.path.join(ROOT, 'docs', 'p38_post_fixing_jpy_resultado.json')


def run_pair(sym):
    P = load_pair(sym)
    utc = P['utc']
    pos = {int(x): i for i, x in enumerate(utc)}
    pip, comm = P['pip'], P['spec']['commission_pips']
    d0 = datetime.fromtimestamp(int(utc[0]), timezone.utc).date() + timedelta(1)
    d1 = datetime.fromtimestamp(int(utc[-1]), timezone.utc).date() - timedelta(1)
    gdays = gotobi_days(d0.year, d1.year)

    def short(d):
        a = int(datetime(d.year, d.month, d.day, 0, 55, tzinfo=timezone.utc).timestamp())
        b = int(datetime(d.year, d.month, d.day, 3, 0, tzinfo=timezone.utc).timestamp())
        i, j = pos.get(a), pos.get(b)
        if i is None or j is None:
            return None
        g = -(P['o'][j] - P['o'][i]) / pip
        return g, g - comm - P['spr'][i]

    ev, ctrl, dropped = [], {}, 0
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            w = short(d)
            if d in gdays:
                if w is None:
                    dropped += 1
                else:
                    ev.append(dict(d=d, sym=sym, gross=w[0], net=w[1]))
            elif w is not None:
                ctrl.setdefault(d.year, []).append(w[1])
        d += timedelta(1)
    return ev, {y: np.array(x) for y, x in ctrl.items()}, dropped


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
        ev, c, dr = run_pair(s)
        ctrls[s] = c
        allev += ev
        per[s] = summary(ev, ctrls, rng, s)
        per[s]['dropped'] = dr
    tot = summary(allev, ctrls, rng, 'EURJPY+AUDJPY')
    ref_ev, ref_c, _ = run_pair(REF)
    ref = summary(ref_ev, {REF: ref_c}, rng, f'[desc] {REF}')
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
        json.dump(dict(criterio='docs/p38_post_fixing_jpy_criterio.md (e1fe1b0)', total=tot, por_par=per,
                       ref_usdjpy=ref, criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
