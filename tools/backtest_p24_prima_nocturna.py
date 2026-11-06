"""
backtest_p24_prima_nocturna.py — P24: prima nocturna (cierre -> apertura) en índices, 2020-2026.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p1/M15`.
Criterio declarado ANTES de medir: docs/p24_prima_nocturna_criterio.md (f55821a). Leer contra eso.

Hora del server = Nueva York + 7 h (verificado en P12). Swap ACTUAL de MT5 (5-nov) como % del precio por noche.

Uso:
    python tools/backtest_p24_prima_nocturna.py
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_p1', 'M15')
MAIN = ['US30', 'USTEC']
DESC = ['DE40']
# swap largo por lote y noche / precio de hoy (MT5 symbol_info + tick, 5-nov-2026), en % del precio
SWAP_PCT = {'US30': 14.416 / 53495.2 * 100, 'USTEC': 7.687 / 28210.6 * 100, 'DE40': 6.07 / 26528.6 * 100}
SESSION = {  # (zona, hora entrada local, hora salida local)
    'US30': ('America/New_York', (16, 0), (9, 30)),
    'USTEC': ('America/New_York', (16, 0), (9, 30)),
    'DE40': ('Europe/Berlin', (17, 30), (9, 0)),
}
NY = ZoneInfo('America/New_York')
CONTROL_REPS = 2000
MIN_N = 250
SEED = 20261105
OUT = os.path.join(ROOT, 'docs', 'p24_prima_nocturna_resultado.json')


def load(sym):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.meta.json')) as f:
        meta = json.load(f)
    t = r['time'].astype(np.int64)
    return dict(sym=sym, t=t, o=r['open'].astype(np.float64), spr=r['spread'].astype(np.float64) * meta['point'],
                idx={int(x): i for i, x in enumerate(t)})


def server_ts(d, hm, zone):
    """Hora local (zona) del día d -> timestamp del server (NY wall clock + 7 h, guardado como UTC)."""
    loc = datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=ZoneInfo(zone))
    ny = loc.astimezone(NY).replace(tzinfo=None) + timedelta(hours=7)
    return int(ny.replace(tzinfo=timezone.utc).timestamp())


def net(P, i, j, nights, swap_pct):
    pe, px = P['o'][i], P['o'][j]
    return (px - pe) / pe * 100 - (P['spr'][i] + P['spr'][j]) / pe * 100 - nights * swap_pct


def run(sym, rng):
    P = load(sym)
    zone, hin, hout = SESSION[sym]
    sw = SWAP_PCT[sym]
    t, idx = P['t'], P['idx']
    first = datetime.fromtimestamp(int(t[0]), timezone.utc).date() + timedelta(days=2)
    last = datetime.fromtimestamp(int(t[-1]), timezone.utc).date()
    # velas por fecha del server (para el control)
    day_of = (t // 86400)
    nights, missing, intraday = [], 0, []
    d = first
    while d < last:
        if d.weekday() < 5:
            i = idx.get(server_ts(d, hin, zone))
            # siguiente día hábil con la vela de apertura
            e, j = d + timedelta(days=1), None
            for _ in range(5):
                if e.weekday() < 5:
                    j = idx.get(server_ts(e, hout, zone))
                    if j is not None:
                        break
                e += timedelta(days=1)
            if i is None or j is None:
                missing += 1
            else:
                n_nights = (e - d).days
                nights.append(dict(d=d.isoformat(), i=i, j=j, nn=n_nights,
                                   net=net(P, i, j, n_nights, sw), gross=(P['o'][j] - P['o'][i]) / P['o'][i] * 100))
            # tramo intradía del mismo día (apertura -> cierre), solo spread
            a, b = idx.get(server_ts(d, hout, zone)), idx.get(server_ts(d, hin, zone))
            if a is not None and b is not None:
                intraday.append(net(P, a, b, 0, 0.0))
        d += timedelta(days=1)
    vals = np.array([x['net'] for x in nights])
    gross = np.array([x['gross'] for x in nights])
    nn = np.array([x['nn'] for x in nights])
    half_swap = gross - np.array([(P['spr'][x['i']] + P['spr'][x['j']]) / P['o'][x['i']] * 100 for x in nights]) \
        - nn * sw / 2
    # control: misma duración, entrada en vela al azar del mismo día del server, mismos costos
    cands = []
    for x in nights:
        i, j = x['i'], x['j']
        dur = int(t[j] - t[i])
        same = np.nonzero(day_of == day_of[i])[0]
        c = []
        for k in same:
            if k == i:
                continue
            kk = idx.get(int(t[k]) + dur)
            if kk is not None:
                c.append(net(P, k, kk, x['nn'], sw))
        cands.append(np.array(c) if c else np.array([x['net']]))
    tot = np.zeros(CONTROL_REPS)
    for c in cands:
        tot += c[rng.integers(0, c.size, CONTROL_REPS)]
    ctrl = np.sort(tot / len(cands))
    return dict(sym=sym, n=int(vals.size), missing=missing, swap_pct_noche=sw,
                mean=float(vals.mean()), median=float(np.median(vals)), win=float((vals > 0).mean()),
                gross_mean=float(gross.mean()), half_swap_mean=float(half_swap.mean()),
                intraday_mean=float(np.mean(intraday)), intraday_n=len(intraday),
                ctrl_p50=float(ctrl[CONTROL_REPS // 2]), ctrl_p95=float(ctrl[int(0.95 * CONTROL_REPS)]),
                anual_neto_pct=float(vals.mean() * 252), series=[(x['d'], x['net']) for x in nights])


def main():
    rng = np.random.default_rng(SEED)
    res = {s: run(s, rng) for s in MAIN + DESC}
    print(f"{'sym':6}{'n':>6}{'falt':>5}{'neto%':>9}{'bruto%':>9}{'1/2swap%':>10}{'intradia%':>10}"
          f"{'gan':>6}{'ctrl p50':>10}{'ctrl p95':>10}")
    for s in MAIN + DESC:
        r = res[s]
        print(f"{s:6}{r['n']:>6}{r['missing']:>5}{r['mean']:>+9.4f}{r['gross_mean']:>+9.4f}"
              f"{r['half_swap_mean']:>+10.4f}{r['intraday_mean']:>+10.4f}{r['win']:>6.0%}"
              f"{r['ctrl_p50']:>+10.4f}{r['ctrl_p95']:>+10.4f}{'' if s in MAIN else '  (descriptivo)'}")
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
    print(f"\nPOOL US30+USTEC: n={pv.size} media {pv.mean():+.4f}%/noche  CI [{lo:+.4f}, {hi:+.4f}]  "
          f"mitades {h1:+.4f} / {h2:+.4f}")
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    for s in res:
        res[s].pop('series')
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p24_prima_nocturna_criterio.md (f55821a)', por_sym=res, pool=dict(
            n=int(pv.size), mean=float(pv.mean()), ci=[lo, hi], halves=[h1, h2]), criterios=crit, PASA=ok),
            f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
