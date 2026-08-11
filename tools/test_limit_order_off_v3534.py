"""v3.53.4 — Tests del apagado del intento de orden LIMITE.

CONTEXTO MEDIDO (logs desde el 31-jul, 274.244 lineas): 36 intentos de orden limite,
36 rechazados con `retcode=10022 Invalid expiration`, 36 fallbacks a market order,
0 fallos de market => el mecanismo NUNCA opero y TODO el track record de AIdan se hizo
con ordenes a mercado.

LO QUE ESTOS TESTS PROTEGEN: que apagarlo NO cambie el comportamiento efectivo. Con el
flag en false el resultado tiene que ser identico al de hoy (market siempre), solo sin
las llamadas que el broker rechaza. Y que encenderlo por env siga siendo posible, para
poder medirlo algun dia.

Correr: python tools/test_limit_order_off_v3534.py
"""
import logging
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.broker.mt5_executor import MT5Executor, MAGIC_NUMBER  # noqa: E402

logging.disable(logging.CRITICAL)

SID = 4242


class FakeMT5:
    """Doble del modulo MT5. Registra los requests para poder afirmar QUE se mando."""
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_TIME_SPECIFIED = 1
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2

    def __init__(self, limit_retcode=10022):
        self.requests = []
        self._limit_retcode = limit_retcode

    def positions_get(self, **kw):
        return ()

    def orders_get(self, **kw):
        return ()

    def history_deals_get(self, *a, **kw):
        return ()

    def symbol_info(self, s):
        return type('S', (), {'filling_mode': 1, 'point': 0.00001})()

    def symbol_info_tick(self, s):
        return type('T', (), {'bid': 1.16000, 'ask': 1.16010, 'time': 1786000000})()

    def account_info(self):
        return type('A', (), {'balance': 640.0, 'equity': 640.0, 'margin': 0.0,
                              'margin_free': 640.0})()

    def order_check(self, req):
        # retcode 0 = la orden pasa la validacion del broker
        return type('C', (), {'retcode': 0, 'comment': 'Done'})()

    def order_send(self, req):
        self.requests.append(req)
        if req.get('action') == self.TRADE_ACTION_PENDING:
            # el broker rechaza la limite: es lo que pasa en produccion (36/36)
            return type('R', (), {'retcode': self._limit_retcode,
                                  'comment': 'Invalid expiration', 'order': 0, 'deal': 0})()
        return type('R', (), {'retcode': self.TRADE_RETCODE_DONE, 'comment': 'ok',
                              'order': 555, 'deal': 556})()

    @property
    def pendientes(self):
        return [r for r in self.requests if r.get('action') == self.TRADE_ACTION_PENDING]

    @property
    def a_mercado(self):
        return [r for r in self.requests if r.get('action') == self.TRADE_ACTION_DEAL]


class Harness(unittest.TestCase):

    def _abrir(self, limit_enabled):
        import src.common.config as cfgmod
        import src.common.db as dbmod
        prev = cfgmod.Config.LIMIT_ORDER_ENABLED
        cfgmod.Config.LIMIT_ORDER_ENABLED = limit_enabled

        orig_cfg = dbmod.get_mt5_config
        orig_tk = dbmod.update_mt5_ticket
        orig_open = dbmod.get_strategies_with_open_mt5
        escrito = {}
        dbmod.get_mt5_config = lambda: {'enabled': 1, 'risk_percent': 1.0,
                                        'max_positions': 4, 'max_lot': 0.1,
                                        'kill_switch': 0}
        dbmod.update_mt5_ticket = lambda sid, t, lot, st, **kw: escrito.update(
            sid=sid, ticket=t, lot=lot, status=st)
        dbmod.get_strategies_with_open_mt5 = lambda: []
        try:
            ex = MT5Executor(logger=logging.getLogger('t'))
            mt5 = FakeMT5()
            ex._mt5 = mt5
            ex.connected = True
            ex.kill_switch = False
            ticket = ex.open_position(SID, 'CALL', 1.16000, 1.15850, 1.16500,
                                      confidence=70, trigger_type='structure')
            return mt5, ticket, escrito
        finally:
            cfgmod.Config.LIMIT_ORDER_ENABLED = prev
            dbmod.get_mt5_config = orig_cfg
            dbmod.update_mt5_ticket = orig_tk
            dbmod.get_strategies_with_open_mt5 = orig_open


class TestApagado(Harness):
    """El default: LIMIT_ORDER_ENABLED=false."""

    def test_NO_manda_orden_pendiente(self):
        mt5, ticket, _ = self._abrir(False)
        self.assertEqual(len(mt5.pendientes), 0,
                         "apagado NO debe pedirle al broker una orden que rechaza siempre")

    def test_SI_manda_la_orden_a_mercado(self):
        mt5, ticket, _ = self._abrir(False)
        self.assertEqual(len(mt5.a_mercado), 1, "la posicion se abre igual, a mercado")
        self.assertIsNotNone(ticket)

    def test_el_resultado_es_el_MISMO_que_encendido(self):
        """LA GARANTIA DEL CAMBIO: hoy el limit siempre falla y cae a mercado, asi que
        apagarlo no puede cambiar el trade que termina abierto."""
        off_mt5, off_tk, off_db = self._abrir(False)
        on_mt5, on_tk, on_db = self._abrir(True)
        self.assertEqual(off_tk, on_tk, "mismo ticket resultante")
        self.assertEqual(off_db, on_db, "misma escritura en la DB")
        self.assertEqual(len(off_mt5.a_mercado), len(on_mt5.a_mercado))
        # la unica diferencia: encendido gasta una llamada extra que el broker rechaza
        self.assertEqual(len(on_mt5.pendientes), 1)
        self.assertEqual(len(off_mt5.pendientes), 0)

    def test_la_orden_a_mercado_conserva_direccion_y_niveles(self):
        mt5, _, _ = self._abrir(False)
        req = mt5.a_mercado[0]
        self.assertEqual(req['type'], FakeMT5.ORDER_TYPE_BUY, "CALL -> BUY")
        self.assertLess(req['sl'], req['price'], "en un BUY el SL va debajo del precio")
        self.assertGreater(req['tp'], req['price'], "y el TP arriba")
        self.assertEqual(req['magic'], MAGIC_NUMBER)


class TestEncendidoPorEnv(Harness):
    """Se puede volver a prender para medirlo algun dia."""

    def test_encendido_intenta_la_limite_primero(self):
        mt5, _, _ = self._abrir(True)
        self.assertEqual(len(mt5.pendientes), 1)
        self.assertEqual(mt5.requests[0]['action'], FakeMT5.TRADE_ACTION_PENDING,
                         "encendido, la limite va primero")

    def test_default_de_config_es_false(self):
        from src.common.config import Config
        self.assertFalse(Config.LIMIT_ORDER_ENABLED,
                         "el default tiene que ser apagado")


class TestEstructura(unittest.TestCase):
    """Fija el gate en el fuente."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'src', 'broker', 'mt5_executor.py'),
                  encoding='utf-8') as fh:
            cls.src = fh.read()

    def test_el_intento_esta_gateado(self):
        i = self.src.find('_try_limit_order(strategy_id')
        self.assertNotEqual(i, -1)
        antes = self.src[max(0, i - 700):i]
        self.assertIn('Config.LIMIT_ORDER_ENABLED', antes,
                      "la llamada a _try_limit_order debe estar detras del flag")

    def test_el_market_order_queda_FUERA_del_if(self):
        """Si el return del market quedara adentro del if, apagar el flag dejaria a
        open_position sin abrir nada. Es el modo de falla a evitar."""
        i = self.src.find('if Config.LIMIT_ORDER_ENABLED:')
        self.assertNotEqual(i, -1)
        bloque = self.src[i:i + 1200]
        linea_market = next((ln for ln in bloque.splitlines()
                             if 'return self._market_order' in ln), None)
        self.assertIsNotNone(linea_market, "no se encontro el return del market order")
        sangria = len(linea_market) - len(linea_market.lstrip())
        self.assertEqual(sangria, 8,
                         f"el return del market order debe estar al nivel del metodo "
                         f"(8 espacios), no dentro del if. Tiene {sangria}.")


if __name__ == '__main__':
    unittest.main(verbosity=2)
