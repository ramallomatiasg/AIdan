"""P79 — ciclo de subastas de la nota a 10 años del Tesoro -> IEF (Lou, Yan & Zhang 2013).

Corto IEF 5 días hábiles antes de la subasta hasta el cierre del día de la subasta; largo del cierre de la subasta a 5
días hábiles después. Criterio declarado antes de medir: docs/p79_subastas_tesoro_criterio.md (df4a706).
Read-only: sin MT5, no toca la DB. Datos: .cache_p79/notes_all.json (TreasuryDirect) y .cache_p64/IEF.json.

  python tools/backtest_p79_subastas_tesoro.py              # 2004 -> 2014
  python tools/backtest_p79_subastas_tesoro.py --reserved   # 2015 -> hoy, solo si pasó
"""
import argparse
import bisect
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
AUC = os.path.join(ROOT, '.cache_p79', 'notes_all.json')
IEF = os.path.join(ROOT, '.cache_p64', 'IEF.json')
OUT = os.path.join(ROOT, 'docs', 'p79_subastas_tesoro_resultado.json')
SIDE, SIDE_P = 0.0005, 0.0010
K, BOOT, SEED, NPLAC = 5, 5000, 20261126, 200
D0, D1, R1 = dt.date(2004, 1, 1), dt.date(2014, 12, 31), dt.date(2026, 12, 31)


def load_auctions():
    d = json.load(open(AUC))
    out = {}
    for x in d:
        if x['type'] != 'Note' or not x['securityTerm'].startswith(('9-Year', '10-Year')):
            continue
        out[dt.date.fromisoformat(x['competitiveAuctionCloseDate'][:10])] = x['reopening'] == 'Yes'
    return out


def trade(px, days, i):
    if i - K < 0 or i + K >= len(days):
        return None
    p0, p1, p2 = px[days[i - K]], px[days[i]], px[days[i + K]]
    return -(p1 / p0 - 1), p2 / p1 - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    lo_d, hi_d = (D1 + dt.timedelta(days=1), R1) if a.reserved else (D0, D1)
    auc = load_auctions()
    raw = json.load(open(IEF))
    days = sorted(raw)
    dset = {dt.date.fromisoformat(k): i for i, k in enumerate(days)}
    px = raw
    idx_auc = sorted(i for d, i in dset.items() if d in auc)
    rows = []
    skipped = 0
    for d in sorted(auc):
        if not (lo_d <= d <= hi_d):
            continue
        if d not in dset:
            skipped += 1
            continue
        t = trade(px, days, dset[d])
        if t is None:
            skipped += 1
            continue
        rows.append((d, auc[d], t[0], t[1]))
    pre = np.array([r[2] for r in rows]); post = np.array([r[3] for r in rows])
    g = pre + post
    ex = g - 4 * SIDE; exp_ = g - 4 * SIDE_P
    n = g.size; h = n // 2
    rng = np.random.default_rng(SEED)
    bs = np.sort([ex[rng.integers(0, n, n)].mean() for _ in range(BOOT)])
    lo, hi = float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])
    # placebo: días hábiles del período a >7 días hábiles de cualquier subasta
    period = [i for k, i in dset.items() if lo_d <= k <= hi_d and K <= i < len(days) - K]
    far = [i for i in period if (lambda j: min(abs(i - idx_auc[j]) for j in (max(j - 1, 0), min(j, len(idx_auc) - 1))))
           (bisect.bisect_left(idx_auc, i)) > 7]
    plac = np.empty(NPLAC)
    for k in range(NPLAC):
        sel = rng.choice(far, n)
        plac[k] = np.mean([sum(trade(px, days, i)) for i in sel])
    p95 = float(np.percentile(plac, 95))
    # superposición de ventanas
    ii = [dset[r[0]] for r in rows]
    overl = sum(1 for x, y in zip(ii[:-1], ii[1:]) if y - x < 2 * K)
    hold = np.array([px[days[i + K]] / px[days[i - K]] - 1 for i in ii])
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P79 subastas 10 años -> IEF {tag}: {n} subastas ({rows[0][0]} -> {rows[-1][0]}), salteadas {skipped}, '
          f'ventanas superpuestas {overl}')
    print(f'  neto {ex.mean():+.3%}/subasta  CI95 [{lo:+.3%}, {hi:+.3%}]  mitades {ex[:h].mean():+.3%} / '
          f'{ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
    print(f'  bruto {g.mean():+.3%} (antes {pre.mean():+.3%} · después {post.mean():+.3%})  placebo media '
          f'{plac.mean():+.3%} p95 {p95:+.3%}  acierto {(g > 0).mean():.1%}')
    print(f'  IEF largo en las mismas 10 ruedas {hold.mean():+.3%}')
    reo = np.array([r[1] for r in rows])
    print(f'  nuevas n={int((~reo).sum())} bruto {g[~reo].mean():+.3%} | reaperturas n={int(reo.sum())} '
          f'bruto {g[reo].mean():+.3%}' if reo.any() and (~reo).any() else '')
    yrs = {}
    for r, x in zip(rows, g):
        yrs.setdefault(r[0].year, []).append(x)
    print('  bruto por año: ' + '  '.join(f'{y} {np.mean(v):+.2%}' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '5_bruto>placebo_p95': g.mean() > p95}
    else:
        crit = {'1_subastas>=80': n >= 80, '2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0,
                '3_dos_mitades>0': ex[:h].mean() > 0 and ex[h:].mean() > 0, '4_pesimista>0': exp_.mean() > 0,
                '5_bruto>placebo_p95': g.mean() > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P79 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(subastas=int(n), neto=float(ex.mean()), ci=[lo, hi], mitades=[float(ex[:h].mean()),
                   float(ex[h:].mean())], pesimista=float(exp_.mean()), bruto=float(g.mean()),
                   antes=float(pre.mean()), despues=float(post.mean()), placebo_p95=p95,
                   criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
                   criterio='docs/p79_subastas_tesoro_criterio.md (df4a706)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
