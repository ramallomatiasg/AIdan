"""
backtest_p56_listados_nuevos.py — P56: corto de los perpetuos USDT recién listados en Binance, del día 2 al día 30.

READ-ONLY. Sin MT5, no toca la DB. Lista de símbolos: .cache_p56/exchangeInfo.json + s3_symbols.json; velas diarias y
funding públicos de fapi a .cache_p56/px/.
Criterio declarado ANTES de medir: docs/p56_listados_nuevos_criterio.md (54ebe1b). Leer contra eso.

    python tools/backtest_p56_listados_nuevos.py              # descubrimiento: altas 2023-2024
    python tools/backtest_p56_listados_nuevos.py --reserved   # altas 2025 → 20-ago-2026, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p56')
PX = os.path.join(C, 'px')
OUT = os.path.join(ROOT, 'docs', 'p56_listados_nuevos_resultado.json')
COST, PESS = 0.003, 0.006
BOOT, SEED = 5000, 20261118
D = 86400_000
T23 = int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
T25 = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
TEND = int(dt.datetime(2026, 8, 20, tzinfo=dt.timezone.utc).timestamp() * 1000)
INDEX_MISSING = {'FOOTBALLUSDT', 'BLUEBIRDUSDT'}


def _get(u):
    for k in range(5):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return None
            if k == 4:
                raise
        except Exception:
            if k == 4:
                raise
        time.sleep(2 + 2 * k)


def fetch(sym):
    os.makedirs(PX, exist_ok=True)
    q0 = urllib.parse.quote(sym, safe='')
    p = os.path.join(PX, f'{q0}.json')

    if os.path.exists(p):
        return json.load(open(p))
    q = urllib.parse.quote(sym)
    kl, t = [], 0
    while True:
        k = _get(f'https://fapi.binance.com/fapi/v1/klines?symbol={q}&interval=1d&startTime={t}&limit=1500')
        if not k:
            break
        kl += [(int(x[0]), float(x[1]), float(x[5])) for x in k]
        if len(k) < 1500:
            break
        t = int(k[-1][0]) + D
    fu, t = [], 0
    while kl:
        r = _get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={q}&startTime={t}&limit=1000')
        if not r:
            break
        fu += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
        if len(r) < 1000:
            break
        t = int(r[-1]['fundingTime']) + 1
        time.sleep(0.1)
    sp = None
    base = re.sub(r'^(1000000|1000|1M)', '', sym[:-4])
    s = _get(f'https://api.binance.com/api/v3/klines?symbol={urllib.parse.quote(base)}USDT&interval=1d&startTime=0&limit=1')
    if s:
        sp = int(s[0][0])
    d = dict(k=kl, f=fu, spot0=sp)
    json.dump(d, open(p, 'w'))
    time.sleep(0.1)
    return d


def universe():
    ei = json.load(open(os.path.join(C, 'exchangeInfo.json')))
    out = {}
    for x in ei['symbols']:
        if (x['contractType'] == 'PERPETUAL' and x['quoteAsset'] == 'USDT' and x['status'] != 'PENDING_TRADING'
                and x.get('underlyingType', 'COIN') == 'COIN' and x['onboardDate'] >= T23):
            out[x['symbol']] = None
    names = {x['symbol'] for x in ei['symbols']}
    s3 = json.load(open(os.path.join(C, 's3_symbols.json')))
    for s in s3:
        if s.endswith('USDT') and s not in names and s not in INDEX_MISSING:
            out[s] = 'missing'
    return sorted(out)


def leg(k, ft, fr, a_ms, b_ms):
    """Corto del open de la vela a_ms al open de b_ms (o de la última vela con volumen antes). None si no hay data."""
    ts = np.array([x[0] for x in k]); o = np.array([x[1] for x in k]); v = np.array([x[2] for x in k])
    ia = np.searchsorted(ts, a_ms)
    if ia >= ts.size or ts[ia] != a_ms or v[ia] <= 0:
        return None
    ib = np.searchsorted(ts, b_ms)
    early = False
    if ib >= ts.size or ts[ib] != b_ms or v[ib] <= 0:
        live = np.flatnonzero((ts > a_ms) & (ts < b_ms) & (v > 0))
        if live.size == 0:
            return None
        ib, early = live[-1], True
    i0, i1 = np.searchsorted(ft, ts[ia], side='right'), np.searchsorted(ft, ts[ib], side='right')
    return -(o[ib] / o[ia] - 1), float(fr[i0:i1].sum()), early


def cluster_ci(x, g, rng):
    ug = np.unique(g)
    idx = [np.flatnonzero(g == w) for w in ug]
    s = np.array([x[i].sum() for i in idx]); n = np.array([i.size for i in idx])
    bs = np.empty(BOOT)
    for r in range(BOOT):
        j = rng.integers(0, ug.size, ug.size)
        bs[r] = s[j].sum() / n[j].sum()
    bs.sort()
    return float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]), int(ug.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    lo, hi = (T25, TEND) if a.reserved else (T23, T25)
    rows, skipped = [], []
    for s in universe():
        d = fetch(s)
        if not d['k']:
            skipped.append((s, 'sin velas')); continue
        t0 = d['k'][0][0]                       # vela del día del alta (o 1ra disponible)
        if not (lo <= t0 < hi):
            continue
        ft = np.array([x[0] for x in d['f']], dtype=np.int64); fr = np.array([x[1] for x in d['f']])
        tr = leg(d['k'], ft, fr, t0 + D, t0 + 29 * D)
        ct = leg(d['k'], ft, fr, t0 + 59 * D, t0 + 87 * D)
        if tr is None or ct is None or ct[2]:
            skipped.append((s, 'sin tramo o sin control')); continue
        day1 = d['k'][1][1] / d['k'][0][1] - 1 if len(d['k']) > 1 else np.nan
        new = d['spot0'] is None or d['spot0'] >= t0 - 30 * D
        wk = dt.datetime.utcfromtimestamp(t0 / 1000).isocalendar()
        rows.append(dict(sym=s, t0=t0, week=wk[0] * 100 + wk[1], gross=tr[0], fund=tr[1], early=tr[2],
                         c_gross=ct[0], c_fund=ct[1], day1=day1, new=new))
    rows.sort(key=lambda r: r['t0'])
    g = np.array([r['week'] for r in rows])
    gross = np.array([r['gross'] for r in rows]); fund = np.array([r['fund'] for r in rows])
    net = gross + fund - COST; pess = gross + fund - PESS
    cnet = np.array([r['c_gross'] + r['c_fund'] for r in rows]) - COST
    diff = net - cnet
    rng = np.random.default_rng(SEED)
    l, h, nw = cluster_ci(net, g, rng)
    dl, dh, _ = cluster_ci(diff, g, rng)
    half = net.size // 2
    h1, h2 = float(net[:half].mean()), float(net[half:].mean())
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'  {tag}: n={net.size} monedas, {nw} semanas; salteadas {len(skipped)}')
    print(f'  neto {net.mean():+.2%}  mediana {np.median(net):+.2%}  CI agrupado [{l:+.2%}, {h:+.2%}]  ganados '
          f'{(net > 0).mean():.0%}  mitades {h1:+.2%} / {h2:+.2%}  pesimista {pess.mean():+.2%}')
    print(f'  bruto {gross.mean():+.2%}  funding {fund.mean():+.2%}  control (días 60-88) {cnet.mean():+.2%}  '
          f'diferencia {diff.mean():+.2%} CI [{dl:+.2%}, {dh:+.2%}]')
    wi = int(np.argmin(net))
    print(f'  peor: {rows[wi]["sym"]} {net[wi]:+.1%} (= {net[wi] * 100:+.0f} USD sobre 100)  cerraron antes del día 30: '
          f'{sum(r["early"] for r in rows)}  golpe día 1 (no operable) mediana {np.nanmedian([r["day1"] for r in rows]):+.2%}')
    nm = np.array([r['new'] for r in rows])
    if nm.any():
        print(f'  descriptivo token nuevo n={nm.sum()}: neto {net[nm].mean():+.2%} mediana {np.median(net[nm]):+.2%}; '
              f'monedas viejas n={(~nm).sum()}: {net[~nm].mean():+.2%}')
    yrs = {}
    for r, x in zip(rows, net):
        yrs.setdefault(dt.datetime.utcfromtimestamp(r['t0'] / 1000).year, []).append(x)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%} (n={len(v)})' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'media>0': net.mean() > 0, 'CI_inf>0': l > 0, 'diferencia_control>0': diff.mean() > 0}
    else:
        crit = {'1_n>=25': net.size >= 25, '2_media>0_y_CI_inf>0': net.mean() > 0 and l > 0,
                '3_dos_mitades>0': h1 > 0 and h2 > 0, '4_diferencia_control_media>0_y_CI_inf>0': diff.mean() > 0 and dl > 0,
                '5_pesimista>0': pess.mean() > 0, '6_mediana>0': np.median(net) > 0}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P56 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(n=int(net.size), semanas=nw, neto=float(net.mean()), mediana=float(np.median(net)), ci=[l, h],
               mitades=[h1, h2], pesimista=float(pess.mean()), bruto=float(gross.mean()), funding=float(fund.mean()),
               control=float(cnet.mean()), diferencia=float(diff.mean()), ci_diferencia=[dl, dh],
               peor=[rows[wi]['sym'], float(net[wi])], salteadas=len(skipped), criterios=crit, PASA=ok,
               criterio='docs/p56_listados_nuevos_criterio.md (54ebe1b)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1, default=lambda x: bool(x) if isinstance(x, np.bool_) else float(x))
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
