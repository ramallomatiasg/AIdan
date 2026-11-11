"""
backtest_p34_gotobi.py — P34: efecto Gotobi (fixing de Tokio) en USD/JPY, dic-2019 → ago-2026.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000/USDJPY`.
Criterio declarado ANTES de medir: docs/p34_gotobi_criterio.md (84834f6). Leer contra eso.

Largo 00:00 → 00:55 UTC los días gotobi. Control: misma ventana en días hábiles no gotobi del mismo año.

Uso:
    python tools/backtest_p34_gotobi.py
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

SYM = 'USDJPY'
CONTROL_REPS = 2000
MIN_N = 300
PESSIMISTIC_EXTRA = 0.3
SEED = 20261111
OUT = os.path.join(ROOT, 'docs', 'p34_gotobi_resultado.json')


def gotobi_days(y0, y1):
    out = set()
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(1)).day
            for dd in (5, 10, 15, 20, 25, last):
                d = date(y, m, dd)
                while d.weekday() > 4:
                    d -= timedelta(1)
                out.add(d)
    return out


def main():
    P = load_pair(SYM)
    utc = P['utc']
    pos = {int(x): i for i, x in enumerate(utc)}
    pip, comm = P['pip'], P['spec']['commission_pips']
    d0 = datetime.fromtimestamp(int(utc[0]), timezone.utc).date() + timedelta(1)
    d1 = datetime.fromtimestamp(int(utc[-1]), timezone.utc).date() - timedelta(1)
    gdays = gotobi_days(d0.year, d1.year)

    def window(d, h0, m0, h1, m1):
        a = int(datetime(d.year, d.month, d.day, h0, m0, tzinfo=timezone.utc).timestamp())
        b = int(datetime(d.year, d.month, d.day, h1, m1, tzinfo=timezone.utc).timestamp())
        i, j = pos.get(a), pos.get(b)
        if i is None or j is None:
            return None
        return (P['o'][j] - P['o'][i]) / pip, P['spr'][i]

    ev, ctrl, dropped = [], {}, 0
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            w = window(d, 0, 0, 0, 55)
            if d in gdays:
                if w is None:
                    dropped += 1
                else:
                    post = window(d, 0, 55, 3, 0)
                    ev.append(dict(d=d, gross=w[0], net=w[0] - comm - w[1],
                                   post_short=None if post is None else -post[0] - comm - post[1]))
            elif w is not None:
                ctrl.setdefault(d.year, []).append(w[0] - comm - w[1])
        d += timedelta(1)

    v = np.array([e['net'] for e in ev])
    g = np.array([e['gross'] for e in ev])
    ctrl = {y: np.array(x) for y, x in ctrl.items()}
    rng = np.random.default_rng(SEED)
    tot = np.zeros(CONTROL_REPS)
    for e in ev:
        c = ctrl[e['d'].year]
        tot += c[rng.integers(0, c.size, CONTROL_REPS)]
    cs = np.sort(tot / len(ev))
    cp50, cp95 = float(cs[CONTROL_REPS // 2]), float(cs[int(0.95 * CONTROL_REPS)])
    lo, hi, _ = bootstrap_ci(v)
    half = v.size // 2
    h1, h2 = float(v[:half].mean()), float(v[half:].mean())
    pess = float(v.mean() - PESSIMISTIC_EXTRA)
    ctrl_gross = float(np.mean(np.concatenate(list(ctrl.values()))) + comm)  # aprox. (spread mínimo ~0)
    crit = {
        f'1_n>={MIN_N}': bool(v.size >= MIN_N),
        '2_media>0_CI_inf>0': bool(v.mean() > 0 and lo is not None and lo > 0),
        '3_dos_mitades>0': h1 > 0 and h2 > 0,
        '4_>control_p95': bool(v.mean() > cp95),
        '5_>0_costo_pesimista': pess > 0,
    }
    print(f"USDJPY gotobi 00:00->00:55 UTC: n={v.size} (descartados {dropped})")
    print(f"  bruto {g.mean():+.2f}p  neto {v.mean():+.2f}p  mediana {np.median(v):+.2f}  ganados {(v > 0).mean():.0%}")
    print(f"  CI [{lo:+.2f}, {hi:+.2f}]  mitades {h1:+.2f} / {h2:+.2f}  pesimista {pess:+.2f}")
    print(f"  control (no gotobi): bruto medio ~{ctrl_gross:+.2f}p  p50 {cp50:+.2f}  p95 {cp95:+.2f}  "
          f"(días {sum(x.size for x in ctrl.values())})")
    by_year = {}
    for e in ev:
        by_year.setdefault(e['d'].year, []).append(e['gross'])
    print('  bruto por año: ' + '  '.join(f"{y} {np.mean(x):+.2f} (n={len(x)})" for y, x in sorted(by_year.items())))
    ps = np.array([e['post_short'] for e in ev if e['post_short'] is not None])
    print(f"  [desc] corto 00:55->03:00: neto {ps.mean():+.2f}p n={ps.size} ganados {(ps > 0).mean():.0%}")
    for k, ok in crit.items():
        print(f"    [{'OK ' if ok else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p34_gotobi_criterio.md (84834f6)', n=int(v.size), dropped=dropped,
                       gross=float(g.mean()), net=float(v.mean()), ci=[lo, hi], halves=[h1, h2], pessimistic=pess,
                       ctrl_p50=cp50, ctrl_p95=cp95, ctrl_gross_approx=ctrl_gross,
                       by_year={y: float(np.mean(x)) for y, x in by_year.items()},
                       post_short_net=float(ps.mean()), criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
