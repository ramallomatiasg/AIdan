"""
backtest_p10_fade_donchian.py — P10: fade del canal Donchian D1 20/10, SOLO en los 6 pares reservados.

READ-ONLY. Sin MT5, no toca la DB. Reusa las piezas de backtest_p2_donchian.py (importadas).
Criterio declarado ANTES de medir: docs/p10_fade_donchian_criterio.md (d9dd03d). Leer contra eso.

El fade es el trade de P2 con la dirección invertida: entra en la misma vela, sale con la MISMA regla de
canal que la posición de P2 que fadea (que para el fade es el objetivo), y el stop 2·ATR va del otro lado.

Uso:
    python tools/backtest_p10_fade_donchian.py --insample   # 20 pares de P2 (descriptivo: sanity espejo)
    python tools/backtest_p10_fade_donchian.py              # 6 reservados, UNA sola vez
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_p2_donchian import Sim, load_fx, summarize, evaluate_main, MAIN  # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'p10_fade_donchian_resultado.json')
MIN_N = 150
MIN_POS_PAIRS = 4


class FadeSim(Sim):
    def __init__(self, F, tf, N, M):
        super().__init__(F, tf, N, M)
        self.sig = -self.sig

    def trade(self, k, d):
        # La salida del fade es la del trade de P2 en la dirección -d: se intercambian las listas de salida
        # y se llama al trade de P2 (que elige exitL para d>0). El stop sigue la dirección d real.
        self.exitL, self.exitS = self.exitS, self.exitL
        try:
            return super().trade(k, d)
        finally:
            self.exitL, self.exitS = self.exitS, self.exitL


def run(symbols):
    tf, N, M = MAIN
    fx = {s: load_fx(s) for s in symbols}
    sims = {s: FadeSim(fx[s], tf, N, M) for s in symbols}
    per_pair = {s: sims[s].run_system() for s in symbols}
    allt = [x for s in per_pair for x in per_pair[s]]
    summ = summarize(allt)
    pairs = {s: summarize(per_pair[s]) for s in symbols}
    print(f'\n=== FADE D1 {N}/{M}  pool: n={summ["n"]}  neto {summ["net_R"]:+.3f}R  '
          f'(bruto {summ["gross_R"]:+.3f} - costo {summ["cost_R"]:.3f} + swap {summ["swap_R"]:+.3f})  '
          f'gan {summ["win"]:.0%}  stop {summ["stop_pct"]:.0%}  noches med {summ["nights_med"]:.0f}')
    for s in symbols:
        p = pairs[s]
        if p['n']:
            print(f'    {s:7s} n={p["n"]:4d}  neto {p["net_R"]:+.3f}R  bruto {p["gross_R"]:+.3f}  '
                  f'swap {p["swap_R"]:+.3f}')
    ev = evaluate_main(per_pair, sims)
    # el gate de P2 está escrito para 20 pares / n>=300; acá se re-evalúan 1 y 5 con el criterio de P10
    ev['criterios']['1_n>=300'] = None
    ev['criterios'].pop('1_n>=300')
    ev['criterios'].pop('5_>=12/20_pares>0')
    ev['criterios'][f'1_n>={MIN_N}'] = ev['n'] >= MIN_N
    ev['criterios'][f'5_>={MIN_POS_PAIRS}/6_pares>0'] = ev['pos_pairs'] >= MIN_POS_PAIRS
    ev['PASA'] = all(ev['criterios'].values())
    print(f'\n  >>> n={ev["n"]} media {ev["mean_R"]:+.4f}R  CI [{ev["ci"][0]:+.4f}, {ev["ci"][1]:+.4f}]  '
          f'mitades {ev["halves"][0]:+.3f} / {ev["halves"][1]:+.3f}  pares>0 {ev["pos_pairs"]}/{ev["n_pairs"]}  '
          f'control mediana {ev["control_median"]:+.3f} p95 {ev["control_p95"]:+.3f}')
    for k, v in sorted(ev['criterios'].items()):
        print(f'      [{"OK " if v else "NO "}] {k}')
    return dict(pool=summ, pares=pairs, gate=ev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--insample', action='store_true', help='20 pares de P2 (descriptivo, no puntúa)')
    a = ap.parse_args()
    prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
    if a.insample:
        print('IN-SAMPLE (20 pares de P2) — DESCRIPTIVO, no puntúa el gate')
        prev['insample_descriptivo'] = run(SYMBOLS_FASE1)
    else:
        if 'reservados' in prev:
            sys.exit('Los reservados ya se corrieron (una sola vez, criterio P10). No se re-corren.')
        print('RESERVADOS (fuera de muestra) — ESTA corrida decide')
        res = run(RESERVADOS)
        print(f'  >>> {"PASA" if res["gate"]["PASA"] else "NO PASA"}')
        prev['reservados'] = res
    with open(OUT, 'w') as f:
        json.dump(prev, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
