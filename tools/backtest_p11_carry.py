"""
backtest_p11_carry.py — P11: carry con filtro de tendencia, rebalanceo semanal, 20 pares FX.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_fase2/M5_500000` y `docs/p11_policy_rates.csv`.
Criterio declarado ANTES de medir: docs/p11_carry_criterio.md (66101d4). Leer contra eso.

Uso:
    python tools/backtest_p11_carry.py              # 20 pares de Fase 1
    python tools/backtest_p11_carry.py --reserved   # 6 reservados: solo si el principal PASÓ
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.screen_generators import RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p2_donchian import Sim, load_fx  # noqa: E402

RATES_CSV = os.path.join(ROOT, 'docs', 'p11_policy_rates.csv')
CALIB_MONTH = '2026-08'       # mes del snapshot de swap del spec (18-ago-2026)
CARRY_MIN = 0.5
TREND_DAYS = 60
CONTROL_REPS = 1000
SEED = 20261023
OUT = os.path.join(ROOT, 'docs', 'p11_carry_resultado.json')


def load_rates():
    with open(RATES_CSV) as f:
        rows = list(csv.DictReader(f))
    return {r['month']: {k: float(v) for k, v in r.items() if k != 'month'} for r in rows}


def prev_month(ts):
    import datetime as dt
    d = dt.datetime.utcfromtimestamp(int(ts))
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return f'{y:04d}-{m:02d}'


class Pair:
    def __init__(self, sym, rates):
        self.sym, self.base, self.quote = sym, sym[:3], sym[3:]
        self.F = load_fx(sym)
        self.S = Sim(self.F, 'D1', 20, 10)
        self.rates = rates
        S, F = self.S, self.F
        theo = self.theo_long(CALIB_MONTH, float(S.o[-1]))
        self.mk_long = theo - F['swap_long']           # recargo del broker (precio/noche), lado largo
        self.mk_short = -theo - F['swap_short']
        day = S.t // 86400
        tod = S.t % 86400
        week = (day + 3) // 7
        ok = (tod >= 3600) & (tod < 82800)
        idx = np.flatnonzero(ok)
        wk = week[idx]
        first = np.concatenate([[True], wk[1:] != wk[:-1]])
        self.reb = dict(zip(wk[first].tolist(), idx[first].tolist()))   # semana -> índice fino de rebalanceo

    def theo_long(self, month, price):
        r = self.rates[month]
        return (r[self.base] - r[self.quote]) / 100.0 / 360.0 * price

    def carry(self, month):
        r = self.rates[month]
        return r[self.base] - r[self.quote]

    def trend(self, e):
        B = self.S.B
        k = int(np.searchsorted(B['end'], e)) - 1
        if k < TREND_DAYS:
            return None
        return B['c'][k] / B['c'][k - TREND_DAYS] - 1.0

    def weeks(self, rule):
        """Lista de (semana, pos, componentes) para cada semana con rebalanceo y la siguiente."""
        S, F = self.S, self.F
        ws = sorted(self.reb)
        out = []
        prev = 0
        for w0, w1 in zip(ws[:-1], ws[1:]):
            e, x = self.reb[w0], self.reb[w1]
            m = prev_month(S.t[e])
            if m not in self.rates:
                prev = 0
                continue
            tr = self.trend(e)
            if tr is None:
                prev = 0
                continue
            c = self.carry(m)
            pos = rule(c, tr)
            if pos:
                price = (S.o[x] - S.o[e]) * pos
                nts = S.nights(e, x)
                theo = self.theo_long(m, S.o[e])
                swap = nts * ((theo - self.mk_long) if pos > 0 else (-theo - self.mk_short))
                cost = (F['comm'] + 2 * F['spr'][e]) if pos != prev else 0.0
                out.append(dict(w=w0, pos=pos, e=e, price=price / S.o[e] * 100, swap=swap / S.o[e] * 100,
                                cost=cost / S.o[e] * 100, nights=nts, theo=theo, m=m))
            prev = pos
        return out


def rule_main(c, tr):
    if c >= CARRY_MIN and tr > 0:
        return 1
    if c <= -CARRY_MIN and tr < 0:
        return -1
    return 0


def rule_carry(c, tr):
    return 1 if c >= CARRY_MIN else (-1 if c <= -CARRY_MIN else 0)


def rule_trend(c, tr):
    return 1 if tr > 0 else -1


def net(x):
    return x['price'] + x['swap'] - x['cost']


def weekly(rows_by_pair, f=net):
    agg = {}
    for rows in rows_by_pair.values():
        for x in rows:
            agg.setdefault(x['w'], []).append(f(x))
    ws = sorted(agg)
    return np.array(ws), np.array([np.mean(agg[w]) for w in ws])


def control(P, rows_by_pair, rng):
    """Misma exposición (pares/semanas, corridas consecutivas) con dirección al azar por corrida."""
    agg = {}
    for s, rows in rows_by_pair.items():
        p = P[s]
        sign, last_w, last_pos = 1, None, None
        for x in rows:
            new_run = x['cost'] > 0
            if new_run:
                sign = 1 if rng.random() < 0.5 else -1
            d = x['pos'] * sign
            theo = x['theo']
            swap_px = x['nights'] * ((theo - p.mk_long) if d > 0 else (-theo - p.mk_short))
            v = x['price'] * sign + swap_px / p.S.o[x['e']] * 100 - x['cost']
            agg.setdefault(x['w'], []).append(v)
    return float(np.mean([np.mean(v) for v in agg.values()]))


def run(symbols, reserved):
    rates = load_rates()
    P = {s: Pair(s, rates) for s in symbols}
    res = {}
    for name, rule in (('principal', rule_main), ('carry_solo', rule_carry), ('tendencia_sola', rule_trend)):
        rows = {s: P[s].weeks(rule) for s in symbols}
        ws, wr = weekly(rows)
        allx = [x for s in rows for x in rows[s]]
        comp = {k: float(np.mean([x[k] for x in allx])) for k in ('price', 'swap', 'cost')}
        per = {s: dict(n=len(rows[s]), suma=float(sum(net(x) for x in rows[s]))) for s in symbols}
        print(f"\n=== {name}: posiciones-semana {len(allx)}  semanas con algo {ws.size}  media semanal "
              f"{wr.mean():+.4f}%  (por posición: precio {comp['price']:+.4f} + swap {comp['swap']:+.4f} - costo "
              f"{comp['cost']:.4f})")
        if name == 'principal':
            for s in symbols:
                if per[s]['n']:
                    print(f"    {s:7s} n={per[s]['n']:4d}  suma neta {per[s]['suma']:+.2f}%")
            lo, hi, _ = bootstrap_ci(wr)
            half = wr.size // 2
            h1, h2 = float(wr[:half].mean()), float(wr[half:].mean())
            rng = np.random.default_rng(SEED)
            ctrl = np.sort([control(P, rows, rng) for _ in range(CONTROL_REPS)])
            p95 = float(ctrl[int(0.95 * CONTROL_REPS)])
            active = [s for s in symbols if per[s]['n']]
            pos = sum(1 for s in active if per[s]['suma'] > 0)
            if reserved:
                crit = {'oos_media>0': bool(wr.mean() > 0), 'oos_>control_p95': bool(wr.mean() > p95)}
            else:
                crit = {'1_n>=300': len(allx) >= 300,
                        '2_media>0_CI_inf>0': bool(wr.mean() > 0 and lo is not None and lo > 0),
                        '3_dos_mitades>0': h1 > 0 and h2 > 0,
                        '4_>control_p95': bool(wr.mean() > p95),
                        '5_>=12/20_pares>0': pos >= 12}
            ok = all(crit.values())
            ann = wr.mean() * 52
            print(f"\n  >>> media semanal {wr.mean():+.4f}% (~{ann:+.2f}%/año por posición)  CI [{lo:+.4f}, {hi:+.4f}]  "
                  f"mitades {h1:+.4f} / {h2:+.4f}  pares>0 {pos}/{len(active)}  control mediana "
                  f"{ctrl[CONTROL_REPS // 2]:+.4f} p95 {p95:+.4f}")
            for k, v in crit.items():
                print(f"      [{'OK ' if v else 'NO '}] {k}")
            print(f"  >>> {'PASA' if ok else 'NO PASA'}")
            res[name] = dict(n=len(allx), weeks=int(ws.size), mean_week=float(wr.mean()), ci=[lo, hi],
                             halves=[h1, h2], control_p95=p95, pos=pos, n_active=len(active), comp=comp,
                             por_par=per, criterios=crit, PASA=ok)
        else:
            res[name] = dict(n=len(allx), mean_week=float(wr.mean()), comp=comp)
    mk = {s: dict(mk_long_pips=P[s].mk_long / P[s].F['pip'], mk_short_pips=P[s].mk_short / P[s].F['pip'])
          for s in symbols}
    res['recargo_broker_pips_noche'] = mk
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('principal', {}).get('PASA'):
            sys.exit('El principal NO pasó (o no se corrió): los reservados no se miran.')
        syms, out = RESERVADOS, OUT.replace('.json', '_reservados.json')
    else:
        syms, out = SYMBOLS_FASE1, OUT
    res = run(syms, a.reserved)
    res['criterio'] = 'docs/p11_carry_criterio.md (66101d4)'
    with open(out, 'w') as f:
        json.dump(res, f, indent=1, default=float)
    print(f'\n-> {os.path.relpath(out, ROOT)}')


if __name__ == '__main__':
    main()
