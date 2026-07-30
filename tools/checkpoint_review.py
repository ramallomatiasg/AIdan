"""Checkpoint review: full weekly stats for Friday decision."""
import sqlite3, os, sys, requests
sys.stdout.reconfigure(encoding='utf-8')
db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db)
cur = conn.cursor()

print("=" * 75)
print("CHECKPOINT VIERNES 22 MAY")
print("=" * 75)

# Balance / estado
try:
    s = requests.get('http://localhost:8000/mt5/status', timeout=3).json()['data']
    print(f"\nBalance:    ${s['account']['balance']:.2f}")
    print(f"Daily PnL:  ${s['daily_pnl']:+.2f}")
    print(f"Posiciones: {s['positions']}")
except Exception as e:
    print(f"AIdan no responde: {e}")

print("\n=== STATS DIARIOS ===")
days = [('2026-05-18','Lun'), ('2026-05-19','Mar'), ('2026-05-20','Mie'), ('2026-05-21','Jue'), ('2026-05-22','Vie')]
total_n, total_w, total_pnl = 0, 0, 0
for date, label in days:
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN result='win' THEN 1 ELSE 0 END), ROUND(SUM(mt5_pnl),2) FROM trade_archive WHERE date(created_at)=? AND mt5_pnl IS NOT NULL", (date,))
    na, wa, sa = cur.fetchone()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN status='auto_win' THEN 1 ELSE 0 END), ROUND(SUM(mt5_pnl),2) FROM auto_strategies WHERE date(created_at)=? AND mt5_pnl IS NOT NULL AND status IN ('auto_win','auto_loss')", (date,))
    ns, ws, ss = cur.fetchone()
    n = (na or 0) + (ns or 0)
    w = (wa or 0) + (ws or 0)
    pnl = (sa or 0) + (ss or 0)
    total_n += n
    total_w += w
    total_pnl += pnl
    if n > 0:
        wr = w * 100 / n
        print(f"  {label} {date}: {n:>3d}t | WR {wr:>5.1f}% | PnL ${pnl:>+7.2f}")
    else:
        print(f"  {label} {date}: 0 trades")

if total_n:
    print(f"\nTOTAL semana   : {total_n}t | WR {total_w*100/total_n:.1f}% | PnL ${total_pnl:+.2f}")
    print(f"Promedio/dia   : {total_n/5:.1f} trades, ${total_pnl/5:+.2f}/dia")

# Pre/post v3.32.0
print("\n=== PRE v3.32.0 vs POST v3.32.0 ===")
cur.execute("SELECT mt5_pnl FROM trade_archive WHERE date(created_at) < '2026-05-20' AND mt5_pnl IS NOT NULL")
pre_pnls = [r[0] for r in cur.fetchall() if r[0] is not None]
def stats(pnls):
    if not pnls: return None
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    return {
        'n': len(pnls),
        'aw': sum(wins)/len(wins) if wins else 0,
        'al': sum(losses)/len(losses) if losses else 0,
        'wr': len(wins)*100/len(pnls),
        'avg': sum(pnls)/len(pnls),
        'pf': sum(wins) / abs(sum(losses)) if losses else 0,
    }
s_pre = stats(pre_pnls)
print(f"  Pre ({s_pre['n']}t): avg_win ${s_pre['aw']:+.2f}, avg_loss ${s_pre['al']:+.2f}, WR {s_pre['wr']:.1f}%, PF {s_pre['pf']:.2f}, avg/trade ${s_pre['avg']:+.2f}")

cur.execute("SELECT mt5_pnl FROM trade_archive WHERE date(created_at) >= '2026-05-20' AND mt5_pnl IS NOT NULL")
post_arc = [r[0] for r in cur.fetchall() if r[0] is not None]
cur.execute("SELECT mt5_pnl FROM auto_strategies WHERE date(created_at) >= '2026-05-20' AND mt5_pnl IS NOT NULL AND status IN ('auto_win','auto_loss')")
post_as = [r[0] for r in cur.fetchall() if r[0] is not None]
post_pnls = post_arc + post_as
s_post = stats(post_pnls)
if s_post:
    print(f"  Post ({s_post['n']}t): avg_win ${s_post['aw']:+.2f}, avg_loss ${s_post['al']:+.2f}, WR {s_post['wr']:.1f}%, PF {s_post['pf']:.2f}, avg/trade ${s_post['avg']:+.2f}")
    print(f"  Cambio avg_win: {s_post['aw']/s_pre['aw'] if s_pre['aw'] else 0:.2f}x  | avg_loss: {s_post['al']/s_pre['al'] if s_pre['al'] else 0:.2f}x")

# Horas UTC esta semana
print("\n=== HORAS UTC SEMANA (confirmar tarde mala) ===")
hours = {}
cur.execute("SELECT hour_utc, mt5_pnl FROM trade_archive WHERE date(created_at) >= '2026-05-18' AND mt5_pnl IS NOT NULL")
for h, p in cur.fetchall():
    if h is None: continue
    if h not in hours: hours[h] = [0, 0]
    hours[h][0] += 1
    hours[h][1] += p
cur.execute("SELECT CAST(strftime('%H', datetime(created_at, '+3 hours')) AS INTEGER), mt5_pnl FROM auto_strategies WHERE date(created_at) >= '2026-05-18' AND mt5_pnl IS NOT NULL AND status IN ('auto_win','auto_loss')")
for h, p in cur.fetchall():
    if h is None: continue
    if h not in hours: hours[h] = [0, 0]
    hours[h][0] += 1
    hours[h][1] += p
for h, (n, p) in sorted(hours.items(), key=lambda x: x[1][1]):
    if n < 2: continue
    marker = 'BAD' if p < -5 else ('GOOD' if p > 3 else '~')
    print(f"  {h:>2d}h UTC: {n:>3d}t  ${p:>+7.2f}  {marker}")

# Tracks
print("\n=== TRACK STATUS ACUMULADO ===")
tracks = {'M5': "trigger_type NOT LIKE 'm15_%' AND trigger_type NOT LIKE 'h1_%'",
          'M15': "trigger_type LIKE 'm15_%'",
          'H1': "trigger_type LIKE 'h1_%'"}
for name, where in tracks.items():
    cur.execute(f"SELECT COUNT(*), SUM(CASE WHEN result='win' THEN 1 ELSE 0 END), ROUND(SUM(mt5_pnl),2), ROUND(SUM(CASE WHEN mt5_pnl>0 THEN mt5_pnl ELSE 0 END),2), ROUND(SUM(CASE WHEN mt5_pnl<0 THEN -mt5_pnl ELSE 0 END),2) FROM trade_archive WHERE result IN ('win','loss') AND mt5_pnl IS NOT NULL AND {where}")
    a = cur.fetchone()
    cur.execute(f"SELECT COUNT(*), SUM(CASE WHEN status='auto_win' THEN 1 ELSE 0 END), ROUND(SUM(mt5_pnl),2), ROUND(SUM(CASE WHEN mt5_pnl>0 THEN mt5_pnl ELSE 0 END),2), ROUND(SUM(CASE WHEN mt5_pnl<0 THEN -mt5_pnl ELSE 0 END),2) FROM auto_strategies WHERE mt5_pnl IS NOT NULL AND status IN ('auto_win','auto_loss') AND {where}")
    l = cur.fetchone()
    n = (a[0] or 0) + (l[0] or 0)
    w = (a[1] or 0) + (l[1] or 0)
    pnl = (a[2] or 0) + (l[2] or 0)
    gw = (a[3] or 0) + (l[3] or 0)
    gl = (a[4] or 0) + (l[4] or 0)
    pf = gw / gl if gl > 0 else 0
    wr = w * 100 / n if n else 0
    print(f"  {name:5s}: {n:>3d}t | WR {wr:>5.1f}% | PF {pf:>4.2f} | PnL ${pnl:>+7.2f}")

# Meta-optimizer
print("\n=== META-OPTIMIZER STATE ===")
try:
    r = requests.get('http://localhost:8000/meta-optimization-status', timeout=3).json()
    print(f"  Counts: {r['counts_by_status']}")
    print(f"  Baseline PF last 50: {r['baseline_last_50']['pf']}")
except Exception as e:
    print(f"  error: {e}")

print("\n=== BALANCE EVOLUTION ===")
print("  Lunes 18 apertura: ~$830")
try:
    s = requests.get('http://localhost:8000/mt5/status', timeout=3).json()['data']
    print(f"  Viernes 22 ahora: ${s['account']['balance']:.2f}")
    print(f"  Cambio semana:    ${s['account']['balance'] - 830:+.2f}")
except: pass

conn.close()
