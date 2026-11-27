"""P81 — SPY gestionado por volatilidad (Moreira & Muir 2017), sin apalancamiento, contra SPY siempre.

Criterio declarado antes de medir: docs/p81_spy_vol_gestionado_criterio.md (9571a39).
Read-only: sin MT5, no toca la DB. Datos: .cache_p81/SPY.json (Yahoo, ajustado) y .cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p81_spy_vol_gestionado.py              # 1994 -> 2009
  python tools/backtest_p81_spy_vol_gestionado.py --reserved   # 2010 -> oct-2026, solo si pasó
"""
import argparse
import bisect
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SPY = os.path.join(ROOT, '.cache_p81', 'SPY.json')
DTB3 = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p81_spy_vol_gestionado_resultado.json')
COST, PESS = 0.0005, 0.0010
BOOT, SEED, BLK = 5000, 20261126, 6
DISC = ('1994-01', '2009-12'); RES = ('2010-01', '2026-10')


def tbill():
    d = json.load(open(DTB3))
    ks = sorted(k for k, v in d.items() if v not in (None, '', '.'))
    days = [dt.date.fromisoformat(k) for k in ks]
    vals = [float(d[k]) / 100 for k in ks]
    return lambda x: vals[bisect.bisect_right(days, x) - 1]


def build(cost):
    px = json.load(open(SPY))
    days = sorted(px)
    p = np.array([px[k] for k in days])
    lr = np.diff(np.log(p))
    r = np.diff(p) / p[:-1]
    ds = [dt.date.fromisoformat(k) for k in days]
    tb = tbill()
    # fines de mes: último día hábil de cada mes
    ends = [i for i in range(len(ds)) if i == len(ds) - 1 or ds[i + 1].month != ds[i].month]
    sig = {}
    for i in ends:
        if i >= 21:
            sig[ds[i].strftime('%Y-%m')] = float(lr[i - 21:i].std(ddof=1) * np.sqrt(252))
    disc_s = [v for m, v in sig.items() if DISC[0] <= m <= DISC[1]]
    # σ_m del fin de mes previo a cada mes del descubrimiento: los fines dic-1993 .. nov-2009 deciden ene-1994 .. dic-2009;
    # el criterio dice "fines de mes del descubrimiento (ene-1994 -> dic-2009)" => se usan esos fines tal cual.
    star = float(np.mean(disc_s))
    out = {}
    w_prev = None
    for a, b in zip(ends[:-1], ends[1:]):
        m_dec = ds[a].strftime('%Y-%m')
        if m_dec not in sig:
            continue
        w = min(1.0, star / sig[m_dec])
        m = ds[b].strftime('%Y-%m')
        g_s, g_m, g_t = 1.0, 1.0, 1.0
        for i in range(a, b):          # retorno del día i -> i+1
            rf = tb(ds[i + 1]) / 252
            g_s *= 1 + r[i]
            g_m *= 1 + w * r[i] + (1 - w) * rf
            g_t *= 1 + rf
        c = cost * (abs(w - w_prev) if w_prev is not None else w)
        out[m] = (g_s - 1, (g_m - 1) - c, g_t - 1, w)
        w_prev = w
    return out, star


def sharpe(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(12))


def mdd(x):
    eq = np.cumprod(1 + x)
    return float((eq / np.maximum.accumulate(eq) - 1).min())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    lo, hi = RES if a.reserved else DISC
    base, star = build(COST)
    pes, _ = build(PESS)
    ms = [m for m in sorted(base) if lo <= m <= hi]
    S = np.array([base[m][0] for m in ms]); M = np.array([base[m][1] for m in ms])
    T = np.array([base[m][2] for m in ms]); W = np.array([base[m][3] for m in ms])
    MP = np.array([pes[m][1] for m in ms])
    xs, xm, xp = S - T, M - T, MP - T
    d = sharpe(xm) - sharpe(xs); dp = sharpe(xp) - sharpe(xs)
    n = len(ms); h = n // 2
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLK)); st = np.arange(0, n - BLK + 1)
    bs = []
    for _ in range(BOOT):
        ix = np.concatenate([np.arange(s, s + BLK) for s in rng.choice(st, nb)])[:n]
        bs.append(sharpe(xm[ix]) - sharpe(xs[ix]))
    bs = np.sort(bs)
    ci = (float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]))
    d1 = sharpe(xm[:h]) - sharpe(xs[:h]); d2 = sharpe(xm[h:]) - sharpe(xs[h:])

    def ann(x):
        return float(np.prod(1 + x) ** (12 / x.size) - 1)
    k = xm.std(ddof=1) / xs.std(ddof=1)
    mix = k * S + (1 - k) * T
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P81 SPY gestionado por vol {tag}: {n} meses ({ms[0]} -> {ms[-1]})  σ* {star:.1%}  exposición media '
          f'{W.mean():.0%}  rotación {np.abs(np.diff(W)).sum() / n * 12:.2f}/año')
    print(f'  Sharpe gestionado {sharpe(xm):.3f} vs SPY {sharpe(xs):.3f}  diferencia {d:+.3f}  CI95 [{ci[0]:+.3f}, '
          f'{ci[1]:+.3f}]  mitades {d1:+.3f} / {d2:+.3f}  pesimista {dp:+.3f}')
    print(f'  anual gestionado {ann(M):+.2%} (vol {M.std(ddof=1) * np.sqrt(12):.1%}, caída máx {mdd(M):+.1%}) | SPY '
          f'{ann(S):+.2%} (vol {S.std(ddof=1) * np.sqrt(12):.1%}, caída máx {mdd(S):+.1%}) | mezcla SPY con la misma vol '
          f'{ann(mix):+.2%} (caída máx {mdd(mix):+.1%}) | letra {ann(T):+.2%}')
    dec = {}
    for m, a_, b_ in zip(ms, xm, xs):
        dec.setdefault(m[:3] + '0s', [[], []]); dec[m[:3] + '0s'][0].append(a_); dec[m[:3] + '0s'][1].append(b_)
    print('  diferencia de Sharpe por década: ' + '  '.join(
        f'{k_} {sharpe(np.array(v[0])) - sharpe(np.array(v[1])):+.2f}' for k_, v in sorted(dec.items())))
    if a.reserved:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0}
    else:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '3_dos_mitades>0': d1 > 0 and d2 > 0,
                '4_pesimista>0': dp > 0, '5_caida_max<=SPY': mdd(M) >= mdd(S)}
    for k_, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k_}")
    ok = bool(all(crit.values()))
    print(f'  >>> P81 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(meses=n, sigma_obj=star, dif_sharpe=d, ci=list(ci), mitades=[d1, d2], pesimista=dp,
                   caida_max=[mdd(M), mdd(S)], criterios={k_: bool(v) for k_, v in crit.items()}, PASA=ok,
                   criterio='docs/p81_spy_vol_gestionado_criterio.md (9571a39)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
