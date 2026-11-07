"""
backtest_p25_cambio_de_mes.py — P25: cambio de mes (turn-of-the-month) en índices, 2020-2026.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p1/M15`.
Criterio declarado ANTES de medir: docs/p25_cambio_de_mes_criterio.md (ec547c9). Leer contra eso.

Largo del cierre del contado del último día hábil del mes al cierre del 3er día hábil del mes siguiente.
Control: ventanas de 3 días hábiles que arrancan en un día hábil al azar del mismo año fuera del cambio de mes.

Uso:
    python tools/backtest_p25_cambio_de_mes.py
"""
import json
import os
import sys
from datetime import date, timedelta

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p24_prima_nocturna import SESSION, SWAP_PCT, load, net, server_ts  # noqa: E402

MAIN = ['US30', 'USTEC']
DESC = ['DE40']
CONTROL_REPS = 2000
MIN_N = 60
HOLD = 3  # días hábiles después del último del mes
SEED = 20261106
OUT = os.path.join(ROOT, 'docs', 'p25_cambio_de_mes_resultado.json')


def trading_days(P, sym):
    """Lista de (fecha, índice de la vela de cierre del contado) para cada día hábil con dato."""
    zone, hclose, _ = SESSION[sym]
    t = P['t']
    from datetime import datetime, timezone
    d = datetime.fromtimestamp(int(t[0]), timezone.utc).date() + timedelta(days=1)
    last = datetime.fromtimestamp(int(t[-1]), timezone.utc).date()
    out = []
    while d <= last:
        if d.weekday() < 5:
            i = P['idx'].get(server_ts(d, hclose, zone))
            if i is not None:
                out.append((d, i))
        d += timedelta(days=1)
    return out


def ev(P, days, a, b, sw):
    da, i = days[a]
    db, j = days[b]
    nn = (db - da).days
    gross = (P['o'][j] - P['o'][i]) / P['o'][i] * 100
    return net(P, i, j, nn, sw), gross, nn


def run(sym, rng):
    P = load(sym)
    sw = SWAP_PCT[sym]
    days = trading_days(P, sym)
    # posición del último día hábil de cada mes (el siguiente día es de otro mes)
    starts = [k for k in range(len(days) - 1) if days[k][0].month != days[k + 1][0].month and k + HOLD < len(days)]
    # el primer mes del cache puede estar incompleto: exigir que el día anterior al último sea del mismo mes
    starts = [k for k in starts if k > 0]
    in_tom = set()
    for k in starts:
        for m in range(k - 1, k + HOLD + 1):
            in_tom.add(m)
    vals, gross, half, rows = [], [], [], []
    for k in starts:
        v, g, nn = ev(P, days, k, k + HOLD, sw)
        vals.append(v)
        gross.append(g)
        half.append(v + nn * sw / 2)
        rows.append((days[k][0].isoformat(), v))
    vals, gross, half = np.array(vals), np.array(gross), np.array(half)
    # control: mismo año, inicio en día hábil fuera del cambio de mes, misma duración en días hábiles
    by_year = {}
    for k in range(len(days) - HOLD):
        if k in in_tom or any(m in in_tom for m in range(k, k + HOLD + 1)):
            continue
        by_year.setdefault(days[k][0].year, []).append(ev(P, days, k, k + HOLD, sw)[0])
    by_year = {y: np.array(v) for y, v in by_year.items()}
    tot = np.zeros(CONTROL_REPS)
    for k in starts:
        c = by_year[days[k][0].year]
        tot += c[rng.integers(0, c.size, CONTROL_REPS)]
    ctrl = np.sort(tot / len(starts))
    return dict(sym=sym, n=int(vals.size), mean=float(vals.mean()), median=float(np.median(vals)),
                win=float((vals > 0).mean()), gross_mean=float(gross.mean()), half_swap_mean=float(half.mean()),
                ctrl_p50=float(ctrl[CONTROL_REPS // 2]), ctrl_p95=float(ctrl[int(0.95 * CONTROL_REPS)]),
                ctrl_pool_n=int(sum(v.size for v in by_year.values())), series=rows)


def main():
    rng = np.random.default_rng(SEED)
    res = {s: run(s, rng) for s in MAIN + DESC}
    print(f"{'sym':6}{'n':>5}{'neto%':>9}{'bruto%':>9}{'1/2swap%':>10}{'gan':>6}{'ctrl p50':>10}{'ctrl p95':>10}")
    for s in MAIN + DESC:
        r = res[s]
        print(f"{s:6}{r['n']:>5}{r['mean']:>+9.3f}{r['gross_mean']:>+9.3f}{r['half_swap_mean']:>+10.3f}"
              f"{r['win']:>6.0%}{r['ctrl_p50']:>+10.3f}{r['ctrl_p95']:>+10.3f}"
              f"{'' if s in MAIN else '  (descriptivo)'}")
    pool = sorted([(d, v) for s in MAIN for d, v in res[s]['series']])
    pv = np.array([v for _, v in pool])
    lo, hi, _ = bootstrap_ci(pv)
    half = pv.size // 2
    h1, h2 = float(pv[:half].mean()), float(pv[half:].mean())
    crit = {
        f'1_n>={MIN_N}_por_instrumento': all(res[s]['n'] >= MIN_N for s in MAIN),
        '2_media>0_CI_inf>0': bool(pv.mean() > 0 and lo is not None and lo > 0),
        '3_dos_mitades>0': h1 > 0 and h2 > 0,
        '4_>control_p95_en_los_dos': all(res[s]['mean'] > res[s]['ctrl_p95'] for s in MAIN),
        '5_US30_y_USTEC>0': all(res[s]['mean'] > 0 for s in MAIN),
    }
    print(f"\nPOOL US30+USTEC: n={pv.size} media {pv.mean():+.3f}%/evento  CI [{lo:+.3f}, {hi:+.3f}]  "
          f"mitades {h1:+.3f} / {h2:+.3f}")
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    for s in res:
        res[s].pop('series')
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p25_cambio_de_mes_criterio.md (ec547c9)', por_sym=res, pool=dict(
            n=int(pv.size), mean=float(pv.mean()), ci=[lo, hi], halves=[h1, h2]), criterios=crit, PASA=ok),
            f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
