"""
backtest_fase5_fin_de_mes.py — FASE 5: canal de cobertura de fin de mes (Melvin & Prins 2015).

READ-ONLY. FX del cache `.cache_fase2/M5_500000`; índices del cache `.cache_fase2/IDX_D1`
(bajados de MT5 una vez). No toca la DB de producción.
Criterio declarado ANTES de medir: docs/fase5_fin_de_mes_criterio.md (e190950).

    python tools/backtest_fase5_fin_de_mes.py
    python tools/backtest_fase5_fin_de_mes.py --oos     # USDCAD/CA60 y USDCHF/SWI20, solo si pasó
"""
import argparse
import json
import os
import sys
import zlib
from datetime import datetime, timezone, date

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase4_planes import load_pair, uk_bst  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

IDX = os.path.join(ROOT, '.cache_fase2', 'IDX_D1')
PAIRS = [('EURUSD', 'STOXX50'), ('GBPUSD', 'UK100'), ('USDJPY', 'JP225'), ('AUDUSD', 'AUS200')]
PAIRS_OOS = [('USDCAD', 'CA60'), ('USDCHF', 'SWI20')]
US = 'US500'
REPS = 200
OUT = os.path.join(ROOT, 'docs', 'fase5_fin_de_mes_resultado.json')
OUT_OOS = os.path.join(ROOT, 'docs', 'fase5_fin_de_mes_oos.json')


def load_index(name):
    r = np.load(os.path.join(IDX, f'{name}.npy'))
    d = np.array([datetime.fromtimestamp(int(x), timezone.utc).date() for x in r['time']])
    return d, r['close'].astype(np.float64)


def close_before(dates, closes, day):
    """Último cierre con fecha < day (o None)."""
    k = np.searchsorted(dates, day) - 1
    return closes[k] if k >= 0 else None


def london_minutes(P):
    u = P['utc']
    days = np.unique(u // 86400)
    off = {int(d): (3600 if uk_bst(datetime.fromtimestamp(int(d) * 86400, timezone.utc)
                                   .replace(tzinfo=None, hour=12)) else 0) for d in days}
    lon = u + np.array([off[int(d)] for d in u // 86400])
    return lon // 86400, (lon % 86400) // 60


def windows_by_date(P, start_min, end_min):
    """{fecha Londres: (i_in, i_out)} solo con la ventana COMPLETA en velas M5."""
    ld, lm = london_minutes(P)
    need = (end_min - start_min) // 5
    sel = np.where((lm >= start_min) & (lm < end_min))[0]
    out = {}
    if sel.size == 0:
        return out
    dd = ld[sel]
    cuts = np.r_[0, np.where(np.diff(dd) != 0)[0] + 1, sel.size]
    for a, b in zip(cuts[:-1], cuts[1:]):
        idx = sel[a:b]
        if idx.size == need and lm[idx[0]] == start_min:
            out[date.fromordinal(date(1970, 1, 1).toordinal() + int(dd[a]))] = (int(idx[0]), int(idx[-1]))
    return out


def month_ends(P):
    """Último día hábil (fecha Londres) de cada mes con velas FX."""
    ld, _ = london_minutes(P)
    days = sorted({date.fromordinal(date(1970, 1, 1).toordinal() + int(x)) for x in np.unique(ld)})
    last = {}
    for d in days:
        if d.weekday() < 5:
            last[(d.year, d.month)] = d
    full = sorted(last.values())
    return full[1:-1]          # descarta el 1er y el último mes (pueden estar incompletos)


def run(pairs):
    us_d, us_c = load_index(US)
    rows, ctrl_sum, ctrl_n, sec = [], np.zeros(REPS), 0, []
    for sym, idx_name in pairs:
        P = load_pair(sym)
        ix_d, ix_c = load_index(idx_name)
        base_usd = sym.startswith('USD')          # USDJPY: la moneda extranjera es la cotizada
        win = windows_by_date(P, 15 * 60, 16 * 60)
        win8 = windows_by_date(P, 8 * 60, 16 * 60)
        ends = month_ends(P)
        trades = []
        for L in ends:
            if L not in win:
                continue
            first = date(L.year, L.month, 1)
            e0, e1 = close_before(ix_d, ix_c, first), close_before(ix_d, ix_c, L)
            u0, u1 = close_before(us_d, us_c, first), close_before(us_d, us_c, L)
            if None in (e0, e1, u0, u1):
                continue
            dif = (e1 / e0 - 1) - (u1 / u0 - 1)
            if dif == 0:
                continue
            sell_foreign = dif > 0
            # dirección sobre el PAR: vender moneda extranjera = vender XXXUSD / comprar USDXXX
            dirn = (1 if base_usd else -1) if sell_foreign else (-1 if base_usd else 1)
            i_in, i_out = win[L]
            g = dirn * (P['c'][i_out] - P['o'][i_in]) / P['pip']
            net = g - P['spec']['commission_pips'] - P['spr'][i_in]
            fx_foreign = (-1 if base_usd else 1) * (P['c'][i_out] - P['o'][i_in]) / P['pip']
            trades.append({'sym': sym, 'date': str(L), 'dif': dif, 'dirn': dirn, 'bruto': g, 'net': net,
                           't': int(P['t'][i_in]), 'fx_foreign': fx_foreign})
            if L in win8:
                a, b = win8[L]
                g8 = dirn * (P['c'][b] - P['o'][a]) / P['pip']
                sec.append(g8 - P['spec']['commission_pips'] - P['spr'][a])
        rows.extend(trades)
        # control: días al azar que NO son fin de mes, misma ventana, mismo n y ratio
        if trades:
            others = [d for d in win if d not in set(ends)]
            rng = np.random.default_rng(zlib.crc32(f'{sym}|f5'.encode()))
            p_long = np.mean([t['dirn'] > 0 for t in trades])
            for r_ in range(REPS):
                ds = rng.choice(len(others), len(trades))
                tot = 0.0
                for k in ds:
                    i_in, i_out = win[others[k]]
                    dn = 1 if rng.random() < p_long else -1
                    tot += dn * (P['c'][i_out] - P['o'][i_in]) / P['pip'] - P['spec']['commission_pips'] - P['spr'][i_in]
                ctrl_sum[r_] += tot
            ctrl_n += len(trades)
    return rows, np.sort(ctrl_sum / max(ctrl_n, 1)), sec


def evaluate(rows, ctrl, sec, oos):
    net = np.array([r['net'] for r in rows])
    tt = np.array([r['t'] for r in rows])
    mid = tt.min() + (tt.max() - tt.min()) / 2
    lo, hi, _ = bootstrap_ci(net)
    m1, m2 = float(net[tt < mid].mean()), float(net[tt >= mid].mean())
    by = {}
    for r in rows:
        by.setdefault(r['sym'], []).append(r['net'])
    pos = sum(1 for v in by.values() if np.mean(v) > 0)
    mean = float(net.mean())
    p95 = float(ctrl[int(0.95 * REPS)])
    difs = np.array([r['dif'] for r in rows]); fxf = np.array([r['fx_foreign'] for r in rows])
    c = {'c1_neto_pos': mean > 0, 'c2_ci_lo_pos': lo is not None and lo > 0,
         'c3_dos_mitades': m1 > 0 and m2 > 0, 'c4_supera_p95': mean > p95,
         'c5_3de4_pares': pos >= 3}
    ver = ('PASA OOS' if (mean > 0 and mean > p95) else 'NO PASA OOS') if oos else \
          ('PASA' if all(c.values()) else 'NO PASA')
    return {'n': int(net.size), 'neto': round(mean, 3), 'bruto': round(float(np.mean([r['bruto'] for r in rows])), 3),
            'ci95': [lo, hi], 'mitad_1': round(m1, 3), 'mitad_2': round(m2, 3),
            'control_mediana': round(float(ctrl[REPS // 2]), 3), 'control_p95': round(p95, 3),
            'por_par': {k: {'n': len(v), 'neto': round(float(np.mean(v)), 3)} for k, v in by.items()},
            'condiciones': c, 'veredicto': ver,
            'secundario_08_16_neto': round(float(np.mean(sec)), 3) if sec else None,
            'secundario_corr_dif_vs_moneda': round(float(np.corrcoef(difs, fxf)[0, 1]), 3) if len(rows) > 2 else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--oos', action='store_true')
    a = ap.parse_args()
    if a.oos:
        with open(OUT, encoding='utf-8') as f:
            if json.load(f)['resultado']['veredicto'] != 'PASA':
                raise SystemExit('No pasó en los 4 pares: por criterio el out-of-sample NO se mira.')
    rows, ctrl, sec = run(PAIRS_OOS if a.oos else PAIRS)
    res = evaluate(rows, ctrl, sec, a.oos)
    out = {'criterio': 'docs/fase5_fin_de_mes_criterio.md (e190950)', 'resultado': res,
           'trades': [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]}
    path = OUT_OOS if a.oos else OUT
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=bool)
    r = res
    print(f"n={r['n']}  NETO={r['neto']:+.3f}p (bruto {r['bruto']:+.3f})  CI95=[{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]")
    print(f"mitades {r['mitad_1']:+.3f} / {r['mitad_2']:+.3f}   control mediana {r['control_mediana']:+.3f}  p95 {r['control_p95']:+.3f}")
    print('por par: ' + '  '.join(f"{k} {v['neto']:+.2f} (n={v['n']})" for k, v in r['por_par'].items()))
    print('condiciones: ' + '  '.join(f"{k}={'OK' if v else 'NO'}" for k, v in r['condiciones'].items()))
    print(f"VEREDICTO: {r['veredicto']}")
    print(f"secundario (no decide): ventana 08-16 neto {r['secundario_08_16_neto']}  ·  corr(dif, moneda) {r['secundario_corr_dif_vs_moneda']}"
          " (el paper predice correlación NEGATIVA)")
    print(f'json: {path}')


if __name__ == '__main__':
    main()
