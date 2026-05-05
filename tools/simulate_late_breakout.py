"""Simular distintos thresholds de 'breakout dist' para evitar entradas tardías."""
import sqlite3, os, re
from collections import defaultdict
db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db); c = conn.cursor()

# Get structure breakouts/breakdowns from trade_archive — parse dist from news_title
c.execute("""SELECT t.id, t.direction, t.result, t.mt5_pnl, t.confidence, t.news_title
FROM trade_archive t WHERE t.result IN ('win','loss') AND t.archived_at >= '2026-04-21'
AND t.trigger_type = 'structure'
AND (t.news_title LIKE '%Breakout sobre%' OR t.news_title LIKE '%Ruptura bajo%')""")
rows = c.fetchall()
conn.close()

# Parse dist
parsed = []
for r in rows:
    tid, d, res, pnl, conf, nt = r
    # Match "+6.2p)" or "-4.5p)" pattern at the end
    m = re.search(r'([+-]?\d+\.\d+)p\)', nt or '')
    if m:
        dist = abs(float(m.group(1)))
        parsed.append((tid, d, res, pnl or 0, conf, dist))

print(f"Parsed {len(parsed)} breakout trades with dist info\n")

# Bucket by dist
buckets = {'0-1p':[], '1-2p':[], '2-3p':[], '3-5p':[], '5-7p':[], '7-15p':[]}
for t in parsed:
    dist = t[5]
    if dist <= 1: bk = '0-1p'
    elif dist <= 2: bk = '1-2p'
    elif dist <= 3: bk = '2-3p'
    elif dist <= 5: bk = '3-5p'
    elif dist <= 7: bk = '5-7p'
    else: bk = '7-15p'
    buckets[bk].append(t)

print(f"{'dist bucket':12} {'n':4} {'WR':5} {'PnL':10}")
for bk in ['0-1p','1-2p','2-3p','3-5p','5-7p','7-15p']:
    ts = buckets[bk]
    if not ts: continue
    n = len(ts); w = sum(1 for x in ts if x[2]=='win')
    p = sum(x[3] for x in ts)
    print(f"{bk:12} {n:3d} {w/n*100:.0f}% ${p:+8.2f}")

# Now simulate: what if max_dist was X
print("\nSimulación: max_dist threshold")
for max_d in [2, 3, 4, 5, 7, 15]:
    kept = [t for t in parsed if t[5] <= max_d]
    excluded = [t for t in parsed if t[5] > max_d]
    if not kept: continue
    n = len(kept); w = sum(1 for x in kept if x[2]=='win')
    p = sum(x[3] for x in kept)
    ex_p = sum(x[3] for x in excluded)
    print(f"  max {max_d}p: keeps {n} | {w}W ({w/n*100:.0f}%) | PnL ${p:+.2f} | excluded ${ex_p:+.2f} ({len(excluded)} trades)")
