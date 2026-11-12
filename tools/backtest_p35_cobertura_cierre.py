"""
backtest_p35_cobertura_cierre.py — P35: demanda de cobertura al cierre de EE.UU. (Baltussen et al. 2021).

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p1/M15`.
Criterio declarado ANTES de medir: docs/p35_cobertura_cierre_criterio.md (b1150ca). Leer contra eso.

Señal = retorno del cierre anterior (16:00 ET) a las 15:30 ET; si cae en el quintil extremo del
descubrimiento, seguir esa dirección de 15:30 a 16:00 ET.

Uso:
    python tools/backtest_p35_cobertura_cierre.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p24_prima_nocturna import load, server_ts  # noqa: E402
from tools.backtest_p33_pre_feriado import nyse_holidays, prev_bday  # noqa: E402

MAIN = ['US30', 'USTEC']
Z = 'America/New_York'
CLOSE, LAST = (16, 0), (15, 30)
REPS = 2000
MIN_N = 100
SEED = 20261111
OUT = os.path.join(ROOT, 'docs', 'p35_cobertura_cierre_resultado.json')


def early_close(d, hol):
    if d.month == 7 and d.day == 3:
        return True
    if d.month == 12 and d.day == 24:
        return True
    thanks = [h for h in hol if h.year == d.year and h.month == 11]
    return any(d == h + timedelta(1) for h in thanks)


def days(sym):
    P = load(sym)
    first = datetime.fromtimestamp(int(P['t'][0]), timezone.utc).date() + timedelta(3)
    last = datetime.fromtimestamp(int(P['t'][-1]), timezone.utc).date()
    hol = {h for y in range(first.year - 1, last.year + 2) for h in nyse_holidays(y)}
    out = []
    d = first
    while d <= last:
        if d.weekday() < 5 and d not in hol and not early_close(d, hol):
            p = prev_bday(d, hol)
            a = P['idx'].get(server_ts(p, CLOSE, Z))
            b = P['idx'].get(server_ts(d, LAST, Z))
            c = P['idx'].get(server_ts(d, CLOSE, Z))
            if a is not None and b is not None and c is not None:
                o = P['o']
                out.append(dict(d=d, r=(o[b] - o[a]) / o[a],
                                last=(o[c] - o[b]) / o[b] * 1e4,
                                cost=(P['spr'][b] + P['spr'][c]) / o[b] * 1e4))
        d += timedelta(1)
    return out


def run(sym, rng):
    ev = days(sym)
    half = len(ev) // 2
    rd = np.array([e['r'] for e in ev[:half]])
    lo, hi = np.percentile(rd, 20), np.percentile(rd, 80)
    trades = []
    for k, e in enumerate(ev):
        s = 1 if e['r'] > hi else -1 if e['r'] < lo else 0
        if s:
            trades.append(dict(d=e['d'], s=s, res=k >= half, gross=s * e['last'], net=s * e['last'] - e['cost']))
    R = [t for t in trades if t['res']]
    sg = np.array([t['s'] for t in R])
    lastv = np.array([t['gross'] * t['s'] for t in R])
    cost = np.array([t['gross'] - t['net'] for t in R])
    ctrl = np.sort([(rng.permutation(sg) * lastv - cost).mean() for _ in range(REPS)])
    x = np.array([e['r'] for e in ev]) * 1e4
    y = np.array([e['last'] for e in ev])
    slope = float(np.polyfit(x, y, 1)[0])
    net = np.array([t['net'] for t in R])
    return dict(sym=sym, days=len(ev), p20=float(lo), p80=float(hi), trades=trades,
                n_res=len(R), mean_res=float(net.mean()), gross_res=float(np.mean([t['gross'] for t in R])),
                win_res=float((net > 0).mean()), ctrl_p95=float(ctrl[int(0.95 * REPS)]),
                ctrl_mean=float(ctrl.mean()), slope_bps_per_bps=slope,
                n_desc=sum(1 for t in trades if not t['res']),
                mean_desc=float(np.mean([t['net'] for t in trades if not t['res']])))


def per_day(res, part, side=None):
    by = {}
    for s in MAIN:
        for t in res[s]['trades']:
            if t['res'] == part and (side is None or t['s'] == side):
                by.setdefault(t['d'], []).append(t['net'])
    ks = sorted(by)
    return ks, np.array([np.mean(by[k]) for k in ks])


def main():
    rng = np.random.default_rng(SEED)
    res = {s: run(s, rng) for s in MAIN}
    print(f"{'sym':6}{'dias':>6}{'n desc':>8}{'neto desc':>11}{'n res':>7}{'neto res':>10}{'bruto':>8}{'gan':>6}"
          f"{'ctrl p95':>10}{'pend':>8}")
    for s in MAIN:
        r = res[s]
        print(f"{s:6}{r['days']:>6}{r['n_desc']:>8}{r['mean_desc']:>+11.2f}{r['n_res']:>7}{r['mean_res']:>+10.2f}"
              f"{r['gross_res']:>+8.2f}{r['win_res']:>6.0%}{r['ctrl_p95']:>+10.2f}{r['slope_bps_per_bps']:>+8.4f}")
    ks, pv = per_day(res, True)
    _, pd_desc = per_day(res, False)
    lo, hi, _ = bootstrap_ci(pv)
    _, lng = per_day(res, True, 1)
    _, sht = per_day(res, True, -1)
    yrs = {}
    for k, v in zip(ks, pv):
        yrs.setdefault(k.year, []).append(v)
    crit = {
        f'1_n_res>={MIN_N}_por_indice': all(res[s]['n_res'] >= MIN_N for s in MAIN),
        '2_reserva_media>0_CI_inf>0': bool(pv.mean() > 0 and lo is not None and lo > 0),
        '3_descubrimiento>0': bool(pd_desc.mean() > 0),
        '4_>control_p95_en_los_dos': all(res[s]['mean_res'] > res[s]['ctrl_p95'] for s in MAIN),
        '5_largos_y_cortos>0': bool(lng.mean() > 0 and sht.mean() > 0),
    }
    print(f"\nRESERVA por dia: n={pv.size} media {pv.mean():+.2f} bps  CI [{lo:+.2f}, {hi:+.2f}]  ganados "
          f"{(pv > 0).mean():.0%}  largos {lng.mean():+.2f} (n={lng.size})  cortos {sht.mean():+.2f} (n={sht.size})")
    print(f"DESCUBRIMIENTO por dia: n={pd_desc.size} media {pd_desc.mean():+.2f} bps")
    print('por año (reserva):', {y: round(float(np.mean(v)), 2) for y, v in sorted(yrs.items())})
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    for s in res:
        res[s].pop('trades')
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p35_cobertura_cierre_criterio.md (b1150ca)', por_sym=res,
                       reserva=dict(n=int(pv.size), mean=float(pv.mean()), ci=[lo, hi], largos=float(lng.mean()),
                                    cortos=float(sht.mean()), por_anio={y: float(np.mean(v)) for y, v in yrs.items()}),
                       descubrimiento=dict(n=int(pd_desc.size), mean=float(pd_desc.mean())),
                       criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
