"""P48 — carry de funding de P15 en ETH con la pata larga en stETH (funding + staking de Lido).

Criterio declarado antes de medir: docs/p48_steth_carry_criterio.md (6cfb36d).
RESULTADO 16-nov: medición INVÁLIDA por datos — el cociente diario stETH/ETH de DefiLlama tiene ruido de
±10% (dos precios con horarios distintos; p1-p99 0,93-1,08, imposible). Ver el registro.
Read-only: sin MT5, no toca la DB. Datos públicos (DefiLlama) a .cache_p48/; Binance ETH desde .cache_p15/.

  python tools/backtest_p48_steth_carry.py              # descubrimiento (may-2022 → 2024)
  python tools/backtest_p48_steth_carry.py --reserved   # 2025-26, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p15_funding as p15  # noqa: E402

ROOT = p15.ROOT
CACHE = os.path.join(ROOT, '.cache_p48')
P8H = p15.P8H
START = dt.datetime(2022, 5, 10, tzinfo=dt.timezone.utc)
SPLIT_MS = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END_MS = p15.END_MS
COST_P15 = p15.RT_COST
COST_ST = p15.RT_COST + 2 * 0.0005                   # 0,48%
STETH = 'ethereum:0xae7ab96520de3a18e5e111b5eaab095312d7fe84'
OUT = os.path.join(ROOT, 'docs', 'p48_steth_carry_resultado.json')


def _get(u):
    for k in range(5):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                                    timeout=60))
        except Exception:
            if k == 4:
                raise
            time.sleep(3 + 3 * k)


def load():
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, 'data.json')
    if os.path.exists(p):
        return json.load(open(p))
    apy = {x['timestamp'][:10]: float(x['apyBase'] if x['apyBase'] is not None else x['apy'])
           for x in _get('https://yields.llama.fi/chart/747c1d2a-c668-4682-b9f9-296708a3dd90')['data']}
    px = {STETH: {}, 'coingecko:ethereum': {}}
    t = int(dt.datetime(2022, 5, 1, tzinfo=dt.timezone.utc).timestamp())
    while t < END_MS / 1000:
        for coin in px:
            c = _get(f'https://coins.llama.fi/chart/{coin}?start={t}&span=300&period=1d')
            for k, v in c['coins'].items():
                for q in v['prices']:
                    px[k][dt.datetime.utcfromtimestamp(q['timestamp']).strftime('%Y-%m-%d')] = q['price']
        t += 300 * 86400
        time.sleep(0.5)
    d = dict(apy=apy, steth=px[STETH], eth=px['coingecko:ethereum'])
    json.dump(d, open(p, 'w'))
    return d


def stats(r, t0, t1, label):
    eq = np.cumprod(1 + r)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    ann = float(r.mean() * p15.PER_YEAR)
    bs = p15.block_boot(r, np.random.default_rng(p15.SEED)) * p15.PER_YEAR
    lo, hi = float(bs[int(.025 * p15.BOOT)]), float(bs[int(.975 * p15.BOOT)])
    h = r.size // 2
    h1, h2 = float(r[:h].mean() * p15.PER_YEAR), float(r[h:].mean() * p15.PER_YEAR)
    hr = p15.hurdle(t0, t1)
    print(f"  {label}: {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx {dd:.2%}  tasa libre {hr:.2%}")
    return dict(annual=ann, ci=[lo, hi], halves=[h1, h2], max_dd=dd, hurdle=hr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    eth = p15.load('ETH')
    d = load()
    days = sorted(set(d['apy']) & set(d['steth']) & set(d['eth']))
    ratio = {k: d['steth'][k] / d['eth'][k] for k in days}
    growth, g = {}, 1.0
    for k in days:
        g *= 1 + d['apy'][k] / 100 / 365
        growth[k] = g
    rmin = min(ratio.items(), key=lambda kv: kv[1])
    t0 = int(START.timestamp() * 1000)
    syn, last = [], None
    for t, s in eth['spot']:
        k = dt.datetime.utcfromtimestamp(t / 1000).strftime('%Y-%m-%d')
        if k in ratio:
            last = k
        if t >= t0 - 8 * 86400 * 1000 and last is not None:
            syn.append((t, s * ratio[last] * growth[last]))
    grid = np.arange(t0 - t0 % P8H, END_MS, P8H, dtype=np.int64).tolist()
    p15.END_MS = END_MS
    dst = dict(spot=syn, perp=eth['perp'], funding=eth['funding'])
    p15.RT_COST = COST_ST
    rs, cs, _ = p15.simulate(dst, grid)
    rsa, _, _ = p15.simulate(dst, grid, always_in=True)
    p15.RT_COST = COST_P15
    re_, ce, _ = p15.simulate(eth, grid)
    g = np.array(grid[:-1])
    m = (g >= SPLIT_MS) if a.reserved else (g < SPLIT_MS)
    tt = g[m]
    print(f"  {'RESERVA 2025-26' if a.reserved else 'DESCUBRIMIENTO may-2022 → 2024'}  (stETH/ETH mínimo "
          f"{rmin[1]:.4f} el {rmin[0]}; APR Lido medio {np.mean([d['apy'][k] for k in days]):.2f}%)")
    print(f"  componentes período completo (x nocional): stETH fund {cs['funding']:+.3f} base {cs['base']:+.3f} "
          f"costo {cs['cost']:.3f} entradas {cs['trades']} | ETH fund {ce['funding']:+.3f} base {ce['base']:+.3f}")
    s = stats(rs[m], tt[0], tt[-1], 'stETH (decide)')
    print('  descriptivo:')
    e = stats(re_[m], tt[0], tt[-1], 'P15 ETH sin staking')
    sa = stats(rsa[m], tt[0], tt[-1], 'stETH siempre adentro')
    years = {}
    for k in np.flatnonzero(m):                      # solo el tramo elegido (no mirar la reserva)
        years.setdefault(dt.datetime.utcfromtimestamp(g[k] / 1000).year, []).append((rs[k], re_[k]))
    print('    por año (stETH / ETH): ' + '  '.join(
        f"{y} {np.mean([x[0] for x in v]) * p15.PER_YEAR:+.1%}/{np.mean([x[1] for x in v]) * p15.PER_YEAR:+.1%}"
        for y, v in sorted(years.items())))
    if a.reserved:
        crit = {'reserva_anual>tasa_libre': s['annual'] > s['hurdle']}
    else:
        crit = {'1_anual>tasa_libre_media': s['annual'] > s['hurdle'], '2_CI_inf>0': s['ci'][0] > 0,
                '3_dos_mitades>0': min(s['halves']) > 0, '4_caida_max<10%': s['max_dd'] < 0.10}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f"  >>> P48 {'reserva' if a.reserved else ''}: {'PASA' if ok else 'NO PASA'}")
    res = dict(decide=s, eth_sin_staking=e, siempre=sa, ratio_min=rmin, criterios=crit, PASA=ok,
               criterio='docs/p48_steth_carry_criterio.md (6cfb36d)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
