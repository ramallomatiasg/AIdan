"""Simulación de propuestas de mejora sobre data histórica."""
import sqlite3, os

db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db); c = conn.cursor()

c.execute("""SELECT id, direction, result, pips, sl_pips, tp_pips, mt5_pnl, avg_range_pips, confidence
FROM trade_archive WHERE result IN ('win','loss') AND archived_at >= '2026-04-21'
AND avg_range_pips > 0""")
trades = c.fetchall()

baseline_pnl = sum(t[6] or 0 for t in trades)
baseline_n = len(trades)
baseline_wins = sum(1 for t in trades if t[2]=='win')
baseline_wr = baseline_wins/baseline_n*100
baseline_gw = sum(t[6] for t in trades if (t[6] or 0)>0)
baseline_gl = abs(sum(t[6] for t in trades if (t[6] or 0)<0))

print(f"BASELINE: {baseline_n} trades | {baseline_wins}W ({baseline_wr:.0f}%) | PnL ${baseline_pnl:+.2f} | PF {baseline_gw/baseline_gl:.2f}")
print()

PROF = 3.5

# === PROPUESTA 1: Revertir SL cap ===
print("=" * 80)
print("P1: SL cap = max(ATR*1.0, prof*1.5) en lugar de min(ATR*1.2, prof*1.6)")
print("=" * 80)
sim1_pnl = 0
saved = 0
for t in trades:
    tid, d, res, pips, sl_p, tp_p, pnl, atr, conf = t
    new_sl_p = max(atr * 1.0, PROF * 1.5)
    if res == 'loss' and abs(pips or 0) >= sl_p * 0.85 and new_sl_p > sl_p + 1:
        # SL hit and new SL gives breathing room
        # Conservative: 50% of these survive (price oscillated past old SL but bounced back)
        if new_sl_p > abs(pips or 0):
            saved += 1
            sim1_pnl += -1.0  # break-even-ish, just commission
        else:
            sim1_pnl += -(new_sl_p * 1.0 + 0.7)  # bigger loss
    else:
        sim1_pnl += pnl or 0

print(f"Trades salvados (SL hit que sobrevivirian): ~{saved}")
print(f"PnL simulado: ${sim1_pnl:+.2f}")
print(f"Delta vs baseline: ${sim1_pnl - baseline_pnl:+.2f}")
print()

# === PROPUESTA 2: ATR floor ===
print("=" * 80)
print("P2: No operar si ATR < 2.5p")
print("=" * 80)
filtered = [t for t in trades if t[7] >= 2.5]
removed = [t for t in trades if t[7] < 2.5]
filtered_pnl = sum(f[6] or 0 for f in filtered)
removed_pnl = sum(r[6] or 0 for r in removed)
filtered_wins = sum(1 for f in filtered if f[2]=='win')
print(f"Excluidos: {len(removed)} trades, PnL ${removed_pnl:+.2f}")
print(f"Restantes: {len(filtered)} trades, {filtered_wins}W ({filtered_wins/max(1,len(filtered))*100:.0f}%), PnL ${filtered_pnl:+.2f}")
print(f"Delta: ${filtered_pnl - baseline_pnl:+.2f}")
print()

# === PROPUESTA 3: ATR ceiling ===
print("=" * 80)
print("P3: No operar si ATR > 6p")
print("=" * 80)
filtered = [t for t in trades if t[7] <= 6.0]
removed = [t for t in trades if t[7] > 6.0]
filtered_pnl = sum(f[6] or 0 for f in filtered)
removed_pnl = sum(r[6] or 0 for r in removed)
filtered_wins = sum(1 for f in filtered if f[2]=='win')
print(f"Excluidos: {len(removed)} trades, PnL ${removed_pnl:+.2f}")
print(f"Restantes: {len(filtered)} trades, {filtered_wins}W ({filtered_wins/max(1,len(filtered))*100:.0f}%), PnL ${filtered_pnl:+.2f}")
print(f"Delta: ${filtered_pnl - baseline_pnl:+.2f}")
print()

# === PROPUESTA 4: Banda 2.5-6 ===
print("=" * 80)
print("P4: Solo operar 2.5 <= ATR <= 6")
print("=" * 80)
filtered = [t for t in trades if 2.5 <= t[7] <= 6.0]
removed = [t for t in trades if t[7] < 2.5 or t[7] > 6.0]
filtered_pnl = sum(f[6] or 0 for f in filtered)
removed_pnl = sum(r[6] or 0 for r in removed)
filtered_wins = sum(1 for f in filtered if f[2]=='win')
filt_gw = sum(f[6] for f in filtered if (f[6] or 0)>0)
filt_gl = abs(sum(f[6] for f in filtered if (f[6] or 0)<0))
pf = filt_gw/filt_gl if filt_gl else 0
print(f"Excluidos: {len(removed)} ({len(removed)/baseline_n*100:.0f}% del total), PnL ${removed_pnl:+.2f}")
print(f"Restantes: {len(filtered)} trades, {filtered_wins}W ({filtered_wins/max(1,len(filtered))*100:.0f}%), PnL ${filtered_pnl:+.2f}, PF {pf:.2f}")
print(f"Delta: ${filtered_pnl - baseline_pnl:+.2f}")
print()

# === PROPUESTA 5: COMBO — P4 + revertir SL cap ===
print("=" * 80)
print("P5: COMBO — P4 (banda ATR) + P1 (SL cap revertido)")
print("=" * 80)
combo_pnl = 0
combo_n = 0
combo_wins = 0
for t in trades:
    tid, d, res, pips, sl_p, tp_p, pnl, atr, conf = t
    if not (2.5 <= atr <= 6.0):
        continue  # skip
    combo_n += 1
    new_sl_p = max(atr * 1.0, PROF * 1.5)
    if res == 'loss' and abs(pips or 0) >= sl_p * 0.85 and new_sl_p > sl_p + 1:
        if new_sl_p > abs(pips or 0):
            combo_pnl += -1.0  # save
        else:
            combo_pnl += -(new_sl_p * 1.0 + 0.7)
    else:
        combo_pnl += pnl or 0
        if res == 'win': combo_wins += 1

print(f"Trades: {combo_n}, ~{combo_wins}W")
print(f"PnL simulado: ${combo_pnl:+.2f}")
print(f"Delta: ${combo_pnl - baseline_pnl:+.2f}")
print()

# === PROPUESTA 6: TP target más realista ===
print("=" * 80)
print("P6: TP target en 5p (en lugar de 9-15p actual)")
print("=" * 80)
# Si TP = 5, los wins que actualmente ganan >= 5p hubieran cerrado en exactamente 5p
# Los wins < 5 mantienen su pips. Losses sin cambio (asumiendo que no llegaron a 5p antes del SL)
sim6_pnl = 0
sim6_wins = 0
TP_NEW = 5.0
big_caps = []
for t in trades:
    res = t[2]; pips = t[3] or 0; pnl = t[6] or 0
    if res == 'win':
        sim6_wins += 1
        new_pips = min(pips, TP_NEW)
        sim6_pnl += new_pips * 1.0 - 0.7
        if pips > TP_NEW:
            big_caps.append((t[0], pips, pips - TP_NEW))
    else:
        sim6_pnl += pnl

print(f"PnL sim: ${sim6_pnl:+.2f}")
print(f"Wins limitados por nuevo TP: {len(big_caps)} (perdimos pips de wins grandes)")
total_lost = sum(b[2] for b in big_caps)
print(f"  Pips perdidos al cap: {total_lost:.1f}p ≈ ${total_lost:.2f}")
print(f"Delta: ${sim6_pnl - baseline_pnl:+.2f}")
print()

conn.close()
