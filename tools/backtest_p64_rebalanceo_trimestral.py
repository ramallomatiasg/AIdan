"""P64 — rebalanceo de fin de trimestre: últimos 5 días hábiles, en contra de lo que más subió (SPY vs TLT).

Criterio declarado antes de medir: docs/p64_rebalanceo_trimestral_criterio.md (27a0e7d).
Read-only: sin MT5, no toca la DB. Yahoo chart API (pública) a .cache_p64/.

  python tools/backtest_p64_rebalanceo_trimestral.py              # 2004-2018
  python tools/backtest_p64_rebalanceo_trimestral.py --reserved   # 2019 → 2026-T3, solo si pasó
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
C = os.path.join(ROOT, '.cache_p64')
OUT = os.path.join(ROOT, 'docs', 'p64_rebalanceo_trimestral_resultado.json')
COST, PESS = 0.0010, 0.0020
SPLIT, LAST_M = '2019-01', '2026-09'
BOOT, SEED = 5000, 20261123
P1 = int(dt.datetime(2003, 12, 1).timestamp()); P2 = int(dt.datetime(2026, 11, 21).timestamp())


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


def windows(eq, bd, quarter=True):
    d = sorted(set(eq) & set(bd))
    a = np.array([eq[x] for x in d]); b = np.array([bd[x] for x in d])
    ends = [i for i in range(len(d) - 1) if d[i][:7] != d[i + 1][:7]]       # último día hábil de cada mes completo
    if quarter:
        ends = [i for i in ends if int(d[i][5:7]) % 3 == 0]
    out = []
    for p, e in zip(ends[:-1], ends[1:]):
        m = d[e][:7]
        if m > LAST_M:
            continue
        s = e - 5
        rel = lambda i, j: (a[j] / a[i] - 1) - (b[j] / b[i] - 1)
        D = rel(p, s)
        sg = -np.sign(D)
        ret = sg * rel(s, e)
        ctrl, j = [], s
        while j - 5 >= p + 1:
            st = j - 5
            Dc = rel(p, st) if st > p else 0.0
            if Dc != 0:
                ctrl.append(-np.sign(Dc) * rel(st, j))
            j -= 5
        out.append(dict(m=m, ret=float(ret), D=float(D), ctrl=ctrl))
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
    spy = fetch('SPY')
    res = {}
    for bsym in ('TLT', 'IEF'):
        w = [r for r in windows(spy, fetch(bsym)) if (r['m'] >= SPLIT) == a.reserved]
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
        print(f'== SPY vs {bsym} {tag}: n={ex.size} trimestres ({w[0]["m"]} → {w[-1]["m"]})')
        print(f'  neto medio {ex.mean():+.3%}/ventana (≈{ex.mean() * 4:+.2%}/año)  CI95 [{lo:+.3%}, {hi:+.3%}]  '
              f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
        print(f'  fin de trimestre bruto {g.mean():+.3%} vs control (bloques de 5 días, n={ctrl_all.size}) '
              f'{ctrl_all.mean():+.3%}  diferencia {diff:+.3%}  CI95 [{dlo:+.3%}, {dhi:+.3%}]')
        big = np.median(np.abs([r['D'] for r in w]))
        gb = np.array([r['ret'] for r in w if abs(r['D']) > big])
        print(f'  positivas {np.mean(g > 0):.0%}  peor {g.min():+.2%}  |D|>mediana: {gb.mean():+.3%} (n={gb.size})')
        mw = [r for r in windows(spy, fetch(bsym), quarter=False)
              if (r['m'] >= SPLIT) == a.reserved and int(r['m'][5:7]) % 3 != 0]
        print(f'  placebo fines de mes NO trimestrales: {np.mean([r["ret"] for r in mw]):+.3%} (n={len(mw)})')
        yrs = {}
        for r, x in zip(w, ex):
            yrs.setdefault(r['m'][:4], []).append(x)
        print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%}' for y, v in sorted(yrs.items())))
        if bsym != 'TLT':
            continue
        if a.reserved:
            crit = {'2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '5_le_gana_al_resto': diff > 0 and dlo > 0}
        else:
            crit = {'1_n>=50': ex.size >= 50, '2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0,
                    '3_dos_mitades>0': ex[:h].mean() > 0 and ex[h:].mean() > 0, '4_pesimista>0': exp_.mean() > 0,
                    '5_le_gana_al_resto': diff > 0 and dlo > 0}
        for k, v in crit.items():
            print(f"    [{'OK ' if v else 'NO '}] {k}")
        ok = bool(all(crit.values()))
        print(f'  >>> P64 {tag}: {"PASA" if ok else "NO PASA"}')
        res = dict(n=int(ex.size), neto_medio=float(ex.mean()), ci=[lo, hi],
                   mitades=[float(ex[:h].mean()), float(ex[h:].mean())], pesimista=float(exp_.mean()),
                   bruto=float(g.mean()), control=float(ctrl_all.mean()), diferencia=float(diff),
                   ci_diferencia=[dlo, dhi], criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
                   criterio='docs/p64_rebalanceo_trimestral_criterio.md (27a0e7d)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
