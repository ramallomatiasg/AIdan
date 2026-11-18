"""
backtest_p49_unlocks.py — P49: corto del perpetuo de Binance de D-7 a D de un desbloqueo grande de tokens.

READ-ONLY. Sin MT5, no toca la DB. Calendario de tools/p49_unlocks_data.py (DefiLlama); velas diarias y funding
públicos de Binance a .cache_p49/px/.
Criterio declarado ANTES de medir: docs/p49_desbloqueos_criterio.md (ad8d14b). Leer contra eso.

    python tools/backtest_p49_unlocks.py              # descubrimiento 2022-2024
    python tools/backtest_p49_unlocks.py --reserved   # 2025-26, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import p49_unlocks_data as U  # noqa: E402

ROOT = U.ROOT
PX = os.path.join(U.C, 'px')
COST, PESS = 0.002, 0.004
REPS, BOOT, SEED = 2000, 5000, 20261117
SPLIT = dt.date(2025, 1, 1)
END_MS = int(dt.datetime(2026, 10, 31, tzinfo=dt.timezone.utc).timestamp() * 1000)
START_MS = int(dt.datetime(2021, 12, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
OUT = os.path.join(ROOT, 'docs', 'p49_desbloqueos_resultado.json')


def fetch(perp):
    os.makedirs(PX, exist_ok=True)
    p = os.path.join(PX, f'{perp}.json')
    if os.path.exists(p):
        return json.load(open(p))
    kl, t = [], START_MS
    while t < END_MS:
        k = U._get(f'https://fapi.binance.com/fapi/v1/klines?symbol={perp}&interval=1d&startTime={t}&limit=1500')
        if not k:
            break
        kl += [(int(x[0]) // 86400000, float(x[1])) for x in k]
        t = int(k[-1][0]) + 86400000
        time.sleep(0.2)
    fu, t = [], START_MS
    while t < END_MS:
        r = U._get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={perp}&startTime={t}&limit=1000')
        if not r:
            break
        fu += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
        if len(r) < 1000:
            break
        t = int(r[-1]['fundingTime']) + 1
        time.sleep(0.2)
    d = dict(k=kl, f=fu)
    json.dump(d, open(p, 'w'))
    return d


def eligible():
    ev = [e for e in U.events() if {'insiders', 'privateSale'} & set(e['cats'])]
    out, last = [], {}
    for e in ev:
        if e['sym'] in last and e['day'] - last[e['sym']] <= 7:
            continue
        last[e['sym']] = e['day']
        out.append(e)
    return out


def short_ret(o, ft, fr, a, b):
    """Corto del open del día a al open del día b (días epoch). None si falta una vela."""
    if a not in o or b not in o:
        return None
    i0, i1 = np.searchsorted(ft, a * 86400000, side='right'), np.searchsorted(ft, b * 86400000, side='right')
    fund = float(fr[i0:i1].sum())
    gross = -(o[b] / o[a] - 1)
    return gross, fund


def cluster_ci(net, wk, rng):
    uw = np.unique(wk)
    idx = [np.flatnonzero(wk == w) for w in uw]
    s = np.array([net[i].sum() for i in idx]); n = np.array([i.size for i in idx])
    bs = np.empty(BOOT)
    for r in range(BOOT):
        j = rng.integers(0, uw.size, uw.size)
        bs[r] = s[j].sum() / n[j].sum()
    bs.sort()
    return float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]), int(uw.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved and not json.load(open(OUT)).get('PASA'):
        sys.exit('El descubrimiento no pasó: la reserva no se mira.')
    ev = eligible()
    allday = {}
    for e in ev:
        allday.setdefault(e['sym'], []).append(e['day'])
    rng = np.random.default_rng(SEED)
    rows, ctrl_pool, dropped = [], {}, 0
    data = {}
    for sym in sorted(allday):
        perp = next(e['perp'] for e in ev if e['sym'] == sym)
        try:
            data[sym] = fetch(perp)
        except Exception as ex:
            print(f'  sin datos {perp}: {ex}')
    for e in ev:
        d = dt.date(1970, 1, 1) + dt.timedelta(e['day'])
        if (d >= SPLIT) != a.reserved or e['sym'] not in data:
            if e['sym'] not in data and (d >= SPLIT) == a.reserved:
                dropped += 1
            continue
        D = data[e['sym']]
        o = dict(D['k'])
        ft = np.array([x[0] for x in D['f']], dtype=np.int64); fr = np.array([x[1] for x in D['f']])
        r = short_ret(o, ft, fr, e['day'] - 7, e['day'])
        if r is None:
            dropped += 1
            continue
        key = (e['sym'], d.year)
        if key not in ctrl_pool:
            evd = np.array(allday[e['sym']])
            pool = []
            for s0 in o:
                y = (dt.date(1970, 1, 1) + dt.timedelta(s0)).year
                if y != d.year or np.any(np.abs(evd - (s0 + 7)) <= 14):
                    continue
                rr = short_ret(o, ft, fr, s0, s0 + 7)
                if rr is not None:
                    pool.append(rr[0] + rr[1] - COST)
            ctrl_pool[key] = np.array(pool)
        post = short_ret(o, ft, fr, e['day'], e['day'] + 7)
        rows.append(dict(e, gross=r[0], fund=r[1], net=r[0] + r[1] - COST,
                         post=None if post is None else post[0] + post[1] - COST))
    rows.sort(key=lambda x: x['day'])
    net = np.array([x['net'] for x in rows]); n = net.size
    wk = np.array([x['day'] // 7 for x in rows])
    lo, hi, nw = cluster_ci(net, wk, rng)
    h = n // 2
    h1, h2 = float(net[:h].mean()), float(net[h:].mean())
    pools = [ctrl_pool[(x['sym'], (dt.date(1970, 1, 1) + dt.timedelta(x['day'])).year)] for x in rows]
    ok_c = [p for p in pools if p.size]
    cm = np.sort(np.mean([p[rng.integers(0, p.size, REPS)] for p in ok_c], axis=0))
    p50, p95 = float(cm[REPS // 2]), float(cm[int(.95 * REPS)])
    tag = 'RESERVA 2025-26' if a.reserved else 'DESCUBRIMIENTO 2022-2024'
    print(f'{tag}: n={n} (descartados {dropped}, monedas {len({x["sym"] for x in rows})}, semanas {nw})')
    print(f'  bruto {np.mean([x["gross"] for x in rows]):+.2%}  funding {np.mean([x["fund"] for x in rows]):+.3%}  '
          f'NETO {net.mean():+.2%}  mediana {np.median(net):+.2%}  ganados {(net > 0).mean():.0%}')
    print(f'  CI95 agrupado por semana [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  '
          f'control p50 {p50:+.2%} p95 {p95:+.2%} (control sin pool: {len(pools) - len(ok_c)})')
    yrs = {}
    for x in rows:
        yrs.setdefault(x['date'][:4], []).append(x['net'])
    print('  [desc] por año: ' + '  '.join(f'{y} {np.mean(v):+.2%} (n={len(v)})' for y, v in sorted(yrs.items())))
    for lab, f in [('1-3%', lambda z: z < .03), ('3-10%', lambda z: .03 <= z < .1), ('>10%', lambda z: z >= .1)]:
        v = [x['net'] for x in rows if f(x['frac'])]
        print(f'  [desc] tamaño {lab}: n={len(v)} neto {np.mean(v) if v else float("nan"):+.2%}')
    pv = [x['post'] for x in rows if x['post'] is not None]
    print(f'  [desc] corto D→D+7: n={len(pv)} neto {np.mean(pv):+.2%}')
    if a.reserved:
        crit = {'media>0': net.mean() > 0, 'CI_agrupado_inf>0': lo > 0, '>control_p95': net.mean() > p95}
    else:
        crit = {'1_n>=150': n >= 150, '2_media>0_CI_agrupado_inf>0': net.mean() > 0 and lo > 0,
                '3_dos_mitades>0': h1 > 0 and h2 > 0, '4_>control_p95': net.mean() > p95,
                '5_>0_costo_pesimista': net.mean() - (PESS - COST) > 0, '6_mediana>0': float(np.median(net)) > 0}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> P49 {'reserva ' if a.reserved else ''}{'PASA' if ok else 'NO PASA'}")
    res = dict(criterio='docs/p49_desbloqueos_criterio.md (ad8d14b)', n=n, net=float(net.mean()),
               median=float(np.median(net)), ci=[lo, hi], halves=[h1, h2], ctrl=[p50, p95], criterios=crit, PASA=ok,
               monedas=sorted({x['sym'] for x in rows}))
    json.dump(res, open(OUT.replace('.json', '_reserva.json') if a.reserved else OUT, 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
