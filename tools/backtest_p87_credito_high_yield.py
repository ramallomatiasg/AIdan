"""P87 — Premio de crédito high yield: VWEHX contra VFITX (Vanguard), mensual.

Criterio declarado antes de medir: docs/p87_credito_high_yield_criterio.md (a93d1fd).
Read-only: sin MT5, no toca la DB. Datos: .cache_p87/*.json (Yahoo ajustado) y .cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p87_credito_high_yield.py              # 1992 -> 2008
  python tools/backtest_p87_credito_high_yield.py --reserved   # 2009 -> oct-2026, solo si pasó
"""
import argparse, bisect, datetime as dt, json, os, sys
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p87')
DTB3 = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p87_credito_high_yield_resultado.json')
BOOT, SEED, BLK = 5000, 20261127, 6
DISC = ('1992-01', '2008-12'); RES = ('2009-01', '2026-10')


def months():
    px = {s: json.load(open(os.path.join(C, f'{s}.json'))) for s in ['VWEHX', 'VFITX', 'VFINX']}
    days = sorted(set.intersection(*[set(v) for v in px.values()]))
    ds = [dt.date.fromisoformat(d) for d in days]
    P = np.array([[px[s][d] for s in ['VWEHX', 'VFITX', 'VFINX']] for d in days])
    t = json.load(open(DTB3)); tk = sorted(k for k in t if t[k] not in (None, '', '.'))
    tdays = [dt.date.fromisoformat(k) for k in tk]; tv = [float(t[k]) / 100 for k in tk]
    rf = np.array([tv[bisect.bisect_right(tdays, x) - 1] / 252 for x in ds])
    ends = [i for i in range(len(ds)) if i == len(ds) - 1 or ds[i + 1].month != ds[i].month]
    out = []
    for a, b in zip(ends[:-1], ends[1:]):
        g = P[b] / P[a] - 1
        out.append((ds[b].strftime('%Y-%m'), g[0], g[1], g[2], float(np.prod(1 + rf[a + 1:b + 1]) - 1)))
    return out


def mdd(x):
    eq = np.cumprod(1 + x); return float((eq / np.maximum.accumulate(eq) - 1).min())


def ann(x):
    return float(np.prod(1 + x) ** (12 / x.size) - 1)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--reserved', action='store_true'); a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    lo, hi = RES if a.reserved else DISC
    rows = [r for r in months() if lo <= r[0] <= hi]
    ms = [r[0] for r in rows]; n = len(ms); h = n // 2
    H, G, E, T = (np.array([r[k] for r in rows]) for k in (1, 2, 3, 4))
    X = H - G
    rng = np.random.default_rng(SEED); nb = int(np.ceil(n / BLK)); st = np.arange(0, n - BLK + 1)
    bs = np.sort([X[np.concatenate([np.arange(s, s + BLK) for s in rng.choice(st, nb)])[:n]].mean()
                  for _ in range(BOOT)])
    ci = (float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]))
    m1, m2 = float(X[:h].mean()), float(X[h:].mean())
    A = np.vstack([np.ones(n), E - T, G - T]).T
    coef = np.linalg.lstsq(A, H - T, rcond=None)[0]
    sh = float(X.mean() / X.std(ddof=1) * np.sqrt(12))
    corr = float(np.corrcoef(H - T, E - T)[0, 1])
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P87 high yield − Tesoro {tag}: {n} meses ({ms[0]} -> {ms[-1]})')
    print(f'  exceso medio {X.mean():+.3%}/mes ({X.mean()*12:+.2%}/año)  CI95 [{ci[0]:+.3%}, {ci[1]:+.3%}]  mitades '
          f'{m1:+.3%} / {m2:+.3%}  Sharpe del exceso {sh:.2f}  caída máx del exceso {mdd(X):+.1%}')
    print(f'  alfa {coef[0]*12:+.2%}/año  beta acciones {coef[1]:.2f}  beta Tesoro {coef[2]:.2f}  correlación con VFINX {corr:.2f}')
    print(f'  anual VWEHX {ann(H):+.2%} (caída máx {mdd(H):+.1%}) | VFITX {ann(G):+.2%} | VFINX {ann(E):+.2%} '
          f'(caída máx {mdd(E):+.1%}) | letra {ann(T):+.2%}')
    dec = {}
    for m, x in zip(ms, X):
        dec.setdefault(m[:3] + '0s', []).append(x)
    print('  exceso anual por década: ' + '  '.join(f'{k} {np.mean(v)*12:+.2%}' for k, v in sorted(dec.items())))
    if a.reserved:
        crit = {'1_exceso>0': X.mean() > 0, '2_CI_inf>0': ci[0] > 0}
    else:
        crit = {'1_exceso>0': X.mean() > 0, '2_CI_inf>0': ci[0] > 0, '3_dos_mitades>0': m1 > 0 and m2 > 0,
                '4_alfa>0': coef[0] > 0}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P87 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(meses=n, exceso_mensual=float(X.mean()), ci=list(ci), mitades=[m1, m2], alfa_anual=float(coef[0] * 12),
                   betas=[float(coef[1]), float(coef[2])], corr_vfinx=corr, criterios={k: bool(v) for k, v in crit.items()},
                   PASA=ok, criterio='docs/p87_credito_high_yield_criterio.md (a93d1fd)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
