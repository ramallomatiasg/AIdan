"""v3.53.1 — Tests del cap-delete de auto_strategies.

EL BUG: add_auto_strategy mantiene un buffer rotativo de 6 filas. Cuando se pasa,
archiva las que estan 'closed' y despues ejecuta

    DELETE FROM auto_strategies WHERE id IN (
        SELECT id FROM auto_strategies ORDER BY created_at ASC LIMIT ?)

sin mirar mt5_status ni mt5_ticket => puede borrar la fila de una posicion VIVA. Si eso
pasa, la posicion sigue abierta en el broker pero desaparece del unico lugar donde AIdan
la registra: el trailing y el Position Manager filtran mt5_status='filled', asi que
dejan de gestionarla, sync_closed_positions no la encuentra y su P&L nunca entra al
track record.

Los tests corren contra una DB temporal (nunca produccion).

Correr con: python tools/test_cap_delete_v3531.py
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _cap_delete_VIEJO(conn, to_delete):
    """La consulta tal como estaba antes del fix. Existe para el test de mutacion."""
    conn.execute("""
        DELETE FROM auto_strategies WHERE id IN (
            SELECT id FROM auto_strategies ORDER BY created_at ASC LIMIT ?
        )
    """, (to_delete,))


class CapDeleteBase(unittest.TestCase):
    """Arma un buffer de prueba con posiciones vivas y cerradas."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, 'cap.db')
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE auto_strategies (
            id INTEGER PRIMARY KEY, direction TEXT, entry_price REAL, stop_loss REAL,
            take_profit REAL, confidence INTEGER, impact_score INTEGER, trigger_type TEXT,
            news_title TEXT, profile_name TEXT, created_at TEXT, mt5_pnl REAL,
            mt5_close_price REAL, mt5_status TEXT, status TEXT, mt5_fill_price REAL,
            mt5_ticket INTEGER, expiry_minutes INTEGER, expires_at TEXT)""")
        conn.execute("CREATE TABLE strategy_results (strategy_id INTEGER, result TEXT)")
        base = datetime(2026, 8, 1, 10, 0, 0)
        # las 3 mas viejas: una VIVA (filled), una pendiente, una cerrada
        filas = [
            (1, 'filled',  1848000001, 'la mas vieja pero VIVA en el broker'),
            (2, 'pending', 1848000002, 'orden limite que puede llenarse'),
            (3, 'closed',  1848000003, 'cerrada, se puede borrar'),
            (4, 'closed',  1848000004, 'cerrada'),
            (5, None,      None,       'nunca se ejecuto'),
            (6, 'closed',  1848000006, 'cerrada'),
        ]
        for i, (sid, st, ticket, _n) in enumerate(filas):
            conn.execute(
                "INSERT INTO auto_strategies (id, direction, entry_price, mt5_status, "
                "mt5_ticket, mt5_close_price, created_at, status) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (sid, 'CALL', 1.16, st, ticket, 1.1610 if st == 'closed' else None,
                 (base + timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S'), 'active'))
            conn.execute("INSERT INTO strategy_results (strategy_id, result) VALUES (?,?)",
                         (sid, 'win'))
        conn.commit()
        conn.close()

    def _ids(self):
        conn = sqlite3.connect(self.db)
        ids = [r[0] for r in conn.execute("SELECT id FROM auto_strategies ORDER BY id")]
        conn.close()
        return ids

    def _vivos_con_ticket(self):
        conn = sqlite3.connect(self.db)
        r = [x[0] for x in conn.execute(
            "SELECT id FROM auto_strategies WHERE mt5_ticket IS NOT NULL "
            "AND (mt5_status IS NULL OR mt5_status != 'closed')")]
        conn.close()
        return r


class TestElBugViejo(CapDeleteBase):
    """Test de mutacion: confirma que el bug era real y que el test tiene poder."""

    def test_la_consulta_vieja_BORRA_una_posicion_viva(self):
        conn = sqlite3.connect(self.db)
        _cap_delete_VIEJO(conn, 1)     # borrar 1: la mas vieja es #1, que esta 'filled'
        conn.commit()
        ids = [r[0] for r in conn.execute("SELECT id FROM auto_strategies ORDER BY id")]
        conn.close()
        self.assertNotIn(1, ids,
                         "con la consulta vieja la posicion VIVA #1 se borra — este es el bug")


class TestFixCapDelete(CapDeleteBase):
    """El fix: el DELETE saltea las filas con posicion potencialmente viva."""

    def _cap_delete_NUEVO(self, to_delete):
        """Replica del fix aplicado en db.py."""
        conn = sqlite3.connect(self.db)
        sub = """
            SELECT id FROM auto_strategies
            WHERE mt5_ticket IS NULL OR mt5_status = 'closed'
            ORDER BY created_at ASC LIMIT ?
        """
        conn.execute(f"DELETE FROM strategy_results WHERE strategy_id IN ({sub})", (to_delete,))
        conn.execute(f"DELETE FROM auto_strategies WHERE id IN ({sub})", (to_delete,))
        conn.commit()
        conn.close()

    def test_NO_borra_la_posicion_viva(self):
        self._cap_delete_NUEVO(1)
        self.assertIn(1, self._ids(), "#1 esta 'filled' => NO se puede borrar")

    def test_NO_borra_la_orden_pendiente(self):
        self._cap_delete_NUEVO(2)
        self.assertIn(2, self._ids(), "#2 esta 'pending': la orden puede llenarse todavia")

    def test_borra_la_mas_vieja_ENTRE_LAS_BORRABLES(self):
        self._cap_delete_NUEVO(1)
        ids = self._ids()
        self.assertNotIn(3, ids, "#3 es la mas vieja de las 'closed' => es la que sale")
        self.assertEqual(ids, [1, 2, 4, 5, 6])

    def test_borra_la_nunca_ejecutada(self):
        """#5 no tiene ticket: es seguro borrarla."""
        self._cap_delete_NUEVO(3)     # deberia sacar 3, 4 y 5
        self.assertEqual(self._ids(), [1, 2, 6])

    def test_nunca_borra_una_viva_ni_pidiendo_de_mas(self):
        """Aunque se pidan mas borrados que filas borrables, las vivas sobreviven."""
        self._cap_delete_NUEVO(99)
        self.assertEqual(self._ids(), [1, 2], "solo quedan las dos que no se pueden tocar")

    def test_los_votos_se_borran_junto_con_su_fila_y_solo_esos(self):
        self._cap_delete_NUEVO(1)
        conn = sqlite3.connect(self.db)
        votos = sorted(r[0] for r in conn.execute("SELECT strategy_id FROM strategy_results"))
        conn.close()
        self.assertEqual(votos, [1, 2, 4, 5, 6],
                         "se borra el voto de #3 (la fila borrada) y ninguno mas")

    def test_las_vivas_siguen_teniendo_su_ticket_intacto(self):
        antes = self._vivos_con_ticket()
        self._cap_delete_NUEVO(99)
        self.assertEqual(self._vivos_con_ticket(), antes)


class TestCodigoReal(unittest.TestCase):
    """Fija el fix en el fuente: si alguien vuelve a la consulta sin filtro, falla."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'src', 'common', 'db.py'), encoding='utf-8') as fh:
            cls.src = fh.read()

    def test_el_subselect_borrable_filtra_por_ticket_y_status(self):
        import re
        m = re.search(r'_deletable\s*=\s*"""(.*?)"""', self.src, re.S)
        self.assertIsNotNone(m, "no se encontro el subselect _deletable del cap-delete")
        sub = m.group(1)
        self.assertIn('mt5_ticket', sub,
                      "el subselect DEBE excluir las filas con posicion viva (mt5_ticket)")
        self.assertIn('mt5_status', sub, "el subselect DEBE mirar mt5_status")
        self.assertIn('ORDER BY created_at', sub, "sigue siendo FIFO entre las borrables")

    def test_los_DOS_delete_usan_el_MISMO_subselect(self):
        """Si los votos usaran el filtro viejo se borrarian los de una fila que se queda."""
        for tabla, col in (('auto_strategies', 'id'), ('strategy_results', 'strategy_id')):
            with self.subTest(tabla=tabla):
                self.assertIn(
                    f"DELETE FROM {tabla} WHERE {col} IN ({{_deletable}})", self.src,
                    f"el DELETE de {tabla} tiene que usar el subselect filtrado")

    def test_no_quedo_ningun_delete_sin_filtro(self):
        """Caza el patron viejo si un refactor lo reintroduce."""
        import re
        viejo = re.findall(
            r"DELETE FROM (?:auto_strategies|strategy_results)[^;]*?"
            r"SELECT id FROM auto_strategies ORDER BY created_at", self.src, re.S)
        self.assertEqual(viejo, [], f"quedo un DELETE sin filtro: {viejo}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
