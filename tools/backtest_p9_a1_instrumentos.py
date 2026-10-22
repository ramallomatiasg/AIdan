"""
backtest_p9_a1_instrumentos.py — P9: A1 (reversión a 2σ) en oro e índices, M15, salida a H32.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p1/M15`.
Criterio declarado ANTES de medir: docs/p9_a1_instrumentos_criterio.md (dc2a273). Leer contra eso.

La señal se importa de screen_generators.gen_A1 (no se re-escribe). Unidad = pseudo-pips de P1 (rango
M15 mediano normalizado al de EURUSD). Sin cruzar el rollover (no hay swap que estimar). EURUSD es
ancla descriptiva: no decide.

Uso:
    python tools/backtest_p9_a1_instrumentos.py
"""
import json
import os
import sys
import zlib

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.screen_generators import gen_A1  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_p1', 'M15')
ANCHOR = 'EURUSD'
NEW = ['XAUUSD', 'USTEC', 'US30', 'DE40']
COMM_RT_USD = {'EURUSD': 7.0, 'XAUUSD': 7.0, 'USTEC': 0.0, 'US30': 0.0, 'DE40': 0.0}
EURUSD_SPREAD_FLOOR = 0.00001
WARMUP = 100
H_MAIN = 32
H_ALL = (4, 16, 32)
CONTROL_REPS = 200
MIN_N = 2000
MIN_POS = 3
OUT = os.path.join(ROOT, 'docs', 'p9_a1_instrumentos_resultado.json')


def load(sym):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.meta.json')) as f:
        meta = json.load(f)
    o, h, l, c = (r[k].astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    t = r['time'].astype(np.int64)
    spr = r['spread'].astype(np.float64) * meta['point']
    if sym == ANCHOR:
        spr = np.maximum(spr, EURUSD_SPREAD_FLOOR)
    cost_px = spr + COMM_RT_USD[sym] / meta['contract_size']
    return dict(sym=sym, o=o, h=h, l=l, c=c, t=t, cost_px=cost_px, meta=meta,
                med_range=float(np.median(h - l)))


def eligible(P, H):
    """Barras donde se puede entrar: fuera de [23:00, 01:00) server y saliendo el mismo día server."""
    t = P['t']
    n = t.size
    ok = np.zeros(n, dtype=bool)
    i = np.arange(WARMUP, n - H - 1)
    tod = t[i] % 86400
    same_day = (t[i + H] // 86400) == (t[i] // 86400)
    ok[i] = ~((tod >= 82800) | (tod < 3600)) & same_day
    return ok


def one_at_a_time(idx, H):
    keep, free = [], -1
    for k, i in enumerate(idx):
        if i >= free:
            keep.append(k)
            free = i + H
    return np.asarray(keep, dtype=np.int64)


def nets(P, ii, dd, H, pp):
    gross = dd * (P['c'][ii + H] - P['c'][ii]) / pp
    return gross, gross - P['cost_px'][ii] / pp


def run_sym(P, H, pp):
    idx, dirs = gen_A1(P['o'], P['h'], P['l'], P['c'], P['t'], pp)
    ok = eligible(P, H)
    k = ok[idx]
    idx, dirs = idx[k], dirs[k]
    sel = one_at_a_time(idx, H)
    ii, dd = idx[sel], dirs[sel]
    g, net = nets(P, ii, dd, H, pp)
    ctrl = np.zeros(CONTROL_REPS)
    pool = np.flatnonzero(ok)
    if ii.size:
        rng = np.random.default_rng(zlib.crc32(f"{P['sym']}|{H}|p9".encode()))
        p_long = float((dd > 0).mean())
        for r_ in range(CONTROL_REPS):
            ri = rng.choice(pool, ii.size)
            rd = np.where(rng.random(ii.size) < p_long, 1, -1)
            ctrl[r_] = float(nets(P, ri, rd, H, pp)[1].sum())
    return dict(ii=ii, dd=dd, gross=g, net=net, t=P['t'][ii], ctrl_sum=ctrl,
                cost=P['cost_px'][ii] / pp)


def pool_eval(rows):
    net = np.concatenate([r['net'] for r in rows])
    tt = np.concatenate([r['t'] for r in rows])
    order = np.argsort(tt)
    net, tt = net[order], tt[order]
    lo, hi, _ = bootstrap_ci(net)
    half = net.size // 2
    ctrl = np.sort(sum(r['ctrl_sum'] for r in rows) / net.size)
    return dict(n=int(net.size), neto=float(net.mean()), ci=[lo, hi],
                mitades=[float(net[:half].mean()), float(net[half:].mean())],
                control_mediana=float(ctrl[CONTROL_REPS // 2]),
                control_p95=float(ctrl[int(0.95 * CONTROL_REPS)]))


def main():
    data = {s: load(s) for s in [ANCHOR] + NEW}
    eu_range_pips = data[ANCHOR]['med_range'] / 0.0001
    pps = {s: data[s]['med_range'] / eu_range_pips for s in data}
    print(f'rango M15 mediano EURUSD = {eu_range_pips:.2f}p  =>  pseudo-pip = rango/{eu_range_pips:.2f}')
    out = {'criterio': 'docs/p9_a1_instrumentos_criterio.md (dc2a273)', 'por_horizonte': {}}
    for H in H_ALL:
        tag = '  <== DECIDE' if H == H_MAIN else '  (secundario)'
        print(f'\n=== H{H} ({H * 15} min){tag}')
        print(f"  {'sym':7}{'n':>7}{'neto':>8}{'bruto':>8}{'costo':>7}{'largo':>8}{'corto':>8}{'ctrl med':>9}{'tr/dia':>7}")
        rows, per = {}, {}
        for s in [ANCHOR] + NEW:
            P = data[s]
            r = run_sym(P, H, pps[s])
            rows[s] = r
            n = r['net'].size
            dias = (P['t'][-1] - P['t'][WARMUP]) / 86400 * 5 / 7
            lg = r['net'][r['dd'] > 0]
            sh = r['net'][r['dd'] < 0]
            cm = float(np.median(r['ctrl_sum'] / n)) if n else float('nan')
            per[s] = dict(n=int(n), neto=float(r['net'].mean()), bruto=float(r['gross'].mean()),
                          costo=float(r['cost'].mean()), largo=float(lg.mean()) if lg.size else None,
                          corto=float(sh.mean()) if sh.size else None, control_mediana=cm,
                          pseudo_pip=pps[s])
            print(f"  {s:7}{n:>7}{per[s]['neto']:>8.3f}{per[s]['bruto']:>8.3f}{per[s]['costo']:>7.3f}"
                  f"{per[s]['largo'] or 0:>8.3f}{per[s]['corto'] or 0:>8.3f}{cm:>9.3f}{n / dias:>7.2f}")
        ev = pool_eval([rows[s] for s in NEW])
        pos = sum(1 for s in NEW if per[s]['n'] and per[s]['neto'] > 0)
        crit = {
            f'1_n>={MIN_N}': ev['n'] >= MIN_N,
            '2_media>0_CI_inf>0': bool(ev['neto'] > 0 and ev['ci'][0] is not None and ev['ci'][0] > 0),
            '3_dos_mitades>0': ev['mitades'][0] > 0 and ev['mitades'][1] > 0,
            '4_>control_p95': ev['neto'] > ev['control_p95'],
            f'5_>={MIN_POS}/4_instrumentos>0': pos >= MIN_POS,
        }
        ev.update(pos=pos, criterios=crit, PASA=all(crit.values()))
        print(f"  POOL 4 nuevos: n={ev['n']} neto {ev['neto']:+.4f}pp  CI [{ev['ci'][0]:+.4f}, {ev['ci'][1]:+.4f}]"
              f"  mitades {ev['mitades'][0]:+.3f} / {ev['mitades'][1]:+.3f}  pos {pos}/4"
              f"  control mediana {ev['control_mediana']:+.3f} p95 {ev['control_p95']:+.3f}")
        if H == H_MAIN:
            for k, v in crit.items():
                print(f"      [{'OK ' if v else 'NO '}] {k}")
            print(f"  >>> {'PASA' if ev['PASA'] else 'NO PASA'}")
        out['por_horizonte'][str(H)] = dict(pool=ev, por_sym=per)
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
