"""v3.53.0 — Tests del boton de panico y de la observabilidad del path de cierre.

EL BUG PRINCIPAL: _cmd_kill de Telegram hacia `kill_switch = True` y RECIEN DESPUES
exigia `is_ready()` (= connected and not kill_switch) => siempre False => las ~25 lineas
de cierre eran codigo INALCANZABLE. El boton de panico no cerraba nada y respondia
"0 posicion(es) cerrada(s)", que se lee como "no habia posiciones".

Se testea contra un doble del modulo MetaTrader5 (self._mt5 es un atributo de instancia,
asi que se inyecta sin refactorizar nada).

Correr con: python tools/test_kill_switch_v3530.py
"""
import logging
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.broker.mt5_executor import MT5Executor, MAGIC_NUMBER  # noqa: E402

logging.disable(logging.CRITICAL)


class FakePos:
    def __init__(self, ticket, magic=MAGIC_NUMBER, ptype=0, volume=0.01, symbol='EURUSD'):
        self.ticket = ticket
        self.magic = magic
        self.type = ptype
        self.volume = volume
        self.symbol = symbol
        self.profit = 0.0


class FakeResult:
    def __init__(self, retcode, comment='ok'):
        self.retcode = retcode
        self.comment = comment
        self.order = 111
        self.deal = 222


class FakeMT5:
    """Doble del modulo MetaTrader5. Solo lo que toca el path de cierre."""
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1

    def __init__(self, positions=None, fail_tickets=(), no_tick=False):
        self._positions = list(positions or [])
        self._fail = set(fail_tickets)          # tickets cuyo order_send falla
        self._no_tick = no_tick                 # symbol_info_tick devuelve None
        self.sent = []                          # requests efectivamente mandados

    def positions_get(self, **kw):
        if 'ticket' in kw:
            return tuple(p for p in self._positions if p.ticket == kw['ticket'])
        return tuple(self._positions)

    def orders_get(self, **kw):
        return ()

    def history_deals_get(self, **kw):
        return ()

    def symbol_info_tick(self, symbol):
        if self._no_tick:
            return None
        return type('T', (), {'bid': 1.16000, 'ask': 1.16010, 'time': 0})()

    def order_send(self, request):
        ticket = request.get('position')
        # emular el gate de tick: el executor pide el tick antes de armar el request
        if ticket in self._fail:
            return FakeResult(10004, 'requote')
        self.sent.append(request)
        self._positions = [p for p in self._positions if p.ticket != ticket]
        return FakeResult(self.TRADE_RETCODE_DONE)


def make_exec(mt5):
    ex = MT5Executor(logger=logging.getLogger('test'))
    ex._mt5 = mt5
    ex.connected = True
    ex.kill_switch = False
    return ex


class TestCloseAllPositions(unittest.TestCase):

    def test_cierra_solo_las_de_aidan(self):
        mt5 = FakeMT5([FakePos(1), FakePos(2, magic=999), FakePos(3)])
        ex = make_exec(mt5)
        closed, found = ex.close_all_positions(return_detail=True)
        self.assertEqual((closed, found), (2, 2), "la de magic ajeno no se cuenta ni se cierra")
        self.assertEqual({r['position'] for r in mt5.sent}, {1, 3})

    def test_shape_viejo_sigue_devolviendo_int(self):
        """AIdan_TodoEnUno.py y toggle() viejo esperaban un int."""
        ex = make_exec(FakeMT5([FakePos(1)]))
        self.assertEqual(ex.close_all_positions(), 1)

    def test_distingue_cero_por_vacio_de_cero_por_fallo(self):
        """LA DIFERENCIA QUE IMPORTA EN EL BOTON DE PANICO."""
        vacio = make_exec(FakeMT5([]))
        self.assertEqual(vacio.close_all_positions(return_detail=True), (0, 0))

        fallan = make_exec(FakeMT5([FakePos(1), FakePos(2)], fail_tickets=(1, 2)))
        self.assertEqual(fallan.close_all_positions(return_detail=True), (0, 2),
                         "found=2 con closed=0 => quedaron 2 abiertas, no es lo mismo que vacio")

    def test_cierre_parcial(self):
        mt5 = FakeMT5([FakePos(1), FakePos(2), FakePos(3)], fail_tickets=(2,))
        closed, found = make_exec(mt5).close_all_positions(return_detail=True)
        self.assertEqual((closed, found), (2, 3))

    def test_sin_conexion_no_miente(self):
        ex = make_exec(FakeMT5([FakePos(1)]))
        ex.connected = False
        self.assertEqual(ex.close_all_positions(return_detail=True), (0, 0))


class TestToggle(unittest.TestCase):

    def test_cierra_ANTES_de_levantar_el_flag(self):
        """EL CORAZON DEL BUG. Si el flag subiera primero, is_ready() daria False y no
        se cerraria nada."""
        mt5 = FakeMT5([FakePos(1), FakePos(2)])
        ex = make_exec(mt5)
        closed, found = ex.toggle(False)
        self.assertEqual((closed, found), (2, 2), "el cierre DEBE ocurrir antes del flag")
        self.assertTrue(ex.kill_switch, "el flag queda arriba despues")
        self.assertEqual(len(mt5.sent), 2)

    def test_is_ready_es_false_despues(self):
        ex = make_exec(FakeMT5([FakePos(1)]))
        ex.toggle(False)
        self.assertFalse(ex.is_ready(), "con el kill switch arriba no se puede operar")

    def test_encender_no_cierra_nada(self):
        mt5 = FakeMT5([FakePos(1)])
        ex = make_exec(mt5)
        ex.kill_switch = True
        closed, found = ex.toggle(True)
        self.assertEqual((closed, found), (0, 0))
        self.assertEqual(mt5.sent, [])
        self.assertFalse(ex.kill_switch)

    def test_devuelve_tupla_sin_romper_al_caller_que_la_ignora(self):
        """main.py:2681 hace `mt5.toggle(enabled)` y descarta el retorno."""
        ex = make_exec(FakeMT5([FakePos(1)]))
        ex.toggle(False)   # no debe tirar


class TestCmdKillDeTelegram(unittest.TestCase):
    """El bug vivia aca. Se ejercita _cmd_kill real con un provider falso."""

    def _bot(self, ex):
        from src.common.telegram_bot import TelegramBot
        bot = TelegramBot.__new__(TelegramBot)   # sin __init__ (no queremos red)
        bot.mt5_provider = lambda: ex
        bot.sent = []
        bot._send = lambda msg: bot.sent.append(msg)
        return bot

    def test_AHORA_CIERRA_DE_VERDAD(self):
        """EL TEST QUE FIJA EL BUG: antes de v3.53.0 mt5.sent quedaba VACIO."""
        mt5 = FakeMT5([FakePos(1), FakePos(2)])
        ex = make_exec(mt5)
        bot = self._bot(ex)
        bot._cmd_kill()
        self.assertEqual(len(mt5.sent), 2,
                         "el /kill DEBE mandar las ordenes de cierre (antes eran inalcanzables)")
        self.assertTrue(ex.kill_switch)
        self.assertIn('2 posicion', bot.sent[0])

    def test_no_dice_cero_cerradas_cuando_no_habia_ninguna(self):
        """El mensaje viejo decia '0 posicion(es) cerrada(s)' en los dos casos."""
        bot = self._bot(make_exec(FakeMT5([])))
        bot._cmd_kill()
        self.assertIn('No habia posiciones', bot.sent[0])

    def test_avisa_FUERTE_si_quedaron_abiertas(self):
        mt5 = FakeMT5([FakePos(1), FakePos(2)], fail_tickets=(2,))
        bot = self._bot(make_exec(mt5))
        bot._cmd_kill()
        msg = bot.sent[0]
        self.assertIn('SIGUEN ABIERTAS', msg)
        self.assertIn('1', msg)

    def test_sin_executor_lo_dice_en_vez_de_fingir(self):
        from src.common.telegram_bot import TelegramBot
        bot = TelegramBot.__new__(TelegramBot)
        bot.mt5_provider = lambda: None
        bot.sent = []
        bot._send = lambda m: bot.sent.append(m)
        bot._cmd_kill()
        self.assertIn('no disponible', bot.sent[0])

    def test_el_flag_sube_igual_aunque_el_cierre_falle(self):
        """Aunque no se pueda cerrar, hay que dejar de ABRIR posiciones nuevas."""
        ex = make_exec(FakeMT5([FakePos(1)], fail_tickets=(1,)))
        self._bot(ex)._cmd_kill()
        self.assertTrue(ex.kill_switch)


class TestObservabilidadDelCierre(unittest.TestCase):
    """Las ramas que antes eran mudas ahora avisan (v3.53.0)."""

    def setUp(self):
        """close_strategy_position hace `from src.common.db import
        get_strategies_with_open_mt5` DENTRO de la funcion, asi que parchear el modulo
        alcanza: el import resuelve en el momento de la llamada."""
        import src.common.db as dbmod
        self.dbmod = dbmod
        self._orig = dbmod.get_strategies_with_open_mt5
        # shape real: (id, ticket, direction, entry, sl, tp, lot, created, title,
        #              step, fill, hwm, conf, trigger_type) -> 14 columnas
        dbmod.get_strategies_with_open_mt5 = lambda: [
            (4242, 777, 'CALL', 1.16, 1.1585, 1.1650, 0.01, '', '', 0, 1.16, 0.0, 70,
             'h1_structure')]

    def tearDown(self):
        self.dbmod.get_strategies_with_open_mt5 = self._orig

    def _spy_logger(self, ex):
        captured = []
        ex.logger = type('L', (), {
            'warning': lambda s, m: captured.append(('W', m)),
            'error': lambda s, m: captured.append(('E', m)),
            'info': lambda s, m: None, 'debug': lambda s, m: None})()
        return captured

    def test_avisa_cuando_positions_get_viene_vacio_y_no_hay_deal(self):
        """LA RAMA QUE ERA MUDA: 25 de 174 cierres del PM (14%) salieron por aca sin log."""
        ex = make_exec(FakeMT5([]))          # el ticket 777 no esta en positions_get
        captured = self._spy_logger(ex)
        px, sent = ex.close_strategy_position(4242, return_sent_flag=True)
        self.assertIsNone(px)
        self.assertFalse(sent, "no se mando ninguna orden")
        self.assertTrue(any('NO se mando orden' in m for _, m in captured),
                        f"la rama muda debe loguear. capturado: {captured}")

    def test_avisa_cuando_no_hay_tick(self):
        ex = make_exec(FakeMT5([FakePos(777)], no_tick=True))
        captured = self._spy_logger(ex)
        px, sent = ex.close_strategy_position(4242, return_sent_flag=True)
        self.assertIsNone(px)
        self.assertFalse(sent)
        self.assertTrue(any('sigue ABIERTA' in m for _, m in captured),
                        f"capturado: {captured}")

    def test_el_cierre_normal_sigue_funcionando(self):
        """Control: el camino feliz no se toco."""
        mt5 = FakeMT5([FakePos(777)])
        ex = make_exec(mt5)
        px, sent = ex.close_strategy_position(4242, return_sent_flag=True)
        self.assertTrue(sent, "mando la orden")
        self.assertAlmostEqual(px, 1.16000, places=5)
        self.assertEqual(len(mt5.sent), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
