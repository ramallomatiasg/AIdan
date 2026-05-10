"""
backtest_h1_m15.py — backtest estructural-only para Track B (M15) y Track C (H1).

Objetivo: estimar WR/PF/expectancy de los nuevos tracks ANTES de esperar 3-4 semanas
de demo. Re-corre detect_structure_signals() sobre candles MT5 historicas y simula
hit de SL/TP/expiry con high/low de candles posteriores.

Caveats (importantes):
- Solo cubre trigger 'structure' (sin news, calendar, pre_planned, smc context live).
- Ausencia de spread variable, slippage, latency execution.
- AutoTuner params actuales aplicados a data vieja (mild data leakage).
- HTF bias = None (no derivamos H1 SMC bias para M15 en backtest).
- Backtest tipico INFLA metricas 20-30% vs real con friccion. Si PF backtest
  da 1.4 -> real ~1.2; si da 1.0 -> real ~0.8.
- Resultados son INDICATIVOS, NO decisivos. Demo real sigue siendo la verdad.

Uso:
    python tools/backtest_h1_m15.py
    python tools/backtest_h1_m15.py --m15-days 30 --h1-days 30
    python tools/backtest_h1_m15.py --min-conf 65

Output:
    backtest_h1_m15_YYYYMMDD_HHMMSS.json (resumen stats)
    backtest_h1_m15_YYYYMMDD_HHMMSS.csv  (cada signal con outcome)

Requiere: AIdan corriendo (o MT5 terminal abierto) para fetch de candles historicas.
"""
import argparse
import csv
import json
import logging
import os
import sys
import time
from copy import deepcopy
from datetime import datetime
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.analyzer.technical_m15 import TechnicalAnalyzerM15, M15_PROFILE
from src.analyzer.technical_h1 import TechnicalAnalyzerH1, H1_PROFILE


def setup_logger(level=logging.WARNING):
    logger = logging.getLogger("backtest_h1_m15")
    logger.setLevel(level)
    h = logging.StreamHandler()
    h.setLevel(level)
    h.setFormatter(logging.Formatter('%(levelname)s | %(message)s'))
    logger.addHandler(h)
    return logger


def fetch_mt5_history(interval, count):
    """Fetch <count> historical candles from MT5 (most recent <count> bars).
    Returns list of dicts: open/high/low/close/datetime/time_unix.
    """
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

    tf_map = {
        '5min': mt5.TIMEFRAME_M5,
        '15min': mt5.TIMEFRAME_M15,
        '1h': mt5.TIMEFRAME_H1,
    }
    if interval not in tf_map:
        raise ValueError(f"Unsupported interval {interval}")

    rates = mt5.copy_rates_from_pos("EURUSD", tf_map[interval], 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No candles returned for {interval}")

    candles = []
    for r in rates:
        candles.append({
            'open': float(r['open']),
            'high': float(r['high']),
            'low': float(r['low']),
            'close': float(r['close']),
            'datetime': str(datetime.utcfromtimestamp(int(r['time']))),
            'time_unix': int(r['time']),
        })
    return candles


def simulate_signal_outcome(entry_idx, candles, direction, sl_pips, tp_pips,
                             expiry_minutes, tf_minutes):
    """Walk forward from entry_idx+1 to detect SL/TP/expiry hit.
    Conservative: si en una misma vela tocan SL y TP, asumimos SL primero.
    Returns dict: {result, exit_idx, exit_price, pips}.
    """
    pip = 0.0001
    entry = candles[entry_idx]
    entry_price = entry['close']

    if direction == 'CALL':
        sl_price = entry_price - sl_pips * pip
        tp_price = entry_price + tp_pips * pip
    elif direction == 'PUT':
        sl_price = entry_price + sl_pips * pip
        tp_price = entry_price - tp_pips * pip
    else:
        return {'result': 'skip', 'exit_idx': entry_idx, 'exit_price': entry_price, 'pips': 0}

    expiry_candles = max(1, int(expiry_minutes / tf_minutes))
    end_idx = min(entry_idx + 1 + expiry_candles, len(candles))

    for j in range(entry_idx + 1, end_idx):
        c = candles[j]
        if direction == 'CALL':
            sl_hit = c['low'] <= sl_price
            tp_hit = c['high'] >= tp_price
        else:
            sl_hit = c['high'] >= sl_price
            tp_hit = c['low'] <= tp_price

        if sl_hit and tp_hit:
            return {'result': 'sl', 'exit_idx': j, 'exit_price': sl_price, 'pips': -float(sl_pips)}
        if tp_hit:
            return {'result': 'tp', 'exit_idx': j, 'exit_price': tp_price, 'pips': float(tp_pips)}
        if sl_hit:
            return {'result': 'sl', 'exit_idx': j, 'exit_price': sl_price, 'pips': -float(sl_pips)}

    # Expiry: close at last candle close
    last = candles[end_idx - 1]
    if direction == 'CALL':
        pips = (last['close'] - entry_price) / pip
    else:
        pips = (entry_price - last['close']) / pip
    return {'result': 'expiry', 'exit_idx': end_idx - 1, 'exit_price': last['close'], 'pips': round(float(pips), 1)}


def run_backtest(tf_label, AnalyzerClass, profile, interval, total_candles,
                 tf_minutes, warmup, min_conf_override, logger):
    """Re-correr scanner sobre candles historicas, generar y simular signals."""
    print(f"\n=== Backtest {tf_label} ===")
    print(f"  interval={interval} | total candles={total_candles} | warmup={warmup}")
    print(f"  profile: SL={profile['stop_loss_pips']}p TP={profile['take_profit_pips']}p"
          f" expiry={profile['expiry_minutes']}min min_conf={profile['min_confidence']}")

    candles = fetch_mt5_history(interval, total_candles)
    if not candles:
        print(f"  ERROR: no candles fetched")
        return None

    print(f"  fetched {len(candles)} candles | {candles[0]['datetime']} -> {candles[-1]['datetime']}")

    analyzer = AnalyzerClass(logger)
    min_conf = min_conf_override if min_conf_override is not None else profile['min_confidence']

    signals = []
    last_print = time.time()
    skipped_errors = 0

    # Patch time.time inside technical module so dedup uses HISTORICAL timestamps,
    # not the real "now" (which makes all triggers fall in the same dedup window).
    import src.analyzer.technical as tech_mod

    for i in range(warmup, len(candles) - 1):
        slice_ = candles[max(0, i - warmup + 1):i + 1]

        # Override fetch + clear cache so market_state recomputes on this slice
        analyzer._fetch_candles = lambda s=slice_: deepcopy(s)
        analyzer._cache.clear()

        candle_unix = candles[i]['time_unix']
        try:
            with patch.object(tech_mod.time, 'time', return_value=candle_unix):
                sigs = analyzer.detect_structure_signals(min_confidence=min_conf)
        except Exception as e:
            skipped_errors += 1
            if skipped_errors <= 3:
                logger.warning(f"  step {i} ({candles[i]['datetime']}): {e}")
            continue

        for s in sigs:
            outcome = simulate_signal_outcome(
                i, candles, s['direction'],
                profile['stop_loss_pips'], profile['take_profit_pips'],
                profile['expiry_minutes'], tf_minutes
            )
            signals.append({
                'step': i,
                'datetime': candles[i]['datetime'],
                'direction': s['direction'],
                'confidence': s.get('confidence', 0),
                'setup_type': s.get('setup_type', '?'),
                'reason': str(s.get('reason', ''))[:100],
                'entry_price': candles[i]['close'],
                **outcome,
            })

        # Progress every 5s
        now = time.time()
        if now - last_print >= 5:
            pct = (i - warmup) / (len(candles) - 1 - warmup) * 100
            print(f"    ... {pct:.0f}% (step {i}/{len(candles)-1}, signals so far: {len(signals)})")
            last_print = now

    if skipped_errors:
        print(f"  WARN: {skipped_errors} steps skipped por error (ver log)")

    return aggregate_stats(tf_label, signals, profile)


def aggregate_stats(tf_label, signals, profile):
    """Compute WR, PF, expectancy, etc."""
    n = len(signals)
    if n == 0:
        return {'tf': tf_label, 'profile': profile, 'signals': 0, 'note': 'no signals generated'}

    wins_tp = sum(1 for s in signals if s['result'] == 'tp')
    losses_sl = sum(1 for s in signals if s['result'] == 'sl')
    expiries = [s for s in signals if s['result'] == 'expiry']
    expiry_wins = sum(1 for s in expiries if s['pips'] > 0)
    expiry_losses = sum(1 for s in expiries if s['pips'] <= 0)

    total_pips = sum(s['pips'] for s in signals)
    gross_win = sum(s['pips'] for s in signals if s['pips'] > 0)
    gross_loss = abs(sum(s['pips'] for s in signals if s['pips'] < 0))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else float('inf')

    # WR includes expiry-wins (positive expiry counts as win)
    total_wins = wins_tp + expiry_wins
    wr = round(total_wins / n * 100, 1)
    avg_pips = round(total_pips / n, 2)

    # Breakdown by setup_type
    by_setup = {}
    for s in signals:
        st = s.get('setup_type', '?')
        by_setup.setdefault(st, {'count': 0, 'wins': 0, 'losses': 0, 'pips': 0.0})
        by_setup[st]['count'] += 1
        by_setup[st]['pips'] += s['pips']
        if s['pips'] > 0:
            by_setup[st]['wins'] += 1
        else:
            by_setup[st]['losses'] += 1
    for st in by_setup:
        c = by_setup[st]['count']
        by_setup[st]['wr_pct'] = round(by_setup[st]['wins'] / c * 100, 1) if c else 0
        by_setup[st]['pips'] = round(by_setup[st]['pips'], 1)

    # Direction breakdown
    by_dir = {'CALL': 0, 'PUT': 0}
    by_dir_wins = {'CALL': 0, 'PUT': 0}
    for s in signals:
        d = s['direction']
        by_dir[d] = by_dir.get(d, 0) + 1
        if s['pips'] > 0:
            by_dir_wins[d] = by_dir_wins.get(d, 0) + 1

    return {
        'tf': tf_label,
        'profile': profile,
        'signals': n,
        'wins_tp': wins_tp,
        'losses_sl': losses_sl,
        'expiries_total': len(expiries),
        'expiry_wins': expiry_wins,
        'expiry_losses': expiry_losses,
        'total_wins': total_wins,
        'wr_pct': wr,
        'pf': pf,
        'total_pips': round(total_pips, 1),
        'avg_pips_per_trade': avg_pips,
        'gross_win_pips': round(gross_win, 1),
        'gross_loss_pips': round(gross_loss, 1),
        'by_setup_type': by_setup,
        'by_direction': by_dir,
        'by_direction_wins': by_dir_wins,
        'all_signals': signals,
    }


def print_summary(s):
    print(f"\n=== Resumen {s['tf']} ===")
    if s['signals'] == 0:
        print("  Sin senales generadas en el periodo. Considera bajar min_conf o aumentar dias.")
        return
    print(f"  Signals total          : {s['signals']}")
    print(f"  Wins TP / Losses SL    : {s['wins_tp']} / {s['losses_sl']}")
    print(f"  Expiries (W/L)         : {s['expiries_total']} ({s['expiry_wins']} / {s['expiry_losses']})")
    print(f"  WR (incl expiry-wins)  : {s['wr_pct']}%")
    print(f"  PF                     : {s['pf']}")
    print(f"  Total pips             : {s['total_pips']}")
    print(f"  Avg pips per trade     : {s['avg_pips_per_trade']}")
    print(f"  Gross win / gross loss : {s['gross_win_pips']}p / {s['gross_loss_pips']}p")
    print(f"  By direction           : {s['by_direction']} (wins {s['by_direction_wins']})")
    print(f"  By setup_type:")
    for st, d in sorted(s['by_setup_type'].items(), key=lambda x: -x[1]['count']):
        print(f"    {st:30s} count={d['count']:3d} wr={d['wr_pct']:5.1f}% pips={d['pips']:+7.1f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--m15-days', type=int, default=60, help='Dias de candles M15 (default 60)')
    parser.add_argument('--h1-days',  type=int, default=60, help='Dias de candles H1 (default 60)')
    parser.add_argument('--warmup', type=int, default=100, help='Candles minimas para indicators (default 100)')
    parser.add_argument('--min-conf', type=int, default=None,
                        help='Override min_confidence (default usa profile)')
    parser.add_argument('--skip-m15', action='store_true', help='Skip Track B (M15)')
    parser.add_argument('--skip-h1',  action='store_true', help='Skip Track C (H1)')
    parser.add_argument('--debug', action='store_true', help='Logging DEBUG')
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARNING
    logger = setup_logger(log_level)

    # M15: dias * 96 candles/dia. H1: dias * 24 candles/dia.
    M15_TOTAL = args.m15_days * 96
    H1_TOTAL = args.h1_days * 24

    print("=" * 70)
    print(f"BACKTEST H1 + M15 — {datetime.now()}")
    print("=" * 70)
    print("CAVEATS:")
    print("- Solo trigger 'structure' (sin news/calendar/pre_planned/smc-live)")
    print("- Sin spread variable, slippage, latency execution")
    print("- AutoTuner params actuales aplicados a data vieja (mild leakage)")
    print("- HTF bias = None (no derivado de SMC live)")
    print("- Resultados INDICATIVOS, no decisivos. Demo real es la verdad.")
    print("- Backtest tipico infla metricas 20-30% vs real con friccion.")
    print("=" * 70)

    results = {}

    if not args.skip_m15:
        try:
            r = run_backtest('M15', TechnicalAnalyzerM15, M15_PROFILE,
                             '15min', M15_TOTAL, tf_minutes=15,
                             warmup=args.warmup, min_conf_override=args.min_conf,
                             logger=logger)
            if r:
                print_summary(r)
                results['M15'] = r
        except Exception as e:
            print(f"M15 backtest failed: {e}")
            import traceback
            traceback.print_exc()

    if not args.skip_h1:
        try:
            r = run_backtest('H1', TechnicalAnalyzerH1, H1_PROFILE,
                             '1h', H1_TOTAL, tf_minutes=60,
                             warmup=args.warmup, min_conf_override=args.min_conf,
                             logger=logger)
            if r:
                print_summary(r)
                results['H1'] = r
        except Exception as e:
            print(f"H1 backtest failed: {e}")
            import traceback
            traceback.print_exc()

    # Comparativo final
    if 'M15' in results and 'H1' in results:
        print("\n" + "=" * 70)
        print("COMPARATIVA M15 vs H1")
        print("=" * 70)
        m, h = results['M15'], results['H1']
        print(f"  Signals      : M15 {m['signals']:3d}  |  H1 {h['signals']:3d}")
        print(f"  WR%          : M15 {m['wr_pct']:5.1f}  |  H1 {h['wr_pct']:5.1f}")
        print(f"  PF           : M15 {m['pf']:5.2f}  |  H1 {h['pf']:5.2f}")
        print(f"  Total pips   : M15 {m['total_pips']:+7.1f}  |  H1 {h['total_pips']:+7.1f}")
        print(f"  Avg pips/sig : M15 {m['avg_pips_per_trade']:+7.2f}  |  H1 {h['avg_pips_per_trade']:+7.2f}")

    # Save outputs
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT
    json_path = os.path.join(out_dir, f'backtest_h1_m15_{ts}.json')
    csv_path = os.path.join(out_dir, f'backtest_h1_m15_{ts}.csv')

    # JSON: stats sin all_signals (para compactness)
    compact = {tf: {k: v for k, v in r.items() if k != 'all_signals'}
               for tf, r in results.items()}
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(compact, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nResults JSON : {json_path}")

    # CSV: per-signal detail
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['tf', 'step', 'datetime', 'direction', 'confidence',
                    'setup_type', 'entry_price', 'result', 'exit_price',
                    'pips', 'reason'])
        for tf, r in results.items():
            for s in r.get('all_signals', []):
                w.writerow([tf, s['step'], s['datetime'], s['direction'],
                            s.get('confidence', 0), s.get('setup_type', '?'),
                            s.get('entry_price', 0), s.get('result', '?'),
                            s.get('exit_price', 0), s.get('pips', 0),
                            s.get('reason', '')])
    print(f"Per-signal CSV: {csv_path}")
    print()


if __name__ == '__main__':
    main()
