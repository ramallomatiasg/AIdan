"""¿Qué tienen de especial los trades con conf<50 que ganan 62% del tiempo?"""
import sqlite3, os, json
from collections import Counter

db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db); c = conn.cursor()

# Get conf<50 trades
c.execute("""SELECT t.id, t.direction, t.result, t.mt5_pnl, t.pips, t.confidence, t.impact_score,
t.trigger_type, t.setup_type, t.htf_bias, t.market_trend, t.trend_strength,
t.rsi_at_entry, t.avg_range_pips, t.session, t.hour_utc, t.created_at,
t.entry_price, t.stop_loss, t.take_profit, t.exit_price, t.sl_pips, t.tp_pips,
t.entry_context, t.news_title, s.candles_snapshot
FROM trade_archive t LEFT JOIN auto_strategies s ON t.strategy_id = s.id
WHERE t.result IN ('win','loss') AND t.archived_at >= '2026-04-21'
AND t.confidence < 50
ORDER BY t.confidence""")
sub50 = c.fetchall()

# Get conf >=50 wins for comparison
c.execute("""SELECT t.id, t.direction, t.result, t.mt5_pnl, t.confidence, t.trigger_type,
t.htf_bias, t.market_trend, t.rsi_at_entry, t.avg_range_pips, t.session, t.hour_utc,
t.entry_context, t.news_title
FROM trade_archive t
WHERE t.result IN ('win','loss') AND t.archived_at >= '2026-04-21'
AND t.confidence >= 50""")
above50 = c.fetchall()
conn.close()

print(f"=== TRADES CON CONF <50 (n={len(sub50)}) ===")
print()
print(f"{'id':4} {'d':4} {'res':4} {'pnl':6} {'pips':5} {'conf':4} {'imp':4} {'trig':10} {'setup':20} {'htf':8} {'m5':8} {'tstr':8} {'rsi':5} {'atr':5} {'sess':8} {'hr':3}")
for r in sub50:
    tid, d, res, pnl, pips, conf, imp = r[0], r[1], r[2], r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0
    trig, setup = r[7] or '?', (r[8] or '?')[:20]
    htf, m5 = (r[9] or '?')[:8], (r[10] or '?')[:8]
    tstr = (r[11] or '?')[:8]
    rsi = r[12] or 0
    atr = r[13] or 0
    sess = (r[14] or '?')[:8]
    hr = r[15]
    print(f"#{tid:3d} {d:4s} {res:4s} ${pnl:+5.2f} {pips:+4.1f}p {conf:3.0f} {imp:3.0f} {trig:10s} {setup:20s} {htf:8s} {m5:8s} {tstr:8s} {rsi:4.1f} {atr:4.1f}p {sess:8s} {hr if hr else '-'}")

# Wins vs losses among conf<50
wins = [r for r in sub50 if r[2]=='win']
losses = [r for r in sub50 if r[2]=='loss']
print(f"\n{len(wins)} wins | {len(losses)} losses | PnL ${sum(r[3] or 0 for r in sub50):+.2f}")

# Check news title for the wins — was it a specific event type?
print("\n=== News titles de los wins conf<50 ===")
for r in wins:
    nt = r[24] or ''
    print(f"  #{r[0]} {r[1]} ${r[3]:+.2f}: {nt[:80]}")

print("\n=== News titles de los losses conf<50 ===")
for r in losses:
    nt = r[24] or ''
    print(f"  #{r[0]} {r[1]} ${r[3]:+.2f}: {nt[:80]}")

# What makes the wins win?
print("\n=== CARACTERISTICAS COMUNES DE LOS WINS (conf<50) ===")
def summarize(records, label):
    if not records: return
    print(f"\n{label} ({len(records)}):")
    # trigger_type
    trigs = Counter(r[7] for r in records)
    print(f"  trigger: {dict(trigs)}")
    # setup_type
    setups = Counter(r[8] for r in records)
    print(f"  setup: {dict(setups)}")
    # direction
    dirs = Counter(r[1] for r in records)
    print(f"  dir: {dict(dirs)}")
    # htf vs direction alignment
    aligns = Counter()
    for r in records:
        d, htf, m5 = r[1], r[9], r[10]
        if (d=='CALL' and htf=='bullish' and m5=='bullish') or (d=='PUT' and htf=='bearish' and m5=='bearish'):
            aligns['fully-aligned'] += 1
        elif (d=='CALL' and htf=='bearish' and m5=='bearish') or (d=='PUT' and htf=='bullish' and m5=='bullish'):
            aligns['counter-both'] += 1
        elif ((d=='CALL' and m5=='bullish') or (d=='PUT' and m5=='bearish')) and ((d=='CALL' and htf!='bullish') or (d=='PUT' and htf!='bearish')):
            aligns['M5-only'] += 1
        elif ((d=='CALL' and htf=='bullish') or (d=='PUT' and htf=='bearish')) and ((d=='CALL' and m5!='bullish') or (d=='PUT' and m5!='bearish')):
            aligns['HTF-only'] += 1
        else:
            aligns['other'] += 1
    print(f"  alignment: {dict(aligns)}")
    # RSI ranges
    rsi_b = Counter()
    for r in records:
        rsi = r[12] or 50
        if rsi < 35: rsi_b['<35'] += 1
        elif rsi < 45: rsi_b['35-44'] += 1
        elif rsi < 55: rsi_b['45-54'] += 1
        elif rsi < 65: rsi_b['55-64'] += 1
        else: rsi_b['65+'] += 1
    print(f"  RSI: {dict(rsi_b)}")
    # ATR
    atrs = [r[13] or 0 for r in records]
    print(f"  ATR: avg={sum(atrs)/len(atrs):.1f}p, range {min(atrs):.1f}-{max(atrs):.1f}")
    # Hour
    hrs = Counter(r[15] for r in records if r[15] is not None)
    print(f"  Hour UTC: {dict(hrs)}")
    # Session
    sess = Counter(r[14] for r in records)
    print(f"  Session: {dict(sess)}")
    # impact_score (from news)
    imps = [r[6] or 0 for r in records]
    if any(imps): print(f"  Impact score avg: {sum(imps)/len(imps):.1f}")

summarize(wins, "WINS conf<50")
summarize(losses, "LOSSES conf<50")

# Compare with conf>=50 wins (baseline)
above50_wins = [r for r in above50 if r[2]=='win']
print(f"\n=== BASELINE: WINS con conf>=50 (n={len(above50_wins)}) ===")
trigs = Counter(r[5] for r in above50_wins)
print(f"  trigger distribution: {dict(trigs)}")
dirs = Counter(r[1] for r in above50_wins)
print(f"  dir distribution: {dict(dirs)}")
rsis = [r[8] or 50 for r in above50_wins]
print(f"  avg RSI: {sum(rsis)/len(rsis):.1f}")

# So what's UNIQUE about the conf<50 wins?
print("\n=== HALLAZGO: ¿Qué hace ESPECIALES estos wins? ===")
print("Comparamos %trigger, %dir entre wins<50 vs wins>=50")
def pct(records, key_fn):
    if not records: return {}
    total = len(records)
    counts = Counter(key_fn(r) for r in records)
    return {k: f"{v/total*100:.0f}%" for k, v in counts.items()}

trig_lt50 = pct(wins, lambda r: r[7])
trig_ge50 = pct(above50_wins, lambda r: r[5])
print(f"  Trigger %:  conf<50 wins: {trig_lt50}  vs conf>=50 wins: {trig_ge50}")
