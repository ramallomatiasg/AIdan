"""
backtest_p76_funding_deribit.py — P76: el carry de funding de P15 con el funding de Deribit, reglas congeladas (BTC/ETH).

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja datos PÚBLICOS de Deribit (sin cuenta) a `.cache_p76/`;
la pata spot es la de P15 (`.cache_p15/`). Criterio declarado ANTES de medir: docs/p76_funding_deribit_criterio.md
(713f3d8). El simulador se IMPORTA de P15.

    python tools/backtest_p76_funding_deribit.py
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
CACHE = os.path.join(ROOT, '.cache_p76')
SYMS = ['BTC', 'ETH']
END_MS = p15.END_MS
FLOOR_MS = int(dt.datetime(2019, 4, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
SEED = 20261126
OUT = os.path.join(ROOT, 'docs', 'p76_funding_deribit_resultado.json')
API = 'https://www.deribit.com/api/v2/public'
STEP = 30 * 86400 * 1000


def _get(url):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                return json.load(r)['result']
        except Exception:
            if k == 4:
                raise
            time.sleep(2 + 3 * k)


def fetch_funding(sym):
    out, t = {}, FLOOR_MS
    while t < END_MS:
        r = _get(f'{API}/get_funding_rate_history?instrument_name={sym}-PERPETUAL&start_timestamp={t}'
                 f'&end_timestamp={min(t + STEP, END_MS)}')
        for x in r:
            if x.get('interest_1h') is not None and x['timestamp'] < END_MS:
                out[int(x['timestamp'])] = float(x['interest_1h'])
        t += STEP
    return sorted(out.items())


def fetch_perp(sym):
    out, t = {}, FLOOR_MS
    while t < END_MS:
        r = _get(f'{API}/get_tradingview_chart_data?instrument_name={sym}-PERPETUAL&start_timestamp={t}'
                 f'&end_timestamp={min(t + STEP, END_MS)}&resolution=60')
        if r.get('status') == 'ok':
            for tk, o in zip(r['ticks'], r['open']):
                if tk % p15.P8H == 0 and tk < END_MS:
                    out[int(tk)] = float(o)
        t += STEP
    return sorted(out.items())


def load(sym):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{sym}.json')
    if os.path.exists(p):
        return json.load(open(p))
    spot = json.load(open(os.path.join(p15.CACHE, f'{sym}.json')))['spot']
    d = dict(funding=fetch_funding(sym), spot=[x for x in spot if x[0] >= FLOOR_MS], perp=fetch_perp(sym))
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
    print(f"\n  CARTERA Deribit: {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx {dd:.2%}  monedas>0 {pos}/2  tasa libre media {hr:.2%}")
    print('  por año: ' + '  '.join(f'{y} {np.mean(v) * p15.PER_YEAR:+.1%}' for y, v in sorted(years.items())))
    print(f"  siempre adentro (desc.): {port_all.mean() * p15.PER_YEAR:+.2%}/año")
    # descriptivo: misma ventana con el funding de Binance (cache de P15)
    bin_ = {s: trim(json.load(open(os.path.join(p15.CACHE, f'{s}.json'))), t0) for s in SYMS}
    pb, _, perb = run_port(bin_, grid)
    n = min(pb.size, port.size)
    dB = np.add.reduceat(port[:n], np.arange(0, n, 3)); dN = np.add.reduceat(pb[:n], np.arange(0, n, 3))
    print(f"  Binance misma ventana: {pb.mean() * p15.PER_YEAR:+.2%}/año  "
          + '  '.join(f"{s} {v['annual']:+.2%}" for s, v in perb.items())
          + f"  | corr diaria Deribit-Binance {np.corrcoef(dB, dN)[0, 1]:+.2f}")
    crit = {'1_anual>tasa_libre_media': ann > hr, '2_CI_inf>0': lo > 0, '3_dos_mitades>0': h1 > 0 and h2 > 0,
            '4_caida_max<10%': dd < 0.10, '5_2/2_monedas>0': pos >= 2}
    ok = all(crit.values())
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f"  >>> P76: {'PASA' if ok else 'NO PASA'}")
    json.dump(dict(por_moneda=per, annual=ann, ci=[lo, hi], halves=[h1, h2], max_dd=dd, hurdle=hr, pos=pos,
                   por_anio={y: float(np.mean(v) * p15.PER_YEAR) for y, v in years.items()},
                   binance_misma_ventana=float(pb.mean() * p15.PER_YEAR), criterios=crit, PASA=ok,
                   criterio='docs/p76_funding_deribit_criterio.md (713f3d8)'),
              open(OUT, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
