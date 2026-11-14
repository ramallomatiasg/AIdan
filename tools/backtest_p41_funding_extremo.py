"""
backtest_p41_funding_extremo.py — P41: funding extremo como señal contraria (BTC/ETH perpetuo, Binance).

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Lee `.cache_p15/` (ya bajado en P15).
Criterio declarado ANTES de medir: docs/p41_funding_extremo_criterio.md (52fba65). Leer contra eso.

Uso:
    python tools/backtest_p41_funding_extremo.py              # BTC+ETH (decide)
    python tools/backtest_p41_funding_extremo.py --reserved   # ADA/LINK/LTC/AVAX: solo si el principal PASÓ
"""
import argparse
import datetime as dt
import json
import os

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p15')
MAIN = ['BTC', 'ETH']
RESERVED = ['ADA', 'LINK', 'LTC', 'AVAX']
DAY = 86400000
HOLD = 7 * DAY
COST = 0.0007
DISC_FROM = dt.date(2020, 1, 1)
RES_FROM = dt.date(2023, 1, 1)
REPS_PLACEBO, REPS_CI, SEED = 2000, 5000, 20261114
OUT = os.path.join(ROOT, 'docs', 'p41_funding_extremo_resultado.json')


def d_of(t):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date()


def load(sym):
    d = json.load(open(os.path.join(CACHE, f'{sym}.json')))
    perp = {int(t): p for t, p in d['perp']}
    ft = np.array([t for t, _ in d['funding']], dtype=np.int64)
    fr = np.array([r for _, r in d['funding']], dtype=float)
    return perp, ft, fr


def trade(perp, ft, fr, t, side):
    """side +1 largo / -1 corto. Retorno neto % de una operación de 7 días entrando a las 00:00 de t."""
    p0, p1 = perp.get(t), perp.get(t + HOLD)
    if p0 is None or p1 is None:
        return None
    m = (ft > t) & (ft <= t + HOLD)
    fund = float(fr[m].sum())
    price = side * (p1 / p0 - 1)
    return dict(net=price - side * fund - 2 * COST, price=price, fund=-side * fund)


def days(perp):
    ts = sorted(t for t in perp if t % DAY == 0)
    return ts


def signals(sym):
    perp, ft, fr = load(sym)
    ts = days(perp)
    f3 = {}
    for t in ts:
        m = (ft > t - 3 * DAY) & (ft <= t)
        if m.sum() >= 8:
            f3[t] = float(fr[m].mean())
    out = []                      # (t, side) para cada día con señal, sin control de superposición
    for t in ts:
        if t not in f3:
            continue
        hist = [f3[u] for u in range(t - 365 * DAY, t, DAY) if u in f3]
        if len(hist) < 300:
            continue
        hi, lo = np.percentile(hist, 90), np.percentile(hist, 10)
        side = -1 if f3[t] > hi else (1 if f3[t] < lo else 0)
        out.append((t, side))
    return perp, ft, fr, out


def run_coin(sym):
    perp, ft, fr, sig = signals(sym)
    trades, busy_until = [], 0
    for t, side in sig:
        if side == 0 or t < busy_until:
            continue
        r = trade(perp, ft, fr, t, side)
        if r is None:
            continue
        r.update(sym=sym, t=t, side=side, date=str(d_of(t)))
        trades.append(r)
        busy_until = t + HOLD
    valid_days = [t for t, _ in sig if trade(perp, ft, fr, t, 1) is not None]
    return trades, valid_days, (perp, ft, fr), len([1 for _, s in sig if s != 0]) / max(1, len(sig))


def summ(xs):
    a = np.array([x['net'] for x in xs])
    return dict(n=int(a.size), mean=float(a.mean()) * 100 if a.size else None,
                win=float((a > 0).mean()) if a.size else None)


def ci(a, rng):
    a = np.asarray(a)
    b = rng.choice(a, size=(REPS_CI, a.size), replace=True).mean(1)
    return float(np.percentile(b, 2.5)) * 100, float(np.percentile(b, 97.5)) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    args = ap.parse_args()
    syms = MAIN
    if args.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('pasa'):
            raise SystemExit('El principal no PASÓ: los reservados no se miran.')
        syms = RESERVED
    rng = np.random.default_rng(SEED)
    all_tr, per = [], {}
    for s in syms:
        tr, vdays, data, frac = run_coin(s)
        per[s] = dict(tr=tr, vdays=vdays, data=data, frac=frac)
        all_tr += tr
    disc = [x for x in all_tr if DISC_FROM <= d_of(x['t']) < RES_FROM]
    res = [x for x in all_tr if d_of(x['t']) >= RES_FROM]
    # placebo: mismas cantidades por moneda y lado, días al azar de la reserva
    pl = []
    for _ in range(REPS_PLACEBO):
        nets = []
        for s in syms:
            perp, ft, fr = per[s]['data']
            pool = [t for t in per[s]['vdays'] if d_of(t) >= RES_FROM]
            for side in (-1, 1):
                k = sum(1 for x in res if x['sym'] == s and x['side'] == side)
                for t in rng.choice(pool, size=k, replace=True) if k else []:
                    nets.append(trade(perp, ft, fr, int(t), side)['net'])
        pl.append(np.mean(nets) if nets else 0.0)
    p95 = float(np.percentile(pl, 95)) * 100
    S = summ(res)
    D = summ(disc)
    lo, hi = ci([x['net'] for x in res], rng) if res else (None, None)
    short_res = summ([x for x in res if x['side'] == -1])
    long_res = summ([x for x in res if x['side'] == 1])
    c = [S['n'] >= 30, bool(S['mean'] and S['mean'] > 0 and lo > 0), bool(D['mean'] and D['mean'] > 0),
         bool(S['mean'] is not None and S['mean'] > p95), bool(short_res['mean'] and short_res['mean'] > 0)]
    by_year = {}
    for x in all_tr:
        by_year.setdefault(x['date'][:4], []).append(x['net'])
    desc = dict(
        por_moneda={s: dict(reserva=summ([x for x in res if x['sym'] == s]),
                            desc=summ([x for x in disc if x['sym'] == s]),
                            frac_dias_senal=round(per[s]['frac'], 3)) for s in syms},
        por_lado=dict(reserva_corto=short_res, reserva_largo=long_res,
                      desc_corto=summ([x for x in disc if x['side'] == -1]),
                      desc_largo=summ([x for x in disc if x['side'] == 1])),
        por_anio={y: dict(n=len(v), mean=round(float(np.mean(v)) * 100, 3)) for y, v in sorted(by_year.items())},
        reserva_precio_pct=float(np.mean([x['price'] for x in res])) * 100 if res else None,
        reserva_funding_pct=float(np.mean([x['fund'] for x in res])) * 100 if res else None,
    )
    o = dict(syms=syms, reserva=S, ci95=[lo, hi], descubrimiento=D, placebo_p95=p95,
             criterios=c, pasa=all(c), descriptivo=desc)
    print(json.dumps(o, indent=1, default=str))
    if not args.reserved:
        json.dump(o, open(OUT, 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
