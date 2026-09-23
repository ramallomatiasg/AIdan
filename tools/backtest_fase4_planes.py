"""
backtest_fase4_planes.py — FASE 4: planes PLANIFICADOS (estilo Leo + evidencia publicada).

READ-ONLY. Lee el cache `.cache_fase2/M5_500000` (sin MT5, sin DB de producción).
Criterio declarado ANTES de medir: docs/fase4_planes_criterio.md (fc3bc22). Leer contra eso:
8 candidatos congelados, control aleatorio p99, 20 pares, reservados solo si alguno pasa.

    python tools/backtest_fase4_planes.py --workers 18
    python tools/backtest_fase4_planes.py --reserved      # solo los candidatos que pasaron
"""
import argparse
import json
import os
import sys
import zlib
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci, set_low_priority  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_fase2', 'M5_500000')
REPS = 200
ADR_N = 14
SL_ADR = 0.25
CANDS = ['L1_prev_day_fade', 'L2_bb_h1_T', 'L3_trend_pullback_pdl', 'E1_round_numbers',
         'E2_home_hours', 'E3a_usd_pre_fix', 'E3b_usd_post_fix', 'E4_tsmom_60d']
LEVEL_CANDS = CANDS[:4]
HOME = {'EUR': (7, 12), 'GBP': (7, 12), 'CHF': (7, 12), 'USD': (13, 20), 'CAD': (13, 20),
        'JPY': (0, 6), 'AUD': (0, 6), 'NZD': (0, 6)}
OUT = os.path.join(ROOT, 'docs', 'fase4_planes_resultado.json')
OUT_RES = os.path.join(ROOT, 'docs', 'fase4_planes_reservados.json')


# ───────────────────────── calendario ─────────────────────────
def _nth_sunday(y, m, n):
    d = datetime(y, m, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_sunday(y, m):
    d = datetime(y, m + 1, 1) - timedelta(days=1) if m < 12 else datetime(y, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def us_dst(dt):
    return _nth_sunday(dt.year, 3, 2) <= dt < _nth_sunday(dt.year, 11, 1)


def uk_bst(dt):
    return _last_sunday(dt.year, 3) <= dt < _last_sunday(dt.year, 10)


def first_true(mask):
    """Índice del primer True o len(mask) si no hay."""
    return int(np.argmax(mask)) if mask.any() else mask.size


# ───────────────────────── datos por par ─────────────────────────
def load_pair(sym):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.spec.json')) as f:
        spec = json.load(f)
    P = {'sym': sym, 'spec': spec, 'pip': spec['pip']}
    for k in ('open', 'high', 'low', 'close'):
        P[k[0]] = r[k].astype(np.float64)
    P['t'] = r['time'].astype(np.int64)
    P['spr'] = r['spread'].astype(np.float64) / 10.0
    t = P['t']
    day = t // 86400
    ud, first = np.unique(day, return_index=True)
    last = np.r_[first[1:] - 1, t.size - 1]
    P['day'], P['ud'], P['dfirst'], P['dlast'] = day, ud, first, last
    P['dopen'] = P['o'][first]
    P['dclose'] = P['c'][last]
    P['dhigh'] = np.maximum.reduceat(P['h'], first)
    P['dlow'] = np.minimum.reduceat(P['l'], first)
    rng_ = P['dhigh'] - P['dlow']
    adr = np.full(ud.size, np.nan)
    cs = np.r_[0, np.cumsum(rng_)]
    adr[ADR_N:] = (cs[ADR_N:-1] - cs[:-ADR_N - 1]) / ADR_N        # días previos, sin el actual
    P['adr'] = adr
    # UTC por barra (offset por día del server)
    off = np.array([3 if us_dst(datetime.fromtimestamp(int(d) * 86400, timezone.utc).replace(tzinfo=None))
                    else 2 for d in ud])
    P['utc'] = t - np.repeat(off, np.diff(np.r_[first, t.size])) * 3600
    # pesos de swap por noche que termina en el día D (miércoles 3, sáb/dom 0)
    d0, d1 = int(ud.min()), int(ud.max()) + 2
    wd = (np.arange(d0, d1) + 3) % 7
    w = np.where(wd == 2, 3.0, np.where(wd >= 5, 0.0, 1.0))
    P['cumw'] = np.r_[0.0, np.cumsum(w)]
    P['d0'] = d0
    return P


def swap_pips(P, i_in, i_out, dirn):
    de = (P['t'][i_in] // 86400) - P['d0']
    dx = (P['t'][i_out] // 86400) - P['d0']
    nights = P['cumw'][dx] - P['cumw'][de]
    s = P['spec']
    return nights * np.where(dirn > 0, s['swap_long_pips'], s['swap_short_pips'])


# ───────────────────────── simulador de planes con nivel ─────────────────────────
def sim_exits(P, k, b, E, dirn, R):
    """Pips de la posición completa (promedio de las 3 partes). Entrada en la vela k, fin en b."""
    h, l, c, pip = P['h'], P['l'], P['c'], P['pip']
    Rp = R * pip
    S = E - dirn * Rp
    T = (E + dirn * Rp, E + 2 * dirn * Rp, E + 3 * dirn * Rp)
    if (l[k] <= S) if dirn > 0 else (h[k] >= S):          # vela del fill: solo SL
        return -R
    if k >= b:
        return dirn * (c[b] - E) / pip
    hh, ll = h[k + 1:b + 1], l[k + 1:b + 1]
    n = hh.size
    tclose = dirn * (c[b] - E) / pip
    if dirn > 0:
        i_sl, i_t1 = first_true(ll <= S), first_true(hh >= T[0])
    else:
        i_sl, i_t1 = first_true(hh >= S), first_true(ll <= T[0])
    if i_sl <= i_t1:
        return tclose if i_sl == n else -R                   # empate => SL
    res = R / 3
    for m in (2, 3):
        if dirn > 0:
            tph, beh = hh[i_t1:] >= T[m - 1], ll[i_t1 + 1:] <= E
        else:
            tph, beh = ll[i_t1:] <= T[m - 1], hh[i_t1 + 1:] >= E
        i_tp = first_true(tph)
        i_be = first_true(beh) + 1
        if i_tp < tph.size and i_tp < i_be:
            res += m * R / 3
        elif i_be <= beh.size:
            res += 0.0
        else:
            res += tclose / 3
    return res


def fill_limit(P, a, b, L, dirn):
    """Primera vela en [a, b] que toca el nivel. Devuelve (k, precio) o None."""
    if dirn < 0:
        hit = P['h'][a:b + 1] >= L
    else:
        hit = P['l'][a:b + 1] <= L
    if not hit.any():
        return None
    k = a + int(np.argmax(hit))
    o = P['o'][k]
    return k, (max(L, o) if dirn < 0 else min(L, o))


def level_trade(P, k, b, E, dirn, R):
    g = sim_exits(P, k, b, E, dirn, R)
    net = g - P['spec']['commission_pips'] - P['spr'][k]     # intradía: sin rollover
    return net


# ───────────────────────── generadores ─────────────────────────
def gen_level_plans(P):
    """Devuelve {cand: [(k, dirn, net, t), ...]} para L1, L2, L3, E1."""
    out = {c: [] for c in LEVEL_CANDS}
    pip, ud = P['pip'], P['ud']
    dh, dl, dc, adr = P['dhigh'], P['dlow'], P['dclose'], P['adr']
    sma = np.full(ud.size, np.nan)
    cs = np.r_[0, np.cumsum(dc)]
    sma[19:] = (cs[20:] - cs[:-20]) / 20
    step = 50 * pip
    for d in range(ADR_N + 6, ud.size):
        if not np.isfinite(adr[d]):
            continue
        a, b = P['dfirst'][d], P['dlast'][d]
        R = SL_ADR * adr[d] / pip
        if R <= 0 or b - a < 12:
            continue
        pdh, pdl = dh[d - 1], dl[d - 1]
        up = dc[d - 1] > sma[d - 1] and sma[d - 1] > sma[d - 6]
        dn = dc[d - 1] < sma[d - 1] and sma[d - 1] < sma[d - 6]
        orders = [('L1_prev_day_fade', pdh, -1), ('L1_prev_day_fade', pdl, 1)]
        if up:
            orders.append(('L3_trend_pullback_pdl', pdl, 1))
        if dn:
            orders.append(('L3_trend_pullback_pdl', pdh, -1))
        op = P['dopen'][d]
        above = np.ceil(op / step) * step
        below = np.floor(op / step) * step
        if np.isclose(above, op):
            above += step
        if np.isclose(below, op):
            below -= step
        orders += [('E1_round_numbers', above, -1), ('E1_round_numbers', below, 1)]
        for cand, L, dirn in orders:
            f = fill_limit(P, a, b, L, dirn)
            if f is None:
                continue
            k, E = f
            out[cand].append((k, dirn, level_trade(P, k, b, E, dirn, R), int(P['t'][k])))
    # L2: Bollinger H1 + vela T
    t = P['t']
    hr = t // 3600
    uh, hf = np.unique(hr, return_index=True)
    hl = np.r_[hf[1:] - 1, t.size - 1]
    H_o, H_c = P['o'][hf], P['c'][hl]
    H_h, H_l = np.maximum.reduceat(P['h'], hf), np.minimum.reduceat(P['l'], hf)
    n = uh.size
    ma = np.full(n, np.nan); sd = np.full(n, np.nan)
    c1, c2 = np.r_[0, np.cumsum(H_c)], np.r_[0, np.cumsum(H_c * H_c)]
    ma[19:] = (c1[20:] - c1[:-20]) / 20
    sd[19:] = np.sqrt(np.maximum((c2[20:] - c2[:-20]) / 20 - ma[19:] ** 2, 0))
    prevc = np.r_[H_c[0], H_c[:-1]]
    tr = np.maximum(H_h - H_l, np.maximum(abs(H_h - prevc), abs(H_l - prevc)))
    atr = np.full(n, np.nan)
    c3 = np.r_[0, np.cumsum(tr)]
    atr[13:] = (c3[14:] - c3[:-14]) / 14
    day_of_bar = P['day']
    for j in range(20, n - 1):
        if not (np.isfinite(ma[j]) and np.isfinite(atr[j])) or uh[j + 1] != uh[j] + 1:
            continue
        rg = H_h[j] - H_l[j]
        if rg <= 0:
            continue
        up_w = H_h[j] - max(H_o[j], H_c[j])
        lo_w = min(H_o[j], H_c[j]) - H_l[j]
        k = hf[j + 1]
        if day_of_bar[k] != day_of_bar[hl[j]]:
            continue
        di = np.searchsorted(P['ud'], day_of_bar[k])
        b = P['dlast'][di]
        E = P['o'][k]
        if H_h[j] >= ma[j] + 2 * sd[j] and up_w >= 0.6 * rg and (H_c[j] - H_l[j]) <= 0.4 * rg:
            S = H_h[j] + 0.1 * atr[j]
            R = (S - E) / P['pip']
            if R > 0:
                out['L2_bb_h1_T'].append((k, -1, level_trade(P, k, b, E, -1, R), int(t[k])))
        elif H_l[j] <= ma[j] - 2 * sd[j] and lo_w >= 0.6 * rg and (H_h[j] - H_c[j]) <= 0.4 * rg:
            S = H_l[j] - 0.1 * atr[j]
            R = (E - S) / P['pip']
            if R > 0:
                out['L2_bb_h1_T'].append((k, 1, level_trade(P, k, b, E, 1, R), int(t[k])))
    return out


def windows(P, ws_utc_min, we_utc_min):
    """Pares (i_in, i_out) de ventanas COMPLETAS [ws, we) en minutos UTC, por fecha UTC.

    ws/we son arrays por fecha UTC (para el fixing, que cambia con BST) o escalares.
    """
    u = P['utc']
    ud_ = u // 86400
    mins = (u % 86400) // 60
    dates = np.unique(ud_)
    ws = np.broadcast_to(ws_utc_min, dates.shape) if np.ndim(ws_utc_min) == 0 else ws_utc_min
    we = np.broadcast_to(we_utc_min, dates.shape) if np.ndim(we_utc_min) == 0 else we_utc_min
    need = None
    res = []
    starts = np.searchsorted(ud_, dates)
    ends = np.r_[starts[1:], u.size]
    for k, dt in enumerate(dates):
        s, e = starts[k], ends[k]
        m = mins[s:e]
        sel = np.where((m >= ws[k]) & (m < we[k]))[0]
        need = (we[k] - ws[k]) // 5
        if sel.size != need or m[sel[0]] != ws[k]:
            continue
        res.append((s + sel[0], s + sel[-1]))
    return res


def gen_time_plans(P):
    out = {c: [] for c in CANDS[4:]}
    sym, pip, spec = P['sym'], P['pip'], P['spec']
    base, quote = sym[:3], sym[3:]

    def add(cand, i_in, i_out, dirn):
        g = dirn * (P['c'][i_out] - P['o'][i_in]) / pip
        net = g - spec['commission_pips'] - P['spr'][i_in] + float(swap_pips(P, i_in, i_out, dirn))
        out[cand].append((i_in, dirn, net, int(P['t'][i_in]), i_out - i_in))

    # E2 horario local
    for cur, dirn in ((base, -1), (quote, 1)):
        other = quote if cur == base else base
        if cur not in HOME or HOME.get(other) == HOME[cur]:
            continue
        ws, we = HOME[cur]
        for i_in, i_out in windows(P, ws * 60, we * 60):
            add('E2_home_hours', i_in, i_out, dirn)
    # E3 fixing de Londres (16:00 Londres)
    if 'USD' in (base, quote):
        usd_buy = 1 if base == 'USD' else -1
        dates = np.unique(P['utc'] // 86400)
        fix = np.array([(15 if uk_bst(datetime.fromtimestamp(int(d) * 86400, timezone.utc)
                                        .replace(tzinfo=None) + timedelta(hours=12)) else 16) * 60
                        for d in dates])
        for i_in, i_out in windows(P, fix - 60, fix):
            add('E3a_usd_pre_fix', i_in, i_out, usd_buy)
        for i_in, i_out in windows(P, fix, fix + 60):
            add('E3b_usd_post_fix', i_in, i_out, -usd_buy)
    # E4 momentum 60 días, semanal
    ud, dc = P['ud'], P['dclose']
    wd = (ud + 3) % 7
    mon = np.where(wd == 0)[0]
    for a_, b_ in zip(mon[:-1], mon[1:]):
        if a_ < 61:
            continue
        r = dc[a_ - 1] - dc[a_ - 61]
        if r == 0:
            continue
        add('E4_tsmom_60d', P['dfirst'][a_], P['dlast'][b_ - 1], 1 if r > 0 else -1)
    return out


# ───────────────────────── control ─────────────────────────
def control_level(P, trades, rng):
    """Entradas al azar a mercado, SL = 0,25 × ADR del día, mismas 3 partes, fin del día."""
    n = len(trades)
    if n == 0:
        return np.zeros(REPS)
    p_long = np.mean([x[1] > 0 for x in trades])
    ok_days = np.where(np.isfinite(P['adr']))[0]
    sums = np.zeros(REPS)
    for r_ in range(REPS):
        ds = rng.choice(ok_days, n)
        tot = 0.0
        for d in ds:
            a, b = P['dfirst'][d], P['dlast'][d]
            if b - a < 2:
                continue
            k = int(rng.integers(a, b))
            dirn = 1 if rng.random() < p_long else -1
            R = SL_ADR * P['adr'][d] / P['pip']
            tot += level_trade(P, k, b, P['o'][k], dirn, R)
        sums[r_] = tot
    return sums


def control_time(P, trades, rng):
    n = len(trades)
    if n == 0:
        return np.zeros(REPS)
    p_long = np.mean([x[1] > 0 for x in trades])
    durs = np.array([x[4] for x in trades])
    spec, pip = P['spec'], P['pip']
    sums = np.zeros(REPS)
    N = P['t'].size
    for r_ in range(REPS):
        dur = rng.choice(durs, n)
        i_in = rng.integers(100, N - dur.max() - 1, n)
        i_out = i_in + dur
        dirn = np.where(rng.random(n) < p_long, 1, -1)
        g = dirn * (P['c'][i_out] - P['o'][i_in]) / pip
        net = g - spec['commission_pips'] - P['spr'][i_in] + swap_pips(P, i_in, i_out, dirn)
        sums[r_] = float(net.sum())
    return sums


def run_pair(job):
    sym, only, low = job
    if low:
        set_low_priority()
    P = load_pair(sym)
    trades = {}
    trades.update(gen_level_plans(P))
    trades.update(gen_time_plans(P))
    res = {}
    for cand in CANDS:
        if only and cand not in only:
            continue
        tr = trades.get(cand, [])
        rng = np.random.default_rng(zlib.crc32(f'{sym}|{cand}|f4'.encode()))
        ctrl = control_level(P, tr, rng) if cand in LEVEL_CANDS else control_time(P, tr, rng)
        res[cand] = {'net': np.array([x[2] for x in tr], dtype=np.float64),
                     't': np.array([x[3] for x in tr], dtype=np.int64),
                     'long': np.array([x[1] > 0 for x in tr]),
                     'ctrl': ctrl, 'n': len(tr),
                     'dias': (P['t'][-1] - P['t'][100]) / 86400 * 5 / 7}
    return sym, res


def evaluate(results, cand, reserved):
    rows = [(s, r[cand]) for s, r in results if cand in r and r[cand]['n'] > 0]
    if not rows:
        return {'n': 0, 'veredicto': 'SIN TRADES'}
    net = np.concatenate([r['net'] for _, r in rows])
    tt = np.concatenate([r['t'] for _, r in rows])
    n = net.size
    ctrl = np.sort(sum(r['ctrl'] for _, r in rows) / n)
    t0, t1 = tt.min(), tt.max()
    mid = t0 + (t1 - t0) / 2
    lo, hi, _ = bootstrap_ci(net)
    m1, m2 = float(net[tt < mid].mean()), float(net[tt >= mid].mean())
    pos = sum(1 for _, r in rows if r['net'].mean() > 0)
    mean = float(net.mean())
    p95, p99 = float(ctrl[int(0.95 * REPS)]), float(ctrl[int(0.99 * REPS)])
    c = {'c1_neto_pos': mean > 0, 'c2_ci_lo_pos': lo is not None and lo > 0,
         'c3_dos_mitades': m1 > 0 and m2 > 0, 'c4_supera_p99': mean > p99,
         'c5_60pct_pares': pos / len(rows) >= 0.6}
    if reserved:
        ver = 'PASA OOS' if (mean > 0 and mean > p95) else 'NO PASA OOS'
    else:
        ver = 'PASA' if all(c.values()) else 'NO PASA'
    return {'n': int(n), 'trades_dia_par': round(n / sum(r['dias'] for _, r in rows), 3),
            'neto': round(mean, 4), 'ci95': [lo, hi], 'mitad_1': round(m1, 4), 'mitad_2': round(m2, 4),
            'control_mediana': round(float(ctrl[REPS // 2]), 4), 'control_p95': round(p95, 4),
            'control_p99': round(p99, 4), 'pares_positivos': f'{pos}/{len(rows)}',
            'pct_long': round(float(np.concatenate([r['long'] for _, r in rows]).mean()), 3),
            'condiciones': c, 'veredicto': ver,
            'por_par': sorted([{'symbol': s, 'n': int(r['n']), 'neto': round(float(r['net'].mean()), 3)}
                               for s, r in rows], key=lambda x: -x['neto'])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=18)
    ap.add_argument('--reserved', action='store_true')
    ap.add_argument('--low-priority', action='store_true')
    ap.add_argument('--symbols', default=None, help='solo para smoke; el veredicto es con los 20')
    a = ap.parse_args()
    only = None
    if a.reserved:
        with open(OUT, encoding='utf-8') as f:
            prev = json.load(f)['candidatos']
        only = [c for c, v in prev.items() if v.get('veredicto') == 'PASA' and not c.startswith('E3')]
        if not only:
            raise SystemExit('Ningún candidato (con out-of-sample posible) pasó en los 20 pares: '
                             'por criterio los reservados NO se miran.')
        syms = list(RESERVADOS)
    else:
        syms = a.symbols.split(',') if a.symbols else list(SYMBOLS_FASE1)
    with Pool(min(a.workers, len(syms))) as pool:
        results = pool.map(run_pair, [(s, only, a.low_priority) for s in syms])
    out = {'criterio': 'docs/fase4_planes_criterio.md (fc3bc22)', 'pares': syms, 'candidatos': {}}
    for cand in (only or CANDS):
        out['candidatos'][cand] = evaluate(results, cand, a.reserved)
    path = OUT_RES if a.reserved else (OUT if not a.symbols else OUT.replace('.json', '_smoke.json'))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=bool)
    print(f"{'candidato':24} {'n':>7} {'t/día/par':>9} {'NETO':>7} {'CI95':>17} {'mitades':>15} "
          f"{'ctrl p99':>8} {'pares+':>6}  veredicto")
    for cand, v in out['candidatos'].items():
        if v['n'] == 0:
            print(f'{cand:24} sin trades')
            continue
        ci = f"[{v['ci95'][0]:+.2f},{v['ci95'][1]:+.2f}]"
        print(f"{cand:24} {v['n']:>7} {v['trades_dia_par']:>9} {v['neto']:>+7.3f} {ci:>17} "
              f"{v['mitad_1']:+.2f}/{v['mitad_2']:+.2f} {v['control_p99']:>+8.3f} {v['pares_positivos']:>6}  "
              f"{v['veredicto']}")
    print(f'json: {path}')


if __name__ == '__main__':
    main()
