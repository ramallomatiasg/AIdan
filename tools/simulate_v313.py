"""Simulación v3.13.0: bloquear todos los trades en regime=trending.
Hipótesis: trending regime es loser-only. Hoy 3/3 CALLs counter-HTF lost.
Histórico: 55 trending trades = -$109.11 (47% del volumen, 79% de las pérdidas).
"""
import sqlite3, os
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')

if not mt5.initialize(): raise SystemExit(1)

def detect_regime(candles, ma_fast, ma_slow, avg_range_pips):
    if len(candles) < 50: return 'uncertain'
    rc = [c['close'] for c in candles[-50:]]; rh = [c['high'] for c in candles[-50:]]; rl = [c['low'] for c in candles[-50:]]
    net = abs(rc[-1] - rc[0]) * 10000
    ds = net / max(avg_range_pips, 1.0)
    range_atrs = (max(rh) - min(rl)) * 10000 / max(avg_range_pips, 1.0)
    ma_score = abs(ma_fast - ma_slow) * 10000 / max(avg_range_pips, 1.0)
    score = 0
    if ds > 3.0: score += 1
    if range_atrs > 7.0: score += 1
    if ma_score > 0.6: score += 1
    if score >= 2: return 'trending'
    if score == 0 and ds < 1.5: return 'ranging'
    return 'uncertain'

def get_state(ts):
    rates = mt5.copy_rates_from('EURUSD', mt5.TIMEFRAME_M5, datetime.fromtimestamp(ts, tz=timezone.utc), 50)
    if rates is None or len(rates) < 50: return None
    candles = [{'open': r['open'], 'high': r['high'], 'low': r['low'], 'close': r['close']} for r in rates]
    closes = [c['close'] for c in candles]
    ma_fast = sum(closes[-9:]) / 9; ma_slow = sum(closes[-21:]) / 21
    trs = []
    for i in range(-14, 0):
        if i == -14: continue
        h, l = candles[i]['high'], candles[i]['low']
        prev_c = candles[i-1]['close']
        trs.append(max(h-l, abs(h-prev_c), abs(l-prev_c)) * 10000)
    return candles, ma_fast, ma_slow, sum(trs)/len(trs)

conn = sqlite3.connect(DB); c = conn.cursor()
c.execute("""SELECT t.id, t.direction, t.result, t.mt5_pnl, t.confidence, t.impact_score,
t.trigger_type, t.htf_bias, t.market_trend, t.avg_range_pips, t.hour_utc, t.created_at
FROM trade_archive t WHERE t.result IN ('win','loss') AND t.archived_at >= '2026-04-21'""")
all_trades = c.fetchall()
conn.close()

# Classify each
classified = []
for t in all_trades:
    tid, d, res, pnl, conf, imp, trig, htf, m5, atr, hr, ct = t
    try:
        dt = datetime.fromisoformat(ct.split('.')[0])
        ts = int((dt + timedelta(hours=3)).replace(tzinfo=timezone.utc).timestamp())
    except: continue
    s = get_state(ts)
    if not s: continue
    regime = detect_regime(*s)
    classified.append((tid, d, res, pnl or 0, conf, imp or 0, trig, htf or 'neutral', m5 or 'unknown', atr or 0, hr, regime))

mt5.shutdown()
print(f"Classified: {len(classified)} trades\n")

baseline_pnl = sum(t[3] for t in classified)
baseline_w = sum(1 for t in classified if t[2]=='win')
print(f"BASELINE: n={len(classified)} | {baseline_w}W ({baseline_w/len(classified)*100:.0f}%) | PnL ${baseline_pnl:+.2f}\n")

# v3.10/3.11/3.12 filters (current state without v3.13)
def passes_v312(t):
    tid, d, res, pnl, conf, imp, trig, htf, m5, atr, hr, regime = t
    # SIM A + counter-both
    if trig in ('structure', 'smc'):
        is_aligned = (d=='CALL' and htf=='bullish' and m5=='bullish') or (d=='PUT' and htf=='bearish' and m5=='bearish')
        is_counter_both = (d=='CALL' and htf=='bearish' and m5=='bearish') or (d=='PUT' and htf=='bullish' and m5=='bullish')
        if is_aligned or is_counter_both: return False
    # ATR floor
    if atr < 2.5: return False
    # Hour gate
    if hr is not None and int(hr) in (12, 14, 20): return False
    # Conf ceiling
    if conf >= 80: return False
    # Min conf with news bypass
    eff_min = 30 if (trig == 'news' and imp >= 55) else 60
    if conf < eff_min: return False
    return True

# v3.13.0 — also block trending regime
def passes_v313(t, news_imp_threshold=70):
    if not passes_v312(t): return False
    tid, d, res, pnl, conf, imp, trig, htf, m5, atr, hr, regime = t
    if regime == 'trending':
        # Allow only news with very high impact (potential reversal catalyst)
        if trig == 'news' and imp >= news_imp_threshold:
            return True
        return False
    return True

# Even stricter: block trending entirely (no news bypass either)
def passes_v313_strict(t):
    if not passes_v312(t): return False
    tid, d, res, pnl, conf, imp, trig, htf, m5, atr, hr, regime = t
    if regime == 'trending': return False
    return True

def stats(label, trades):
    if not trades: print(f"{label}: 0 trades"); return
    n = len(trades); w = sum(1 for t in trades if t[2]=='win')
    p = sum(t[3] for t in trades)
    gw = sum(t[3] for t in trades if t[3] > 0)
    gl = abs(sum(t[3] for t in trades if t[3] < 0))
    pf = gw/gl if gl > 0 else 0
    print(f"{label}: n={n:3d} | {w}W ({w/n*100:.0f}%) | PnL ${p:+8.2f} | PF {pf:.2f}")

v312 = [t for t in classified if passes_v312(t)]
stats("v3.12 (current)", v312)

v313 = [t for t in classified if passes_v313(t, 70)]
stats("v3.13 (block trending, allow news imp>=70)", v313)

v313_strict = [t for t in classified if passes_v313_strict(t)]
stats("v3.13 strict (block trending entirely)", v313_strict)

# Show what gets excluded
ex_v313 = [t for t in v312 if t not in v313]
print(f"\nv3.13 excluye {len(ex_v313)} trades adicionales vs v3.12:")
ex_pnl = sum(t[3] for t in ex_v313)
ex_w = sum(1 for t in ex_v313 if t[2]=='win')
print(f"  Excluded: {ex_w}W/{len(ex_v313)-ex_w}L | PnL ${ex_pnl:+.2f}")

# By regime
print("\n=== Distribución por regime de los excluidos ===")
from collections import Counter
regs = Counter(t[11] for t in ex_v313)
print(regs)
