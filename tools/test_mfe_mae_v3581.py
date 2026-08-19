"""
Tests v3.58.1 — MFE/MAE: excursion favorable y adversa persistida por trade.

Que cubre (call-site + mutacion + E2E contra COPIA de la DB, nunca produccion):
  1. El loop de trailing trackea low_water con min() y lo persiste.
  2. update_mt5_low_water solo puede BAJAR el valle (MIN en SQL).
  3. archive_trade convierte watermarks precio->pips y PRESERVA NULL.
  4. El fallback de get_trade_excursion devuelve PIPS, no precio (bugfix).
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MONO = os.path.join(ROOT, 'AIdan_TodoEnUno.py')
PROD_DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')


class TestTrailingLoopCallSite(unittest.TestCase):
    def setUp(self):
        with open(MONO, encoding='utf-8') as f:
            self.src = f.read()

    def test_low_water_tracked_with_min(self):
        """Mutacion: el MAE tiene que salir de min(stored, progress) — un max() aca
        lo convertiria en un segundo MFE y nadie lo notaria."""
        m = re.search(r"low_water = (min|max)\(stored_lwm or 0, progress\)", self.src)
        self.assertIsNotNone(m, "tracking de low_water no encontrado en el loop")
        self.assertEqual(m.group(1), 'min')

    def test_low_water_persisted(self):
        self.assertIn("update_mt5_low_water(sid, low_water)", self.src)

    def test_low_water_import(self):
        self.assertIn("update_mt5_low_water)", self.src.replace('\n', ' ').replace('  ', ' ')
                      if False else self.src)


class TestLowWaterMinSemantics(unittest.TestCase):
    def _tmp_db(self):
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE auto_strategies (id INTEGER PRIMARY KEY, mt5_low_water REAL)")
        conn.execute("INSERT INTO auto_strategies (id) VALUES (1)")
        conn.commit()
        conn.close()
        return tmp.name

    def test_valley_never_rises(self):
        import src.common.db as db
        path = self._tmp_db()
        orig = db.DB_PATH
        try:
            db.DB_PATH = path
            db.update_mt5_low_water(1, -0.0008)
            db.update_mt5_low_water(1, -0.0002)   # valle "mas alto" -> no debe pisar
            conn = sqlite3.connect(path)
            v = conn.execute("SELECT mt5_low_water FROM auto_strategies WHERE id=1").fetchone()[0]
            conn.close()
            self.assertAlmostEqual(v, -0.0008, places=6)
        finally:
            db.DB_PATH = orig
            os.unlink(path)


class TestArchiveWritesExcursion(unittest.TestCase):
    """E2E contra una COPIA de la DB de produccion."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        cls.tmp.close()
        shutil.copy2(PROD_DB, cls.tmp.name)
        # Correr la MIGRACION REAL sobre la copia (la prod la corre el exe al arrancar).
        # Esto ademas verifica que init_db() agrega las columnas nuevas sin romper.
        import src.common.db as db
        orig = db.DB_PATH
        try:
            db.DB_PATH = cls.tmp.name
            db.init_db()
        finally:
            db.DB_PATH = orig

    @classmethod
    def tearDownClass(cls):
        import gc
        gc.collect()
        try:
            os.unlink(cls.tmp.name)
        except PermissionError:
            pass  # Windows: alguna conexion viva; el archivo queda en %TEMP%

    def _archive(self, sid, hwm, lwm):
        import src.common.db as db
        assert db.DB_PATH != self.tmp.name or True
        orig = db.DB_PATH
        try:
            db.DB_PATH = self.tmp.name
            conn = sqlite3.connect(self.tmp.name)
            conn.execute("""INSERT INTO auto_strategies
                (id, direction, entry_price, stop_loss, take_profit, confidence,
                 trigger_type, mt5_pnl, mt5_fill_price, mt5_ticket, mt5_status,
                 mt5_high_water, mt5_low_water, created_at)
                VALUES (?, 'CALL', 1.1000, 1.0985, 1.1020, 70, 'm15_structure',
                        -2.5, 1.1001, 424242, 'closed', ?, ?, '2026-08-19 10:00:00')""",
                (sid, hwm, lwm))
            conn.commit()
            conn.close()
            db.archive_trade(sid, 'loss', 1.0985, -16.0)
            conn = sqlite3.connect(self.tmp.name)
            row = conn.execute(
                "SELECT mfe_pips, mae_pips FROM trade_archive WHERE strategy_id=?", (sid,)).fetchone()
            conn.close()
            return row
        finally:
            db.DB_PATH = orig

    def test_price_units_converted_to_pips(self):
        row = self._archive(990001, 0.00055, -0.0016)
        self.assertIsNotNone(row, "no se archivo")
        self.assertAlmostEqual(row[0], 5.5, places=1)
        self.assertAlmostEqual(row[1], -16.0, places=1)

    def test_null_preserved(self):
        """NULL != 0: 'no muestreado' tiene que quedar distinguible de 'excursion 0'."""
        row = self._archive(990002, None, None)
        self.assertIsNotNone(row)
        self.assertIsNone(row[0])
        self.assertIsNone(row[1])

    def test_production_untouched(self):
        conn = sqlite3.connect(f'file:{PROD_DB}?mode=ro', uri=True)
        n = conn.execute("SELECT COUNT(*) FROM trade_archive WHERE strategy_id >= 990000").fetchone()[0]
        conn.close()
        self.assertEqual(n, 0, "EL TEST ESCRIBIO EN PRODUCCION")


class TestExcursionFallbackUnits(unittest.TestCase):
    def test_fallback_returns_pips_not_price(self):
        """Bugfix v3.58.1: el fallback devolvia mt5_high_water crudo (precio) como pips."""
        import src.common.db as db
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE position_manager_log (strategy_id INTEGER, hwm_pips REAL, created_at TEXT)")
        conn.execute("CREATE TABLE auto_strategies (id INTEGER PRIMARY KEY, mt5_high_water REAL)")
        conn.execute("INSERT INTO auto_strategies VALUES (7, 0.0007)")  # 7 pips en precio
        conn.commit()
        conn.close()
        orig = db.DB_PATH
        try:
            db.DB_PATH = tmp.name
            exc = db.get_trade_excursion(7)
            self.assertIsNotNone(exc)
            self.assertAlmostEqual(exc['mfe_pips'], 7.0, places=1)
        finally:
            db.DB_PATH = orig
            os.unlink(tmp.name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
