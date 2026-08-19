"""Verificacion END-TO-END del camino de decision nuevo (v3.57.0).

Prueba lo que un unit test no puede: que `add_auto_strategy` -> ajuste de
confianza -> retrospectiva -> fila persistida funcione DE VERDAD, con la data
real, sin esperar a que aparezca una senal en vivo (AIdan hace ~5 trades/dia).

SEGURIDAD: copia la DB de produccion a un temporal y reapunta `db.DB_PATH` ANTES
de cualquier escritura, con un assert que aborta si el path no es el temporal.
La regla del proyecto (v3.53.6) es que nada de prueba escriba en la DB viva —
ya paso una vez y sus filas coparon el panel. Al final imprime el conteo de
produccion como control.

Fuerza RETRO_MODE=active a proposito, para ver el delta aplicado; el default en
produccion sigue siendo `shadow`.

    python tools/verify_retro_path.py
"""
import os, sqlite3, sys, tempfile, logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
sys.path.insert(0, r'F:\AIdan')

prod = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
dst = os.path.join(tempfile.mkdtemp(prefix='aidan_e2e_'), 'copia.db')
s = sqlite3.connect('file:%s?mode=ro' % prod, uri=True); d = sqlite3.connect(dst)
with d: s.backup(d)
s.close(); d.close()

import src.common.db as db
db.DB_PATH = dst
db._WAL_READY = False
assert 'aidan_e2e_' in db.DB_PATH, 'la prueba NO debe escribir en produccion'
print('DB de prueba:', db.DB_PATH)

os.environ['RETRO_MODE'] = 'active'   # forzado para ver el delta aplicado

sid = db.add_auto_strategy(
    alert_id=None, news_title='E2E test', direction='CALL',
    entry_price=1.1000, stop_loss=1.0985, take_profit=1.1060,
    confidence=70, impact_score=0, expiry_minutes=45,
    trigger_type='m15_structure',
    entry_context={'setup_type': 'trend_continuation_bull', 'volatility': 'normal',
                   'session': 'ny', 'hour_utc': 16, 'htf_bias': 'bullish', 'rsi': 55})
print('\nstrategy creada:', sid)

c = sqlite3.connect(dst); c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM pre_trade_retrospective ORDER BY id DESC LIMIT 1").fetchone()
if not r:
    print('!! NO se escribio fila de retrospectiva'); sys.exit(1)
print('\n--- fila de pre_trade_retrospective ---')
for k in ('strategy_id','mode','verdict','direction','setup_type','matched_on','n_similar',
          'n_same','n_opp','wr_same','wr_opp','pnl_same','pnl_opp','lesson_hits',
          'conf_before','conf_delta_suggested','conf_delta_applied','meta_delta_applied','reason'):
    print('  %-22s %s' % (k, r[k]))
conf = c.execute("SELECT confidence FROM auto_strategies WHERE id=?", (sid,)).fetchone()[0]
print('\nconfidence guardada: %s   (entro 70)' % conf)
print('prod intacta:', sqlite3.connect('file:%s?mode=ro' % prod, uri=True)
      .execute("select count(*) from pre_trade_retrospective").fetchone()[0], 'filas (debe ser 0)')
c.close()
