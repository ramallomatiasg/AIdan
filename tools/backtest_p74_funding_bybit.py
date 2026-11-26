"""
backtest_p74_funding_bybit.py — P74: el carry de funding de P15 con datos de Bybit, reglas congeladas (BTC/ETH/SOL).

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja datos PÚBLICOS de Bybit (API v5, sin cuenta) a `.cache_p74/`.
Criterio declarado ANTES de medir: docs/p74_funding_bybit_criterio.md (cc3bd83). El simulador se IMPORTA de P15.

    python tools/backtest_p74_funding_bybit.py
"""
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
CACHE = os.path.join(ROOT, '.cache_p74')
SYMS = ['BTC', 'ETH', 'SOL']
END_MS = int(dt.datetime(2026, 11, 24, tzinfo=dt.timezone.utc).timestamp() * 1000)
FLOOR_MS = int(dt.datetime(2018, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
SEED = 20261125
OUT = os.path.join(ROOT, 'docs', 'p74_funding_bybit_resultado.json')
API = 'https://api.bybit.com/v5/market'


def _get(url):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                j = json.load(r)
            if j.get('retCode') != 0:
                raise RuntimeError(j)
            return j['result']['list']
        except Exception:
            if k == 4:
                raise
            time.sleep(2 + 3 * k)


def fetch_funding(sym):
    out, end = {}, END_MS - 1
    while end > FLOOR_MS:
        r = _get(f'{API}/funding/history?category=linear&symbol={sym}USDT&endTime={end}&limit=200')
        if not r:
            break
        for x in r:
            out[int(x['fundingRateTimestamp'])] = float(x['fundingRate'])
        oldest = min(int(x['fundingRateTimestamp']) for x in r)
        if oldest - 1 >= end:
            break
        end = oldest - 1
    return sorted(out.items())


def fetch_8h_open(sym, cat):
    """open de las velas de 4 h que arrancan a las 00/08/16 UTC = open de la vela de 8 h."""
    out, end = {}, END_MS - 1
    while end > FLOOR_MS:
        r = _get(f'{API}/kline?category={cat}&symbol={sym}USDT&interval=240&end={end}&limit=1000')
        if not r:
            break
        for x in r:
            t = int(x[0])
            if t % p15.P8H == 0 and t < END_MS:
                out[t] = float(x[1])
        oldest = min(int(x[0]) for x in r)
        if oldest - 1 >= end:
            break
        end = oldest - 1
    return sorted(out.items())


def load(sym):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{sym}.json')
    if os.path.exists(p):
        return json.load(open(p))
    d = dict(funding=fetch_funding(sym), spot=fetch_8h_open(sym, 'spot'), perp=fetch_8h_open(sym, 'linear'))
    json.dump(d, open(p, 'w'))
    return d


def trim(d, t0):
    return {k: [x for x in v if x[0] >= t0] for k, v in d.items()}


def run_port(datas, grid):
    rs, rs_all, per = [], [], {}
    for s, d in datas.items():
        r, comp, tot = p15.simulate(d, grid)
        ra, _, tot_a = p15.simulate(d, grid, always_in=True)
        rs.append(r); rs_all.append(ra)
        per[s] = dict(total=tot, annual=float(r.mean() * p15.PER_YEAR), comp=comp, always_in=tot_a)
    return np.mean(rs, axis=0), np.mean(rs_all, axis=0), per


def main():
    data = {s: load(s) for s in SYMS}
    starts = {}
    for s, d in data.items():
        t0 = max(d['funding'][0][0], d['spot'][0][0], d['perp'][0][0])
        starts[s] = t0
        data[s] = trim(d, t0)
        f = lambda t: dt.datetime.utcfromtimestamp(t / 1000).strftime('%Y-%m-%d')
        print(f"  {s}: funding desde {f(d['funding'][0][0])} spot {f(d['spot'][0][0])} perp {f(d['perp'][0][0])} "
              f"-> usa desde {f(t0)}  ({len(d['funding'])} cobros)")
    t0 = min(starts.values())
    grid = np.arange(t0 - t0 % p15.P8H, END_MS, p15.P8H, dtype=np.int64).tolist()
    port, port_all, per = run_port(data, grid)
    for s, v in per.items():
        c = v['comp']
        print(f"  {s:4s} neto {v['total']:+.2%} del capital ({v['annual']:+.2%}/año)  funding {c['funding']:+.3f} "
              f"base {c['base']:+.3f} costo {c['cost']:.3f}  entradas {c['trades']} rebal {c['rebal']}  "
              f"| siempre adentro {v['always_in']:+.2%}")
    eq = np.cumprod(1 + port); dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    ann = float(port.mean() * p15.PER_YEAR)
    bs = p15.block_boot(port, np.random.default_rng(SEED)) * p15.PER_YEAR
    lo, hi = float(bs[int(.025 * p15.BOOT)]), float(bs[int(.975 * p15.BOOT)])
    h = port.size // 2
    h1, h2 = float(port[:h].mean() * p15.PER_YEAR), float(port[h:].mean() * p15.PER_YEAR)
    hr = p15.hurdle(grid[0], grid[-1])
    pos = sum(1 for v in per.values() if v['total'] > 0)
    years = {}
    for k in range(port.size):
        years.setdefault(dt.datetime.utcfromtimestamp(grid[k] / 1000).year, []).append(port[k])
    print(f"\n  CARTERA Bybit: {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx {dd:.2%}  monedas>0 {pos}/3  tasa libre media {hr:.2%}")
    print('  por año: ' + '  '.join(f'{y} {np.mean(v) * p15.PER_YEAR:+.1%}' for y, v in sorted(years.items())))
    print(f"  siempre adentro (desc.): {port_all.mean() * p15.PER_YEAR:+.2%}/año")
    # descriptivo: misma ventana con Binance (cache de P15)
    bin_ = {s: trim(json.load(open(os.path.join(p15.CACHE, f'{s}.json'))), t0) for s in SYMS}
    gb = [t for t in grid if t < p15.END_MS]
    pb, _, perb = run_port(bin_, gb)
    n = min(pb.size, port.size)
    dB = np.add.reduceat(port[:n], np.arange(0, n, 3)); dN = np.add.reduceat(pb[:n], np.arange(0, n, 3))
    print(f"  Binance misma ventana (hasta {dt.datetime.utcfromtimestamp(p15.END_MS / 1000):%Y-%m-%d}): "
          f"{pb.mean() * p15.PER_YEAR:+.2%}/año  " + '  '.join(f"{s} {v['annual']:+.2%}" for s, v in perb.items())
          + f"  | corr diaria Bybit-Binance {np.corrcoef(dB, dN)[0, 1]:+.2f}")
    crit = {'1_anual>tasa_libre_media': ann > hr, '2_CI_inf>0': lo > 0, '3_dos_mitades>0': h1 > 0 and h2 > 0,
            '4_caida_max<10%': dd < 0.10, '5_>=2/3_monedas>0': pos >= 2}
    ok = all(crit.values())
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f"  >>> P74: {'PASA' if ok else 'NO PASA'}")
    json.dump(dict(por_moneda=per, annual=ann, ci=[lo, hi], halves=[h1, h2], max_dd=dd, hurdle=hr, pos=pos,
                   por_anio={y: float(np.mean(v) * p15.PER_YEAR) for y, v in years.items()},
                   binance_misma_ventana=float(pb.mean() * p15.PER_YEAR), criterios=crit, PASA=ok,
                   criterio='docs/p74_funding_bybit_criterio.md (cc3bd83)'),
              open(OUT, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
