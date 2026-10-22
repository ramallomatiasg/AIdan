"""
backtest_p5_nr7.py — P5: ruptura del NR7 (y del inside bar, descriptivo) en D1, 20 pares FX.

READ-ONLY. Sin MT5, no toca la DB. Reusa la carga, el re-muestreo a D1, la ejecución fuera del rollover y el
swap de backtest_p2_donchian.py (importados).
Criterio declarado ANTES de medir: docs/p5_nr7_criterio.md (5b18dda). Leer contra eso.

Uso:
    python tools/backtest_p5_nr7.py              # 20 pares de Fase 1
    python tools/backtest_p5_nr7.py --reserved   # 6 reservados: solo si el principal PASÓ
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
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p2_donchian import Sim, load_fx  # noqa: E402

HOLD_DAYS = 3
CONTROL_REPS = 200
SEED = 20261022
OUT = os.path.join(ROOT, 'docs', 'p5_nr7_resultado.json')


def setups(B, kind):
    rng = B['h'] - B['l']
    n = rng.size
    s = np.zeros(n, dtype=bool)
    if kind == 'NR7':
        from numpy.lib.stride_tricks import sliding_window_view
        w = sliding_window_view(rng, 7)
        s[6:] = (rng[6:] <= w.min(axis=1)) & (rng[6:] > 0)
    else:
        s[1:] = (B['h'][1:] < B['h'][:-1]) & (B['l'][1:] > B['l'][:-1])
    return s


class P5:
    def __init__(self, F):
        self.F = F
        self.S = Sim(F, 'D1', 20, 10)       # solo para B, exec_idx, nights y arrays finos
        S = self.S
        self.tod = S.t % 86400

    def exit_px(self, j, fill, d, stop, x):
        """Stop vela M5 por vela M5 desde j (la vela del llenado cuenta como stop si lo toca), si no salida en x."""
        S = self.S
        if (d > 0 and S.l[j] <= stop) or (d < 0 and S.h[j] >= stop):
            return j, stop, 'stop'
        seg_l, seg_h = S.l[j + 1:x], S.h[j + 1:x]
        hit = np.flatnonzero(seg_l <= stop) if d > 0 else np.flatnonzero(seg_h >= stop)
        if hit.size:
            jj = j + 1 + hit[0]
            px = min(S.o[jj], stop) if d > 0 else max(S.o[jj], stop)
            return jj, px, 'stop'
        return x, S.o[x], 'tiempo'

    def pnl(self, j, fill, d, stop, x, R):
        F, S = self.F, self.S
        jx, px, how = self.exit_px(j, fill, d, stop, x)
        gross = d * (px - fill)
        cost = F['comm'] + F['spr'][j] + F['spr'][jx]
        swap = S.nights(j, jx) * (F['swap_long'] if d > 0 else F['swap_short'])
        return dict(j=int(j), jx=int(jx), t=int(S.t[j]), d=int(d), R=R, fill=fill, x=int(x),
                    gross=gross, cost=cost, swap=swap, net=gross - cost + swap, how=how)

    def run(self, kind):
        S = self.S
        B = S.B
        nb = B['h'].size
        sig = setups(B, kind)
        trades, ambiguous, last_bar = [], 0, -1
        for k in np.flatnonzero(sig):
            if k <= last_bar or k + HOLD_DAYS >= nb:
                continue
            day = k + 1
            a, b = B['start'][day], B['end'][day] + 1
            win = np.arange(a, b)
            win = win[(self.tod[win] >= 3600) & (self.tod[win] < 82800)]
            if not win.size:
                continue
            Hk, Lk = B['h'][k], B['l'][k]
            up = S.h[win] >= Hk
            dn = S.l[win] <= Lk
            any_ = np.flatnonzero(up | dn)
            if not any_.size:
                continue
            q = any_[0]
            if up[q] and dn[q]:
                ambiguous += 1
                continue
            j = win[q]
            d = 1 if up[q] else -1
            fill = max(S.o[j], Hk) if d > 0 else min(S.o[j], Lk)
            stop = Lk if d > 0 else Hk
            x = S.exec_idx[k + HOLD_DAYS]
            if x >= S.n or x <= j:
                continue
            tr = self.pnl(j, fill, d, stop, x, Hk - Lk)
            trades.append(tr)
            last_bar = int(np.searchsorted(B['end'], tr['jx']))
        return trades, ambiguous

    def control(self, trades, rng):
        out = []
        for tr in trades:
            d = int(rng.choice([-1, 1]))
            r = self.pnl(tr['j'], tr['fill'], d, tr['fill'] - d * tr['R'], tr['x'], tr['R'])
            out.append(r['net'] / r['R'])
        return out


def summ(tr):
    if not tr:
        return dict(n=0)
    r = lambda k: np.array([x[k] / x['R'] for x in tr])  # noqa: E731
    return dict(n=len(tr), net_R=float(r('net').mean()), gross_R=float(r('gross').mean()),
                cost_R=float(r('cost').mean()), swap_R=float(r('swap').mean()),
                win=float((r('net') > 0).mean()), stop_pct=float(np.mean([x['how'] == 'stop' for x in tr])))


def evaluate(per_pair, models, reserved):
    allt = sorted([x for s in per_pair for x in per_pair[s]], key=lambda x: x['t'])
    r = np.array([x['net'] / x['R'] for x in allt])
    lo, hi, _ = bootstrap_ci(r)
    half = r.size // 2
    h1, h2 = float(r[:half].mean()), float(r[half:].mean())
    pos = sum(1 for s in per_pair if per_pair[s] and np.mean([x['net'] / x['R'] for x in per_pair[s]]) > 0)
    rng = np.random.default_rng(SEED)
    ctrl = np.array([np.mean([v for s in per_pair for v in models[s].control(per_pair[s], rng)])
                     for _ in range(CONTROL_REPS)])
    p95 = float(np.percentile(ctrl, 95))
    if reserved:
        crit = {'oos_media>0': bool(r.mean() > 0), 'oos_>control_p95': bool(r.mean() > p95)}
    else:
        crit = {'1_n>=300': r.size >= 300,
                '2_media>0_CI_inf>0': bool(r.mean() > 0 and lo is not None and lo > 0),
                '3_dos_mitades>0': bool(h1 > 0 and h2 > 0),
                '4_>control_p95': bool(r.mean() > p95),
                '5_>=12/20_pares>0': pos >= 12}
    return dict(n=int(r.size), mean_R=float(r.mean()), ci=[lo, hi], halves=[h1, h2], pos_pairs=pos,
                n_pairs=len(per_pair), control_median=float(np.median(ctrl)), control_p95=p95,
                criterios=crit, PASA=all(crit.values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('principal', {}).get('PASA'):
            sys.exit('El principal NO pasó (o no se corrió): los reservados no se miran.')
        symbols, out_path = RESERVADOS, OUT.replace('.json', '_reservados.json')
    else:
        symbols, out_path = SYMBOLS_FASE1, OUT
    models = {s: P5(load_fx(s)) for s in symbols}
    result = {'criterio': 'docs/p5_nr7_criterio.md (5b18dda)'}
    for kind in ('NR7', 'INSIDE'):
        per_pair, amb = {}, 0
        for s in symbols:
            per_pair[s], a_ = models[s].run(kind)
            amb += a_
        pool = summ([x for s in per_pair for x in per_pair[s]])
        tag = 'PRINCIPAL' if kind == 'NR7' else 'secundario (descriptivo)'
        print(f'\n=== {kind} — {tag}: n={pool["n"]}  neto {pool["net_R"]:+.3f}R  (bruto {pool["gross_R"]:+.3f} '
              f'- costo {pool["cost_R"]:.3f} + swap {pool["swap_R"]:+.3f})  gan {pool["win"]:.0%}  '
              f'stop {pool["stop_pct"]:.0%}  ambiguos {amb}')
        pairs = {s: summ(per_pair[s]) for s in symbols}
        for s in symbols:
            p = pairs[s]
            if p['n']:
                print(f'    {s:7s} n={p["n"]:4d}  neto {p["net_R"]:+.3f}R  bruto {p["gross_R"]:+.3f}  '
                      f'costo {p["cost_R"]:.3f}  swap {p["swap_R"]:+.3f}')
        entry = dict(pool=pool, pares=pairs, ambiguos=amb)
        if kind == 'NR7':
            ev = evaluate(per_pair, models, a.reserved)
            entry['gate'] = ev
            result['principal'] = ev
            print(f'\n  >>> n={ev["n"]} media {ev["mean_R"]:+.4f}R  CI [{ev["ci"][0]:+.4f}, {ev["ci"][1]:+.4f}]  '
                  f'mitades {ev["halves"][0]:+.3f} / {ev["halves"][1]:+.3f}  pares>0 {ev["pos_pairs"]}/'
                  f'{ev["n_pairs"]}  control mediana {ev["control_median"]:+.3f} p95 {ev["control_p95"]:+.3f}')
            for k, v in ev['criterios'].items():
                print(f'      [{"OK " if v else "NO "}] {k}')
            print(f'  >>> {"PASA" if ev["PASA"] else "NO PASA"}')
        result[kind] = entry
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(out_path, ROOT)}')


if __name__ == '__main__':
    main()
