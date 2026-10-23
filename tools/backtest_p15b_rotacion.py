"""
backtest_p15b_rotacion.py — P15b: carry de funding con ROTACIÓN hacia las K=3 monedas que más pagan.

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Reusa los datos públicos de Binance y la simulación de P15.
Criterio declarado ANTES de medir: docs/p15b_rotacion_criterio.md (5f1dc1f). Leer contra eso.

Uso:
    python tools/backtest_p15b_rotacion.py              # en muestra: las 10 monedas de P15
    python tools/backtest_p15b_rotacion.py --reserved   # fuera de muestra (10 nuevas): solo si pasó, una vez
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_p15_funding import (load, simulate, hurdle, block_boot, RT_COST, CAPITAL, REBAL,  # noqa: E402
                                        ENTER, EXIT, WINDOW_MS, P8H, END_MS, PER_YEAR, BOOT, SEED)

IN_SAMPLE = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'LINK', 'LTC', 'AVAX']
OOS = ['TRX', 'DOT', 'BCH', 'ETC', 'ATOM', 'FIL', 'UNI', 'XLM', 'NEAR', 'XTZ']
K = 3
KEEP_RANK = 2 * K
YEAR_MS = 365 * 24 * 3600 * 1000
OUT = os.path.join(ROOT, 'docs', 'p15b_rotacion_resultado.json')
OUT_OOS = os.path.join(ROOT, 'docs', 'p15b_rotacion_reservados.json')


class Coin:
    def __init__(self, d):
        self.st = dict(d['spot'])
        self.pp = dict(d['perp'])
        self.ft = np.array([x[0] for x in d['funding']], dtype=np.int64)
        self.fr = np.array([x[1] for x in d['funding']], dtype=np.float64)
        self.cs = np.concatenate([[0.0], np.cumsum(self.fr)])
        self.pt = np.array(sorted(self.pp), dtype=np.int64)
        self.pv = np.array([self.pp[t] for t in self.pt])

    def have(self, t):
        return t in self.st and t in self.pp

    def signal(self, t):
        """Media del funding de los 7 días previos a t, por 8 h (mismo cálculo que P15)."""
        if not self.ft.size or self.ft[0] > t - WINDOW_MS:
            return None
        hi = np.searchsorted(self.ft, t, side='left')
        lo = np.searchsorted(self.ft, t - WINDOW_MS, side='left')
        return (self.cs[hi] - self.cs[lo]) / 21.0

    def perp_at(self, t):
        i = np.searchsorted(self.pt, t, side='right') - 1
        return self.pv[max(i, 0)]

    def funding(self, after, before, f0):
        """Funding por unidad de nocional de los eventos en (after, before), como P15."""
        i0 = np.searchsorted(self.ft, after, side='right')
        i1 = np.searchsorted(self.ft, before, side='left')
        return float(sum(self.fr[j] * self.perp_at(self.ft[j]) / f0 for j in range(i0, i1)))


def rotate(coins, grid):
    legs = {}
    realized = 0.0
    value = np.zeros(len(grid))
    stats = dict(entries=0, exits=0, rebal=0, slots_used=[])
    for k, t in enumerate(grid):
        for sym, pos in legs.items():
            pos['fund'] += coins[sym].funding(pos['t'], t, pos['f0'])
            pos['t'] = t - 1
        sigs = {}
        for sym, c in coins.items():
            if c.have(t):
                s = c.signal(t)
                if s is not None:
                    sigs[sym] = s
        ranking = sorted(sigs, key=lambda x: -sigs[x])
        rank = {s: i for i, s in enumerate(ranking)}
        for sym in list(legs):                                   # salidas
            if sym in sigs and (sigs[sym] < EXIT or rank[sym] >= KEEP_RANK):
                c, pos = coins[sym], legs.pop(sym)
                realized += c.st[t] / pos['s0'] - c.pp[t] / pos['f0'] + pos['fund'] - RT_COST / 2
                stats['exits'] += 1
        free = K - len(legs)                                     # entradas
        for sym in [s for s in ranking if s not in legs and sigs[s] >= ENTER][:max(free, 0)]:
            c = coins[sym]
            legs[sym] = dict(s0=c.st[t], f0=c.pp[t], ref=c.st[t], t=t, fund=0.0, mtm=0.0, new=True)
            realized -= RT_COST / 2
            stats['entries'] += 1
        mtm = 0.0
        for sym, pos in legs.items():
            c = coins[sym]
            if c.have(t):
                s, f = c.st[t], c.pp[t]
                if not pos.pop('new', False) and (s / pos['ref'] >= REBAL or s / pos['ref'] <= 1 / REBAL):
                    realized += s / pos['s0'] - f / pos['f0'] + pos['fund'] - RT_COST
                    legs[sym] = pos = dict(s0=s, f0=f, ref=s, t=pos['t'], fund=0.0, mtm=0.0)
                    stats['rebal'] += 1
                pos['mtm'] = s / pos['s0'] - f / pos['f0'] + pos['fund']
            mtm += pos['mtm']
        value[k] = realized + mtm
        stats['slots_used'].append(len(legs))
    value[-1] -= len(legs) * RT_COST / 2                         # cierra lo abierto al final
    return np.diff(value) / (CAPITAL * K), stats


def ann(x):
    return float(np.mean(x) * PER_YEAR)


def run(syms, oos):
    data = {s: load(s) for s in syms}
    coins = {s: Coin(data[s]) for s in syms}
    t0 = min(min(t for t, _ in data[s]['perp']) for s in syms)
    grid = np.arange(t0 - t0 % P8H, END_MS, P8H, dtype=np.int64).tolist()
    r_rot, st = rotate(coins, grid)
    r_eq = np.mean([simulate(data[s], grid)[0] for s in syms], axis=0)
    diff = r_rot - r_eq
    rng = np.random.default_rng(SEED)
    bd = block_boot(diff, rng) * PER_YEAR
    d_lo, d_hi = float(bd[int(0.025 * BOOT)]), float(bd[int(0.975 * BOOT)])
    br = block_boot(r_rot, np.random.default_rng(SEED + 1)) * PER_YEAR
    eq = np.cumprod(1 + r_rot)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    half = r_rot.size // 2
    h1, h2 = ann(r_rot[:half]), ann(r_rot[half:])
    last = np.array(grid[1:]) >= END_MS - YEAR_MS
    hr = hurdle(grid[0], grid[-1])
    years = {}
    for k in range(r_rot.size):
        y = dt.datetime.utcfromtimestamp(grid[k] / 1000).year
        years.setdefault(y, ([], []))
        years[y][0].append(r_rot[k])
        years[y][1].append(r_eq[k])
    print(f"monedas: {', '.join(syms)}")
    print(f"  ROTACIÓN K={K}: {ann(r_rot):+.2%}/año  CI [{br[int(0.025 * BOOT)]:+.2%}, {br[int(0.975 * BOOT)]:+.2%}]  "
          f"mitades {h1:+.2%} / {h2:+.2%}  caída máx {dd:.2%}  últimos 12 meses {ann(r_rot[last]):+.2%}")
    print(f"  P15 (ranura fija por moneda): {ann(r_eq):+.2%}/año  últimos 12 meses {ann(r_eq[last]):+.2%}")
    print(f"  DIFERENCIA rotacion - P15: {ann(diff):+.2%}/año  CI95 [{d_lo:+.2%}, {d_hi:+.2%}]")
    print(f"  ranuras usadas en promedio {np.mean(st['slots_used']):.2f}/{K}  entradas {st['entries']}  "
          f"salidas {st['exits']}  rebalanceos {st['rebal']}  tasa libre media {hr:.2%}")
    print('  por año (rotación / P15): ' + '  '.join(
        f'{y} {ann(a):+.1%}/{ann(b):+.1%}' for y, (a, b) in sorted(years.items())))
    if oos:
        crit = {'oos_rotacion>P15': ann(r_rot) > ann(r_eq), 'oos_rotacion>tasa_libre': ann(r_rot) > hr}
    else:
        crit = {'1_dif_CI_inf>0': d_lo > 0,
                '2_anual>tasa_libre': ann(r_rot) > hr,
                '3_dos_mitades>0': h1 > 0 and h2 > 0,
                '4_caida_max<10%': dd < 0.10,
                '5_ultimos_12m>0': ann(r_rot[last]) > 0}
    ok = all(crit.values())
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f"  >>> {'PASA' if ok else 'NO PASA'}")
    return dict(monedas=syms, rot_annual=ann(r_rot), eq_annual=ann(r_eq), diff_annual=ann(diff),
                diff_ci=[d_lo, d_hi], halves=[h1, h2], max_dd=dd, last12_rot=ann(r_rot[last]),
                last12_eq=ann(r_eq[last]), hurdle=hr, slots_used=float(np.mean(st['slots_used'])),
                entries=st['entries'], por_anio={y: [ann(a), ann(b)] for y, (a, b) in years.items()},
                criterios=crit, PASA=ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('En muestra NO pasó (o no se corrió): las monedas nuevas no se bajan ni se miran.')
        if os.path.exists(OUT_OOS):
            sys.exit('El fuera de muestra ya se corrió (una sola vez).')
        res, path = run(OOS, True), OUT_OOS
    else:
        res, path = run(IN_SAMPLE, False), OUT
    res['criterio'] = 'docs/p15b_rotacion_criterio.md (5f1dc1f)'
    with open(path, 'w') as f:
        json.dump(res, f, indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
