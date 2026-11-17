"""P46 — nowcast de inflación de Cleveland vs consenso, posición en EURUSD antes del CPI.

Criterio declarado antes de medir: docs/p46_nowcast_cpi_criterio.md (a4e8af1).
Read-only: sin MT5 (usa .cache_fase2/M15_500000), no toca la DB. Datos públicos cacheados en .cache_p46/.

  python tools/backtest_p46_nowcast_cpi.py              # descubrimiento (jun-2018 → dic-2023)
  python tools/backtest_p46_nowcast_cpi.py --reserved   # solo si el descubrimiento pasó
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p46')
OUT = os.path.join(ROOT, 'docs', 'p46_nowcast_cpi_resultado.json')
NY = ZoneInfo('America/New_York')
PIP, COST, THR = 0.0001, 1.3, 0.05
SPLIT = dt.date(2024, 1, 1)
SEED, BOOT = 20261116, 5000
MONTHS = {m: i for i, m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct',
                                      'Nov', 'Dec'], 1)}


def releases():
    h = open(os.path.join(C, 'investing_cpi69.html'), encoding='utf8', errors='ignore').read()
    i = h.index('"occurrences":[') + len('"occurrences":')
    occ, _ = json.JSONDecoder().raw_decode(h[i:])
    out = []
    for o in occ:
        if o.get('event_id') != 69 or o.get('forecast') is None or o.get('actual') is None:
            continue
        t = dt.datetime.fromisoformat(o['occurrence_time'].replace('Z', '+00:00'))
        m = MONTHS[o['reference_period'][:3]]
        y = t.year - (1 if m > t.month else 0)
        out.append(dict(t=t, ym=(y, m), cons=float(o['forecast']), act=float(o['actual'])))
    return sorted(out, key=lambda r: r['t'])


def nowcasts():
    d = json.load(open(os.path.join(C, 'nowcast_month.json')))
    out = {}
    for ch in d:
        y, m = map(int, ch['chart']['subcaption'].split('-'))
        labels = [c['label'] for c in ch['categories'][0]['category'] if not c.get('vline')]
        ser = next(s for s in ch['dataset'] if s['seriesname'] == 'CPI Inflation')
        vals = [x.get('value') for x in ser['data']]
        pts = []
        for lab, v in zip(labels, vals):
            if not v:
                continue
            mm, dd = map(int, lab.split('/'))
            pts.append((dt.date(y + (1 if mm < m else 0), mm, dd), float(v)))
        out[(y, m)] = sorted(pts)
    return out


def server_ts(t_utc):
    ny = t_utc.astimezone(NY).replace(tzinfo=None)
    return int((ny + dt.timedelta(hours=7)).replace(tzinfo=dt.timezone.utc).timestamp())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    bars = np.load(os.path.join(ROOT, '.cache_fase2', 'M15_500000', 'EURUSD.npy'))
    bt, bo = bars['time'].astype(np.int64), bars['open']
    pos = {int(t): i for i, t in enumerate(bt)}
    nc = nowcasts()
    rows, skipped = [], dict(sin_nowcast=0, sin_vela=0, chico=0)
    for r in releases():
        rel_srv = server_ts(r['t'])
        day0 = rel_srv - rel_srv % 86400
        pts = [v for d_, v in nc.get(r['ym'], []) if d_ < r['t'].date()]
        if not pts:
            skipped['sin_nowcast'] += 1
            continue
        sig = pts[-1] - r['cons']
        if abs(sig) < THR:
            skipped['chico'] += 1
            continue
        side = -1 if sig > 0 else 1                      # + nowcast > consenso ⇒ USD fuerte ⇒ venta EURUSD
        ie, ix, ithr = pos.get(day0 + 3600), pos.get(rel_srv - 900), pos.get(rel_srv + 1800)
        if ie is None or ix is None:
            skipped['sin_vela'] += 1
            continue
        g = side * (bo[ix] - bo[ie]) / PIP
        thr = side * (bo[ithr] - bo[ie]) / PIP if ithr is not None else np.nan
        plac = []
        k, d = 0, day0
        while k < 5:
            d -= 86400
            wd = dt.datetime.utcfromtimestamp(d).weekday()
            if wd >= 5:
                continue
            k += 1
            pe, px = pos.get(d + 3600), pos.get(d + (rel_srv - day0) - 900)
            if pe is not None and px is not None:
                plac.append(side * (bo[px] - bo[pe]) / PIP)
        rows.append(dict(date=r['t'].date().isoformat(), nowcast=pts[-1], cons=r['cons'], act=r['act'], side=side,
                         gross=float(g), net=float(g - COST), through=float(thr - COST),
                         placebo=float(np.mean(plac)) if plac else None))
    sel = [x for x in rows if (dt.date.fromisoformat(x['date']) >= SPLIT) == a.reserved]
    net = np.array([x['net'] for x in sel])
    gross = np.array([x['gross'] for x in sel])
    print(f"  {'RESERVA' if a.reserved else 'DESCUBRIMIENTO'}: n={len(sel)} (saltadas {skipped}, total con señal "
          f"{len(rows)})")
    rng = np.random.default_rng(SEED)
    bs = np.sort(net[rng.integers(0, net.size, (BOOT, net.size))].mean(axis=1))
    lo, hi = float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])
    h = net.size // 2
    h1, h2 = float(net[:h].mean()), float(net[h:].mean())
    signs = rng.choice([-1, 1], (BOOT, gross.size))
    absg = np.abs(gross)                                  # mover la dirección = cambiar el signo del bruto
    rnd = np.sort((signs * absg * np.sign(gross)).mean(axis=1))
    p95 = float(rnd[int(.95 * BOOT)])
    surp = [(np.sign(x['nowcast'] - x['cons']), np.sign(x['act'] - x['cons'])) for x in sel]
    dec = [(s, t) for s, t in surp if t != 0]
    hit = sum(1 for s, t in dec if s == t)
    thr = np.array([x['through'] for x in sel if not np.isnan(x['through'])])
    pl = np.array([x['placebo'] for x in sel if x['placebo'] is not None])
    print(f"  neto media {net.mean():+.2f}p  mediana {np.median(net):+.2f}p  CI95 [{lo:+.2f}, {hi:+.2f}]  "
          f"mitades {h1:+.2f} / {h2:+.2f}  bruto {gross.mean():+.2f}p vs azar p95 {p95:+.2f}p  ganadas "
          f"{(net > 0).mean():.0%}")
    print(f"  descriptivo: el nowcast acierta el signo de la sorpresa {hit}/{len(dec)} ({hit / max(len(dec), 1):.0%}) "
          f"| hasta +30 min DESPUÉS del dato neto {thr.mean():+.2f}p (n={thr.size}) | placebo 5 días previos "
          f"{pl.mean():+.2f}p (bruto)")
    if a.reserved:
        crit = {'reserva_media_neta>0': net.mean() > 0}
    else:
        crit = {'1_n>=30': net.size >= 30, '2_media>0_y_CI_inf>0': net.mean() > 0 and lo > 0,
                '3_dos_mitades>0': h1 > 0 and h2 > 0, '4_bruto>azar_p95': gross.mean() > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f"  >>> P46 {'reserva' if a.reserved else ''}: {'PASA' if ok else 'NO PASA'}")
    res = dict(n=int(net.size), media_neta=float(net.mean()), mediana=float(np.median(net)), ci=[lo, hi],
               mitades=[h1, h2], bruto=float(gross.mean()), azar_p95=p95, acierto_sorpresa=[hit, len(dec)],
               hasta_despues_del_dato=float(thr.mean()) if thr.size else None,
               placebo=float(pl.mean()) if pl.size else None, saltadas=skipped, criterios=crit, PASA=ok,
               filas=sel, criterio='docs/p46_nowcast_cpi_criterio.md (a4e8af1)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
