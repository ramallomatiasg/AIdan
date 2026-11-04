"""
backtest_p23_a1_limite.py — P23: A1 (reversión a 2σ) en EUR/USD M15 entrando con orden LÍMITE en vez de a mercado.

READ-ONLY: no toca la DB ni MT5 (las velas M1 se bajaron una vez a `.cache_p23/EURUSD_M1.npy` con AIdan cerrado).
Criterio declarado ANTES de medir: docs/p23_a1_limite_criterio.md (720f8ff). Leer contra eso.

La señal se importa de screen_generators.gen_A1 y las ventanas/una-a-la-vez de backtest_p9 (no se re-escriben).
Unidad = pips de EUR/USD por operación.

Uso:
    python tools/backtest_p23_a1_limite.py
"""
import json
import os
import sys
import zlib

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.screen_generators import gen_A1, roll_std  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools import backtest_p9_a1_instrumentos as p9  # noqa: E402

M1_FILE = os.path.join(ROOT, '.cache_p23', 'EURUSD_M1.npy')
OUT = os.path.join(ROOT, 'docs', 'p23_a1_limite_resultado.json')
PIP = 0.0001
H = 16
COMM = {'fusion': 4.5 / 100000, 'ic': 7.0 / 100000}
THROUGH = 0.1 * PIP
SPREAD_FLOOR = 0.1 * PIP
MAIN = (0.25, 30)
DESC = [(0.0, 30), (0.5, 30), (0.25, 15), (0.25, 60)]
CONTROL_REPS = 200
MIN_N = 1500


def load():
    P = p9.load('EURUSD')
    m = np.load(M1_FILE)
    M = dict(t=m['time'].astype(np.int64), h=m['high'].astype(np.float64), l=m['low'].astype(np.float64),
             s=np.maximum(m['spread'].astype(np.float64) * 1e-5, SPREAD_FLOOR))
    P['spr'] = np.maximum(P['cost_px'] - COMM_P9_EURUSD, SPREAD_FLOOR)
    P['sd'] = roll_std(P['c'], 20)
    return P, M


COMM_P9_EURUSD = p9.COMM_RT_USD['EURUSD'] / 100000


def fills(P, M, ii, dd, k_sd, life):
    """Por señal: (llenada, precio límite). Ventana M1 = [cierre de i, cierre de i + life min)."""
    t0 = P['t'][ii] + 900
    L = P['c'][ii] - dd * k_sd * P['sd'][ii]
    start = np.searchsorted(M['t'], t0)
    idx = start[:, None] + np.arange(life)[None, :]
    idx = np.minimum(idx, M['t'].size - 1)
    inwin = (M['t'][idx] >= t0[:, None]) & (M['t'][idx] < (t0 + life * 60)[:, None])
    long_hit = M['l'][idx] <= (L[:, None] - M['s'][idx] - THROUGH)
    short_hit = M['h'][idx] >= (L[:, None] + THROUGH)
    hit = np.where(dd[:, None] > 0, long_hit, short_hit) & inwin
    covered = inwin.sum(1) >= life * 0.8          # ventana con datos M1 (no un hueco)
    return hit.any(1), L, covered


def pnl_limit(P, ii, dd, L, comm):
    ce = P['c'][ii + H]
    se = P['spr'][ii + H]
    return np.where(dd > 0, ce - L, L - (ce + se)) / PIP - comm / PIP


def pnl_market(P, ii, dd, comm):
    ci, ce = P['c'][ii], P['c'][ii + H]
    return np.where(dd > 0, ce - (ci + P['spr'][ii]), ci - (ce + P['spr'][ii + H])) / PIP - comm / PIP


def select(P, M, idx, dirs, k_sd, life):
    """Una posición u orden viva a la vez; la orden sin llenar libera a los `life` minutos."""
    keep, free = [], -1
    filled_all, L_all, cov_all = fills(P, M, idx, dirs, k_sd, life)
    pend = int(np.ceil(life / 15))
    for k, i in enumerate(idx):
        if i < free or not cov_all[k]:
            continue
        keep.append(k)
        free = i + (H if filled_all[k] else pend)
    keep = np.asarray(keep, dtype=np.int64)
    return idx[keep], dirs[keep], filled_all[keep], L_all[keep]


def run(P, M, idx, dirs, k_sd, life, comm):
    ii, dd, f, L = select(P, M, idx, dirs, k_sd, life)
    lim = pnl_limit(P, ii, dd, L, comm)
    mkt = pnl_market(P, ii, dd, comm)
    return dict(ii=ii, dd=dd, f=f, lim=lim, mkt=mkt)


def summary(r):
    f = r['f']
    net = r['lim'][f]
    order = np.argsort(r['ii'][f])
    net = net[order]
    lo, hi, _ = bootstrap_ci(net) if net.size > 10 else (None, None, None)
    half = net.size // 2
    per_sig_lim = float(np.where(f, r['lim'], 0.0).mean())
    return dict(senales=int(f.size), llenadas=int(f.sum()), tasa=float(f.mean()), neto=float(net.mean()),
                ci=[lo, hi], mitades=[float(net[:half].mean()), float(net[half:].mean())],
                por_senal_limite=per_sig_lim, por_senal_mercado=float(r['mkt'].mean()),
                mercado_no_llenadas=float(r['mkt'][~f].mean()) if (~f).any() else None,
                mercado_llenadas=float(r['mkt'][f].mean()))


def control(P, M, pool, n, p_long, k_sd, life, comm, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros(CONTROL_REPS)
    for r_ in range(CONTROL_REPS):
        ri = np.sort(rng.choice(pool, n, replace=False))
        rd = np.where(rng.random(n) < p_long, 1, -1)
        f, L, cov = fills(P, M, ri, rd, k_sd, life)
        f &= cov
        out[r_] = float(pnl_limit(P, ri[f], rd[f], L[f], comm).mean()) if f.any() else 0.0
    return np.sort(out)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    P, M = load()
    idx, dirs = gen_A1(P['o'], P['h'], P['l'], P['c'], P['t'], PIP)
    ok = p9.eligible(P, H)
    ok &= P['t'] + 900 >= M['t'][0]                       # el M1 de MT5 arranca el 23-jun-2021
    ok &= np.isfinite(P['sd'])
    k = ok[idx]
    idx, dirs = idx[k], dirs[k]
    print(f'P23 — A1 EUR/USD M15 con entrada límite · señales elegibles {idx.size} · H{H} · M1 desde 2021-06-23')
    out = {'criterio': 'docs/p23_a1_limite_criterio.md (720f8ff)', 'variantes': {}}
    for (k_sd, life) in [MAIN] + DESC:
        for broker in ('fusion', 'ic'):
            if (k_sd, life) != MAIN and broker == 'ic':
                continue
            r = run(P, M, idx, dirs, k_sd, life, COMM[broker])
            s = summary(r)
            tag = f'{k_sd}sd/{life}min/{broker}'
            out['variantes'][tag] = s
            print(f"  {tag:22} señales {s['senales']:5} llenadas {s['llenadas']:5} ({s['tasa']:.0%})"
                  f"  neto {s['neto']:+.3f}p CI [{s['ci'][0]:+.3f}, {s['ci'][1]:+.3f}]"
                  f"  mitades {s['mitades'][0]:+.3f}/{s['mitades'][1]:+.3f}"
                  f"  x señal: lím {s['por_senal_limite']:+.3f} vs mkt {s['por_senal_mercado']:+.3f}"
                  f"  | mkt llenadas {s['mercado_llenadas']:+.3f} / no llenadas {s['mercado_no_llenadas']:+.3f}")
            if (k_sd, life) == MAIN and broker == 'fusion':
                main_s, main_r = s, r
    pool = np.flatnonzero(ok)
    pool = pool[np.isfinite(P['sd'][pool])]
    p_long = float((main_r['dd'] > 0).mean())
    ctrl = control(P, M, pool, main_r['ii'].size, p_long, MAIN[0], MAIN[1], COMM['fusion'],
                   zlib.crc32(b'EURUSD|p23'))
    p95 = float(ctrl[int(0.95 * CONTROL_REPS)])
    crit = {
        f'1_llenadas>={MIN_N}': main_s['llenadas'] >= MIN_N,
        '2_media>0_CI_inf>0': bool(main_s['neto'] > 0 and main_s['ci'][0] > 0),
        '3_dos_mitades>0': all(x > 0 for x in main_s['mitades']),
        '4_>control_p95': main_s['neto'] > p95,
        '5_limite>mercado_por_senal': main_s['por_senal_limite'] > main_s['por_senal_mercado'],
    }
    print(f"\n  PRINCIPAL 0,25sd/30min/Fusion — control azar: mediana {ctrl[CONTROL_REPS // 2]:+.3f} p95 {p95:+.3f}")
    for kk, v in crit.items():
        print(f"      [{'OK ' if v else 'NO '}] {kk}")
    passed = all(crit.values())
    print(f"  >>> {'PASA' if passed else 'NO PASA'}")
    out.update(principal=dict(main_s, control_mediana=float(ctrl[CONTROL_REPS // 2]), control_p95=p95,
                              criterios=crit, PASA=passed))
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
