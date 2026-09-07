"""v3.62.0 — Tests del cache de SL del thread de trailing (spam de 1 modify/segundo).

El bug: en run_trailing_monitor el SL "actual" es auto_strategies.stop_loss (row[4]), el
ORIGINAL, que nunca se actualiza tras el modify. Con el BE armado, `candidate > sl +
MIN_SL_MOVE` era verdadero cada segundo => modify_position_sl + UPDATE + INFO por segundo
por posicion. El no-op guard de v3.50.1 frenaba el order_send pero devolvia True, asi que
se logueaba como exito y se escribia la DB igual. #944: 9.039 lineas identicas en 2,5 h.

Se testea (a) los helpers puros contra un dict real, y (b) la ESTRUCTURA del bloque en el
fuente: que el chequeo del cache vaya ANTES del modify, que el log de exito quede adentro
del path que SI envio, que el pico se persista igual cuando se saltea, y que un SL
DISTINTO (etapa TRAIL) siga pasando — este fix no puede convertir el trailing en un
"se envia una vez y nunca mas".

Correr con: python tools/test_trailing_sl_cache_v3620.py
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.broker.sl_cache import sl_already_sent, remember_sl, prune_sl_cache  # noqa: E402


class TestHelpers(unittest.TestCase):

    def test_vacio_no_esta_enviado(self):
        self.assertFalse(sl_already_sent({}, 1892659893, 1.15963))
        self.assertFalse(sl_already_sent(None, 1892659893, 1.15963))

    def test_mismo_sl_tras_remember_esta_enviado(self):
        c = {}
        remember_sl(c, 1892659893, 1.15963)
        self.assertTrue(sl_already_sent(c, 1892659893, 1.15963))
        # ruido de float por debajo del 5to decimal = el mismo precio para el broker
        self.assertTrue(sl_already_sent(c, 1892659893, 1.1596300000001))

    def test_sl_distinto_pasa(self):
        """Etapa TRAIL: el HWM sube, el candidato sube => tiene que reenviarse."""
        c = {}
        remember_sl(c, 7, 1.15963)
        self.assertFalse(sl_already_sent(c, 7, 1.15980))
        remember_sl(c, 7, 1.15980)
        self.assertTrue(sl_already_sent(c, 7, 1.15980))
        self.assertFalse(sl_already_sent(c, 7, 1.15963))

    def test_otro_ticket_no_contamina(self):
        c = {}
        remember_sl(c, 7, 1.15963)
        self.assertFalse(sl_already_sent(c, 8, 1.15963))

    def test_prune_saca_los_cerrados(self):
        c = {7: 1.1, 8: 1.2, 9: 1.3}
        prune_sl_cache(c, [8])
        self.assertEqual(set(c), {8})
        prune_sl_cache(c, [])
        self.assertEqual(c, {})
        prune_sl_cache(c, None)
        self.assertEqual(c, {})


class TestCallSite(unittest.TestCase):
    """La estructura del bloque de ejecucion del trailing en el fuente."""

    @classmethod
    def setUpClass(cls):
        src = open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8').read()
        m = re.search(r'def run_trailing_monitor\(', src)
        assert m, 'no encuentro run_trailing_monitor'
        end = src.find('\n    def ', m.end())
        cls.fn = src[m.start():end if end > 0 else None]

    def test_importa_y_arma_el_cache_antes_del_loop(self):
        i_imp = self.fn.find('from src.broker.sl_cache import')
        i_init = self.fn.find('_sl_sent = {}')
        i_loop = self.fn.find('while True:')
        self.assertGreater(i_imp, 0)
        self.assertGreater(i_init, 0)
        self.assertLess(i_imp, i_loop)
        self.assertLess(i_init, i_loop)

    def test_prune_por_ciclo(self):
        self.assertIn('prune_sl_cache(_sl_sent', self.fn)

    def test_chequeo_del_cache_antes_del_modify(self):
        i_chk = self.fn.find('sl_already_sent(_sl_sent, ticket, new_sl)')
        i_mod = self.fn.find('mt5.modify_position_sl(ticket, new_sl)')
        i_log = self.fn.find('Trailing[{stage_label}]')
        self.assertGreater(i_chk, 0)
        self.assertLess(i_chk, i_mod)
        self.assertLess(i_mod, i_log)

    def test_remember_solo_tras_exito(self):
        """Si el broker rechazo, el proximo ciclo tiene que volver a intentar."""
        i_mod = self.fn.find('mt5.modify_position_sl(ticket, new_sl)')
        blk = self.fn[i_mod:i_mod + 400]
        m = re.search(r'if success:\s*\n\s*remember_sl\(_sl_sent, ticket, new_sl\)', blk)
        self.assertIsNotNone(m, 'remember_sl tiene que ser lo primero bajo `if success:`')

    def test_el_skip_persiste_el_pico(self):
        """Saltear el reenvio NO puede volver a causar la amnesia del HWM (v3.52.1)."""
        i_chk = self.fn.find('sl_already_sent(_sl_sent, ticket, new_sl)')
        i_elif = self.fn.find('elif new_sl is not None:', i_chk)
        blk = self.fn[i_chk:i_elif]
        self.assertIn('update_mt5_high_water(sid, high_water)', blk)
        self.assertNotIn('modify_position_sl', blk)
        self.assertNotIn('_logger.info', blk)

    def test_mutacion_el_sl_de_la_db_sigue_siendo_el_original(self):
        """Documenta la premisa: el fix es el cache, NO tocar stop_loss en la DB (el archive
        lo usa como sl_pips del plan). Si alguien agrega un UPDATE de stop_loss aca, este
        test avisa para que se revise el efecto en el archive."""
        self.assertNotIn('SET stop_loss', self.fn)


if __name__ == '__main__':
    unittest.main(verbosity=2)
