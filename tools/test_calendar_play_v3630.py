"""
test_calendar_play_v3630.py — tests del shadow "calendar play" (v3.63.0).

NO toca la DB de produccion ni la red ni MT5: todo con dobles (leccion v3.53.6).

Cubre, en orden de importancia:
  1. FRONTERA: el modulo no puede ejecutar. Regex sobre el fuente: sin order_send,
     open_position, add_auto_strategy, _try_mt5_execute, close_*. Y el bloque del
     monolito que lo arranca tampoco.
  2. El parser de titulos Forexlive ('X vs Y expected') con titulos reales del feed
     y con negativos (discursos, sin numero, 'vs' sin 'expected').
  3. El resumen de la ruta en pips: excursiones arriba/abajo, spread maximo del
     primer minuto, closes por offset (ultimo sample <= offset).
  4. record_release con reloj y sleep inyectados: escribe UNA fila por evento del
     grupo, misma ruta; sin tick pre => no escribe nada.
  5. start('off') no lanza thread. La tabla tiene las columnas que el scorer lee.
  6. El except del start en el monolito loguea como error (no traga).
"""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.analyzer import calendar_play as cp  # noqa: E402

SRC = open(os.path.join(ROOT, 'src', 'analyzer', 'calendar_play.py'), encoding='utf-8').read()
MONO = open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8').read()
DB = open(os.path.join(ROOT, 'src', 'common', 'db.py'), encoding='utf-8').read()


def _sin_comentarios(txt):
    return '\n'.join(l for l in txt.splitlines() if not l.strip().startswith('#'))


class TestFrontera(unittest.TestCase):
    def test_modulo_no_ejecuta(self):
        code = _sin_comentarios(SRC)
        # sacar el docstring del modulo (explica lo que NO hace, y eso matchea)
        code = code.split('"""', 2)[-1]
        for prohibido in ('order_send', 'open_position', 'add_auto_strategy', '_try_mt5_execute',
                          'close_strategy_position', 'close_all_positions', 'TRADE_ACTION'):
            self.assertNotIn(prohibido, code, f"calendar_play no puede contener {prohibido}")

    def test_modulo_solo_escribe_en_su_tabla(self):
        code = _sin_comentarios(SRC).split('"""', 2)[-1]
        for prohibido in ('auto_strategies', 'trade_archive', 'update_mt5_', 'archive_trade'):
            self.assertNotIn(prohibido, code)
        self.assertIn('log_calendar_play', code)

    def test_no_existe_modo_active(self):
        self.assertNotIn("'active'", _sin_comentarios(SRC).split('"""', 2)[-1])

    def test_bloque_del_monolito(self):
        ini = MONO.index('v3.63.0 — CALENDAR PLAY (shadow): thread propio')
        fin = MONO.index('except Exception as _cp_e', ini)
        bloque = _sin_comentarios(MONO[ini:fin])
        self.assertIn('_cp_mod.start(', bloque)
        self.assertNotIn('add_auto_strategy', bloque)
        self.assertNotIn('_try_mt5_execute', bloque)
        cola = MONO[fin:fin + 160]
        self.assertIn('logger.error', cola)

    def test_getter_sigue_reconexiones(self):
        # si pasara mt5_exec por valor, un reconnect dejaria al shadow con el executor viejo
        self.assertIn("lambda: getattr(self, '_mt5_exec', None)", MONO)


class TestParser(unittest.TestCase):
    def test_titulos_reales(self):
        self.assertEqual(cp.parse_vs_title('US August CPI +2.9% vs +2.9% expected'), (2.9, 2.9))
        self.assertEqual(cp.parse_vs_title('US initial jobless claims 263K vs 235K estimate'), (263000.0, 235000.0))
        self.assertEqual(cp.parse_vs_title('Eurozone August final CPI 2.1% vs 2.0% expected'), (2.1, 2.0))
        self.assertEqual(cp.parse_vs_title('US July core PCE +0.3% vs +0.3% exp'), (0.3, 0.3))
        self.assertEqual(cp.parse_vs_title('US Q2 GDP second estimate 3.3% vs 3.1% expected'), (3.3, 3.1))

    def test_negativos(self):
        self.assertIsNone(cp.parse_vs_title('ECB President Lagarde speaks'))
        self.assertIsNone(cp.parse_vs_title('Dollar vs euro: what to watch this week'))
        self.assertIsNone(cp.parse_vs_title(''))
        self.assertIsNone(cp.parse_vs_title(None))

    def test_parse_number(self):
        self.assertEqual(cp.parse_number('2.9%'), 2.9)
        self.assertEqual(cp.parse_number('-0.1'), -0.1)
        self.assertEqual(cp.parse_number('263K'), 263000.0)
        self.assertEqual(cp.parse_number('1.2M'), 1200000.0)
        self.assertIsNone(cp.parse_number(''))
        self.assertIsNone(cp.parse_number(None))

    def test_match_evento(self):
        self.assertTrue(cp.title_matches_event('US August CPI +2.9% vs +2.9% expected', 'CPI m/m'))
        self.assertTrue(cp.title_matches_event('US initial jobless claims 263K vs 235K estimate', 'Unemployment Claims'))
        self.assertFalse(cp.title_matches_event('Fed Waller speech', 'Core CPI m/m'))


class TestRuta(unittest.TestCase):
    def test_resumen(self):
        pre_bid, pre_ask = 1.1000, 1.1001            # mid 1.10005, spread 1p
        samples = [(1, 1.1005, 1.1008),              # mid 1.10065 => +6p, spread 3p
                   (30, 1.0990, 1.0991),             # mid 1.09905 => -10p
                   (70, 1.1010, 1.1011),             # mid 1.10105 => +10p (fuera de los 60s)
                   (200, 1.1020, 1.1021),            # mid 1.10205 => +20p (fuera de los 3 min)
                   (890, 1.0985, 1.0986)]            # mid 1.09855 => -15p
        s = cp.summarize_path(pre_bid, pre_ask, samples)
        self.assertEqual(s['pre_spread'], 1.0)
        self.assertEqual(s['spread_max_60s'], 3.0)
        self.assertAlmostEqual(s['max_up_3m'], 10.0, places=1)
        self.assertAlmostEqual(s['max_down_3m'], 10.0, places=1)
        self.assertAlmostEqual(s['max_up_15m'], 20.0, places=1)
        self.assertAlmostEqual(s['max_down_15m'], 15.0, places=1)
        self.assertAlmostEqual(s['close_1m'], -10.0, places=1)   # ultimo <=60s
        self.assertAlmostEqual(s['close_3m'], 10.0, places=1)    # ultimo <=180s
        self.assertAlmostEqual(s['close_5m'], 20.0, places=1)
        self.assertAlmostEqual(s['close_15m'], -15.0, places=1)

    def test_sin_samples(self):
        s = cp.summarize_path(1.1, 1.1001, [])
        self.assertEqual(s['max_up_3m'], 0.0)
        self.assertEqual(s['close_5m'], 0.0)


class _FakeDB:
    def __init__(self):
        self.rows = []
        self.updates = []

    def log_calendar_play(self, **kw):
        self.rows.append(kw)

    def update_calendar_play_actual(self, k, actual, source, expected=None):
        self.updates.append((k, actual, source, expected))

    def calendar_play_already_logged(self, k):
        return any(r['event_key'] == k for r in self.rows)


class _FakeExec:
    def __init__(self, ticks):
        self.ticks = list(ticks)

    def get_tick(self):
        if not self.ticks:
            return None
        return self.ticks.pop(0) if len(self.ticks) > 1 else self.ticks[0]


class TestRecord(unittest.TestCase):
    def _run(self, ticks, n_events=1):
        T = 1_000_000.0
        clock = {'t': T - 100}
        def fake_clock():
            return clock['t']
        def fake_sleep(s):
            clock['t'] += s
        evs = [{'event': f'Evento {i}', 'currency': 'USD', 'impact': 'High', 'release_ts': T,
                'forecast': '0.2%', 'previous': '0.1%', 'actual': ''} for i in range(n_events)]
        ex = _FakeExec(ticks)
        db = _FakeDB()
        keys = cp.record_release(evs, lambda: ex, db, sleep=fake_sleep, clock=fake_clock)
        return keys, db, clock['t'] - T

    def test_una_fila_por_evento_misma_ruta(self):
        keys, db, dur = self._run([{'bid': 1.1, 'ask': 1.1001}, {'bid': 1.1005, 'ask': 1.1007}], n_events=3)
        self.assertEqual(len(keys), 3)
        self.assertEqual(len(db.rows), 3)
        self.assertEqual(len({r['samples_json'] for r in db.rows}), 1, 'los 3 comparten la ruta')
        self.assertEqual(db.rows[0]['pre_bid'], 1.1)
        self.assertGreaterEqual(dur, cp.TOTAL_UNTIL_S)
        self.assertLess(dur, cp.TOTAL_UNTIL_S + 15)

    def test_sin_tick_pre_no_escribe(self):
        keys, db, _ = self._run([])
        self.assertIsNone(keys)
        self.assertEqual(db.rows, [])

    def test_event_key_idempotente(self):
        ev = {'event': 'CPI m/m', 'release_ts': 123.0}
        self.assertEqual(cp.event_key(ev), cp.event_key(dict(ev)))
        self.assertEqual(cp.event_key(ev), 'CPI m/m|123')


class TestStartYTabla(unittest.TestCase):
    def test_off_no_lanza(self):
        self.assertIsNone(cp.start(lambda: None, _FakeDB(), 'off'))
        self.assertIsNone(cp.start(lambda: None, _FakeDB(), 'OFF'))

    def test_tabla_tiene_lo_que_lee_el_scorer(self):
        i = DB.index('CREATE TABLE IF NOT EXISTS calendar_play_log')
        ddl = DB[i:DB.index(')', i + 200) + 1] if False else DB[i:i + 1500]
        for col in ('event_key TEXT UNIQUE', 'release_ts', 'forecast', 'actual', 'actual_source',
                    'pre_spread', 'spread_max_60s', 'max_up_3m', 'max_down_3m', 'close_5m',
                    'samples_json', 'created_at'):
            self.assertIn(col, ddl)

    def test_db_funcs_existen_y_fallan_cerrado(self):
        from src.common import db
        for fn in ('calendar_play_already_logged', 'log_calendar_play',
                   'update_calendar_play_actual', 'news_titles_between'):
            self.assertTrue(callable(getattr(db, fn)))
        # already_logged devuelve True ante error (no duplicar el n del shadow)
        src_fn = DB[DB.index('def calendar_play_already_logged'):DB.index('def log_calendar_play')]
        self.assertIn('return True', src_fn.split('except Exception:')[1])

    def test_perilla_en_config(self):
        from src.common.config import Config
        self.assertIn(Config.CALENDAR_PLAY_MODE, ('off', 'shadow'))


if __name__ == '__main__':
    unittest.main(verbosity=1)
