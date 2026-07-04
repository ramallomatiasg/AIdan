# -*- coding: utf-8 -*-
"""
score_fade_chop_shadow.py — Scorer FORWARD del shadow fade-en-chop (v3.45.0). READ-ONLY salvo
que rellena outcome_fav_pips/outcome_adv_pips de filas ya viejas (>70min). NO re-simula SL/TP
(eso invirtio la realidad en el caso bounce) — mide el movimiento REAL en las ~12 velas M5
siguientes (~1h).

A diferencia del scorer de pullback, un FADE (reversion) puede ir a favor y darse vuelta, asi
que medimos AMBAS excursiones desde el entry:
  fav = cuanto se movio A FAVOR (PUT -> cayo; CALL -> subio)
  adv = cuanto se movio EN CONTRA (PUT -> subio; CALL -> cayo)
Un fade "bueno" = fav grande con adv chico (reverte antes de romper). En el checkpoint se
compara pareado vs lo que el breakout perdio en el mismo regimen + gate de significancia.

Correr de a noche (o manual, con AIdan cerrado si se quiere el terminal MT5 libre).
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
        tick = mt5.symbol_info_tick(SYMBOL)
        srv_off = round((tick.time - time.time()) / 1800.0) * 1800 if tick else 0

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM fade_chop_shadow_log WHERE outcome_fav_pips IS NULL ORDER BY created_at"
        ).fetchall()
        if not rows:
            print('Sin filas pendientes de scorear.')
        scored = 0
        for r in rows:
            try:
                ca = datetime.strptime(str(r['created_at']).split('.')[0].replace('T', ' '),
                                       '%Y-%m-%d %H:%M:%S')  # AR naive
            except Exception:
                continue
            t_utc = ca + timedelta(hours=3)          # AR (UTC-3) -> UTC
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
            hi = max(b['high'] for b in fwd)
            lo = min(b['low'] for b in fwd)
            if r['direction'] == 'PUT':      # a favor = cae ; en contra = sube
                fav = (entry - lo) * 10000
                adv = (hi - entry) * 10000
            else:                            # CALL: a favor = sube ; en contra = cae
                fav = (hi - entry) * 10000
                adv = (entry - lo) * 10000
            conn.execute(
                "UPDATE fade_chop_shadow_log SET outcome_fav_pips=?, outcome_adv_pips=?, scored_at=? WHERE id=?",
                (round(fav, 1), round(adv, 1), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), r['id']))
            scored += 1
        conn.commit()

        print(f'Scoreadas {scored} filas nuevas.')
        agg = conn.execute(
            "SELECT setup_type, COUNT(*) n, ROUND(AVG(outcome_fav_pips),1) avg_fav, "
            "ROUND(AVG(outcome_adv_pips),1) avg_adv, "
            "SUM(CASE WHEN outcome_fav_pips>=6 AND outcome_fav_pips>outcome_adv_pips THEN 1 ELSE 0 END) good "
            "FROM fade_chop_shadow_log WHERE outcome_fav_pips IS NOT NULL GROUP BY setup_type").fetchall()
        print('--- fade_chop forward (~1h) ---')
        for a in agg:
            print(f"  {a['setup_type']}: n={a['n']} avg_fav={a['avg_fav']}p avg_adv={a['avg_adv']}p  "
                  f"buenos(fav>=6 y fav>adv): {a['good']}")
        print('  (comparar pareado vs breakout vivo en el MISMO regimen chop + verify_finding antes de activar)')
        conn.close()
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
