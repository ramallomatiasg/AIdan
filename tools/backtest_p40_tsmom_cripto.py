"""
backtest_p40_tsmom_cripto.py — P40: largo semanal el perpetuo si el retorno de 4 semanas es > 0 (cripto, Binance).

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Lee `.cache_p15/` (ya bajado en P15).
Criterio declarado ANTES de medir: docs/p40_tsmom_cripto_criterio.md (d8110df). Leer contra eso.

Uso:
    python tools/backtest_p40_tsmom_cripto.py              # 6 principales (decide)
    python tools/backtest_p40_tsmom_cripto.py --reserved   # ADA/LINK/LTC/AVAX: solo si el principal PASÓ
"""
import argparse
import datetime as dt
import json
import os

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p15')
MAIN = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
RESERVED = ['ADA', 'LINK', 'LTC', 'AVAX']
DAY = 86400000
WEEK = 7 * DAY
LOOK = 28 * DAY
COST = 0.0007
RESERVE_FROM = dt.date(2023, 1, 2)
START = dt.datetime(2020, 1, 6, tzinfo=dt.timezone.utc)      # lunes
REPS, BLOCK, SEED = 2000, 4, 20261112
OUT = os.path.join(ROOT, 'docs', 'p40_tsmom_cripto_resultado.json')


def load(sym):
    d = json.load(open(os.path.join(CACHE, f'{sym}.json')))
    perp = {int(t): p for t, p in d['perp']}
    ft = np.array([t for t, _ in d['funding']], dtype=np.int64)
    fr = np.array([r for _, r in d['funding']], dtype=float)
    return perp, ft, fr


def coin_weeks(sym, mondays):
    perp, ft, fr = load(sym)
    rows = []
    for t in mondays:
        p0, pb, p1 = perp.get(t), perp.get(t - LOOK), perp.get(t + WEEK)
        if p0 is None or pb is None or p1 is None:
            rows.append(None)
            continue
        m = (ft > t) & (ft <= t + WEEK)
        rows.append(dict(sig=p0 / pb - 1 > 0, ret=p1 / p0 - 1, fund=float(fr[m].sum())))
    return rows


def portfolio(cw, pos):
    """cw: {sym: rows}, pos: {sym: array 0/1 por semana} -> retorno semanal neto de la cartera."""
    n = len(next(iter(cw.values())))
    out = np.full(n, np.nan)
    for i in range(n):
        acc, k = 0.0, 0
        for s, rows in cw.items():
            r = rows[i]
            if r is None:
                continue
            p = pos[s][i]
            prev = pos[s][i - 1] if i and rows[i - 1] is not None else 0
            acc += p * (r['ret'] - r['fund']) - COST * abs(p - prev)
            k += 1
        if k:
            out[i] = acc / k
    return out


def sharpe(x):
    x = x[~np.isnan(x)]
    return float(x.mean() / x.std() * np.sqrt(52)) if x.size > 2 and x.std() > 0 else 0.0


def block_ci(x, rng):
    x = x[~np.isnan(x)]
    nb = int(np.ceil(x.size / BLOCK))
    means = []
    for _ in range(5000):
        st = rng.integers(0, x.size - BLOCK + 1, nb)
        means.append(np.concatenate([x[s:s + BLOCK] for s in st])[:x.size].mean())
    means = np.sort(means)
    return float(means[125]), float(means[4874])


def run(syms):
    end = min(max(load(s)[0]) for s in syms[:1])
    mondays = []
    t = int(START.timestamp() * 1000)
    while t + WEEK <= end:
        mondays.append(t)
        t += WEEK
    dates = [dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date() for t in mondays]
    cw = {s: coin_weeks(s, mondays) for s in syms}
    rule = {s: np.array([1 if (r and r['sig']) else 0 for r in rows]) for s, rows in cw.items()}
    always = {s: np.array([1 if r else 0 for r in rows]) for s, rows in cw.items()}
    R, A = portfolio(cw, rule), portfolio(cw, always)
    res = np.array([d >= RESERVE_FROM for d in dates])
    rng = np.random.default_rng(SEED)
    lo, hi = block_ci(R[res], rng)
    # placebo: misma fracción de semanas largas por moneda, dentro de la reserva
    frac = {s: rule[s][res & (always[s] == 1)].mean() for s in syms}
    plac = []
    for _ in range(REPS):
        pos = {s: (rng.random(len(mondays)) < frac[s]).astype(int) * always[s] for s in syms}
        plac.append(sharpe(portfolio(cw, pos)[res]))
    p95 = float(np.sort(plac)[int(0.95 * REPS)])
    out = dict(weeks_res=int(np.sum(res & ~np.isnan(R))), mean_res=float(np.nanmean(R[res])), ci=[lo, hi],
               mean_desc=float(np.nanmean(R[~res])), sharpe_rule=sharpe(R[res]), sharpe_always=sharpe(A[res]),
               mean_always_res=float(np.nanmean(A[res])), sharpe_rule_desc=sharpe(R[~res]),
               sharpe_always_desc=sharpe(A[~res]), placebo_p95=p95,
               invested_frac={s: float(v) for s, v in frac.items()})
    cum = np.nancumsum(R[res])
    out['mdd_res'] = float(np.max(np.maximum.accumulate(cum) - cum))
    cumA = np.nancumsum(A[res])
    out['mdd_always_res'] = float(np.max(np.maximum.accumulate(cumA) - cumA))
    by = {}
    for d, x, a in zip(dates, R, A):
        if not np.isnan(x):
            by.setdefault(d.year, [[], []])
            by[d.year][0].append(x)
            by[d.year][1].append(a)
    out['by_year'] = {y: [float(np.mean(v[0])), float(np.mean(v[1]))] for y, v in sorted(by.items())}
    out['crit'] = {
        '1_n_reserva>=150': out['weeks_res'] >= 150,
        '2_media>0_CI_inf>0': out['mean_res'] > 0 and lo > 0,
        '3_desc>0': out['mean_desc'] > 0,
        '4_sharpe>siempre_largo': out['sharpe_rule'] > out['sharpe_always'],
        '5_sharpe>placebo_p95': out['sharpe_rule'] > p95,
    }
    out['PASA'] = all(out['crit'].values())
    return out


def show(o, label):
    print(f"{label}: reserva {o['weeks_res']} semanas  regla {o['mean_res']*100:+.3f}%/sem  CI [{o['ci'][0]*100:+.3f}, "
          f"{o['ci'][1]*100:+.3f}]  Sharpe {o['sharpe_rule']:.2f}  | siempre largo {o['mean_always_res']*100:+.3f}% "
          f"Sharpe {o['sharpe_always']:.2f}  | placebo p95 {o['placebo_p95']:.2f}")
    print(f"  descubrimiento: regla {o['mean_desc']*100:+.3f}%/sem Sharpe {o['sharpe_rule_desc']:.2f}  "
          f"(siempre largo Sharpe {o['sharpe_always_desc']:.2f})   caída máx reserva {o['mdd_res']*100:.0f}% vs "
          f"{o['mdd_always_res']*100:.0f}%")
    print('  por año (regla / siempre): ' + '  '.join(f"{y} {a*100:+.2f}/{b*100:+.2f}" for y, (a, b) in o['by_year'].items()))
    print('  fracción invertida: ' + ' '.join(f"{s} {v:.0%}" for s, v in o['invested_frac'].items()))
    for k, ok in o['crit'].items():
        print(f"    [{'OK ' if ok else 'NO '}] {k}")
    print(f">>> {'PASA' if o['PASA'] else 'NO PASA'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT))
        if not prev.get('PASA'):
            raise SystemExit('El principal no pasó: por criterio los reservados NO se miran.')
        o = run(RESERVED)
        show(o, 'reservados')
        prev['reservados'] = o
        json.dump(prev, open(OUT, 'w'), indent=1, default=str)
        return
    o = run(MAIN)
    show(o, 'principales')
    o['criterio'] = 'docs/p40_tsmom_cripto_criterio.md (d8110df)'
    json.dump(o, open(OUT, 'w'), indent=1, default=str)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
