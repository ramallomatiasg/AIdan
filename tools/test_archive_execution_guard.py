"""v3.51.1 — verificacion del guard de ejecucion de trade_archive.

trade_archive es la tabla de PLATA REALIZADA. Una estrategia que nunca llego al broker
(skip por cooldown, "market closing soon", spread gate, sin fill) no es un trade.

Corre sobre una DB TEMPORAL, nunca toca la de produccion.
  python tools/test_archive_execution_guard.py
"""
import os
import sys
import shutil
import sqlite3
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fails = []


def check(name, cond, detail=''):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail else ''))
    if not cond:
        fails.append(name)


# ── DB temporal con el esquema real ────────────────────────────────────────────
tmpdir = tempfile.mkdtemp(prefix='aidan_t_')
tmpdb = os.path.join(tmpdir, 'test.db')
os.environ['AIDAN_DB_PATH'] = tmpdb

import src.common.db as db
db.DB_PATH = tmpdb
db.init_db()


def mk_strategy(sid, ticket=None, pnl=None, status=None, trigger='m15_structure'):
    conn = sqlite3.connect(tmpdb)
    conn.execute("""
        INSERT INTO auto_strategies
            (id, direction, entry_price, stop_loss, take_profit, confidence, impact_score,
             expiry_minutes, status, created_at, expires_at, trigger_type, news_title,
             mt5_ticket, mt5_pnl, mt5_status)
        VALUES (?, 'CALL', 1.15437, 1.15287, 1.15617, 63, 50, 45, 'expired',
                '2026-08-06 11:00:17', '2026-08-06 11:45:17', ?, '[M15-STRUCT] test',
                ?, ?, ?)
    """, (sid, trigger, ticket, pnl, status))
    conn.commit()
    conn.close()


def archived(sid):
    conn = sqlite3.connect(tmpdb)
    r = conn.execute("SELECT mt5_pnl, pips, result FROM trade_archive WHERE strategy_id=?", (sid,)).fetchone()
    conn.close()
    return r


print("\n=== BLOQUEA lo que nunca llego al broker ===")
# #881 real: nunca ejecutado ("MT5 blocked: market closing soon")
mk_strategy(881, ticket=None, pnl=None, status=None, trigger='h1_structure')
db.archive_trade(881, 'loss', 1.15583, -0.7)
check("#881 (nunca ejecutado, como el caso real) NO se archiva", archived(881) is None)

# #865 real: skipeado por el cooldown, se habria archivado como "+13.3p WIN"
mk_strategy(865, ticket=None, pnl=None, status=None)
db.archive_trade(865, 'win', 1.15575, 13.3)
check("#865 (skip por cooldown, +13.3p 'win' teorico) NO se archiva", archived(865) is None)

mk_strategy(900, ticket=None, pnl=None, status='pending')
db.archive_trade(900, 'loss', 1.15400, -5.0)
check("limit order que nunca llenó (mt5_status='pending') NO se archiva", archived(900) is None)

print("\n=== DEJA PASAR todo lo que si es un trade ===")
mk_strategy(901, ticket=1848714326, pnl=-0.80, status='closed')
db.archive_trade(901, 'loss', 1.15400, -0.2)
r = archived(901)
check("trade normal (ticket + P&L) se archiva", r is not None and r[0] == -0.80, str(r))

# La carrera que cubre el backfill de v3.50.3: ticket si, P&L todavia no.
mk_strategy(902, ticket=1848714999, pnl=None, status='filled')
db.archive_trade(902, 'win', 1.15600, 6.3)
r = archived(902)
check("ticket SIN P&L todavia (carrera del backfill v3.50.3) SI se archiva", r is not None, str(r))
check("  y queda con mt5_pnl NULL para que update_mt5_close lo complete",
      r is not None and r[0] is None)

# Fila vieja sin ticket pero con P&L cargado (no deberia existir, pero no la bloqueamos).
mk_strategy(903, ticket=None, pnl=2.50, status='closed')
db.archive_trade(903, 'win', 1.15700, 5.0)
check("sin ticket pero CON P&L real se archiva igual (evidencia = P&L)", archived(903) is not None)

print("\n=== el backfill de v3.50.3 sigue funcionando sobre el caso 902 ===")
db.update_mt5_close(902, -3.21, 1.15300)
r = archived(902)
check("update_mt5_close completa el mt5_pnl del archivo", r is not None and r[0] == -3.21, str(r))

print("\n=== apagar por env restaura el comportamiento previo ===")
from src.common.config import Config
_prev = Config.ARCHIVE_REQUIRE_EXECUTION
try:
    Config.ARCHIVE_REQUIRE_EXECUTION = False
    mk_strategy(904, ticket=None, pnl=None, status=None)
    db.archive_trade(904, 'win', 1.15575, 13.3)
    check("ARCHIVE_REQUIRE_EXECUTION=false vuelve a archivar el fantasma", archived(904) is not None)
finally:
    Config.ARCHIVE_REQUIRE_EXECUTION = _prev

print("\n=== idempotencia y bordes ===")
mk_strategy(905, ticket=1848715000, pnl=1.5, status='closed')
db.archive_trade(905, 'win', 1.15600, 3.0)
db.archive_trade(905, 'loss', 1.15200, -9.9)     # 2do intento
conn = sqlite3.connect(tmpdb)
n = conn.execute("SELECT COUNT(*) FROM trade_archive WHERE strategy_id=905").fetchone()[0]
res = conn.execute("SELECT result FROM trade_archive WHERE strategy_id=905").fetchone()[0]
conn.close()
check("sigue siendo idempotente (1 sola fila, gana la primera)", n == 1 and res == 'win', f"n={n} result={res}")

db.archive_trade(999999, 'win', 1.1, 1.0)        # strategy inexistente
check("strategy inexistente no explota", archived(999999) is None)

print("\n=== el guard NO toca la evaluacion a nivel SEÑAL (strategy_results) ===")
mk_strategy(906, ticket=None, pnl=None, status=None)
db.auto_evaluate_strategy(906, 'loss', 1.15400, -5.0)
conn = sqlite3.connect(tmpdb)
sr = conn.execute("SELECT COUNT(*) FROM strategy_results WHERE strategy_id=906").fetchone()[0]
conn.close()
check("la señal no ejecutada SIGUE registrandose en strategy_results", sr == 1, f"n={sr}")
check("  pero no en trade_archive", archived(906) is None)

shutil.rmtree(tmpdir, ignore_errors=True)
print("\n" + ("TODO OK" if not fails else f"{len(fails)} FALLARON: {fails}"))
sys.exit(1 if fails else 0)
