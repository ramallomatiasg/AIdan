"""P71 — reversión acciones/bonos de fin de MES (meses que no cierran trimestre), SOLO la reserva 2019 → oct-2026.

Criterio declarado antes de medir: docs/p71_reversion_fin_de_mes_criterio.md (97448a8).
Read-only: sin MT5, no toca la DB. Reusa el cache y la función `windows` de P64 (regla idéntica).

  python tools/backtest_p71_reversion_fin_de_mes.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p64_rebalanceo_trimestral as p64  # noqa: E402

ROOT = p64.ROOT
OUT = os.path.join(ROOT, 'docs', 'p71_reversion_fin_de_mes_resultado.json')
p64.LAST_M = '2026-10'
SPLIT = '2019-01'


def main():
    spy = p64.fetch('SPY')
    res = {}
    for bsym in ('TLT', 'IEF'):
        w = [r for r in p64.windows(spy, p64.fetch(bsym), quarter=False)
             if r['m'] >= SPLIT and int(r['m'][5:7]) % 3 != 0]
        g = np.array([r['ret'] for r in w]); ex = g - p64.COST; exp_ = g - p64.PESS
        rng = np.random.default_rng(p64.SEED)
        lo, hi = p64.boot_mean(ex, rng)
        h = ex.size // 2
        ctrl_all = np.concatenate([r['ctrl'] for r in w])
        diff = g.mean() - ctrl_all.mean()
        bdd = np.empty(p64.BOOT)
        for k in range(p64.BOOT):
            j = rng.integers(0, len(w), len(w))
            bdd[k] = g[j].mean() - np.concatenate([w[i]['ctrl'] for i in j]).mean()
        bdd.sort(); dlo, dhi = float(bdd[int(.025 * p64.BOOT)]), float(bdd[int(.975 * p64.BOOT)])
        print(f'== SPY vs {bsym} RESERVA: n={ex.size} meses ({w[0]["m"]} → {w[-1]["m"]})')
        print(f'  neto medio {ex.mean():+.3%}/ventana (≈{ex.mean() * 8:+.2%}/año)  CI95 [{lo:+.3%}, {hi:+.3%}]  '
              f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
        print(f'  bruto {g.mean():+.3%} vs control (n={ctrl_all.size}) {ctrl_all.mean():+.3%}  '
              f'diferencia {diff:+.3%}  CI95 [{dlo:+.3%}, {dhi:+.3%}]')
        print(f'  positivas {np.mean(g > 0):.0%}  peor {g.min():+.2%}  mejor {g.max():+.2%}')
        yrs = {}
        for r, x in zip(w, ex):
            yrs.setdefault(r['m'][:4], []).append(x)
        print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%}' for y, v in sorted(yrs.items())))
        if bsym != 'TLT':
            continue
        crit = {'1_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '2_le_gana_al_resto': diff > 0 and dlo > 0,
                '3_pesimista>0': exp_.mean() > 0}
        for k, v in crit.items():
            print(f"    [{'OK ' if v else 'NO '}] {k}")
        ok = bool(all(crit.values()))
        print(f'  >>> P71 RESERVA: {"PASA" if ok else "NO PASA"}')
        res = dict(n=int(ex.size), neto_medio=float(ex.mean()), ci=[lo, hi],
                   mitades=[float(ex[:h].mean()), float(ex[h:].mean())], pesimista=float(exp_.mean()),
                   bruto=float(g.mean()), control=float(ctrl_all.mean()), diferencia=float(diff),
                   ci_diferencia=[dlo, dhi], peor=float(g.min()), criterios={k: bool(v) for k, v in crit.items()},
                   PASA=ok, criterio='docs/p71_reversion_fin_de_mes_criterio.md (97448a8)')
    json.dump(res, open(OUT, 'w'), indent=1)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
