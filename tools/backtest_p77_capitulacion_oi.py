"""
backtest_p77_capitulacion_oi.py — P77: caída fuerte del OI + caída de precio en BTC/ETH ⇒ largo 3 días.

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. OI de data.binance.vision (metrics diarios) a `.cache_p77/`;
precio y funding del perpetuo de `.cache_p15/`. Criterio declarado ANTES de medir:
docs/p77_capitulacion_oi_criterio.md (f3cd174).

    python tools/backtest_p77_capitulacion_oi.py              # descubrimiento
    python tools/backtest_p77_capitulacion_oi.py --reserved   # 2024 -> 2026, solo si pasó
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p15_funding as p15  # noqa: E402

ROOT = p15.ROOT
C = os.path.join(ROOT, '.cache_p77')
OUT = os.path.join(ROOT, 'docs', 'p77_capitulacion_oi_resultado.json')
SEED = 20261126
SYMS = ['BTC', 'ETH']
DAY = 86400 * 1000
D0 = int(dt.datetime(2020, 9, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
SPLIT = int(dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END = p15.END_MS - DAY            # último día con precio a las 08:00 de d+4 lo filtra el loop
COST = 0.0010
HOLD = 3 * DAY
BOOT = 5000


def fd(t):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime('%Y-%m-%d')


def oi_day(sym, t):
    d = fd(t)
    p = os.path.join(C, sym, d + '.json')
    if os.path.exists(p):
        return json.load(open(p))['oi']
    u = f'https://data.binance.vision/data/futures/um/daily/metrics/{sym}USDT/{sym}USDT-metrics-{d}.zip'
    val, done = None, False
    for k in range(5):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                         timeout=60).read()
            z = zipfile.ZipFile(io.BytesIO(raw))
            rows = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode())))
            rows.sort(key=lambda r: r['create_time'])
            if rows and rows[0]['create_time'][:10] == d and rows[0]['create_time'][11:16] <= '00:15':
                v = float(rows[0]['sum_open_interest'] or 0)
                val = v if v > 0 else None
            done = True
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                done = True
                break
            time.sleep(2 + 3 * k)
        except Exception:
            time.sleep(2 + 3 * k)
    if not done:
        raise RuntimeError('sin respuesta: ' + u)
    os.makedirs(os.path.join(C, sym), exist_ok=True)
    json.dump({'oi': val}, open(p, 'w'))
    return val


def build(sym):
    days = list(range(D0, END, DAY))
    with cf.ThreadPoolExecutor(16) as ex:
        oi = dict(zip(days, ex.map(lambda t: oi_day(sym, t), days)))
    d = json.load(open(os.path.join(p15.CACHE, f'{sym}.json')))
    perp = dict((int(t), v) for t, v in d['perp'])
    ft = np.array([x[0] for x in d['funding']], dtype=np.int64)
    fr = np.array([x[1] for x in d['funding']])
    rows = []
    for t in days:
        a, b = oi.get(t), oi.get(t + DAY)
        p0, p1 = perp.get(t), perp.get(t + DAY)
        e0, e1 = perp.get(t + DAY + 8 * 3600 * 1000), perp.get(t + DAY + 8 * 3600 * 1000 + HOLD)
        if None in (a, b, p0, p1, e0, e1):
            continue
        # funding pagado por el largo entre la entrada y la salida (cobros con timestamp en (entrada, salida])
        i0 = np.searchsorted(ft, t + DAY + 8 * 3600 * 1000, side='right')
        i1 = np.searchsorted(ft, t + DAY + 8 * 3600 * 1000 + HOLD, side='right')
        fund = float(fr[i0:i1].sum())
        net = e1 / e0 - 1 - fund - COST
        rows.append(dict(t=t, sym=sym, doi=float(np.log(b / a)), r=float(np.log(p1 / p0)), net=net))
    return rows


def no_overlap(evs):
    out, busy = [], {}
    for e in sorted(evs, key=lambda x: x['t']):
        if e['t'] < busy.get(e['sym'], -1):
            continue
        out.append(e)
        busy[e['sym']] = e['t'] + HOLD
    return out


def boot_ci(x, rng):
    x = np.asarray(x)
    m = np.sort(x[rng.integers(0, x.size, (BOOT, x.size))].mean(axis=1))
    return float(m[int(.025 * BOOT)]), float(m[int(.975 * BOOT)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    allrows = {s: build(s) for s in SYMS}
    thr = {}
    for s, rows in allrows.items():
        disc = [r for r in rows if r['t'] < SPLIT]
        thr[s] = dict(doi10=float(np.percentile([r['doi'] for r in disc], 10)),
                      doi50=float(np.percentile([r['doi'] for r in disc], 50)),
                      r10=float(np.percentile([r['r'] for r in disc], 10)))
        print(f"  {s}: {len(rows)} días con datos ({fd(rows[0]['t'])} -> {fd(rows[-1]['t'])})  "
              f"umbral dOI p10 {thr[s]['doi10']:+.3f}  r p10 {thr[s]['r10']:+.3f}")
    sel = (lambda r: r['t'] >= SPLIT) if a.reserved else (lambda r: r['t'] < SPLIT)
    pool, ev, ctl = [], [], []
    for s, rows in allrows.items():
        rr = [r for r in rows if sel(r)]
        ev += [r for r in rr if r['doi'] <= thr[s]['doi10'] and r['r'] < 0]
        ctl += [r for r in rr if r['r'] <= thr[s]['r10'] and r['doi'] >= thr[s]['doi50']]
        pool += [r for r in rr if r['r'] < 0]
    ev, ctl = no_overlap(ev), no_overlap(ctl)
    x = np.array([e['net'] for e in ev])
    rng = np.random.default_rng(SEED)
    lo, hi = boot_ci(x, rng)
    pl = []
    for _ in range(2000):
        idx = rng.choice(len(pool), size=x.size, replace=False)
        pl.append(np.mean([pool[i]['net'] for i in idx]))
    p95 = float(np.percentile(pl, 95))
    cm = float(np.mean([c['net'] for c in ctl])) if ctl else float('nan')
    h = x.size // 2
    h1, h2 = float(x[:h].mean()), float(x[h:].mean())
    by = {s: [e['net'] for e in ev if e['sym'] == s] for s in SYMS}
    print(f"\n  {'RESERVA' if a.reserved else 'DESCUBRIMIENTO'}: eventos n={x.size}  media neta {x.mean():+.2%}  "
          f"mediana {np.median(x):+.2%}  CI95 [{lo:+.2%}, {hi:+.2%}]  acierto {np.mean(x > 0):.0%}")
    print(f"  mitades {h1:+.2%} / {h2:+.2%}  | " + '  '.join(f"{s} n={len(v)} {np.mean(v):+.2%}" for s, v in by.items()))
    print(f"  control (caída igual sin caída de OI) n={len(ctl)} media {cm:+.2%}  | placebo p95 {p95:+.2%}")
    if a.reserved:
        crit = {'R_media>0': x.mean() > 0, 'R_media>control': x.mean() > cm}
    else:
        crit = {'1_n>=25': x.size >= 25, '2_CI_inf>0': lo > 0,
                '3_>placebo_p95_y_>control': x.mean() > p95 and x.mean() > cm,
                '4_dos_mitades>0': h1 > 0 and h2 > 0, '5_dos_monedas>0': all(np.mean(v) > 0 for v in by.values())}
    ok = all(crit.values())
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f"  >>> P77 {'reserva' if a.reserved else 'descubrimiento'}: {'PASA' if ok else 'NO PASA'}")
    out = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(n=int(x.size), mean=float(x.mean()), median=float(np.median(x)), ci=[lo, hi], halves=[h1, h2],
                   por_moneda={s: dict(n=len(v), mean=float(np.mean(v)) if v else None) for s, v in by.items()},
                   control=dict(n=len(ctl), mean=cm), placebo_p95=p95, umbrales=thr, criterios=crit, PASA=ok,
                   eventos=[dict(dia=fd(e['t']), sym=e['sym'], doi=e['doi'], r=e['r'], net=e['net']) for e in ev],
                   criterio='docs/p77_capitulacion_oi_criterio.md (f3cd174)'),
              open(out, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
