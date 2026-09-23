"""
backtest_fase3b_a1.py — FASE 3b: A1 (reversión a 2σ) por el arnés completo.

READ-ONLY. Lee velas del cache `.cache_fase2/M5_500000` (no necesita MT5, no toca la DB).
Criterio declarado ANTES de correr: docs/fase3b_a1_criterio.md (8868169). Leer contra eso.

Qué agrega sobre el screen de Fase 3 (tools/screen_generators.py, 24affcb):
  - una posición por par a la vez (el screen tomaba las 942k señales solapadas)
  - spread de la vela de entrada (el screen no lo cobraba; MT5 guarda el MÍNIMO de la barra
    ⇒ cota optimista)
  - swap REAL: por rollover cruzado (00:00 server), miércoles triple, sábado/domingo 0
  - 4 sesiones, dos mitades, control aleatorio p95 con los mismos costos

La señal se importa de screen_generators.gen_A1 (no se re-escribe) y antes de medir se
verifica que reproduce el +0,982p del screen (todas las señales, bruto, H96). Si no lo
reproduce, ABORTA: estaría midiendo otra cosa.

Uso:
    python tools/backtest_fase3b_a1.py              # los 20 pares de Fase 1
    python tools/backtest_fase3b_a1.py --reserved   # los 6 reservados (solo si los 20 PASAN)
"""
import argparse
import json
import os
import sys
import zlib
from datetime import datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_multi_symbol import SYMBOLS_FASE1  # noqa: E402
from tools.screen_generators import gen_A1, RESERVADOS  # noqa: E402
from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_fase2', 'M5_500000')
WARMUP = 100
H_MAIN = 96
H_ALL = (12, 48, 96)
MAX_H_SCREEN = 96            # el screen descartaba idx >= n - max(HORIZONS) - 1
CONTROL_REPS = 200
SCREEN_A1_H96 = 0.9824       # docs/fase3_screen_M5.json (pooled close, 20 pares)
OUT_20 = os.path.join(ROOT, 'docs', 'fase3b_a1_resultado.json')
OUT_RES = os.path.join(ROOT, 'docs', 'fase3b_a1_reservados.json')


def load_raw(sym):
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    with open(os.path.join(CACHE, f'{sym}.spec.json')) as f:
        spec = json.load(f)
    return r, spec


def us_dst(dt):
    """Horario de verano de EE.UU.: 2do domingo de marzo -> 1er domingo de noviembre."""
    y = dt.year
    mar = datetime(y, 3, 8) + timedelta(days=(6 - datetime(y, 3, 8).weekday()) % 7)
    nov = datetime(y, 11, 1) + timedelta(days=(6 - datetime(y, 11, 1).weekday()) % 7)
    return mar <= dt.replace(tzinfo=None) < nov


def session_of(t_server):
    dt = datetime.fromtimestamp(int(t_server), timezone.utc).replace(tzinfo=None)
    h = (dt - timedelta(hours=3 if us_dst(dt) else 2)).hour
    if 7 <= h < 12:
        return 'london'
    if 12 <= h < 16:
        return 'overlap'
    if 16 <= h < 20:
        return 'ny'
    return 'off'


def night_weights(t, H):
    """Para cada barra i: noches de swap cobradas entre t[i] y t[i+H] (miércoles=3, sáb/dom=0).

    La noche que TERMINA el día D (rollover a las 00:00 del día D+1) pesa según el weekday de D.
    Las barras están en hora del SERVER, que es donde vive el rollover.
    """
    n = t.size
    day = (t // 86400).astype(np.int64)
    d0 = day.min()
    rel = day - d0
    nd = int(rel.max()) + 2
    wd = (np.arange(nd) + d0 + 3) % 7          # epoch day 0 = jueves ⇒ lunes=0
    w = np.where(wd == 2, 3.0, np.where(wd >= 5, 0.0, 1.0))
    cum = np.concatenate([[0.0], np.cumsum(w)])  # cum[k] = suma de w[0..k-1]
    out = np.zeros(n)
    j = np.arange(n - H)
    de, dx = rel[j], rel[j + H]
    out[j] = cum[dx] - cum[de]                   # noches que terminan en de..dx-1
    return out


def pair_arrays(sym):
    r, spec = load_raw(sym)
    pip = spec['pip']
    o, h, l, c = (r[k].astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    t = r['time'].astype(np.int64)
    spread_pips = r['spread'].astype(np.float64) / 10.0
    idx, dirs = gen_A1(o, h, l, c, t, pip)
    return dict(sym=sym, spec=spec, pip=pip, c=c, t=t, spread=spread_pips, idx=idx, dirs=dirs,
                nw={H: night_weights(t, H) for H in H_ALL})


def trade_nets(P, ii, dd, H):
    """Neto en pips por trade + desglose de costos (vectorizado)."""
    c, pip, spec = P['c'], P['pip'], P['spec']
    gross = dd * (c[ii + H] - c[ii]) / pip
    comm = np.full(ii.size, spec['commission_pips'])
    spr = P['spread'][ii]
    swap = P['nw'][H][ii] * np.where(dd > 0, spec['swap_long_pips'], spec['swap_short_pips'])
    return gross, gross - comm - spr + swap, comm, spr, swap


def one_at_a_time(idx, H):
    keep, free = [], -1
    for k, i in enumerate(idx):
        if i >= free:
            keep.append(k)
            free = i + H
    return np.asarray(keep, dtype=np.int64)


def run(symbols, label):
    pairs = [pair_arrays(s) for s in symbols]

    # ── validación: reproducir el screen (todas las señales, bruto, H96) ──
    if label == '20':
        tot, cnt = 0.0, 0
        for P in pairs:
            n = P['c'].size
            k = (P['idx'] >= WARMUP) & (P['idx'] < n - MAX_H_SCREEN - 1)
            g = P['dirs'][k] * (P['c'][P['idx'][k] + H_MAIN] - P['c'][P['idx'][k]]) / P['pip']
            tot += float(g.sum()); cnt += int(k.sum())
        repro = tot / cnt
        print(f"validación screen: bruto H96 todas las señales = {repro:+.4f}p (screen {SCREEN_A1_H96:+.4f}), n={cnt}")
        if abs(repro - SCREEN_A1_H96) > 0.005:
            raise SystemExit("ABORTA: no reproduce el screen de Fase 3 — la señal o los datos no son los mismos")

    t_first = min(int(P['t'][WARMUP]) for P in pairs)
    t_last = max(int(P['t'][-1]) for P in pairs)
    mid = t_first + (t_last - t_first) / 2
    out = {'pares': symbols, 'por_horizonte': {}}

    for H in H_ALL:
        nets, times, sess, gross_all, comm_all, spr_all, swap_all = [], [], [], [], [], [], []
        por_par, ctrl_sum, ctrl_cnt = [], np.zeros(CONTROL_REPS), np.zeros(CONTROL_REPS)
        for P in pairs:
            n = P['c'].size
            k = (P['idx'] >= WARMUP) & (P['idx'] < n - H - 1)
            idx, dirs = P['idx'][k], P['dirs'][k]
            sel = one_at_a_time(idx, H)
            ii, dd = idx[sel], dirs[sel]
            g, net, cm, sp, sw = trade_nets(P, ii, dd, H)
            nets.append(net); times.append(P['t'][ii]); gross_all.append(g)
            comm_all.append(cm); spr_all.append(sp); swap_all.append(sw)
            if H == H_MAIN:
                sess.extend(session_of(x) for x in P['t'][ii])
            dias = (P['t'][-1] - P['t'][WARMUP]) / 86400 * 5 / 7
            por_par.append({'symbol': P['sym'], 'n': int(ii.size), 'trades_dia': round(ii.size / dias, 2),
                            'neto': round(float(net.mean()), 3) if ii.size else None,
                            'bruto': round(float(g.mean()), 3) if ii.size else None,
                            'swap': round(float(sw.mean()), 3) if ii.size else None,
                            'spread': round(float(sp.mean()), 3) if ii.size else None})
            # control: mismo n, mismo ratio long, misma salida, mismos costos
            if ii.size:
                rng = np.random.default_rng(zlib.crc32(f"{P['sym']}|{H}|f3b".encode()))  # hash() de str es aleatorio por proceso
                p_long = float((dd > 0).mean())
                for r_ in range(CONTROL_REPS):
                    ri = rng.integers(WARMUP, n - H - 1, ii.size)
                    rd = np.where(rng.random(ii.size) < p_long, 1, -1)
                    ctrl_sum[r_] += float(trade_nets(P, ri, rd, H)[1].sum())
                    ctrl_cnt[r_] += ii.size
        net = np.concatenate(nets); tt = np.concatenate(times)
        ctrl = np.sort(ctrl_sum / ctrl_cnt)
        lo, hi, _ = bootstrap_ci(net)
        h1, h2 = net[tt < mid], net[tt >= mid]
        res = {
            'n': int(net.size),
            'neto': round(float(net.mean()), 4),
            'bruto': round(float(np.concatenate(gross_all).mean()), 4),
            'comision': round(float(np.concatenate(comm_all).mean()), 4),
            'spread': round(float(np.concatenate(spr_all).mean()), 4),
            'swap': round(float(np.concatenate(swap_all).mean()), 4),
            'ci95': [lo, hi],
            'mitad_1': round(float(h1.mean()), 4), 'mitad_2': round(float(h2.mean()), 4),
            'control_mediana': round(float(ctrl[CONTROL_REPS // 2]), 4),
            'control_p95': round(float(ctrl[int(0.95 * CONTROL_REPS)]), 4),
            'por_par': sorted(por_par, key=lambda x: -(x['neto'] or -99)),
        }
        if H == H_MAIN:
            sa = np.asarray(sess)
            res['sesiones'] = {s: {'n': int((sa == s).sum()),
                                   'neto': round(float(net[sa == s].mean()), 4) if (sa == s).any() else None}
                               for s in ('london', 'overlap', 'ny', 'off')}
            c = {
                'c1_neto_pos': res['neto'] > 0,
                'c2_ci_lo_pos': lo is not None and lo > 0,
                'c3_dos_mitades': res['mitad_1'] > 0 and res['mitad_2'] > 0,
                'c4_supera_p95': res['neto'] > res['control_p95'],
                'c5_4_sesiones': all((v['neto'] or -1) > 0 for v in res['sesiones'].values()),
            }
            res['condiciones'] = c
            if label == '20':
                res['veredicto'] = 'PASA' if all(c.values()) else 'NO PASA'
            else:
                res['veredicto'] = 'PASA OOS' if (c['c1_neto_pos'] and c['c4_supera_p95']) else 'NO PASA OOS'
        out['por_horizonte'][str(H)] = res
    return out


def show(out):
    for H, r in out['por_horizonte'].items():
        tag = ' <== DECIDE' if int(H) == H_MAIN else ' (secundario)'
        print(f"\nH{H}{tag}: n={r['n']}  NETO={r['neto']:+.3f}p  (bruto {r['bruto']:+.3f} − comisión "
              f"{r['comision']:.3f} − spread {r['spread']:.3f} + swap {r['swap']:+.3f})")
        print(f"   CI95=[{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]  mitades {r['mitad_1']:+.3f} / {r['mitad_2']:+.3f}"
              f"  control mediana {r['control_mediana']:+.3f} p95 {r['control_p95']:+.3f}")
        if 'sesiones' in r:
            print('   sesiones: ' + '  '.join(f"{s} {v['neto']:+.3f} (n={v['n']})" for s, v in r['sesiones'].items()))
            print('   condiciones: ' + '  '.join(f"{k}={'OK' if v else 'NO'}" for k, v in r['condiciones'].items()))
            print(f"   VEREDICTO: {r['veredicto']}")
            print('   por par (neto | trades/día): ' + ', '.join(
                f"{p['symbol']} {p['neto']:+.2f}|{p['trades_dia']}" for p in r['por_par']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        if not os.path.exists(OUT_20):
            raise SystemExit("Primero los 20 pares.")
        with open(OUT_20, encoding='utf-8') as f:
            v = json.load(f)['por_horizonte'][str(H_MAIN)]['veredicto']
        if v != 'PASA':
            raise SystemExit(f"Los 20 pares dieron '{v}': por criterio los reservados NO se miran.")
        out, path = run(list(RESERVADOS), 'res'), OUT_RES
    else:
        out, path = run(list(SYMBOLS_FASE1), '20'), OUT_20
    out['criterio'] = 'docs/fase3b_a1_criterio.md (8868169)'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=bool)
    show(out)
    print(f"\njson: {path}")


if __name__ == '__main__':
    main()
