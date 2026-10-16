"""
backtest_p2_donchian.py — P2: trend following clásico (canal Donchian / turtle) en D1 y H4.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000` (FX) y `.cache_p1/M15` (oro/índices).
Criterio declarado ANTES de medir: docs/p2_donchian_criterio.md (192e3c2). Leer contra eso.

Reglas (congeladas en el criterio): señal al cierre de la barra D1/H4 (cierre fuera del canal de N
barras anteriores), ejecución en la 1ra vela fina siguiente fuera de [23:00, 01:00) server, stop
inicial 2·ATR(20) chequeado vela fina por vela fina (gap ⇒ apertura), salida por canal de M barras
con la misma regla de ejecución. Una posición por instrumento. Neto en R (1R = stop inicial).

Uso:
    python tools/backtest_p2_donchian.py              # 20 pares + oro/índices (descriptivo)
    python tools/backtest_p2_donchian.py --reserved   # 6 reservados: solo si el principal PASÓ
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

FX_CACHE = os.path.join(ROOT, '.cache_fase2', 'M5_500000')
P1_CACHE = os.path.join(ROOT, '.cache_p1', 'M15')
OTHERS = ['XAUUSD', 'USTEC', 'US30', 'DE40']
OTHER_COMM = {'XAUUSD': 0.07}          # $7/lote RT, lote = 100 oz ⇒ $0,07 de precio. Índices: 0
SYSTEMS = [('D1', 20, 10), ('D1', 55, 20), ('H4', 20, 10), ('H4', 55, 20)]
MAIN = ('D1', 20, 10)
ATR_N = 20
STOP_ATR = 2.0
CONTROL_REPS = 200
SEED = 20261016
OUT = os.path.join(ROOT, 'docs', 'p2_donchian_resultado.json')


# ── datos ────────────────────────────────────────────────────────────────────

def load_fx(sym):
    r = np.load(os.path.join(FX_CACHE, f'{sym}.npy'))
    with open(os.path.join(FX_CACHE, f'{sym}.spec.json')) as f:
        spec = json.load(f)
    pip = spec['pip']
    point = 10.0 ** -spec['digits']
    spr = np.maximum(r['spread'].astype(np.float64) * point, 0.1 * pip)   # piso 0,1p (TCA)
    return dict(sym=sym, kind='fx', fine_sec=300, pip=pip, r=r, spr=spr,
                comm=spec['commission_pips'] * pip,
                swap_long=spec['swap_long_pips'] * pip, swap_short=spec['swap_short_pips'] * pip)


def load_other(sym):
    r = np.load(os.path.join(P1_CACHE, f'{sym}.npy'))
    with open(os.path.join(P1_CACHE, f'{sym}.meta.json')) as f:
        meta = json.load(f)
    point = meta['point']
    spr = r['spread'].astype(np.float64) * point
    return dict(sym=sym, kind='other', fine_sec=900, pip=point, r=r, spr=spr,
                comm=OTHER_COMM.get(sym, 0.0), swap_long=None, swap_short=None)


def resample(F, tf):
    """Barras de señal desde las velas finas. Devuelve dict con o/h/l/c y [start,end] fino."""
    r = F['r']
    t = r['time'].astype(np.int64)
    sec = 86400 if tf == 'D1' else 14400
    g = t // sec
    cut = np.flatnonzero(np.diff(g)) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut - 1, [t.size - 1]])
    cnt = ends - starts + 1
    keep = cnt >= 0.5 * (sec // F['fine_sec'])
    starts, ends = starts[keep], ends[keep]
    h = np.maximum.reduceat(r['high'].astype(np.float64), np.concatenate([[0], cut]))[keep]
    l = np.minimum.reduceat(r['low'].astype(np.float64), np.concatenate([[0], cut]))[keep]
    o = r['open'].astype(np.float64)[starts]
    c = r['close'].astype(np.float64)[ends]
    return dict(o=o, h=h, l=l, c=c, start=starts, end=ends)


def rolling_ext(x, n, fn):
    """fn de los n valores ANTERIORES a cada índice (excluye el actual). NaN en los primeros n."""
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full(x.size, np.nan)
    if x.size > n:
        w = sliding_window_view(x[:-1], n)
        out[n:] = fn(w, axis=1)
    return out


def atr(B, n=ATR_N):
    h, l, c = B['h'], B['l'], B['c']
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    out = np.full(tr.size, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(tr)])
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


# ── simulación ───────────────────────────────────────────────────────────────

class Sim:
    def __init__(self, F, tf, N, M):
        r = F['r']
        self.F = F
        self.t = r['time'].astype(np.int64)
        self.o = r['open'].astype(np.float64)
        self.h = r['high'].astype(np.float64)
        self.l = r['low'].astype(np.float64)
        self.n = self.t.size
        tod = self.t % 86400
        ok = ~((tod >= 82800) | (tod < 3600))
        self.ok_idx = np.flatnonzero(ok)
        B = resample(F, tf)
        self.B = B
        self.atr = atr(B)
        hh, ll = rolling_ext(B['h'], N, np.max), rolling_ext(B['l'], N, np.min)
        xl, xh = rolling_ext(B['l'], M, np.min), rolling_ext(B['h'], M, np.max)
        with np.errstate(invalid='ignore'):
            sig = np.where(B['c'] > hh, 1, np.where(B['c'] < ll, -1, 0))
        valid = ~np.isnan(hh) & ~np.isnan(self.atr) & (self.atr > 0)
        self.sig = np.where(valid, sig, 0)
        self.valid_bars = np.flatnonzero(valid)
        with np.errstate(invalid='ignore'):
            self.exitL = np.flatnonzero(B['c'] < xl)    # bar donde un LARGO sale por canal
            self.exitS = np.flatnonzero(B['c'] > xh)
        # índice fino de ejecución para cada barra de señal
        e = B['end'] + 1
        pos = np.searchsorted(self.ok_idx, e)
        self.exec_idx = np.where(pos < self.ok_idx.size, self.ok_idx[np.minimum(pos, self.ok_idx.size - 1)],
                                 self.n)
        self.exec_idx = np.where(e >= self.n, self.n, self.exec_idx)
        # swap: noches acumuladas por día del server (miércoles ×3, sáb/dom 0)
        day = self.t // 86400
        self.d0 = int(day.min())
        nd = int(day.max()) - self.d0 + 2
        wd = (np.arange(nd) + self.d0 + 3) % 7
        w = np.where(wd == 2, 3.0, np.where(wd >= 5, 0.0, 1.0))
        self.cumw = np.concatenate([[0.0], np.cumsum(w)])

    def nights(self, i, j):
        return self.cumw[self.t[j] // 86400 - self.d0] - self.cumw[self.t[i] // 86400 - self.d0]

    def trade(self, k, d):
        """Simula una entrada en la barra de señal k, dirección d. None si no cierra dentro de la data."""
        F, B = self.F, self.B
        e = self.exec_idx[k]
        if e >= self.n:
            return None
        entry = self.o[e]
        R = STOP_ATR * self.atr[k]
        stop = entry - d * R
        ke = np.searchsorted(B['end'], e)               # barra que contiene la entrada
        ex = self.exitL if d > 0 else self.exitS
        p = np.searchsorted(ex, ke)
        xc = self.exec_idx[ex[p]] if p < ex.size else self.n
        seg_end = min(xc, self.n)
        if d > 0:
            hit = np.flatnonzero(self.l[e:seg_end] <= stop)
        else:
            hit = np.flatnonzero(self.h[e:seg_end] >= stop)
        if hit.size:
            j = e + hit[0]
            px = min(self.o[j], stop) if d > 0 else max(self.o[j], stop)
            how = 'stop'
        else:
            if xc >= self.n:
                return None
            j, px, how = xc, self.o[xc], 'canal'
        gross = d * (px - entry)
        cost = F['comm'] + F['spr'][e] + F['spr'][j]
        nts = self.nights(e, j)
        swap = 0.0
        if F['swap_long'] is not None:
            swap = nts * (F['swap_long'] if d > 0 else F['swap_short'])
        net = gross - cost + swap
        return dict(e=int(e), j=int(j), t=int(self.t[e]), d=int(d), R=R, gross=gross, cost=cost,
                    swap=swap, nights=nts, net=net, how=how)

    def run_system(self):
        out, k = [], 0
        sig_bars = np.flatnonzero(self.sig != 0)
        p = 0
        while p < sig_bars.size:
            k = sig_bars[p]
            tr = self.trade(k, self.sig[k])
            if tr is None:
                break
            out.append(tr)
            # próxima entrada: barra cuya ejecución sea posterior a la salida
            p = np.searchsorted(sig_bars, np.searchsorted(self.exec_idx, tr['j'] + 1))
        return out

    def run_random(self, count, rng):
        if self.valid_bars.size == 0 or count == 0:
            return []
        ks = rng.choice(self.valid_bars, size=count, replace=True)
        ds = rng.choice([-1, 1], size=count)
        res = []
        for k, d in zip(ks, ds):
            tr = self.trade(int(k), int(d))
            if tr is not None:
                res.append(tr['net'] / tr['R'])
        return res


# ── reporte ──────────────────────────────────────────────────────────────────

def summarize(trades):
    if not trades:
        return dict(n=0)
    r = np.array([x['net'] / x['R'] for x in trades])
    g = np.array([x['gross'] / x['R'] for x in trades])
    c = np.array([x['cost'] / x['R'] for x in trades])
    s = np.array([x['swap'] / x['R'] for x in trades])
    return dict(n=int(r.size), net_R=float(r.mean()), gross_R=float(g.mean()), cost_R=float(c.mean()),
                swap_R=float(s.mean()), win=float((r > 0).mean()),
                stop_pct=float(np.mean([x['how'] == 'stop' for x in trades])),
                nights_med=float(np.median([x['nights'] for x in trades])))


def evaluate_main(per_pair, sims):
    allt = [x for s in per_pair for x in per_pair[s]]
    allt.sort(key=lambda x: x['t'])
    r = np.array([x['net'] / x['R'] for x in allt])
    lo, hi, _ = bootstrap_ci(r)
    half = r.size // 2
    h1, h2 = float(r[:half].mean()), float(r[half:].mean())
    pos_pairs = sum(1 for s in per_pair if per_pair[s] and
                    np.mean([x['net'] / x['R'] for x in per_pair[s]]) > 0)
    rng = np.random.default_rng(SEED)
    ctrl = []
    for _ in range(CONTROL_REPS):
        v = []
        for s, sim in sims.items():
            v.extend(sim.run_random(len(per_pair[s]), rng))
        ctrl.append(float(np.mean(v)) if v else np.nan)
    ctrl = np.array(ctrl)
    p95 = float(np.nanpercentile(ctrl, 95))
    crit = {
        '1_n>=300': r.size >= 300,
        '2_media>0_CI_inf>0': bool(r.mean() > 0 and lo is not None and lo > 0),
        '3_dos_mitades>0': bool(h1 > 0 and h2 > 0),
        '4_>control_p95': bool(r.mean() > p95),
        '5_>=12/20_pares>0': pos_pairs >= 12,
    }
    return dict(n=int(r.size), mean_R=float(r.mean()), ci=[lo, hi], halves=[h1, h2],
                pos_pairs=pos_pairs, n_pairs=len(per_pair), control_median=float(np.nanmedian(ctrl)),
                control_p95=p95, criterios=crit, PASA=all(crit.values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    result = {}
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('principal', {}).get('PASA'):
            sys.exit('El principal NO pasó (o no se corrió): los reservados no se miran.')
        symbols = RESERVADOS
    else:
        symbols = SYMBOLS_FASE1
    fx = {s: load_fx(s) for s in symbols}

    # ── principal + secundarios FX ──
    for tf, N, M in SYSTEMS:
        key = f'{tf}_{N}_{M}'
        sims = {s: Sim(fx[s], tf, N, M) for s in symbols}
        per_pair = {s: sims[s].run_system() for s in symbols}
        allt = [x for s in per_pair for x in per_pair[s]]
        summ = summarize(allt)
        pairs = {s: summarize(per_pair[s]) for s in symbols}
        print(f'\n=== FX {key}  pool: n={summ["n"]}  neto {summ["net_R"]:+.3f}R  '
              f'(bruto {summ["gross_R"]:+.3f} - costo {summ["cost_R"]:.3f} + swap {summ["swap_R"]:+.3f})  '
              f'gan {summ["win"]:.0%}  stop {summ["stop_pct"]:.0%}  noches med {summ["nights_med"]:.0f}')
        for s in symbols:
            p = pairs[s]
            if p['n']:
                print(f'    {s:7s} n={p["n"]:4d}  neto {p["net_R"]:+.3f}R  bruto {p["gross_R"]:+.3f}  '
                      f'swap {p["swap_R"]:+.3f}')
        entry = dict(pool=summ, pares=pairs)
        if (tf, N, M) == MAIN:
            ev = evaluate_main(per_pair, sims)
            entry['gate'] = ev
            result['principal'] = ev
            print(f'\n  >>> PRINCIPAL {key}: n={ev["n"]} media {ev["mean_R"]:+.4f}R  '
                  f'CI [{ev["ci"][0]:+.4f}, {ev["ci"][1]:+.4f}]  mitades {ev["halves"][0]:+.3f} / '
                  f'{ev["halves"][1]:+.3f}  pares>0 {ev["pos_pairs"]}/{ev["n_pairs"]}  '
                  f'control mediana {ev["control_median"]:+.3f} p95 {ev["control_p95"]:+.3f}')
            for k, v in ev['criterios'].items():
                print(f'      [{"OK " if v else "NO "}] {k}')
            print(f'  >>> {"PASA" if ev["PASA"] else "NO PASA"}')
        result[f'fx_{key}'] = entry

    # ── oro / índices (descriptivo, sin swap) ──
    if not a.reserved:
        print('\n=== ORO / ÍNDICES (descriptivo, SIN swap: el cache no lo trae)')
        for s in OTHERS:
            F = load_other(s)
            for tf, N, M in SYSTEMS:
                tr = Sim(F, tf, N, M).run_system()
                sm = summarize(tr)
                if not sm['n']:
                    continue
                net_px = sum(x['net'] for x in tr)
                nts = sum(x['nights'] for x in tr)
                be = net_px / nts if nts else float('nan')
                sm['swap_breakeven_px_noche'] = be
                print(f'    {s:7s} {tf}_{N}_{M:<3d} n={sm["n"]:4d}  neto {sm["net_R"]:+.3f}R  '
                      f'bruto {sm["gross_R"]:+.3f}  costo {sm["cost_R"]:.3f}  '
                      f'swap que lo lleva a 0: {be:+.3f}/noche (precio)')
                result[f'{s}_{tf}_{N}_{M}'] = sm

    out = OUT if not a.reserved else OUT.replace('.json', '_reservados.json')
    with open(out, 'w') as f:
        json.dump(result, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
