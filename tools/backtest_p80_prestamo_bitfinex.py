"""P80 — prestar USD en el funding de Bitfinex contra la letra a 3 meses.

Criterio declarado antes de medir: docs/p80_prestamo_bitfinex_criterio.md (793d0dd).
Read-only: sin MT5, no toca la DB. Datos: .cache_p80/fusd_a30_p2_p30.json (velas diarias públicas) y
.cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p80_prestamo_bitfinex.py              # 2016-08 -> 2021
  python tools/backtest_p80_prestamo_bitfinex.py --reserved   # 2022 -> hoy, solo si pasó
"""
import argparse
import bisect
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p80', 'fusd_a30_p2_p30.json')
C30 = os.path.join(ROOT, '.cache_p80', 'fusd_p30.json')
DTB3 = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p80_prestamo_bitfinex_resultado.json')
BOOT, SEED, BLK = 5000, 20261126, 30
HACK, REPAY, HAIR = dt.date(2016, 8, 2), dt.date(2017, 4, 3), 0.36067
D0, D1, R1 = dt.date(2016, 8, 1), dt.date(2021, 12, 31), dt.date(2026, 11, 26)


def load_rates(path):
    d = json.load(open(path))
    return {dt.datetime.utcfromtimestamp(x[0] / 1000).date(): float(x[2]) for x in d}


def tbill():
    d = json.load(open(DTB3))
    ks = sorted(k for k, v in d.items() if v not in (None, '', '.'))
    days = [dt.date.fromisoformat(k) for k in ks]
    vals = [float(d[k]) / 100 for k in ks]

    def f(x):
        i = bisect.bisect_right(days, x) - 1
        return vals[i]
    return f


def series(rates, lo, hi, util, fee, carry, tb, hack_repay=True):
    """Retorno diario del PATRIMONIO en log (corrección 26-nov, antes de reportar: la 1ra corrida sumaba retornos
    aritméticos y el par hackeo -36% / devolución +56% inflaba el promedio). Tras el hackeo, el 36,067% queda como
    reclamo T sin interés hasta la devolución; sin devolución, T = 0."""
    out = []
    last = None
    L, T = 1.0, 0.0
    for n in range((hi - lo).days + 1):
        d = lo + dt.timedelta(days=n)
        r = rates.get(d)
        if r is None:
            r = last if carry and last is not None else 0.0
        else:
            last = r
        y = r * util * (1 - fee)
        e0 = L + T
        L *= 1 + y
        if d == HACK:
            T = L * HAIR if hack_repay else 0.0
            L *= 1 - HAIR
        if d == REPAY and hack_repay:
            L += T; T = 0.0
        lr = np.log((L + T) / e0)
        prem = lr - np.log(1 + tb(d) / 365 + 0.01 / 365)
        out.append((d, lr, prem))
    return out


def ann(x):
    return float(np.mean(x) * 365)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    lo, hi = (D1 + dt.timedelta(days=1), R1) if a.reserved else (D0, D1)
    rates = load_rates(C)
    tb = tbill()
    base = series(rates, lo, hi, 1.0, 0.15, True, tb)
    pes = series(rates, lo, hi, 0.70, 0.18, False, tb)
    nore = series(rates, lo, hi, 1.0, 0.15, True, tb, hack_repay=False)
    p = np.array([x[2] for x in base]); pp = np.array([x[2] for x in pes])
    n = p.size; h = n // 2
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLK)); st = np.arange(0, n - BLK + 1)
    bs = np.sort([p[np.concatenate([np.arange(s, s + BLK) for s in rng.choice(st, nb)])[:n]].mean() * 365
                  for _ in range(BOOT)])
    ci = (float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]))
    months = {}
    for d, _, pr in base:
        months.setdefault((d.year, d.month), []).append(pr)
    mpos = np.mean([sum(v) > 0 for v in months.values()])
    missing = sum(1 for x in base if x[0] not in rates)
    eq = np.exp(np.cumsum([x[1] for x in base])); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P80 préstamo USD Bitfinex {tag}: {n} días ({lo} -> {hi}), días sin vela {missing}')
    print(f'  premio log sobre la letra (base) {ann(p):+.2%}/año  CI95 [{ci[0]:+.2%}, {ci[1]:+.2%}]  mitades '
          f'{ann(p[:h]):+.2%} / {ann(p[h:]):+.2%}  pesimista {ann(pp):+.2%}  meses>0 {mpos:.0%}')
    print(f'  rendimiento base {ann([x[1] for x in base]):+.2%}/año · sin devolución del hackeo premio '
          f'{ann([x[2] for x in nore]):+.2%}/año · caída máx base {dd:+.1%}')
    yrs = {}
    for d, y, pr in base:
        yrs.setdefault(d.year, [[], []]); yrs[d.year][0].append(y); yrs[d.year][1].append(pr)
    print('  por año (rend / premio): ' + '  '.join(f'{k} {ann(v[0]):+.1%}/{ann(v[1]):+.1%}'
                                                   for k, v in sorted(yrs.items())))
    b30 = series(load_rates(C30), lo, hi, 1.0, 0.15, True, tb)
    print(f'  desc.: solo plazo 30 días, premio base {ann([x[2] for x in b30]):+.2%}/año')
    if a.reserved:
        crit = {'1_premio>0': ann(p) > 0, '2_CI_inf>0': ci[0] > 0}
    else:
        crit = {'1_premio>0': ann(p) > 0, '2_CI_inf>0': ci[0] > 0,
                '3_dos_mitades>0': ann(p[:h]) > 0 and ann(p[h:]) > 0, '4_pesimista>0': ann(pp) > 0,
                '5_meses>0_>=60%': mpos >= 0.60}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P80 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(dias=n, premio=ann(p), ci=list(ci), mitades=[ann(p[:h]), ann(p[h:])], pesimista=ann(pp),
                   meses_pos=float(mpos), caida_max=dd, criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
                   criterio='docs/p80_prestamo_bitfinex_criterio.md (793d0dd)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
