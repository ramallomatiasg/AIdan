"""
backtest_p53_deslistados.py — P53: corto del perpetuo de Binance desde el anuncio de deslistado del spot hasta el día
del deslistado.

READ-ONLY. Sin MT5, no toca la DB. Anuncios: catálogo público "Delisting" de Binance (cache .cache_p53/articles.json);
velas 1 h y funding públicos de fapi a .cache_p53/px/.
Criterio declarado ANTES de medir: docs/p53_deslistados_criterio.md (3cac83a). Leer contra eso.

    python tools/backtest_p53_deslistados.py              # descubrimiento 2022-2024
    python tools/backtest_p53_deslistados.py --reserved   # 2025-26, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p53')
PX = os.path.join(C, 'px')
OUT = os.path.join(ROOT, 'docs', 'p53_deslistados_resultado.json')
COST, PESS = 0.006, 0.012
REPS, BOOT, SEED = 2000, 5000, 20261118
H = 3600_000
EXCL = {'SUSD', 'USDP', 'IDRT', 'VAI', 'RENBTC', 'TUSD', 'BUSD', 'USDC', 'PAX'}
SPLIT = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


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


def announcements():
    arts = json.load(open(os.path.join(C, 'articles.json'), encoding='utf-8'))
    ev = []
    for a in arts:
        m = re.match(r'Binance (?:Announced .*? and )?Will Delist (.+) on (\d{4}-\d{2}-\d{2})$', a['title'].strip())
        if not m:
            continue
        syms = [s.strip() for s in re.split(r',| and ', m.group(1)) if s.strip()]
        d = dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(tzinfo=dt.timezone.utc)
        ev.append(dict(ann_ms=int(a['releaseDate']), delist=d, syms=[s for s in syms if s not in EXCL],
                       title=a['title']))
    return sorted(ev, key=lambda e: e['ann_ms'])


def fetch(sym, t0, t1):
    """Velas 1 h y funding de <sym>USDT o 1000<sym>USDT entre t0 y t1 (ms). None si no hay perpetuo."""
    os.makedirs(PX, exist_ok=True)
    p = os.path.join(PX, f'{sym}.json')
    if os.path.exists(p):
        return json.load(open(p))
    for perp in (f'{sym}USDT', f'1000{sym}USDT'):
        k = _get(f'https://fapi.binance.com/fapi/v1/klines?symbol={perp}&interval=1h&limit=1&startTime={t0}')
        if k is not None:
            break
    else:
        json.dump(None, open(p, 'w'))
        return None
    kl, t = [], t0
    while t < t1:
        k = _get(f'https://fapi.binance.com/fapi/v1/klines?symbol={perp}&interval=1h&startTime={t}&limit=1500')
        if not k:
            break
        kl += [(int(x[0]), float(x[1]), float(x[5])) for x in k if int(x[0]) < t1]
        t = int(k[-1][0]) + H
        time.sleep(0.15)
    fu, t = [], t0
    while t < t1:
        r = _get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={perp}&startTime={t}&limit=1000')
        if not r:
            break
        fu += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r if int(x['fundingTime']) < t1]
        if len(r) < 1000:
            break
        t = int(r[-1]['fundingTime']) + 1
        time.sleep(0.15)
    d = dict(perp=perp, k=kl, f=fu)
    json.dump(d, open(p, 'w'))
    return d


def short(o, ft, fr, a, b):
    i0, i1 = np.searchsorted(ft, a, side='right'), np.searchsorted(ft, b, side='right')
    return -(o[b] / o[a] - 1), float(fr[i0:i1].sum())


def cluster_ci(net, g, rng):
    ug = np.unique(g)
    idx = [np.flatnonzero(g == w) for w in ug]
    s = np.array([net[i].sum() for i in idx]); n = np.array([i.size for i in idx])
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
    if a.reserved and not json.load(open(OUT)).get('PASA'):
        sys.exit('El descubrimiento no pasó: la reserva no se mira.')
    rng = np.random.default_rng(SEED)
    rows, nodata, novol, ctrl = [], [], 0, []
    for e in announcements():
        ann = dt.datetime.fromtimestamp(e['ann_ms'] / 1000, dt.timezone.utc)
        if (ann >= SPLIT) != a.reserved:
            continue
        t_in = ((e['ann_ms'] + 5 * 60_000) // H + 1) * H
        t_del = int(e['delist'].timestamp() * 1000)
        for s in e['syms']:
            D = fetch(s, e['ann_ms'] - 400 * 86400_000, t_del + 2 * H)
            if D is None:
                nodata.append(s)
                continue
            o = {t: op for t, op, v in D['k']}
            vol = {t: v for t, op, v in D['k']}
            if vol.get(t_in, 0) <= 0:
                novol += 1
                continue
            live = [t for t, op, v in D['k'] if t_in <= t <= t_del and v > 0]
            t_out = t_del if (t_del in o and vol.get(t_del - H, 0) > 0) else live[-1]
            if t_out <= t_in:
                novol += 1
                continue
            ft = np.array([x[0] for x in D['f']], dtype=np.int64); fr = np.array([x[1] for x in D['f']])
            g, f = short(o, ft, fr, t_in, t_out)
            pre = max(t for t in o if t <= e['ann_ms'])
            hit = o[t_in] / o[pre] - 1
            L = (t_out - t_in) // H
            lo_c, hi_c = e['ann_ms'] - 395 * 86400_000, e['ann_ms'] - 30 * 86400_000 - L * H
            starts = [t for t, op, v in D['k'] if lo_c <= t <= hi_c and v > 0 and (t + L * H) in o]
            pool = []
            if starts:
                for t0 in rng.choice(starts, min(len(starts), 400), replace=False):
                    cg, cf = short(o, ft, fr, int(t0), int(t0) + L * H)
                    pool.append(cg + cf - COST)
            ctrl.append(np.array(pool))
            rows.append(dict(sym=s, perp=D['perp'], ann=ann.strftime('%Y-%m-%d %H:%M'), grp=e['ann_ms'], gross=g,
                             fund=f, net=g + f - COST, hours=int(L), early=t_out < t_del, hit=hit))
    net = np.array([x['net'] for x in rows]); n = net.size
    grp = np.array([x['grp'] for x in rows])
    lo, hi, ng = cluster_ci(net, grp, rng)
    ug = np.unique(grp); half = ug[ug.size // 2]
    h1, h2 = float(net[grp < half].mean()), float(net[grp >= half].mean())
    ok_c = [p for p in ctrl if p.size]
    cm = np.sort(np.mean([p[rng.integers(0, p.size, REPS)] for p in ok_c], axis=0))
    p50, p95 = float(cm[REPS // 2]), float(cm[int(.95 * REPS)])
    tag = 'RESERVA 2025-26' if a.reserved else 'DESCUBRIMIENTO 2022-2024'
    print(f'{tag}: n={n} (anuncios {ng}; sin perpetuo {len(nodata)}; sin volumen a la entrada {novol}; '
          f'control sin pool {len(ctrl) - len(ok_c)})')
    print(f'  bruto {np.mean([x["gross"] for x in rows]):+.2%}  funding {np.mean([x["fund"] for x in rows]):+.3%}  '
          f'NETO {net.mean():+.2%}  mediana {np.median(net):+.2%}  ganados {(net > 0).mean():.0%}')
    print(f'  CI95 agrupado por anuncio [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  '
          f'control p50 {p50:+.2%} p95 {p95:+.2%}')
    print(f'  [desc] golpe anuncio→entrada (no operable) {np.mean([x["hit"] for x in rows]):+.2%}  '
          f'horas mediana {np.median([x["hours"] for x in rows]):.0f}  perpetuo cerró antes {sum(x["early"] for x in rows)}/{n}  '
          f'peor {net.min():+.2%}  mejor {net.max():+.2%}')
    for x in sorted(rows, key=lambda r: r['net'])[:3]:
        print(f'  [desc] peor: {x["perp"]} {x["ann"]} neto {x["net"]:+.2%} ({x["hours"]} h)')
    if a.reserved:
        crit = {'media>0': net.mean() > 0, 'CI_agrupado_inf>0': lo > 0, '>control_p95': net.mean() > p95}
    else:
        crit = {'1_n>=25': n >= 25, '2_media>0_CI_agrupado_inf>0': net.mean() > 0 and lo > 0,
                '3_dos_mitades>0': h1 > 0 and h2 > 0, '4_>control_p95': net.mean() > p95,
                '5_>0_costo_pesimista': net.mean() - (PESS - COST) > 0, '6_mediana>0': float(np.median(net)) > 0}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> P53 {'reserva ' if a.reserved else ''}{'PASA' if ok else 'NO PASA'}")
    res = dict(criterio='docs/p53_deslistados_criterio.md (3cac83a)', n=n, net=float(net.mean()),
               median=float(np.median(net)), ci=[lo, hi], halves=[h1, h2], ctrl=[p50, p95], criterios=crit, PASA=ok,
               sin_perpetuo=nodata, rows=rows)
    json.dump(res, open(OUT.replace('.json', '_reserva.json') if a.reserved else OUT, 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
