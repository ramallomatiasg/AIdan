"""P59 — atención en Wikipedia → reversión semanal de las alts (largo las de menos salto de vistas, corto las de más).

Criterio declarado antes de medir: docs/p59_wikipedia_atencion_criterio.md (68aebaa).
Read-only: sin MT5, no toca la DB. Fuentes públicas (Binance, Wikipedia, Wikimedia) a .cache_p59/.

  python tools/backtest_p59_wikipedia_atencion.py --map     # solo arma el mapeo moneda → artículo (sin vistas ni precios)
  python tools/backtest_p59_wikipedia_atencion.py           # descubrimiento 2020-2023
  python tools/backtest_p59_wikipedia_atencion.py --reserved
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
C = os.path.join(ROOT, '.cache_p59')
PX = os.path.join(C, 'px'); PV = os.path.join(C, 'pv')
OUT = os.path.join(ROOT, 'docs', 'p59_wikipedia_atencion_resultado.json')
COST, PESS = 0.001, 0.002
MIN_V8, MIN_N, MIN_AGE = 700, 10, 30
D0, SPLIT, DEND = dt.date(2020, 1, 6), dt.date(2024, 1, 1), dt.date(2026, 11, 9)
BOOT, SEED, NPLAC = 5000, 20261119, 200
DAY = 86400_000
UA = {'User-Agent': 'AIdan-research/1.0 (personal backtest)'}
KEYS = ('cryptocurrency', 'blockchain', 'token', 'coin')


def _get(u, headers=UA):
    for k in range(8):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=headers), timeout=20).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            if e.code == 429:
                time.sleep(30 * (k + 1)); continue
            if k == 7:
                raise
        except Exception:
            if k == 7:
                raise
        time.sleep(2 + 3 * k)


def base_of(sym):
    return re.sub(r'^(1000000|1000|1M)', '', sym[:-4])


def build_map():
    os.makedirs(C, exist_ok=True)
    ei = _get('https://fapi.binance.com/fapi/v1/exchangeInfo', {'User-Agent': 'Mozilla/5.0'})
    syms = {x['symbol'] for x in ei['symbols'] if x['contractType'] == 'PERPETUAL' and x['quoteAsset'] == 'USDT'
            and x.get('underlyingType', 'COIN') == 'COIN'}
    s3 = json.load(open(os.path.join(ROOT, '.cache_p56', 's3_symbols.json')))
    syms |= {s for s in s3 if s.endswith('USDT')}
    assets = _get('https://www.binance.com/bapi/asset/v2/public/asset/asset/get-all-asset', {'User-Agent': 'Mozilla/5.0'})
    names = {a['assetCode']: a['assetName'] for a in assets['data']}
    # Misma regla del criterio. Implementación (20-nov, antes de mirar vistas o precios): la API REST página por página
    # devolvía 429 (Wikipedia limita pedidos sueltos), así que se consulta la API de acción en lotes de 20 títulos,
    # siguiendo redirecciones, con pageprops (desambiguación) y el texto de la introducción (en vez del resumen REST).
    cand = {}
    for s in sorted(syms):
        nm = names.get(base_of(s))
        if nm and re.match(r'^[ -~]+$', nm):
            cand[s] = [f'{nm} (cryptocurrency)', f'{nm} (blockchain)', f'{nm} (blockchain platform)', nm]
    titles = sorted({t for v in cand.values() for t in v})
    info, tried = {}, 0
    for i in range(0, len(titles), 20):
        chunk = titles[i:i + 20]
        q = urllib.parse.urlencode({'action': 'query', 'format': 'json', 'redirects': 1, 'prop': 'extracts|pageprops',
                                    'exintro': 1, 'explaintext': 1, 'exlimit': 20, 'ppprop': 'disambiguation',
                                    'titles': '|'.join(chunk)})
        r = _get('https://en.wikipedia.org/w/api.php?' + q) or {}
        tried += len(chunk)
        qq = r.get('query', {})
        mapn = {x['from']: x['to'] for x in qq.get('normalized', [])}
        mapr = {x['from']: x['to'] for x in qq.get('redirects', [])}
        pages = {pg['title']: pg for pg in qq.get('pages', {}).values() if 'missing' not in pg and 'invalid' not in pg}
        for t in chunk:
            u = mapn.get(t, t); u = mapr.get(u, u)
            pg = pages.get(u)
            if pg:
                info[t] = (pg['title'].replace(' ', '_'), 'disambiguation' in pg.get('pageprops', {}), pg.get('extract') or '')
        if i % 400 == 0:
            print(f'  {i}/{len(titles)} títulos', flush=True)
        time.sleep(1.0)
    by_art = {}
    for s, ts in cand.items():
        for t in ts:
            x = info.get(t)
            if not x or x[1]:
                continue
            if any(k in x[2].lower() for k in KEYS):
                by_art.setdefault(x[0], []).append(s)
                break
    mp = {v[0]: a for a, v in by_art.items() if len(v) == 1}
    dup = {a: v for a, v in by_art.items() if len(v) > 1}
    json.dump(dict(map=mp, duplicados=dup, n_simbolos=len(syms), consultas=tried), open(os.path.join(C, 'mapping.json'), 'w'), indent=1)
    print(f'mapeo: {len(mp)} monedas con artículo propio ({len(dup)} artículos compartidos excluidos) de {len(syms)} símbolos')
    return mp


def views(art):
    os.makedirs(PV, exist_ok=True)
    p = os.path.join(PV, urllib.parse.quote(art, safe='') + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    r = _get('https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/'
             f'{urllib.parse.quote(art, safe="")}/daily/2019070100/2026111900')
    out = {x['timestamp'][:8]: x['views'] for x in (r or {}).get('items', [])}
    json.dump(out, open(p, 'w')); time.sleep(0.05)
    return out


def prices(sym):
    os.makedirs(PX, exist_ok=True)
    p = os.path.join(PX, urllib.parse.quote(sym, safe='') + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    alt = os.path.join(ROOT, '.cache_p56', 'px', urllib.parse.quote(sym, safe='') + '.json')
    if os.path.exists(alt):
        d = json.load(open(alt))
        json.dump(d, open(p, 'w'))
        return d
    q = urllib.parse.quote(sym)
    kl, t = [], 0
    while True:
        k = _get(f'https://fapi.binance.com/fapi/v1/klines?symbol={q}&interval=1d&startTime={t}&limit=1500',
                 {'User-Agent': 'Mozilla/5.0'})
        if not k:
            break
        kl += [(int(x[0]), float(x[1]), float(x[5])) for x in k]
        if len(k) < 1500:
            break
        t = int(k[-1][0]) + DAY
    fu, t = [], 0
    while kl:
        r = _get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={q}&startTime={t}&limit=1000',
                 {'User-Agent': 'Mozilla/5.0'})
        if not r:
            break
        fu += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
        if len(r) < 1000:
            break
        t = int(r[-1]['fundingTime']) + 1
        time.sleep(0.1)
    d = dict(k=kl, f=fu)
    json.dump(d, open(p, 'w')); time.sleep(0.1)
    return d


def ms(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def panel(mp, weeks):
    """Para cada moneda: señal por semana y retorno largo (con funding) del lunes t al lunes t+1."""
    sig, ret = {}, {}
    for s, art in mp.items():
        v = views(art)
        if not v:
            continue
        px = prices(s)
        if not px['k']:
            continue
        ts = np.array([x[0] for x in px['k']]); o = np.array([x[1] for x in px['k']]); vol = np.array([x[2] for x in px['k']])
        ft = np.array([x[0] for x in px['f']], dtype=np.int64); fr = np.array([x[1] for x in px['f']])
        first = ts[0]
        sg, rt = {}, {}
        for w in weeks:
            wk = [sum(v.get((w - dt.timedelta(days=7 * j + i)).strftime('%Y%m%d'), 0) for i in range(1, 8)) for j in range(9)]
            v8 = np.mean(wk[1:])
            a, b = ms(w), ms(w + dt.timedelta(days=7))
            if v8 < MIN_V8 or wk[0] <= 0 or a - first < MIN_AGE * DAY:
                continue
            ia = np.searchsorted(ts, a)
            if ia >= ts.size or ts[ia] != a or vol[ia] <= 0:
                continue
            ib = np.searchsorted(ts, b)
            if ib >= ts.size or ts[ib] != b or vol[ib] <= 0:
                live = np.flatnonzero((ts > a) & (ts < b) & (vol > 0))
                if live.size == 0:
                    continue
                ib = live[-1]
            f = fr[np.searchsorted(ft, ts[ia], side='right'):np.searchsorted(ft, ts[ib], side='right')].sum()
            sg[w] = float(np.log(wk[0] / v8)); rt[w] = float(o[ib] / o[ia] - 1 - f)
        if sg:
            sig[s], ret[s] = sg, rt
    return sig, ret


def run(sig, ret, weeks, cost):
    """Devuelve retornos semanales netos y brutos (una fila por semana con cartera)."""
    net, gross, wk, prev, nL = [], [], [], (set(), set()), []
    for w in weeks:
        el = [(sig[s][w], s) for s in sig if w in sig[s]]
        if len(el) < MIN_N:
            prev = (set(), set()); continue
        el.sort()
        k = max(2, len(el) // 5)
        L = {s for _, s in el[:k]}; S = {s for _, s in el[-k:]}
        rl = np.mean([ret[s][w] for s in L]); rs = np.mean([-ret[s][w] for s in S])
        tl = len(L ^ prev[0]) / k; ts_ = len(S ^ prev[1]) / k   # cada entrada o salida paga `cost`
        c = cost * (tl + ts_)
        gross.append(rl + rs); net.append(rl + rs - c); wk.append(w); nL.append((rl, rs, len(el)))
        prev = (L, S)
    return np.array(net), np.array(gross), wk, nL


def block_ci(x, rng, b=4):
    n = x.size; nb = int(np.ceil(n / b)); out = np.empty(BOOT)
    for r in range(BOOT):
        st = rng.integers(0, n - b + 1, nb)
        out[r] = np.concatenate([x[s:s + b] for s in st])[:n].mean()
    out.sort()
    return float(out[int(.025 * BOOT)]), float(out[int(.975 * BOOT)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', action='store_true')
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    mpf = os.path.join(C, 'mapping.json')
    if a.map or not os.path.exists(mpf):
        build_map()
        if a.map:
            return
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    mp = json.load(open(mpf))['map']
    lo_d, hi_d = (SPLIT, DEND) if a.reserved else (D0, SPLIT - dt.timedelta(days=7))
    weeks = [lo_d + dt.timedelta(days=7 * i) for i in range((hi_d - lo_d).days // 7 + 1)]
    sig, ret = panel(mp, weeks)
    net, gross, wk, info = run(sig, ret, weeks, COST)
    netp, _, _, _ = run(sig, ret, weeks, PESS)
    rng = np.random.default_rng(SEED)
    lo, hi = block_ci(net, rng)
    h = net.size // 2
    # placebo: desplazamiento circular de la serie de señales de cada moneda (≥26 semanas)
    plac = []
    wi = {w: i for i, w in enumerate(weeks)}
    for _ in range(NPLAC):
        ps = {}
        for s, sg in sig.items():
            sh = int(rng.integers(26, max(27, len(weeks) - 26)))
            vals = [sg.get(w) for w in weeks]
            ps[s] = {w: vals[(wi[w] + sh) % len(weeks)] for w in sg if vals[(wi[w] + sh) % len(weeks)] is not None}
        _, g, _, _ = run(ps, ret, weeks, 0)
        plac.append(g.mean() if g.size else np.nan)
    plac = np.array(plac); p95 = float(np.nanpercentile(plac, 95))
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    rl = np.array([x[0] for x in info]); rs = np.array([x[1] for x in info]); nn = np.array([x[2] for x in info])
    print(f'== P59 {tag}: {len(mp)} monedas mapeadas, {len(sig)} con vistas y precio; {net.size} semanas con cartera '
          f'(monedas elegibles media {nn.mean():.0f})')
    print(f'  neto {net.mean():+.3%}/semana (≈{net.mean() * 52:+.1%}/año)  CI95 bloques [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {net[:h].mean():+.3%} / {net[h:].mean():+.3%}  pesimista {netp.mean():+.3%}')
    print(f'  bruto {gross.mean():+.3%}  placebo media {np.nanmean(plac):+.3%} p95 {p95:+.3%}  '
          f'pata larga {rl.mean():+.3%}  pata corta {rs.mean():+.3%}')
    yrs = {}
    for w, x in zip(wk, net):
        yrs.setdefault(w.year, []).append(x)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%}' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': net.mean() > 0 and lo > 0, '5_le_gana_al_placebo': gross.mean() > p95}
    else:
        crit = {'1_semanas>=100': net.size >= 100, '2_neto>0_y_CI_inf>0': net.mean() > 0 and lo > 0,
                '3_dos_mitades>0': net[:h].mean() > 0 and net[h:].mean() > 0, '4_pesimista>0': netp.mean() > 0,
                '5_le_gana_al_placebo': gross.mean() > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P59 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(semanas=int(net.size), monedas=len(sig), neto_semanal=float(net.mean()), ci=[lo, hi],
               mitades=[float(net[:h].mean()), float(net[h:].mean())], pesimista=float(netp.mean()),
               bruto=float(gross.mean()), placebo_p95=p95, pata_larga=float(rl.mean()), pata_corta=float(rs.mean()),
               criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p59_wikipedia_atencion_criterio.md (68aebaa)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
