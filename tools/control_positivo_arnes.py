"""P0 del registro de propuestas (9-oct-2026): CONTROL POSITIVO del arnes de Fase 2.

Pregunta: ¿el arnes que dijo NO PASA en las Fases 2-6 es capaz de decir PASA cuando
hay un edge? Si no lo detecta, todos los NO PASA quedan en duda.

Metodo: mismas piezas del arnes (simulate, net_of_costs, sl_tp_for, random_control,
evaluate_session — IMPORTADAS, no copiadas), pero las senales salen de un ORACULO con
precision conocida q: en una vela al azar se mira el signo real de close[i+hold]-close[i]
y se acierta con probabilidad q. q=0,50 = sin edge (debe dar NO PASA); q>0,50 = edge
sintetico (debe dar PASA a partir de cierto q). Se reporta el q minimo que detecta.

Criterio declarado ANTES de correr:
  - q=0,50 -> NO PASA (si da PASA, el arnes tiene un sesgo a favor).
  - q=1,00 -> PASA con neto muy positivo (si no, el arnes esta roto).
  - Curva monotona en q. Se reporta el q minimo con PASA = sensibilidad del arnes.

Read-only: lee el cache .cache_fase2/ (sin MT5), no escribe la DB. Solo imprime.
Uso: python tools/control_positivo_arnes.py [--tf M15] [--n 1500] [--reps 50]
"""
import argparse
import os
import random
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import tools.backtest_fase2 as f2  # noqa: E402
from tools.backtest_multi_symbol import simulate  # noqa: E402

SYMS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'EURJPY', 'EURAUD']


def oracle_rows(q, candles, spec, profile, sym, n, rng):
    pip = spec['pip']
    hold = profile['hold']
    lo, hi = f2.WARMUP, len(candles) - hold - 2
    netos, times, n_long = [], [], 0
    for _ in range(n):
        i = rng.randint(lo, hi)
        true_up = candles[i + hold]['close'] > candles[i]['close']
        right = rng.random() < q
        d = 'CALL' if (true_up == right) else 'PUT'
        n_long += d == 'CALL'
        sl, tp = f2.sl_tp_for(profile, candles, i, pip)
        r = simulate(i, candles, d, sl, tp, hold, pip)
        netos.append(f2.net_of_costs(r, i, candles, d, spec))
        times.append(candles[i]['time_unix'])
    p_long = n_long / n
    ctrl = f2.random_control(n, p_long, candles, spec, profile, pip, sym, f'oracle{q}')
    t = np.asarray(times)
    return {'symbol': sym, 'n': n, 'netos': np.asarray(netos), 'times': t,
            't_first': int(t.min()), 't_last': int(t.max()), 'control': ctrl,
            'p_long': round(p_long, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='M15')
    ap.add_argument('--profile', default='live')
    ap.add_argument('--n', type=int, default=1500)
    ap.add_argument('--reps', type=int, default=50)
    ap.add_argument('--qs', default='0.50,0.52,0.55,0.60,0.70,1.00')
    a = ap.parse_args()
    f2.CONTROL_REPS = a.reps
    f2.BOOTSTRAP_REPS = 2000
    cache = os.path.join(ROOT, '.cache_fase2', f'{a.tf}_500000')
    profile = f2.PROFILES_F2[a.profile]
    data = {s: f2.load_symbol(s, cache) for s in SYMS}
    print(f'CONTROL POSITIVO — arnes Fase 2, {a.tf}, perfil {a.profile} {profile}')
    print(f'{len(SYMS)} pares x n={a.n} senales, control {a.reps} reps\n')
    print(f"{'q':>5} {'neto':>8} {'CI95':>20} {'mit1':>7} {'mit2':>7} {'ctl_p95':>8}  veredicto")
    for q in [float(x) for x in a.qs.split(',')]:
        rng = random.Random(f'oracle|{q}')
        rows = [oracle_rows(q, c, sp, profile, s, a.n, rng) for s, (c, sp) in data.items()]
        r = f2.evaluate_session(rows)
        ci = r['ci95']
        print(f"{q:5.2f} {r['pooled_neto']:8.3f} [{ci[0]:8.3f},{ci[1]:8.3f}] "
              f"{r['mitad_1']:7.2f} {r['mitad_2']:7.2f} {r['control_p95']:8.3f}  {r['veredicto']}")


if __name__ == '__main__':
    main()
