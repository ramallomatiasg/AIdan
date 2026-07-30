# -*- coding: utf-8 -*-
"""
measure_exhaustion_runup.py — Medidor READ-ONLY de la METRICA DE AGOTAMIENTO (idea #7).

Hipotesis: cuando la senal dispara, el precio YA corrio mucho en la direccion del
trade (run-up previo) => entrada tardia => pierde.

Fuente: deals del broker (pairing identico a measure_entry_suspects.py, magic AIdan)
+ candles M5 del terminal filtradas por EPOCH del deal (misma convencion server-time
en ambos lados; los datetimes de copy_rates_range se piden con ventana generosa y
se filtra por r['time'] directamente, inmune al corrimiento ~3h de la lib).

run_pips = (close_ultima - close_primera)/PIP * (+1 CALL / -1 PUT)
  ventana 60min: candles con time en [open_ts-3900, open_ts-60]
  ventana 30min: candles con time en [open_ts-2100, open_ts-60]

NO escribe a la DB. Veredicto por el gate de la casa (significance.verify_finding).
"""
import os
import sys
import re
import bisect
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAGIC_NUMBER = 20260402
SYMBOL = 'EURUSD'
PIP = 0.0001


def pair_positions(mt5):
    """Identico a measure_entry_suspects.pair_positions (broker-truth)."""
    deals = mt5.history_deals_get(datetime(2026, 4, 1), datetime.now() + timedelta(days=2))
    if deals is None:
        return []
    by_pos = defaultdict(list)
    for d in deals:
        if d.magic == MAGIC_NUMBER and d.symbol == SYMBOL:
            by_pos[d.position_id].append(d)
    positions = []
    for pid, ds in by_pos.items():
        entries = [d for d in ds if d.entry == 0]
        exits = [d for d in ds if d.entry == 1]
        if not entries or not exits:
            continue
        e = entries[0]
        sid = None
        m = re.search(r'AIdan #(\d+)', e.comment or '')
        if m:
            sid = int(m.group(1))
        pnl = sum(d.profit + d.swap + d.commission for d in ds)
        positions.append({
            'sid': sid,
            'direction': 'CALL' if e.type == 0 else 'PUT',
            'open_ts': e.time,
            'close_ts': max(d.time for d in exits),
            'pnl': round(pnl, 2),
        })
    positions.sort(key=lambda p: p['open_ts'])
    return positions


def fmt_stats(subset):
    n = len(subset)
    if n == 0:
        return 'n=  0', 0, 0
    w = sum(1 for p in subset if p['pnl'] > 0)
    pnl = round(sum(p['pnl'] for p in subset), 2)
    return f"n={n:3d}  WR={round(100 * w / n):3d}%  PnL={pnl:+8.2f}", n, w


def gate(label, n, wins, baseline):
    try:
        from src.optimizer.significance import verify_finding
        wr = wins / n if n else 0.0
        direction = 'worse' if wr < baseline else 'better'
        r = verify_finding(n, wins, baseline_wr=baseline, direction=direction)
        return (f"    gate[{label}] dir={direction}: p={r.p_value:.3f} "
                f"CI=[{r.ci_low:.2f},{r.ci_high:.2f}] vs base {baseline:.3f} -> "
                f"{'SIGNIFICATIVO' if r.significant else 'RUIDO'} ({r.reason})")
    except Exception as ex:
        return f"    gate[{label}]: error {ex}"


def main():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print('MetaTrader5 package no disponible'); return
    if not mt5.initialize():
        print(f'No pude attachear al terminal MT5: {mt5.last_error()}'); return
    try:
        positions = pair_positions(mt5)
        print(f'Posiciones cerradas (deals broker, magic AIdan): {len(positions)}')
        if len(positions) < 30:
            print('Muestra demasiado chica. Abortando.'); return
        line, n_all, w_all = fmt_stats(positions)
        baseline = w_all / n_all
        print(f'UNIVERSO: {line}  (baseline interno {baseline:.3f})')

        # Una sola descarga grande de M5; filtrado por epoch (server-time del broker).
        rates = mt5.copy_rates_range(
            SYMBOL, mt5.TIMEFRAME_M5,
            datetime(2026, 3, 28), datetime.now() + timedelta(days=2))
        if rates is None or len(rates) == 0:
            print('Sin candles M5 del terminal.'); return
        times = [int(r['time']) for r in rates]
        closes = [float(r['close']) for r in rates]
        print(f'Candles M5: {len(times)}  '
              f'[{datetime.utcfromtimestamp(times[0])} .. {datetime.utcfromtimestamp(times[-1])}] (server time)')

        def run_pips(p, win_s, min_candles, last_cut=60):
            """Pips recorridos EN LA DIRECCION del trade en la ventana previa."""
            lo = bisect.bisect_left(times, p['open_ts'] - win_s)
            hi = bisect.bisect_right(times, p['open_ts'] - last_cut)
            if hi - lo < min_candles:
                return None
            sign = 1 if p['direction'] == 'CALL' else -1
            return (closes[hi - 1] - closes[lo]) / PIP * sign

        def report(win_label, win_s, min_candles, edges, last_cut=60, run_gates=True):
            # edges = (contra_max, plano_max, mid_max) p.ej. (-5, 5, 15)
            buckets = OrderedDict()
            buckets[f'contra (<{edges[0]:+.1f}p)'] = []
            buckets[f'plano ({edges[0]:+.1f}..{edges[1]:+.1f}p)'] = []
            buckets[f'corrio {edges[1]:.1f}-{edges[2]:.1f}p'] = []
            buckets[f'corrio >{edges[2]:.1f}p'] = []
            nodata = 0
            runs_w, runs_l = [], []
            for p in positions:
                v = run_pips(p, win_s, min_candles, last_cut)
                if v is None:
                    nodata += 1
                    continue
                (runs_w if p['pnl'] > 0 else runs_l).append(v)
                if v < edges[0]:
                    key = list(buckets)[0]
                elif v <= edges[1]:
                    key = list(buckets)[1]
                elif v <= edges[2]:
                    key = list(buckets)[2]
                else:
                    key = list(buckets)[3]
                buckets[key].append(p)
            print(f'\n=== RUN-UP previo {win_label} (cutoff ultima candle: open_ts-{last_cut}s) ===')
            if nodata:
                print(f'  (sin candles suficientes para {nodata} posiciones)')

            def med(xs):
                xs = sorted(xs)
                return xs[len(xs) // 2] if xs else float('nan')
            if runs_w and runs_l:
                print(f'  run-up mediano: ganadores {med(runs_w):+.1f}p  vs  perdedores {med(runs_l):+.1f}p')
            keys = list(buckets)
            for i, (name, sub) in enumerate(buckets.items()):
                line, n, w = fmt_stats(sub)
                print(f'  {name:24s}: {line}')
                if run_gates and n >= 10 and i in (0, 2, 3):  # extremos + corrida media
                    print(gate(name, n, w, baseline))
            return buckets

        # Ventana 60min (espec del frente) y 30min con umbrales mitad
        b60 = report('60min', 3900, 10, (-5.0, 5.0, 15.0))
        b30 = report('30min', 2100, 5, (-2.5, 2.5, 7.5))

        # Robustez: solo candles 100% cerradas antes del entry (cutoff open_ts-300)
        # para descartar contaminacion de la candle en formacion al entry.
        print('\n--- ROBUSTEZ (sin la candle en formacion: cutoff open_ts-300s) ---')
        report('60min*', 3900, 9, (-5.0, 5.0, 15.0), last_cut=300, run_gates=True)
        report('30min*', 2100, 4, (-2.5, 2.5, 7.5), last_cut=300, run_gates=True)

        print('\n--- CAVEATS (leer antes de actuar) ---')
        print('1. Muestra historica SUCIA (mezcla v3.6->v3.40, phantom-pnl viejo, regimenes')
        print('   distintos). Esto RANKEA la hipotesis #7 para el pipeline; NO auto-aplica nada.')
        print('2. run_pips usa closes M5; la ultima candle del cutoff -60s puede estar en')
        print('   formacion al entry (ver bloque ROBUSTEZ para la version sin esa candle).')
        print('3. Default de la casa: RUIDO salvo que el gate diga SIGNIFICATIVO.')
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
