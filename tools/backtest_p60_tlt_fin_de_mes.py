"""P60 — extensión de duración de fin de mes: largo TLT los últimos 3 días hábiles del mes, contra la letra y el resto.

Criterio declarado antes de medir: docs/p60_tlt_fin_de_mes_criterio.md (d799319).
Read-only: sin MT5, no toca la DB. Yahoo chart API (pública) a .cache_p60/; letra: .cache_p50/dtb3.json.

  python tools/backtest_p60_tlt_fin_de_mes.py              # 2004-2018
  python tools/backtest_p60_tlt_fin_de_mes.py --reserved   # 2019 → oct-2026, solo si pasó
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
C = os.path.join(ROOT, '.cache_p60')
TB = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p60_tlt_fin_de_mes_resultado.json')
COST, PESS = 0.0005, 0.0010
SPLIT, LAST_M = '2019-01', '2026-10'
BOOT, SEED = 5000, 20261119
P1 = int(dt.datetime(2003, 12, 1).timestamp()); P2 = int(dt.datetime(2026, 11, 19).timestamp())


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


def windows(px, tb, tbd):
    d = sorted(px); c = np.array([px[x] for x in d])
    ends = [i for i in range(len(d) - 1) if d[i][:7] != d[i + 1][:7]]   # último día hábil de cada mes completo
    out = []
    for a, e in zip(ends[:-1], ends[1:]):
        m = d[e][:7]
        if m > LAST_M:
            continue
        s = e - 3
        bill = tb[max(x for x in tbd if x <= d[s])] / 100
        fm = c[e] / c[s] - 1
        last1 = c[e] / c[e - 1] - 1
        ctrl, j = [], s
        while j - 3 >= a:
            ctrl.append(c[j] / c[j - 3] - 1); j -= 3
        out.append(dict(m=m, fm=fm, bill3=bill * 3 / 252, last1=last1, ctrl=ctrl))
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
    tb = json.load(open(TB)); tbd = sorted(tb)
    res = {}
    for sym in ('TLT', 'IEF'):
        w = [r for r in windows(fetch(sym), tb, tbd) if (r['m'] >= SPLIT) == a.reserved]
        fm = np.array([r['fm'] for r in w]); b3 = np.array([r['bill3'] for r in w])
        ex = fm - b3 - COST; exp_ = fm - b3 - PESS
        rng = np.random.default_rng(SEED)
        lo, hi = boot_mean(ex, rng)
        h = ex.size // 2
        ctrl_all = np.concatenate([r['ctrl'] for r in w])
        diff = fm.mean() - ctrl_all.mean()
        bd = np.empty(BOOT)
        for k in range(BOOT):
            j = rng.integers(0, len(w), len(w))
            bd[k] = fm[j].mean() - np.concatenate([w[i]['ctrl'] for i in j]).mean()
        bd.sort(); dlo, dhi = float(bd[int(.025 * BOOT)]), float(bd[int(.975 * BOOT)])
        yrs = {}
        for r, x in zip(w, ex):
            yrs.setdefault(r['m'][:4], []).append(x)
        tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
        print(f'== {sym} {tag}: n={ex.size} ventanas ({w[0]["m"]} → {w[-1]["m"]})')
        print(f'  exceso medio {ex.mean():+.3%}/ventana (≈{ex.mean() * 12:+.2%}/año)  CI95 [{lo:+.3%}, {hi:+.3%}]  '
              f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
        print(f'  fin de mes bruto {fm.mean():+.3%} vs control (bloques de 3 días, n={ctrl_all.size}) '
              f'{ctrl_all.mean():+.3%}  diferencia {diff:+.3%}  CI95 [{dlo:+.3%}, {dhi:+.3%}]')
        print(f'  positivas {np.mean(fm > 0):.0%}  peor ventana {fm.min():+.2%}  último día solo '
              f'{np.mean([r["last1"] for r in w]):+.3%}')
        print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%}' for y, v in sorted(yrs.items())))
        if sym != 'TLT':
            continue
        if a.reserved:
            crit = {'2_exceso>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '5_le_gana_al_resto': diff > 0 and dlo > 0}
        else:
            crit = {'1_n>=100': ex.size >= 100, '2_exceso>0_y_CI_inf>0': ex.mean() > 0 and lo > 0,
                    '3_dos_mitades>0': ex[:h].mean() > 0 and ex[h:].mean() > 0, '4_pesimista>0': exp_.mean() > 0,
                    '5_le_gana_al_resto': diff > 0 and dlo > 0}
        for k, v in crit.items():
            print(f"    [{'OK ' if v else 'NO '}] {k}")
        ok = bool(all(crit.values()))
        print(f'  >>> P60 {tag}: {"PASA" if ok else "NO PASA"}')
        res = dict(n=int(ex.size), exceso_medio=float(ex.mean()), ci=[lo, hi],
                   mitades=[float(ex[:h].mean()), float(ex[h:].mean())], pesimista=float(exp_.mean()),
                   fin_de_mes_bruto=float(fm.mean()), control=float(ctrl_all.mean()), diferencia=float(diff),
                   ci_diferencia=[dlo, dhi], criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
                   criterio='docs/p60_tlt_fin_de_mes_criterio.md (d799319)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
