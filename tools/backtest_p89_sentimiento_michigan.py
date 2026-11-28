"""P89 — Sentimiento Michigan (UMCSENT, mes m-1) en el 20% mas bajo -> VFINX, si no letra; contra VFINX siempre.

Criterio declarado antes de medir: docs/p89_sentimiento_michigan_criterio.md (ba7872b).
Read-only: sin MT5, no toca la DB. Datos: .cache_p83/VFINX.json (Yahoo), .cache_p83/T10Y3M.json (FRED),
.cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p89_sentimiento_michigan.py              # ene-1987 -> dic-2005
  python tools/backtest_p89_sentimiento_michigan.py --reserved   # ene-2006 -> oct-2026, solo si pasó
"""
import argparse
import bisect
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
VFINX = os.path.join(ROOT, '.cache_p89', 'VFINX.json')
SLOPE = os.path.join(ROOT, '.cache_p89', 'UMCSENT.json')
DTB3 = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p89_sentimiento_michigan_resultado.json')
COST, PESS = 0.0005, 0.0010
BOOT, NRAND, SEED, BLK = 5000, 1000, 20261128, 6
DISC = ('1981-03', '2002-12')
RES = ('2003-01', '2026-10')


def step(path, scale=1.0):
    d = json.load(open(path))
    ks = sorted(k for k, v in d.items() if v not in (None, '', '.'))
    days = [dt.date.fromisoformat(k) for k in ks]
    vals = [float(d[k]) * scale for k in ks]
    return lambda x: vals[bisect.bisect_right(days, x) - 1]


def build():
    px = json.load(open(VFINX))
    cal = sorted(px)
    tb = step(DTB3, 0.01)
    um = json.load(open(SLOPE))
    uk = sorted(k for k in um if k >= '1978-01' and um[k] not in (None, '', '.'))
    uv = {k[:7]: float(um[k]) for k in uk}
    umon = sorted(uv)

    def low(dec_month):
        # valor del mes anterior al de decision, percentil contra hasta 120 previos (minimo 36)
        y, mo = int(dec_month[:4]), int(dec_month[5:7])
        prev = f'{y - (mo == 1)}-{12 if mo == 1 else mo - 1:02d}'
        if prev not in uv:
            return None
        i = umon.index(prev)
        hist = [uv[x] for x in umon[max(0, i - 120):i]]
        if len(hist) < 36:
            return None
        return 1.0 if sum(h <= uv[prev] for h in hist) / len(hist) <= 0.20 else 0.0
    ends = [i for i in range(len(cal) - 1) if cal[i][:7] != cal[i + 1][:7]]
    rows = {}
    for a, b in zip(ends[:-1], ends[1:]):
        m = cal[b][:7]
        g = 1.0
        for i in range(a, b):
            g *= 1 + tb(dt.date.fromisoformat(cal[i + 1])) / 252
        sig = low(cal[a][:7])
        if sig is None:
            continue
        rows[m] = dict(dec=cal[a][:7], s=sig, r=px[cal[b]] / px[cal[a]] - 1, t=g - 1)
    return rows


def strat(R, T, inside, cost):
    out = []
    prev = None
    for k in range(len(R)):
        w = inside[k]
        c = cost * (abs(w - prev) if prev is not None else w)
        out.append(w * R[k] + (1 - w) * T[k] - c)
        prev = w
    return np.array(out)


def sharpe(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(12))


def mdd(x):
    eq = np.cumprod(1 + x)
    return float((eq / np.maximum.accumulate(eq) - 1).min())


def ann(x):
    return float(np.prod(1 + x) ** (12 / x.size) - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    rows = build()
    dm = [m for m in sorted(rows) if DISC[0] <= m <= DISC[1]]
    star = 0.5  # s ya es 1 (piso) / 0
    lo, hi = RES if a.reserved else DISC
    ms = [m for m in sorted(rows) if lo <= m <= hi]
    R = np.array([rows[m]['r'] for m in ms])
    T = np.array([rows[m]['t'] for m in ms])
    inside = np.array([1.0 if rows[m]['s'] > star else 0.0 for m in ms])
    st_ = strat(R, T, inside, COST)
    stp = strat(R, T, inside, PESS)
    xs, xb = st_ - T, R - T
    d = sharpe(xs) - sharpe(xb)
    dp = sharpe(stp - T) - sharpe(xb)
    n = len(ms)
    h = n // 2
    d1 = sharpe(xs[:h]) - sharpe(xb[:h])
    d2 = sharpe(xs[h:]) - sharpe(xb[h:])
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLK))
    stt = np.arange(0, n - BLK + 1)
    bs = []
    for _ in range(BOOT):
        ix = np.concatenate([np.arange(s, s + BLK) for s in rng.choice(stt, nb)])[:n]
        bs.append(sharpe(xs[ix]) - sharpe(xb[ix]))
    bs = np.sort(bs)
    ci = (float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]))
    ex_in = float(xb[inside == 1].mean())
    ex_out = float(xb[inside == 0].mean())
    p = inside.mean()
    rnd = [sharpe(strat(R, T, (rng.random(n) < p).astype(float), COST) - T) for _ in range(NRAND)]
    p95 = float(np.percentile(rnd, 95))
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P89 Michigan -> VFINX {tag}: {n} meses ({ms[0]} -> {ms[-1]})  dentro {p:.0%}  '
          f'cambios {np.abs(np.diff(inside)).sum() / n * 12:.2f}/año')
    print(f'  Sharpe regla {sharpe(xs):.3f} vs VFINX {sharpe(xb):.3f}  diferencia {d:+.3f}  CI95 [{ci[0]:+.3f}, '
          f'{ci[1]:+.3f}]  mitades {d1:+.3f} / {d2:+.3f}  pesimista {dp:+.3f}')
    print(f'  exceso medio mensual de VFINX: dentro {ex_in:+.3%} vs fuera {ex_out:+.3%}')
    print(f'  azar: mediana {np.median(rnd):.3f}  p95 {p95:.3f}')
    print(f'  anual regla {ann(st_):+.2%} (vol {st_.std(ddof=1) * np.sqrt(12):.1%}, caída máx {mdd(st_):+.1%}) | VFINX '
          f'{ann(R):+.2%} (vol {R.std(ddof=1) * np.sqrt(12):.1%}, caída máx {mdd(R):+.1%}) | letra {ann(T):+.2%}')
    dec = {}
    for m, x1, x2 in zip(ms, xs, xb):
        dec.setdefault(m[:3] + '0s', [[], []])
        dec[m[:3] + '0s'][0].append(x1)
        dec[m[:3] + '0s'][1].append(x2)
    print('  diferencia de Sharpe por década: ' + '  '.join(
        f'{k} {sharpe(np.array(v[0])) - sharpe(np.array(v[1])):+.2f}' for k, v in sorted(dec.items())))
    if a.reserved:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '6_azar_p95': sharpe(xs) > p95}
    else:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '3_dos_mitades>0': d1 > 0 and d2 > 0,
                '4_pesimista>0': dp > 0, '5_dentro>fuera': ex_in > ex_out, '6_azar_p95': sharpe(xs) > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P89 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(meses=n, s_star=star, sharpe=[sharpe(xs), sharpe(xb)], dif_sharpe=d, ci=list(ci),
                   mitades=[d1, d2], pesimista=dp, exceso_dentro_fuera=[ex_in, ex_out], azar_p95=p95,
                   criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
                   criterio='docs/p89_sentimiento_michigan_criterio.md (ba7872b)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
