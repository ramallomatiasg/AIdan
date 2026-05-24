"""
enrich_archive_features.py — Calcula features predictivos adicionales sobre
cada trade del archive, retroactivamente usando MT5 historical candles.

Features agregados (v1 + v2 Domingo):

V1 (sábado):
- velocity_5c, velocity_10c: pips movidos en N candles previos (momentum reciente)
- body_atr_ratio: |close-open| / ATR de la vela de entry (fuerza presión)
- dist_prev_high, dist_prev_low: pips desde el high/low del día anterior
- mins_since_high_impact_news: minutos desde el último impact>=70 news

V2 (domingo):
- volume_zscore: tick_volume del candle de entry / mean(last 20)
- multi_tf_score: cuantos TFs (M5+M15+H1+H4) alineados con direction
- dist_round_pips: distancia al numero redondo mas cercano
- dist_5d_high_pips, dist_5d_low_pips: posicion en rango semanal
- spread_at_entry_pips: spread del candle (mas alto = mas fricción)

Output: F:/AIdan/trade_archive_enriched.csv (features extra por trade_id)

Razon: Fase A del refactor mostro modelo logistic regression con AUC 0.45
(peor que la heuristica vieja AUC 0.59). Indica que el problema NO es
algoritmo sino DATA — features actuales (RSI, ATR, session, htf_bias)
no contienen suficiente info predictiva. Antes de invertir mas tiempo en
algoritmo, validar si MÁS features mueven el AUC.

Si AUC sube significativamente (>0.6) → seguimos Fase A→D con confianza.
Si NO → señal honesta de que approach scalp retail no funciona y toca pivot.

Uso:
    python tools/enrich_archive_features.py
"""
import csv
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'financial_news.db')
OUTPUT = ROOT / 'trade_archive_enriched.csv'

# Map trigger_type -> MT5 timeframe + candles a fetch
TF_MAP = {
    'structure': (mt5.TIMEFRAME_M5, 15),
    'news': (mt5.TIMEFRAME_M5, 15),
    'smc': (mt5.TIMEFRAME_M5, 15),
    'pre_planned': (mt5.TIMEFRAME_M5, 15),
    'calendar': (mt5.TIMEFRAME_M5, 15),
    'm15_structure': (mt5.TIMEFRAME_M15, 15),
    'h1_structure': (mt5.TIMEFRAME_H1, 15),
}


def parse_ts(s):
    """Parse trade_archive created_at to datetime."""
    s = str(s).split('.')[0]
    try:
        return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            return None


def fetch_candles_before(symbol, timeframe, end_dt, count):
    """Fetch `count` candles BEFORE end_dt. Returns list of dicts or None."""
    try:
        rates = mt5.copy_rates_from(symbol, timeframe, end_dt, count)
        if rates is None or len(rates) == 0:
            return None
        return [
            {
                'time': int(r['time']),
                'open': float(r['open']),
                'high': float(r['high']),
                'low': float(r['low']),
                'close': float(r['close']),
                'tick_volume': int(r['tick_volume']) if 'tick_volume' in rates.dtype.names else 0,
                'spread': int(r['spread']) if 'spread' in rates.dtype.names else 0,
            }
            for r in rates
        ]
    except Exception:
        return None


def compute_volume_zscore(candles):
    """tick_volume del candle de entry vs media de los previos."""
    if not candles or len(candles) < 11:
        return None
    last_volume = candles[-1].get('tick_volume', 0)
    prev_volumes = [c.get('tick_volume', 0) for c in candles[-11:-1]]
    if not prev_volumes or all(v == 0 for v in prev_volumes):
        return None
    mean_v = sum(prev_volumes) / len(prev_volumes)
    if mean_v == 0:
        return None
    return round(last_volume / mean_v, 3)


def compute_multi_tf_score(symbol, trade_dt, direction):
    """Score 0-4: cuántos TFs (M5, M15, H1, H4) están alineados con direction.
    Trend simple: close[now] > close[-10] -> bullish."""
    tfs = [mt5.TIMEFRAME_M5, mt5.TIMEFRAME_M15, mt5.TIMEFRAME_H1, mt5.TIMEFRAME_H4]
    score = 0
    for tf in tfs:
        try:
            rates = mt5.copy_rates_from(symbol, tf, trade_dt, 12)
            if rates is None or len(rates) < 11:
                continue
            trend_bullish = float(rates[-1]['close']) > float(rates[-11]['close'])
            if direction == 'CALL' and trend_bullish:
                score += 1
            elif direction == 'PUT' and not trend_bullish:
                score += 1
        except Exception:
            continue
    return score


def compute_dist_to_round_number(entry_price):
    """Distancia en pips al numero redondo mas cercano (1.17, 1.175, 1.18)."""
    if not entry_price:
        return None
    # Niveles redondos: cada 50 pips (1.1700, 1.1750, 1.1800...)
    nearest_50pip = round(entry_price * 200) / 200  # round to nearest 0.005 = 50p
    dist_pips = abs(entry_price - nearest_50pip) / 0.0001
    return round(dist_pips, 1)


def get_5d_extremes(symbol, trade_dt):
    """Fetch high/low de los últimos 5 daily candles antes del trade."""
    try:
        d1_candles = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_D1, trade_dt, 7)
        if d1_candles is None or len(d1_candles) < 5:
            return None, None
        trade_date = trade_dt.date()
        previous_5 = []
        for r in reversed(d1_candles):
            candle_date = datetime.fromtimestamp(int(r['time'])).date()
            if candle_date < trade_date:
                previous_5.append(r)
            if len(previous_5) >= 5:
                break
        if not previous_5:
            return None, None
        highs = [float(r['high']) for r in previous_5]
        lows = [float(r['low']) for r in previous_5]
        return max(highs), min(lows)
    except Exception:
        return None, None


def compute_velocity(candles, n):
    """Pips moved over last n candles (close[-1] - close[-n-1])."""
    if not candles or len(candles) < n + 1:
        return None
    p = 0.0001
    return (candles[-1]['close'] - candles[-(n+1)]['close']) / p


def compute_body_ratio(candle, atr_pips):
    """|close - open| / atr (cuán fuerte la vela en relación al rango típico)."""
    if not candle or not atr_pips or atr_pips <= 0:
        return None
    p = 0.0001
    body_pips = abs(candle['close'] - candle['open']) / p
    return body_pips / atr_pips


def get_prev_day_extremes(symbol, trade_dt):
    """Fetch daily candle of yesterday (relative to trade_dt). Returns (high, low) or (None, None)."""
    try:
        # Fetch ultimos 5 daily candles to be safe
        d1_candles = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_D1, trade_dt, 3)
        if d1_candles is None or len(d1_candles) < 2:
            return None, None
        # Buscar la vela cuyo día sea < trade_dt.date() (la anterior)
        trade_date = trade_dt.date()
        for r in reversed(d1_candles):
            candle_date = datetime.fromtimestamp(int(r['time'])).date()
            if candle_date < trade_date:
                return float(r['high']), float(r['low'])
        return None, None
    except Exception:
        return None, None


def get_mins_since_news(cur, trade_dt, impact_threshold=70):
    """Query alerts for last high-impact alert BEFORE trade_dt."""
    try:
        cur.execute("""SELECT alert_sent_at FROM alerts
                       WHERE impact_score >= ? AND alert_sent_at < ?
                       ORDER BY alert_sent_at DESC LIMIT 1""",
                    (impact_threshold, trade_dt.isoformat()))
        row = cur.fetchone()
        if not row:
            return None
        news_dt = parse_ts(row[0])
        if not news_dt:
            return None
        delta = (trade_dt - news_dt).total_seconds() / 60
        return round(delta, 1)
    except Exception:
        return None


def main():
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        sys.exit(1)

    symbol = 'EURUSD'
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Load trades
    cur.execute("""SELECT id, created_at, entry_price, trigger_type, avg_range_pips, direction
                   FROM trade_archive
                   WHERE result IN ('win','loss') AND mt5_pnl IS NOT NULL
                   ORDER BY id""")
    trades = cur.fetchall()
    print(f"Loaded {len(trades)} trades from archive")

    results = []
    skipped = 0
    for i, (tid, created_at, entry_price, trigger_type, atr, direction) in enumerate(trades, 1):
        trade_dt = parse_ts(created_at)
        if not trade_dt:
            skipped += 1
            continue

        tf, n_candles = TF_MAP.get(trigger_type, (mt5.TIMEFRAME_M5, 15))
        candles = fetch_candles_before(symbol, tf, trade_dt, n_candles)

        velocity_5c = compute_velocity(candles, 5) if candles else None
        velocity_10c = compute_velocity(candles, 10) if candles else None
        body_ratio = compute_body_ratio(candles[-1], atr) if candles else None

        # Velocity ALINEADA con direction (CALL = positive favors, PUT = negative favors)
        # Para que sea predictivo: si entry CALL despues de subida fuerte, ¿mejor o peor?
        # Test ambas: signed (raw) y aligned (positivo si en favor)
        v5_aligned = velocity_5c if direction == 'CALL' else (-velocity_5c if velocity_5c is not None else None)
        v10_aligned = velocity_10c if direction == 'CALL' else (-velocity_10c if velocity_10c is not None else None)

        prev_high, prev_low = get_prev_day_extremes(symbol, trade_dt)
        dist_prev_high_pips = None
        dist_prev_low_pips = None
        if prev_high and entry_price:
            dist_prev_high_pips = (prev_high - entry_price) / 0.0001
        if prev_low and entry_price:
            dist_prev_low_pips = (entry_price - prev_low) / 0.0001

        mins_since_news = get_mins_since_news(cur, trade_dt)

        # V2 — domingo features
        volume_zscore = compute_volume_zscore(candles) if candles else None
        multi_tf_score = compute_multi_tf_score(symbol, trade_dt, direction)
        dist_round = compute_dist_to_round_number(entry_price)
        high_5d, low_5d = get_5d_extremes(symbol, trade_dt)
        dist_5d_high = (high_5d - entry_price) / 0.0001 if high_5d and entry_price else None
        dist_5d_low = (entry_price - low_5d) / 0.0001 if low_5d and entry_price else None
        spread_entry = candles[-1].get('spread', 0) / 10 if candles else None  # MT5 spread in points/10

        results.append({
            'trade_id': tid,
            'velocity_5c_pips': round(velocity_5c, 2) if velocity_5c is not None else None,
            'velocity_10c_pips': round(velocity_10c, 2) if velocity_10c is not None else None,
            'velocity_5c_aligned': round(v5_aligned, 2) if v5_aligned is not None else None,
            'velocity_10c_aligned': round(v10_aligned, 2) if v10_aligned is not None else None,
            'body_atr_ratio': round(body_ratio, 3) if body_ratio is not None else None,
            'dist_prev_high_pips': round(dist_prev_high_pips, 1) if dist_prev_high_pips is not None else None,
            'dist_prev_low_pips': round(dist_prev_low_pips, 1) if dist_prev_low_pips is not None else None,
            'mins_since_high_impact_news': mins_since_news,
            # V2 domingo
            'volume_zscore': volume_zscore,
            'multi_tf_score': multi_tf_score,
            'dist_round_pips': dist_round,
            'dist_5d_high_pips': round(dist_5d_high, 1) if dist_5d_high is not None else None,
            'dist_5d_low_pips': round(dist_5d_low, 1) if dist_5d_low is not None else None,
            'spread_entry_pips': round(spread_entry, 2) if spread_entry is not None else None,
        })

        if i % 50 == 0:
            print(f"  Processed {i}/{len(trades)}...")

    conn.close()
    mt5.shutdown()

    print(f"\nFinal: {len(results)} enriched, {skipped} skipped")

    # Save to CSV
    with open(OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved: {OUTPUT} ({os.path.getsize(OUTPUT)} bytes)")

    # Quick coverage stats
    print("\n=== Feature coverage (non-null %) ===")
    if results:
        for k in results[0].keys():
            if k == 'trade_id': continue
            non_null = sum(1 for r in results if r[k] is not None)
            print(f"  {k:35s} {non_null}/{len(results)} ({non_null*100/len(results):.0f}%)")


if __name__ == '__main__':
    main()
