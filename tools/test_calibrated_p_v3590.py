# -*- coding: utf-8 -*-
"""Tests v3.59.0 — P calibrada en FASE REGISTRO (calibrated_p).

Cubre las 4 formas en que esto podria mentir:
  (1) Formula: que el modulo congelado reproduzca EXACTAMENTE apply_platt()
      del calibrador que paso el gate (mismos 4 params, misma sigmoid).
  (2) Alcance: solo m15_structure devuelve valor; el resto None (None, no 0.5).
  (3) E2E call-site: add_auto_strategy contra una DB TEMPORAL registra
      calibrated_p en entry_context — y sobre la confianza FINAL, no la previa.
      (Leccion v3.57.0: un test que solo ejercita la funcion habria estado en
      verde los 5 meses en que adjust_setup_confidence estuvo muerto.)
  (4) Inercia: que calibrated_p NO se consuma en ningun path de decision
      (ejecutor, detectores, position manager, monolito) — es registro puro.

DB temporal. No necesita MT5 ni Ollama.
"""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('  OK   ' if cond else '  FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''))


# ── (1) la formula congelada == la del calibrador ────────────────────────────
print('\n[1] formula: modulo congelado vs apply_platt del calibrador')
from src.analyzer.confidence_calibration import calibrated_p, FROZEN_PARAMS

_spec = importlib.util.spec_from_file_location(
    'cal', os.path.join(ROOT, 'tools', 'calibrate_confidence.py'))
_cal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cal)

_p = FROZEN_PARAMS['m15_structure']
_tuple = (_p['a'], _p['b'], _p['mu'], _p['sd'])
_ok = all(
    abs(calibrated_p('m15_structure', c) - _cal.apply_platt(_tuple, c)) < 5e-5
    for c in (30, 47.5, 60, 70, 79.9, 85, 90, 99))
check('sigmoid identica en 8 confianzas', _ok)
check('monotona creciente', calibrated_p('m15_structure', 60)
      < calibrated_p('m15_structure', 75) < calibrated_p('m15_structure', 90))
check('rango sano (0,1)', 0.0 < calibrated_p('m15_structure', 1) and calibrated_p('m15_structure', 99) < 1.0)

# ── (2) alcance ───────────────────────────────────────────────────────────────
print('\n[2] alcance: solo el track que paso el gate')
check('structure -> None', calibrated_p('structure', 75) is None)
check('news -> None', calibrated_p('news', 75) is None)
check('h1_structure -> None', calibrated_p('h1_structure', 75) is None)
check('smc -> None', calibrated_p('smc', 75) is None)
check('conf None -> None', calibrated_p('m15_structure', None) is None)
check('conf basura -> None (no explota)', calibrated_p('m15_structure', 'alta') is None)

# ── (3) E2E: add_auto_strategy registra sobre DB temporal ────────────────────
print('\n[3] E2E call-site: add_auto_strategy -> entry_context.calibrated_p')
import src.common.db as dbmod

_orig_db_path = dbmod.DB_PATH
_tmpdb = os.path.join(tempfile.mkdtemp(prefix='aidan_calp3590_'), 'test.db')
dbmod.DB_PATH = _tmpdb
assert dbmod.DB_PATH != _orig_db_path
try:
    dbmod.init_db()
    _sid = dbmod.add_auto_strategy(
        alert_id=None, news_title='[TEST v3.59.0] calibrated_p',
        direction='CALL', entry_price=1.1000, stop_loss=1.0985,
        take_profit=1.1060, confidence=90, impact_score=70,
        expiry_minutes=45, trigger_type='m15_structure',
        entry_context={'timeframe': 'M15', 'setup_type': 'trend_continuation_bull'})
    check('la estrategia se creo en la DB temporal', _sid is not None, f'sid={_sid}')
    if _sid:
        _row = sqlite3.connect(_tmpdb).execute(
            "SELECT entry_context, confidence FROM auto_strategies WHERE id=?", (_sid,)).fetchone()
        _ctx = json.loads(_row[0]) if _row and _row[0] else {}
        check('entry_context tiene calibrated_p', 'calibrated_p' in _ctx, str(_ctx)[:120])
        # sobre la confianza FINAL guardada (post meta/retro), no la de entrada
        _expected = calibrated_p('m15_structure', _row[1])
        check('calculada sobre la conf GUARDADA', abs(_ctx.get('calibrated_p', -1) - _expected) < 5e-5,
              f"ctx={_ctx.get('calibrated_p')} esperada={_expected} conf_guardada={_row[1]}")

    # un track sin calibracion NO registra la clave
    # (retro-datar la m15 para no chocar con el cooldown global de 2 min)
    _c = sqlite3.connect(_tmpdb)
    _c.execute("UPDATE auto_strategies SET created_at = datetime(created_at, '-30 minutes')")
    _c.commit(); _c.close()
    _sid2 = dbmod.add_auto_strategy(
        alert_id=None, news_title='[TEST v3.59.0] sin calibracion',
        direction='CALL', entry_price=1.2000, stop_loss=1.1960,
        take_profit=1.2100, confidence=75, impact_score=70,
        expiry_minutes=180, trigger_type='h1_structure',
        entry_context={'timeframe': 'H1'})
    if _sid2:
        _row2 = sqlite3.connect(_tmpdb).execute(
            "SELECT entry_context FROM auto_strategies WHERE id=?", (_sid2,)).fetchone()
        _ctx2 = json.loads(_row2[0]) if _row2 and _row2[0] else {}
        check('h1 NO registra calibrated_p', 'calibrated_p' not in _ctx2)
    else:
        check('h1 NO registra calibrated_p', False, 'no se pudo crear la estrategia h1')
finally:
    dbmod.DB_PATH = _orig_db_path
check('DB_PATH restaurado a produccion', dbmod.DB_PATH == _orig_db_path)

# ── (4) inercia: nadie consume calibrated_p para decidir ─────────────────────
print('\n[4] inercia: calibrated_p no aparece en ningun path de decision')
_decision_files = [
    'AIdan_TodoEnUno.py',
    os.path.join('src', 'broker', 'mt5_executor.py'),
    os.path.join('src', 'analyzer', 'technical.py'),
    os.path.join('src', 'analyzer', 'technical_m15.py'),
    os.path.join('src', 'broker', 'position_manager.py'),
    os.path.join('src', 'optimizer', 'change_manager.py'),
]
for _f in _decision_files:
    _path = os.path.join(ROOT, _f)
    if not os.path.exists(_path):
        check(f'{_f}: existe', False, 'archivo no encontrado')
        continue
    _src = open(_path, encoding='utf-8', errors='replace').read()
    check(f'{_f}: sin calibrated_p', 'calibrated_p' not in _src)

# db.py SI la tiene, pero solo en el hook de registro (1 import + 1 asignacion)
_dbsrc = open(os.path.join(ROOT, 'src', 'common', 'db.py'), encoding='utf-8', errors='replace').read()
check('db.py: importa el modulo congelado',
      'from src.analyzer.confidence_calibration import calibrated_p' in _dbsrc)
check('db.py: asigna a entry_context (registro)',
      "entry_context['calibrated_p']" in _dbsrc)
_uses = _dbsrc.count('calibrated_p')
check('db.py: sin usos extra (solo registro)', _uses <= 4, f'apariciones={_uses}')

# ── resumen ───────────────────────────────────────────────────────────────────
_fails = [r for r in RESULTS if not r[1]]
print('\n' + '=' * 60)
print('%d checks, %d FAIL' % (len(RESULTS), len(_fails)))
sys.exit(1 if _fails else 0)
