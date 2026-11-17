"""P50 — préstamo de USDC/USDT en Aave v3 contra la letra del Tesoro a 3 meses.

Criterio declarado antes de medir: docs/p50_prestamo_stablecoins_criterio.md (2cbfe52).
Read-only: sin MT5, no toca la DB. Datos públicos (DefiLlama, FRED) a .cache_p50/.

  python tools/backtest_p50_prestamo_stablecoins.py              # descubrimiento (feb → dic 2023)
  python tools/backtest_p50_prestamo_stablecoins.py --reserved   # 2024 →, solo si pasó
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p50')
POOLS = {'USDC': 'aa70268e-4b52-42bf-a116-608b370f9501', 'USDT': 'f981a304-bb6c-45b8-b0c5-fd2f515ad23a'}
COINS = {'USDC': 'coingecko:usd-coin', 'USDT': 'coingecko:tether'}
D0, SPLIT, D1 = dt.date(2023, 2, 13), dt.date(2024, 1, 1), dt.date(2026, 11, 15)
GAS = 0.01
BLOCK, BOOT, SEED = 30, 5000, 20261116
OUT = os.path.join(ROOT, 'docs', 'p50_prestamo_stablecoins_resultado.json')


def _get(u, raw=False):
    for k in range(5):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60)
            return r.read().decode() if raw else json.load(r)
        except Exception:
            if k == 4:
                raise
            time.sleep(3 + 3 * k)


def cached(name, fn):
    p = os.path.join(C, name)
    if os.path.exists(p):
        return json.load(open(p))
    v = fn()
    json.dump(v, open(p, 'w'))
    return v


def load():
    os.makedirs(C, exist_ok=True)
    apy = {}
    for s, pid in POOLS.items():
        d = cached(f'{pid}.json', lambda pid=pid: _get(f'https://yields.llama.fi/chart/{pid}')['data'])
        apy[s] = {x['timestamp'][:10]: float(x['apyBase'] or 0) for x in d}

    def fred():
        txt = _get('https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3', raw=True)
        return {r['observation_date']: float(r['DTB3']) for r in csv.DictReader(io.StringIO(txt)) if r['DTB3']}
    tb = cached('dtb3.json', fred)

    def coin(c):
        out, t = {}, int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        while t < time.time():
            for q in _get(f'https://coins.llama.fi/chart/{c}?start={t}&span=300&period=1d')['coins'][c]['prices']:
                out[dt.datetime.utcfromtimestamp(q['timestamp']).strftime('%Y-%m-%d')] = q['price']
            t += 300 * 86400
        return out
    px = {s: cached(f'px_{s}.json', lambda c=c: coin(c)) for s, c in COINS.items()}
    return apy, tb, px


def ffill(d, days):
    out, last = [], None
    for k in days:
        last = d.get(k, last)
        out.append(np.nan if last is None else last)
    return np.array(out, dtype=float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    apy, tb, px = load()
    lo_d, hi_d = (SPLIT, D1) if a.reserved else (D0, SPLIT - dt.timedelta(days=1))
    days = [(lo_d + dt.timedelta(days=i)).isoformat() for i in range((hi_d - lo_d).days + 1)]
    bill = ffill(tb, days) / 100
    per, prem_each, value = {}, [], np.zeros(len(days))
    for s in POOLS:
        y = ffill(apy[s], days) / 100
        p = ffill(px[s], days)
        prem = (y - bill - GAS) / 365
        prem_each.append(prem)
        bal = np.cumprod(1 + y / 365)
        value += 0.5 * bal * p
        per[s] = dict(apy_media=float(np.nanmean(y)), premio_anual=float(np.nanmean(prem) * 365),
                      sin_gas=float(np.nanmean(prem + GAS / 365) * 365), precio_min=float(np.nanmin(p)),
                      dia_precio_min=days[int(np.nanargmin(p))])
    prem = np.nanmean(prem_each, axis=0)
    ann = float(prem.mean() * 365)
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(prem.size / BLOCK))
    st = rng.integers(0, prem.size - BLOCK, (BOOT, nb))
    idx = (st[:, :, None] + np.arange(BLOCK)).reshape(BOOT, -1)[:, :prem.size]
    bs = np.sort(prem[idx].mean(axis=1)) * 365
    lo, hi = float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])
    h = prem.size // 2
    h1, h2 = float(prem[:h].mean() * 365), float(prem[h:].mean() * 365)
    v = value[~np.isnan(value)]                          # días sin precio al arranque
    dd = float(np.max(1 - v / np.maximum.accumulate(v)))
    print(f"  {'RESERVA' if a.reserved else 'DESCUBRIMIENTO'} {days[0]} → {days[-1]}  letra media {bill.mean():.2%}")
    for s, v in per.items():
        print(f"    {s}: APY media {v['apy_media']:.2%}  premio neto {v['premio_anual']:+.2%}/año (sin gas "
              f"{v['sin_gas']:+.2%})  precio mín {v['precio_min']:.4f} el {v['dia_precio_min']}")
    print(f"  cartera 50/50: premio neto {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx en USD {dd:.2%}")
    years = {}
    for k, d_ in enumerate(days):
        years.setdefault(d_[:4], []).append(prem[k])
    print('    por año: ' + '  '.join(f'{y} {np.mean(v) * 365:+.2%}' for y, v in sorted(years.items())))
    if a.reserved:
        crit = {'reserva_premio>0': ann > 0}
    else:
        crit = {'1_premio>0': ann > 0, '2_CI_inf>0': lo > 0, '3_dos_mitades>0': h1 > 0 and h2 > 0,
                '4_caida_max_USD<15%': dd < 0.15}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f"  >>> P50 {'reserva' if a.reserved else ''}: {'PASA' if ok else 'NO PASA'}")
    res = dict(por_moneda=per, premio_anual=ann, ci=[lo, hi], mitades=[h1, h2], caida_max_usd=dd,
               letra_media=float(bill.mean()), criterios=crit, PASA=ok,
               criterio='docs/p50_prestamo_stablecoins_criterio.md (2cbfe52)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
