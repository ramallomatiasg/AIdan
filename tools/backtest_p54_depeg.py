"""
backtest_p54_depeg.py — P54: comprar la stablecoin cuando cierra < 0,995 contra USDT y venderla al volver a 0,999
o a los 7 días.

READ-ONLY. Sin MT5, no toca la DB. Velas 1 h públicas del spot de Binance a .cache_p54/.
Criterio declarado ANTES de medir: docs/p54_depeg_stablecoins_criterio.md (ef3ab63). Leer contra eso.

    python tools/backtest_p54_depeg.py              # descubrimiento hasta 2024
    python tools/backtest_p54_depeg.py --reserved   # 2025-26, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p54')
OUT = os.path.join(ROOT, 'docs', 'p54_depeg_resultado.json')
PAIRS = ['USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'PAXUSDT', 'USDPUSDT', 'FDUSDUSDT', 'DAIUSDT', 'USDEUSDT', 'USD1USDT',
         'USDSUSDT']
COST, PESS = 0.004, 0.008
IN, OUTP, MAXH = 0.995, 0.999, 168
REPS, BOOT, SEED = 2000, 5000, 20261118
H = 3600_000
SPLIT = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END = int(dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc).timestamp() * 1000)


def fetch(sym):
    os.makedirs(C, exist_ok=True)
    p = os.path.join(C, f'{sym}.json')
    if os.path.exists(p):
        return json.load(open(p))
    out, t = [], 1500000000000
    while t < END:
        u = f'https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&startTime={t}&limit=1000'
        k = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                              timeout=60).read())
        if not k:
            break
        out += [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in k]
        t = int(k[-1][0]) + H
        time.sleep(0.12)
    json.dump(out, open(p, 'w'))
    return out


def trades(k):
    k = [x for x in k if x[5] > 0]
    t = np.array([x[0] for x in k]); o = np.array([x[1] for x in k]); lo = np.array([x[3] for x in k])
    c = np.array([x[4] for x in k])
    res, i = [], 0
    while i < len(k) - 1:
        if c[i] < IN:
            j0 = i + 1
            j = j0
            while j < len(k) - 1 and c[j] < OUTP and (t[j] - t[j0]) // H < MAXH:
                j += 1
            jx = j + 1 if j < len(k) - 1 else j       # vende en el open siguiente; si no hay, la última vela
            px_out = o[jx] if jx > j else c[j]
            res.append(dict(t_in=int(t[j0]), t_out=int(t[jx]), p_in=float(o[j0]), p_out=float(px_out),
                            mae=float(lo[j0:jx + 1].min() / o[j0] - 1), hours=int((t[jx] - t[j0]) // H)))
            i = jx
        else:
            i += 1
    return res, t, o, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved and not json.load(open(OUT)).get('PASA'):
        sys.exit('El descubrimiento no pasó: la reserva no se mira.')
    rng = np.random.default_rng(SEED)
    rows, ctrl = [], []
    usdp0 = None
    for s in PAIRS:
        k = fetch(s)
        if s == 'USDPUSDT':
            usdp0 = k[0][0] if k else None
        if s == 'PAXUSDT':
            pass
        rows_s, t, o, c = trades(k)
        if s == 'PAXUSDT':
            usdp = fetch('USDPUSDT')
            cut = usdp[0][0] if usdp else END
            rows_s = [r for r in rows_s if r['t_in'] < cut]
        normal = np.flatnonzero((np.abs(c - 1) <= 0.001)[:-1])
        for r in rows_s:
            if (r['t_in'] >= SPLIT) != a.reserved or r['t_in'] >= END:
                continue
            r['pair'] = s
            r['net'] = r['p_out'] / r['p_in'] - 1 - COST
            L = max(r['hours'], 1)
            ok = normal[normal + 1 + L < len(t)]
            pool = []
            for i in rng.choice(ok, min(ok.size, 400), replace=False):
                pool.append(o[i + 1 + L] / o[i + 1] - 1 - COST)
            ctrl.append(np.array(pool))
            rows.append(r)
    rows.sort(key=lambda r: r['t_in'])
    ep, last = {}, {}
    for r in rows:
        if r['pair'] not in last or r['t_in'] - last[r['pair']][1] > 30 * 86400_000:
            last[r['pair']] = (len(ep), r['t_in'])
            ep[len(ep)] = 1
        else:
            last[r['pair']] = (last[r['pair']][0], r['t_in'])
        r['ep'] = last[r['pair']][0]
    tag = 'RESERVA 2025-26' if a.reserved else 'DESCUBRIMIENTO hasta 2024'
    n = len(rows)
    if n == 0:
        print(f'{tag}: n=0 (ninguna señal)')
        crit = {'1_n>=8_y_4_episodios': False}
        json.dump(dict(n=0, criterios=crit, PASA=False), open(OUT, 'w'))
        print('>>> P54 NO PASA')
        return
    net = np.array([r['net'] for r in rows]); g = np.array([r['ep'] for r in rows])
    ug = np.unique(g)
    idx = [np.flatnonzero(g == e) for e in ug]
    sm = np.array([net[i].sum() for i in idx]); nn = np.array([i.size for i in idx])
    bs = np.sort([sm[j].sum() / nn[j].sum() for j in (rng.integers(0, ug.size, ug.size) for _ in range(BOOT))])
    lo, hi = float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])
    okc = [p for p in ctrl if p.size]
    cm = np.sort(np.mean([p[rng.integers(0, p.size, REPS)] for p in okc], axis=0))
    p95 = float(cm[int(.95 * REPS)])
    print(f'{tag}: n={n} operaciones, {ug.size} episodios')
    print(f'  NETO {net.mean():+.3%}  mediana {np.median(net):+.3%}  ganadas {(net > 0).mean():.0%}  '
          f'peor {net.min():+.2%}  CI95 agrupado [{lo:+.3%}, {hi:+.3%}]  control p95 {p95:+.3%}')
    for e in ug:
        rr = [r for r in rows if r['ep'] == e]
        d0 = dt.datetime.utcfromtimestamp(rr[0]['t_in'] / 1000).strftime('%Y-%m-%d')
        print(f'  [desc] ep {e:2d} {rr[0]["pair"]:9s} {d0} n={len(rr):2d} neto medio {np.mean([r["net"] for r in rr]):+.3%} '
              f'peor intra {min(r["mae"] for r in rr):+.2%} horas med {np.median([r["hours"] for r in rr]):.0f}')
    yrs = (min(SPLIT, END) - 1525000000000) / (365.25 * 86400_000) if not a.reserved else (END - SPLIT) / (365.25 * 86400_000)
    print(f'  [desc] ganancia total por cada $1.000 puestos en cada operación: ${net.sum() * 1000:+.1f} en ~{yrs:.1f} años')
    if a.reserved:
        crit = {'media>0': net.mean() > 0, 'peor>-3%': net.min() > -0.03}
    else:
        crit = {'1_n>=8_y_4_episodios': n >= 8 and ug.size >= 4, '2_media>0_CI_agrupado_inf>0': net.mean() > 0 and lo > 0,
                '3_ganadas>=75%': (net > 0).mean() >= .75, '4_>control_p95': net.mean() > p95,
                '5_>0_costo_pesimista': net.mean() - (PESS - COST) > 0, '6_peor>-3%': net.min() > -0.03}
    for kk, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {kk}")
    ok = all(crit.values())
    print(f">>> P54 {'reserva ' if a.reserved else ''}{'PASA' if ok else 'NO PASA'}")
    json.dump(dict(criterio='docs/p54_depeg_stablecoins_criterio.md (ef3ab63)', n=n, episodios=int(ug.size),
                   net=float(net.mean()), ci=[lo, hi], ctrl_p95=p95, worst=float(net.min()), criterios=crit, PASA=ok,
                   rows=rows), open(OUT.replace('.json', '_reserva.json') if a.reserved else OUT, 'w'), indent=1,
              default=float)


if __name__ == '__main__':
    main()
