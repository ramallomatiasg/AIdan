"""
backtest_p3_rango_asiatico.py — P3: rango asiático → ruptura de Londres.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000` (FX).
Criterio declarado ANTES de medir: docs/p3_rango_asiatico_criterio.md (ea1e715). Leer contra eso.

Reglas (congeladas en el criterio): rango = máx/mín de las M5 con hora Londres en [00:00, 07:00)
(≥70/84 velas); stops OCO en los extremos activos [07:00, 12:00); stop al otro extremo (1R = ancho W);
objetivo 1·W (principal) / 2·W (descriptivo); salida a la apertura de la 1ra vela ≥ 16:00 Londres.
Vela que cruza los dos niveles = −1R − costo. Stop y objetivo en la misma vela = stop.
Hora server = NY + 7h (verificado en el cache: la semana va de lun 00:00 a vie 23:55 server).

Uso:
    python tools/backtest_p3_rango_asiatico.py              # 20 pares de Fase 1
    python tools/backtest_p3_rango_asiatico.py --reserved   # 6 reservados: solo si el principal PASÓ
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

FX_CACHE = os.path.join(ROOT, '.cache_fase2', 'M5_500000')
NY = ZoneInfo('America/New_York')
LON = ZoneInfo('Europe/London')
RANGE_END, WIN_START, WIN_END, EXIT_MIN = 7 * 60, 7 * 60, 12 * 60, 16 * 60
MIN_RANGE_BARS = 70
TP_MULTS = (1.0, 2.0)
MAIN_TP = 1.0
CONTROL_REPS = 200
SEED = 20261017
OUT = os.path.join(ROOT, 'docs', 'p3_rango_asiatico_resultado.json')


def load_fx(sym):
    r = np.load(os.path.join(FX_CACHE, f'{sym}.npy'))
    with open(os.path.join(FX_CACHE, f'{sym}.spec.json')) as f:
        spec = json.load(f)
    pip = spec['pip']
    point = 10.0 ** -spec['digits']
    spr = np.maximum(r['spread'].astype(np.float64) * point, 0.1 * pip)
    return dict(sym=sym, pip=pip, r=r, spr=spr, comm=spec['commission_pips'] * pip)


def _offsets(days, tz, base_s):
    """offset (s) de tz al mediodía de cada día (los cambios de DST caen en fin de semana)."""
    out = {}
    for dd in days:
        t = datetime.fromtimestamp(int(dd) * 86400 + 43200 - base_s, tz=timezone.utc)
        out[int(dd)] = int(t.astimezone(tz).utcoffset().total_seconds())
    return out


def london_clock(t_server):
    """hora server -> (día Londres, minuto Londres)."""
    sday = t_server // 86400
    ny = _offsets(np.unique(sday), NY, 7 * 3600)
    utc = t_server - (7 * 3600 + np.vectorize(ny.get)(sday))
    uday = utc // 86400
    lo = _offsets(np.unique(uday), LON, 0)
    lon = utc + np.vectorize(lo.get)(uday)
    return lon // 86400, (lon % 86400) // 60


class Pair:
    def __init__(self, F):
        r = F['r']
        self.F = F
        self.t = r['time'].astype(np.int64)
        self.o = r['open'].astype(np.float64)
        self.h = r['high'].astype(np.float64)
        self.l = r['low'].astype(np.float64)
        day, mins = london_clock(self.t)
        self.days = []                    # (rng_hi, rng_lo, w0, w1, x) por día válido
        bounds = np.flatnonzero(np.diff(day)) + 1
        starts = np.concatenate([[0], bounds])
        ends = np.concatenate([bounds, [day.size]])
        for s, e in zip(starts, ends):
            if (int(day[s]) + 3) % 7 >= 5:           # 1970-01-01 = jueves ⇒ (d+3)%7: lun=0
                continue
            m = mins[s:e]
            a = np.flatnonzero(m < RANGE_END)
            if a.size < MIN_RANGE_BARS:
                continue
            w = np.flatnonzero((m >= WIN_START) & (m < WIN_END))
            x = np.flatnonzero(m >= EXIT_MIN)
            if w.size == 0 or x.size == 0:
                continue
            hi, lo = self.h[s + a].max(), self.l[s + a].min()
            if hi <= lo:
                continue
            self.days.append((hi, lo, s + w[0], s + w[-1] + 1, s + x[0]))

    def _manage(self, e, entry, d, W, x, tpm):
        stop, tp = entry - d * W, entry + d * W * tpm
        hs, ls = self.h[e:x], self.l[e:x]
        if d > 0:
            sh, th = np.flatnonzero(ls <= stop), np.flatnonzero(hs >= tp)
        else:
            sh, th = np.flatnonzero(hs >= stop), np.flatnonzero(ls <= tp)
        js = sh[0] if sh.size else 10 ** 9
        jt = th[0] if th.size else 10 ** 9
        if js <= jt and sh.size:
            j = e + js
            px = min(self.o[j], stop) if d > 0 else max(self.o[j], stop)
            if j == e:
                px = stop
            how = 'stop'
        elif th.size:
            j, px, how = e + jt, tp, 'tp'
        else:
            j, px, how = x, self.o[x], 'tiempo'
        return j, px, how

    def trade_day(self, k, tpm):
        hi, lo, w0, w1, x = self.days[k]
        W = hi - lo
        F = self.F
        up = np.flatnonzero(self.h[w0:w1] >= hi)
        dn = np.flatnonzero(self.l[w0:w1] <= lo)
        iu = up[0] if up.size else 10 ** 9
        idn = dn[0] if dn.size else 10 ** 9
        if not up.size and not dn.size:
            return None
        if iu == idn:
            e = w0 + iu
            cost = F['comm'] + 2 * F['spr'][e]
            return dict(k=k, t=int(self.t[e]), d=0, W=W, gross=-W, cost=cost, net=-W - cost, how='ambiguo')
        if iu < idn:
            e, d = w0 + iu, 1
            entry = max(self.o[e], hi)
        else:
            e, d = w0 + idn, -1
            entry = min(self.o[e], lo)
        j, px, how = self._manage(e, entry, d, W, x, tpm)
        gross = d * (px - entry)
        cost = F['comm'] + F['spr'][e] + F['spr'][j]
        return dict(k=k, t=int(self.t[e]), d=d, W=W, gross=gross, cost=cost, net=gross - cost, how=how)

    def run(self, tpm):
        return [tr for tr in (self.trade_day(k, tpm) for k in range(len(self.days))) if tr is not None]

    def random_trades(self, ks, rng, tpm):
        res = []
        for k in ks:
            hi, lo, w0, w1, x = self.days[k]
            W = hi - lo
            e = int(rng.integers(w0, w1))
            d = 1 if rng.random() < 0.5 else -1
            entry = self.o[e]
            j, px, _ = self._manage(e, entry, d, W, x, tpm)
            net = d * (px - entry) - (self.F['comm'] + self.F['spr'][e] + self.F['spr'][j])
            res.append(net / W)
        return res


def summarize(trades, pip):
    if not trades:
        return dict(n=0)
    r = np.array([x['net'] / x['W'] for x in trades])
    return dict(n=int(r.size), net_R=float(r.mean()),
                gross_R=float(np.mean([x['gross'] / x['W'] for x in trades])),
                cost_R=float(np.mean([x['cost'] / x['W'] for x in trades])),
                net_pips=float(np.mean([x['net'] for x in trades]) / pip),
                W_pips_med=float(np.median([x['W'] for x in trades]) / pip),
                win=float((r > 0).mean()),
                how={h: float(np.mean([x['how'] == h for x in trades]))
                     for h in ('tp', 'stop', 'tiempo', 'ambiguo')})


def evaluate(per_pair, pairs):
    allt = sorted([x for s in per_pair for x in per_pair[s]], key=lambda x: x['t'])
    r = np.array([x['net'] / x['W'] for x in allt])
    lo, hi, _ = bootstrap_ci(r)
    half = r.size // 2
    h1, h2 = float(r[:half].mean()), float(r[half:].mean())
    pos = sum(1 for s in per_pair if per_pair[s] and np.mean([x['net'] / x['W'] for x in per_pair[s]]) > 0)
    rng = np.random.default_rng(SEED)
    ctrl = []
    for _ in range(CONTROL_REPS):
        v = []
        for s, P in pairs.items():
            v.extend(P.random_trades([x['k'] for x in per_pair[s]], rng, MAIN_TP))
        ctrl.append(float(np.mean(v)))
    ctrl = np.array(ctrl)
    p95 = float(np.percentile(ctrl, 95))
    crit = {
        '1_n>=300': r.size >= 300,
        '2_media>0_CI_inf>0': bool(r.mean() > 0 and lo is not None and lo > 0),
        '3_dos_mitades>0': bool(h1 > 0 and h2 > 0),
        '4_>control_p95': bool(r.mean() > p95),
        '5_>=12/20_pares>0': pos >= 12,
    }
    return dict(n=int(r.size), mean_R=float(r.mean()), ci=[lo, hi], halves=[h1, h2], pos_pairs=pos,
                n_pairs=len(per_pair), control_median=float(np.median(ctrl)), control_p95=p95,
                criterios=crit, PASA=all(crit.values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('principal', {}).get('PASA'):
            sys.exit('El principal NO pasó (o no se corrió): los reservados no se miran.')
        symbols = RESERVADOS
    else:
        symbols = SYMBOLS_FASE1
    pairs = {s: Pair(load_fx(s)) for s in symbols}
    result = {}
    for tpm in TP_MULTS:
        per_pair = {s: pairs[s].run(tpm) for s in symbols}
        allt = [x for s in per_pair for x in per_pair[s]]
        r = np.array([x['net'] / x['W'] for x in allt])
        g = np.mean([x['gross'] / x['W'] for x in allt])
        c = np.mean([x['cost'] / x['W'] for x in allt])
        ndays = sum(len(pairs[s].days) for s in symbols)
        print(f'\n=== TP {tpm:g}·W  pool n={r.size} (días válidos {ndays}, disparó {r.size / ndays:.0%})  '
              f'neto {r.mean():+.3f}R  (bruto {g:+.3f} - costo {c:.3f})  gan {(r > 0).mean():.0%}')
        pp = {}
        for s in symbols:
            sm = summarize(per_pair[s], pairs[s].F['pip'])
            pp[s] = sm
            if sm['n']:
                print(f'    {s:7s} n={sm["n"]:4d}  neto {sm["net_R"]:+.3f}R ({sm["net_pips"]:+.2f}p)  '
                      f'bruto {sm["gross_R"]:+.3f}  costo {sm["cost_R"]:.3f}  W med {sm["W_pips_med"]:.1f}p  '
                      f'tp {sm["how"]["tp"]:.0%} stop {sm["how"]["stop"]:.0%} '
                      f'tiempo {sm["how"]["tiempo"]:.0%} amb {sm["how"]["ambiguo"]:.0%}')
        # terciles de ancho relativos al par (descriptivo)
        terc = {}
        for name, qlo, qhi in (('angosto', 0, 1 / 3), ('medio', 1 / 3, 2 / 3), ('ancho', 2 / 3, 1.01)):
            v = []
            for s in symbols:
                Ws = np.array([x['W'] for x in per_pair[s]])
                if Ws.size < 3:
                    continue
                a_, b_ = np.quantile(Ws, qlo), np.quantile(Ws, min(qhi, 1.0))
                v += [x['net'] / x['W'] for x in per_pair[s] if a_ <= x['W'] <= b_]
            terc[name] = dict(n=len(v), net_R=float(np.mean(v)) if v else None)
        print('    terciles de ancho: ' + ' · '.join(f'{k} n={v["n"]} {v["net_R"]:+.3f}R' for k, v in terc.items()))
        entry = dict(pares=pp, terciles=terc)
        if tpm == MAIN_TP:
            ev = evaluate(per_pair, pairs)
            entry['gate'] = ev
            result['principal'] = ev
            print(f'\n  >>> PRINCIPAL TP 1·W: n={ev["n"]} media {ev["mean_R"]:+.4f}R  '
                  f'CI [{ev["ci"][0]:+.4f}, {ev["ci"][1]:+.4f}]  mitades {ev["halves"][0]:+.3f} / '
                  f'{ev["halves"][1]:+.3f}  pares>0 {ev["pos_pairs"]}/{ev["n_pairs"]}  '
                  f'control mediana {ev["control_median"]:+.3f} p95 {ev["control_p95"]:+.3f}')
            for k, v in ev['criterios'].items():
                print(f'      [{"OK " if v else "NO "}] {k}')
            print(f'  >>> {"PASA" if ev["PASA"] else "NO PASA"}')
        result[f'tp_{tpm:g}W'] = entry
    out = OUT if not a.reserved else OUT.replace('.json', '_reservados.json')
    with open(out, 'w') as f:
        json.dump(result, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
