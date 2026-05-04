"""Profundizar en por qué las trades de regime=trending pierden tanto.
Mira los 53 trades clasificados trending y desglosa por setup, alineación, dirección."""
import sqlite3, os
from datetime import datetime, timezone, timedelta

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit(1)

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')

if not mt5.initialize(): raise SystemExit(1)

# Re-classify (same logic as simulate_regime.py)
def detect_regime(candles, ma_fast, ma_slow, avg_range_pips):
    if len(candles) < 50: return 'uncertain', 0
    recent = candles[-50:]
    rc = [c['close'] for c in recent]
    rh = [c['high'] for c in recent]; rl = [c['low'] for c in recent]
    net_pips = abs(rc[-1] - rc[0]) * 10000
    ds = net_pips / max(avg_range_pips, 1.0)
    range_atrs = (max(rh) - min(rl)) * 10000 / max(avg_range_pips, 1.0)
    ma_score = abs(ma_fast - ma_slow) * 10000 / max(avg_range_pips, 1.0)
    score = 0
    if ds > 3.0: score += 1
    if range_atrs > 7.0: score += 1
    if ma_score > 0.6: score += 1
    if score >= 2: return 'trending', score
    if score == 0 and ds < 1.5: return 'ranging', score
    return 'uncertain', score


def get_state(ts):
    rates = mt5.copy_rates_from('EURUSD', mt5.TIMEFRAME_M5,
        datetime.fromtimestamp(ts, tz=timezone.utc), 50)
    if rates is None or len(rates) < 50: return None
    candles = [{'open': r['open'], 'high': r['high'], 'low': r['low'], 'close': r['close']} for r in rates]
    closes = [c['close'] for c in candles]
    ma_fast = sum(closes[-9:]) / 9
    ma_slow = sum(closes[-21:]) / 21
    trs = []
    for i in range(-14, 0):
        if i == -14: continue
        h, l = candles[i]['high'], candles[i]['low']
        prev_c = candles[i-1]['close']
        trs.append(max(h-l, abs(h-prev_c), abs(l-prev_c)) * 10000)
    return candles, ma_fast, ma_slow, sum(trs)/len(trs)


try:
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("""SELECT t.id, t.direction, t.result, t.mt5_pnl, t.pips, t.trigger_type,
        t.htf_bias, t.market_trend, t.created_at, t.setup_type
    FROM trade_archive t
    WHERE t.result IN ('win','loss') AND t.archived_at >= '2026-04-21'""")
    trades = c.fetchall()
    conn.close()

    trending_trades = []
    for t in trades:
        tid, d, res, pnl, pips, trig, htf, m5, ct, setup = t
        try:
            dt = datetime.fromisoformat(ct.split('.')[0])
            ts = int((dt + timedelta(hours=3)).replace(tzinfo=timezone.utc).timestamp())
        except: continue
        s = get_state(ts)
        if not s: continue
        regime, score = detect_regime(*s)
        if regime == 'trending':
            trending_trades.append({
                'id': tid, 'd': d, 'res': res, 'pnl': pnl or 0, 'pips': pips,
                'trig': trig, 'htf': htf or 'neutral', 'm5': m5 or 'unknown',
                'setup': setup or '', 'score': score,
            })

    print(f"=== {len(trending_trades)} TRENDING TRADES ===")
    pnl_total = sum(t['pnl'] for t in trending_trades)
    wins = sum(1 for t in trending_trades if t['res']=='win')
    print(f"WR: {wins/len(trending_trades)*100:.0f}% | PnL ${pnl_total:+.2f}\n")

    # By trigger
    print("Por TRIGGER:")
    triggers = {}
    for t in trending_trades:
        triggers.setdefault(t['trig'], []).append(t)
    for trig, ts in sorted(triggers.items(), key=lambda x: -len(x[1])):
        n = len(ts); w = sum(1 for t in ts if t['res']=='win')
        p = sum(t['pnl'] for t in ts)
        print(f"  {trig:12s}: n={n:3d} | {w}W ({w/n*100:.0f}%) | PnL ${p:+.2f}")

    # By alignment
    print("\nPor ALINEACION en regime trending:")
    cats = {'aligned': [], 'M5-only': [], 'HTF-only': [], 'counter-both': [], 'other': []}
    for t in trending_trades:
        d, htf, m5 = t['d'], t['htf'], t['m5']
        with_htf = (d=='CALL' and htf=='bullish') or (d=='PUT' and htf=='bearish')
        with_m5 = (d=='CALL' and m5=='bullish') or (d=='PUT' and m5=='bearish')
        against_htf = (d=='CALL' and htf=='bearish') or (d=='PUT' and htf=='bullish')
        against_m5 = (d=='CALL' and m5=='bearish') or (d=='PUT' and m5=='bullish')
        if with_htf and with_m5: cats['aligned'].append(t)
        elif with_m5 and against_htf: cats['M5-only'].append(t)
        elif with_htf and against_m5: cats['HTF-only'].append(t)
        elif against_htf and against_m5: cats['counter-both'].append(t)
        else: cats['other'].append(t)
    for cat, ts in cats.items():
        if not ts: continue
        n = len(ts); w = sum(1 for t in ts if t['res']=='win')
        p = sum(t['pnl'] for t in ts)
        print(f"  {cat:14s}: n={n:3d} | {w}W ({w/n*100:.0f}%) | PnL ${p:+.2f}")

    # By setup_type pattern
    print("\nPor SETUP type:")
    setups = {}
    for t in trending_trades:
        s = t['setup'][:20] if t['setup'] else 'unknown'
        setups.setdefault(s, []).append(t)
    for s, ts in sorted(setups.items(), key=lambda x: -sum(t['pnl'] for t in x[1])):
        if len(ts) < 2: continue
        n = len(ts); w = sum(1 for t in ts if t['res']=='win')
        p = sum(t['pnl'] for t in ts)
        print(f"  {s:25s}: n={n:3d} | {w}W ({w/n*100:.0f}%) | PnL ${p:+.2f}")

    # Detail of worst losers
    print("\n10 PEORES trades en trending:")
    worst = sorted(trending_trades, key=lambda x: x['pnl'])[:10]
    for t in worst:
        print(f"  #{t['id']} {t['d']} {t['trig']:12s} {t['setup'][:20]:20s} htf={t['htf']:8s} m5={t['m5']:8s} -> ${t['pnl']:+.2f}")

finally:
    mt5.shutdown()
