"""P21 — carry de funding (P15) en Hyperliquid y diferencial Binance-Hyperliquid.

Criterio declarado antes de medir: docs/p21_hyperliquid_criterio.md (edc1715).
Read-only: sin MT5, no toca la DB. Datos públicos de Hyperliquid a .cache_p21/; Binance desde .cache_p15/.
Reusa el motor `simulate` de P15 (importado, no copiado) cambiando solo el costo de ida y vuelta.

  python tools/backtest_p21_hyperliquid.py              # 6 principales, variantes A y B
  python tools/backtest_p21_hyperliquid.py --reserved   # solo si alguna pasó
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
CACHE = os.path.join(ROOT, '.cache_p21')
START_MS = int(dt.datetime(2023, 5, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)
END_MS = p15.END_MS
P8H = 8 * 3600 * 1000
COST_A = 2 * (0.0010 + 0.00045) + 4 * 0.0002     # 0,37%
COST_B = 2 * (0.0005 + 0.00045) + 4 * 0.0002     # 0,27%
COST_P15 = p15.RT_COST
OUT = os.path.join(ROOT, 'docs', 'p21_hyperliquid_resultado.json')


def _post(body):
    for k in range(5):
        try:
            req = urllib.request.Request('https://api.hyperliquid.xyz/info', data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if k == 4:
                raise
            time.sleep(2 + 3 * k)


def load_hl(sym):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{sym}.json')
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    fund, start = [], 0
    while True:
        r = _post({'type': 'fundingHistory', 'coin': sym, 'startTime': start})
        r = [x for x in r if int(x['time']) < END_MS]
        if not r:
            break
        fund += [(int(x['time']), float(x['fundingRate'])) for x in r]
        nxt = int(r[-1]['time']) + 1
        if nxt <= start or len(r) < 500:
            break
        start = nxt
        time.sleep(0.25)
    c = _post({'type': 'candleSnapshot', 'req': {'coin': sym, 'interval': '8h', 'startTime': 0, 'endTime': END_MS}})
    perp = [(int(x['t']), float(x['o'])) for x in c if int(x['t']) < END_MS]
    d = dict(funding=fund, perp=perp)
    with open(p, 'w') as f:
        json.dump(d, f)
    return d


def stats(rs, syms, grid, label, reserved):
    port = np.mean(rs, axis=0)
    eq = np.cumprod(1 + port)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    ann = float(port.mean() * p15.PER_YEAR)
    bs = p15.block_boot(port, np.random.default_rng(p15.SEED)) * p15.PER_YEAR
    lo, hi = float(bs[int(0.025 * p15.BOOT)]), float(bs[int(0.975 * p15.BOOT)])
    half = port.size // 2
    h1, h2 = float(port[:half].mean() * p15.PER_YEAR), float(port[half:].mean() * p15.PER_YEAR)
    hr = p15.hurdle(grid[0], grid[-1])
    pos = sum(1 for r in rs if r.sum() > 0)
    years = {}
    for k in range(port.size):
        years.setdefault(dt.datetime.utcfromtimestamp(grid[k] / 1000).year, []).append(port[k])
    print(f"  {label}: {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx {dd:.2%}  monedas>0 {pos}/{len(syms)}  tasa libre {hr:.2%}")
    print('    por año: ' + '  '.join(f'{y} {np.mean(v) * p15.PER_YEAR:+.1%}' for y, v in sorted(years.items())))
    if reserved:
        crit = {'oos_anual>0': ann > 0, 'oos_anual>tasa_libre': ann > hr}
    else:
        crit = {'1_anual>tasa_libre_media': ann > hr, '2_CI_inf>0': lo > 0, '3_dos_mitades>0': h1 > 0 and h2 > 0,
                '4_caida_max<10%': dd < 0.10, '5_>=4/6_monedas>0': pos >= 4}
    return dict(annual=ann, ci=[lo, hi], halves=[h1, h2], max_dd=dd, hurdle=hr, pos=pos,
                por_anio={y: float(np.mean(v) * p15.PER_YEAR) for y, v in years.items()},
                criterios=crit, PASA=all(crit.values()))


def sim(d, grid, cost, always_in=False):
    p15.RT_COST = cost
    p15.END_MS = END_MS
    return p15.simulate(d, grid, always_in=always_in)


def run(syms, reserved):
    grid = np.arange(START_MS - START_MS % P8H, END_MS, P8H, dtype=np.int64).tolist()
    rA, rB, rP, rAall = [], [], [], []
    per = {}
    for s in syms:
        bn = p15.load(s)
        hl = load_hl(s)
        dA = dict(spot=bn['spot'], perp=hl['perp'], funding=hl['funding'])
        ev = sorted([(t, r) for t, r in hl['funding']] + [(t, -r) for t, r in bn['funding'] if t >= START_MS])
        dB = dict(spot=bn['perp'], perp=hl['perp'], funding=ev)
        a, ca, ta = sim(dA, grid, COST_A)
        aa, _, taa = sim(dA, grid, COST_A, always_in=True)
        b, cb, tb = sim(dB, grid, COST_B)
        pz, cp, tp = sim(bn, grid, COST_P15)
        rA.append(a); rAall.append(aa); rB.append(b); rP.append(pz)
        first = dt.datetime.utcfromtimestamp(hl['funding'][0][0] / 1000).strftime('%Y-%m-%d') if hl['funding'] else '-'
        per[s] = dict(first_hl=first, A=ta, A_always=taa, B=tb, P15_mismo_periodo=tp, compA=ca, compB=cb)
        print(f"  {s:5s} HL desde {first}  A {ta:+.2%} (siempre {taa:+.2%}, fund {ca['funding']:+.3f} base "
              f"{ca['base']:+.3f} costo {ca['cost']:.3f}, entradas {ca['trades']})  B {tb:+.2%} (entradas "
              f"{cb['trades']})  | P15-Binance mismo período {tp:+.2%}")
    print()
    sA = stats(rA, syms, grid, 'A carry en Hyperliquid', reserved)
    sB = stats(rB, syms, grid, 'B diferencial BN-HL   ', reserved)
    print('  descriptivo:')
    sP = stats(rP, syms, grid, 'P15 Binance (mismo período)', True)
    sAall = stats(rAall, syms, grid, 'A siempre adentro', True)
    for name, st in (('A', sA), ('B', sB)):
        for k, v in st['criterios'].items():
            print(f"    {name} [{'OK ' if v else 'NO '}] {k}")
        print(f"  >>> {name}: {'PASA' if st['PASA'] else 'NO PASA'}")
    return dict(por_moneda=per, A=sA, B=sB, P15_mismo_periodo=sP, A_siempre=sAall,
                PASA=sA['PASA'] or sB['PASA'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('Ninguna variante pasó (o no se corrió): los reservados no se miran.')
        res, path = run(p15.RESERVED, True), OUT.replace('.json', '_reservados.json')
    else:
        res, path = run(p15.MAIN, False), OUT
    res['criterio'] = 'docs/p21_hyperliquid_criterio.md (edc1715)'
    with open(path, 'w') as f:
        json.dump(res, f, indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
