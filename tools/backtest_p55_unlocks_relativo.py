"""
backtest_p55_unlocks_relativo.py — P55: corto la moneda que desbloquea y largo una cesta de las otras (D-7 → D),
SOLO sobre la reserva 2025 → oct-2026 (un disparo).

READ-ONLY. Sin MT5, no toca la DB. Reusa el calendario y la cache de P49 (tools/p49_unlocks_data.py,
tools/backtest_p49_unlocks.py, .cache_p49/px/).
Criterio declarado ANTES de medir: docs/p55_desbloqueos_relativos_criterio.md (96174c7). Leer contra eso.

    python tools/backtest_p55_unlocks_relativo.py
"""
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p49_unlocks as P  # noqa: E402

OUT = os.path.join(P.ROOT, 'docs', 'p55_desbloqueos_relativos_resultado.json')
COST, PESS = 0.004, 0.008
REPS, BOOT, SEED = 2000, 5000, 20261118
D0, D1 = dt.date(2025, 1, 1), dt.date(2026, 10, 15)
EPOCH = dt.date(1970, 1, 1)


def main():
    ev = P.eligible()
    allday = {}
    for e in ev:
        allday.setdefault(e['sym'], []).append(e['day'])
    data = {}
    for sym in sorted(allday):
        perp = next(e['perp'] for e in ev if e['sym'] == sym)
        D = P.fetch(perp)
        ft = np.array([x[0] for x in D['f']], dtype=np.int64)
        fr = np.array([x[1] for x in D['f']])
        data[sym] = (dict(D['k']), ft, fr, np.array(allday[sym]))

    def leg(sym, a, b):
        o, ft, fr, _ = data[sym]
        return P.short_ret(o, ft, fr, a, b)          # (−r, funding cobrado por el corto)

    basket_cache = {}

    def basket(a, b, excl):
        key = (a, b)
        if key not in basket_cache:
            v = {}
            for s, (o, ft, fr, evd) in data.items():
                if np.any(np.abs(evd - b) <= 14):
                    continue
                r = leg(s, a, b)
                if r is not None:
                    v[s] = (-r[0], -r[1])            # largo: +r, paga el funding
            basket_cache[key] = v
        v = {s: x for s, x in basket_cache[key].items() if s != excl}
        if len(v) < 5:
            return None
        return float(np.mean([x[0] for x in v.values()])), float(np.mean([x[1] for x in v.values()])), len(v)

    rng = np.random.default_rng(SEED)
    rows, drop, ctrl = [], 0, {}
    for e in ev:
        d = EPOCH + dt.timedelta(e['day'])
        if not (D0 <= d <= D1):
            continue
        s, a, b = e['sym'], e['day'] - 7, e['day']
        sh = leg(s, a, b)
        bk = basket(a, b, s)
        if sh is None or bk is None:
            drop += 1
            continue
        key = (s, d.year)
        if key not in ctrl:
            o, ft, fr, evd = data[s]
            pool = []
            for s0 in o:
                if (EPOCH + dt.timedelta(s0)).year != d.year or np.any(np.abs(evd - (s0 + 7)) <= 14):
                    continue
                cs, cb = leg(s, s0, s0 + 7), basket(s0, s0 + 7, s)
                if cs is not None and cb is not None:
                    pool.append(cs[0] + cs[1] + cb[0] + cb[1] - COST)
            ctrl[key] = np.array(pool)
        net = sh[0] + sh[1] + bk[0] + bk[1] - COST
        rows.append(dict(sym=s, date=e['date'], day=e['day'], frac=e['frac'], short=sh[0], fs=sh[1], bask=bk[0],
                         fb=bk[1], nb=bk[2], net=net))
    rows.sort(key=lambda x: x['day'])
    net = np.array([x['net'] for x in rows]); n = net.size
    lo, hi, nw = P.cluster_ci(net, np.array([x['day'] // 7 for x in rows]), rng)
    h = n // 2
    h1, h2 = float(net[:h].mean()), float(net[h:].mean())
    pools = [ctrl[(x['sym'], int(x['date'][:4]))] for x in rows]
    ok_c = [p for p in pools if p.size]
    cm = np.sort(np.mean([p[rng.integers(0, p.size, REPS)] for p in ok_c], axis=0))
    p50, p95 = float(cm[REPS // 2]), float(cm[int(.95 * REPS)])
    print(f'RESERVA 2025 → oct-2026: n={n} (descartados {drop}, monedas {len({x["sym"] for x in rows})}, semanas {nw}, '
          f'cesta mediana {np.median([x["nb"] for x in rows]):.0f} monedas)')
    print(f'  pata corta {np.mean([x["short"] for x in rows]):+.2%} (+funding {np.mean([x["fs"] for x in rows]):+.3%})  '
          f'pata cesta {np.mean([x["bask"] for x in rows]):+.2%} (funding {np.mean([x["fb"] for x in rows]):+.3%})')
    print(f'  NETO {net.mean():+.2%}  mediana {np.median(net):+.2%}  ganados {(net > 0).mean():.0%}  peor {net.min():+.2%}')
    print(f'  CI95 agrupado por semana [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  '
          f'control p50 {p50:+.2%} p95 {p95:+.2%} (sin pool {len(pools) - len(ok_c)})')
    for lab, f in [('1-3%', lambda z: z < .03), ('3-10%', lambda z: .03 <= z < .1), ('>10%', lambda z: z >= .1)]:
        v = [x['net'] for x in rows if f(x['frac'])]
        print(f'  [desc] tamaño {lab}: n={len(v)} neto {np.mean(v) if v else float("nan"):+.2%}')
    crit = {'1_n>=50': n >= 50, '2_media>0_CI_agrupado_inf>0': net.mean() > 0 and lo > 0,
            '3_dos_mitades>0': h1 > 0 and h2 > 0, '4_>control_p95': net.mean() > p95,
            '5_>0_costo_pesimista': net.mean() - (PESS - COST) > 0, '6_mediana>0': float(np.median(net)) > 0}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> P55 {'PASA' if ok else 'NO PASA'}")
    json.dump(dict(criterio='docs/p55_desbloqueos_relativos_criterio.md (96174c7)', n=n, net=float(net.mean()),
                   median=float(np.median(net)), ci=[lo, hi], halves=[h1, h2], ctrl=[p50, p95], criterios=crit,
                   PASA=ok, rows=rows), open(OUT, 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
