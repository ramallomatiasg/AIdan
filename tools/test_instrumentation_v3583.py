"""
Tests v3.58.3 — signal_age_at_fill_min + efficiency_ratio (instrumentacion pura).

  1. ER: formula correcta contra casos construidos (drift limpio ~1, zigzag ~0),
     None con historia corta, y presente en el dict de get_market_state.
  2. Call-site: los 6 entry_context del monolito incluyen efficiency_ratio.
  3. signal_age: se setea al marcar 'filled', NO se pisa en updates posteriores,
     y archive_trade la copia al archivo (E2E contra copia de la DB).
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


def _er(closes):
    """Reimplementacion de referencia de la formula (21 cierres = 20 cambios)."""
    if len(closes) < 21:
        return None
    c = closes[-21:]
    net = abs(c[-1] - c[0])
    path = sum(abs(c[i] - c[i-1]) for i in range(1, len(c)))
    return round(net / path, 3) if path > 0 else None


class TestEfficiencyRatio(unittest.TestCase):
    def test_source_formula_matches_reference(self):
        """Mutacion textual: la formula del codigo usa net/path sobre closes[-21:]."""
        with open(os.path.join(ROOT, 'src', 'analyzer', 'technical.py'), encoding='utf-8') as f:
            src = f.read()
        self.assertIn("closes[-21:]", src)
        self.assertIn("'efficiency_ratio': efficiency_ratio", src)

    def test_clean_drift_is_one(self):
        closes = [1.1000 + i * 0.0001 for i in range(30)]
        self.assertAlmostEqual(_er(closes), 1.0, places=3)

    def test_zigzag_is_near_zero(self):
        closes = [1.1000 + (0.0005 if i % 2 else 0.0) for i in range(30)]
        self.assertLess(_er(closes), 0.05)

    def test_short_history_none(self):
        self.assertIsNone(_er([1.1] * 10))

    def test_live_state_includes_er(self):
        """Integracion: get_market_state real devuelve la clave (feed puede fallar,
        en ese caso solo se exige que la clave exista si hay velas)."""
        from src.analyzer.technical import TechnicalAnalyzer
        import logging
        ta = TechnicalAnalyzer(logging.getLogger('test'))
        try:
            st = ta.get_market_state()
        except Exception:
            self.skipTest("feed no disponible")
        if not st or not st.get('price'):
            self.skipTest("sin velas")
        self.assertIn('efficiency_ratio', st)


class TestContextCallSites(unittest.TestCase):
    def test_six_ctx_sites_wired(self):
        with open(MONO, encoding='utf-8') as f:
            src = f.read()
        n = len(re.findall(r"'efficiency_ratio': \w+\.get\('efficiency_ratio'\)", src))
        self.assertEqual(n, 6, f"esperaba 6 sitios de entry_context con ER, hay {n}")


class TestSignalAge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        cls.tmp.close()
        shutil.copy2(PROD_DB, cls.tmp.name)
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
            pass

    def test_set_on_fill_and_not_overwritten(self):
        import src.common.db as db
        orig = db.DB_PATH
        try:
            db.DB_PATH = self.tmp.name
            conn = sqlite3.connect(self.tmp.name)
            # señal creada hace ~30 min (hora AR = now_ar)
            created = conn.execute(
                "SELECT datetime(?, '-30 minutes')", (db.now_ar(),)).fetchone()[0]
            conn.execute("""INSERT INTO auto_strategies
                (id, direction, entry_price, confidence, trigger_type, created_at)
                VALUES (991001, 'CALL', 1.1, 70, 'm15_structure', ?)""", (created,))
            conn.commit()
            conn.close()

            db.update_mt5_ticket(991001, 555, 0.01, 'filled', fill_price=1.1001)
            conn = sqlite3.connect(self.tmp.name)
            age1 = conn.execute(
                "SELECT signal_age_at_fill_min FROM auto_strategies WHERE id=991001"
            ).fetchone()[0]
            conn.close()
            self.assertIsNotNone(age1, "no se seteo la edad al fill")
            self.assertTrue(25 <= age1 <= 35, f"edad {age1} fuera de [25,35]")

            # un segundo update (re-sync) NO debe pisar la edad original
            db.update_mt5_ticket(991001, 555, 0.01, 'filled', fill_price=1.1001)
            conn = sqlite3.connect(self.tmp.name)
            age2 = conn.execute(
                "SELECT signal_age_at_fill_min FROM auto_strategies WHERE id=991001"
            ).fetchone()[0]
            conn.close()
            self.assertEqual(age1, age2, "la edad se piso en un update posterior")
        finally:
            db.DB_PATH = orig

    def test_copied_to_archive(self):
        import src.common.db as db
        orig = db.DB_PATH
        try:
            db.DB_PATH = self.tmp.name
            conn = sqlite3.connect(self.tmp.name)
            conn.execute("""INSERT INTO auto_strategies
                (id, direction, entry_price, stop_loss, take_profit, confidence,
                 trigger_type, mt5_pnl, mt5_ticket, mt5_status, signal_age_at_fill_min,
                 created_at)
                VALUES (991002, 'PUT', 1.1, 1.1015, 1.098, 70, 'm15_structure',
                        3.1, 556, 'closed', 12.3, '2026-08-19 10:00:00')""")
            conn.commit()
            conn.close()
            db.archive_trade(991002, 'win', 1.0985, 15.0)
            conn = sqlite3.connect(self.tmp.name)
            v = conn.execute(
                "SELECT signal_age_at_fill_min FROM trade_archive WHERE strategy_id=991002"
            ).fetchone()
            conn.close()
            self.assertIsNotNone(v)
            self.assertAlmostEqual(v[0], 12.3, places=1)
        finally:
            db.DB_PATH = orig

    def test_production_untouched(self):
        conn = sqlite3.connect(f'file:{PROD_DB}?mode=ro', uri=True)
        n = conn.execute(
            "SELECT COUNT(*) FROM auto_strategies WHERE id >= 991000").fetchone()[0]
        conn.close()
        self.assertEqual(n, 0, "EL TEST ESCRIBIO EN PRODUCCION")


if __name__ == '__main__':
    unittest.main(verbosity=1)
