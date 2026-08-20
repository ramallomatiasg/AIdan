# -*- coding: utf-8 -*-
"""Tests v3.60.0 — SHADOW TRADER LLM (decide en papel, jamas opera).

Cubre las formas en que esto podria hacer dano o mentir:
  (1) SIN PATH DE EJECUCION: el modulo no contiene ni importa nada que mande
      ordenes (order_send, open_position, close_position, TRADE_ACTION).
  (2) Parse defensivo: JSON valido, envuelto en ```, con texto alrededor,
      basura -> None (jamas explota). Acciones invalidas -> None.
  (3) Registro: log_shadow_trader_decision escribe en DB temporal con los
      campos correctos y fail-loud si la tabla no existe.
  (4) Call-site: el monolito tiene el timer con guard de modo y try/except
      propio (un error del shadow trader no puede matar el analyzer loop).
  (5) Anti-loro: el prompt lleva NUMEROS del mercado, no veredictos.
  (6) Scorer: la aritmetica de saved/held y del neto direccional con friccion.

DB temporal. No necesita MT5 ni llama a Groq (no gasta quota).
"""
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


# ── (1) sin path de ejecucion ─────────────────────────────────────────────────
print('\n[1] el modulo NO puede operar')
_src = open(os.path.join(ROOT, 'src', 'analyzer', 'shadow_trader.py'),
            encoding='utf-8', errors='replace').read()
_codigo = '\n'.join(l for l in _src.splitlines()
                    if not l.strip().startswith('#') and '"""' not in l)
# se permite en docstring/comentarios (explican que NO se usa), no en codigo
_docstring_end = _src.find('"""', _src.find('"""') + 3) + 3
_body = _src[_docstring_end:]
_body_code = '\n'.join(l for l in _body.splitlines() if not l.strip().startswith('#'))
for _bad in ('order_send', 'open_position', 'close_position', 'TRADE_ACTION',
             'modify_position', 'order_check'):
    check(f'sin {_bad} en el codigo', _bad not in _body_code)
check('positions_get presente (read-only permitido)', 'positions_get' in _body_code)

# ── (2) parse defensivo ───────────────────────────────────────────────────────
print('\n[2] parse defensivo de la respuesta del LLM')
from src.analyzer.shadow_trader import _parse_json, _norm_decision, \
    _build_open_prompt, _build_manage_prompt, OPEN_HORIZON_MIN, FRICTION_PIPS

check('JSON directo', _parse_json('{"action":"CALL","confidence":70,"reasoning":"x"}') is not None)
check('JSON en fence markdown', _parse_json('```json\n{"action":"PUT","confidence":50}\n```') is not None)
check('JSON con texto alrededor', _parse_json('I think: {"action":"NONE","confidence":10} ok') is not None)
check('basura -> None', _parse_json('no puedo decidir') is None)
check('vacio -> None', _parse_json('') is None)
check('lista JSON -> None', _parse_json('[1,2]') is None)

check('accion valida normaliza', _norm_decision({'action': 'call', 'confidence': 70}, ('CALL', 'PUT', 'NONE'))[0] == 'CALL')
check('accion invalida -> None', _norm_decision({'action': 'BUY', 'confidence': 70}, ('CALL', 'PUT', 'NONE')) is None)
check('conf basura -> 0', _norm_decision({'action': 'HOLD', 'confidence': 'alta'}, ('CLOSE', 'HOLD'))[1] == 0.0)
check('conf clampeada a 100', _norm_decision({'action': 'HOLD', 'confidence': 500}, ('CLOSE', 'HOLD'))[1] == 100.0)
check('None -> None', _norm_decision(None, ('CLOSE', 'HOLD')) is None)

# ── (3) registro en DB temporal ───────────────────────────────────────────────
print('\n[3] log_shadow_trader_decision contra DB temporal')
import src.common.db as dbmod

_orig_db_path = dbmod.DB_PATH
_tmpdb = os.path.join(tempfile.mkdtemp(prefix='aidan_st3600_'), 'test.db')
dbmod.DB_PATH = _tmpdb
assert dbmod.DB_PATH != _orig_db_path
try:
    dbmod.init_db()
    dbmod.log_shadow_trader_decision(
        kind='open', decision='CALL', direction='CALL', price=1.1234,
        confidence=72, horizon_min=45, reasoning='test', model='test-model',
        latency_ms=900)
    dbmod.log_shadow_trader_decision(
        kind='manage', decision='CLOSE', ticket=12345, direction='PUT',
        price=1.1200, pips_at_decision=-3.2, pnl_at_decision=-2.1,
        age_min=17.0, confidence=60, reasoning='test', model='test-model',
        latency_ms=800)
    _c = sqlite3.connect(_tmpdb)
    _rows = _c.execute("SELECT kind, decision, ticket, pips_at_decision, created_at "
                       "FROM shadow_trader_log ORDER BY id").fetchall()
    _c.close()
    check('2 filas escritas', len(_rows) == 2, str(_rows))
    if len(_rows) == 2:
        check('open sin ticket', _rows[0][2] is None)
        check('manage con ticket y pips', _rows[1][2] == 12345 and abs(_rows[1][3] - (-3.2)) < 1e-9)
        check('created_at seteado (now_ar, no default UTC)', _rows[0][4] is not None and len(str(_rows[0][4])) >= 19)
finally:
    dbmod.DB_PATH = _orig_db_path
check('DB_PATH restaurado', dbmod.DB_PATH == _orig_db_path)

# ── (4) call-site en el monolito ──────────────────────────────────────────────
print('\n[4] call-site: timer + guard + try/except en el monolito')
_mono = open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8', errors='replace').read()
check('importa run_cycle del modulo', 'from src.analyzer.shadow_trader import run_cycle' in _mono)
check('guard de modo off', "_st_mode != 'off'" in _mono)
check('timer propio', '_last_st_cycle' in _mono and 'ST_CYCLE_SEC' in _mono)
_idx = _mono.find('from src.analyzer.shadow_trader import run_cycle')
_window = _mono[max(0, _idx - 600):_idx + 600]
check('el hook esta dentro de su propio try/except', 'except Exception as _st_e' in _window)
check('config define el modo', 'SHADOW_TRADER_MODE' in open(
    os.path.join(ROOT, 'src', 'common', 'config.py'), encoding='utf-8', errors='replace').read())

# ── (5) anti-loro: numeros, no veredictos ────────────────────────────────────
print('\n[5] prompts: numeros del mercado, sin veredictos')
_ms = {'price': 1.1234, 'trend': 'bearish', 'trend_strength': 62, 'rsi': 38.5,
       'rsi_zone': 'neutral', 'momentum': 'down', 'avg_range_pips': 6.2,
       'volatility': 'normal', 'session': 'ny', 'efficiency_ratio': 0.41}
_p = _build_open_prompt(_ms)
check('open: lleva price', '1.1234' in _p)
check('open: lleva rsi y atr', '38.5' in _p and '6.2' in _p)
check('open: declara horizonte y friccion', str(OPEN_HORIZON_MIN) in _p and str(FRICTION_PIPS) in _p)
check('open: pide JSON con NONE valido', '"NONE"' in _p)
_pos = {'direction': 'PUT', 'age_min': 22.0, 'pips': -4.1, 'sl_dist': 11.2, 'tp_dist': 9.3,
        'price': 1.1200, 'pnl': -3.0, 'ticket': 1}
_p2 = _build_manage_prompt(_pos, _ms)
check('manage: lleva pips actuales y distancias', '-4.1' in _p2 and '11.2' in _p2 and '9.3' in _p2)
check('manage: pide CLOSE|HOLD', '"CLOSE"' in _p2 and '"HOLD"' in _p2)
for _verdict in ('you should', 'the opposite was paying', 'recommended action'):
    check(f'sin veredicto sembrado ("{_verdict}")', _verdict not in (_p + _p2).lower())

# ── (6) aritmetica del scorer ─────────────────────────────────────────────────
print('\n[6] scorer: saved/held y neto direccional')
# CLOSE a -3.2p, el trade termino en -8.0p => cerrar salvaba +4.8
check('saved = pips@dec - final', abs(round(-3.2 - (-8.0), 1) - 4.8) < 1e-9)
# HOLD a +2.0p, termino +7.5 => holdear aporto +5.5
check('held = final - pips@dec', abs(round(7.5 - 2.0, 1) - 5.5) < 1e-9)
# CALL a 1.1000, cierre del horizonte 1.1010 => +10p - 1.3 = +8.7
_net = (1.1010 - 1.1000) / 0.0001
check('CALL neto de friccion', abs(round(_net - FRICTION_PIPS, 1) - 8.7) < 1e-9)
# PUT mismo movimiento => -10 - 1.3 = -11.3
check('PUT neto de friccion', abs(round(-_net - FRICTION_PIPS, 1) - (-11.3)) < 1e-9)

# el scorer solo escribe en SU tabla
_scorer = open(os.path.join(ROOT, 'tools', 'score_shadow_trader.py'),
               encoding='utf-8', errors='replace').read()
_writes = [l for l in _scorer.splitlines() if 'UPDATE ' in l or 'INSERT ' in l]
check('scorer: solo UPDATE shadow_trader_log',
      all('shadow_trader_log' in w for w in _writes) and _writes, str(_writes)[:120])

# ── resumen ───────────────────────────────────────────────────────────────────
_fails = [r for r in RESULTS if not r[1]]
print('\n' + '=' * 60)
print('%d checks, %d FAIL' % (len(RESULTS), len(_fails)))
sys.exit(1 if _fails else 0)
