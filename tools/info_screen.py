"""
info_screen.py — P29: ¿qué dato anticipa el retorno? Screen de INFORMACIÓN antes de armar cualquier estrategia.

Criterio declarado ANTES de medir: docs/p29_info_screen_criterio.md. Contexto: docs/fuentes_de_ventaja_2026-11-04.md.
READ-ONLY: sin MT5, sin la DB de AIdan. Lee los caches ya bajados (.cache_fase2, .cache_p1, .cache_p15).

Por celda (instrumento × dato × horizonte): IC de Spearman en descubrimiento (70%) y reserva (30%), placebo por
corrimiento circular, y prueba económica (quintiles del descubrimiento aplicados en la reserva, neto de costo).
Todo en retorno relativo; el costo se expresa como fracción del precio de entrada.

Nota: la "hora" es la hora del SERVIDOR de MT5 (UTC+2/+3), que sigue a las sesiones igual que el horario de verano.

Uso:
    python tools/info_screen.py            # corre todo el catálogo y escribe docs/p29_info_screen_resultado.json
"""
import json
import os
import sys
import zlib

import numpy as np
from scipy.stats import spearmanr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
OUT = os.path.join(ROOT, 'docs', 'p29_info_screen_resultado.json')
FX_DIR = os.path.join(ROOT, '.cache_fase2', 'M15_500000')
P1_DIR = os.path.join(ROOT, '.cache_p1', 'M15')
CR_DIR = os.path.join(ROOT, '.cache_p15')

FX = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD']
IDX = ['USTEC', 'US30', 'DE40', 'XAUUSD']
CRYPTO = ['BTC', 'ETH', 'SOL']
H_M15 = (4, 16, 96)
H_CR = (1, 3, 21)
DISC = 0.70
WARM = 200
PLACEBO = 200
BOOT = 2000
SEED = 20261104
MIN_N = 200
CRYPTO_COST = 0.0010
GOLD_COMMISSION = 0.07          # USD 7 por lote de 100 oz, ida y vuelta


# ---------------------------------------------------------------- datos

def load_fx(sym):
    r = np.load(os.path.join(FX_DIR, f'{sym}.npy'))
    with open(os.path.join(FX_DIR, f'{sym}.spec.json')) as f:
        sp = json.load(f)
    point = 10.0 ** -sp['digits']
    cost_px = float(np.median(r['spread'])) * point + sp['commission_pips'] * sp['pip']
    return dict(sym=sym, t=r['time'].astype(np.int64), h=r['high'].astype(float), l=r['low'].astype(float),
                c=r['close'].astype(float), cost_px=cost_px, kind='m15')


def load_p1(sym):
    r = np.load(os.path.join(P1_DIR, f'{sym}.npy'))
    with open(os.path.join(P1_DIR, f'{sym}.meta.json')) as f:
        m = json.load(f)
    cost_px = float(np.median(r['spread'])) * m['point'] + (GOLD_COMMISSION if sym == 'XAUUSD' else 0.0)
    return dict(sym=sym, t=r['time'].astype(np.int64), h=r['high'].astype(float), l=r['low'].astype(float),
                c=r['close'].astype(float), cost_px=cost_px, kind='m15')


def load_crypto(sym):
    with open(os.path.join(CR_DIR, f'{sym}.json')) as f:
        j = json.load(f)
    spot = dict((int(t), float(v)) for t, v in j['spot'])
    perp = sorted((int(t), float(v)) for t, v in j['perp'])
    t = np.array([x[0] for x in perp if x[0] in spot], dtype=np.int64)
    c = np.array([dict(perp)[x] for x in t])
    s = np.array([spot[x] for x in t])
    ft = np.array([int(x[0]) for x in j['funding']], dtype=np.int64)
    fr = np.array([float(x[1]) for x in j['funding']])
    return dict(sym=sym, t=t, c=c, spot=s, ft=ft, fr=fr, cost_frac=CRYPTO_COST, kind='crypto')


# ---------------------------------------------------------------- features (todas causales: usan datos <= t)

def fwd_ret(c, h):
    r = np.full(c.size, np.nan)
    r[:-h] = c[h:] / c[:-h] - 1.0
    return r


def f_momentum(c, h):
    f = np.full(c.size, np.nan)
    f[h:] = c[h:] / c[:-h] - 1.0
    return f


def f_rev2s(c, n=20):
    f = np.full(c.size, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(c)])
    cs2 = np.concatenate([[0.0], np.cumsum(c * c)])
    m = (cs[n:] - cs[:-n]) / n
    v = np.maximum((cs2[n:] - cs2[:-n]) / n - m * m, 0.0)
    sd = np.sqrt(v)
    with np.errstate(invalid='ignore', divide='ignore'):
        z = (c[n - 1:] - m) / sd
    f[n - 1:] = -z
    return f


def f_vol_range(hh, ll, c, n=16):
    rng = (hh - ll) / c
    cs = np.concatenate([[0.0], np.cumsum(rng)])
    f = np.full(c.size, np.nan)
    f[n - 1:] = (cs[n:] - cs[:-n]) / n
    return f


def f_vol_ret(c, n=6):
    r = np.concatenate([[np.nan], c[1:] / c[:-1] - 1.0])
    f = np.full(c.size, np.nan)
    for i in range(n, c.size):
        f[i] = np.std(r[i - n + 1:i + 1])
    return f


def f_bucket_mean(keys, r, disc_end):
    """Media del retorno siguiente por categoría (hora/día), estimada SOLO en descubrimiento."""
    f = np.full(r.size, np.nan)
    k_d, r_d = keys[:disc_end], r[:disc_end]
    for k in np.unique(keys):
        sel = (k_d == k) & np.isfinite(r_d)
        if sel.sum() >= 30:
            f[keys == k] = r_d[sel].mean()
    return f


def f_lead(t_target, t_src, c_src, bars=4):
    """Retorno del activo fuente en sus últimas `bars` velas, en la vela con el MISMO timestamp que el destino."""
    src_ret = np.full(c_src.size, np.nan)
    src_ret[bars:] = c_src[bars:] / c_src[:-bars] - 1.0
    pos = np.searchsorted(t_src, t_target)
    pos_c = np.clip(pos, 0, t_src.size - 1)
    ok = (pos < t_src.size) & (t_src[pos_c] == t_target)
    out = np.full(t_target.size, np.nan)
    out[ok] = src_ret[pos_c[ok]]
    return out


def f_funding_7d(t, ft, fr):
    """Funding medio de los 7 días previos (21 cobros de 8 h), signo invertido."""
    cs = np.concatenate([[0.0], np.cumsum(fr)])
    hi = np.searchsorted(ft, t, side='left')
    lo = np.searchsorted(ft, t - 7 * 86400 * 1000, side='left')
    out = -(cs[hi] - cs[lo]) / 21.0
    out[lo == hi] = np.nan
    out[t - 7 * 86400 * 1000 < ft[0]] = np.nan
    return out


# ---------------------------------------------------------------- medición

def ic(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 30 or np.nanstd(a[ok]) == 0:
        return np.nan
    return float(spearmanr(a[ok], b[ok]).correlation)


def evaluate(f, r, cost_frac, disc_end, h, label, risk=False, seed_key=''):
    """f, r alineados por vela; cost_frac escalar o array. Devuelve dict con IC, placebo y prueba económica."""
    n = f.size
    idx = np.arange(WARM, n - h, h)
    idx = idx[np.isfinite(f[idx]) & np.isfinite(r[idx])]
    d_idx, r_idx = idx[idx < disc_end], idx[idx >= disc_end]
    tgt = np.abs(r) if risk else r
    out = dict(label=label, h=int(h), n_disc=int(d_idx.size), n_res=int(r_idx.size),
               ic_disc=ic(f[d_idx], tgt[d_idx]), ic_res=ic(f[r_idx], tgt[r_idx]))
    if r_idx.size < 30:
        out['PASA'] = False
        return out
    rng = np.random.default_rng(zlib.crc32(f'{seed_key}|{label}|{h}'.encode()) ^ SEED)
    fr_, tr_ = f[r_idx], tgt[r_idx]
    plac = [abs(ic(np.roll(fr_, int(rng.integers(fr_.size // 10, 9 * fr_.size // 10))), tr_)) for _ in range(PLACEBO)]
    out['placebo_p95'] = float(np.nanpercentile(plac, 95))
    info_ok = (np.isfinite(out['ic_disc']) and np.isfinite(out['ic_res'])
               and np.sign(out['ic_disc']) == np.sign(out['ic_res'])
               and abs(out['ic_res']) > out['placebo_p95'])
    if risk:
        out['PASA'] = bool(out['ic_res'] > 0 and info_ok)
        return out
    q20, q80 = np.nanpercentile(f[d_idx], [20, 80])
    s = np.where(f[r_idx] >= q80, 1.0, np.where(f[r_idx] <= q20, -1.0, 0.0))
    take = s != 0
    cf = cost_frac[r_idx] if np.ndim(cost_frac) else np.full(r_idx.size, cost_frac)
    gross = s[take] * r[r_idx][take]
    net = gross - cf[take]
    out.update(n_trades=int(take.sum()), gross_bps=float(gross.mean() * 1e4) if take.any() else np.nan,
               cost_bps=float(cf[take].mean() * 1e4) if take.any() else np.nan,
               net_bps=float(net.mean() * 1e4) if take.any() else np.nan)
    if take.sum() >= 30:
        bs = np.array([rng.choice(net, net.size).mean() for _ in range(BOOT)]) * 1e4
        out['net_ci'] = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    else:
        out['net_ci'] = [np.nan, np.nan]
    out['info_ok'] = bool(info_ok)
    out['PASA'] = bool(out['n_res'] >= MIN_N and info_ok and out['net_bps'] > 0 and out['net_ci'][0] > 0)
    return out


# ---------------------------------------------------------------- catálogo

def cells_m15(P, ustec=None):
    c, t = P['c'], P['t']
    disc_end = int(c.size * DISC)
    cost = P['cost_px'] / c
    hour = (t // 3600) % 24
    dow = ((t // 86400) + 4) % 7
    rows = []
    for h in H_M15:
        r = fwd_ret(c, h)
        key = P['sym']
        rows.append(evaluate(f_bucket_mean(hour, r, disc_end), r, cost, disc_end, h, 'F1_hora', seed_key=key))
        rows.append(evaluate(f_bucket_mean(dow, r, disc_end), r, cost, disc_end, h, 'F2_dia', seed_key=key))
        if ustec is not None:
            rows.append(evaluate(f_lead(t, ustec['t'], ustec['c']), r, cost, disc_end, h, 'F3_lead_ustec',
                                 seed_key=key))
        rows.append(evaluate(f_momentum(c, h), r, cost, disc_end, h, 'F4_momentum', seed_key=key))
        rows.append(evaluate(f_rev2s(c), r, cost, disc_end, h, 'F5_rev2s', seed_key=key))
        rows.append(evaluate(f_vol_range(P['h'], P['l'], c), r, cost, disc_end, h, 'R1_vol', risk=True,
                             seed_key=key))
    return rows


def cells_crypto(P):
    c, t = P['c'], P['t']
    disc_end = int(c.size * DISC)
    rows = []
    for h in H_CR:
        r = fwd_ret(c, h)
        key = P['sym']
        rows.append(evaluate(f_funding_7d(t, P['ft'], P['fr']), r, P['cost_frac'], disc_end, h, 'F6_funding_7d',
                             seed_key=key))
        rows.append(evaluate(-(c / P['spot'] - 1.0), r, P['cost_frac'], disc_end, h, 'F7_basis', seed_key=key))
        rows.append(evaluate(f_momentum(c, h), r, P['cost_frac'], disc_end, h, 'F4_momentum', seed_key=key))
        rows.append(evaluate(f_vol_ret(c), r, P['cost_frac'], disc_end, h, 'R1_vol', risk=True, seed_key=key))
    return rows


def fmt(x, d=3):
    return '   n/a' if x is None or (isinstance(x, float) and not np.isfinite(x)) else f'{x:+.{d}f}'


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ustec = load_p1('USTEC')
    results = []
    for s in FX:
        P = load_fx(s)
        for row in cells_m15(P, ustec):
            results.append(dict(row, sym=s))
    for s in IDX:
        P = load_p1(s)
        for row in cells_m15(P, ustec if s == 'XAUUSD' else None):
            results.append(dict(row, sym=s))
    for s in CRYPTO:
        for row in cells_crypto(load_crypto(s)):
            results.append(dict(row, sym=s))

    print('=' * 112)
    print('P29 — screen de información (IC Spearman; neto en bps = puntos básicos por operación, ya restado el costo)')
    print('=' * 112)
    print(f"{'inst':7} {'dato':14} {'h':>3} {'n_res':>6} {'IC desc':>8} {'IC res':>8} {'placebo95':>9} "
          f"{'bruto':>8} {'costo':>7} {'neto':>8} {'CI neto':>18}  veredicto")
    for x in results:
        risk = x['label'].startswith('R')
        ci = x.get('net_ci', [np.nan, np.nan])
        verdict = ('PASA' if x['PASA'] else ('info sí, costo no' if x.get('info_ok') else 'no'))
        if risk:
            verdict = 'PASA (riesgo)' if x['PASA'] else 'no'
        print(f"{x['sym']:7} {x['label']:14} {x['h']:>3} {x['n_res']:>6} {fmt(x['ic_disc'])} {fmt(x['ic_res'])} "
              f"{fmt(x.get('placebo_p95')):>9} {fmt(x.get('gross_bps'), 2):>8} {fmt(x.get('cost_bps'), 2):>7} "
              f"{fmt(x.get('net_bps'), 2):>8} [{fmt(ci[0], 2)}, {fmt(ci[1], 2)}]  {verdict}")
    d = [x for x in results if not x['label'].startswith('R')]
    rk = [x for x in results if x['label'].startswith('R')]
    print('-' * 112)
    print(f"dirección: {len(d)} celdas · con información {sum(1 for x in d if x.get('info_ok'))} · "
          f"PASAN {sum(1 for x in d if x['PASA'])}  |  riesgo: {len(rk)} celdas · PASAN {sum(1 for x in rk if x['PASA'])}")
    cal = [x for x in results if x['sym'] == 'EURUSD' and x['label'] == 'F5_rev2s']
    print('calibración F5 EURUSD (debe tener info y fallar el costo): ' +
          ', '.join(f"h{x['h']} info={'sí' if x.get('info_ok') else 'no'} pasa={'sí' if x['PASA'] else 'no'}"
                    for x in cal))
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(dict(criterio='docs/p29_info_screen_criterio.md', celdas=results), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
