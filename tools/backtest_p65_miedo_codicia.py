"""P65 — índice de miedo y codicia de cripto como señal contraria semanal en BTC.

Criterio declarado antes de medir: docs/p65_miedo_codicia_criterio.md (6391be4).
Read-only: sin MT5, no toca la DB. Datos públicos (alternative.me, Binance) a .cache_p65/; funding de .cache_p15/.

  python tools/backtest_p65_miedo_codicia.py              # feb-2018 → dic-2022
  python tools/backtest_p65_miedo_codicia.py --reserved   # 2023 → 16-nov-2026, solo si pasó
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
C = os.path.join(ROOT, '.cache_p65')
FUND = os.path.join(ROOT, '.cache_p15', 'BTC.json')
OUT = os.path.join(ROOT, 'docs', 'p65_miedo_codicia_resultado.json')
COST, PESS = 0.0010, 0.0020
SPLIT, LAST = '2023-01-01', '2026-11-16'     # LAST = último lunes de entrada con semana completa
BOOT, SEED, BLK = 5000, 20261123, 4
DAY = 86400000


def get(u):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                return json.load(r)
        except Exception:
            if k == 4:
                raise
            time.sleep(2 + 3 * k)


def load():
    os.makedirs(C, exist_ok=True)
    p = os.path.join(C, 'data.json')
    if os.path.exists(p):
        return json.load(open(p))
    fng = {dt.datetime.utcfromtimestamp(int(x['timestamp'])).strftime('%Y-%m-%d'): int(x['value'])
           for x in get('https://api.alternative.me/fng/?limit=0&format=json')['data']}
    px, start = {}, int(dt.datetime(2017, 12, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    end = int(dt.datetime(2026, 11, 24, tzinfo=dt.timezone.utc).timestamp() * 1000)
    while start < end:
        r = get(f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&startTime={start}&limit=1000')
        if not r:
            break
        for x in r:
            px[dt.datetime.utcfromtimestamp(x[0] / 1000).strftime('%Y-%m-%d')] = float(x[1])
        nxt = int(r[-1][0]) + DAY
        if nxt <= start or len(r) < 1000:
            break
        start = nxt
    d = dict(fng=fng, px=px)
    json.dump(d, open(p, 'w'))
    return d


def weeks(d):
    fng, px = d['fng'], d['px']
    fund = json.load(open(FUND))['funding']
    ft = np.array([f[0] for f in fund]); fr = np.array([f[1] for f in fund])
    mon = dt.date(2018, 2, 5)
    rows = []
    while mon.isoformat() <= LAST:
        sun = (mon - dt.timedelta(days=1)).isoformat(); nm = mon + dt.timedelta(days=7)
        if sun in fng and mon.isoformat() in px and nm.isoformat() in px:
            v = fng[sun]
            s = 1 if v <= 20 else (-1 if v >= 80 else 0)
            r = px[nm.isoformat()] / px[mon.isoformat()] - 1
            t0 = int(dt.datetime(mon.year, mon.month, mon.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
            fsum = float(fr[(ft >= t0) & (ft < t0 + 7 * DAY)].sum())
            p30 = (mon - dt.timedelta(days=30)).isoformat()
            past = px[mon.isoformat()] / px[p30] - 1 if p30 in px else np.nan
            rows.append(dict(w=mon.isoformat(), v=v, s=s, r=r, f=fsum, past=past))
        mon = nm
    return rows


def evaluate(rows, tag):
    s = np.array([x['s'] for x in rows]); r = np.array([x['r'] for x in rows]); f = np.array([x['f'] for x in rows])
    prev = np.concatenate([[0], s[:-1]])
    trade = np.abs(s - prev)
    gross = s * r + np.where(s < 0, f, 0.0)
    net = gross - trade * COST; pes = gross - trade * PESS
    act = s != 0
    na, pa = net[act], pes[act]
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(na.size / BLK)); bm = np.empty(BOOT)
    for k in range(BOOT):
        st = rng.integers(0, na.size - BLK + 1, nb)
        bm[k] = np.concatenate([na[i:i + BLK] for i in st])[:na.size].mean()
    bm.sort(); lo, hi = float(bm[int(.025 * BOOT)]), float(bm[int(.975 * BOOT)])
    h = na.size // 2
    real = (s * r)[act].mean()
    plc = []
    for k in range(8, s.size - 7):
        ss = np.roll(s, k); m = ss != 0
        plc.append((ss * r)[m].mean())
    plc = np.array(plc); p95 = float(np.percentile(plc, 95))
    L, S = act & (s > 0), act & (s < 0)
    print(f'== P65 {tag}: {len(rows)} semanas ({rows[0]["w"]} → {rows[-1]["w"]}), activas {act.sum()} '
          f'(largas {L.sum()}, cortas {S.sum()})')
    print(f'  neto por semana activa {na.mean():+.2%}  CI95 bloques [{lo:+.2%}, {hi:+.2%}]  mitades '
          f'{na[:h].mean():+.2%} / {na[h:].mean():+.2%}  pesimista {pa.mean():+.2%}')
    print(f'  bruto real {real:+.2%} vs placebo media {plc.mean():+.2%} p95 {p95:+.2%} (n={plc.size})')
    print(f'  pata larga (miedo) {gross[L].mean():+.2%}  pata corta (codicia) {gross[S].mean() if S.any() else 0:+.2%}  '
          f'BTC incondicional {r.mean():+.2%}/sem  peor semana {net[act].min():+.2%}')
    ok_p = ~np.isnan([x['past'] for x in rows])
    cc = np.corrcoef(np.array([x['v'] for x in rows])[ok_p], np.array([x['past'] for x in rows])[ok_p])[0, 1]
    print(f'  corr(índice, retorno 30d previo) {cc:+.2f}')
    yrs = {}
    for x, n_ in zip(np.array(rows)[act], na):
        yrs.setdefault(x['w'][:4], []).append(n_)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%} (n={len(v)})' for y, v in sorted(yrs.items())))
    return dict(n=int(act.sum()), neto=float(na.mean()), ci=[lo, hi], mitades=[float(na[:h].mean()),
                float(na[h:].mean())], pesimista=float(pa.mean()), bruto=float(real), placebo_p95=p95), \
        dict(lo=lo, h=h, na=na, pa=pa, real=real, p95=p95)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    rows = [x for x in weeks(load()) if (x['w'] >= SPLIT) == a.reserved]
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    res, z = evaluate(rows, tag)
    na = z['na']
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': na.mean() > 0 and z['lo'] > 0, '5_placebo': z['real'] > z['p95']}
    else:
        h = z['h']
        crit = {'1_n>=30': na.size >= 30, '2_neto>0_y_CI_inf>0': na.mean() > 0 and z['lo'] > 0,
                '3_dos_mitades>0': na[:h].mean() > 0 and na[h:].mean() > 0, '4_pesimista>0': z['pa'].mean() > 0,
                '5_placebo': z['real'] > z['p95']}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P65 {tag}: {"PASA" if ok else "NO PASA"}')
    res.update(criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p65_miedo_codicia_criterio.md (6391be4)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
