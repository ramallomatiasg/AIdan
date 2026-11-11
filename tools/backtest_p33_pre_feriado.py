"""
backtest_p33_pre_feriado.py — P33: día pre-feriado en índices de EE.UU., 2020-2026.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p1/M15`.
Criterio declarado ANTES de medir: docs/p33_pre_feriado_criterio.md (20f0527). Leer contra eso.

Largo del cierre del contado (16:00 ET) del día hábil anterior al pre-feriado al cierre del pre-feriado
(12:45 ET si ese día cierra temprano). Control: mismo año y mismo día de la semana, días que no son
pre-feriado.

Uso:
    python tools/backtest_p33_pre_feriado.py
    python tools/backtest_p33_pre_feriado.py --selftest   # calendario de feriados contra fechas conocidas
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p24_prima_nocturna import SWAP_PCT, load, net, server_ts  # noqa: E402

MAIN = ['US30', 'USTEC']
Z = 'America/New_York'
CLOSE, EARLY = (16, 0), (12, 45)
CONTROL_REPS = 2000
MIN_N = 50
SEED = 20261111
OUT = os.path.join(ROOT, 'docs', 'p33_pre_feriado_resultado.json')


def _nth(y, m, wd, n):
    d = date(y, m, 1)
    d += timedelta((wd - d.weekday()) % 7)
    return d + timedelta(7 * (n - 1))


def _last_mon(y, m):
    d = date(y, m + 1, 1) - timedelta(1)
    while d.weekday() != 0:
        d -= timedelta(1)
    return d


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    return date(y, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)


def _obs(d):
    return d - timedelta(1) if d.weekday() == 5 else d + timedelta(1) if d.weekday() == 6 else d


def nyse_holidays(y):
    H = []
    ny = date(y, 1, 1)
    if ny.weekday() == 6:
        H.append(ny + timedelta(1))
    elif ny.weekday() < 5:
        H.append(ny)  # sábado: no se observa
    H += [_nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _easter(y) - timedelta(2), _last_mon(y, 5)]
    if y >= 2022:
        H.append(_obs(date(y, 6, 19)))
    H += [_obs(date(y, 7, 4)), _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), _obs(date(y, 12, 25))]
    return sorted(H)


def selftest():
    known = [date(2021, 4, 2), date(2021, 12, 24), date(2022, 6, 20), date(2023, 1, 2), date(2023, 7, 4),
             date(2024, 3, 29), date(2024, 11, 28), date(2025, 4, 18), date(2026, 7, 3), date(2026, 5, 25)]
    allh = {h for y in range(2020, 2027) for h in nyse_holidays(y)}
    for k in known:
        assert k in allh, k
    for no in [date(2021, 12, 31), date(2021, 6, 18), date(2022, 1, 3), date(2025, 1, 9)]:
        assert no not in allh, no
    assert all(len(nyse_holidays(y)) in (9, 10) for y in range(2020, 2027))
    print('selftest OK')


def prev_bday(d, hol):
    d -= timedelta(1)
    while d.weekday() > 4 or d in hol:
        d -= timedelta(1)
    return d


def day_ret(P, d, hol, sw, allow_early):
    """Cierre del día hábil anterior -> cierre de d. None si falta una vela."""
    p = prev_bday(d, hol)
    i = P['idx'].get(server_ts(p, CLOSE, Z))
    j = P['idx'].get(server_ts(d, CLOSE, Z))
    early = False
    if j is None and allow_early:
        j = P['idx'].get(server_ts(d, EARLY, Z))
        early = True
    if i is None or j is None:
        return None
    nn = (d - p).days
    return net(P, i, j, nn, sw), (P['o'][j] - P['o'][i]) / P['o'][i] * 100, early


def run(sym, rng):
    P = load(sym)
    sw = SWAP_PCT[sym]
    first = datetime.fromtimestamp(int(P['t'][0]), timezone.utc).date() + timedelta(days=3)
    last = datetime.fromtimestamp(int(P['t'][-1]), timezone.utc).date()
    hol = {h for y in range(first.year - 1, last.year + 2) for h in nyse_holidays(y)}
    pre = {prev_bday(h, hol): h for h in hol}
    ev, dropped = [], 0
    for d, h in sorted(pre.items()):
        if not (first <= d <= last):
            continue
        r = day_ret(P, d, hol, sw, True)
        if r is None:
            dropped += 1
            continue
        ev.append(dict(d=d, h=h, net=r[0], gross=r[1], early=r[2]))
    # control: mismo año, mismo día de la semana, no pre-feriado ni feriado
    pool = {}
    d = first
    while d <= last:
        if d.weekday() < 5 and d not in hol and d not in pre:
            r = day_ret(P, d, hol, sw, False)
            if r is not None:
                pool.setdefault((d.year, d.weekday()), []).append(r[0])
        d += timedelta(1)
    pool = {k: np.array(v) for k, v in pool.items()}
    tot = np.zeros(CONTROL_REPS)
    for e in ev:
        c = pool[(e['d'].year, e['d'].weekday())]
        tot += c[rng.integers(0, c.size, CONTROL_REPS)]
    ctrl = np.sort(tot / len(ev))
    v = np.array([e['net'] for e in ev])
    g = np.array([e['gross'] for e in ev])
    ne = np.array([e['net'] for e in ev if not e['early']])
    return dict(sym=sym, n=int(v.size), dropped=dropped, mean=float(v.mean()), median=float(np.median(v)),
                win=float((v > 0).mean()), gross_mean=float(g.mean()),
                n_no_early=int(ne.size), mean_no_early=float(ne.mean()),
                ctrl_mean=float(ctrl.mean()), ctrl_p95=float(ctrl[int(0.95 * CONTROL_REPS)]),
                ctrl_days=int(sum(c.size for c in pool.values())), events=ev)


def main():
    if '--selftest' in sys.argv:
        return selftest()
    selftest()
    rng = np.random.default_rng(SEED)
    res = {s: run(s, rng) for s in MAIN}
    print(f"{'sym':6}{'n':>4}{'desc':>5}{'neto%':>9}{'bruto%':>9}{'gan':>6}{'sin temprano':>14}{'ctrl med':>10}{'ctrl p95':>10}")
    for s in MAIN:
        r = res[s]
        print(f"{s:6}{r['n']:>4}{r['dropped']:>5}{r['mean']:>+9.3f}{r['gross_mean']:>+9.3f}{r['win']:>6.0%}"
              f"{r['mean_no_early']:>+10.3f} ({r['n_no_early']}){r['ctrl_mean']:>+10.3f}{r['ctrl_p95']:>+10.3f}")
    # serie por evento: promedio de los instrumentos que tengan ese feriado
    by = {}
    for s in MAIN:
        for e in res[s]['events']:
            by.setdefault(e['d'], []).append(e['net'])
    days = sorted(k for k, v in by.items() if len(v) == len(MAIN))
    pv = np.array([np.mean(by[k]) for k in days])
    lo, hi, _ = bootstrap_ci(pv)
    half = pv.size // 2
    h1, h2 = float(pv[:half].mean()), float(pv[half:].mean())
    crit = {
        f'1_n>={MIN_N}_por_instrumento': all(res[s]['n'] >= MIN_N for s in MAIN),
        '2_por_evento_media>0_CI_inf>0': bool(pv.mean() > 0 and lo is not None and lo > 0),
        '3_dos_mitades>0': h1 > 0 and h2 > 0,
        '4_>control_p95_en_los_dos': all(res[s]['mean'] > res[s]['ctrl_p95'] for s in MAIN),
        '5_US30_y_USTEC>0': all(res[s]['mean'] > 0 for s in MAIN),
    }
    print(f"\nPOR EVENTO (media US30+USTEC): n={pv.size} media {pv.mean():+.3f}%  CI [{lo:+.3f}, {hi:+.3f}]  "
          f"ganados {(pv > 0).mean():.0%}  mitades {h1:+.3f} / {h2:+.3f}")
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    for s in res:
        res[s].pop('events')
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p33_pre_feriado_criterio.md (20f0527)', por_sym=res, por_evento=dict(
            n=int(pv.size), mean=float(pv.mean()), ci=[lo, hi], halves=[h1, h2], win=float((pv > 0).mean())),
            criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
