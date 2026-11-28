"""P86 — Beta baja en los 9 SPDR sectoriales (Frazzini & Pedersen 2014) contra SPY.

Criterio declarado antes de medir: docs/p86_beta_baja_sectores_criterio.md (f6b3f92).
Read-only: sin MT5, no toca la DB. Datos: .cache_p86/*.json (Yahoo ajustado) y .cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p86_beta_baja_sectores.py              # 2000 -> 2012
  python tools/backtest_p86_beta_baja_sectores.py --reserved   # 2013 -> oct-2026, solo si pasó
"""
import argparse, bisect, datetime as dt, json, os, sys
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p86')
DTB3 = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p86_beta_baja_sectores_resultado.json')
SEC = ['XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY']
COST, PESS = 0.0005, 0.0010
BOOT, SEED, BLK, NPLAC = 5000, 20261127, 6, 1000
DISC = ('2000-01', '2012-12'); RES = ('2013-01', '2026-10')


def load():
    px = {s: json.load(open(os.path.join(C, f'{s}.json'))) for s in SEC + ['SPY']}
    days = sorted(set.intersection(*[set(v) for v in px.values()]))
    P = np.array([[px[s][d] for s in SEC + ['SPY']] for d in days])
    ds = [dt.date.fromisoformat(d) for d in days]
    t = json.load(open(DTB3)); tk = sorted(k for k in t if t[k] not in (None, '', '.'))
    tdays = [dt.date.fromisoformat(k) for k in tk]; tv = [float(t[k]) / 100 for k in tk]
    rf = np.array([tv[bisect.bisect_right(tdays, x) - 1] / 252 for x in ds])
    return ds, P, rf


def monthly(ds, P, rf):
    r = P[1:] / P[:-1] - 1
    ends = [i for i in range(len(ds)) if i == len(ds) - 1 or ds[i + 1].month != ds[i].month]
    rows = []  # (mes, betas al fin del mes previo, retornos del mes por activo, letra del mes)
    for a, b in zip(ends[:-1], ends[1:]):
        if a < 252:
            continue
        w = r[a - 252:a]               # retornos que terminan en el cierre de a
        spy = w[:, -1]
        beta = np.array([np.cov(w[:, k], spy)[0, 1] / spy.var(ddof=1) for k in range(len(SEC))])
        g = np.prod(1 + r[a:b], axis=0) - 1
        t = np.prod(1 + rf[a + 1:b + 1]) - 1
        rows.append((ds[b].strftime('%Y-%m'), beta, g, t))
    return rows


def run(rows, pick, cost):
    out, wprev = [], None
    for m, beta, g, t in rows:
        idx = pick(beta)
        w = np.zeros(len(SEC)); w[idx] = 1 / len(idx)
        turn = np.abs(w - wprev).sum() if wprev is not None else 1.0
        rp = float(w @ g[:len(SEC)])
        out.append(rp - cost * turn)
        wprev = w * (1 + g[:len(SEC)]) / (1 + rp)
    return np.array(out)


def sharpe(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(12))


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
    ds, P, rf = load()
    rows = [x for x in monthly(ds, P, rf) if lo <= x[0] <= hi]
    ms = [x[0] for x in rows]; n = len(ms); h = n // 2
    low3 = lambda b: np.argsort(b)[:3]
    L = run(rows, low3, COST); LP = run(rows, low3, PESS)
    S = np.array([x[2][-1] for x in rows]); T = np.array([x[3] for x in rows])
    EW = np.array([x[2][:len(SEC)].mean() for x in rows])
    xl, xs, xp = L - T, S - T, LP - T
    d = sharpe(xl) - sharpe(xs); dp = sharpe(xp) - sharpe(xs)
    d1 = sharpe(xl[:h]) - sharpe(xs[:h]); d2 = sharpe(xl[h:]) - sharpe(xs[h:])
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLK)); st = np.arange(0, n - BLK + 1); bs = []
    for _ in range(BOOT):
        ix = np.concatenate([np.arange(s, s + BLK) for s in rng.choice(st, nb)])[:n]
        bs.append(sharpe(xl[ix]) - sharpe(xs[ix]))
    bs = np.sort(bs); ci = (float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]))
    pl = np.sort([sharpe(run(rows, lambda b: rng.choice(len(SEC), 3, replace=False), COST) - T) for _ in range(NPLAC)])
    p95 = float(pl[int(.95 * NPLAC)])
    B = np.vstack([np.ones(n), xs]).T; coef = np.linalg.lstsq(B, xl, rcond=None)[0]
    cnt = {}
    for x in rows:
        for k in low3(x[1]):
            cnt[SEC[k]] = cnt.get(SEC[k], 0) + 1
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P86 beta baja en sectores {tag}: {n} meses ({ms[0]} -> {ms[-1]})')
    print(f'  Sharpe beta baja {sharpe(xl):.3f} vs SPY {sharpe(xs):.3f}  diferencia {d:+.3f}  CI95 [{ci[0]:+.3f}, '
          f'{ci[1]:+.3f}]  mitades {d1:+.3f} / {d2:+.3f}  pesimista {dp:+.3f}  azar p95 {p95:.3f}')
    print(f'  anual beta baja {ann(L):+.2%} (vol {L.std(ddof=1)*np.sqrt(12):.1%}, caída máx {mdd(L):+.1%}) | SPY '
          f'{ann(S):+.2%} (vol {S.std(ddof=1)*np.sqrt(12):.1%}, caída máx {mdd(S):+.1%}) | 9 a peso igual {ann(EW):+.2%} '
          f'(Sharpe {sharpe(EW - T):.3f}) | letra {ann(T):+.2%}')
    print(f'  alfa {coef[0]*12:+.2%}/año, beta {coef[1]:.2f} | veces elegido: ' +
          ' '.join(f'{k} {v}' for k, v in sorted(cnt.items(), key=lambda z: -z[1])))
    dec = {}
    for m, u, v in zip(ms, xl, xs):
        dec.setdefault(m[:3] + '0s', [[], []]); dec[m[:3] + '0s'][0].append(u); dec[m[:3] + '0s'][1].append(v)
    print('  diferencia de Sharpe por década: ' + '  '.join(
        f'{k} {sharpe(np.array(v[0])) - sharpe(np.array(v[1])):+.2f}' for k, v in sorted(dec.items())))
    if a.reserved:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0}
    else:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '3_dos_mitades>0': d1 > 0 and d2 > 0,
                '4_pesimista>0': dp > 0, '5_supera_azar_p95': sharpe(xl) > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P86 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(meses=n, dif_sharpe=d, ci=list(ci), mitades=[d1, d2], pesimista=dp, azar_p95=p95,
                   alfa_anual=float(coef[0] * 12), beta=float(coef[1]), criterios={k: bool(v) for k, v in crit.items()},
                   PASA=ok, criterio='docs/p86_beta_baja_sectores_criterio.md (f6b3f92)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
