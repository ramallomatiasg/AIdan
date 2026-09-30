"""
backtest_fase6_leo_smc.py — FASE 6: Setup 1 de Leo (SMC) en reglas mecánicas.

READ-ONLY. Cache `.cache_fase2/M5_500000` (sin MT5, sin DB de producción).
Criterio declarado ANTES de medir: docs/fase6_leo_smc_criterio.md (35d935f + enmienda a47a0d7).

Implementación (sin mirar el futuro):
  - M15/H1/H4 se arman desde el M5 por cubetas de hora del server. En la vela M5 i solo se usa la
    última vela de cada temporalidad que ya CERRÓ al cierre de la M5.
  - Swings = fractal de 2 velas por lado, confirmado 2 velas después.
  - Estructura: BOS por CIERRE contra el último swing confirmado (ya consumido no vuelve a disparar).
  - Extremo de M15 (bajista): el swing high MÁS ALTO confirmado desde el último BOS alcista (= el techo
    del movimiento previo, origen del movimiento general), reemplazado por uno más alto si aparece
    mientras siga bajista. (Enmienda 1 del criterio, antes de medir.)
    Zona = última vela alcista en o antes del extremo (hasta 10 velas atrás): [su mínimo, el extremo].
  - Decisional (secundario): el swing high vigente en cada BOS bajista (el que originó esa ruptura).

    python tools/backtest_fase6_leo_smc.py --workers 18
    python tools/backtest_fase6_leo_smc.py --reserved     # solo si los 20 pares dan PASA
"""
import argparse
import json
import os
import sys
import zlib
from multiprocessing import Pool

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci, set_low_priority  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_fase2', 'M5_500000')
REPS = 200
MAX_SL_PIPS = 10.0
BUF_PIPS = 0.5
MIN_TP_PIPS = 1.0
OB_LOOKBACK = 10
VARIANTS = ['principal', 'sec_decisional', 'sec_agresiva']
OUT = os.path.join(ROOT, 'docs', 'fase6_leo_smc_resultado.json')
OUT_RES = os.path.join(ROOT, 'docs', 'fase6_leo_smc_reservados.json')


def first_true(mask):
    return int(np.argmax(mask)) if mask.any() else mask.size


# ───────────────────────── velas y estructura ─────────────────────────
def resample(t, o, h, l, c, sec):
    g = t // sec
    ug, f = np.unique(g, return_index=True)
    last = np.r_[f[1:] - 1, t.size - 1]
    return {'o': o[f], 'h': np.maximum.reduceat(h, f), 'l': np.minimum.reduceat(l, f),
            'c': c[last], 'end': (ug + 1) * sec, 'n': ug.size}


def structure(B, zones=False):
    """Estado por vela cerrada j de la temporalidad. trend: +1/-1/0. Con zones=True, además la zona del
    extremo y la decisional para el lado vigente, y el extremo opuesto de la pierna (para el TP)."""
    o, h, l, c, n = B['o'], B['h'], B['l'], B['c'], B['n']
    trend = np.zeros(n, np.int8)
    Z = {k: np.full(n, np.nan) for k in ('lo', 'hi', 'leg', 'dlo', 'dhi')} if zones else None
    zid = np.zeros(n, np.int64) if zones else None
    did = np.zeros(n, np.int64) if zones else None
    alive = np.zeros(n, bool) if zones else None
    sh = sl = None                 # (precio, idx) último swing confirmado, no consumido
    sh_any = sl_any = None         # último swing confirmado (aunque consumido) — para la decisional
    sh_top = sl_bot = None         # swing más alto (bajo) desde el último BOS alcista (bajista) = techo (piso) de la pierna previa
    state = 0
    top_at_turn = bot_at_turn = None
    ext = None; leg = None; zlo = zhi = None; zone_alive = False; zcount = 0
    dlo = dhi = None; dcount = 0

    def ob(idx, bearish):
        for k in range(idx, max(-1, idx - OB_LOOKBACK - 1), -1):
            if (c[k] > o[k]) if bearish else (c[k] < o[k]):
                return k
        return idx

    for j in range(n):
        prev = state
        bos_dn = sl is not None and c[j] < sl[0]
        bos_up = sh is not None and c[j] > sh[0]
        if bos_dn and not bos_up:
            state = -1; sl = None; top_at_turn = sh_top; sl_bot = None
        elif bos_up and not bos_dn:
            state = 1; sh = None; bot_at_turn = sl_bot; sh_top = None
        if zones:
            if state == -1:
                if prev != -1:                      # giro a bajista: extremo = techo de la pierna previa
                    ext = top_at_turn if top_at_turn is not None else sh_any; leg = None
                    if ext is not None:
                        k = ob(ext[1], True); zlo, zhi = l[k], ext[0]; zone_alive = True; zcount += 1
                if bos_dn and sh_any is not None:  # decisional = swing high que originó esta ruptura
                    k = ob(sh_any[1], True); dlo, dhi = l[k], sh_any[0]; dcount += 1
                leg = l[j] if leg is None else min(leg, l[j])
                if zone_alive and zhi is not None and c[j] > zhi:
                    zone_alive = False
            elif state == 1:
                if prev != 1:
                    ext = bot_at_turn if bot_at_turn is not None else sl_any; leg = None
                    if ext is not None:
                        k = ob(ext[1], False); zlo, zhi = ext[0], h[k]; zone_alive = True; zcount += 1
                if bos_up and sl_any is not None:
                    k = ob(sl_any[1], False); dlo, dhi = sl_any[0], h[k]; dcount += 1
                leg = h[j] if leg is None else max(leg, h[j])
                if zone_alive and zlo is not None and c[j] < zlo:
                    zone_alive = False
        # confirmar swings nuevos (vela m = j-2) DESPUÉS del chequeo de BOS de esta vela
        if j >= 4:
            m = j - 2
            if h[m] > h[m - 2] and h[m] > h[m - 1] and h[m] > h[m + 1] and h[m] > h[m + 2]:
                sh = (h[m], m); sh_any = sh
                if sh_top is None or h[m] > sh_top[0]:
                    sh_top = sh
                if zones and state == -1 and ext is not None and h[m] > ext[0]:
                    ext = sh; k = ob(m, True); zlo, zhi = l[k], h[m]; zone_alive = True; zcount += 1
            if l[m] < l[m - 2] and l[m] < l[m - 1] and l[m] < l[m + 1] and l[m] < l[m + 2]:
                sl = (l[m], m); sl_any = sl
                if sl_bot is None or l[m] < sl_bot[0]:
                    sl_bot = sl
                if zones and state == 1 and ext is not None and l[m] < ext[0]:
                    ext = sl; k = ob(m, False); zlo, zhi = l[m], h[k]; zone_alive = True; zcount += 1
        trend[j] = state
        if zones:
            if zlo is not None:
                Z['lo'][j], Z['hi'][j] = zlo, zhi
            if leg is not None:
                Z['leg'][j] = leg
            if dlo is not None:
                Z['dlo'][j], Z['dhi'][j] = dlo, dhi
            zid[j], did[j], alive[j] = zcount, dcount, zone_alive
    out = {'trend': trend}
    if zones:
        out.update(Z); out.update({'zid': zid, 'did': did, 'alive': alive})
    return out


# ───────────────────────── simulación de un trade ─────────────────────────
def sim_trade(h, l, c, k, b, E, dirn, S, T, fill_bar_check):
    """Pips del trade. Entrada en la vela k (al cierre si fill_bar_check=False; dentro de k si True).
    Stop S, TP T, break-even al 50% del camino al TP, salida al cierre de b."""
    if fill_bar_check and ((l[k] <= S) if dirn > 0 else (h[k] >= S)):
        return dirn * (S - E)
    if k >= b:
        return dirn * (c[b] - E)
    hh, ll = h[k + 1:b + 1], l[k + 1:b + 1]
    n = hh.size
    be = E + dirn * 0.5 * abs(T - E)
    if dirn > 0:
        i_sl, i_tp, i_be = first_true(ll <= S), first_true(hh >= T), first_true(hh >= be)
    else:
        i_sl, i_tp, i_be = first_true(hh >= S), first_true(ll <= T), first_true(ll <= be)
    if i_be >= min(i_sl, i_tp):             # SL o TP antes de armar el BE (empate ⇒ SL)
        if i_sl == n and i_tp == n:
            return dirn * (c[b] - E)
        return dirn * (S - E) if i_sl <= i_tp else dirn * (T - E)
    if i_tp == i_be:                         # misma vela arma el BE y toca el TP (SL no tocado)
        return dirn * (T - E)
    rest_h, rest_l = hh[i_be + 1:], ll[i_be + 1:]
    if dirn > 0:
        j_sl, j_tp = first_true(rest_l <= E), first_true(rest_h >= T)
    else:
        j_sl, j_tp = first_true(rest_h >= E), first_true(rest_l <= T)
    if j_tp < j_sl:
        return dirn * (T - E)
    if j_sl < rest_h.size:
        return 0.0
    return dirn * (c[b] - E)


# ───────────────────────── un par ─────────────────────────
def load(sym):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.spec.json')) as f:
        spec = json.load(f)
    return r, spec


def run_pair(job):
    sym, low = job
    if low:
        set_low_priority()
    r, spec = load(sym)
    pip = spec['pip']
    t = r['time'].astype(np.int64)
    o, h, l, c = (r[k].astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    spr = r['spread'].astype(np.float64) / 10.0
    close_t = t + 300
    B15, B1, B4 = resample(t, o, h, l, c, 900), resample(t, o, h, l, c, 3600), resample(t, o, h, l, c, 14400)
    S15, S1, S4 = structure(B15, zones=True), structure(B1), structure(B4)
    j15 = np.searchsorted(B15['end'], close_t, side='right') - 1
    j1 = np.searchsorted(B1['end'], close_t, side='right') - 1
    j4 = np.searchsorted(B4['end'], close_t, side='right') - 1
    day = t // 86400
    dlast = np.r_[np.where(np.diff(day) != 0)[0], t.size - 1]
    day_end = dlast[np.searchsorted(dlast, np.arange(t.size))]
    # swings M5 confirmados en la vela i (bar i-2)
    n = t.size
    swl = np.full(n, np.nan); swh = np.full(n, np.nan)
    m = np.arange(2, n - 2)
    is_l = (l[m] < l[m - 2]) & (l[m] < l[m - 1]) & (l[m] < l[m + 1]) & (l[m] < l[m + 2])
    is_h = (h[m] > h[m - 2]) & (h[m] > h[m - 1]) & (h[m] > h[m + 1]) & (h[m] > h[m + 2])
    swl[m[is_l] + 2] = l[m[is_l]]; swh[m[is_h] + 2] = h[m[is_h]]
    comm = spec['commission_pips']
    res = {v: [] for v in VARIANTS}

    for var in VARIANTS:
        klo, khi, kid = ('dlo', 'dhi', 'did') if var == 'sec_decisional' else ('lo', 'hi', 'zid')
        used = set(); busy_until = -1
        in_zone = False; cur = None; mx = mn = None; last_sw = None; entry_i = None
        for i in range(200, n - 1):
            a, b_, d4 = j15[i], j1[i], j4[i]
            if a < 0 or b_ < 0 or d4 < 0:
                continue
            tr = S15['trend'][a]
            D = tr if (tr != 0 and S1['trend'][b_] == tr and S4['trend'][d4] == tr) else 0
            zl, zh, zi = S15[klo][a], S15[khi][a], S15[kid][a]
            ok = D != 0 and np.isfinite(zl) and zi > 0 and (var == 'sec_decisional' or S15['alive'][a])
            key = (int(D), int(zi))
            if not ok or key in used or i <= busy_until:
                in_zone = False; cur = None
                continue
            if cur != key:
                in_zone = False; cur = key
            leg = S15['leg'][a]
            if not np.isfinite(leg):
                continue
            if D == -1:
                touched = h[i] >= zl
            else:
                touched = l[i] <= zh
            if var == 'sec_agresiva':
                if not touched:
                    continue
                used.add(key)
                E = max(zl, o[i]) if D == -1 else min(zh, o[i])
                S = (zh + BUF_PIPS * pip) if D == -1 else (zl - BUF_PIPS * pip)
                T = (leg - BUF_PIPS * pip) if D == -1 else (leg + BUF_PIPS * pip)
                sl_p, tp_p = abs(S - E) / pip, abs(E - T) / pip
                if sl_p > MAX_SL_PIPS or sl_p <= 0 or tp_p < MIN_TP_PIPS or D * (T - E) <= 0:
                    continue
                b = day_end[i]
                g = sim_trade(h, l, c, i, b, E, D, S, T, True) / pip
                res[var].append((int(t[i]), int(D), g - comm - spr[i], sl_p, tp_p))
                busy_until = b
                continue
            if not in_zone:
                if touched:
                    in_zone = True; entry_i = i; mx = h[i]; mn = l[i]; last_sw = None
                continue
            mx, mn = max(mx, h[i]), min(mn, l[i])
            if D == -1:
                if np.isfinite(swl[i]) and i - 2 >= entry_i:
                    last_sw = swl[i]
                if last_sw is not None and c[i] < last_sw:
                    used.add(key)
                    E = c[i]; S = max(zh, mx) + BUF_PIPS * pip; T = leg - BUF_PIPS * pip
                else:
                    continue
            else:
                if np.isfinite(swh[i]) and i - 2 >= entry_i:
                    last_sw = swh[i]
                if last_sw is not None and c[i] > last_sw:
                    used.add(key)
                    E = c[i]; S = min(zl, mn) - BUF_PIPS * pip; T = leg + BUF_PIPS * pip
                else:
                    continue
            sl_p, tp_p = abs(S - E) / pip, abs(E - T) / pip
            in_zone = False
            if sl_p > MAX_SL_PIPS or sl_p <= 0 or tp_p < MIN_TP_PIPS or D * (T - E) <= 0:
                continue
            b = day_end[i]
            g = sim_trade(h, l, c, i, b, E, D, S, T, False) / pip
            res[var].append((int(t[i]), int(D), g - comm - spr[i], sl_p, tp_p))
            busy_until = b

    # control: velas al azar, distancias de SL/TP sorteadas de los trades reales, mismos costos
    ctrl = {}
    for var in VARIANTS:
        tr = res[var]
        sums = np.zeros(REPS)
        if tr:
            rng = np.random.default_rng(zlib.crc32(f'{sym}|{var}|f6'.encode()))
            p_long = np.mean([x[1] > 0 for x in tr])
            dist = np.array([(x[3], x[4]) for x in tr])
            for r_ in range(REPS):
                ks = rng.integers(200, n - 2, len(tr))
                picks = dist[rng.integers(0, len(tr), len(tr))]
                tot = 0.0
                for k, (slp, tpp) in zip(ks, picks):
                    dn = 1 if rng.random() < p_long else -1
                    E = c[k]; S = E - dn * slp * pip; T = E + dn * tpp * pip
                    tot += sim_trade(h, l, c, k, day_end[k], E, dn, S, T, False) / pip - comm - spr[k]
                sums[r_] = tot
        ctrl[var] = sums
    return sym, res, ctrl, (t[-1] - t[200]) / 86400 * 5 / 7


def evaluate(results, var, reserved):
    rows = [(s, np.array([x[2] for x in r[var]]), np.array([x[0] for x in r[var]]), c[var], d)
            for s, r, c, d in results if r[var]]
    if not rows:
        return {'n': 0, 'veredicto': 'SIN TRADES'}
    net = np.concatenate([x[1] for x in rows]); tt = np.concatenate([x[2] for x in rows])
    n = net.size
    ctrl = np.sort(sum(x[3] for x in rows) / n)
    mid = tt.min() + (tt.max() - tt.min()) / 2
    lo, hi, _ = bootstrap_ci(net)
    m1, m2 = float(net[tt < mid].mean()), float(net[tt >= mid].mean())
    pos = sum(1 for x in rows if x[1].mean() > 0)
    mean = float(net.mean()); p95 = float(ctrl[int(0.95 * REPS)])
    allr = [y for _, r, _, _ in results for y in r[var]]
    c = {'c1_neto_pos': mean > 0, 'c2_ci_lo_pos': lo is not None and lo > 0,
         'c3_dos_mitades': m1 > 0 and m2 > 0, 'c4_supera_p95': mean > p95,
         'c5_60pct_pares': pos / len(rows) >= 0.6}
    ver = ('PASA OOS' if mean > 0 and mean > p95 else 'NO PASA OOS') if reserved else \
          ('PASA' if all(c.values()) else 'NO PASA')
    return {'n': int(n), 'trades_dia_par': round(n / sum(x[4] for x in rows), 3),
            'neto': round(mean, 3), 'ci95': [lo, hi], 'mitad_1': round(m1, 3), 'mitad_2': round(m2, 3),
            'win_pct': round(float((net > 0).mean()) * 100, 1),
            'sl_med': round(float(np.median([x[3] for x in allr])), 2),
            'tp_med': round(float(np.median([x[4] for x in allr])), 2),
            'control_mediana': round(float(ctrl[REPS // 2]), 3), 'control_p95': round(p95, 3),
            'pares_positivos': f'{pos}/{len(rows)}', 'condiciones': c, 'veredicto': ver,
            'por_par': sorted([{'symbol': s, 'n': int(x.size), 'neto': round(float(x.mean()), 3)}
                               for s, x, _, _, _ in rows], key=lambda z: -z['neto'])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=18)
    ap.add_argument('--reserved', action='store_true')
    ap.add_argument('--low-priority', action='store_true')
    ap.add_argument('--symbols', default=None, help='solo smoke; el veredicto es con los 20')
    a = ap.parse_args()
    if a.reserved:
        with open(OUT, encoding='utf-8') as f:
            if json.load(f)['variantes']['principal']['veredicto'] != 'PASA':
                raise SystemExit('La principal no pasó en los 20 pares: por criterio los reservados NO se miran.')
        syms = list(RESERVADOS)
    else:
        syms = a.symbols.split(',') if a.symbols else list(SYMBOLS_FASE1)
    with Pool(min(a.workers, len(syms))) as pool:
        results = pool.map(run_pair, [(s, a.low_priority) for s in syms])
    out = {'criterio': 'docs/fase6_leo_smc_criterio.md (35d935f + enmienda a47a0d7)', 'pares': syms,
           'variantes': {v: evaluate(results, v, a.reserved) for v in VARIANTS}}
    path = OUT_RES if a.reserved else (OUT.replace('.json', '_smoke.json') if a.symbols else OUT)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=bool)
    for v, r in out['variantes'].items():
        tag = '<== DECIDE' if v == 'principal' else '(descriptivo)'
        if r['n'] == 0:
            print(f'{v:15} sin trades'); continue
        print(f"{v:15} {tag}  n={r['n']}  {r['trades_dia_par']}/día/par  NETO={r['neto']:+.3f}p  "
              f"CI=[{r['ci95'][0]:+.2f},{r['ci95'][1]:+.2f}]  mitades {r['mitad_1']:+.2f}/{r['mitad_2']:+.2f}  "
              f"ganados {r['win_pct']}%  SL med {r['sl_med']}p TP med {r['tp_med']}p  "
              f"ctrl p95 {r['control_p95']:+.3f}  pares+ {r['pares_positivos']}  -> {r['veredicto']}")
    print(f'json: {path}')


if __name__ == '__main__':
    main()
