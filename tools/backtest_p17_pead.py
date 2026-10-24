"""
backtest_p17_pead.py — P17: deriva post-resultados (PEAD) en acciones de EE.UU., sorpresa medida por la
reacción del precio al anuncio (EAR).

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja datos PÚBLICOS a `.cache_p17/`:
fechas de resultados (8-K con ítem 2.02, SEC EDGAR, con hora de aceptación) y cierres ajustados (Yahoo).
Criterio declarado ANTES de medir: docs/p17_pead_criterio.md (12256eb). Leer contra eso.

Regla: d = día del anuncio (antes de 09:30 ET ⇒ ese día; si no, el hábil siguiente). EAR = ret(d-1 → d+1) − SPY.
Señal: EAR >= p80 de los EAR del universo en los 365 días previos (>=200 previos). Entrada cierre d+2, salida
cierre d+22, resultado = ret − SPY − 0,10%. Control: misma acción, entrada al azar lejos (>30 días) de anuncios.

Uso:
    python tools/backtest_p17_pead.py              # universo principal (400)
    python tools/backtest_p17_pead.py --reserved   # 401-700: se niega si el principal no PASÓ
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from bisect import bisect_left, bisect_right

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p17')
OUT = os.path.join(ROOT, 'docs', 'p17_pead_resultado.json')
SEC_UA = {'User-Agent': 'AIdan research bot aidan-research@example.org'}
P1 = int(dt.datetime(2008, 6, 1, tzinfo=dt.timezone.utc).timestamp())
P2 = int(dt.datetime(2026, 10, 24, tzinfo=dt.timezone.utc).timestamp())
EV_FROM, EV_TO = '2010-01-01', '2026-08-31'
RECENT_FROM = '2023-09-01'
HOLD, HOLD_LONG = 20, 60
COST = 0.0010
PCT, MIN_PRIOR = 80, 200
CTRL_GAP_DAYS = 30
N_CTRL, N_BOOT = 1000, 5000
SEED = 20261024
MAIN_N, RES_N = 400, 700


# ---------------------------------------------------------------- datos
def _get(url, headers, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 + 2 * k)


def universe():
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, 'company_tickers.json')
    if not os.path.exists(p):
        with open(p, 'w') as f:
            json.dump(_get('https://www.sec.gov/files/company_tickers.json', SEC_UA), f)
    with open(p) as f:
        d = json.load(f)
    seen, out = set(), []
    for i in range(len(d)):
        e = d[str(i)]
        if e['cik_str'] in seen:
            continue
        seen.add(e['cik_str'])
        out.append((e['cik_str'], e['ticker'].replace('.', '-'), e['title']))
    return out


def _rows_202(block):
    out = []
    for i, form in enumerate(block['form']):
        if form != '8-K' or '2.02' not in (block.get('items', [''] * (i + 1))[i] or ''):
            continue
        out.append(block['acceptanceDateTime'][i] or block['filingDate'][i] + 'T12:00:00.000Z')
    return out


def announcements(cik):
    p = os.path.join(CACHE, 'sec', f'{cik}.json')
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    s = _get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json', SEC_UA)
    acc = _rows_202(s['filings']['recent'])
    for fi in s['filings'].get('files', []):
        if fi.get('filingTo', '9999') < '2009-06-01':
            continue
        time.sleep(0.15)
        acc += _rows_202(_get(f'https://data.sec.gov/submissions/{fi["name"]}', SEC_UA))
    time.sleep(0.15)
    with open(p, 'w') as f:
        json.dump(sorted(set(acc)), f)
    return sorted(set(acc))


def prices(sym):
    p = os.path.join(CACHE, 'px', f'{sym}.json')
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    u = (f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}'
         f'?period1={P1}&period2={P2}&interval=1d')
    rows = {}
    try:
        j = _get(u, {'User-Agent': 'Mozilla/5.0'})['chart']['result'][0]
        off = j['meta'].get('gmtoffset', 0)
        q = j['indicators']['quote'][0]
        adj = j['indicators'].get('adjclose', [{}])[0].get('adjclose') or q['close']
        for i, t in enumerate(j.get('timestamp') or []):
            c, a = q['close'][i], adj[i]
            if None in (c, a) or c <= 0:
                continue
            rows[dt.datetime.utcfromtimestamp(t + off).strftime('%Y-%m-%d')] = (c, a)
    except Exception as e:
        print(f'  [px] {sym}: sin datos ({type(e).__name__})')
    with open(p, 'w') as f:
        json.dump(rows, f)
    return rows


# ---------------------------------------------------------------- reloj
def _us_dst(d):
    y = d.year
    mar = dt.date(y, 3, 8) + dt.timedelta(days=(6 - dt.date(y, 3, 8).weekday()) % 7)     # 2do domingo de marzo
    nov = dt.date(y, 11, 1) + dt.timedelta(days=(6 - dt.date(y, 11, 1).weekday()) % 7)   # 1er domingo de nov
    return mar <= d < nov


def to_et(s):
    u = dt.datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
    e = u - dt.timedelta(hours=4)
    if not _us_dst(e.date()):
        e = u - dt.timedelta(hours=5)
    return e


def event_day(acc, cal):
    e = to_et(acc)
    ds = e.strftime('%Y-%m-%d')
    pre_open = (e.hour, e.minute) < (9, 30)
    i = bisect_left(cal, ds) if pre_open else bisect_right(cal, ds)
    return i if i < len(cal) else None


# ---------------------------------------------------------------- medición
def build(names):
    spy = prices('SPY')
    cal = sorted(spy)
    spy_a = np.array([spy[d][1] for d in cal])
    events, stocks = [], {}
    for k, (cik, sym, title) in enumerate(names):
        if k % 50 == 0:
            print(f'  ... {k}/{len(names)}')
        try:
            acc = announcements(cik)
        except Exception as e:
            print(f'  [sec] {sym}: {type(e).__name__}')
            continue
        px = prices(sym)
        if not px:
            continue
        a = np.array([px.get(d, (np.nan, np.nan))[1] for d in cal], dtype=float)
        raw = np.array([px.get(d, (np.nan, np.nan))[0] for d in cal], dtype=float)
        idxs = sorted({i for i in (event_day(x, cal) for x in acc) if i is not None})
        kept = []
        for i in idxs:                                   # dos 2.02 en <5 hábiles = el mismo anuncio
            if kept and i - kept[-1] < 5:
                continue
            kept.append(i)
        stocks[sym] = (a, kept)
        for i in kept:
            if not (EV_FROM <= cal[i] <= EV_TO) or i < 1 or i + 2 + HOLD_LONG >= len(cal):
                continue
            w = a[[i - 1, i + 1, i + 2, i + 2 + HOLD]]
            if np.isnan(w).any() or raw[i - 1] < 5:
                continue
            ear = (a[i + 1] / a[i - 1] - 1) - (spy_a[i + 1] / spy_a[i - 1] - 1)
            r20 = (a[i + 2 + HOLD] / a[i + 2] - 1) - (spy_a[i + 2 + HOLD] / spy_a[i + 2] - 1) - COST
            r60 = np.nan
            if not np.isnan(a[i + 2 + HOLD_LONG]):
                r60 = (a[i + 2 + HOLD_LONG] / a[i + 2] - 1) - (spy_a[i + 2 + HOLD_LONG] / spy_a[i + 2] - 1) - COST
            events.append(dict(sym=sym, i=i, d=cal[i], ear=ear, r20=r20, r60=r60))
    return cal, spy_a, events, stocks


def classify(events):
    events.sort(key=lambda e: e['d'])
    ds = [dt.date.fromisoformat(e['d']) for e in events]
    ears = np.array([e['ear'] for e in events])
    for k, e in enumerate(events):
        lo = bisect_left(ds, ds[k] - dt.timedelta(days=365))
        hi = bisect_left(ds, ds[k])
        if hi - lo < MIN_PRIOR:
            e['sig'] = None
            continue
        prior = ears[lo:hi]
        e['sig'] = 'pos' if e['ear'] >= np.percentile(prior, PCT) else (
            'neg' if e['ear'] <= np.percentile(prior, 100 - PCT) else 'mid')


def boot_month(ev):
    rng = np.random.default_rng(SEED)
    by = {}
    for e in ev:
        by.setdefault(e['d'][:7], []).append(e['r20'])
    groups = [np.array(v) for v in by.values()]
    sums = np.array([g.sum() for g in groups])
    cnts = np.array([g.size for g in groups])
    pick = rng.integers(0, len(groups), (N_BOOT, len(groups)))
    m = np.sort(sums[pick].sum(1) / cnts[pick].sum(1))
    return float(m[int(0.025 * N_BOOT)]), float(m[int(0.975 * N_BOOT)])


def control(ev, stocks, cal, spy_a):
    rng = np.random.default_rng(SEED + 1)
    caldates = np.array([dt.date.fromisoformat(d).toordinal() for d in cal])
    pools = {}
    for sym in {e['sym'] for e in ev}:
        a, ann = stocks[sym]
        n = len(cal)
        i = np.arange(1, n - HOLD - 1)
        ok = ~np.isnan(a[i]) & ~np.isnan(a[i + HOLD])
        ok &= (cal_arr := np.array(cal))[i] >= EV_FROM
        ok &= cal_arr[i] <= EV_TO
        ann_ord = caldates[ann] if ann else np.array([], dtype=int)
        if ann_ord.size:
            j = np.searchsorted(ann_ord, caldates[i])
            dl = np.abs(caldates[i] - ann_ord[np.clip(j - 1, 0, ann_ord.size - 1)])
            dr = np.abs(ann_ord[np.clip(j, 0, ann_ord.size - 1)] - caldates[i])
            ok &= np.minimum(dl, dr) > CTRL_GAP_DAYS
        ii = i[ok]
        pools[sym] = (a[ii + HOLD] / a[ii] - 1) - (spy_a[ii + HOLD] / spy_a[ii] - 1) - COST
    means = np.empty(N_CTRL)
    for r in range(N_CTRL):
        means[r] = np.mean([pools[e['sym']][rng.integers(0, pools[e['sym']].size)] for e in ev])
    return float(np.percentile(means, 95)), float(means.mean())


def summarize(ev, key='r20'):
    x = np.array([e[key] for e in ev if not np.isnan(e[key])])
    return dict(n=int(x.size), mean=float(x.mean()) if x.size else float('nan'),
                median=float(np.median(x)) if x.size else float('nan'), win=float((x > 0).mean()) if x.size else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    args = ap.parse_args()
    uni = universe()
    if args.reserved:
        if not os.path.exists(OUT) or not json.load(open(OUT)).get('main', {}).get('pasa'):
            sys.exit('El principal no PASÓ: los reservados no se miran (criterio).')
        names, tag = uni[MAIN_N:RES_N], 'reserved'
    else:
        names, tag = uni[:MAIN_N], 'main'
    print(f'P17 PEAD — universo {tag}: {len(names)} empresas')
    cal, spy_a, events, stocks = build(names)
    classify(events)
    pos = [e for e in events if e['sig'] == 'pos']
    neg = [e for e in events if e['sig'] == 'neg']
    allc = [e for e in events if e['sig'] is not None]
    s = summarize(pos)
    ci = boot_month(pos)
    half = len(pos) // 2
    h1, h2 = summarize(pos[:half]), summarize(pos[half:])
    rec = summarize([e for e in pos if e['d'] >= RECENT_FROM])
    c95, cmean = control(pos, stocks, cal, spy_a)
    checks = {
        '1_n>=300': s['n'] >= 300,
        '2_CI_inf>0': ci[0] > 0,
        '3_mitades>0': h1['mean'] > 0 and h2['mean'] > 0,
        '4_>p95_control': s['mean'] > c95,
        '5_ultimos3a>0': rec['mean'] > 0,
    }
    pasa = all(checks.values())
    years = {}
    for e in pos:
        years.setdefault(e['d'][:4], []).append(e['r20'])
    print(f'\n  eventos con anuncio clasificados: {len(allc)} (todas las clases)  · stocks con datos: {len(stocks)}')
    print(f'  SEÑAL (EAR >= p{PCT}): n={s["n"]}  media neta {s["mean"]*100:+.3f}%  mediana {s["median"]*100:+.3f}%'
          f'  ganadas {s["win"]*100:.0f}%')
    print(f'  CI95 (bootstrap por mes): [{ci[0]*100:+.3f}%, {ci[1]*100:+.3f}%]')
    print(f'  mitades: {h1["mean"]*100:+.3f}% / {h2["mean"]*100:+.3f}%   · desde {RECENT_FROM}: n={rec["n"]} '
          f'{rec["mean"]*100:+.3f}%')
    print(f'  control (misma acción, día al azar): media {cmean*100:+.3f}%  p95 {c95*100:+.3f}%')
    print('  descriptivos: 60 días', f'{summarize(pos, "r60")["mean"]*100:+.3f}%',
          f'· cola opuesta (EAR<=p{100-PCT}) 20d n={len(neg)} {summarize(neg)["mean"]*100:+.3f}%',
          f'· todos los anuncios 20d {summarize(allc)["mean"]*100:+.3f}%')
    print('  por año:', ' · '.join(f'{y} {np.mean(v)*100:+.2f}% (n={len(v)})' for y, v in sorted(years.items())))
    per_year = s['n'] / max(1, len(years))
    print(f'  ~{per_year:.0f} señales/año; con capital repartido en ~{per_year*HOLD/252:.0f} posiciones abiertas, '
          f'el retorno anual sobre SPY ~ {s["mean"]*252/HOLD*100:+.1f}% (cubierto, aprox.)')
    for k, v in checks.items():
        print(f'   [{"OK " if v else "NO "}] {k}')
    print(f'\n  => {"PASA" if pasa else "NO PASA"}')
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    res[tag] = dict(n=s['n'], mean=s['mean'], median=s['median'], ci=ci, halves=[h1['mean'], h2['mean']],
                    recent=rec, control_p95=c95, control_mean=cmean, checks=checks, pasa=pasa,
                    years={y: float(np.mean(v)) for y, v in years.items()},
                    neg=summarize(neg), r60=summarize(pos, 'r60'))
    with open(OUT, 'w') as f:
        json.dump(res, f, indent=1)


if __name__ == '__main__':
    main()
