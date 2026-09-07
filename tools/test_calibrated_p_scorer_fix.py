"""Tests del fix del scorer `score_calibrated_p_forward.py` (7-sep-2026).

El bug: el scorer leia `entry_context` de `auto_strategies` (JOIN) y contaba "registradas"
solo ahi. Pero el cap-delete PODA `auto_strategies` (quedan ~6 filas vivas), asi que los
trades cerrados desaparecen de esa tabla => el scorer decia "CERO registros -> hook MUERTO"
cuando los 4 m15 desde el deploy SI tenian `calibrated_p` en `trade_archive.entry_context`.
Falsa alarma de la peor clase: la que hace desconfiar del tripwire real.

Se testea contra una DB temporal con el escenario exacto: archive con `calibrated_p`,
`auto_strategies` vacia (podada). El scorer tiene que MEDIR esos trades y NO alertar.
Y el tripwire tiene que seguir vivo: trades post-deploy SIN registro en ninguna tabla
=> alerta.

Correr con: python tools/test_calibrated_p_scorer_fix.py
"""
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import score_calibrated_p_forward as scorer  # noqa: E402

TRACK = 'm15_structure'
POST = '2026-09-03 12:16:01'   # despues del deploy 2026-08-21


def _mk_db(path):
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE auto_strategies (id INTEGER PRIMARY KEY, trigger_type TEXT,
                 entry_context TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE trade_archive (id INTEGER PRIMARY KEY, strategy_id INTEGER,
                 trigger_type TEXT, result TEXT, mt5_pnl REAL, created_at TEXT,
                 entry_context TEXT)""")
    c.commit()
    return c


def _run():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        scorer.main()
    return buf.getvalue()


class TestScorerLeeElArchive(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, 't.db')
        self._orig = scorer.DB_PATH
        scorer.DB_PATH = self.db

    def tearDown(self):
        scorer.DB_PATH = self._orig

    def test_archive_con_registro_y_auto_strategies_podada(self):
        """El escenario real del 7-sep: cap-delete se llevo las filas de auto_strategies."""
        c = _mk_db(self.db)
        for i, (res, p) in enumerate([('win', 0.4858), ('loss', 0.5446), ('loss', 0.5026)]):
            c.execute("INSERT INTO trade_archive VALUES (?,?,?,?,?,?,?)",
                      (i + 1, 960 + i, TRACK, res, 1.0 if res == 'win' else -1.0, POST,
                       json.dumps({'timeframe': 'M15', 'calibrated_p': p})))
        c.commit(); c.close()
        out = _run()
        self.assertNotIn('ALERTA', out)
        self.assertNotIn('hook de add_auto_strategy puede estar MUERTO', out)
        self.assertIn('cerrados forward: n=3', out)
        self.assertIn('registradas', out)

    def test_tripwire_sigue_vivo_sin_registro_en_ninguna_tabla(self):
        """Trades post-deploy sin calibrated_p en archive NI en auto_strategies => alerta."""
        c = _mk_db(self.db)
        c.execute("INSERT INTO trade_archive VALUES (1, 971, ?, 'loss', -1.0, ?, ?)",
                  (TRACK, POST, json.dumps({'timeframe': 'M15'})))
        c.commit(); c.close()
        out = _run()
        self.assertIn('ALERTA', out)
        self.assertIn('cerrados con calibrated_p: 0', out)

    def test_viva_en_auto_strategies_cuenta_como_registrada(self):
        """Una posicion abierta con registro (todavia no archivada) mantiene el tripwire
        en silencio aunque no haya cerrados."""
        c = _mk_db(self.db)
        c.execute("INSERT INTO auto_strategies VALUES (980, ?, ?, ?)",
                  (TRACK, json.dumps({'calibrated_p': 0.51}), POST))
        c.execute("INSERT INTO trade_archive VALUES (1, 971, ?, 'loss', -1.0, ?, ?)",
                  (TRACK, POST, json.dumps({'timeframe': 'M15'})))
        c.commit(); c.close()
        out = _run()
        self.assertNotIn('ALERTA', out)
        self.assertIn('registradas (cerradas 0 + vivas 1)', out)

    def test_fallback_a_auto_strategies_si_el_archive_no_tiene_context(self):
        """Fila vieja: archive sin entry_context pero auto_strategies aun con la fila."""
        c = _mk_db(self.db)
        c.execute("INSERT INTO auto_strategies VALUES (962, ?, ?, ?)",
                  (TRACK, json.dumps({'calibrated_p': 0.4858}), POST))
        c.execute("INSERT INTO trade_archive VALUES (1, 962, ?, 'win', 1.0, ?, NULL)",
                  (TRACK, POST))
        c.commit(); c.close()
        out = _run()
        self.assertIn('cerrados forward: n=1', out)

    def test_el_scorer_no_escribe(self):
        src = open(os.path.join(ROOT, 'tools', 'score_calibrated_p_forward.py'), encoding='utf-8').read()
        for kw in ('INSERT', 'UPDATE ', 'DELETE', 'ALTER'):
            self.assertNotIn(kw, src.split('def main')[1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
