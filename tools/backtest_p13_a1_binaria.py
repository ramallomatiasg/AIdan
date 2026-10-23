"""
backtest_p13_a1_binaria.py — P13: A1 (reversión a 2σ) medida como opción binaria, SOLO en los 6 reservados.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000`.
Criterio declarado ANTES de mirar los reservados: docs/p13_a1_binaria_criterio.md (0a752de).

Gana si el close a la expiración está a favor; empate excluido. Una sola corrida.

Uso:
    python tools/backtest_p13_a1_binaria.py
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.screen_generators import gen_A1, RESERVADOS  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_fase2', 'M5_500000')
WARMUP = 100
H_MAIN = 3
H_ALL = (1, 3, 6, 12)
BE_90 = 1 / 1.90
BE_85 = 1 / 1.85
MIN_N = 20000
OUT = os.path.join(ROOT, 'docs', 'p13_a1_binaria_resultado.json')


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - m) / d, (c + m) / d


def one_at_a_time(idx, H):
    keep, free = [], -1
    for k, i in enumerate(idx):
        if i >= free:
            keep.append(k)
            free = i + H
    return np.asarray(keep, dtype=np.int64)


def outcomes(sym, H):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.spec.json')) as f:
        pip = json.load(f)['pip']
    o, h, l, c = (r[k].astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    idx, d = gen_A1(o, h, l, c, r['time'], pip)
    m = (idx >= WARMUP) & (idx < c.size - H - 1)
    idx, d = idx[m], d[m]
    sel = one_at_a_time(idx, H)
    idx, d = idx[sel], d[sel]
    mv = d * (c[idx + H] - c[idx])
    nz = mv != 0
    return r['time'][idx][nz].astype(np.int64), (mv[nz] > 0)


def main():
    if os.path.exists(OUT):
        sys.exit('Los reservados ya se corrieron para P13 (una sola vez). No se re-corren.')
    out = {'criterio': 'docs/p13_a1_binaria_criterio.md (0a752de)'}
    for H in H_ALL:
        tag = '  <== DECIDE' if H == H_MAIN else '  (secundario)'
        print(f'\n=== H{H} ({H * 5} min){tag}')
        tt, ww, per = [], [], {}
        for s in RESERVADOS:
            t, w = outcomes(s, H)
            lo, hi = wilson(int(w.sum()), w.size)
            per[s] = dict(n=int(w.size), hit=float(w.mean()), ci=[lo, hi])
            tt.append(t)
            ww.append(w)
            print(f'  {s:7s} n={w.size:6d}  acierto {w.mean():.2%}  CI [{lo:.2%}, {hi:.2%}]')
        t = np.concatenate(tt)
        w = np.concatenate(ww)[np.argsort(t)]
        k, n = int(w.sum()), int(w.size)
        lo, hi = wilson(k, n)
        half = n // 2
        h1, h2 = float(w[:half].mean()), float(w[half:].mean())
        pos = sum(1 for s in per if per[s]['hit'] > BE_90)
        ev = dict(n=n, hit=k / n, ci=[lo, hi], halves=[h1, h2], pairs_above_be90=pos, por_par=per,
                  ev_payout_85=k / n * 0.85 - (1 - k / n), ev_payout_90=k / n * 0.90 - (1 - k / n))
        print(f'  POOL n={n} acierto {k / n:.2%}  CI [{lo:.2%}, {hi:.2%}]  mitades {h1:.2%} / {h2:.2%}  '
              f'pares>52,6% {pos}/6  EV por $1: payout85 {ev["ev_payout_85"]:+.3f}  payout90 {ev["ev_payout_90"]:+.3f}')
        if H == H_MAIN:
            crit = {f'1_n>={MIN_N}': n >= MIN_N,
                    '2_CI_inf>52,6%': lo > BE_90,
                    '3_dos_mitades>52,6%': h1 > BE_90 and h2 > BE_90,
                    '4_>=4/6_pares>52,6%': pos >= 4}
            ok = all(crit.values())
            strong = ok and lo > BE_85
            for kk, v in crit.items():
                print(f"      [{'OK ' if v else 'NO '}] {kk}")
            print(f"  >>> {'PASA FUERTE' if strong else 'PASA' if ok else 'NO PASA'}"
                  f"  (CI inf {lo:.2%} vs 54,1% del payout 85%)")
            ev.update(criterios=crit, PASA=ok, PASA_FUERTE=strong)
        out[str(H)] = ev
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
