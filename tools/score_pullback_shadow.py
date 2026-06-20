# -*- coding: utf-8 -*-
"""
score_pullback_shadow.py — Scorer FORWARD del shadow pullback_quality. READ-ONLY salvo
que rellena outcome_pips/outcome_price de filas ya viejas (>70min). NO re-simula SL/TP
(eso invirtio la realidad en el caso bounce) — mide el MOVIMIENTO REAL a favor en las
~12 velas M5 siguientes (~1h, el horizonte tipico del trade).

outcome_pips = max excursion a FAVOR tras el rechazo:
  PUT  -> (entry - min(low_siguientes)) * 10000   (cuanto cayo = a favor)
  CALL -> (max(high_siguientes) - entry) * 10000

Correr de a noche (o manual). Despues, en el checkpoint, comparar pareado vs el breakdown
vivo en la misma ventana (mercado/momento = control limpio) + gate de significancia.
"""
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
SYMBOL = 'EURUSD'
HORIZON_MIN = 60   # 12 velas M5


def main():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print('MetaTrader5 no disponible'); return
    if not mt5.initialize():
        print(f'No pude attachear a MT5: {mt5.last_error()}'); return
    try:
        # offset server-vs-UTC (robusto a DST): derivado del tick vivo
        tick = mt5.symbol_info_tick(SYMBOL)
        srv_off = round((tick.time - time.time()) / 1800.0) * 1800 if tick else 0

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM pullback_shadow_log WHERE outcome_pips IS NULL ORDER BY created_at"
        ).fetchall()
        if not rows:
            print('Sin filas pendientes de scorear.'); return

        scored = 0
        for r in rows:
            try:
                ca = datetime.strptime(str(r['created_at']).split('.')[0].replace('T', ' '),
                                       '%Y-%m-%d %H:%M:%S')  # AR naive
            except Exception:
                continue
            # AR (UTC-3) -> UTC -> server time
            t_utc = ca + timedelta(hours=3)
            t_srv = t_utc + timedelta(seconds=srv_off)
            if datetime.now() - ca < timedelta(minutes=HORIZON_MIN + 10):
                continue  # aun no maduro
            bars = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5,
                                        t_srv - timedelta(minutes=10),
                                        t_srv + timedelta(minutes=HORIZON_MIN + 5))
            if bars is None or len(bars) == 0:
                continue
            entry = r['entry_price']
            fwd = [b for b in bars if b['time'] >= (t_srv.timestamp() - 300)]
            if not fwd:
                continue
            if r['direction'] == 'PUT':
                fav = (entry - min(b['low'] for b in fwd)) * 10000
                px = min(b['low'] for b in fwd)
            else:
                fav = (max(b['high'] for b in fwd) - entry) * 10000
                px = max(b['high'] for b in fwd)
            conn.execute(
                "UPDATE pullback_shadow_log SET outcome_pips=?, outcome_price=?, scored_at=? WHERE id=?",
                (round(fav, 1), round(px, 5), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), r['id']))
            scored += 1
        conn.commit()

        # Resumen
        print(f'Scoreadas {scored} filas nuevas.')
        agg = conn.execute(
            "SELECT setup_type, COUNT(*) n, ROUND(AVG(outcome_pips),1) avg_fav, "
            "SUM(CASE WHEN outcome_pips>=6 THEN 1 ELSE 0 END) reached6 "
            "FROM pullback_shadow_log WHERE outcome_pips IS NOT NULL GROUP BY setup_type").fetchall()
        print('--- pullback_quality forward (a favor en ~1h) ---')
        for a in agg:
            print(f"  {a['setup_type']}: n={a['n']} avg_fav={a['avg_fav']}p  >=6p: {a['reached6']}")
        print('  (comparar pareado vs breakdown vivo en checkpoint + verify_finding antes de activar)')
        conn.close()
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
