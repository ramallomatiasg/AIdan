"""v3.52.1 — Tests del fix de la AMNESIA DEL HWM.

El bug: en run_trailing_monitor la escritura del high-water vivia bajo `if success:`,
y el respaldo era el `elif` de `new_sl is not None`, NO de `success`. Cuando el trailing
decidia mover el SL y el broker rechazaba el modify, ese ciclo perdia el pico -- y el
pico no se recupera, porque al ciclo siguiente high_water se recalcula como
max(stored_hwm_viejo, progress_actual).

Se testea (a) el helper nuevo update_mt5_high_water contra una DB temporal real, y
(b) la ESTRUCTURA del bloque en el fuente, que es donde vivia el bug.

Correr con: python tools/test_hwm_amnesia_v3521.py
"""
import ast
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class TestHelperHwmOnly(unittest.TestCase):
    """El helper escribe el pico y NO toca step ni be_triggered."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, 'test.db')
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE auto_strategies (
            id INTEGER PRIMARY KEY, mt5_trailing_step INTEGER DEFAULT 0,
            mt5_high_water REAL, be_triggered INTEGER DEFAULT 0)""")
        conn.execute("INSERT INTO auto_strategies (id, mt5_trailing_step, mt5_high_water, "
                     "be_triggered) VALUES (1, 0, 0.0005, 0)")
        conn.commit()
        conn.close()
        import src.common.db as dbmod
        self._orig = dbmod.DB_PATH
        dbmod.DB_PATH = self.db
        self.dbmod = dbmod

    def tearDown(self):
        self.dbmod.DB_PATH = self._orig

    def _row(self):
        conn = sqlite3.connect(self.db)
        r = conn.execute("SELECT mt5_trailing_step, mt5_high_water, be_triggered "
                         "FROM auto_strategies WHERE id=1").fetchone()
        conn.close()
        return r

    def test_persiste_el_pico(self):
        self.dbmod.update_mt5_high_water(1, 0.0011)
        step, hwm, be = self._row()
        self.assertAlmostEqual(hwm, 0.0011, places=7)

    def test_no_toca_step_ni_be_triggered(self):
        """El SL no se movio => marcar step/be_triggered seria mentir sobre el stop."""
        self.dbmod.update_mt5_high_water(1, 0.0011)
        step, hwm, be = self._row()
        self.assertEqual(step, 0, "el step no se debe tocar")
        self.assertEqual(be, 0, "be_triggered no se debe encender")

    def test_es_monotonico_no_baja_el_pico(self):
        self.dbmod.update_mt5_high_water(1, 0.0011)
        self.dbmod.update_mt5_high_water(1, 0.0003)   # intento de bajarlo
        _, hwm, _ = self._row()
        self.assertAlmostEqual(hwm, 0.0011, places=7, msg="el pico nunca puede bajar")

    def test_null_previo_no_rompe(self):
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE auto_strategies SET mt5_high_water = NULL WHERE id=1")
        conn.commit()
        conn.close()
        self.dbmod.update_mt5_high_water(1, 0.0007)
        _, hwm, _ = self._row()
        self.assertAlmostEqual(hwm, 0.0007, places=7)

    def test_strategy_inexistente_no_crashea(self):
        self.dbmod.update_mt5_high_water(99999, 0.0011)  # no debe tirar

    def test_contraste_con_update_mt5_trailing_data(self):
        """El helper viejo SI enciende be_triggered: por eso hacia falta uno nuevo."""
        self.dbmod.update_mt5_trailing_data(1, 1, 0.0011)
        step, hwm, be = self._row()
        self.assertEqual(step, 1)
        self.assertEqual(be, 1, "el helper viejo enciende be_triggered (por eso no servia)")


class TestEstructuraDelBloque(unittest.TestCase):
    """El bug era ESTRUCTURAL (un elif colgado del if equivocado). Se fija en el AST
    para que un refactor futuro no lo reintroduzca en silencio."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8') as fh:
            cls.tree = ast.parse(fh.read())

    def _bloque_modify(self):
        """Encuentra el `if new_sl is not None:` del trailing monitor."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'run_trailing_monitor':
                for n in ast.walk(node):
                    if (isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                            and isinstance(n.test.left, ast.Name)
                            and n.test.left.id == 'new_sl'):
                        return n
        return None

    def test_existe_el_bloque(self):
        self.assertIsNotNone(self._bloque_modify(), "no se encontro `if new_sl is not None`")

    def test_el_if_success_tiene_rama_else(self):
        """EL TEST QUE CAZA EL BUG: si `if success:` no tiene rama else, el ciclo en que
        el modify falla vuelve a perder el pico."""
        blk = self._bloque_modify()
        ifs = [n for n in blk.body if isinstance(n, ast.If)
               and isinstance(n.test, ast.Name) and n.test.id == 'success']
        self.assertEqual(len(ifs), 1, "se esperaba un solo `if success:`")
        self.assertTrue(ifs[0].orelse,
                        "`if success:` DEBE tener rama else: sin ella, cuando el modify "
                        "falla se pierde el high-water (bug v3.52.1)")

    def test_la_rama_else_persiste_el_hwm(self):
        blk = self._bloque_modify()
        succ = [n for n in blk.body if isinstance(n, ast.If)
                and isinstance(n.test, ast.Name) and n.test.id == 'success'][0]
        llamadas = {n.func.id for n in ast.walk(ast.Module(body=succ.orelse, type_ignores=[]))
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn('update_mt5_high_water', llamadas,
                      "la rama de fallo debe persistir el pico")

    def test_la_rama_else_NO_usa_el_helper_que_pisa_el_step(self):
        """El 'fix naive' que la nota de deuda tecnica advertia: usar
        update_mt5_trailing_data ahi pisaria el step y encenderia be_triggered."""
        blk = self._bloque_modify()
        succ = [n for n in blk.body if isinstance(n, ast.If)
                and isinstance(n.test, ast.Name) and n.test.id == 'success'][0]
        llamadas = {n.func.id for n in ast.walk(ast.Module(body=succ.orelse, type_ignores=[]))
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertNotIn('update_mt5_trailing_data', llamadas,
                         "en la rama de fallo el SL NO se movio: escribir el step seria mentir")

    def test_el_import_esta_en_el_mismo_scope(self):
        """La clase de bug de v3.50.4 (SMC) y v3.33.0 (M15): nombre resuelto desde otro
        scope + excepcion tragada = subsistema muerto en silencio."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'run_trailing_monitor':
                importados = set()
                for n in ast.walk(node):
                    if isinstance(n, (ast.Import, ast.ImportFrom)):
                        for a in n.names:
                            importados.add(a.asname or a.name.split('.')[0])
                self.assertIn('update_mt5_high_water', importados,
                              "debe importarse DENTRO del metodo, no depender de otro scope")
                return
        self.fail("no se encontro run_trailing_monitor")


class TestSimulacionDelBug(unittest.TestCase):
    """Reproduce la perdida del pico con la estructura vieja vs la nueva."""

    def _ciclos(self, con_fix):
        """Simula 3 ciclos del trailing con el modify fallando en el ciclo del pico."""
        stored = 0.0
        picos = [0.0004, 0.0012, 0.0006]   # el precio sube a 12p y despues retrocede
        modify_ok = [True, False, True]     # el broker rechaza justo en el pico
        for progress, ok in zip(picos, modify_ok):
            high_water = max(stored, progress)
            be_active = high_water >= 0.0005
            new_sl = 0.0001 if be_active else None
            if new_sl is not None:
                if ok:
                    stored = high_water
                elif con_fix and high_water != stored and high_water > 0:
                    stored = high_water
            elif high_water != stored and high_water > 0:
                stored = high_water
        return stored

    def test_sin_fix_se_pierde_el_pico(self):
        self.assertAlmostEqual(self._ciclos(con_fix=False), 0.0006, places=7,
                               msg="estructura vieja: el pico de 12p se perdio, queda el de 6p")

    def test_con_fix_el_pico_sobrevive(self):
        self.assertAlmostEqual(self._ciclos(con_fix=True), 0.0012, places=7,
                               msg="con el fix el pico de 12p se conserva")


if __name__ == '__main__':
    unittest.main(verbosity=2)
