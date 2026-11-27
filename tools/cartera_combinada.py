"""
cartera_combinada.py — mide la cartera de peso igual de lo que pasó (docs/cartera_de_lo_que_pasa.md). DESCRIPTIVO.

READ-ONLY: sin MT5, no toca la DB, sin red (usa los caches de P15, P21, P74, P76, P57 y P80). Período común: desde que
existen todos los libros (Hyperliquid, may-2023) hasta el 22-oct-2026. Retornos mensuales sobre el capital de cada libro.

    python tools/cartera_combinada.py
"""
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p15_funding as p15  # noqa: E402

ROOT = p15.ROOT
START = int(dt.datetime(2023, 6, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END = p15.END_MS
P8H = p15.P8H
OUT = os.path.join(ROOT, 'docs', 'cartera_combinada_resultado.json')
COST_P15 = p15.RT_COST
COST_HL = 2 * (0.0010 + 0.00045) + 4 * 0.0002


def month(t):
    return dt.datetime.utcfromtimestamp(t / 1000).strftime('%Y-%m')


def book(datas, cost):
    grid = np.arange(START, END, P8H, dtype=np.int64).tolist()
    p15.RT_COST = cost
    rs = [p15.simulate({k: [x for x in v if x[0] >= START - 8 * 86400 * 1000] for k, v in d.items()}, grid)[0]
          for d in datas]
    p15.RT_COST = COST_P15
    r = np.mean(rs, axis=0)
    out = {}
    for k in range(r.size):
        out.setdefault(month(grid[k + 1]), []).append(r[k])
    return {m: float(np.prod(1 + np.array(v)) - 1) for m, v in out.items()}


def load(cache, s):
    return json.load(open(os.path.join(ROOT, cache, f'{s}.json')))


def hlp():
    port = dict(json.load(open(os.path.join(ROOT, '.cache_p57', 'hlp_vaultDetails.json')))['portfolio'])['allTime']
    av = [(t, float(v)) for t, v in port['accountValueHistory']]
    pnl = [float(v) for _, v in port['pnlHistory']]
    out = {}
    for i in range(len(av) - 1):
        if av[i][1] <= 0 or (av[i + 1][0] - av[i][0]) < 864e5 or not START <= av[i][0] < END:
            continue
        out.setdefault(month(av[i][0]), []).append((pnl[i + 1] - pnl[i]) / av[i][1])
    return {m: float(np.prod(1 + np.array(v)) - 1) for m, v in out.items()}


def bitfinex():
    import backtest_p80_prestamo_bitfinex as p80
    lo = dt.datetime.utcfromtimestamp(START / 1000).date()
    hi = dt.datetime.utcfromtimestamp(END / 1000).date() - dt.timedelta(days=1)
    ser = p80.series(p80.load_rates(p80.C), lo, hi, 1.0, 0.15, True, lambda d: 0.0)
    out = {}
    for d, _, pr in ser:                       # pr = log del patrimonio neto del 1%/año de entrada/salida
        out.setdefault(d.strftime('%Y-%m'), []).append(pr)
    return {m: float(np.exp(np.sum(v)) - 1) for m, v in out.items()}


def main():
    s3 = ['BTC', 'ETH', 'SOL']
    books = {
        'P15 Binance': book([load('.cache_p15', s) for s in s3], COST_P15),
        'P74 Bybit': book([load('.cache_p74', s) for s in s3], COST_P15),
        'P76 Deribit': book([load('.cache_p76', s) for s in ['BTC', 'ETH']], COST_P15),
        'P21-A Hyperliquid': book([dict(spot=load('.cache_p15', s)['spot'], perp=load('.cache_p21', s)['perp'],
                                        funding=load('.cache_p21', s)['funding']) for s in s3], COST_HL),
        'P57 vault HLP': hlp(),
        'P80 préstamo Bitfinex': bitfinex(),
    }
    months = sorted(set.intersection(*[set(b) for b in books.values()]))
    M = np.array([[books[k][m] for m in months] for k in books])
    names = list(books)
    rates = {r.split(',')[0]: float(r.split(',')[1]) for r in open(os.path.join(ROOT, 'docs', 'p11_policy_rates.csv'))
             .read().splitlines()[1:]}
    letra = float(np.mean([rates[m] for m in months if m in rates])) / 100
    print(f'  período común {months[0]} → {months[-1]} ({len(months)} meses)  letra media {letra:.2%}')

    def stat(x):
        eq = np.cumprod(1 + x)
        return dict(anual=float((eq[-1]) ** (12 / x.size) - 1), vol=float(x.std() * np.sqrt(12)),
                    caida_max=float(np.max(1 - eq / np.maximum.accumulate(eq))), peor_mes=float(x.min()),
                    meses_neg=int((x < 0).sum()))
    res = {}
    for k, x in zip(names, M):
        res[k] = stat(x)
    port = M.mean(axis=0)
    carry = M[:4].mean(axis=0)
    res['CARTERA peso igual (6)'] = stat(port)
    res['solo carry (4 exchanges)'] = stat(carry)
    for k, v in res.items():
        print(f"  {k:26s} {v['anual']:+6.2%}/año  vol {v['vol']:5.2%}  caída máx {v['caida_max']:5.2%}  "
              f"peor mes {v['peor_mes']:+6.2%} (con $1.000: {v['peor_mes'] * 1000:+.0f} USD)  meses<0 {v['meses_neg']}")
    C = np.corrcoef(M)
    print('  correlación mensual:')
    for i, k in enumerate(names):
        print(f"    {k:18s} " + ' '.join(f'{C[i, j]:+.2f}' for j in range(len(names))))
    vol_sum = float(np.mean([res[k]['vol'] for k in names]))
    print(f"  vol promedio de los libros {vol_sum:.2%} vs vol de la cartera {res['CARTERA peso igual (6)']['vol']:.2%}"
          f"  | por año: " + '  '.join(f"{y} {np.prod(1 + port[[m.startswith(y) for m in months]]) - 1:+.1%}"
                                         for y in sorted({m[:4] for m in months})))
    json.dump(dict(periodo=[months[0], months[-1]], letra=letra, libros=res, correlacion=C.tolist(), nombres=names,
                   mensual={k: dict(zip(months, map(float, x))) for k, x in zip(names, M)}),
              open(OUT, 'w'), indent=1)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
