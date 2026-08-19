# -*- coding: utf-8 -*-
"""
screen_generators.py — FASE 3: screen barato de generadores candidatos.

READ-ONLY. Reusa el cache de velas de backtest_fase2.py. No toca produccion, no
manda ordenes, no consulta la DB viva.

═══ QUE ES ══════════════════════════════════════════════════════════════════

La lista de los 9 candidatos, sus parametros y el criterio de exito estan
CONGELADOS en docs/fase3_candidatos_declarados.md, commiteado ANTES de escribir
este archivo (12622b3). Si el resultado no se lee contra ese doc, no vale nada.

Mide, por generador y por horizonte (3,6,12,24,48,96 velas):
    close = movimiento neto en pips a favor de la direccion de la senal
    fav / adv = maxima excursion favorable / adversa (diagnostico)

NO simula SL/TP a proposito: elegir SL y TP mete parametros tuneables. El
movimiento neto crudo no tiene supuestos.

CRITERIO (las tres, en el mismo horizonte):
    close medio > 0,90 pips (el costo round turn)
    Y por encima del percentil 99 del control aleatorio
    Y n >= 1.000 senales

Universo del screen: los 20 pares de Fase 1. Los 6 de Fase 1b quedan RESERVADOS
y no se miran hasta que un candidato sobreviva.

═══ IMPLEMENTACION ══════════════════════════════════════════════════════════

Todo vectorizado con numpy: 9 generadores x 500k velas x 20 pares son 90 M de
evaluaciones y con un loop por vela no termina. Cada generador devuelve, de una
sola pasada, los indices de entrada y su direccion.

CAVEAT declarado: D1/D2 usan la hora del timestamp del BROKER (eje del servidor
MT5), no UTC exacto. El offset del servidor es de +2/+3 h segun DST. Para un
screen de forma eso alcanza; si D1 o D2 sobreviven, hay que rehacerlo anclando la
hora como lo hace measure_news_llm_error.py.

Uso:
    python tools/screen_generators.py --tf M5 --workers 14
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.backtest_fase2 import load_symbol, set_low_priority  # noqa: E402

HORIZONS = [3, 6, 12, 24, 48, 96]
COST_PIPS = 0.90          # round turn, el umbral del criterio
MIN_N = 1000
CONTROL_REPS = 10
WARMUP = 100

RESERVADOS = ['CHFJPY', 'NZDJPY', 'GBPNZD', 'NZDCHF', 'NZDCAD', 'GBPCAD']


# ═══════════════════════════════════════════════════════════════════════════
# helpers vectorizados
# ═══════════════════════════════════════════════════════════════════════════

def roll_mean(a, n):
    c = np.cumsum(np.insert(a, 0, 0.0))
    out = np.full(a.size, np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def roll_std(a, n):
    m = roll_mean(a, n)
    m2 = roll_mean(a * a, n)
    v = np.maximum(m2 - m * m, 0.0)
    return np.sqrt(v)


def roll_min(a, n):
    out = np.full(a.size, np.nan)
    if a.size < n:
        return out
    v = np.lib.stride_tricks.sliding_window_view(a, n).min(axis=1)
    out[n - 1:] = v
    return out


def roll_max(a, n):
    out = np.full(a.size, np.nan)
    if a.size < n:
        return out
    v = np.lib.stride_tricks.sliding_window_view(a, n).max(axis=1)
    out[n - 1:] = v
    return out


def fwd_extremes(high, low, horizons):
    """Para cada i: max(high[i+1..i+H]) y min(low[i+1..i+H]) por cada H.

    Acumulativo entre horizontes: se extiende el maximo anterior en vez de
    recalcular. Total de pasadas = max(H), no la suma.
    """
    n = high.size
    res = {}
    cur_hi = np.full(n, -np.inf)
    cur_lo = np.full(n, np.inf)
    k = 1
    for H in sorted(horizons):
        while k <= H:
            sh_h = np.full(n, -np.inf)
            sh_l = np.full(n, np.inf)
            if k < n:
                sh_h[:n - k] = high[k:]
                sh_l[:n - k] = low[k:]
            np.maximum(cur_hi, sh_h, out=cur_hi)
            np.minimum(cur_lo, sh_l, out=cur_lo)
            k += 1
        res[H] = (cur_hi.copy(), cur_lo.copy())
    return res


def fwd_close(close, horizons):
    n = close.size
    out = {}
    for H in horizons:
        c = np.full(n, np.nan)
        if H < n:
            c[:n - H] = close[H:]
        out[H] = c
    return out


# ═══════════════════════════════════════════════════════════════════════════
# LOS 9 GENERADORES — parametros congelados en el doc, no se tocan
# ═══════════════════════════════════════════════════════════════════════════
# Cada uno devuelve (idx, dirs) con dirs = +1 (CALL) / -1 (PUT).

def _pack(mask_call, mask_put):
    idx = np.where(mask_call | mask_put)[0]
    dirs = np.where(mask_call[idx], 1, -1)
    return idx, dirs


def gen_A1(o, h, l, c, t, pip):
    """Z-score contra la media: |z| > 2 entra CONTRA el desvio."""
    ma, sd = roll_mean(c, 20), roll_std(c, 20)
    with np.errstate(invalid='ignore', divide='ignore'):
        z = (c - ma) / sd
    return _pack(np.nan_to_num(z) < -2.0, np.nan_to_num(z) > 2.0)


def gen_A2(o, h, l, c, t, pip):
    """Extremo de rango 20: close en el minimo -> CALL; en el maximo -> PUT."""
    lo20, hi20 = roll_min(c, 20), roll_max(c, 20)
    return _pack(c <= lo20, c >= hi20)


def gen_A3(o, h, l, c, t, pip):
    """Pin bar: mecha >= 66% del rango y cuerpo <= 25%."""
    rng = h - l
    body = np.abs(c - o)
    up_w = h - np.maximum(o, c)
    dn_w = np.minimum(o, c) - l
    ok = rng > 0
    with np.errstate(invalid='ignore', divide='ignore'):
        small_body = ok & (body / np.where(ok, rng, 1) <= 0.25)
        long_dn = ok & (dn_w / np.where(ok, rng, 1) >= 0.66)
        long_up = ok & (up_w / np.where(ok, rng, 1) >= 0.66)
    return _pack(small_body & long_dn, small_body & long_up)


def gen_B1(o, h, l, c, t, pip):
    """Compresion -> quiebre: rango de 10 en su minimo de 100, cierre fuera."""
    hi10, lo10 = roll_max(h, 10), roll_min(l, 10)
    rng10 = hi10 - lo10
    minrng100 = roll_min(np.nan_to_num(rng10, nan=np.inf), 100)
    comp = np.isfinite(rng10) & np.isfinite(minrng100) & (rng10 <= minrng100 * 1.0)
    # el quiebre se evalua en la vela SIGUIENTE a la compresion (sin lookahead)
    comp_prev = np.zeros_like(comp)
    comp_prev[1:] = comp[:-1]
    hi_prev = np.roll(hi10, 1)
    lo_prev = np.roll(lo10, 1)
    return _pack(comp_prev & (c > hi_prev), comp_prev & (c < lo_prev))


def gen_B2(o, h, l, c, t, pip):
    """ATR(5) > 1,5 x ATR(20): entra en la direccion del cuerpo."""
    tr = h - l
    a5, a20 = roll_mean(tr, 5), roll_mean(tr, 20)
    with np.errstate(invalid='ignore'):
        exp = np.nan_to_num(a5) > 1.5 * np.nan_to_num(a20)
    return _pack(exp & (c > o), exp & (c < o))


def gen_C1(o, h, l, c, t, pip):
    """Cruce MA20/MA50 con pendiente de MA50 a 10 velas del mismo signo."""
    m20, m50 = roll_mean(c, 20), roll_mean(c, 50)
    prev20, prev50 = np.roll(m20, 1), np.roll(m50, 1)
    slope = m50 - np.roll(m50, 10)
    up = (prev20 <= prev50) & (m20 > m50) & (slope > 0)
    dn = (prev20 >= prev50) & (m20 < m50) & (slope < 0)
    return _pack(np.nan_to_num(up).astype(bool), np.nan_to_num(dn).astype(bool))


def gen_C2(o, h, l, c, t, pip):
    """Pullback a la MA20 en tendencia (MA20 vs MA50). El pullback BIEN hecho:
    contra una media, no contra un fractal de 2 vecinos."""
    m20, m50 = roll_mean(c, 20), roll_mean(c, 50)
    prevc = np.roll(c, 1)
    trend_up = m20 > m50
    trend_dn = m20 < m50
    touch_dn = (prevc > np.roll(m20, 1)) & (l <= m20)      # baja a tocar la MA20
    touch_up = (prevc < np.roll(m20, 1)) & (h >= m20)
    up = np.nan_to_num(trend_up & touch_dn).astype(bool)
    dn = np.nan_to_num(trend_dn & touch_up).astype(bool)
    return _pack(up, dn)


def _hour_of(t):
    return ((t // 3600) % 24).astype(np.int64)


def gen_D1(o, h, l, c, t, pip):
    """Rango de sesion asiatica (00-06 en el eje del broker); quiebre 06-12."""
    hr = _hour_of(t)
    day = t // 86400
    asia = (hr >= 0) & (hr < 6)
    win = (hr >= 6) & (hr < 12)
    hi = np.full(t.size, np.nan)
    lo = np.full(t.size, np.nan)
    # rango asiatico por dia, propagado hacia adelante (sin lookahead: solo se usa
    # en la ventana 06-12 del MISMO dia, y el rango ya cerro a las 06)
    uniq = np.unique(day)
    for d in uniq:
        m = day == d
        a = m & asia
        if not a.any():
            continue
        hi[m] = h[a].max()
        lo[m] = l[a].min()
    return _pack(win & (c > hi), win & (c < lo))


def gen_D2(o, h, l, c, t, pip):
    """Quiebre del rango del dia calendario anterior."""
    day = t // 86400
    uniq, first_idx = np.unique(day, return_index=True)
    hi_prev = np.full(t.size, np.nan)
    lo_prev = np.full(t.size, np.nan)
    for k in range(1, uniq.size):
        s, e = first_idx[k], (first_idx[k + 1] if k + 1 < uniq.size else t.size)
        ps, pe = first_idx[k - 1], first_idx[k]
        if pe > ps:
            hi_prev[s:e] = h[ps:pe].max()
            lo_prev[s:e] = l[ps:pe].min()
    return _pack(c > hi_prev, c < lo_prev)


GENERATORS = {
    'A1_zscore_rev': gen_A1,
    'A2_extremo_rango': gen_A2,
    'A3_pinbar': gen_A3,
    'B1_compresion': gen_B1,
    'B2_atr_expand': gen_B2,
    'C1_cruce_ma': gen_C1,
    'C2_pullback_ma': gen_C2,
    'D1_rango_asia': gen_D1,
    'D2_rango_dia_prev': gen_D2,
}


# ═══════════════════════════════════════════════════════════════════════════

def run_symbol(job):
    sym, cache_dir, low_prio = job
    if low_prio:
        set_low_priority()
    t0 = time.perf_counter()
    candles, spec = load_symbol(sym, cache_dir)
    pip = spec['pip']
    n = len(candles)

    o = np.fromiter((x['open'] for x in candles), np.float64, n)
    h = np.fromiter((x['high'] for x in candles), np.float64, n)
    l = np.fromiter((x['low'] for x in candles), np.float64, n)
    c = np.fromiter((x['close'] for x in candles), np.float64, n)
    t = np.fromiter((x['time_unix'] for x in candles), np.int64, n)

    ext = fwd_extremes(h, l, HORIZONS)
    fc = fwd_close(c, HORIZONS)
    valid_lo = WARMUP

    def score(idx, dirs):
        """Devuelve {H: (sum_fav, sum_adv, sum_close, n)} para esas entradas."""
        out = {}
        keep = (idx >= valid_lo) & (idx < n - max(HORIZONS) - 1)
        idx, dirs = idx[keep], dirs[keep]
        if idx.size == 0:
            return {H: (0.0, 0.0, 0.0, 0) for H in HORIZONS}
        entry = c[idx]
        for H in HORIZONS:
            hi, lo = ext[H][0][idx], ext[H][1][idx]
            cl = fc[H][idx]
            up = dirs > 0
            fav = np.where(up, hi - entry, entry - lo) / pip
            adv = np.where(up, entry - lo, hi - entry) / pip
            clo = np.where(up, cl - entry, entry - cl) / pip
            ok = np.isfinite(fav) & np.isfinite(adv) & np.isfinite(clo)
            out[H] = (float(fav[ok].sum()), float(adv[ok].sum()),
                      float(clo[ok].sum()), int(ok.sum()))
        return out

    res = {}
    for name, fn in GENERATORS.items():
        idx, dirs = fn(o, h, l, c, t, pip)
        res[name] = score(idx, dirs)

    # control aleatorio: mismo n TOTAL que el promedio de los generadores,
    # mismo ratio long/short 50/50 (los generadores son ~simetricos por diseno)
    rng = np.random.default_rng(abs(hash(sym)) % (2**32))
    n_ctl = max(1000, int(np.mean([res[g][HORIZONS[0]][3] for g in GENERATORS])))
    ctl_reps = []
    for _ in range(CONTROL_REPS):
        ridx = rng.integers(valid_lo, n - max(HORIZONS) - 1, n_ctl)
        rdirs = np.where(rng.random(n_ctl) < 0.5, 1, -1)
        ctl_reps.append(score(ridx, rdirs))

    return {'symbol': sym, 'gen': res, 'ctl': ctl_reps,
            'secs': round(time.perf_counter() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='M5')
    ap.add_argument('--candles', type=int, default=500_000)
    ap.add_argument('--workers', type=int, default=14)
    ap.add_argument('--low-priority', action='store_true')
    ap.add_argument('--cache-dir', default=os.path.join(ROOT, '.cache_fase2'))
    a = ap.parse_args()

    cache_dir = os.path.join(a.cache_dir, f'{a.tf}_{a.candles}')
    with open(os.path.join(cache_dir, 'manifest.json')) as f:
        manifest = json.load(f)
    # SOLO los 20 de Fase 1. Los 6 de Fase 1b quedan reservados (§2 del doc).
    syms = [s for s in SYMBOLS_FASE1
            if s in manifest and 'error' not in manifest[s]]
    print(f'universo del screen: {len(syms)} de los 20 de Fase 1 '
          f'(reservados y NO mirados: {RESERVADOS})', flush=True)

    jobs = [(s, cache_dir, a.low_priority) for s in syms]
    res = []
    t0 = time.perf_counter()
    with Pool(processes=a.workers) as pool:
        for k, r in enumerate(pool.imap_unordered(run_symbol, jobs), 1):
            res.append(r)
            el = time.perf_counter() - t0
            print(f'[{k}/{len(jobs)}] {r["symbol"]} ({r["secs"]}s) | '
                  f'ETA {el/k*(len(jobs)-k)/60:.1f} min', flush=True)

    # ── pooled por generador ──
    def pooled(getter):
        agg = {H: [0.0, 0.0, 0.0, 0] for H in HORIZONS}
        for r in res:
            d = getter(r)
            for H in HORIZONS:
                s = d[H]
                x = agg[H]
                x[0] += s[0]; x[1] += s[1]; x[2] += s[2]; x[3] += s[3]

        return {H: (v[0] / v[3], v[1] / v[3], v[2] / v[3], v[3])
                for H, v in agg.items() if v[3]}

    # control: p99 de la distribucion de close por horizonte (pooled por rep)
    ctl_p99, ctl_med = {}, {}
    for H in HORIZONS:
        per_rep = []
        for i in range(CONTROL_REPS):
            tot = sum(r['ctl'][i][H][2] for r in res)
            cnt = sum(r['ctl'][i][H][3] for r in res)
            if cnt:
                per_rep.append(tot / cnt)
        if per_rep:
            per_rep.sort()
            ctl_p99[H] = per_rep[min(len(per_rep) - 1, int(0.99 * len(per_rep)))]
            ctl_med[H] = per_rep[len(per_rep) // 2]

    print('\n' + '=' * 104)
    print(f'  FASE 3 — SCREEN DE GENERADORES  |  {a.tf}  |  {len(syms)} pares  |  '
          f'umbral: close > {COST_PIPS} p  Y  > p99 azar  Y  n >= {MIN_N}')
    print('=' * 104)
    print(f'{"generador":20} {"n":>9} | ' +
          ' '.join(f'{"H"+str(H):>9}' for H in HORIZONS) + '  | mejor')
    print('-' * 104)

    tabla, pasan = {}, []
    for name in GENERATORS:
        P = pooled(lambda r, nm=name: r['gen'][nm])
        if not P:
            continue
        tabla[name] = {str(H): P[H] for H in P}
        nmax = max(P[H][3] for H in P)
        best = max(P, key=lambda H: P[H][2])
        closes = ' '.join(f'{P[H][2]:>+9.3f}' for H in HORIZONS if H in P)
        ok = (P[best][2] > COST_PIPS and P[best][3] >= MIN_N
              and best in ctl_p99 and P[best][2] > ctl_p99[best])
        if ok:
            pasan.append((name, best, P[best][2]))
        print(f'{name:20} {nmax:>9,} | {closes}  | H{best} {P[best][2]:+.3f} '
              f'{"<<< PASA" if ok else ""}')

    print('-' * 104)
    print(f'{"REF-azar (mediana)":20} {"":>9} | ' +
          ' '.join(f'{ctl_med.get(H, 0):>+9.3f}' for H in HORIZONS))
    print(f'{"REF-azar (p99)":20} {"":>9} | ' +
          ' '.join(f'{ctl_p99.get(H, 0):>+9.3f}' for H in HORIZONS))
    print(f'{"REF-detector actual":20} {"":>9} |    -0.082    -0.109    -0.136 '
          f'   -0.162    -0.189    -0.251   (medido en 26 pares, commit 71616eb)')
    print('=' * 104)
    if pasan:
        print('  PASAN EL SCREEN:')
        for nm, H, v in sorted(pasan, key=lambda x: -x[2]):
            print(f'    {nm}  H={H}  close={v:+.3f} p')
        print('  => siguiente paso: arnes completo de Fase 2 (costos, swap, 4 sesiones,')
        print('     dos mitades) y DESPUES los 6 pares reservados. NO habilita a operar.')
    else:
        print('  NINGUNO PASA EL SCREEN.')
        print('  Por §5 del doc: ninguna de las 9 familias tiene edge extraible en M5')
        print('  sobre los 20 pares. No prueba que no exista edge en ningun lugar;')
        print('  si cierra esta familia de busqueda. Los 6 pares reservados siguen sin')
        print('  mirarse (no hay candidato que validar).')
    print('=' * 104)

    out = os.path.join(ROOT, 'docs', f'fase3_screen_{a.tf}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'tf': a.tf, 'symbols': syms, 'horizons': HORIZONS,
                   'cost_pips': COST_PIPS, 'min_n': MIN_N,
                   'generadores': tabla,
                   'control_p99': {str(k): v for k, v in ctl_p99.items()},
                   'control_mediana': {str(k): v for k, v in ctl_med.items()},
                   'pasan': [{'gen': n, 'H': h, 'close': v} for n, h, v in pasan]},
                  f, indent=2)
    print(f'json: {out}')


if __name__ == '__main__':
    main()
