"""P85 — Arbitraje de fusiones con ETF (MNA) contra la letra: comprar y mantener.

Criterio declarado antes de medir: docs/p85_arbitraje_fusiones_criterio.md (6cdcfa2).
Read-only: sin MT5, no toca la DB. Datos: .cache_p85/MNA.json y SPY.json (Yahoo ajustado), .cache_p50/dtb3.json.

  python tools/backtest_p85_arbitraje_fusiones.py              # ene-2010 -> dic-2017
  python tools/backtest_p85_arbitraje_fusiones.py --reserved   # ene-2018 -> oct-2026, solo si pasó
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from backtest_p82_tendencia_12m_etfs import monthly, mdd, ann  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
OUT = os.path.join(ROOT, 'docs', 'p85_arbitraje_fusiones_resultado.json')
COST, PESS = 0.0005, 0.0010
BOOT, SEED, BLK = 5000, 20261127, 6
DISC = ('2010-01', '2017-12')
RES = ('2018-01', '2026-10')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    lo, hi = RES if a.reserved else DISC
    R, B = monthly('.cache_p85', ['MNA', 'SPY'], 'SPY')
    ms = [m for m in sorted(R) if lo <= m <= hi]
    M = np.array([R[m]['MNA'] for m in ms])
    S = np.array([R[m]['SPY'] for m in ms])
    T = np.array([B[m] for m in ms])
    M[0] -= COST
    M[-1] -= COST
    x = M - T
    xs = S - T
    n = len(ms)
    h = n // 2
    exc = ann(M) - ann(T)
    e1 = ann(M[:h]) - ann(T[:h])
    e2 = ann(M[h:]) - ann(T[h:])
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLK))
    st = np.arange(0, n - BLK + 1)
    bs = np.sort([x[np.concatenate([np.arange(s, s + BLK) for s in rng.choice(st, nb)])[:n]].mean()
                  for _ in range(BOOT)])
    ci = (float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)]))
    beta, alpha = np.polyfit(xs, x, 1)
    corr = float(np.corrcoef(x, xs)[0, 1])
    sh = float(x.mean() / x.std(ddof=1) * np.sqrt(12))
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P85 MNA contra la letra {tag}: {n} meses ({ms[0]} -> {ms[-1]})')
    print(f'  exceso anual {exc:+.2%}  exceso medio mensual {x.mean():+.3%}  CI95 [{ci[0]:+.3%}, {ci[1]:+.3%}]  '
          f'mitades {e1:+.2%} / {e2:+.2%}')
    print(f'  alfa {alpha * 12:+.2%}/año  beta {beta:.2f}  correlación con SPY {corr:.2f}  Sharpe del exceso {sh:.2f}')
    print(f'  MNA {ann(M):+.2%}/año (vol {M.std(ddof=1) * np.sqrt(12):.1%}, caída máx {mdd(M):+.1%}) | SPY '
          f'{ann(S):+.2%} (caída máx {mdd(S):+.1%}) | letra {ann(T):+.2%}')
    yr = {}
    for m, v in zip(ms, M):
        yr[m[:4]] = yr.get(m[:4], 1.0) * (1 + v)
    print('  por año: ' + '  '.join(f'{y} {v - 1:+.1%}' for y, v in sorted(yr.items())))
    if a.reserved:
        crit = {'1_exceso>0': exc > 0, '2_CI_inf>0': ci[0] > 0, '4_alfa>0': alpha > 0}
    else:
        crit = {'1_exceso>0': exc > 0, '2_CI_inf>0': ci[0] > 0, '3_dos_mitades>0': e1 > 0 and e2 > 0,
                '4_alfa>0': alpha > 0, '5_corr<=0.7': corr <= 0.7}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P85 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(meses=n, exceso_anual=exc, ci_mensual=list(ci), mitades=[e1, e2], alfa_anual=alpha * 12,
                   beta=beta, corr_spy=corr, sharpe_exceso=sh, criterios={k: bool(v) for k, v in crit.items()},
                   PASA=ok, criterio='docs/p85_arbitraje_fusiones_criterio.md (6cdcfa2)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
