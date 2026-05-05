"""Simulación v3.11.0: 4 fixes data-driven sobre data histórica.
Valida el efecto combinado de:
1. ATR floor 2.5p
2. Hour gate (12, 14, 20 UTC = 09h, 11h, 17h AR)
3. min_conf 50
4. Conf ceiling >= 80
Plus continúa filtros v3.10.0 (universal SIM A + counter-both).
"""
import sqlite3, os
DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')

conn = sqlite3.connect(DB_PATH); c = conn.cursor()
c.execute("""SELECT id, direction, result, mt5_pnl, pips, confidence, trigger_type,
htf_bias, market_trend, rsi_at_entry, avg_range_pips, hour_utc
FROM trade_archive WHERE result IN ('win','loss') AND archived_at >= '2026-04-21'""")
trades = c.fetchall()
conn.close()

print(f"Total: {len(trades)} trades")
print()

baseline_pnl = sum(t[3] or 0 for t in trades)
baseline_n = len(trades)
baseline_w = sum(1 for t in trades if t[2]=='win')

# v3.10.0 filters
def passes_v310(t):
    tid, d, res, pnl, pips, conf, trig, htf, m5, rsi, atr, hr = t
    if trig in ('structure', 'smc'):
        is_aligned = (d=='CALL' and htf=='bullish' and m5=='bullish') or (d=='PUT' and htf=='bearish' and m5=='bearish')
        is_counter_both = (d=='CALL' and htf=='bearish' and m5=='bearish') or (d=='PUT' and htf=='bullish' and m5=='bullish')
        if is_aligned or is_counter_both: return False
    return True

# v3.11.0 = v3.10 + 4 new filters
def passes_v311(t):
    if not passes_v310(t): return False
    tid, d, res, pnl, pips, conf, trig, htf, m5, rsi, atr, hr = t
    # ATR floor
    if (atr or 0) < 2.5: return False
    # Hour gate
    if hr is not None and int(hr) in (12, 14, 20): return False
    # Conf ceiling
    if (conf or 0) >= 80: return False
    # Min conf 50 (down from 60)
    if (conf or 0) < 50: return False  # Note: in real impl, conf<50 would NOW pass since min is 50
    return True

def stats(label, kept):
    n = len(kept); w = sum(1 for t in kept if t[2]=='win')
    p = sum(t[3] or 0 for t in kept)
    gw = sum(t[3] for t in kept if (t[3] or 0)>0)
    gl = abs(sum(t[3] for t in kept if (t[3] or 0)<0))
    pf = gw/gl if gl > 0 else 0
    print(f"{label:30s}: n={n:3d} | {w}W ({w/max(1,n)*100:.0f}%) | PnL ${p:+8.2f} | PF {pf:.2f}")

stats("BASELINE (todos)", trades)

v310_kept = [t for t in trades if passes_v310(t)]
stats("v3.10.0 (universal SIM A)", v310_kept)

v311_kept = [t for t in trades if passes_v311(t)]
stats("v3.11.0 (con 4 fixes)", v311_kept)

print()
print("Filtros individuales sobre v3.10.0 base:")

# Each filter alone
def passes_atr_only(t):
    if not passes_v310(t): return False
    return (t[10] or 0) >= 2.5

def passes_hour_only(t):
    if not passes_v310(t): return False
    return t[11] is None or int(t[11]) not in (12, 14, 20)

def passes_conf_ceil_only(t):
    if not passes_v310(t): return False
    return (t[5] or 0) < 80

def passes_minconf_50(t):
    if not passes_v310(t): return False
    # If min was 50, then conf>=50 passes. If min was 60, conf 50-59 was blocked. Now they pass.
    # Simulating LOWERING min_conf: trades with conf in [50, 60) ALSO pass now.
    return (t[5] or 0) >= 50

stats("v3.10 + ATR floor 2.5", [t for t in trades if passes_atr_only(t)])
stats("v3.10 + hour gate", [t for t in trades if passes_hour_only(t)])
stats("v3.10 + conf ceil 80", [t for t in trades if passes_conf_ceil_only(t)])
stats("v3.10 + min_conf 50 (now)", [t for t in trades if passes_minconf_50(t)])

# What conf<50 brings if we LOWER threshold (currently blocked by min_conf=60)
print()
print("Detalle: bucket conf <50 (que con min=50 SE TOMARIA pero con min=60 NO):")
sub_50 = [t for t in trades if (t[5] or 0) < 50 and passes_v310(t)]
stats("  conf <50 (in v3.10 universe)", sub_50)
sub_50_60 = [t for t in trades if 50 <= (t[5] or 0) < 60 and passes_v310(t)]
stats("  conf 50-59 (in v3.10 universe)", sub_50_60)

# Summary delta
v311_pnl = sum(t[3] or 0 for t in v311_kept)
v310_pnl = sum(t[3] or 0 for t in v310_kept)
print()
print("="*60)
print(f"DELTA v3.11.0 vs v3.10.0: ${v311_pnl - v310_pnl:+.2f}")
print(f"DELTA v3.11.0 vs baseline: ${v311_pnl - baseline_pnl:+.2f}")

# v3.11 SIN cambio #3 (mantiene min_conf=60)
def passes_v311_no3(t):
    if not passes_v310(t): return False
    if (t[10] or 0) < 2.5: return False  # ATR floor
    if t[11] is not None and int(t[11]) in (12, 14, 20): return False  # hour gate
    if (t[5] or 0) >= 80: return False  # conf ceiling
    if (t[5] or 0) < 60: return False  # KEEP min_conf=60
    return True

v311_no3_kept = [t for t in trades if passes_v311_no3(t)]
print()
stats("v3.11 SIN cambio #3 (min=60)", v311_no3_kept)
v311_no3_pnl = sum(t[3] or 0 for t in v311_no3_kept)
print(f"DELTA v3.11_no3 vs v3.10: ${v311_no3_pnl - v310_pnl:+.2f}")
print(f"DELTA v3.11_no3 vs baseline: ${v311_no3_pnl - baseline_pnl:+.2f}")
