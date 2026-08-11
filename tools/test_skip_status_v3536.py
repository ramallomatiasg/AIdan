# -*- coding: utf-8 -*-
"""Tests v3.53.6 — una señal que nunca llego al broker no puede disfrazarse de trade.

Cubre los dos fixes:
  (1) auto_evaluate_strategy conserva el status de skip (antes lo pisaba con auto_loss)
      + el helper strategy_was_executed + la etiqueta del dashboard.
  (3) el post-trade analyzer no corre sobre señales sin ticket ni P&L.

Corre contra una DB TEMPORAL. No toca produccion ni necesita MT5.
"""
import os
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('  OK   ' if cond else '  FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''))


# ── DB temporal con el esquema minimo ────────────────────────────────────────
def _mk_db():
    path = os.path.join(tempfile.mkdtemp(prefix='aidan_t5535_'), 'test.db')
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE auto_strategies (
        id INTEGER PRIMARY KEY, direction TEXT, entry_price REAL, stop_loss REAL,
        take_profit REAL, confidence REAL, expiry_minutes INTEGER, status TEXT,
        created_at TEXT, expires_at TEXT, news_title TEXT, trigger_type TEXT,
        mt5_ticket INTEGER, mt5_pnl REAL, mt5_status TEXT)""")
    c.execute("""CREATE TABLE strategy_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_id INTEGER UNIQUE, result TEXT,
        recorded_at TEXT, entry_price REAL, exit_price REAL, pips REAL, direction TEXT,
        confidence REAL, setup_type TEXT, trigger_type TEXT, market_trend TEXT,
        rsi_at_entry REAL, htf_bias TEXT, reported_to_sheets INTEGER DEFAULT 0)""")
    c.commit()
    c.close()
    return path


def _add(path, sid, status, ticket=None, pnl=None):
    c = sqlite3.connect(path)
    c.execute("INSERT INTO auto_strategies (id, direction, status, trigger_type, mt5_ticket, mt5_pnl)"
              " VALUES (?,'PUT',?,'smc',?,?)", (sid, status, ticket, pnl))
    c.commit()
    c.close()


def _status(path, sid):
    c = sqlite3.connect(path)
    r = c.execute("SELECT status FROM auto_strategies WHERE id=?", (sid,)).fetchone()
    c.close()
    return r[0] if r else None


def _sr(path, sid):
    c = sqlite3.connect(path)
    r = c.execute("SELECT result, pips FROM strategy_results WHERE strategy_id=?", (sid,)).fetchone()
    c.close()
    return r


# ── (1) auto_evaluate_strategy ───────────────────────────────────────────────
print('\n[1] auto_evaluate_strategy: no pisa el status de skip')
db_path = _mk_db()
import src.common.db as dbmod
dbmod.DB_PATH = db_path
_orig_connect = dbmod._connect
dbmod._connect = lambda *a, **k: sqlite3.connect(db_path, timeout=15.0)

# los 4 status de skip que existen en el codigo
for sid, st in ((886, 'skipped_cooldown'), (2, 'skipped_bounce'),
                (3, 'skipped_opposite'), (4, 'auto_skipped')):
    _add(db_path, sid, st)
    dbmod.auto_evaluate_strategy(sid, 'loss', 1.15421, -2.2, {'direction': 'PUT'})
    check(f'conserva status={st}', _status(db_path, sid) == st, _status(db_path, sid))

# la señal SI se evalua: la fila de strategy_results tiene que existir igual
row = _sr(db_path, 886)
check('la señal igual queda en strategy_results', row is not None and row[0] == 'loss',
      str(row))
check('con sus pips teoricos intactos', row is not None and abs(row[1] - (-2.2)) < 1e-9, str(row))

# el camino normal NO cambia
for sid, res, expected in ((10, 'win', 'auto_win'), (11, 'loss', 'auto_loss'),
                           (12, 'break_even', 'auto_break_even')):
    _add(db_path, sid, 'active', ticket=999000 + sid, pnl=1.0)
    dbmod.auto_evaluate_strategy(sid, res, 1.15, 1.0, {'direction': 'CALL'})
    check(f'trade ejecutado {res} -> {expected}', _status(db_path, sid) == expected,
          _status(db_path, sid))

# status desconocido/vacio: se comporta como antes (se pisa)
_add(db_path, 13, 'expired')
dbmod.auto_evaluate_strategy(13, 'loss', 1.15, -1.0, {})
check('status no-skip se sigue pisando', _status(db_path, 13) == 'auto_loss', _status(db_path, 13))

# MUTACION: la logica vieja (UPDATE incondicional) SI pisaba el skip
_add(db_path, 20, 'skipped_cooldown')
c = sqlite3.connect(db_path)
c.execute("UPDATE auto_strategies SET status=? WHERE id=?", ('auto_loss', 20))  # codigo v3.53.4
c.commit(); c.close()
check('MUTACION: la logica vieja pisaba el skip (rojo antes del fix)',
      _status(db_path, 20) == 'auto_loss', _status(db_path, 20))


# ── strategy_was_executed ────────────────────────────────────────────────────
print('\n[1b] strategy_was_executed: True / False / None')
_add(db_path, 30, 'active', ticket=123456)                 # ticket, sin P&L todavia
_add(db_path, 31, 'active', ticket=None, pnl=-2.0)         # P&L sin ticket
_add(db_path, 32, 'skipped_cooldown')                      # ninguno de los dos
_add(db_path, 33, 'active', ticket=0)                      # ticket 0 = falsy, sin P&L
check('ticket sin P&L -> True (carrera del backfill v3.50.3)', dbmod.strategy_was_executed(30) is True)
check('P&L sin ticket -> True', dbmod.strategy_was_executed(31) is True)
check('sin ticket ni P&L -> False', dbmod.strategy_was_executed(32) is False)
check('ticket=0 sin P&L -> False', dbmod.strategy_was_executed(33) is False)
check('estrategia inexistente -> None (no se asume nada)', dbmod.strategy_was_executed(9999) is None)

# P&L = 0.0 es un P&L valido, no ausencia
_add(db_path, 34, 'active', ticket=None, pnl=0.0)
check('P&L 0.0 -> True (0 es un valor, no NULL)', dbmod.strategy_was_executed(34) is True)

dbmod._connect = _orig_connect


# ── (3) guard del post-trade: tabla de decision ──────────────────────────────
print('\n[3] guard del post-trade analyzer')


def corre_post_trade(was_executed):
    """Replica la condicion del guard: `if _was_exec(sid) is False: return`."""
    return not (was_executed is False)


check('ejecutada -> corre', corre_post_trade(True) is True)
check('NO ejecutada -> NO corre', corre_post_trade(False) is False)
check('desconocido (None) -> corre igual (fail-open)', corre_post_trade(None) is True)


# ── el guard esta realmente en los DOS call sites del monolito ───────────────
print('\n[3b] el guard esta en el fuente (los 2 call sites)')
mono = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'AIdan_TodoEnUno.py'), encoding='utf-8', errors='replace').read()
sin_comentarios = '\n'.join(l for l in mono.splitlines() if not l.strip().startswith('#'))
n_guards = len(re.findall(r'_was_exec\(s_id\)\s+is\s+False', sin_comentarios))
check('guard presente en los 2 call sites (arranque + loop)', n_guards == 2, f'encontrados={n_guards}')
check('el guard usa `is False`, no un truthiness suelto',
      'is False' in sin_comentarios and not re.search(r'if\s+not\s+_was_exec\(', sin_comentarios))


# ── dashboard ────────────────────────────────────────────────────────────────
print('\n[1c] dashboard: etiqueta "No operada"')
html_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'dashboard_multi_theme.html')
html = open(html_path, encoding='utf-8', errors='replace').read()
check('define `executed` por ticket/P&L, no por status',
      'const executed = !!(s.mt5_ticket || s.mt5_pnl != null);' in html)
check('la etiqueta dice "No operada"', 'No operada' in html)
check('helper _skipWhy definido', 'const _skipWhy = (st) =>' in html)
check('stripe gris cuando no se ejecuto', "!executed ? 'var(--text-muted)'" in html)

# La trampa que casi shipeo: comentarios JS escritos con backslash en vez de //.
# Un solo `\ ` al principio de linea rompe TODO el dashboard.
malos = [i + 1 for i, l in enumerate(html.splitlines()) if l.lstrip().startswith('\\ ')]
check('sin comentarios con backslash (romperian el JS)', not malos, f'lineas={malos[:5]}')

print('\n' + '=' * 60)
ok = sum(1 for _, c, _ in RESULTS if c)
print(f'{ok}/{len(RESULTS)} OK')
for n, c, d in RESULTS:
    if not c:
        print(f'  FAIL: {n}  {d}')
sys.exit(0 if ok == len(RESULTS) else 1)
