"""P58 — comprar PT de stablecoins de Pendle y aguantar al vencimiento, contra la letra del Tesoro a 3 meses.

Criterio declarado antes de medir: docs/p58_pendle_pt_criterio.md (3e62b75).
Read-only: sin MT5, no toca la DB. Datos públicos de la API de Pendle a .cache_p58/; letra: .cache_p50/dtb3.json.

  python tools/backtest_p58_pendle_pt.py              # vencimientos hasta jun-2025
  python tools/backtest_p58_pendle_pt.py --reserved   # jul-2025 → nov-2026, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p58')
TB = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p58_pendle_pt_resultado.json')
COST, PESS = 0.006, 0.012
MIN_TVL, MIN_DAYS = 1e6, 30
SPLIT, END = dt.date(2025, 7, 1), dt.date(2026, 11, 18)
BOOT, SEED = 5000, 20261118
API = 'https://api-v2.pendle.finance/core'
STABLE = re.compile(r'USD|DAI|GHO', re.I)


def _get(u):
    for k in range(5):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            if k == 4:
                raise
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
    time.sleep(0.25)
    return v


def series(m):
    ch, pt, mk = m['chainId'], m['pt']['address'], m['address']

    def px():
        r = _get(f'{API}/v4/{ch}/prices/{pt}/ohlcv?time_frame=day')
        if not r or not r.get('results'):
            return {}
        out = {}
        for ln in r['results'].strip().split('\n')[1:]:
            f = ln.split(',')
            out[dt.datetime.utcfromtimestamp(int(f[0])).strftime('%Y-%m-%d')] = float(f[4])
        return out

    def tvl():
        r = _get(f'{API}/v2/{ch}/markets/{mk}/historical-data?time_frame=day')
        if not r:
            return {}
        return {x['timestamp'][:10]: [x.get('tvl') or 0, x.get('impliedApy')] for x in r['results']}
    return cached(f'px_{ch}_{pt}.json', px), cached(f'tvl_{ch}_{mk}.json', tvl)


def cluster_ci(x, d, g, rng):
    ug = np.unique(g)
    idx = [np.flatnonzero(g == w) for w in ug]
    s = np.array([x[i].sum() for i in idx]); n = np.array([d[i].sum() for i in idx])
    bs = np.empty(BOOT)
    for r in range(BOOT):
        j = rng.integers(0, ug.size, ug.size)
        bs[r] = s[j].sum() / n[j].sum() * 365
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
    tb = json.load(open(TB)); tbd = sorted(tb)
    mk = [m for m in json.load(open(os.path.join(C, 'expired_markets.json')))
          if STABLE.search(m['accountingAsset']['symbol'] or '')]
    rows, drop = [], {}
    for m in mk:
        exp = dt.date.fromisoformat(m['expiry'][:10])
        if (exp >= SPLIT) != a.reserved or exp > END:
            continue
        start = dt.date.fromisoformat(m['timestamp'][:10])
        ent = max(start + dt.timedelta(days=7), exp - dt.timedelta(days=90))
        days = (exp - ent).days
        if days < MIN_DAYS:
            drop['menos de 30 días'] = drop.get('menos de 30 días', 0) + 1; continue
        px, tv = series(m)
        e = ent.isoformat()
        if e not in px or e not in tv or tv[e][0] < MIN_TVL:
            drop['sin precio/TVL < 1M al entrar'] = drop.get('sin precio/TVL < 1M al entrar', 0) + 1; continue
        xs = [(exp - dt.timedelta(days=k)).isoformat() for k in range(6)]
        xk = next((k for k in xs if k in px), None)
        if xk is None:
            drop['sin precio al vencer'] = drop.get('sin precio al vencer', 0) + 1; continue
        ret = px[xk] / px[e] - 1
        bills = [tb[d] for d in tbd if e <= d <= xk] or [tb[max(d for d in tbd if d <= e)]]
        bill = np.mean(bills) / 100
        rows.append(dict(sym=m['pt']['symbol'], chain=m['chainId'], exp=exp.isoformat(), days=days, ret=ret,
                         bill=bill, ex=ret - COST - bill * days / 365, exp_p=ret - PESS - bill * days / 365,
                         impl=tv[e][1], tvl=tv[e][0]))
    rows.sort(key=lambda r: r['exp'])
    ex = np.array([r['ex'] for r in rows]); exp_p = np.array([r['exp_p'] for r in rows])
    d = np.array([r['days'] for r in rows], dtype=float); ret = np.array([r['ret'] for r in rows])
    g = np.array([int(r['exp'][:7].replace('-', '')) for r in rows])
    ann = float(ex.sum() / d.sum() * 365); annp = float(exp_p.sum() / d.sum() * 365)
    rng = np.random.default_rng(SEED)
    lo, hi, nm = cluster_ci(ex, d, g, rng)
    h = ex.size // 2
    h1 = float(ex[:h].sum() / d[:h].sum() * 365); h2 = float(ex[h:].sum() / d[h:].sum() * 365)
    months = {}
    for r in rows:
        months.setdefault(r['exp'][:7], []).append(r['ret'] - COST)
    worst_m = min(months.items(), key=lambda kv: np.mean(kv[1]))
    ret_ann = float((ret - COST).sum() / d.sum() * 365)
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'  {tag}: n={ex.size} mercados, {nm} meses de vencimiento; descartados {drop}')
    print(f'  rendimiento neto {ret_ann:+.2%}/año  letra media {np.mean([r["bill"] for r in rows]):.2%}  '
          f'premio {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  pesimista {annp:+.2%}')
    wi = int(np.argmin(ret))
    print(f'  implícito medio al entrar {np.nanmean([r["impl"] or np.nan for r in rows]):.2%}  peor mercado '
          f'{rows[wi]["sym"]} (cadena {rows[wi]["chain"]}) {ret[wi]:+.1%}  peor mes {worst_m[0]} '
          f'{np.mean(worst_m[1]):+.2%} (n={len(worst_m[1])})')
    exp_ret = np.array([(1 + (r['impl'] or 0)) ** (r['days'] / 365) - 1 for r in rows])
    print(f'  terminaron < 0,98 de lo esperado: {int(((1 + ret) / (1 + exp_ret) < 0.98).sum())}/{ret.size}')
    yrs, chs = {}, {}
    for r, x in zip(rows, ex):
        yrs.setdefault(r['exp'][:4], [0, 0]); yrs[r['exp'][:4]][0] += x; yrs[r['exp'][:4]][1] += r['days']
        chs.setdefault(r['chain'], [0, 0]); chs[r['chain']][0] += x; chs[r['chain']][1] += r['days']
    print('  premio por año: ' + '  '.join(f'{y} {v[0] / v[1] * 365:+.1%}' for y, v in sorted(yrs.items())))
    print('  premio por cadena: ' + '  '.join(f'{c} {v[0] / v[1] * 365:+.1%}' for c, v in sorted(chs.items())))
    if a.reserved:
        crit = {'premio>0': ann > 0, 'CI_inf>0': lo > 0, 'peor_mes>-5%': np.mean(worst_m[1]) > -0.05}
    else:
        crit = {'1_n>=25': ex.size >= 25, '2_premio>0_y_CI_inf>0': ann > 0 and lo > 0,
                '3_dos_mitades>0': h1 > 0 and h2 > 0, '4_pesimista>0': annp > 0,
                '5_peor_mes>-5%': np.mean(worst_m[1]) > -0.05}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P58 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(n=int(ex.size), rendimiento_anual=ret_ann, premio_anual=ann, ci=[lo, hi], mitades=[h1, h2],
               pesimista=annp, peor_mercado=[rows[wi]['sym'], float(ret[wi])], peor_mes=[worst_m[0], float(np.mean(worst_m[1]))],
               descartados=drop, criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p58_pendle_pt_criterio.md (3e62b75)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
