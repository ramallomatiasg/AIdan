"""
Tests v3.58.2 — Shadow book (rejected_signals): hooks de call-site + helper.

Cubre:
  1. Los 3 hooks existen en el bloque m15 del monolito (atr_floor SIN direccion,
     counter_both y active_opposite CON direccion) — tests de CALL-SITE.
  2. El hook del gate de ATR NO corre el detector (correrlo contaminaria los
     shadows de pullback/fade-chop que escriben desde adentro) — test de mutacion.
  3. log_rejected_signal escribe la fila correcta (DB temporal) y falla LOUD.
  4. El throttle del gate es por vela M15 (900s), no por ciclo.
"""
import os
import re
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
MONO = os.path.join(ROOT, 'AIdan_TodoEnUno.py')


def _m15_block():
    with open(MONO, encoding='utf-8') as f:
        src = f.read()
    start = src.find("Track B: M15 structure scan paralelo")
    end = src.find("h1_structure", start)
    return src[start:end if end > start else len(src)]


class TestHooks(unittest.TestCase):
    def setUp(self):
        self.block = _m15_block()
        self.assertTrue(len(self.block) > 1000, "bloque m15 no encontrado")

    def test_atr_floor_hook_exists_without_direction(self):
        m = re.search(r"log_rejected_signal\(\s*'m15_structure',\s*'atr_floor',\s*direction=None", self.block)
        self.assertIsNotNone(m, "hook atr_floor sin direccion no encontrado")

    def test_directional_hooks_exist(self):
        for reason in ('counter_both', 'active_opposite'):
            m = re.search(rf"'{reason}',\s*\n?\s*direction=_m15_dir", self.block)
            self.assertIsNotNone(m, f"hook {reason} con direccion no encontrado")

    def test_atr_hook_does_not_run_detector(self):
        """Mutacion: entre el gate de ATR y el hook NO puede aparecer una llamada a
        detect_structure_signals (contaminaria pullback/fade-chop shadow)."""
        gate = self.block.find("'atr_floor'")
        scan = self.block.find("detect_structure_signals")
        self.assertGreater(scan, gate, "el detector corre ANTES del hook de atr_floor "
                           "(o el hook desaparecio)")

    def test_throttle_is_per_candle(self):
        self.assertIn("> 900", self.block, "throttle de 900s (1 fila por vela M15) ausente")

    def test_hooks_are_guarded(self):
        """Cada hook en try/except: instrumentacion nunca tumba el scan."""
        n_hooks = self.block.count("log_rejected_signal(")
        n_guards = len(re.findall(r"except Exception as _rj_e", self.block))
        self.assertEqual(n_hooks, 3)
        self.assertEqual(n_guards, 3)


class TestHelper(unittest.TestCase):
    def test_writes_and_defaults(self):
        import src.common.db as db
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute("""CREATE TABLE rejected_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, track TEXT NOT NULL,
            reason TEXT NOT NULL, direction TEXT, confidence REAL, price REAL,
            atr_pips REAL, horizon_min INTEGER DEFAULT 45, fav_pips REAL,
            adv_pips REAL, abs_move_pips REAL, net_drift_pips REAL,
            scored_at TEXT, created_at TEXT)""")
        conn.commit()
        conn.close()
        orig = db.DB_PATH
        try:
            db.DB_PATH = tmp.name
            db.log_rejected_signal('m15_structure', 'atr_floor', price=1.1, atr_pips=4.2)
            db.log_rejected_signal('m15_structure', 'counter_both', direction='PUT',
                                   confidence=71, price=1.1, atr_pips=9.0)
            conn = sqlite3.connect(tmp.name)
            rows = conn.execute(
                "SELECT reason, direction, scored_at, created_at FROM rejected_signals "
                "ORDER BY id").fetchall()
            conn.close()
            self.assertEqual(len(rows), 2)
            self.assertIsNone(rows[0][1])          # atr_floor sin direccion
            self.assertEqual(rows[1][1], 'PUT')
            for r in rows:
                self.assertIsNone(r[2], "scored_at debe nacer NULL (pendiente)")
                self.assertIsNotNone(r[3], "created_at vacio")
        finally:
            db.DB_PATH = orig
            os.unlink(tmp.name)

    def test_fail_loud(self):
        with open(os.path.join(ROOT, 'src', 'common', 'db.py'), encoding='utf-8') as f:
            src = f.read()
        m = re.search(r"def log_rejected_signal\(.*?(?=\ndef )", src, re.S)
        self.assertIsNotNone(m)
        self.assertIn("warning", m.group(0))
        self.assertNotIn("logger.debug", m.group(0))


class TestScorerReadOnly(unittest.TestCase):
    def test_scorer_only_writes_own_table(self):
        """El scorer solo puede escribir en rejected_signals (su instrumentacion)."""
        with open(os.path.join(ROOT, 'tools', 'score_rejected_signals.py'),
                  encoding='utf-8') as f:
            src = f.read()
        writes = re.findall(r"(?:UPDATE|INSERT INTO|DELETE FROM)\s+(\w+)", src)
        self.assertTrue(writes, "el scorer no escribe outcomes?")
        self.assertEqual(set(writes), {'rejected_signals'})


if __name__ == '__main__':
    unittest.main(verbosity=1)
