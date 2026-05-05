"""Análisis profundo de patrones win/loss en AIdan.
Busca correlaciones que no detectamos antes."""
import sqlite3, os, json
from collections import defaultdict
from datetime import datetime

db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db); c = conn.cursor()

c.execute("""SELECT t.id, t.direction, t.result, t.mt5_pnl, t.pips, t.confidence,
t.trigger_type, t.setup_type, t.htf_bias, t.market_trend, t.trend_strength,
t.rsi_at_entry, t.avg_range_pips, t.session, t.hour_utc, t.created_at,
t.entry_price, t.stop_loss, t.take_profit, t.exit_price, t.sl_pips, t.tp_pips,
t.entry_context, s.mt5_closed_at, s.mt5_fill_price
FROM trade_archive t LEFT JOIN auto_strategies s ON t.strategy_id = s.id
WHERE t.result IN ('win','loss') AND t.archived_at >= '2026-04-21'""")
trades = c.fetchall()
conn.close()

print(f"Loaded {len(trades)} trades\n")

def parse_trade(r):
    tid, d, res, pnl, pips, conf, trig, setup, htf, m5, ts, rsi, atr, sess, hr, ct, ep, sl, tp, xp, sl_p, tp_p, ectx, closed_at, fill_p = r
    ctx = json.loads(ectx) if ectx else {}
    duration_min = 0
    try:
        if closed_at and ct:
            ct_dt = datetime.fromisoformat(ct.split('.')[0])
            cl_dt = datetime.fromisoformat(closed_at.split('.')[0])
            duration_min = (cl_dt - ct_dt).total_seconds() / 60
    except: pass
    return {
        'id': tid, 'd': d, 'res': res, 'pnl': pnl or 0, 'pips': pips or 0, 'conf': conf,
        'trig': trig, 'setup': setup or '', 'htf': htf or 'neutral', 'm5': m5 or 'unknown',
        'trend_str': ts or '?', 'rsi': rsi or 50, 'atr': atr or 0, 'session': sess or '?',
        'hour': hr, 'momentum': ctx.get('momentum', '?'), 'volatility': ctx.get('volatility', '?'),
        'sl_p': sl_p or 0, 'tp_p': tp_p or 0,
        'duration_min': duration_min, 'fill_p': fill_p or ep,
    }

trades_p = [parse_trade(r) for r in trades]

# Aggregator helper
def stats(trades_subset, label):
    if not trades_subset: return
    n = len(trades_subset)
    w = sum(1 for t in trades_subset if t['res']=='win')
    p = sum(t['pnl'] for t in trades_subset)
    return f"n={n:3d} | {w}W ({w/n*100:.0f}%) | PnL ${p:+7.2f}"

# ============================================
# HALLAZGO 1: DURATION DE TRADES
# ============================================
print("="*70)
print("HALLAZGO 1: ¿La velocidad del cierre dice algo?")
print("="*70)
durations = {'<2min (instant SL)': [], '2-5min': [], '5-15min': [], '15-30min': [], '30-60min': [], '>60min': []}
for t in trades_p:
    d = t['duration_min']
    if d < 2: durations['<2min (instant SL)'].append(t)
    elif d < 5: durations['2-5min'].append(t)
    elif d < 15: durations['5-15min'].append(t)
    elif d < 30: durations['15-30min'].append(t)
    elif d < 60: durations['30-60min'].append(t)
    else: durations['>60min'].append(t)
for label, ts in durations.items():
    s = stats(ts, label)
    if s: print(f"  {label:28s}: {s}")

# ============================================
# HALLAZGO 2: RSI EXTREMES (más granular)
# ============================================
print("\n" + "="*70)
print("HALLAZGO 2: RSI buckets fine-grained")
print("="*70)
rsi_buckets = defaultdict(list)
for t in trades_p:
    rsi = t['rsi']
    bk = f"{int(rsi//5)*5}-{int(rsi//5)*5+4}"
    rsi_buckets[bk].append(t)
for bk in sorted(rsi_buckets.keys(), key=lambda x: int(x.split('-')[0])):
    ts = rsi_buckets[bk]
    if len(ts) < 3: continue
    s = stats(ts, bk)
    print(f"  RSI {bk:8s}: {s}")

# ============================================
# HALLAZGO 3: Setup type + dir specific
# ============================================
print("\n" + "="*70)
print("HALLAZGO 3: ¿Qué setup_type específicos ganan?")
print("="*70)
setup_d = defaultdict(list)
for t in trades_p:
    s = t['setup'] or 'unknown'
    setup_d[f"{s}/{t['d']}"].append(t)
for k, ts in sorted(setup_d.items(), key=lambda x: -sum(t['pnl'] for t in x[1])):
    if len(ts) < 3: continue
    s = stats(ts, k)
    p = sum(t['pnl'] for t in ts)
    flag = '★' if p > 0 else ''
    print(f"  {k:35s}: {s} {flag}")

# ============================================
# HALLAZGO 4: PnL distribution — cuántos wins grandes vs chicos
# ============================================
print("\n" + "="*70)
print("HALLAZGO 4: Distribución de PnL")
print("="*70)
buckets = {'-10+': 0, '-5..-10': 0, '-3..-5': 0, '-1..-3': 0, '0..-1': 0,
           '0..1': 0, '1..3': 0, '3..5': 0, '5..10': 0, '10+': 0}
for t in trades_p:
    p = t['pnl']
    if p <= -10: buckets['-10+'] += 1
    elif p <= -5: buckets['-5..-10'] += 1
    elif p <= -3: buckets['-3..-5'] += 1
    elif p <= -1: buckets['-1..-3'] += 1
    elif p < 0: buckets['0..-1'] += 1
    elif p < 1: buckets['0..1'] += 1
    elif p < 3: buckets['1..3'] += 1
    elif p < 5: buckets['3..5'] += 1
    elif p < 10: buckets['5..10'] += 1
    else: buckets['10+'] += 1
for k, n in buckets.items():
    bar = '█' * n
    print(f"  ${k:9s}: {n:3d} {bar}")

# ============================================
# HALLAZGO 5: ¿Volatilidad importa? — ATR buckets
# ============================================
print("\n" + "="*70)
print("HALLAZGO 5: ATR buckets (volatilidad al entry)")
print("="*70)
atr_buckets = defaultdict(list)
for t in trades_p:
    atr = t['atr']
    if atr < 2: bk = 'A: <2 (deadzone)'
    elif atr < 3: bk = 'B: 2-3 (low)'
    elif atr < 4: bk = 'C: 3-4 (mid-low)'
    elif atr < 5: bk = 'D: 4-5 (normal)'
    elif atr < 6: bk = 'E: 5-6 (mid-high)'
    elif atr < 8: bk = 'F: 6-8 (high)'
    else: bk = 'G: >8 (extreme)'
    atr_buckets[bk].append(t)
for bk in sorted(atr_buckets.keys()):
    ts = atr_buckets[bk]
    if len(ts) < 3: continue
    s = stats(ts, bk)
    avg_pip = sum(t['pips'] for t in ts)/len(ts)
    print(f"  {bk:22s}: {s} | avg pips {avg_pip:+.1f}")

# ============================================
# HALLAZGO 6: ¿Hora del día específicas?
# ============================================
print("\n" + "="*70)
print("HALLAZGO 6: Hour × dirección — patrones específicos")
print("="*70)
hour_dir = defaultdict(list)
for t in trades_p:
    if t['hour'] is None: continue
    hour_ar = (int(t['hour']) - 3) % 24
    hour_dir[(hour_ar, t['d'])].append(t)
for (h, d), ts in sorted(hour_dir.items()):
    if len(ts) < 3: continue
    s = stats(ts, '')
    p = sum(t['pnl'] for t in ts)
    flag = '★' if p > 0 else '✗' if p < -10 else ''
    print(f"  {h:02d}h AR {d:4s}: {s} {flag}")

# ============================================
# HALLAZGO 7: Wins grandes — ¿qué tienen en común?
# ============================================
print("\n" + "="*70)
print("HALLAZGO 7: TOP 10 WINS — ¿qué hicimos bien?")
print("="*70)
top_wins = sorted([t for t in trades_p if t['pnl'] > 0], key=lambda x: -x['pnl'])[:10]
print(f"  {'id':4} {'d':4} {'pips':5} {'conf':4} {'trig':10} {'htf':8} {'m5':8} {'rsi':5} {'atr':4} {'mom':5} {'sess':8} {'dur':6}")
for t in top_wins:
    print(f"  #{t['id']:3d} {t['d']:4s} {t['pips']:+4.1f}p {t['conf']:3.0f} {t['trig']:10s} {t['htf']:8s} {t['m5']:8s} {t['rsi']:4.1f} {t['atr']:3.1f}p {t['momentum']:5s} {t['session']:8s} {t['duration_min']:.0f}m")

print()
print("HALLAZGO 8: TOP 10 LOSSES — ¿qué hicimos mal?")
print("="*70)
top_losses = sorted([t for t in trades_p if t['pnl'] < 0], key=lambda x: x['pnl'])[:10]
for t in top_losses:
    print(f"  #{t['id']:3d} {t['d']:4s} {t['pips']:+4.1f}p {t['conf']:3.0f} {t['trig']:10s} {t['htf']:8s} {t['m5']:8s} {t['rsi']:4.1f} {t['atr']:3.1f}p {t['momentum']:5s} {t['session']:8s} {t['duration_min']:.0f}m")

# ============================================
# HALLAZGO 9: confidence — ¿alguna correlación válida?
# ============================================
print("\n" + "="*70)
print("HALLAZGO 9: Confidence buckets — recheck post-fixes")
print("="*70)
conf_b = defaultdict(list)
for t in trades_p:
    c = t['conf']
    if c < 50: bk = '<50'
    elif c < 60: bk = '50-59'
    elif c < 70: bk = '60-69'
    elif c < 80: bk = '70-79'
    elif c < 90: bk = '80-89'
    else: bk = '90+'
    conf_b[bk].append(t)
for bk in ['<50','50-59','60-69','70-79','80-89','90+']:
    ts = conf_b.get(bk, [])
    if len(ts) < 3: continue
    s = stats(ts, bk)
    print(f"  conf {bk:6s}: {s}")
