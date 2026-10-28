"""P18 — sesgo favorito-longshot en Kalshi (criterio: docs/p18_favorito_longshot_criterio.md).

Read-only: no toca la DB de AIdan ni MT5. Baja datos PUBLICOS de la API de Kalshi a .cache_p18/
(series, mercados liquidados del endpoint historico y velas de 1 h con bid/ask) y evalua la regla
congelada del criterio. --reserved corre las series 41-100 y se niega salvo que el principal haya PASADO.

  python tools/backtest_p18_kalshi.py            # principal (series 1-40)
  python tools/backtest_p18_kalshi.py --reserved # solo si el principal paso
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import numpy as np

B = 'https://api.elections.kalshi.com/trade-api/v2'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, '.cache_p18')
RESULT = os.path.join(ROOT, 'docs', 'p18_kalshi_resultado.json')

SEED = 20261028
N_MAIN, N_RES_END = 40, 100
EVENTS_PER_SERIES = 150
MARKETS_PER_EVENT = 6
P_START = dt.datetime(2025, 10, 1, tzinfo=dt.timezone.utc)
P_END = dt.datetime(2026, 8, 28, tzinfo=dt.timezone.utc)
RECENT = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
H_MAIN = 6
FAV_LO, FAV_HI = 0.90, 0.97
LONG_HI = 0.10
MAX_SPREAD = 0.03
DEFAULT_FEE = 0.07


def ts(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00'))


def get(path, tries=12):
    url = B + path
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 or e.code >= 500:
                time.sleep(min(30, 2 * (i + 1)))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(2 * (i + 1))
    raise RuntimeError(f'sin respuesta: {url}')


def cached(name, fn):
    p = os.path.join(CACHE, name)
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    data = fn()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return data


def series_ranked():
    def fn():
        s = get('/series?include_volume=true')['series']
        return [dict(ticker=x['ticker'], category=x.get('category'), volume=float(x.get('volume_fp') or 0),
                     fee_type=x.get('fee_type'), fee_multiplier=x.get('fee_multiplier')) for x in s]
    s = cached('series.json', fn)
    s = [x for x in s if not x['ticker'].startswith('KXMVE')]
    s.sort(key=lambda x: -x['volume'])
    return s


def series_markets(ticker):
    def fn():
        out, cursor = [], None
        while True:
            q = f'/historical/markets?series_ticker={ticker}&limit=1000' + (f'&cursor={cursor}' if cursor else '')
            r = get(q) or {}
            for m in r.get('markets', []):
                out.append({k: m.get(k) for k in ('ticker', 'event_ticker', 'open_time', 'close_time',
                                                  'expected_expiration_time', 'result', 'volume_fp',
                                                  'volume', 'status')})
            cursor = r.get('cursor')
            if not cursor or not r.get('markets'):
                break
        return out
    return cached(f'markets/{ticker}.json', fn)


def market_candles(ticker, exp_epoch):
    def fn():
        r = get(f'/historical/markets/{ticker}/candlesticks?start_ts={exp_epoch - 26 * 3600}'
                f'&end_ts={exp_epoch}&period_interval=60') or {}
        return r.get('candlesticks', [])
    return cached(f'candles/{ticker}.json', fn)


def _px(block, key='close'):
    if not block:
        return None
    v = block.get(key, block.get(key + '_dollars'))
    return float(v) if v not in (None, '') else None


def eligible(m):
    exp = m.get('expected_expiration_time')
    if not exp or m.get('result') not in ('yes', 'no') or not m.get('open_time') or not m.get('close_time'):
        return False
    e = ts(exp)
    if not (P_START <= e <= P_END):
        return False
    return (e - ts(m['open_time'])).total_seconds() >= 24 * 3600


def fee(mult, p):
    return (DEFAULT_FEE if mult is None else float(mult)) * p * (1 - p)


def bet(candles, m, h, lo, hi, mult):
    """Lado comprado y retorno neto por dolar a h horas de la expiracion programada, o None."""
    e = int(ts(m['expected_expiration_time']).timestamp()) - h * 3600
    if int(ts(m['close_time']).timestamp()) <= e or int(ts(m['open_time']).timestamp()) > e - 3600:
        return None
    cs = [c for c in candles if int(c['end_period_ts']) <= e]
    if not cs:
        return None
    c = cs[-1]
    ask, bid = _px(c.get('yes_ask')), _px(c.get('yes_bid'))
    if ask is None or bid is None or bid <= 0 or ask >= 1 or ask - bid > MAX_SPREAD + 1e-9:
        return None
    for side, p in (('yes', ask), ('no', 1 - bid)):
        if lo <= p + 1e-9 and p <= hi + 1e-9:
            win = 1.0 if m['result'] == side else 0.0
            f = fee(mult, p)
            return dict(side=side, price=p, win=win, fee=f, ret=(win - p - f) / p)
    return None


def sample(series, workers=8):
    rng = random.Random(SEED)
    work = []
    with ThreadPoolExecutor(workers) as ex:                # solo baja/cachea; el muestreo sigue en orden fijo
        listed = list(ex.map(lambda s: series_markets(s['ticker']), series))
    for s, allm in zip(series, listed):
        ms = [m for m in allm if eligible(m)]
        ev = defaultdict(list)
        for m in ms:
            ev[m['event_ticker']].append(m)
        keys = sorted(ev)
        rng.shuffle(keys)
        for k in keys[:EVENTS_PER_SERIES]:
            top = sorted(ev[k], key=lambda m: -float(m.get('volume_fp') or m.get('volume') or 0))
            for m in top[:MARKETS_PER_EVENT]:
                work.append((s, m))
        print(f'  {s["ticker"]:<28} mercados elegibles {len(ms):>6}  eventos {len(ev):>5}', flush=True)
    return work


def evaluate(work, h, lo, hi):
    by_event = defaultdict(list)
    for s, m, cs in work:
        b = bet(cs, m, h, lo, hi, s.get('fee_multiplier'))
        if b:
            b['series'], b['category'] = s['ticker'], s.get('category')
            b['when'] = ts(m['expected_expiration_time'])
            by_event[m['event_ticker']].append(b)
    rows = []
    for k, bs in by_event.items():
        rows.append(dict(event=k, series=bs[0]['series'], category=bs[0]['category'], when=bs[0]['when'],
                         ret=float(np.mean([b['ret'] for b in bs])), win=float(np.mean([b['win'] for b in bs])),
                         price=float(np.mean([b['price'] for b in bs])),
                         fee=float(np.mean([b['fee'] for b in bs]))))
    rows.sort(key=lambda r: r['when'])
    return rows


def boot_week(rows, n=2000):
    rng = np.random.default_rng(SEED)
    wk = defaultdict(list)
    for r in rows:
        wk[r['when'].isocalendar()[:2]].append(r['ret'])
    groups = list(wk.values())
    means = []
    for _ in range(n):
        pick = rng.integers(0, len(groups), len(groups))
        vals = np.concatenate([groups[i] for i in pick])
        means.append(vals.mean())
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summary(rows):
    if not rows:
        return dict(n=0)
    r = np.array([x['ret'] for x in rows])
    return dict(n=len(rows), mean=float(r.mean()), win=float(np.mean([x['win'] for x in rows])),
                price=float(np.mean([x['price'] for x in rows])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args()

    ranked = series_ranked()
    if a.reserved:
        if not os.path.exists(RESULT) or not json.load(open(RESULT, encoding='utf-8')).get('pasa'):
            sys.exit('reservadas: el principal no PASO (o no se corrio) => no se miran.')
        universe, label = ranked[N_MAIN:N_RES_END], 'reservadas 41-100'
    else:
        universe, label = ranked[:N_MAIN], 'principal 1-40'
    print(f'P18 Kalshi — {label}')

    print('mercados por serie (historico):')
    base = sample(universe, a.workers)
    print(f'mercados a bajar velas: {len(base)}', flush=True)

    failed = []

    def job(sm):
        s, m = sm
        try:
            return s, m, market_candles(m['ticker'], int(ts(m['expected_expiration_time']).timestamp()))
        except RuntimeError:                           # no se cachea: la proxima corrida lo reintenta
            failed.append(m['ticker'])
            return s, m, []
    work, done = [], 0
    with ThreadPoolExecutor(a.workers) as ex:
        for w in ex.map(job, base):
            work.append(w)
            done += 1
            if done % 1000 == 0:
                print(f'  velas {done}/{len(base)}', flush=True)

    print(f'velas sin respuesta (fuera de la muestra): {len(failed)}/{len(base)}', flush=True)
    rows = evaluate(work, H_MAIN, FAV_LO, FAV_HI)
    out = dict(universo=label, criterio='docs/p18_favorito_longshot_criterio.md', h=H_MAIN,
               tramo=[FAV_LO, FAV_HI], n_mercados=len(base), velas_fallidas=len(failed))
    s = summary(rows)
    out['principal'] = s
    if s['n'] == 0:
        print('sin señales'); out['pasa'] = False
        json.dump(out, open(RESULT if not a.reserved else RESULT.replace('.json', '_reservadas.json'), 'w'), indent=1, default=str)
        return
    lo, hi = boot_week(rows)
    half = len(rows) // 2
    h1, h2 = summary(rows[:half]), summary(rows[half:])
    contrib = defaultdict(float)
    for r in rows:
        contrib[r['series']] += r['ret']
    top_series = max(contrib, key=contrib.get)
    sin_top = summary([r for r in rows if r['series'] != top_series])
    recent = summary([r for r in rows if r['when'] >= RECENT])
    calib_null = -float(np.mean([r['fee'] / r['price'] for r in rows]))

    checks = {
        '1_n>=300': s['n'] >= 300,
        '2_CI_inf>0': lo > 0,
        '3_mitades>0': h1['mean'] > 0 and h2['mean'] > 0,
        f'4_sin_{top_series}>0': sin_top.get('mean', -1) > 0,
        '5_desde_jun-2026>0': recent.get('n', 0) > 0 and recent['mean'] > 0,
    }
    out.update(ci95=[lo, hi], mitades=[h1, h2], sin_top=dict(serie=top_series, **sin_top), recientes=recent,
               nula_calibrado=calib_null, checks=checks, pasa=all(checks.values()))

    print(f"\nFAVORITO [{FAV_LO}-{FAV_HI}] a {H_MAIN} h: n={s['n']} eventos  media neta {s['mean']*100:+.2f}%/apuesta  "
          f"CI95 [{lo*100:+.2f}, {hi*100:+.2f}]")
    print(f"  acierto {s['win']*100:.1f}% vs precio medio {s['price']*100:.1f}%  (nula calibrado: {calib_null*100:+.2f}%)")
    print(f"  mitades {h1['mean']*100:+.2f}% / {h2['mean']*100:+.2f}%  · sin {top_series}: {sin_top.get('mean',0)*100:+.2f}% "
          f"(n={sin_top.get('n')})  · desde jun-2026: {recent.get('mean',0)*100:+.2f}% (n={recent.get('n')})")
    for k, v in checks.items():
        print(f'  [{"OK " if v else "NO "}] {k}')
    print('>>> PASA' if out['pasa'] else '>>> NO PASA')

    # descriptivos
    print('\nDescriptivos (no deciden):')
    desc = {}
    for name, (h, l_, u_) in {'longshot<=0.10_6h': (6, 0.0, LONG_HI), 'favorito_1h': (1, FAV_LO, FAV_HI),
                              'favorito_24h': (24, FAV_LO, FAV_HI)}.items():
        d = summary(evaluate(work, h, max(l_, 0.01), u_))
        desc[name] = d
        if d['n']:
            print(f"  {name:<20} n={d['n']:>5}  neta {d['mean']*100:+.2f}%  acierto {d['win']*100:.1f}% vs precio {d['price']*100:.1f}%")
    cat = defaultdict(list)
    for r in rows:
        cat[r['category']].append(r)
    for c, rs in sorted(cat.items(), key=lambda kv: -len(kv[1])):
        d = summary(rs)
        desc[f'cat_{c}'] = d
        print(f"  cat {c:<22} n={d['n']:>5}  neta {d['mean']*100:+.2f}%  acierto {d['win']*100:.1f}% vs precio {d['price']*100:.1f}%")
    calib = {}
    allb = []
    for s_, m, cs in work:
        b = bet(cs, m, H_MAIN, 0.01, 0.99, s_.get('fee_multiplier'))
        if b:
            allb.append(b)
    for k in range(10):
        bs = [b for b in allb if k / 10 <= b['price'] < (k + 1) / 10]
        if len(bs) >= 20:
            calib[f'{k/10:.1f}-{(k+1)/10:.1f}'] = dict(n=len(bs), precio=float(np.mean([b['price'] for b in bs])),
                                                         acierto=float(np.mean([b['win'] for b in bs])))
    print('  calibracion del SI al ask (a 6 h):')
    for k, v in calib.items():
        print(f"    {k}  n={v['n']:>5}  precio {v['precio']*100:5.1f}%  acierto {v['acierto']*100:5.1f}%")
    out['descriptivos'] = desc
    out['calibracion'] = calib
    path = RESULT if not a.reserved else RESULT.replace('.json', '_reservadas.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, default=str)
    print(f'\nresultado -> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
