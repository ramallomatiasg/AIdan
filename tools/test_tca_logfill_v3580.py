"""
Tests v3.58.0 — TCA: log_fill() enchufado al path de ejecucion.

Historia: src/common/slippage_tracker.py existia desde hace meses con log_fill()
definido y CERO call-sites (slippage_log = 0 filas, verificado 19-ago). Es el 9no
mecanismo "construido y desconectado" del proyecto. Estos tests son de CALL-SITE:
un test que solo ejercitara log_fill() habria estado verde todos esos meses.

No toca MT5 ni la DB de produccion (log_fill se prueba contra una DB temporal).
"""
import ast
import os
import re
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

EXECUTOR = os.path.join(ROOT, 'src', 'broker', 'mt5_executor.py')
TRACKER = os.path.join(ROOT, 'src', 'common', 'slippage_tracker.py')


class TestCallSite(unittest.TestCase):
    def setUp(self):
        with open(EXECUTOR, encoding='utf-8') as f:
            self.src = f.read()

    def test_market_order_calls_log_fill(self):
        """El unico path vivo de entrada (_market_order) debe invocar log_fill."""
        m = re.search(r"def _market_order\(.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(m, "_market_order no encontrado")
        body = m.group(0)
        self.assertIn("log_fill(", body, "log_fill no se llama en _market_order")

    def test_log_fill_inside_done_branch(self):
        """Mutacion: el hook tiene que estar DENTRO de la rama retcode==DONE
        (loguear fills que no ocurrieron seria peor que no loguear)."""
        m = re.search(r"def _market_order\(.*?(?=\n    def )", self.src, re.S)
        body = m.group(0)
        done_idx = body.find("TRADE_RETCODE_DONE")
        else_idx = body.find("order failed", done_idx)
        hook_idx = body.find("log_fill(")
        self.assertGreater(hook_idx, done_idx, "hook antes del branch DONE")
        self.assertLess(hook_idx, else_idx, "hook fuera de la rama DONE")

    def test_hook_is_guarded(self):
        """El hook no puede tumbar la ejecucion: debe estar en try/except propio."""
        m = re.search(r"def _market_order\(.*?(?=\n    def )", self.src, re.S)
        body = m.group(0)
        hook_region = body[body.find("log_fill(") - 400: body.find("log_fill(") + 200]
        self.assertIn("try:", hook_region)
        self.assertIn("except", hook_region)

    def test_uses_result_price_not_requested(self):
        """El actual debe salir de result.price (fill real), no del pedido."""
        m = re.search(r"def _market_order\(.*?(?=\n    def )", self.src, re.S)
        body = m.group(0)
        self.assertIn("getattr(result, 'price'", body)


class TestTrackerFailLoud(unittest.TestCase):
    def test_no_silent_debug_in_write_path(self):
        """La clase de bug que mato M15/SMC: except a logger.debug. El path de
        escritura del TCA tiene que fallar a WARNING como minimo."""
        with open(TRACKER, encoding='utf-8') as f:
            src = f.read()
        for fn in ('_ensure_table', 'log_fill'):
            m = re.search(rf"def {fn}\(.*?(?=\ndef )", src, re.S)
            self.assertIsNotNone(m, f"{fn} no encontrada")
            self.assertNotIn("logger.debug", m.group(0),
                             f"{fn} traga excepciones a debug (fail-silent)")


class TestLogFillWrites(unittest.TestCase):
    def test_writes_row_to_temp_db(self):
        """log_fill escribe una fila correcta (contra DB temporal, nunca prod)."""
        import src.common.db as db
        import src.common.slippage_tracker as st
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        orig = db.DB_PATH
        try:
            db.DB_PATH = tmp.name
            st.log_fill(999999, 1.10000, 1.10012, 'CALL', spread_pips=0.8)
            conn = sqlite3.connect(tmp.name)
            row = conn.execute(
                "SELECT strategy_id, slippage_pips, spread_pips, direction "
                "FROM slippage_log").fetchone()
            conn.close()
            self.assertIsNotNone(row, "log_fill no escribio nada")
            self.assertEqual(row[0], 999999)
            self.assertAlmostEqual(row[1], 1.2, places=2)  # (1.10012-1.10000)*1e4, CALL: + = peor
            self.assertAlmostEqual(row[2], 0.8, places=2)
            self.assertEqual(row[3], 'CALL')
        finally:
            db.DB_PATH = orig
            os.unlink(tmp.name)

    def test_put_sign_convention(self):
        """PUT: fill mas BAJO que el pedido = peor => slippage positivo."""
        import src.common.db as db
        import src.common.slippage_tracker as st
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        orig = db.DB_PATH
        try:
            db.DB_PATH = tmp.name
            st.log_fill(1, 1.10000, 1.09990, 'PUT')
            conn = sqlite3.connect(tmp.name)
            slip = conn.execute("SELECT slippage_pips FROM slippage_log").fetchone()[0]
            conn.close()
            self.assertAlmostEqual(slip, 1.0, places=2)
        finally:
            db.DB_PATH = orig
            os.unlink(tmp.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
