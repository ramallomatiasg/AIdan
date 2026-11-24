"""P66 — adelanto al roll de commodities: largo USL / corto USO en los días hábiles 1-4 del mes (antes del roll).

Criterio declarado antes de medir: docs/p66_goldman_roll_criterio.md (1750940).
Read-only: sin MT5, no toca la DB. Yahoo chart API (pública) a .cache_p66/.

  python tools/backtest_p66_goldman_roll.py              # 2008-2014
  python tools/backtest_p66_goldman_roll.py --reserved   # 2015 → mar-2020, solo si pasó
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
C = os.path.join(ROOT, '.cache_p66')
OUT = os.path.join(ROOT, 'docs', 'p66_goldman_roll_resultado.json')
COST, PESS = 0.0020, 0.0040
FIRST_M, SPLIT, LAST_M = '2008-01', '2015-01', '2020-03'
BOOT, SEED = 5000, 20261123
P1 = int(dt.datetime(2007, 11, 1).timestamp()); P2 = int(dt.datetime(2020, 5, 1).timestamp())


def fetch(sym):
    os.makedirs(C, exist_ok=True)
    p = os.path.join(C, sym + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    u = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={P1}&period2={P2}&interval=1d'
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                j = json.load(r)['chart']['result'][0]
            break
        except Exception:
            if k == 3:
                raise
            time.sleep(3)
    off = j['meta'].get('gmtoffset', 0)
    adj = j['indicators']['adjclose'][0]['adjclose']
    rows = {dt.datetime.utcfromtimestamp(t + off).strftime('%Y-%m-%d'): a
            for t, a in zip(j['timestamp'], adj) if a}
    json.dump(rows, open(p, 'w'))
    return rows



def windows(lng, sht):
    d = sorted(set(lng) & set(sht))
    a = np.array([lng[x] for x in d]); b = np.array([sht[x] for x in d])
    rel = lambda i, j: (a[j] / a[i] - 1) - (b[j] / b[i] - 1)
    ends = [i for i in range(len(d) - 1) if d[i][:7] != d[i + 1][:7]]
    out = []
    for p, e in zip(ends[:-1], ends[1:]):
        m = d[e][:7]
        if m < FIRST_M or m > LAST_M or e - p < 14:
            continue
        ctrl, j = [], p + 9                      # el día hábil 10 empieza al cierre del 9
        while j + 4 <= e:
            ctrl.append(rel(j, j + 4)); j += 4
        out.append(dict(m=m, ret=float(rel(p, p + 4)), roll=float(rel(p + 4, p + 9)), ctrl=ctrl))
    return out


def boot_mean(x, rng):
    b = np.array([x[rng.integers(0, x.size, x.size)].mean() for _ in range(BOOT)]); b.sort()
    return float(b[int(.025 * BOOT)]), float(b[int(.975 * BOOT)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    w = [r for r in windows(fetch('USL'), fetch('USO')) if (r['m'] >= SPLIT) == a.reserved]
    g = np.array([r['ret'] for r in w]); ex = g - COST; exp_ = g - PESS
    rng = np.random.default_rng(SEED)
    lo, hi = boot_mean(ex, rng)
    h = ex.size // 2
    ctrl_all = np.concatenate([r['ctrl'] for r in w])
    diff = g.mean() - ctrl_all.mean()
    bdd = np.empty(BOOT)
    for k in range(BOOT):
        j = rng.integers(0, len(w), len(w))
        bdd[k] = g[j].mean() - np.concatenate([w[i]['ctrl'] for i in j]).mean()
    bdd.sort(); dlo, dhi = float(bdd[int(.025 * BOOT)]), float(bdd[int(.975 * BOOT)])
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P66 USL-USO {tag}: n={ex.size} meses ({w[0]["m"]} → {w[-1]["m"]})')
    print(f'  neto medio {ex.mean():+.3%}/ventana (≈{ex.mean() * 12:+.2%}/año)  CI95 [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
    print(f'  días 1-4 bruto {g.mean():+.3%} vs control (bloques de 4 días desde el día 10, n={ctrl_all.size}) '
          f'{ctrl_all.mean():+.3%}  diferencia {diff:+.3%}  CI95 [{dlo:+.3%}, {dhi:+.3%}]')
    print(f'  positivas {np.mean(g > 0):.0%}  peor {g.min():+.2%}  días 5-9 (durante el roll) '
          f'{np.mean([r["roll"] for r in w]):+.3%}')
    yrs = {}
    for r, x in zip(w, ex):
        yrs.setdefault(r['m'][:4], []).append(x)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%}' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '5_le_gana_al_resto': diff > 0 and dlo > 0}
    else:
        crit = {'1_n>=70': ex.size >= 70, '2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0,
                '3_dos_mitades>0': ex[:h].mean() > 0 and ex[h:].mean() > 0, '4_pesimista>0': exp_.mean() > 0,
                '5_le_gana_al_resto': diff > 0 and dlo > 0}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P66 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(n=int(ex.size), neto_medio=float(ex.mean()), ci=[lo, hi],
               mitades=[float(ex[:h].mean()), float(ex[h:].mean())], pesimista=float(exp_.mean()),
               bruto=float(g.mean()), control=float(ctrl_all.mean()), diferencia=float(diff),
               ci_diferencia=[dlo, dhi], criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p66_goldman_roll_criterio.md (1750940)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
