"""
backtest_p4_lead_lag.py — P4: lead-lag de la cesta USD ("catch-up"), M5, salida a H6.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000`.
Criterio declarado ANTES de medir: docs/p4_lead_lag_criterio.md (c924563). Leer contra eso.

Uso:
    python tools/backtest_p4_lead_lag.py              # cesta USD (decide)
    python tools/backtest_p4_lead_lag.py --reserved   # cesta JPY con CHFJPY/NZDJPY: solo si la USD PASÓ
"""
import argparse
import json
import os
import sys
import zlib
from functools import reduce

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_fase2', 'M5_500000')
USD = dict(targets=['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD'], others=[])
JPY = dict(targets=['CHFJPY', 'NZDJPY'], others=['EURJPY', 'GBPJPY', 'USDJPY'])
L = 6
ATR_N = 20
BASKET_MIN = 1.0
TARGET_MAX = 0.25
H_MAIN = 6
H_ALL = (3, 6, 12)
CONTROL_REPS = 200
MIN_N = 1000
MIN_POS = 3
OUT = os.path.join(ROOT, 'docs', 'p4_lead_lag_resultado.json')
OUT_RES = os.path.join(ROOT, 'docs', 'p4_lead_lag_reservados.json')


def load(sym):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.spec.json')) as f:
        spec = json.load(f)
    pip = spec['pip']
    point = 10.0 ** -spec['digits']
    h, l, c = (r[k].astype(np.float64) for k in ('high', 'low', 'close'))
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    cs = np.concatenate([[0.0], np.cumsum(np.nan_to_num(tr))])
    atr = np.full(c.size, np.nan)
    atr[ATR_N:] = (cs[ATR_N + 1:] - cs[1:-ATR_N]) / ATR_N
    spr = np.maximum(r['spread'].astype(np.float64) * point, 0.1 * pip) / pip
    return dict(sym=sym, t=r['time'].astype(np.int64), c=c, atr=atr, pip=pip,
                cost=spr + spec['commission_pips'])


def aligned(D, syms):
    common = reduce(np.intersect1d, [D[s]['t'] for s in syms])
    pos = {s: np.searchsorted(D[s]['t'], common) for s in syms}
    return common, pos


def move(D, s, p):
    """r = movimiento de L velas en unidades de ATR, sobre la serie ALINEADA (p = índices propios)."""
    c, atr = D[s]['c'], D[s]['atr']
    out = np.full(p.size, np.nan)
    out[L:] = (c[p[L:]] - c[p[:-L]]) / atr[p[L:]]
    return out


def run_target(D, tgt, basket, common, pos, H):
    T = D[tgt]
    p = pos[tgt]
    n_own = T['t'].size
    contiguous = np.zeros(common.size, dtype=bool)
    contiguous[L:] = (common[L:] - common[:-L]) == L * 300
    rt = move(D, tgt, p)
    rb = np.vstack([move(D, s, pos[s]) for s in basket])
    with np.errstate(invalid='ignore'):
        up = (rb >= BASKET_MIN).all(axis=0) & (np.abs(rt) <= TARGET_MAX)
        dn = (rb <= -BASKET_MIN).all(axis=0) & (np.abs(rt) <= TARGET_MAX)
    # elegibilidad de la entrada (sobre la serie propia del objetivo)
    ok = contiguous & ~np.isnan(rt) & ~np.isnan(rb).any(axis=0) & (p + H < n_own)
    pe = np.minimum(p + H, n_own - 1)
    tod = common % 86400
    ok &= ~((tod >= 82800) | (tod < 3600))
    ok &= (T['t'][pe] - T['t'][p]) == H * 300
    ok &= (T['t'][pe] // 86400) == (common // 86400)
    sig_k = np.flatnonzero(ok & (up | dn))
    dirs_all = np.where(up, 1, -1)
    keep, free = [], -1
    for k in sig_k:
        if p[k] >= free:
            keep.append(k)
            free = p[k] + H
    kk = np.asarray(keep, dtype=np.int64)
    dd = dirs_all[kk]

    def nets(ks, ds):
        i = p[ks]
        g = ds * (T['c'][i + H] - T['c'][i]) / T['pip']
        return g, g - T['cost'][i]

    g, net = nets(kk, dd)
    ctrl = np.zeros(CONTROL_REPS)
    pool = np.flatnonzero(ok)
    if kk.size:
        rng = np.random.default_rng(zlib.crc32(f'{tgt}|{H}|p4'.encode()))
        p_long = float((dd > 0).mean())
        for r_ in range(CONTROL_REPS):
            rk = rng.choice(pool, kk.size)
            rd = np.where(rng.random(kk.size) < p_long, 1, -1)
            ctrl[r_] = float(nets(rk, rd)[1].sum())
    return dict(gross=g, net=net, dd=dd, t=common[kk], ctrl_sum=ctrl, cost=T['cost'][p[kk]],
                dias=(common[-1] - common[0]) / 86400 * 5 / 7)


def evaluate(rows, min_pos):
    net = np.concatenate([r['net'] for r in rows.values()])
    tt = np.concatenate([r['t'] for r in rows.values()])
    o = np.argsort(tt)
    net = net[o]
    lo, hi, _ = bootstrap_ci(net)
    half = net.size // 2
    ctrl = np.sort(sum(r['ctrl_sum'] for r in rows.values()) / max(net.size, 1))
    pos = sum(1 for r in rows.values() if r['net'].size and r['net'].mean() > 0)
    ev = dict(n=int(net.size), neto=float(net.mean()) if net.size else float('nan'), ci=[lo, hi],
              mitades=[float(net[:half].mean()), float(net[half:].mean())] if net.size > 1 else [None, None],
              control_mediana=float(ctrl[CONTROL_REPS // 2]), control_p95=float(ctrl[int(0.95 * CONTROL_REPS)]),
              pos=pos)
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get(str(H_MAIN), {}).get('PASA'):
            sys.exit('La cesta USD NO pasó (o no se corrió): los reservados no se miran.')
        U, out_path = JPY, OUT_RES
    else:
        U, out_path = USD, OUT
    syms = U['targets'] + U['others']
    D = {s: load(s) for s in syms}
    common, pos = aligned(D, syms)
    print(f'velas alineadas: {common.size}  ({len(syms)} instrumentos)')
    out = {'criterio': 'docs/p4_lead_lag_criterio.md (c924563)'}
    for H in H_ALL:
        tag = '  <== DECIDE' if H == H_MAIN else '  (secundario)'
        print(f'\n=== H{H} ({H * 5} min){tag}')
        rows = {}
        for tgt in U['targets']:
            basket = [s for s in syms if s != tgt][:3] if not U['others'] else \
                U['others'] + [s for s in U['targets'] if s != tgt]
            r = run_target(D, tgt, basket, common, pos, H)
            rows[tgt] = r
            n = r['net'].size
            if n:
                lg, sh = r['net'][r['dd'] > 0], r['net'][r['dd'] < 0]
                cm = float(np.median(r['ctrl_sum'] / n))
                print(f"  {tgt:7s} cesta={','.join(basket)}  n={n:5d} ({n / r['dias']:.2f}/dia)  "
                      f"neto {r['net'].mean():+.3f}p  bruto {r['gross'].mean():+.3f}  costo {r['cost'].mean():.3f}  "
                      f"largo {lg.mean() if lg.size else 0:+.3f} corto {sh.mean() if sh.size else 0:+.3f}  "
                      f"ctrl med {cm:+.3f}")
            else:
                print(f'  {tgt:7s} n=0')
        ev = evaluate(rows, MIN_POS)
        if a.reserved:
            crit = {'oos_media>0': ev['neto'] > 0, 'oos_>control_p95': ev['neto'] > ev['control_p95']}
        else:
            crit = {
                f'1_n>={MIN_N}': ev['n'] >= MIN_N,
                '2_media>0_CI_inf>0': bool(ev['neto'] > 0 and ev['ci'][0] is not None and ev['ci'][0] > 0),
                '3_dos_mitades>0': bool(ev['mitades'][0] and ev['mitades'][0] > 0 and ev['mitades'][1] > 0),
                '4_>control_p95': ev['neto'] > ev['control_p95'],
                f'5_>={MIN_POS}/4_objetivos>0': ev['pos'] >= MIN_POS,
            }
        ev.update(criterios=crit, PASA=all(crit.values()))
        ci = ev['ci']
        print(f"  POOL: n={ev['n']} neto {ev['neto']:+.4f}p  CI [{ci[0] if ci[0] is None else round(ci[0], 4)}, "
              f"{ci[1] if ci[1] is None else round(ci[1], 4)}]  mitades {ev['mitades']}  pos {ev['pos']}/"
              f"{len(rows)}  control mediana {ev['control_mediana']:+.3f} p95 {ev['control_p95']:+.3f}")
        if H == H_MAIN:
            for k, v in crit.items():
                print(f"      [{'OK ' if v else 'NO '}] {k}")
            print(f"  >>> {'PASA' if ev['PASA'] else 'NO PASA'}")
        out[str(H)] = ev
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(out_path, ROOT)}')


if __name__ == '__main__':
    main()
