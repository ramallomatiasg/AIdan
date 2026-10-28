"""
backtest_p21_broker.py — P21: ¿un broker más barato (Fusion Zero, USD 4,50 ida y vuelta vs IC USD 7) salva alguna
estrategia ya medida? Criterio declarado ANTES de medir: docs/p21_broker_barato_criterio.md.

READ-ONLY: sin MT5, no toca la DB. Lee los resultados ya guardados en docs/ (escritorio) y re-corre el arnés de P9
(importado, no copiado) con la comisión de Fusion sobre el cache `.cache_p1/M15`.
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import backtest_p9_a1_instrumentos as p9  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

IC_RT, FUSION_RT = 7.0, 4.5
SCALE = FUSION_RT / IC_RT
OUT = os.path.join(ROOT, 'docs', 'p21_broker_resultado.json')


def _load(name):
    with open(os.path.join(ROOT, 'docs', name), encoding='utf-8') as f:
        return json.load(f)


def desk():
    """Paso 1: bruto − costo con Fusion − swap, con los números ya medidos de cada estrategia."""
    rows = []
    f3 = _load('fase3b_a1_resultado.json')['por_horizonte']
    for H in ('48', '96'):
        r = f3[H]
        net = r['bruto'] - r['comision'] * SCALE - r['spread'] + r['swap']
        rows.append((f'A1 reversión 2σ, 20 pares M5, H{H} (Fase 3b)', r['bruto'], r['neto'], net))
    p9r = _load('p9_a1_instrumentos_resultado.json')['por_horizonte']
    for H in ('16', '32'):
        e = p9r[H]['por_sym']['EURUSD']
        fusion_cost = e['costo'] - 0.7 * (1 - SCALE)            # en EUR/USD la comisión de IC son 0,70 pips
        rows.append((f'A1 reversión 2σ, EURUSD M15, H{H} (ancla de P9)', e['bruto'], e['neto'],
                     e['bruto'] - fusion_cost))
    p4 = _load('p4_lead_lag_resultado.json')
    rows.append(('Lead-lag de la cesta USD (P4)', 0.13, p4['6']['neto'], 0.13 - 0.55))
    p3 = _load('p3_rango_asiatico_resultado.json')['tp_1W']['pares']
    g = np.mean([v['gross_R'] for v in p3.values()])
    c = np.mean([v['cost_R'] for v in p3.values()])
    rows.append(('Rango asiático → Londres, en R (P3)', g, g - c, g - c * SCALE))
    e3 = _load('fase4_planes_resultado.json')['candidatos']['E3a_usd_pre_fix']
    rows.append(('USD antes del fixing de Londres (Fase 4 E3a)', None, e3['neto'], e3['neto'] + 0.7 * (1 - SCALE)))
    return rows


def remeasure():
    """Paso 2: el arnés de P9 con la comisión de Fusion (FX y oro; índices no tienen comisión en ninguno)."""
    p9.COMM_RT_USD = {k: (v * SCALE if v else v) for k, v in p9.COMM_RT_USD.items()}
    data = {s: p9.load(s) for s in [p9.ANCHOR] + p9.NEW}
    eu = data[p9.ANCHOR]['med_range'] / 0.0001
    pps = {s: data[s]['med_range'] / eu for s in data}
    out = {}
    for H in (16, p9.H_MAIN):
        rows = {s: p9.run_sym(data[s], H, pps[s]) for s in data}
        ev = p9.pool_eval([rows[s] for s in p9.NEW])
        pos = sum(1 for s in p9.NEW if rows[s]['net'].size and rows[s]['net'].mean() > 0)
        crit = {f'1_n>={p9.MIN_N}': ev['n'] >= p9.MIN_N,
                '2_media>0_CI_inf>0': bool(ev['neto'] > 0 and ev['ci'][0] is not None and ev['ci'][0] > 0),
                '3_dos_mitades>0': ev['mitades'][0] > 0 and ev['mitades'][1] > 0,
                '4_>control_p95': ev['neto'] > ev['control_p95'],
                f'5_>={p9.MIN_POS}/4_instrumentos>0': pos >= p9.MIN_POS}
        eur = rows[p9.ANCHOR]
        net = eur['net'][np.argsort(eur['t'])]
        lo, hi, _ = bootstrap_ci(net)
        half = net.size // 2
        ctrl = np.sort(eur['ctrl_sum'] / max(net.size, 1))
        out[H] = dict(pool=dict(ev, pos=pos, criterios=crit, PASA=all(crit.values())),
                      eurusd=dict(n=int(net.size), neto=float(net.mean()), ci=[lo, hi],
                                  mitades=[float(net[:half].mean()), float(net[half:].mean())],
                                  control_p95=float(ctrl[int(0.95 * ctrl.size)])))
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print('=' * 92)
    print(f'P21 — broker más barato: Fusion Zero USD {FUSION_RT} vs IC USD {IC_RT} ida y vuelta (comisión × {SCALE:.3f})')
    print('=' * 92)
    print('\nPASO 1 — escritorio (pips por operación salvo P3, en R):')
    print(f"  {'estrategia':55} {'bruto':>7} {'neto IC':>8} {'neto Fusion':>12}")
    rows = desk()
    for name, g, n_ic, n_fu in rows:
        print(f"  {name:55} {('%+.3f' % g) if g is not None else '   -':>7} {n_ic:>+8.3f} {n_fu:>+12.3f}"
              f"  {'→ re-medir' if n_fu > 0 else 'cerrado'}")
    print('\nPASO 2 — re-medición por el arnés de P9 con la comisión de Fusion:')
    rem = remeasure()
    for H, r in rem.items():
        ev, e = r['pool'], r['eurusd']
        print(f"  H{H}: POOL oro+índices n={ev['n']} neto {ev['neto']:+.3f} CI [{ev['ci'][0]:+.3f}, {ev['ci'][1]:+.3f}]"
              f" mitades {ev['mitades'][0]:+.3f}/{ev['mitades'][1]:+.3f} p95 azar {ev['control_p95']:+.3f}"
              f" ⇒ {'PASA' if ev['PASA'] else 'NO PASA'}")
        print(f"       EURUSD solo (descriptivo) n={e['n']} neto {e['neto']:+.3f} CI [{e['ci'][0]:+.3f}, {e['ci'][1]:+.3f}]"
              f" mitades {e['mitades'][0]:+.3f}/{e['mitades'][1]:+.3f} p95 azar {e['control_p95']:+.3f}")
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(dict(criterio='docs/p21_broker_barato_criterio.md (d401247)',
                       escritorio=[dict(estrategia=a, bruto=b, neto_ic=c, neto_fusion=d) for a, b, c, d in rows],
                       remedicion={str(k): v for k, v in rem.items()}), f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
