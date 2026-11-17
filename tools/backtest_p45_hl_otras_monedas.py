"""P45 — carry de funding de Hyperliquid (P21-A) en 15 monedas nuevas, reglas congeladas.

Criterio declarado antes de medir: docs/p45_hl_otras_monedas_criterio.md (863e142) + enmienda 1 (c475b3f).
Read-only: sin MT5, no toca la DB. Datos públicos de Hyperliquid y Binance spot a .cache_p45/.
Motor `simulate` de P15 y costo de P21-A importados.

  python tools/backtest_p45_hl_otras_monedas.py
"""
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p15_funding as p15  # noqa: E402
import backtest_p21_hyperliquid as p21  # noqa: E402

ROOT = p15.ROOT
CACHE = os.path.join(ROOT, '.cache_p45')
UNIVERSE = [('HYPE', 'HYPE'), ('ZEC', 'ZEC'), ('NEAR', 'NEAR'), ('PUMP', 'PUMP'), ('kPEPE', 'PEPE'),
            ('ENA', 'ENA'), ('UNI', 'UNI'), ('XPL', 'XPL'), ('ASTER', 'ASTER'), ('WLD', 'WLD'),
            ('ZRO', 'ZRO'), ('AAVE', 'AAVE'), ('JUP', 'JUP'), ('TRUMP', 'TRUMP'), ('TAO', 'TAO')]
START_MS, END_MS, P8H = p21.START_MS, p21.END_MS, p21.P8H
COST_A = p21.COST_A                                   # 0,37%
COST_HI = 2 * (0.0010 + 0.00045) + 4 * 0.0005        # 0,49% (descriptivo)
WEEK = 7 * 24 * 3600 * 1000
OUT = os.path.join(ROOT, 'docs', 'p45_hl_otras_monedas_resultado.json')


def load_spot(b):
    p = os.path.join(CACHE, f'spot_{b}.json')
    if os.path.exists(p):
        return json.load(open(p))
    s = p15.fetch_klines(b, False)
    json.dump(s, open(p, 'w'))
    return s


def summary(port, grid, label, hurdle_ms, pos, n):
    eq = np.cumprod(1 + port)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    ann = float(port.mean() * p15.PER_YEAR)
    bs = p15.block_boot(port, np.random.default_rng(p15.SEED)) * p15.PER_YEAR
    lo, hi = float(bs[int(0.025 * p15.BOOT)]), float(bs[int(0.975 * p15.BOOT)])
    half = port.size // 2
    h1, h2 = float(port[:half].mean() * p15.PER_YEAR), float(port[half:].mean() * p15.PER_YEAR)
    hr = p15.hurdle(*hurdle_ms)
    years = {}
    for k in range(port.size):
        years.setdefault(dt.datetime.utcfromtimestamp(grid[k] / 1000).year, []).append(port[k])
    print(f"  {label}: {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx {dd:.2%}  monedas>0 {pos}/{n}  tasa libre {hr:.2%}")
    print('    por año: ' + '  '.join(f'{y} {np.mean(v) * p15.PER_YEAR:+.1%}' for y, v in sorted(years.items())))
    crit = {'1_anual>tasa_libre_media': ann > hr, '2_CI_inf>0': lo > 0, '3_dos_mitades>0': h1 > 0 and h2 > 0,
            '4_caida_max<10%': dd < 0.10, '5_>=10/15_monedas>0': pos >= 10}
    return dict(annual=ann, ci=[lo, hi], halves=[h1, h2], max_dd=dd, hurdle=hr, pos=pos,
                por_anio={y: float(np.mean(v) * p15.PER_YEAR) for y, v in years.items()},
                criterios=crit, PASA=all(crit.values()))


def main():
    os.makedirs(CACHE, exist_ok=True)
    p21.CACHE = CACHE
    grid = np.arange(START_MS - START_MS % P8H, END_MS, P8H, dtype=np.int64).tolist()
    g = np.array(grid[:-1], dtype=np.int64)
    R, RA, RH, ACT, per = [], [], [], [], {}
    for hl_sym, b in UNIVERSE:
        hl = p21.load_hl(hl_sym)
        spot = load_spot(b)[1:]          # enmienda 1: la 1ra vela tras el listado trae un open de relleno
        d = dict(spot=spot, perp=hl['perp'], funding=hl['funding'])
        both = sorted(set(t for t, _ in spot) & set(t for t, _ in hl['perp']))
        avail = max(both[0], hl['funding'][0][0] + WEEK) if both and hl['funding'] else END_MS
        pp_, k = dict(map(tuple, hl['perp'])), (1000.0 if hl_sym.startswith('k') else 1.0)
        worst = max((abs(pp_[t] / x / k - 1) for t, x in spot if t in pp_ and t >= max(avail, START_MS)),
                    default=0.0)
        if worst >= 0.05:
            sys.exit(f'{hl_sym}: perpetuo/spot se desvía {worst:.1%} en alguna vela usada: dato roto, no se mide')
        act = (g >= avail).astype(float)
        r, comp, tot = p21.sim(d, grid, COST_A)
        ra, _, tota = p21.sim(d, grid, COST_A, always_in=True)
        rh, _, toth = p21.sim(d, grid, COST_HI)
        R.append(r); RA.append(ra); RH.append(rh); ACT.append(act)
        yrs = max(act.sum() / p15.PER_YEAR, 1e-9)
        per[hl_sym] = dict(desde=dt.datetime.utcfromtimestamp(avail / 1000).strftime('%Y-%m-%d'), total=tot,
                           anual_activo=tot / yrs, siempre=tota, costo_alto=toth, comp=comp)
        mf = float(np.mean([x for t, x in hl['funding'] if t >= avail])) * 8 if hl['funding'] else 0
        print(f"  {hl_sym:6s} desde {per[hl_sym]['desde']}  neto {tot:+.2%} ({tot / yrs:+.1%}/año activo)  "
              f"fund {comp['funding']:+.3f} base {comp['base']:+.3f} costo {comp['cost']:.3f} entradas "
              f"{comp['trades']}  | siempre {tota:+.2%}  costo 0,49% {toth:+.2%}  funding medio/8h {mf:.4%}")
    R, RA, RH, ACT = map(np.array, (R, RA, RH, ACT))
    nact = ACT.sum(axis=0)
    first = int(np.argmax(nact > 0))

    def port(M):
        return np.where(nact > 0, (M * ACT).sum(axis=0) / np.maximum(nact, 1), 0.0)[first:]

    gg = grid[first:]
    pos = sum(1 for v in per.values() if v['total'] > 0)
    print(f"\n  cartera desde {dt.datetime.utcfromtimestamp(gg[0] / 1000).date()}, monedas activas media "
          f"{nact[first:].mean():.1f}")
    hm = (gg[0], gg[-1])
    main_s = summary(port(R), gg, 'P45 (decide, capital entre disponibles)', hm, pos, len(UNIVERSE))
    print('  descriptivo:')
    zeros = summary(R.mean(axis=0)[first:], gg, 'con ceros (P21)', hm, pos, len(UNIVERSE))
    alw = summary(port(RA), gg, 'siempre adentro', hm, sum(1 for v in per.values() if v['siempre'] > 0), 15)
    hi = summary(port(RH), gg, 'costo 0,49%', hm, sum(1 for v in per.values() if v['costo_alto'] > 0), 15)
    for k, v in main_s['criterios'].items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f"  >>> P45: {'PASA' if main_s['PASA'] else 'NO PASA'}")
    res = dict(por_moneda=per, decide=main_s, con_ceros=zeros, siempre=alw, costo_alto=hi, PASA=main_s['PASA'],
               criterio='docs/p45_hl_otras_monedas_criterio.md (863e142) + enmienda 1 (c475b3f)')
    json.dump(res, open(OUT, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
