"""P52 — carry de funding de P15 en ETH con la pata larga en WBETH de Binance (funding + staking).

Criterio declarado antes de medir: docs/p52_wbeth_carry_criterio.md (48c072c + enmienda 1e6de96).
Read-only: sin MT5, no toca la DB. Velas públicas de WBETHETH (Binance) a .cache_p52/; ETH desde .cache_p15/.

  python tools/backtest_p52_wbeth_carry.py              # descubrimiento (may-2023 → 2024)
  python tools/backtest_p52_wbeth_carry.py --reserved   # 2025-26, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p15_funding as p15  # noqa: E402

ROOT = p15.ROOT
CACHE = os.path.join(ROOT, '.cache_p52')
P8H = p15.P8H
START = dt.datetime(2023, 5, 26, tzinfo=dt.timezone.utc)
DISCARD_MS = int(dt.datetime(2023, 5, 19, tzinfo=dt.timezone.utc).timestamp() * 1000)   # listado 12-may + 7 días
SPLIT_MS = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
END_MS = p15.END_MS
COST_P15 = p15.RT_COST
COST_ST = p15.RT_COST + 2 * 0.0005                   # 0,48%
OUT = os.path.join(ROOT, 'docs', 'p52_wbeth_carry_resultado.json')


def _get(u):
    for k in range(5):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                                    timeout=60))
        except Exception:
            if k == 4:
                raise
            time.sleep(3 + 3 * k)


def load():
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, 'WBETHETH.json')
    if os.path.exists(p):
        return json.load(open(p))
    out, t = [], int(dt.datetime(2023, 5, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    while t < END_MS:
        k = _get(f'https://data-api.binance.vision/api/v3/klines?symbol=WBETHETH&interval=8h&startTime={t}&limit=1000')
        if not k:
            break
        out += [(int(x[0]), float(x[1])) for x in k]
        t = int(k[-1][0]) + P8H
        time.sleep(0.3)
    json.dump(out, open(p, 'w'))
    return out


def stats(r, t0, t1, label):
    eq = np.cumprod(1 + r)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    ann = float(r.mean() * p15.PER_YEAR)
    bs = p15.block_boot(r, np.random.default_rng(p15.SEED)) * p15.PER_YEAR
    lo, hi = float(bs[int(.025 * p15.BOOT)]), float(bs[int(.975 * p15.BOOT)])
    h = r.size // 2
    h1, h2 = float(r[:h].mean() * p15.PER_YEAR), float(r[h:].mean() * p15.PER_YEAR)
    hr = p15.hurdle(t0, t1)
    print(f"  {label}: {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx {dd:.2%}  tasa libre {hr:.2%}")
    return dict(annual=ann, ci=[lo, hi], halves=[h1, h2], max_dd=dd, hurdle=hr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    eth = p15.load('ETH')
    wb = [(t, r) for t, r in load() if t >= DISCARD_MS and t < END_MS]
    ratio = dict(wb)
    tt_ = np.array([x[0] for x in wb]); rr = np.array([x[1] for x in wb])
    step = np.abs(np.diff(rr) / rr[:-1])
    seg = (tt_[1:] >= SPLIT_MS) if a.reserved else (tt_[1:] < SPLIT_MS)      # enmienda 1: control por tramo
    bad = np.flatnonzero(seg & (step > 0.02))
    if a.reserved:                                    # en la reserva solo aborta si el salto no vuelve en 3 velas
        # un salto vale si vuelve dentro de 3 velas, o si el propio salto es la vuelta de uno anterior
        bad = [k for k in bad if not np.any(np.abs(rr[k + 2:k + 5] / rr[k] - 1) <= 0.02)
               and not np.any(np.abs(rr[k + 1] / rr[max(k - 3, 0):k] - 1) <= 0.02)]
    if len(bad):
        k = int(bad[0])
        sys.exit(f'ABORTA (control de datos): el cociente WBETHETH salta {step[k]:.2%} el '
                 f'{dt.datetime.utcfromtimestamp(tt_[k + 1] / 1000)} ⇒ medición inválida.')
    rmin = (dt.datetime.utcfromtimestamp(tt_[rr.argmin()] / 1000).strftime('%Y-%m-%d'), float(rr.min()))
    t0 = int(START.timestamp() * 1000)
    syn, last = [], None
    for t, s in eth['spot']:
        if t in ratio:
            last = ratio[t]
        if t >= t0 - 8 * 86400 * 1000 and last is not None:
            syn.append((t, s * last))
    grid = np.arange(t0 - t0 % P8H, END_MS, P8H, dtype=np.int64).tolist()
    p15.END_MS = END_MS
    dst = dict(spot=syn, perp=eth['perp'], funding=eth['funding'])
    p15.RT_COST = COST_ST
    rs, cs, _ = p15.simulate(dst, grid)
    rsa, _, _ = p15.simulate(dst, grid, always_in=True)
    p15.RT_COST = COST_P15
    re_, ce, _ = p15.simulate(eth, grid)
    g = np.array(grid[:-1])
    m = (g >= SPLIT_MS) if a.reserved else (g < SPLIT_MS)
    tt = g[m]
    sel = (tt_ >= SPLIT_MS) if a.reserved else (tt_ < SPLIT_MS)
    yrs = (tt_[sel][-1] - tt_[sel][0]) / (365.25 * 86400 * 1000)
    stk = (rr[sel][-1] / rr[sel][0]) ** (1 / yrs) - 1
    print(f"  {'RESERVA 2025-26' if a.reserved else 'DESCUBRIMIENTO may-2023 → 2024'}  (WBETH/ETH: crecimiento "
          f"{stk:+.2%}/año en el tramo; salto máx 8 h en el tramo {step[seg].max():.3%})")
    print(f"  componentes período completo (x nocional): WBETH fund {cs['funding']:+.3f} base {cs['base']:+.3f} "
          f"costo {cs['cost']:.3f} entradas {cs['trades']} | ETH fund {ce['funding']:+.3f} base {ce['base']:+.3f}")
    s = stats(rs[m], tt[0], tt[-1], 'WBETH (decide)')
    print('  descriptivo:')
    e = stats(re_[m], tt[0], tt[-1], 'P15 ETH sin staking')
    sa = stats(rsa[m], tt[0], tt[-1], 'WBETH siempre adentro')
    years = {}
    for k in np.flatnonzero(m):                      # solo el tramo elegido (no mirar la reserva)
        years.setdefault(dt.datetime.utcfromtimestamp(g[k] / 1000).year, []).append((rs[k], re_[k]))
    print('    por año (WBETH / ETH): ' + '  '.join(
        f"{y} {np.mean([x[0] for x in v]) * p15.PER_YEAR:+.1%}/{np.mean([x[1] for x in v]) * p15.PER_YEAR:+.1%}"
        for y, v in sorted(years.items())))
    if a.reserved:
        crit = {'reserva_anual>tasa_libre': s['annual'] > s['hurdle']}
    else:
        crit = {'1_anual>tasa_libre_media': s['annual'] > s['hurdle'], '2_CI_inf>0': s['ci'][0] > 0,
                '3_dos_mitades>0': min(s['halves']) > 0, '4_caida_max<10%': s['max_dd'] < 0.10}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f"  >>> P52 {'reserva' if a.reserved else ''}: {'PASA' if ok else 'NO PASA'}")
    res = dict(decide=s, eth_sin_staking=e, siempre=sa, ratio_min=rmin, criterios=crit, PASA=ok,
               criterio='docs/p52_wbeth_carry_criterio.md (48c072c + enmienda 1e6de96)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
