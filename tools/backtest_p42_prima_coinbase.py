"""
backtest_p42_prima_coinbase.py — P42: prima de Coinbase (BTC-USD vs BTCUSDT×USDT) → BTC perpetuo del día siguiente.

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja velas diarias públicas de Coinbase (sin clave) a
`.cache_p42/` y usa `.cache_p15/BTC.json` (Binance spot/perp/funding, ya bajado).
Criterio declarado ANTES de medir: docs/p42_prima_coinbase_criterio.md (cd321ec). Leer contra eso.

Uso:
    python tools/backtest_p42_prima_coinbase.py
"""
import datetime as dt
import json
import os
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p42')
P15 = os.path.join(ROOT, '.cache_p15', 'BTC.json')
DAY = 86400
COST = 0.0007
RES_FROM = dt.date(2024, 1, 1)
REPS_PLACEBO, REPS_CI, BLOCK, SEED = 1000, 5000, 5, 20261114
OUT = os.path.join(ROOT, 'docs', 'p42_prima_coinbase_resultado.json')
UA = {'User-Agent': 'research-script/1.0'}


def fetch_cb(product):
    path = os.path.join(CACHE, f'{product}.json')
    if os.path.exists(path):
        return json.load(open(path))
    os.makedirs(CACHE, exist_ok=True)
    out = {}
    end = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    start_all = dt.datetime(2019, 1, 1, tzinfo=dt.timezone.utc)
    while end > start_all:
        start = max(start_all, end - dt.timedelta(days=299))
        url = (f'https://api.exchange.coinbase.com/products/{product}/candles?granularity=86400'
               f'&start={start.isoformat()}&end={end.isoformat()}')
        rows = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        for r in rows:                                   # [time, low, high, open, close, volume]
            out[int(r[0])] = float(r[4])
        end = start
        time.sleep(0.4)
    json.dump(out, open(path, 'w'))
    return {str(k): v for k, v in out.items()}


def main():
    cb = {int(k): v for k, v in fetch_cb('BTC-USD').items()}
    us = {int(k): v for k, v in fetch_cb('USDT-USD').items()}
    d = json.load(open(P15))
    spot = {int(t) // 1000: p for t, p in d['spot']}
    perp = {int(t) // 1000: p for t, p in d['perp']}
    ft = np.array([t // 1000 for t, _ in d['funding']], dtype=np.int64)
    fr = np.array([r for _, r in d['funding']], dtype=float)

    days = sorted(t for t in cb if t in us and (t + DAY) in spot)
    prem = {t: cb[t] / (spot[t + DAY] * us[t]) - 1 for t in days}
    tlist = sorted(prem)

    def day_ret(t0, h=0):
        """retorno del perpetuo y funding entre t0+h y t0+h+1 día (t0 = 00:00 UTC del día de entrada)."""
        a, b = perp.get(t0 + h), perp.get(t0 + h + DAY)
        if a is None or b is None:
            return None
        m = (ft > t0 + h) & (ft <= t0 + h + DAY)
        return b / a - 1, float(fr[m].sum())

    t0, t1 = tlist[0], tlist[-1]
    grid = list(range(t0, t1 + DAY, DAY))

    def positions(pr):
        arr = np.array([pr.get(t, np.nan) for t in grid])
        pos = {}
        for i, t in enumerate(grid):
            if t not in pr:
                continue
            w = arr[max(0, i - 365):i]
            w = w[~np.isnan(w)]
            if w.size < 300:
                continue
            lo, hi = np.percentile(w, [100 / 3, 200 / 3])
            pos[t + DAY] = 1 if pr[t] > hi else (-1 if pr[t] < lo else 0)   # entra a las 00:00 de d+1
        return pos

    def pnl(pos, h=0):
        rows, prev = [], 0
        for t in sorted(pos):
            r = day_ret(t, h)
            if r is None:
                prev = 0
                continue
            p = pos[t]
            net = p * r[0] - p * r[1] - COST * abs(p - prev)
            prev = p
            if p != 0:
                rows.append((t, net))
        return rows

    pos = positions(prem)
    rows = pnl(pos)
    dsc = np.array([x for t, x in rows if dt.datetime.fromtimestamp(t, dt.timezone.utc).date() < RES_FROM])
    res = np.array([x for t, x in rows if dt.datetime.fromtimestamp(t, dt.timezone.utc).date() >= RES_FROM])
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(res.size / BLOCK))
    bs = []
    for _ in range(REPS_CI):
        st = rng.integers(0, res.size - BLOCK + 1, nb)
        bs.append(np.concatenate([res[s:s + BLOCK] for s in st])[:res.size].mean())
    lo, hi = np.percentile(bs, [2.5, 97.5]) * 100
    # placebo: serie de prima desplazada circularmente
    vals = np.array([prem[t] for t in tlist])
    pl = []
    for _ in range(REPS_PLACEBO):
        k = int(rng.integers(30, len(vals) - 30))
        sh = dict(zip(tlist, np.roll(vals, k)))
        r2 = [x for t, x in pnl(positions(sh)) if dt.datetime.fromtimestamp(t, dt.timezone.utc).date() >= RES_FROM]
        pl.append(np.mean(r2) if r2 else 0.0)
    p95 = float(np.percentile(pl, 95)) * 100
    half = res.size // 2
    m = float(res.mean()) * 100
    c = [res.size >= 300, bool(m > 0 and lo > 0), bool(dsc.size and dsc.mean() > 0), m > p95,
         bool(res[:half].mean() > 0 and res[half:].mean() > 0)]

    # descriptivo
    def spear(a, b):
        ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])
    same, nxt, pv = [], [], []
    for t in tlist:
        r0 = day_ret(t)            # mismo día d (00:00 d -> 00:00 d+1)
        r1 = day_ret(t + DAY)      # día siguiente
        if r0 and r1:
            pv.append(prem[t]); same.append(r0[0]); nxt.append(r1[0])
    by_year = {}
    for t, x in rows:
        by_year.setdefault(str(dt.datetime.fromtimestamp(t, dt.timezone.utc).year), []).append(x)
    side = {}
    for t, x in rows:
        if dt.datetime.fromtimestamp(t, dt.timezone.utc).date() >= RES_FROM:
            side.setdefault('largo' if pos[t] == 1 else 'corto', []).append(x)
    r8 = [x for t, x in pnl(pos, h=8 * 3600) if dt.datetime.fromtimestamp(t, dt.timezone.utc).date() >= RES_FROM]
    o = dict(
        primer_dia_prima=str(dt.datetime.fromtimestamp(tlist[0], dt.timezone.utc).date()),
        reserva=dict(n=int(res.size), mean_pct=m, ci95=[float(lo), float(hi)],
                     mitades=[float(res[:half].mean()) * 100, float(res[half:].mean()) * 100]),
        descubrimiento=dict(n=int(dsc.size), mean_pct=float(dsc.mean()) * 100 if dsc.size else None),
        placebo_p95=p95, criterios=c, pasa=all(c),
        descriptivo=dict(
            spearman_mismo_dia=spear(pv, same), spearman_dia_siguiente=spear(pv, nxt), n_spear=len(pv),
            prima_mediana_pct=float(np.median(vals)) * 100,
            reserva_por_lado={k: dict(n=len(v), mean_pct=float(np.mean(v)) * 100) for k, v in side.items()},
            por_anio={y: dict(n=len(v), mean_pct=round(float(np.mean(v)) * 100, 3)) for y, v in sorted(by_year.items())},
            reserva_entrada_0800=dict(n=len(r8), mean_pct=float(np.mean(r8)) * 100 if r8 else None)))
    print(json.dumps(o, indent=1))
    json.dump(o, open(OUT, 'w'), indent=1)


if __name__ == '__main__':
    main()
