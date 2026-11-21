"""P61 (sUSDe de Ethena) y P62 (sDAI de Sky) contra la letra del Tesoro a 3 meses.

Criterios declarados antes de medir: docs/p61_susde_criterio.md (937f963), docs/p62_sdai_criterio.md (08ee6ed).
Read-only: sin MT5, no toca la DB. Precios públicos de DefiLlama coins; letra FRED DTB3 (.cache_p50/dtb3.json).

  python tools/backtest_p61_p62_ahorro.py --p 61              # descubrimiento
  python tools/backtest_p61_p62_ahorro.py --p 61 --reserved   # solo si pasó
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
TB = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
SPLIT = dt.date(2025, 1, 1)
STEP, BLOCK, BOOT, SEED = 28, 3, 5000, 20261120
CFG = {
    61: dict(name='sUSDe', coin='coingecko:ethena-staked-usde', start=dt.date(2024, 3, 20), cost=0.005, pess=0.015,
             dd=0.10, crit='docs/p61_susde_criterio.md (937f963)', extra=None, out='p61_susde'),
    62: dict(name='sDAI', coin='coingecko:savings-dai', start=dt.date(2023, 10, 12), cost=0.003, pess=0.01,
             dd=0.05, crit='docs/p62_sdai_criterio.md (08ee6ed)',
             extra=('sUSDS', 'ethereum:0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD'), out='p62_sdai'),
}


def _get(u):
    for k in range(6):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                                     timeout=60).read())
        except Exception:
            if k == 5:
                raise
            time.sleep(3 + 3 * k)


def series(coin, cache):
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    if os.path.exists(cache):
        return {dt.date.fromisoformat(k): v for k, v in json.load(open(cache)).items()}
    out, t = {}, int(dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    now = time.time()
    while t < now:
        r = _get(f'https://coins.llama.fi/chart/{coin}?start={t}&span=300&period=1d')
        p = list(r.get('coins', {}).values())
        if p:
            for q in p[0]['prices']:
                out[dt.datetime.utcfromtimestamp(q['timestamp']).date().isoformat()] = q['price']
        t += 300 * 86400
        time.sleep(0.3)
    json.dump(out, open(cache, 'w'))
    return {dt.date.fromisoformat(k): v for k, v in out.items()}


def tranches(px, tb, start, lo, hi, cost):
    tbd = sorted(tb)
    days = sorted(d for d in px if d >= start)
    rows, d0 = [], days[0]
    while True:
        d1 = d0 + dt.timedelta(days=STEP)
        # precio del día exacto o el último disponible antes (la serie diaria de DefiLlama puede tener huecos)
        a = max((d for d in days if d <= d0), default=None); b = max((d for d in days if d <= d1), default=None)
        if d1 > days[-1]:
            break
        if lo <= d0 < hi and a and b and b > a:
            n = (b - a).days
            bills = [tb[x] for x in tbd if a.isoformat() <= x <= b.isoformat()] or \
                    [tb[max(x for x in tbd if x <= a.isoformat())]]
            bill = float(np.mean(bills)) / 100
            r = px[b] / px[a] - 1
            rows.append(dict(d0=a, days=n, r=r, bill=bill, prem=r - (bill + cost) * n / 365))
        d0 = d1
    return rows


def ann(rows, key='prem'):
    return sum(x[key] for x in rows) / sum(x['days'] for x in rows) * 365


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--p', type=int, required=True, choices=(61, 62))
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    c = CFG[a.p]
    out = os.path.join(ROOT, 'docs', c['out'] + '_resultado.json')
    if a.reserved:
        prev = json.load(open(out)) if os.path.exists(out) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    cache = os.path.join(ROOT, f'.cache_p{a.p}', 'px.json')
    px = series(c['coin'], cache)
    tb = json.load(open(TB))
    lo, hi = (SPLIT, dt.date(2100, 1, 1)) if a.reserved else (c['start'], SPLIT)
    rows = tranches(px, tb, c['start'], lo, hi, c['cost'])
    rows_p = tranches(px, tb, c['start'], lo, hi, c['pess'])
    prem = np.array([x['prem'] for x in rows]); days = np.array([x['days'] for x in rows])
    pa = ann(rows); pp = ann(rows_p); ra = ann(rows, 'r')
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(prem.size / BLOCK))
    st = rng.integers(0, prem.size - BLOCK + 1, (BOOT, nb))
    idx = (st[:, :, None] + np.arange(BLOCK)).reshape(BOOT, -1)[:, :prem.size]
    bs = np.sort(prem[idx].sum(axis=1) / days[idx].sum(axis=1) * 365)
    cl, ch = float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])
    h = prem.size // 2
    h1, h2 = ann(rows[:h]), ann(rows[h:])
    # caída máxima diaria del precio dentro del período
    dd_days = sorted(d for d in px if rows[0]['d0'] <= d <= rows[-1]['d0'] + dt.timedelta(days=STEP))
    v = np.array([px[d] for d in dd_days])
    dd = float(np.max(1 - v / np.maximum.accumulate(v)))
    dr = v[1:] / v[:-1] - 1
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f"== P{a.p} {c['name']} {tag}: {rows[0]['d0']} → {rows[-1]['d0']}  n={len(rows)} tramos de {STEP} días  "
          f"letra media {np.mean([x['bill'] for x in rows]):.2%}")
    print(f'  rendimiento {ra:+.2%}/año  premio neto {pa:+.2%}/año  CI95 [{cl:+.2%}, {ch:+.2%}]  mitades {h1:+.2%} / '
          f'{h2:+.2%}  pesimista {pp:+.2%}')
    print(f'  caída máx diaria {dd:.2%}  peor día {dr.min():+.2%}  peor tramo {prem.min():+.2%}  tramos con premio<0 '
          f'{(prem < 0).sum()}/{prem.size}')
    yrs = {}
    for x in rows:
        yrs.setdefault(x['d0'].year, []).append(x)
    print('  por año (rendimiento / premio): ' + '  '.join(f'{y} {ann(v, "r"):+.1%} / {ann(v):+.1%}' for y, v in sorted(yrs.items())))
    if a.reserved and c['extra']:
        en, ec = c['extra']
        epx = series(ec, os.path.join(ROOT, f'.cache_p{a.p}', 'px_extra.json'))
        er = tranches(epx, tb, min(epx), lo, hi, c['cost'])
        if er:
            print(f'  descriptivo (no decide) {en}: {len(er)} tramos, rendimiento {ann(er, "r"):+.2%}/año, premio {ann(er):+.2%}/año')
    if a.reserved:
        crit = {'premio>0': pa > 0, 'CI_inf>0': cl > 0, f'caida_max<{c["dd"]:.0%}': dd < c['dd']}
    else:
        crit = {'1_premio>0': pa > 0, '2_CI_inf>0': cl > 0, '3_dos_mitades>0': h1 > 0 and h2 > 0,
                f'4_caida_max<{c["dd"]:.0%}': dd < c['dd'], '5_pesimista>0': pp > 0}
    for k, val in crit.items():
        print(f"    [{'OK ' if val else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P{a.p} {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(n=len(rows), rendimiento_anual=ra, premio_anual=pa, ci=[cl, ch], mitades=[h1, h2], pesimista=pp,
               caida_max=dd, por_anio={str(y): [ann(v, 'r'), ann(v)] for y, v in yrs.items()},
               criterios={k: bool(val) for k, val in crit.items()}, PASA=ok, criterio=c['crit'])
    path = out.replace('.json', '_reserva.json') if a.reserved else out
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
