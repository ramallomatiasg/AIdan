"""
backtest_p39_vrp_cripto.py — P39: vender volatilidad a 30 días de BTC cuando DVOL > realizada previa.

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja el DVOL público de Deribit a `.cache_p39/` y usa el spot
8 h de Binance de `.cache_p15/BTC.json`.
Criterio declarado ANTES de medir: docs/p39_vrp_cripto_criterio.md (f3d7dee). Leer contra eso.

Uso:
    python tools/backtest_p39_vrp_cripto.py            # BTC (decide)
    python tools/backtest_p39_vrp_cripto.py --eth      # fuera de muestra: solo si BTC PASÓ
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_p39')
END = dt.datetime(2026, 10, 31, tzinfo=dt.timezone.utc)
DAY = 86400000
H = 30
COST, COST_PESS = 2.0, 4.0
RESERVE_FROM = dt.date(2024, 1, 1)
OUT = os.path.join(ROOT, 'docs', 'p39_vrp_cripto_resultado.json')


def _get(url):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                return json.load(r)
        except Exception:
            if k == 4:
                raise
            time.sleep(2 + 3 * k)


def fetch_dvol(cur):
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, f'{cur}_dvol.json')
    if os.path.exists(fn):
        return json.load(open(fn))
    out, start, end = {}, int(dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000), \
        int(END.timestamp() * 1000)
    while start < end:
        stop = min(start + 900 * DAY, end)
        r = _get('https://www.deribit.com/api/v2/public/get_volatility_index_data?currency='
                 f'{cur}&start_timestamp={start}&end_timestamp={stop}&resolution=1D')['result']['data']
        for t, o, h, l, c in r:
            out[int(t)] = o          # apertura del día = valor a las 00:00 UTC (sin mirar el día)
        start = stop
        time.sleep(0.3)
    out = sorted(out.items())
    json.dump(out, open(fn, 'w'))
    return out


def run(cur, anchor_shift=0, verbose=False):
    dvol = {t: v for t, v in fetch_dvol(cur)}
    spot = json.load(open(os.path.join(ROOT, '.cache_p15', f'{cur}.json')))['spot']
    st = np.array([t for t, _ in spot], dtype=np.int64)
    sp = np.log(np.array([p for _, p in spot], dtype=float))
    r = np.diff(sp)
    rt = st[1:]

    def rv(a, b):                      # retornos con cierre en (a, b]
        m = (rt > a) & (rt <= b)
        if m.sum() < H * 3 - 3:
            return None
        return float(np.sqrt((r[m] ** 2).sum() * 365.0 / H))

    days = sorted(dvol)
    t = days[0] + anchor_shift * DAY
    trades = []
    while True:
        if t not in dvol:
            t += DAY
            if t > days[-1]:
                break
            continue
        prev, nxt = rv(t - H * DAY, t), rv(t, t + H * DAY)
        if nxt is None:
            if t + H * DAY > st[-1]:
                break
            t += H * DAY
            continue
        iv = dvol[t] / 100.0
        gross = (iv ** 2 - nxt ** 2) / (2 * iv) * 100
        d = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date()
        trades.append(dict(d=d, iv=iv * 100, rv_prev=None if prev is None else prev * 100, rv_next=nxt * 100,
                           sig=prev is not None and iv > prev, gross=gross))
        t += H * DAY
    return trades


def evaluate(cur):
    tr = run(cur)
    on = [x for x in tr if x['sig']]
    v = np.array([x['gross'] - COST for x in on])
    desc = np.array([x['gross'] - COST for x in on if x['d'] < RESERVE_FROM])
    res = np.array([x['gross'] - COST for x in on if x['d'] >= RESERVE_FROM])
    lo, hi, _ = bootstrap_ci(v)
    anchors = [np.mean([x['gross'] - COST for x in run(cur, s) if x['sig']]) for s in range(30)]
    allv = np.array([x['gross'] - COST for x in tr])
    cum = np.cumsum(v)
    mdd = float(np.max(np.maximum.accumulate(cum) - cum)) if v.size else 0.0
    print(f"{cur}: operaciones {len(tr)} ({tr[0]['d']} -> {tr[-1]['d']}), con señal {v.size}")
    print(f"  IV media {np.mean([x['iv'] for x in tr]):.1f}  RV siguiente media {np.mean([x['rv_next'] for x in tr]):.1f}")
    print(f"  con señal: neto {v.mean():+.2f} pts  mediana {np.median(v):+.2f}  ganadas {(v > 0).mean():.0%}  "
          f"CI [{lo:+.2f}, {hi:+.2f}]  peor {v.min():+.2f}  caída máx {mdd:.1f}")
    print(f"  descubrimiento n={desc.size} {desc.mean():+.2f}  |  reserva n={res.size} "
          f"{res.mean() if res.size else float('nan'):+.2f}")
    print(f"  anclas con media>0: {sum(a > 0 for a in anchors)}/30  (min {min(anchors):+.2f}, max {max(anchors):+.2f})")
    print(f"  [desc] vender siempre: n={allv.size} neto {allv.mean():+.2f}  pesimista con señal {v.mean() - 2:+.2f}")
    by = {}
    for x in on:
        by.setdefault(x['d'].year, []).append(x['gross'] - COST)
    print('  por año: ' + '  '.join(f"{y} {np.mean(z):+.1f} (n={len(z)})" for y, z in sorted(by.items())))
    crit = {
        '1_n_reserva>=15': bool(res.size >= 15),
        '2_media>0_CI_inf>0': bool(v.mean() > 0 and lo is not None and lo > 0),
        '3_desc_y_reserva>0': bool(desc.size and res.size and desc.mean() > 0 and res.mean() > 0),
        '4_anclas>=25/30': sum(a > 0 for a in anchors) >= 25,
        '5_>0_costo_pesimista': bool(v.mean() - (COST_PESS - COST) > 0),
    }
    for k, ok in crit.items():
        print(f"    [{'OK ' if ok else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    return dict(n=int(v.size), net=float(v.mean()), ci=[lo, hi], desc=[int(desc.size), float(desc.mean())],
                res=[int(res.size), float(res.mean()) if res.size else None], anchors_pos=int(sum(a > 0 for a in anchors)),
                worst=float(v.min()), mdd=mdd, always=float(allv.mean()),
                by_year={int(y): float(np.mean(z)) for y, z in by.items()}, criterios=crit, PASA=ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eth', action='store_true')
    a = ap.parse_args()
    if a.eth:
        prev = json.load(open(OUT))
        if not prev.get('PASA'):
            raise SystemExit('BTC no pasó: por criterio ETH NO se mira.')
        res = evaluate('ETH')
        prev['ETH_fuera_de_muestra'] = res
        json.dump(prev, open(OUT, 'w'), indent=1, default=str)
        return
    res = evaluate('BTC')
    res['criterio'] = 'docs/p39_vrp_cripto_criterio.md (f3d7dee)'
    json.dump(res, open(OUT, 'w'), indent=1, default=str)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
