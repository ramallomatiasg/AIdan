"""v3.53.5 + v3.53.6 — Tests del kill switch del dashboard y del UNIQUE de trade_archive.

v3.53.5 — KILL SWITCH DEL DASHBOARD (src/admin/main.py, POST /mt5/toggle). Tres defectos
en el mismo bloque:
  (a) el P&L sumaba SOLO los deals con `d.entry == 1` => perdia la comision de ENTRADA
      (la mitad del round-turn), mientras sync_closed_positions suma TODOS => habia DOS
      formulas distintas escribiendo la misma columna mt5_pnl, y ganaba la ultima.
  (b) escribia mt5_status='closed' INCONDICIONALMENTE, con pnl=0.0 y close_price=0.0 si
      no habia deals: si close_all_positions habia fallado para ese ticket, la posicion
      quedaba VIVA en el broker pero invisible para el trailing y el Position Manager
      (los dos filtran mt5_status='filled'). Y un cierre plano se etiquetaba auto_loss.
  (c) escribia con SQL a mano en vez de update_mt5_close => se salteaba el backfill de
      v3.50.3, y sostenia el write-lock de SQLite mientras llamaba al broker.

v3.53.6 — UNIQUE INDEX en trade_archive(strategy_id): defensa en profundidad para el
check-then-insert de archive_trade (SELECT y INSERT con ~100 lineas en el medio).

Correr: python tools/test_killswitch_dash_and_unique_v3535.py
"""
import os
import re
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class Deal:
    def __init__(self, entry, profit, commission, price, swap=0.0):
        self.entry = entry
        self.profit = profit
        self.commission = commission
        self.swap = swap
        self.price = price


APERTURA = Deal(entry=0, profit=0.0, commission=-0.35, price=1.16000)
CIERRE = Deal(entry=1, profit=1.00, commission=-0.35, price=1.16100)


def pnl_VIEJO(deals):
    """La formula que tenia el endpoint: solo los deals de cierre."""
    pnl, cp = 0.0, 0.0
    for d in deals or []:
        if d.entry == 1:
            pnl += d.profit + d.swap + d.commission
            cp = d.price
    return pnl, cp


def pnl_NUEVO(deals):
    """La del fix: todos los deals, igual que sync_closed_positions."""
    pnl, cp = 0.0, 0.0
    for d in deals or []:
        pnl += d.profit + d.swap + d.commission
        if d.entry == 1:
            cp = d.price
    return pnl, cp


class TestFormulaDelPnL(unittest.TestCase):

    def test_la_formula_vieja_perdia_la_comision_de_entrada(self):
        v, _ = pnl_VIEJO([APERTURA, CIERRE])
        self.assertAlmostEqual(v, 0.65, places=6,
                               msg="la vieja daba +0.65: le falta la comision de entrada")

    def test_la_nueva_da_el_neto_real(self):
        n, cp = pnl_NUEVO([APERTURA, CIERRE])
        self.assertAlmostEqual(n, 0.30, places=6, msg="1.00 - 0.35 - 0.35 = +0.30")
        self.assertAlmostEqual(cp, 1.16100, places=5)

    def test_coincide_con_sync_closed_positions(self):
        """LO QUE IMPORTA: una sola formula escribiendo mt5_pnl."""
        from src.broker import mt5_executor  # noqa: F401  (solo para fijar el contrato)
        # la de sync es: pnl += profit + swap + commission para TODOS los deals
        esperado = sum(d.profit + d.swap + d.commission for d in [APERTURA, CIERRE])
        n, _ = pnl_NUEVO([APERTURA, CIERRE])
        self.assertAlmostEqual(n, esperado, places=6)

    def test_un_perdedor_no_queda_inflado_ni_desinflado(self):
        ci = Deal(entry=1, profit=-2.00, commission=-0.35, price=1.15800)
        n, _ = pnl_NUEVO([APERTURA, ci])
        self.assertAlmostEqual(n, -2.70, places=6)


class TestNoMarcarClosedSinEvidencia(unittest.TestCase):
    """El defecto (b): sin deal de cierre no se puede afirmar que la posicion cerro."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'src', 'admin', 'main.py'), encoding='utf-8') as fh:
            cls.src = fh.read()

    def _bloque(self):
        i = self.src.find('KILL-SWITCH EVAL v3.53.5')
        self.assertNotEqual(i, -1, "no se encontro el marcador del fix")
        crudo = self.src[i:i + 4000]
        return '\n'.join(ln for ln in crudo.splitlines()
                         if not ln.strip().startswith('#'))

    def test_hay_un_guard_de_close_price_antes_de_escribir(self):
        blk = self._bloque()
        i_guard = blk.find('if close_price == 0')
        i_write = blk.find('update_mt5_close(')
        self.assertNotEqual(i_guard, -1, "falta el guard de close_price")
        self.assertNotEqual(i_write, -1, "falta la escritura via update_mt5_close")
        self.assertLess(i_guard, i_write,
                        "el guard tiene que estar ANTES de escribir el cierre")

    def test_el_guard_saltea_la_estrategia(self):
        blk = self._bloque()
        i = blk.find('if close_price == 0')
        self.assertIn('continue', blk[i:i + 400],
                      "sin deal de cierre hay que SALTEAR, no escribir 'closed'")

    def test_ya_no_escribe_mt5_status_closed_a_mano(self):
        blk = self._bloque()
        self.assertNotIn("mt5_status='closed'", blk,
                         "el cierre se escribe via update_mt5_close (que corre el backfill "
                         "de v3.50.3), no con SQL a mano")

    def test_usa_update_mt5_close(self):
        self.assertIn('update_mt5_close', self._bloque())

    def test_no_sostiene_el_write_lock_mientras_llama_al_broker(self):
        """(c): antes la transaccion quedaba abierta durante history_deals_get."""
        blk = self._bloque()
        i_close_conn = blk.find('conn.close()')
        i_deals = blk.find('history_deals_get')
        self.assertNotEqual(i_close_conn, -1)
        self.assertNotEqual(i_deals, -1)
        self.assertLess(i_close_conn, i_deals,
                        "la conexion de lectura debe cerrarse ANTES de consultar al broker")


class TestUniqueIndex(unittest.TestCase):
    """v3.53.6 — el UNIQUE y el INSERT OR IGNORE que lo acompana."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, 'u.db')
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE trade_archive (id INTEGER PRIMARY KEY, strategy_id INTEGER, "
                  "result TEXT, mt5_pnl REAL)")
        c.execute("CREATE INDEX idx_trade_archive_strategy ON trade_archive(strategy_id)")
        c.commit()
        c.close()

    def _migrar(self):
        """Replica del bloque de migracion de db.py."""
        c = sqlite3.connect(self.db)
        cur = c.cursor()
        dups = cur.execute(
            "SELECT COUNT(*) FROM (SELECT strategy_id FROM trade_archive "
            "GROUP BY strategy_id HAVING COUNT(*) > 1)").fetchone()[0]
        creado = False
        if not dups:
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_archive_strategy_uniq "
                        "ON trade_archive(strategy_id)")
            cur.execute("DROP INDEX IF EXISTS idx_trade_archive_strategy")
            creado = True
        c.commit()
        c.close()
        return dups, creado

    def _indices(self):
        c = sqlite3.connect(self.db)
        out = {r[1]: r[2] for r in c.execute("PRAGMA index_list('trade_archive')")}
        c.close()
        return out

    def test_crea_el_unique_y_borra_el_viejo(self):
        dups, creado = self._migrar()
        self.assertEqual(dups, 0)
        self.assertTrue(creado)
        idx = self._indices()
        self.assertIn('idx_trade_archive_strategy_uniq', idx)
        self.assertEqual(idx['idx_trade_archive_strategy_uniq'], 1, "debe ser UNIQUE")
        self.assertNotIn('idx_trade_archive_strategy', idx, "el viejo no-unico se borra")

    def test_con_duplicados_NO_crea_el_unique_y_conserva_el_viejo(self):
        """No se puede crear el UNIQUE sobre duplicados, y el histórico no se toca."""
        c = sqlite3.connect(self.db)
        c.execute("INSERT INTO trade_archive (strategy_id, result) VALUES (7,'win')")
        c.execute("INSERT INTO trade_archive (strategy_id, result) VALUES (7,'loss')")
        c.commit()
        c.close()
        dups, creado = self._migrar()
        self.assertEqual(dups, 1)
        self.assertFalse(creado)
        idx = self._indices()
        self.assertIn('idx_trade_archive_strategy', idx, "el indice viejo sobrevive")
        self.assertNotIn('idx_trade_archive_strategy_uniq', idx)

    def test_insert_or_ignore_no_tira_al_duplicar(self):
        self._migrar()
        c = sqlite3.connect(self.db)
        c.execute("INSERT OR IGNORE INTO trade_archive (strategy_id, result, mt5_pnl) "
                  "VALUES (9,'win',1.5)")
        c.commit()
        # segundo intento con el mismo strategy_id: no debe tirar ni duplicar
        c.execute("INSERT OR IGNORE INTO trade_archive (strategy_id, result, mt5_pnl) "
                  "VALUES (9,'loss',-9.9)")
        c.commit()
        filas = c.execute("SELECT result, mt5_pnl FROM trade_archive "
                          "WHERE strategy_id=9").fetchall()
        c.close()
        self.assertEqual(len(filas), 1, "una sola fila por strategy_id")
        self.assertEqual(filas[0][0], 'win', "gana la PRIMERA, no la ultima")

    def test_el_insert_sin_or_ignore_SI_tiraria(self):
        """Control: confirma que el UNIQUE de verdad esta activo."""
        self._migrar()
        c = sqlite3.connect(self.db)
        c.execute("INSERT INTO trade_archive (strategy_id, result) VALUES (11,'win')")
        c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO trade_archive (strategy_id, result) VALUES (11,'loss')")
        c.close()


class TestCodigoRealDb(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'src', 'common', 'db.py'), encoding='utf-8') as fh:
            cls.src = fh.read()

    def test_los_inserts_con_check_usan_or_ignore(self):
        n = self.src.count('INSERT OR IGNORE INTO trade_archive')
        self.assertEqual(n, 2, f"se esperaban los 2 inserts con check-then-insert, hay {n}")

    def test_la_migracion_verifica_duplicados_primero(self):
        i = self.src.find('UNIQUE en trade_archive(strategy_id)')
        self.assertNotEqual(i, -1, "falta el bloque de migracion del UNIQUE")
        blk = self.src[i:i + 2000]
        i_dups = blk.find('HAVING COUNT(*) > 1')
        i_create = blk.find('CREATE UNIQUE INDEX')
        self.assertNotEqual(i_dups, -1,
                            "hay que contar duplicados antes de intentar el UNIQUE")
        self.assertLess(i_dups, i_create,
                        "el conteo de duplicados va ANTES del CREATE UNIQUE")

    def test_la_migracion_no_esta_dentro_del_loop_que_traga(self):
        """El loop de indices tiene `except Exception: pass`. El UNIQUE va aparte para
        poder loguear si no se pudo crear."""
        i_loop = self.src.find('for idx_sql in indexes:')
        i_uniq = self.src.find('CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_archive_strategy_uniq')
        self.assertNotEqual(i_uniq, -1)
        self.assertLess(i_loop, i_uniq, "el UNIQUE va despues del loop, no adentro")
        entre = self.src[i_loop:i_uniq]
        self.assertIn('warning', entre, "el bloque del UNIQUE tiene que poder avisar")


if __name__ == '__main__':
    unittest.main(verbosity=2)
