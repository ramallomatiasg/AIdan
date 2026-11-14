"""
backtest_p43_vencimiento_deribit.py — P43: ¿la volatilidad de BTC cambia alrededor del vencimiento mensual de Deribit?

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja velas de 1 h de BTCUSDT (Binance spot, API pública) a
`.cache_p43/`.
Criterio declarado ANTES de medir: docs/p43_vencimiento_deribit_criterio.md (03af480). Leer contra eso.

Uso:
    python tools/backtest_p43_vencimiento_deribit.py
"""
import calendar
import datetime as dt
import json
import os
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p43')
H = 3600
RES_FROM = dt.date(2023, 1, 1)
START = dt.datetime(2019, 6, 25, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
REPS, SEED = 5000, 20261114
OUT = os.path.join(ROOT, 'docs', 'p43_vencimiento_deribit_resultado.json')
UA = {'User-Agent': 'research-script/1.0'}


def fetch():
    path = os.path.join(CACHE, 'BTCUSDT_1h.json')
    if os.path.exists(path):
        return {int(k): v for k, v in json.load(open(path)).items()}
    os.makedirs(CACHE, exist_ok=True)
    out, t = {}, int(START.timestamp() * 1000)
    end = int(END.timestamp() * 1000)
    while t < end:
        url = f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&startTime={t}&limit=1000'
        rows = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
        if not rows:
            break
        for r in rows:
            out[int(r[0]) // 1000] = float(r[1])          # precio de APERTURA de la hora
        t = int(rows[-1][0]) + H * 1000
        time.sleep(0.2)
    json.dump(out, open(path, 'w'))
    return out


def last_friday(y, m):
    d = dt.date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() != 4:
        d -= dt.timedelta(days=1)
    return d


def rv(px, a, b):
    """suma de retornos log horarios al cuadrado entre a y b (segundos, exclusivo de b). None si falta alguna hora."""
    p = [px.get(t) for t in range(a, b + H, H)]
    if any(x is None for x in p):
        return None
    r = np.diff(np.log(p))
    return float((r ** 2).sum())


def main():
    px = fetch()
    exp = {last_friday(y, m) for y in range(2019, 2027) for m in range(1, 13)}
    rows = []
    d = dt.date(2019, 6, 28)
    while d < END.date() - dt.timedelta(days=3):
        f = int(dt.datetime(d.year, d.month, d.day, 8, tzinfo=dt.timezone.utc).timestamp())
        pre, post = rv(px, f - 48 * H, f), rv(px, f, f + 48 * H)
        if pre and post:
            rows.append(dict(date=d, exp=d in exp, q=d in exp and d.month in (3, 6, 9, 12),
                             L=np.log(post / pre), pre=pre, post=post,
                             ret_pre=float(np.log(px[f] / px[f - 48 * H]))))
        d += dt.timedelta(days=7)
    rng = np.random.default_rng(SEED)

    def stats(rs):
        e = np.array([r['L'] for r in rs if r['exp']])
        n = np.array([r['L'] for r in rs if not r['exp']])
        D = float(e.mean() - n.mean())
        bs = [rng.choice(e, e.size).mean() - rng.choice(n, n.size).mean() for _ in range(REPS)]
        lpre = np.log([r['pre'] for r in rs if r['exp']]).mean() - np.log([r['pre'] for r in rs if not r['exp']]).mean()
        lpost = np.log([r['post'] for r in rs if r['exp']]).mean() - np.log([r['post'] for r in rs if not r['exp']]).mean()
        return dict(n_exp=int(e.size), n_normal=int(n.size), D=D, expD=float(np.exp(D)),
                    ci95=[float(x) for x in np.percentile(bs, [2.5, 97.5])],
                    pre_vs_normal_log=float(lpre), post_vs_normal_log=float(lpost))
    res = [r for r in rows if r['date'] >= RES_FROM]
    dsc = [r for r in rows if r['date'] < RES_FROM]
    S, Dd = stats(res), stats(dsc)
    c = [S['n_exp'] >= 36, S['D'] > 0 and S['ci95'][0] > 0, Dd['D'] > 0, S['expD'] >= 1.10]
    by_year = {}
    for r in rows:
        by_year.setdefault(str(r['date'].year), {'e': [], 'n': []})['e' if r['exp'] else 'n'].append(r['L'])
    q = np.array([r['L'] for r in rows if r['q']])
    mo = np.array([r['L'] for r in rows if r['exp'] and not r['q']])
    o = dict(reserva=S, descubrimiento=Dd, criterios=c, pasa=all(c),
             descriptivo=dict(
                 trimestrales_L=float(q.mean()), mensuales_no_trim_L=float(mo.mean()),
                 normales_L=float(np.mean([r['L'] for r in rows if not r['exp']])),
                 ret_pre48_exp_pct=float(np.mean([r['ret_pre'] for r in rows if r['exp']])) * 100,
                 ret_pre48_normal_pct=float(np.mean([r['ret_pre'] for r in rows if not r['exp']])) * 100,
                 por_anio={y: dict(D=round(float(np.mean(v['e']) - np.mean(v['n'])), 3), n_exp=len(v['e']))
                           for y, v in sorted(by_year.items()) if v['e'] and v['n']}))
    print(json.dumps(o, indent=1))
    json.dump(o, open(OUT, 'w'), indent=1)


if __name__ == '__main__':
    main()
