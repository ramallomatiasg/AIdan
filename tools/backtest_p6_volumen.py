"""
backtest_p6_volumen.py — P6: pico de tick_volume como filtro de las señales de `structure` (M15, Fase 2).

READ-ONLY. Sin MT5, no toca la DB. Lee los checkpoints de Fase 2 (neto por trade ya calculado) y las velas M15
del mismo cache. Criterio declarado ANTES de medir: docs/p6_volumen_criterio.md (270287f). Leer contra eso.

Uso:
    python tools/backtest_p6_volumen.py              # 20 pares de Fase 1
    python tools/backtest_p6_volumen.py --reserved   # 6 reservados: solo si PASÓ
"""
import argparse
import json
import os
import pickle
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1 as _S20  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_fase2', 'M15_500000')
CKPT = os.path.join(CACHE, 'ckpt', 'v1_M15_live_{}_london.pkl')
LOOKBACK = 20
SPIKE = 1.5
CONTROL_REPS = 2000
SEED = 20261023
OUT = os.path.join(ROOT, 'docs', 'p6_volumen_resultado.json')
# enmienda 1: Fase 2 M15 solo tiene checkpoints de 15 de los 20 pares
SYMBOLS_FASE1 = [s for s in _S20 if os.path.exists(CKPT.format(s))]


def pair(sym):
    with open(CKPT.format(sym), 'rb') as f:
        ck = pickle.load(f)
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    t = r['time'].astype(np.int64)
    v = r['tick_volume'].astype(np.float64)
    from numpy.lib.stride_tricks import sliding_window_view
    med = np.full(v.size, np.nan)
    med[LOOKBACK:] = np.median(sliding_window_view(v[:-1], LOOKBACK), axis=1)
    i = np.searchsorted(t, ck['times'])
    ok = (i < t.size) & (t[np.minimum(i, t.size - 1)] == ck['times'])
    if ok.mean() < 0.99:
        raise SystemExit(f'{sym}: solo {ok.mean():.1%} de las señales matchean una vela — mapeo roto')
    i = i[ok]
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = v[i] / med[i]
    keep = np.isfinite(ratio)
    return dict(sym=sym, t=ck['times'][ok][keep], net=ck['netos'][ok][keep].astype(np.float64), ratio=ratio[keep])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('No pasó (o no se corrió): los reservados no se miran.')
        syms, out = RESERVADOS, OUT.replace('.json', '_reservados.json')
    else:
        syms, out = SYMBOLS_FASE1, OUT
    P = {s: pair(s) for s in syms}
    allr = np.concatenate([P[s]['ratio'] for s in syms])
    q1, q2 = np.percentile(allr, [33.33, 66.67])
    print(f'señales: {allr.size}  vol_ratio mediana {np.median(allr):.2f}  terciles {q1:.2f} / {q2:.2f}  '
          f'pico (>= {SPIKE}): {(allr >= SPIKE).mean():.1%}')
    print(f"{'par':7}{'n_pico':>8}{'neto pico':>11}{'neto resto':>12}")
    sel, per = [], {}
    for s in syms:
        p = P[s]
        m = p['ratio'] >= SPIKE
        per[s] = dict(n=int(m.sum()), neto_pico=float(p['net'][m].mean()) if m.any() else None,
                      neto_resto=float(p['net'][~m].mean()) if (~m).any() else None)
        sel.append((p['t'][m], p['net'][m]))
        print(f"{s:7}{per[s]['n']:>8}{per[s]['neto_pico'] or 0:>+11.3f}{per[s]['neto_resto'] or 0:>+12.3f}")
    tt = np.concatenate([x[0] for x in sel])
    nn = np.concatenate([x[1] for x in sel])
    o = np.argsort(tt)
    nn = nn[o]
    lo, hi, _ = bootstrap_ci(nn)
    half = nn.size // 2
    h1, h2 = float(nn[:half].mean()), float(nn[half:].mean())
    rng = np.random.default_rng(SEED)
    sums = np.zeros(CONTROL_REPS)
    for s in syms:
        k = per[s]['n']
        if k:
            net = P[s]['net']
            for r_ in range(CONTROL_REPS):
                sums[r_] += net[rng.choice(net.size, k, replace=False)].sum()
    ctrl = np.sort(sums / nn.size)
    p95 = float(ctrl[int(0.95 * CONTROL_REPS)])
    pos = sum(1 for s in syms if per[s]['n'] and per[s]['neto_pico'] > 0)
    all_net = np.concatenate([P[s]['net'] for s in syms])
    terc = {lab: float(all_net[mk].mean()) for lab, mk in
            (('bajo', allr < q1), ('medio', (allr >= q1) & (allr < q2)), ('alto', allr >= q2))}
    print(f'\nterciles de vol_ratio (descriptivo): ' + '  '.join(f'{k} {v:+.3f}p' for k, v in terc.items()))
    print(f'todas las señales: n={all_net.size} neto {all_net.mean():+.3f}p')
    crit = {'1_n>=1000': nn.size >= 1000,
            '2_media>0_CI_inf>0': bool(nn.mean() > 0 and lo is not None and lo > 0),
            '3_dos_mitades>0': h1 > 0 and h2 > 0,
            '4_>control_p95': bool(nn.mean() > p95),
            '5_>=60%_pares>0': pos >= int(np.ceil(0.6 * len(syms)))}
    ok = all(crit.values())
    print(f'\nPICO: n={nn.size} neto {nn.mean():+.4f}p  CI [{lo:+.4f}, {hi:+.4f}]  mitades {h1:+.3f} / {h2:+.3f}  '
          f'pares>0 {pos}/{len(syms)}  control (subconjuntos al azar) mediana {ctrl[CONTROL_REPS // 2]:+.4f} '
          f'p95 {p95:+.4f}')
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(out, 'w') as f:
        json.dump(dict(criterio='docs/p6_volumen_criterio.md (270287f + enmienda 1)', n=int(nn.size), mean=float(nn.mean()),
                       ci=[lo, hi], halves=[h1, h2], control_p95=p95, pos=pos, terciles=terc, por_par=per,
                       criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
