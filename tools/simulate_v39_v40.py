"""Simulación v3.9.0 (expiry fix + SIM A) y proyección v4.0 sobre data corregida.

Modela el efecto del expiry fix asumiendo:
- 60% de wins amputados llegan a TP (avg captura 70-80% del TP nominal)
- 25% se mantienen en pequeño profit (similar a actual)
- 15% reversionan a SL (loss)

Esto genera una baseline 'corregida' sobre la cual simulamos v4.0.
"""
import sqlite3, os, json
from random import random

db = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(db); c = conn.cursor()

c.execute("""SELECT id, direction, result, mt5_pnl, pips, confidence, trigger_type,
htf_bias, market_trend, rsi_at_entry, avg_range_pips, session, hour_utc, entry_context,
sl_pips, tp_pips
FROM trade_archive WHERE result IN ('win','loss') AND archived_at >= '2026-04-21'""")
trades_raw = c.fetchall()

# === STEP 1: Apply expiry fix model to historical wins ===
# Wins that captured <70% of TP were amputated. Project what they would have done.
def model_expiry_fix(t):
    """Returns (new_pips, new_pnl, new_result). Modeling assumptions documented above."""
    tid, d, res, pnl, pips, conf, trig, htf, m5, rsi, atr, sess, hr, ectx, sl_p, tp_p = t

    if res == 'loss':
        # Losses already hit SL — no change (TP wasn't going to happen anyway)
        return (pips, pnl, res, sl_p, tp_p)

    # Win — was it amputated?
    capture_pct = (pips / tp_p * 100) if tp_p > 0 else 100
    if capture_pct >= 70:
        # Already captured most of TP — no change
        return (pips, pnl, res, sl_p, tp_p)

    # Amputated win — project what would have happened
    # Use trade ID as deterministic "random" seed for reproducibility
    seed = (tid * 9301 + 49297) % 233280
    r = seed / 233280.0

    if r < 0.60:
        # 60% — would have hit TP
        new_pips = tp_p
        new_pnl = tp_p * 1.0 - 0.7  # 0.1 lot, $1/pip, $0.7 commission
        return (new_pips, new_pnl, 'win', sl_p, tp_p)
    elif r < 0.85:
        # 25% — would have closed at similar small win (price stalled)
        return (pips, pnl, res, sl_p, tp_p)
    else:
        # 15% — would have reversed to SL
        new_pips = -sl_p
        new_pnl = -sl_p * 1.0 - 0.7  # commission too
        return (new_pips, new_pnl, 'loss', sl_p, tp_p)

# Apply expiry fix
trades_v39 = []
for t in trades_raw:
    new_pips, new_pnl, new_res, sl_p, tp_p = model_expiry_fix(t)
    new_t = list(t)
    new_t[3] = new_pnl
    new_t[4] = new_pips
    new_t[2] = new_res
    trades_v39.append(tuple(new_t))

# === STEP 2: Apply SIM A on top (block fully-aligned structure) ===
def is_aligned(d, htf, m5):
    return ((d=='CALL' and htf=='bullish' and m5=='bullish') or
            (d=='PUT' and htf=='bearish' and m5=='bearish'))

def passes_sim_a(t):
    d, htf, m5, trig = t[1], t[7] or 'neutral', t[8] or 'unknown', t[6]
    if trig == 'structure' and is_aligned(d, htf, m5):
        return False
    return True

trades_v39_sima = [t for t in trades_v39 if passes_sim_a(t)]

# === Compare ===
def stats(trades, label):
    n = len(trades)
    wins = sum(1 for t in trades if t[2]=='win')
    pnl = sum(t[3] or 0 for t in trades)
    gw = sum(t[3] for t in trades if (t[3] or 0)>0)
    gl = abs(sum(t[3] for t in trades if (t[3] or 0)<0))
    pf = gw/gl if gl else 0
    avg_win_pips = sum(t[4] for t in trades if t[2]=='win')/wins if wins else 0
    avg_loss_pips = sum(t[4] for t in trades if t[2]=='loss')/(n-wins) if (n-wins) else 0
    print(f"{label}:")
    print(f"  n={n} | {wins}W ({wins/max(1,n)*100:.0f}%) | PnL ${pnl:+.2f} | PF {pf:.2f}")
    print(f"  avg win {avg_win_pips:+.1f}p | avg loss {avg_loss_pips:+.1f}p")
    print()

print("="*80)
print("BASELINE vs v3.9.0 (expiry fix + SIM A)")
print("="*80)
stats(trades_raw, "BASELINE actual (con bugs)")
stats(trades_v39, "Solo expiry fix (modelo conservador)")
stats(trades_v39_sima, "v3.9.0 — expiry fix + SIM A")

# === STEP 3: Now layer v4.0 changes on the v3.9.0 baseline ===
print("="*80)
print("Sobre v3.9.0 (data corregida), ¿qué aporta v4.0 adicional?")
print("="*80)
print()

def get_momentum(t):
    ctx = json.loads(t[13]) if t[13] else {}
    return ctx.get('momentum', 'flat')

def is_against_momentum(d, mom):
    return ((d=='CALL' and mom=='down') or (d=='PUT' and mom=='up'))

def is_counter(d, htf, m5):
    is_with_m5 = (d=='CALL' and m5=='bullish') or (d=='PUT' and m5=='bearish')
    is_with_htf = (d=='CALL' and htf=='bullish') or (d=='PUT' and htf=='bearish')
    is_against_htf = (d=='CALL' and htf=='bearish') or (d=='PUT' and htf=='bullish')
    is_against_m5 = (d=='CALL' and m5=='bearish') or (d=='PUT' and m5=='bullish')
    return (is_with_m5 and is_against_htf) or (is_with_htf and is_against_m5)

# v4.0 v1: agregar invertir momentum scoring (no aligned ya filtrado por SIM A)
# Aproximacion: filter trades where momentum is WITH direction (bad)
v40_v1 = [t for t in trades_v39_sima
          if not ((t[1]=='CALL' and get_momentum(t)=='up') or
                  (t[1]=='PUT' and get_momentum(t)=='down'))]
stats(v40_v1, "v3.9.0 + filter WITH-momentum trades")

# v4.0 v2: solo counter-trend (más estricto)
v40_v2 = [t for t in trades_v39_sima
          if is_counter(t[1], t[7] or 'neutral', t[8] or 'unknown')]
stats(v40_v2, "v3.9.0 + solo counter-trend")

# v4.0 v3: hour gate 13-20h UTC
v40_v3 = [t for t in trades_v39_sima
          if t[12] is not None and 13 <= int(t[12]) <= 20]
stats(v40_v3, "v3.9.0 + hour gate 13-20 UTC")

# v4.0 final: combo (counter-trend + against-momentum + hour)
v40_final = [t for t in trades_v39_sima
             if is_counter(t[1], t[7] or 'neutral', t[8] or 'unknown')
             and is_against_momentum(t[1], get_momentum(t))
             and t[12] is not None and 13 <= int(t[12]) <= 20]
stats(v40_final, "v4.0 FULL — counter+against-momentum+hour")

# Final comparison
print("="*80)
print("CONCLUSION: ¿v4.0 sigue agregando valor sobre v3.9.0?")
print("="*80)
v39_pnl = sum(t[3] or 0 for t in trades_v39_sima)
v40_pnl = sum(t[3] or 0 for t in v40_final)
delta = v40_pnl - v39_pnl
print(f"v3.9.0 PnL:     ${v39_pnl:+.2f}")
print(f"v4.0 FULL PnL:  ${v40_pnl:+.2f}")
print(f"Delta v4.0:     ${delta:+.2f} (sobre {len(v40_final)} trades vs {len(trades_v39_sima)})")

if delta > 20:
    print(f"\n  → v4.0 SI agrega valor significativo (+${delta:.0f}). Vale la pena implementar después de validar v3.9.")
elif delta > 0:
    print(f"\n  → v4.0 agrega valor MARGINAL (+${delta:.0f}). Esperar 30 trades de v3.9 antes de decidir.")
else:
    print(f"\n  → v4.0 NO agrega valor sobre v3.9. El expiry fix capturó todo el upside disponible.")

conn.close()
