"""P88 — Vender puts cubiertos del S&P 500 (índice CBOE PutWrite ^PUT) contra SPY, mensual.

Criterio declarado antes de medir: docs/p88_puts_sp500_criterio.md (f5b2611).
Read-only: sin MT5, no toca la DB. Datos: .cache_p88/*.json (Yahoo) y .cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p88_puts_sp500.py              # 1997 -> 2010
  python tools/backtest_p88_puts_sp500.py --reserved   # 2011 -> oct-2026, solo si pasó
"""
import argparse, bisect, datetime as dt, json, os, sys
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p88')
DTB3 = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p88_puts_sp500_resultado.json')
COST, PESS = 0.0005, 0.0015
BOOT, SEED, BLK = 5000, 20261127, 6
DISC = ('1997-01', '2010-12'); RES = ('2011-01', '2026-10')


def months():
    px = {s: json.load(open(os.path.join(C, f'{s}.json'))) for s in ['^PUT', 'SPY']}
    days = sorted(set(px['^PUT']) & set(px['SPY']))
    ds = [dt.date.fromisoformat(d) for d in days]
    P = np.array([[px['^PUT'][d], px['SPY'][d]] for d in days])
    t = json.load(open(DTB3)); tk = sorted(k for k in t if t[k] not in (None, '', '.'))
    tdays = [dt.date.fromisoformat(k) for k in tk]; tv = [float(t[k]) / 100 for k in tk]
    rf = np.array([tv[bisect.bisect_right(tdays, x) - 1] / 252 for x in ds])
    ends = [i for i in range(len(ds)) if i == len(ds) - 1 or ds[i + 1].month != ds[i].month]
    out = []
    for a, b in zip(ends[:-1], ends[1:]):
        g = P[b] / P[a] - 1
        out.append((ds[b].strftime('%Y-%m'), g[0], g[1], float(np.prod(1 + rf[a + 1:b + 1]) - 1)))
    return out


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
    rows = [r for r in months() if lo <= r[0] <= hi]
    ms = [r[0] for r in rows]; n = len(ms); h = n // 2
    U0, S, T = (np.array([r[k] for r in rows]) for k in (1, 2, 3))
    U, UP = U0 - COST, U0 - PESS
    xu, xs, xp = U - T, S - T, UP - T
    d = sharpe(xu) - sharpe(xs); dp = sharpe(xp) - sharpe(xs)
    d1 = sharpe(xu[:h]) - sharpe(xs[:h]); d2 = sharpe(xu[h:]) - sharpe(xs[h:])
    rng = np.random.default_rng(SEED); nb = int(np.ceil(n / BLK)); st = np.arange(0, n - BLK + 1)
    bd, bm = [], []
    for _ in range(BOOT):
        ix = np.concatenate([np.arange(s, s + BLK) for s in rng.choice(st, nb)])[:n]
        bd.append(sharpe(xu[ix]) - sharpe(xs[ix])); bm.append(xu[ix].mean())
    bd, bm = np.sort(bd), np.sort(bm)
    ci = (float(bd[int(.025 * BOOT)]), float(bd[int(.975 * BOOT)]))
    cim = (float(bm[int(.025 * BOOT)]), float(bm[int(.975 * BOOT)]))
    B = np.vstack([np.ones(n), xs]).T; coef = np.linalg.lstsq(B, xu, rcond=None)[0]
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P88 vender puts del S&P 500 (^PUT) {tag}: {n} meses ({ms[0]} -> {ms[-1]})')
    print(f'  Sharpe PUT {sharpe(xu):.3f} vs SPY {sharpe(xs):.3f}  diferencia {d:+.3f}  CI95 [{ci[0]:+.3f}, {ci[1]:+.3f}]  '
          f'mitades {d1:+.3f} / {d2:+.3f}  pesimista {dp:+.3f}')
    print(f'  exceso de PUT sobre la letra {xu.mean()*12:+.2%}/año  CI95 mensual [{cim[0]:+.3%}, {cim[1]:+.3%}]')
    print(f'  anual PUT {ann(U):+.2%} (vol {U.std(ddof=1)*np.sqrt(12):.1%}, caída máx {mdd(U):+.1%}, peor mes {U.min():+.1%}) '
          f'| SPY {ann(S):+.2%} (vol {S.std(ddof=1)*np.sqrt(12):.1%}, caída máx {mdd(S):+.1%}, peor mes {S.min():+.1%}) '
          f'| letra {ann(T):+.2%}')
    print(f'  alfa {coef[0]*12:+.2%}/año  beta {coef[1]:.2f}')
    dec = {}
    for m, u, v in zip(ms, xu, xs):
        dec.setdefault(m[:3] + '0s', [[], []]); dec[m[:3] + '0s'][0].append(u); dec[m[:3] + '0s'][1].append(v)
    print('  diferencia de Sharpe por década: ' + '  '.join(
        f'{k} {sharpe(np.array(v[0])) - sharpe(np.array(v[1])):+.2f}' for k, v in sorted(dec.items())))
    if a.reserved:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '5_exceso_CI_inf>0': cim[0] > 0}
    else:
        crit = {'1_dif_sharpe>0': d > 0, '2_CI_inf>0': ci[0] > 0, '3_dos_mitades>0': d1 > 0 and d2 > 0,
                '4_pesimista>0': dp > 0, '5_exceso_CI_inf>0': cim[0] > 0, '6_caida_max<=SPY': mdd(U) >= mdd(S)}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P88 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(meses=n, dif_sharpe=d, ci=list(ci), mitades=[d1, d2], pesimista=dp, exceso_anual=float(xu.mean() * 12),
                   ci_exceso_mensual=list(cim), caida_max=[mdd(U), mdd(S)], alfa_anual=float(coef[0] * 12),
                   beta=float(coef[1]), criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
                   criterio='docs/p88_puts_sp500_criterio.md (f5b2611)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
