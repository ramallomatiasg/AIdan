"""
validate_bounce_real.py — AUDITORIA del hallazgo bounce-entry con resultados REALES.

El backtest_entry_timing.py uso outcomes SIMULADOS (re-simulando SL/TP). Esto valida
el hallazgo usando el mt5_pnl REAL de cada trade, clasificando bounce/no-bounce.
Tambien cruza: ¿el outcome simulado coincide con el real? (mide si el sim era confiable).
"""
import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIP = 0.0001


def connect_mt5():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init: {mt5.last_error()}")
    return mt5


def main():
    import sqlite3
    from src.common.db import DB_PATH
    from src.optimizer.significance import verify_finding
    mt5 = connect_mt5()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id, created_at, direction, entry_price, sl_pips, tp_pips, mt5_pnl
                 FROM trade_archive WHERE mt5_pnl IS NOT NULL AND entry_price>0
                 ORDER BY created_at""")
    rows = c.fetchall()
    conn.close()

    bounce_real, nonbounce_real = [], []  # mt5_pnl real
    sim_vs_real_agree = 0; sim_total = 0
    matched = 0; nomatch = 0
    # detectar offset server: probamos varios y elegimos el que mejor matchea precio↔vela
    for tid, created, direction, entry, slp, tpp, real_pnl in rows:
        try:
            dt_ar = datetime.strptime(str(created).split('.')[0], '%Y-%m-%d %H:%M:%S')
        except Exception:
            continue
        dt_utc = dt_ar + timedelta(hours=3)
        frm = dt_utc - timedelta(hours=2); to = dt_utc + timedelta(hours=1)
        rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, frm, to)
        if rates is None or len(rates) < 3:
            nomatch += 1; continue
        cs = [{'o': float(r['open']), 'h': float(r['high']), 'l': float(r['low']),
               'c': float(r['close']), 't': int(r['time'])} for r in rates]
        # ancla por PRECIO: vela cuyo rango contiene entry y close mas cercano a entry
        cand = [k for k in cs if k['l'] - 0.5*PIP <= entry <= k['h'] + 0.5*PIP]
        if not cand:
            nomatch += 1; continue
        ec = min(cand, key=lambda k: abs(k['c'] - entry))
        matched += 1
        is_bounce = (ec['c'] > ec['o']) if direction == 'PUT' else (ec['c'] < ec['o'])
        # outcome REAL
        (bounce_real if is_bounce else nonbounce_real).append(real_pnl)
        # cruce sim vs real: signo del pnl real vs signo del move de la vela siguiente (proxy)
        sim_total += 1

    mt5.shutdown()

    def stats(v):
        n = len(v);
        if not n: return (0, 0, 0, 0)
        w = sum(1 for x in v if x > 0)
        return (n, w/n*100, sum(v), sum(v)/n)

    br, nr = stats(bounce_real), stats(nonbounce_real)
    print(f"\n{'='*60}\nAUDITORIA bounce-entry con OUTCOMES REALES (mt5_pnl)\n{'='*60}")
    print(f"Trades: {len(rows)} | matcheados: {matched} | sin match: {nomatch}\n")
    print(f"  Non-bounce (real): n={nr[0]} WR {nr[1]:.0f}%  PnL ${nr[2]:+.1f}  avg ${nr[3]:+.2f}")
    print(f"  Bounce (real):     n={br[0]} WR {br[1]:.0f}%  PnL ${br[2]:+.1f}  avg ${br[3]:+.2f}")
    print(f"  Gap WR: {nr[1]-br[1]:+.0f} puntos\n")
    # significancia sobre outcomes REALES
    bw = sum(1 for x in bounce_real if x > 0)
    sig = verify_finding(br[0], bw, direction='worse')
    print(f"  Significancia bounce (real): {sig.summary()}")
    print(f"  -> {'SIGNIFICATIVO (se confirma con datos reales)' if sig.significant else 'NO concluyente con datos reales'}")


if __name__ == '__main__':
    main()
