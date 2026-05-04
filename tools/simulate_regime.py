"""Simulación v3.10.0: efecto del regime detection sobre 107 trades históricos.

Para cada trade, fetch las 50 velas M5 anteriores al entry desde MT5,
clasifica el régimen, y aplica los nuevos filtros.

Read-only. Output: console + comparativa con baseline.
"""
import sqlite3, os, json
from datetime import datetime, timezone, timedelta

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MT5 not installed"); raise SystemExit(1)

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')


def init_mt5():
    if not mt5.initialize(): print(f"MT5 init: {mt5.last_error()}"); return False
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    env = {}
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, _, v = line.strip().partition('=')
                    env[k.strip()] = v.strip()
    if env.get('MT5_ACCOUNT'):
        try: mt5.login(int(env['MT5_ACCOUNT']), password=env.get('MT5_PASSWORD',''), server=env.get('MT5_SERVER',''))
        except: pass
    return True


def detect_regime(candles, ma_fast, ma_slow, avg_range_pips):
    """Same logic as in technical.py — uses last 50 M5 candles."""
    if len(candles) < 50:
        return 'uncertain', 0
    recent = candles[-50:]
    recent_closes = [c['close'] for c in recent]
    recent_highs = [c['high'] for c in recent]
    recent_lows = [c['low'] for c in recent]

    net_move_pips = abs(recent_closes[-1] - recent_closes[0]) * 10000
    directional_score = net_move_pips / max(avg_range_pips, 1.0)
    range_pips = (max(recent_highs) - min(recent_lows)) * 10000
    range_atrs = range_pips / max(avg_range_pips, 1.0)
    ma_gap_pips = abs(ma_fast - ma_slow) * 10000
    ma_alignment_score = ma_gap_pips / max(avg_range_pips, 1.0)

    score = 0
    if directional_score > 3.0: score += 1
    if range_atrs > 7.0: score += 1
    if ma_alignment_score > 0.6: score += 1

    if score >= 2: return 'trending', score
    if score == 0 and directional_score < 1.5: return 'ranging', score
    return 'uncertain', score


def get_m5_state_at(ts_unix):
    """Fetch 50 M5 candles ending at ts, compute MAs and ATR."""
    rates = mt5.copy_rates_from('EURUSD', mt5.TIMEFRAME_M5, datetime.fromtimestamp(ts_unix, tz=timezone.utc), 50)
    if rates is None or len(rates) < 50:
        return None
    candles = [{'open': r['open'], 'high': r['high'], 'low': r['low'], 'close': r['close']} for r in rates]
    closes = [c['close'] for c in candles]
    ma_fast = sum(closes[-9:]) / 9
    ma_slow = sum(closes[-21:]) / 21

    # ATR-14
    trs = []
    for i in range(-14, 0):
        if i == -14: continue
        h, l = candles[i]['high'], candles[i]['low']
        prev_c = candles[i-1]['close']
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr * 10000)
    avg_range = sum(trs) / len(trs) if trs else 0
    return candles, ma_fast, ma_slow, avg_range


def main():
    if not init_mt5(): return
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT t.id, t.direction, t.result, t.mt5_pnl, t.pips, t.trigger_type, t.htf_bias, t.market_trend,
        t.created_at, COALESCE(s.mt5_fill_price, t.entry_price) as fill_price, t.setup_type
        FROM trade_archive t LEFT JOIN auto_strategies s ON t.strategy_id = s.id
        WHERE t.result IN ('win','loss') AND t.archived_at >= '2026-04-21'
        AND COALESCE(s.mt5_fill_price, t.entry_price) > 0
        ORDER BY t.id""")
        trades = c.fetchall()
        conn.close()

        print(f"Loaded {len(trades)} trades")

        # Classify each trade
        results = []
        skipped = 0
        regime_counts = {'trending': 0, 'ranging': 0, 'uncertain': 0}

        for t in trades:
            tid, d, res, pnl, pips, trig, htf, m5_trend, created_at, fill, setup_type = t
            try:
                dt_ar = datetime.fromisoformat(created_at.split('.')[0])
                ts = int((dt_ar + timedelta(hours=3)).replace(tzinfo=timezone.utc).timestamp())
            except: skipped += 1; continue

            state = get_m5_state_at(ts)
            if not state: skipped += 1; continue
            candles, ma_fast, ma_slow, avg_range = state
            regime, score = detect_regime(candles, ma_fast, ma_slow, avg_range)
            regime_counts[regime] += 1

            # Apply new filters
            is_aligned = (d=='CALL' and htf=='bullish' and m5_trend=='bullish') or (d=='PUT' and htf=='bearish' and m5_trend=='bearish')
            is_counter_htf = (d=='CALL' and htf=='bearish') or (d=='PUT' and htf=='bullish')
            is_reversal = setup_type and any(t in (setup_type or '') for t in ('reversal', 'rejection', 'rebote', 'rechazo'))

            blocked_by = None
            # Apply v3.10.0 CORRECTED logic to structure/smc trades (news exempt)
            is_counter_both = (d=='CALL' and htf=='bearish' and m5_trend=='bearish') or (d=='PUT' and htf=='bullish' and m5_trend=='bullish')
            if trig in ('structure', 'smc'):
                if is_aligned:
                    blocked_by = 'fully-aligned (exhaustion)'
                elif is_counter_both:
                    blocked_by = 'counter-both (no edge)'

            results.append({
                'id': tid, 'dir': d, 'res': res, 'pnl': pnl, 'pips': pips,
                'trig': trig, 'htf': htf, 'm5_trend': m5_trend, 'setup': setup_type,
                'regime': regime, 'score': score,
                'aligned': is_aligned, 'counter_htf': is_counter_htf, 'reversal': is_reversal,
                'blocked_by': blocked_by,
            })

        print(f"Classified: {len(results)}, skipped: {skipped}")
        print(f"Regime distribution: {regime_counts}")
        print()

        # === COMPARATIVA ===
        baseline_pnl = sum(r['pnl'] or 0 for r in results)
        baseline_n = len(results)
        baseline_w = sum(1 for r in results if r['res']=='win')
        print("=" * 70)
        print("BASELINE (current behavior, all 107 trades):")
        print(f"  n={baseline_n} | {baseline_w}W ({baseline_w/baseline_n*100:.0f}%) | PnL ${baseline_pnl:+.2f}")
        gw = sum(r['pnl'] for r in results if (r['pnl'] or 0)>0)
        gl = abs(sum(r['pnl'] for r in results if (r['pnl'] or 0)<0))
        print(f"  PF: {gw/gl:.2f}")
        print()

        # v3.10.0 — apply filters
        kept_v310 = [r for r in results if not r['blocked_by']]
        blocked_v310 = [r for r in results if r['blocked_by']]
        v310_pnl = sum(r['pnl'] or 0 for r in kept_v310)
        v310_w = sum(1 for r in kept_v310 if r['res']=='win')
        bw = sum(1 for r in blocked_v310 if r['res']=='win')
        bl = sum(1 for r in blocked_v310 if r['res']=='loss')
        b_pnl = sum(r['pnl'] or 0 for r in blocked_v310)

        print("v3.10.0 (regime-aware filters applied):")
        print(f"  n={len(kept_v310)} | {v310_w}W ({v310_w/max(1,len(kept_v310))*100:.0f}%) | PnL ${v310_pnl:+.2f}")
        gw2 = sum(r['pnl'] for r in kept_v310 if (r['pnl'] or 0)>0)
        gl2 = abs(sum(r['pnl'] for r in kept_v310 if (r['pnl'] or 0)<0))
        print(f"  PF: {gw2/gl2 if gl2 else 0:.2f}")
        print(f"  Blocked: {len(blocked_v310)} ({bw}W/{bl}L), saved blocked PnL ${-b_pnl:+.2f}")
        print(f"  Delta vs baseline: ${v310_pnl - baseline_pnl:+.2f}")
        print()

        # Por motivo de bloqueo
        print("Blocked breakdown:")
        from collections import Counter
        block_reasons = Counter(r['blocked_by'] for r in blocked_v310)
        for reason, count in block_reasons.most_common():
            wins_blk = sum(1 for r in blocked_v310 if r['blocked_by']==reason and r['res']=='win')
            losses_blk = sum(1 for r in blocked_v310 if r['blocked_by']==reason and r['res']=='loss')
            pnl_blk = sum(r['pnl'] or 0 for r in blocked_v310 if r['blocked_by']==reason)
            print(f"  {reason}: {count} trades | {wins_blk}W/{losses_blk}L | PnL ${pnl_blk:+.2f}")

        # Por régimen
        print()
        print("Por régimen detectado:")
        for regime in ['trending', 'ranging', 'uncertain']:
            rs = [r for r in results if r['regime']==regime]
            if not rs: continue
            n = len(rs); w = sum(1 for r in rs if r['res']=='win')
            p = sum(r['pnl'] or 0 for r in rs)
            print(f"  {regime:10s}: n={n:3d} | {w}W ({w/n*100:.0f}%) | PnL ${p:+.2f}")

    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
