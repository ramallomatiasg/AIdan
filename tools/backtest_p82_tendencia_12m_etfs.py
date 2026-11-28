"""P82 — Tendencia de 12 meses multi-activo con 8 ETFs (Moskowitz-Ooi-Pedersen 2012) contra 1/8 siempre.

Criterio declarado antes de medir: docs/p82_tendencia_12m_etfs_criterio.md (bbd2b48).
Read-only: sin MT5, no toca la DB. Datos: .cache_p82/*.json (Yahoo ajustado) y .cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p82_tendencia_12m_etfs.py              # mar-2007 -> dic-2015
  python tools/backtest_p82_tendencia_12m_etfs.py --reserved   # ene-2016 -> oct-2026, solo si pasó
"""
import argparse
import bisect
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ETFS = ['SPY', 'EFA', 'EEM', 'TLT', 'IEF', 'GLD', 'DBC', 'VNQ']
DTB3 = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p82_tendencia_12m_etfs_resultado.json')
COST, PESS = 0.0005, 0.0010
BOOT, NRAND, SEED, BLK = 5000, 1000, 20261127, 6
DISC = ('2007-03', '2015-12')
RES = ('2016-01', '2026-10')


def tbill():
    d = json.load(open(DTB3))
    ks = sorted(k for k, v in d.items() if v not in (None, '', '.'))
    days = [dt.date.fromisoformat(k) for k in ks]
    vals = [float(d[k]) / 100 for k in ks]
    return lambda x: vals[bisect.bisect_right(days, x) - 1]


def monthly(folder='.cache_p82', syms=ETFS, cal_sym='SPY'):
    """Retorno mensual de cada símbolo y de la letra, por mes calendario (fin de mes a fin de mes)."""
    px = {s: json.load(open(os.path.join(ROOT, folder, f'{s}.json'))) for s in syms}
    cal = sorted(px[cal_sym])
    tb = tbill()
    ends = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]
    R, B = {}, {}
    for a, b in zip(ends[:-1], ends[1:]):
        m = cal[b][:7]
        g = 1.0
        for i in range(a, b):
            g *= 1 + tb(dt.date.fromisoformat(cal[i + 1])) / 252
        B[m] = g - 1
        row = {}
        for s in syms:
            p0, p1 = px[s].get(cal[a]), px[s].get(cal[b])
            row[s] = (p1 / p0 - 1) if p0 and p1 else None
        R[m] = row
    return R, B


def run(R, B, months, cost, weights_fn):
    """weights_fn(k) -> vector de pesos (8) para months[k]; el resto a la letra. Costo sobre la rotación real."""
    out, turn = [], []
    drift = None
    for k, m in enumerate(months):
        w = weights_fn(k)
        wb = 1 - w.sum()
        tv = (np.abs(w - drift[0]).sum() + abs(wb - drift[1])) if drift is not None else w.sum()
        r = np.array([R[m][s] for s in ETFS])
        out.append(float(w @ r + wb * B[m]) - cost * tv)
        turn.append(tv)
        v = w * (1 + r)
        vb = wb * (1 + B[m])
        tot = v.sum() + vb
        drift = (v / tot, vb / tot)
    return np.array(out), np.array(turn)


def sharpe(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(12))


def mdd(x):
    eq = np.cumprod(1 + x)
    return float((eq / np.maximum.accumulate(eq) - 1).min())


def ann(x):
    return float(np.prod(1 + x) ** (12 / x.size) - 1)


def yearly(ms, x):
    out = {}
    for m, v in zip(ms, x):
        out[m[:4]] = out.get(m[:4], 1.0) * (1 + v)
    return {k: v - 1 for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    lo, hi = RES if a.reserved else DISC
    R, B = monthly()
    allm = sorted(R)
    ms = [m for m in allm if lo <= m <= hi]
    sig = []
    for m in ms:
        j = allm.index(m)
        prev12 = allm[j - 12:j]
        l12 = np.prod([1 + B[x] for x in prev12]) - 1
        row = []
        for s in ETFS:
            rr = [R[x][s] for x in prev12]
            if any(v is None for v in rr) or R[m][s] is None:
                sys.exit(f'falta historia de {s} para {m}')
            row.append(np.prod([1 + v for v in rr]) - 1 > l12)
        sig.append(row)
    sig = np.array(sig, dtype=float)
    eq8 = np.full(8, 1 / 8)
    T = np.array([B[m] for m in ms])
    tr, tt = run(R, B, ms, COST, lambda k: sig[k] / 8)
    bh, bt = run(R, B, ms, COST, lambda k: eq8)
    trp, _ = run(R, B, ms, PESS, lambda k: sig[k] / 8)
    bhp, _ = run(R, B, ms, PESS, lambda k: eq8)
    xt, xb = tr - T, bh - T
    d = sharpe(xt) - sharpe(xb)
    dp = sharpe(trp - T) - sharpe(bhp - T)
    n = len(ms)
    h = n // 2
    d1 = sharpe(xt[:h]) - sharpe(xb[:h])
    d2 = sharpe(xt[h:]) - sharpe(xb[h:])
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLK))
    st = np.arange(0, n - BLK + 1)
    bs = []
    for _ in range(BOOT):
        ix = np.concatenate([np.arange(s, s + BLK) for s in rng.choice(st, nb)])[:n]
        bs.append(sharpe(xt[ix]) - sharpe(xb[ix]))
    bs = np.sort(bs)
    ci = (float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]))
    p_in = sig.mean(axis=0)
    rnd = []
    for _ in range(NRAND):
        rs = (rng.random(sig.shape) < p_in).astype(float)
        x, _ = run(R, B, ms, COST, lambda k: rs[k] / 8)
        rnd.append(sharpe(x - T))
    p95 = float(np.percentile(rnd, 95))
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P82 tendencia 12m 8 ETFs {tag}: {n} meses ({ms[0]} -> {ms[-1]})  exposición media {sig.mean():.0%}  '
          f'rotación {tt.sum() / n * 12:.2f}/año (1/8: {bt.sum() / n * 12:.2f})')
    print(f'  Sharpe tendencia {sharpe(xt):.3f} vs 1/8 {sharpe(xb):.3f}  diferencia {d:+.3f}  CI95 [{ci[0]:+.3f}, '
          f'{ci[1]:+.3f}]  mitades {d1:+.3f} / {d2:+.3f}  pesimista {dp:+.3f}')
    print(f'  azar: mediana {np.median(rnd):.3f}  p95 {p95:.3f}')
    print(f'  anual tendencia {ann(tr):+.2%} (vol {tr.std(ddof=1) * np.sqrt(12):.1%}, caída máx {mdd(tr):+.1%}) | 1/8 '
          f'{ann(bh):+.2%} (vol {bh.std(ddof=1) * np.sqrt(12):.1%}, caída máx {mdd(bh):+.1%}) | letra {ann(T):+.2%}')
    print('  meses dentro por ETF: ' + '  '.join(f'{s} {p:.0%}' for s, p in zip(ETFS, p_in)))
    yt, yb = yearly(ms, tr), yearly(ms, bh)
    print('  por año (tendencia - 1/8): ' + '  '.join(f'{y} {yt[y] - yb[y]:+.1%}' for y in sorted(yt)))
    if a.reserved:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '6_azar_p95': sharpe(xt) > p95}
    else:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '3_dos_mitades>0': d1 > 0 and d2 > 0,
                '4_pesimista>0': dp > 0, '5_caida_max<=1/8': mdd(tr) >= mdd(bh), '6_azar_p95': sharpe(xt) > p95}
    for k_, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k_}")
    ok = bool(all(crit.values()))
    print(f'  >>> P82 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(meses=n, sharpe=[sharpe(xt), sharpe(xb)], dif_sharpe=d, ci=list(ci), mitades=[d1, d2],
                   pesimista=dp, caida_max=[mdd(tr), mdd(bh)], azar_p95=p95,
                   criterios={k_: bool(v) for k_, v in crit.items()}, PASA=ok,
                   criterio='docs/p82_tendencia_12m_etfs_criterio.md (bbd2b48)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
