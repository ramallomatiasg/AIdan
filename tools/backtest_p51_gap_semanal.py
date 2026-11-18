"""
backtest_p51_gap_semanal.py — P51: cierre del gap de apertura semanal en FX (20 pares M5).

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000/`.
Criterio declarado ANTES de medir: docs/p51_gap_semanal_criterio.md (9500745). Leer contra eso.

Uso:
    python tools/backtest_p51_gap_semanal.py              # descubrimiento (20 pares)
    python tools/backtest_p51_gap_semanal.py --reserved   # solo si el descubrimiento PASÓ
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import SYMBOLS, bootstrap_ci  # noqa: E402
from tools.backtest_fase4_planes import load_pair, swap_pips  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402

DISC = [s for s in SYMBOLS if s not in RESERVADOS]
RES_LEFT = ['GBPNZD', 'NZDCHF', 'NZDCAD', 'GBPCAD']
THR = 0.5
CONTROL_REPS = 2000
MIN_N = 150
PESS = 0.3
SEED = 20261117
OUT = os.path.join(ROOT, 'docs', 'p51_gap_semanal_resultado.json')
OUT_RES = os.path.join(ROOT, 'docs', 'p51_gap_semanal_resultado_reservados.json')


def sim(P, e, F, dirn, horizon_end):
    """Desde la vela e (entrada en su open). Sale al tocar F o en el open de la 1ra vela >= horizon_end.
    Devuelve (indice_salida, precio_salida, toco) o None si no hay vela de salida."""
    utc = P['utc']
    k_end = int(np.searchsorted(utc, horizon_end, side='left'))
    if k_end >= utc.size:
        return None
    hi, lo = P['h'][e:k_end], P['l'][e:k_end]
    hit = (lo <= F) if dirn < 0 else (hi >= F)
    if hit.any():
        k = e + int(np.argmax(hit))
        return k, F, True
    return k_end, P['o'][k_end], False


def run_pair(sym, thr, rng=None):
    P = load_pair(sym)
    utc, pip, comm = P['utc'], P['pip'], P['spec']['commission_pips']
    gaps = np.where(np.diff(utc) > 24 * 3600)[0]
    day_idx = np.searchsorted(P['ud'], P['day'])
    ev, closed_1h, dropped, n_weeks = [], 0, 0, 0
    for i in gaps:
        j = i + 1
        F, A = P['c'][i], P['o'][j]
        adr = P['adr'][day_idx[j]]
        if not np.isfinite(adr) or adr <= 0:
            continue
        n_weeks += 1
        gap = A - F
        if abs(gap) <= thr * adr:
            continue
        dirn = -1 if gap > 0 else 1
        e = int(np.searchsorted(utc, utc[j] + 3600, side='left'))
        if e >= utc.size:
            dropped += 1
            continue
        first = slice(j, e)
        if (dirn < 0 and P['l'][first].min() <= F) or (dirn > 0 and P['h'][first].max() >= F):
            closed_1h += 1
            continue
        E = P['o'][e]
        r = sim(P, e, F, dirn, utc[e] + 24 * 3600)
        if r is None:
            dropped += 1
            continue
        k, X, touched = r
        gross = dirn * (X - E) / pip
        cost = comm + P['spr'][e] - float(swap_pips(P, e, k, dirn))
        # control: misma distancia, dirección al azar (se precalculan los dos lados)
        D = abs(F - E)
        alt = {}
        for dd in (1, -1):
            T = E + dd * D
            rr = sim(P, e, T, dd, utc[e] + 24 * 3600)
            if rr is None:
                alt = None
                break
            alt[dd] = dd * (rr[1] - E) / pip - (comm + P['spr'][e] - float(swap_pips(P, e, rr[0], dd)))
        if alt is None:
            dropped += 1
            continue
        ev.append(dict(t=int(utc[e]), sym=sym, gross=gross, net=gross - cost, touched=touched,
                       gap_adr=abs(gap) / adr, ctrl=(alt[1], alt[-1])))
    return ev, dict(weeks=n_weeks, closed_1h=closed_1h, dropped=dropped)


def summary(ev, rng, label):
    ev = sorted(ev, key=lambda e: e['t'])
    v = np.array([e['net'] for e in ev])
    g = np.array([e['gross'] for e in ev])
    if v.size == 0:
        print(f'{label}: n=0')
        return dict(n=0)
    lo, hi, _ = bootstrap_ci(v)
    half = v.size // 2
    h1, h2 = float(v[:half].mean()) if half else float('nan'), float(v[half:].mean())
    C = np.array([e['ctrl'] for e in ev])                       # n x 2
    pick = rng.integers(0, 2, (CONTROL_REPS, v.size))
    cm = np.sort(np.where(pick == 0, C[:, 0], C[:, 1]).mean(1))
    p50, p95 = float(cm[CONTROL_REPS // 2]), float(cm[int(0.95 * CONTROL_REPS)])
    touch = float(np.mean([e['touched'] for e in ev]))
    print(f'{label}: n={v.size}  bruto {g.mean():+.2f}p  neto {v.mean():+.2f}p  ganados {(v > 0).mean():.0%}  '
          f'toca F {touch:.0%}  CI [{lo:+.2f}, {hi:+.2f}]  mitades {h1:+.2f}/{h2:+.2f}  '
          f'control p50 {p50:+.2f} p95 {p95:+.2f}')
    by_year = {}
    for e in ev:
        by_year.setdefault(datetime.fromtimestamp(e['t'], timezone.utc).year, []).append(e['net'])
    print('   neto por año: ' + '  '.join(f'{y} {np.mean(x):+.2f} (n={len(x)})' for y, x in sorted(by_year.items())))
    return dict(n=int(v.size), gross=float(g.mean()), net=float(v.mean()), win=float((v > 0).mean()),
                touch=touch, ci=[lo, hi], halves=[h1, h2], ctrl_p50=p50, ctrl_p95=p95,
                by_year={int(y): float(np.mean(x)) for y, x in by_year.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    rng = np.random.default_rng(SEED)
    if a.reserved:
        with open(OUT) as f:
            if not json.load(f).get('PASA'):
                sys.exit('El descubrimiento NO pasó: los reservados no se abren.')
        allev = []
        for s in RES_LEFT:
            ev, _ = run_pair(s, THR)
            allev += ev
            summary(ev, rng, s)
        tot = summary(allev, rng, 'RESERVADOS')
        ok = tot['n'] > 0 and tot['net'] > 0 and (tot['n'] < 40 or tot['ci'][0] > 0)
        print(f">>> reservados {'PASA' if ok else 'NO PASA'}")
        with open(OUT_RES, 'w') as f:
            json.dump(dict(total=tot, PASA=ok), f, indent=1, default=float)
        return
    allev, per, info, desc025 = [], {}, {}, []
    for s in DISC:
        ev, inf = run_pair(s, THR)
        allev += ev
        info[s] = inf
        per[s] = dict(n=len(ev), net=float(np.mean([e['net'] for e in ev])) if ev else None)
        print(f"{s}: semanas {inf['weeks']}  señales operadas {len(ev)}  cerrados 1ra hora {inf['closed_1h']}  "
              f"descartados {inf['dropped']}  neto {per[s]['net'] if ev else float('nan'):+.2f}p")
        ev2, _ = run_pair(s, 0.25)
        desc025 += ev2
    tot = summary(allev, rng, 'DESCUBRIMIENTO 20 pares (0,5·ADR)')
    d025 = summary(desc025, rng, '[desc] umbral 0,25·ADR')
    elig = [s for s in DISC if per[s]['n'] >= 5]
    pos = sum(per[s]['net'] > 0 for s in elig)
    print(f'pares con n>=5: {len(elig)}, con media neta > 0: {pos}')
    crit = {
        f'1_n>={MIN_N}': tot.get('n', 0) >= MIN_N,
        '2_media>0_CI_inf>0': bool(tot.get('n') and tot['net'] > 0 and tot['ci'][0] > 0),
        '3_dos_mitades>0': bool(tot.get('n') and all(h > 0 for h in tot['halves'])),
        '4_>control_p95': bool(tot.get('n') and tot['net'] > tot['ctrl_p95']),
        '5_>0_costo_pesimista': bool(tot.get('n') and tot['net'] - PESS > 0),
        '6_>=12_pares>0': pos >= 12,
    }
    for k, ok in crit.items():
        print(f"    [{'OK ' if ok else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p51_gap_semanal_criterio.md (9500745)', total=tot, por_par=per, info=info,
                       desc_umbral_025=d025, pares_pos=f'{pos}/{len(elig)}', criterios=crit, PASA=ok),
                  f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
