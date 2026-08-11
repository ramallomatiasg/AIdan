# -*- coding: utf-8 -*-
"""Tests v3.53.6 (2da tanda) — que un test no pueda volver a escribir en produccion.

Cubre los 4 fixes del incidente del #999:
  (1) el harness de test_commission_double_count_v3533 apunta a una DB temporal
  (2) guards de existencia en auto_evaluate_strategy y save_post_trade_analysis
  (3) analyzed_at sellado con now_ar() en vez del DEFAULT UTC
  (4) la limpieza: que las filas imposibles ya no esten y las reales sigan

DB temporal. No necesita MT5.
"""
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('  OK   ' if cond else '  FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''))


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── (1) el harness del test de comision esta aislado ─────────────────────────
print('\n[1] test_commission_double_count_v3533: aislado de produccion')
src = open(os.path.join(ROOT, 'tools', 'test_commission_double_count_v3533.py'),
           encoding='utf-8', errors='replace').read()
codigo = '\n'.join(l for l in src.splitlines() if not l.strip().startswith('#'))
check('apunta DB_PATH a un temporal', 'dbmod.DB_PATH = cls._tmpdb' in codigo)
check('reemplaza _connect por el temporal', 'dbmod._connect = lambda' in codigo)
check('usa tempfile.mkdtemp', 'tempfile.mkdtemp' in codigo)
check('restaura DB_PATH y _connect al terminar',
      'dbmod.DB_PATH = cls._orig_db_path' in codigo and 'dbmod._connect = cls._orig_connect' in codigo)
check('neutraliza el LLM (no gasta cuota de Groq)',
      'ptmod.analyze_closed_trade = lambda' in codigo)
check('restaura el analyzer', 'ptmod.analyze_closed_trade = orig_analyze' in codigo)
check('assert de que la DB NO es la de prod', 'assert dbmod.DB_PATH != cls._orig_db_path' in codigo)

# ── (2) guards de existencia ─────────────────────────────────────────────────
print('\n[2] guards: no se escribe sobre strategy_id inexistente')
tmp = os.path.join(tempfile.mkdtemp(prefix='aidan_pg3536_'), 'test.db')
c = sqlite3.connect(tmp)
c.execute("""CREATE TABLE auto_strategies (id INTEGER PRIMARY KEY, direction TEXT,
    status TEXT, trigger_type TEXT, mt5_ticket INTEGER, mt5_pnl REAL)""")
c.execute("""CREATE TABLE strategy_results (id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER UNIQUE, result TEXT, recorded_at TEXT, entry_price REAL,
    exit_price REAL, pips REAL, direction TEXT, confidence REAL, setup_type TEXT,
    trigger_type TEXT, market_trend TEXT, rsi_at_entry REAL, htf_bias TEXT)""")
c.execute("""CREATE TABLE post_trade_analysis (id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL, result TEXT, entry_quality TEXT, exit_quality TEXT,
    news_accuracy TEXT, timing_assessment TEXT, key_lesson TEXT, confidence_was TEXT,
    suggested_adjustment TEXT, raw_response TEXT, analyzed_at TEXT DEFAULT (datetime('now')))""")
c.execute("INSERT INTO auto_strategies (id, direction, status, trigger_type) VALUES (500,'PUT','active','smc')")
c.commit(); c.close()

import src.common.db as dbmod
_orig_connect = dbmod._connect
dbmod._connect = lambda *a, **k: sqlite3.connect(tmp, timeout=15.0)

check('strategy_exists: existente -> True', dbmod.strategy_exists(500) is True)
check('strategy_exists: inexistente -> False', dbmod.strategy_exists(999) is False)

# el caso real: el id inventado del harness
dbmod.auto_evaluate_strategy(999, 'win', 1.161, 10.0, {'direction': 'CALL', 'trigger_type': 'structure'})
n = sqlite3.connect(tmp).execute("SELECT COUNT(*) FROM strategy_results WHERE strategy_id=999").fetchone()[0]
check('auto_evaluate_strategy NO escribe para #999', n == 0, f'filas={n}')

_ana = {'entry_quality': 'good', 'exit_quality': 'good', 'key_lesson': 'Ajustar el SL a 15 pips',
        'trigger_type': 'structure', 'sl_action': 'keep', 'recommended_sl_pips': 15}
dbmod.save_post_trade_analysis(999, _ana, 'win')
n = sqlite3.connect(tmp).execute("SELECT COUNT(*) FROM post_trade_analysis WHERE strategy_id=999").fetchone()[0]
check('save_post_trade_analysis NO escribe para #999', n == 0, f'filas={n}')

# control: la estrategia que SI existe se sigue registrando igual que siempre
dbmod.auto_evaluate_strategy(500, 'loss', 1.15, -3.0, {'direction': 'PUT', 'trigger_type': 'smc'})
row = sqlite3.connect(tmp).execute(
    "SELECT result, pips FROM strategy_results WHERE strategy_id=500").fetchone()
check('la estrategia REAL se sigue registrando', row is not None and row[0] == 'loss', str(row))

dbmod.save_post_trade_analysis(500, _ana, 'loss')
row = sqlite3.connect(tmp).execute(
    "SELECT strategy_id, key_lesson, analyzed_at FROM post_trade_analysis WHERE strategy_id=500").fetchone()
check('el post-trade REAL se sigue guardando', row is not None, str(row))

# ── (3) analyzed_at en hora AR, no UTC ───────────────────────────────────────
print('\n[3] analyzed_at sellado en AR (no el DEFAULT UTC)')
ts = datetime.strptime(str(row[2]).split('.')[0], '%Y-%m-%d %H:%M:%S')
ar_ahora = dbmod.now_ar()
if hasattr(ar_ahora, 'replace'):
    ar_ahora = ar_ahora.replace(tzinfo=None)
delta_ar = abs((ts - ar_ahora).total_seconds())
check('analyzed_at ~= now_ar() (segundos, no 3 horas)', delta_ar < 120, f'delta={delta_ar:.0f}s')
utc_default = sqlite3.connect(tmp).execute("SELECT datetime('now')").fetchone()[0]
delta_utc = abs((ts - datetime.strptime(utc_default, '%Y-%m-%d %H:%M:%S')).total_seconds())
check('y NO coincide con el DEFAULT UTC (queda ~3h de diferencia)', delta_utc > 3000,
      f'delta_utc={delta_utc:.0f}s')

# MUTACION: sin el fix, el DEFAULT habria puesto UTC
cm = sqlite3.connect(tmp)
cm.execute("INSERT INTO post_trade_analysis (strategy_id, result) VALUES (500,'win')")
cm.commit()
viejo = cm.execute("SELECT analyzed_at FROM post_trade_analysis ORDER BY id DESC LIMIT 1").fetchone()[0]
cm.close()
d_viejo = abs((datetime.strptime(str(viejo).split('.')[0], '%Y-%m-%d %H:%M:%S') - ar_ahora).total_seconds())
check('MUTACION: el DEFAULT sin now_ar() se va ~3h (era el bug)', d_viejo > 3000, f'delta={d_viejo:.0f}s')

dbmod._connect = _orig_connect

# ── (4) la limpieza dejo la DB de prod sana ──────────────────────────────────
print('\n[4] produccion: las filas del test ya no estan, las reales si')
prod = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
p = sqlite3.connect(prod)
max_real = max(p.execute("SELECT MAX(id) FROM auto_strategies").fetchone()[0],
               p.execute("SELECT MAX(strategy_id) FROM trade_archive").fetchone()[0])
n999 = p.execute("SELECT COUNT(*) FROM post_trade_analysis WHERE strategy_id > ?", (max_real,)).fetchone()[0]
check('0 post_trade_analysis con strategy_id imposible', n999 == 0, f'quedan={n999}')
n999sr = p.execute("SELECT COUNT(*) FROM strategy_results WHERE strategy_id > ?", (max_real,)).fetchone()[0]
check('0 strategy_results con strategy_id imposible', n999sr == 0, f'quedan={n999sr}')
n_pt = p.execute("SELECT COUNT(*) FROM post_trade_analysis").fetchone()[0]
check('los analisis REALES siguen (589 = 619 - 30)', n_pt == 589, f'hay={n_pt}')
n_arch = p.execute("SELECT COUNT(*) FROM trade_archive").fetchone()[0]
check('trade_archive INTACTO (585, la limpieza no lo toca)', n_arch == 585, f'hay={n_arch}')
ok = p.execute("PRAGMA integrity_check").fetchone()[0]
check('integrity_check ok', ok == 'ok', str(ok))
# el respaldo existe
bdir = os.path.join(os.environ['APPDATA'], 'AIdan', 'backups')
check('backup pre-limpieza guardado', any(f.startswith('pre_clean_test_rows_') for f in os.listdir(bdir)))
check('CSV de lo borrado guardado', any(f.startswith('test_rows_removed_') for f in os.listdir(bdir)))
p.close()

print('\n' + '=' * 60)
ok_n = sum(1 for _, c_, _ in RESULTS if c_)
print(f'{ok_n}/{len(RESULTS)} OK')
for n_, c_, d in RESULTS:
    if not c_:
        print(f'  FAIL: {n_}  {d}')
sys.exit(0 if ok_n == len(RESULTS) else 1)
