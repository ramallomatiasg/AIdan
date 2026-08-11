"""v3.53.3 — Tests del DOBLE CONTEO de la comision de entrada en sync_closed_positions.

EL BUG (mt5_executor.py:757-778):

    pnl = 0.0
    deals = history_deals_get(position=ticket)
    if deals:
        for deal in deals:
            pnl += deal.profit + deal.swap + deal.commission     # suma

    if not deals or close_price == 0:        # <-- entra AUNQUE deals tenga filas
        deals_fb = history_deals_get(time_from, time_to)
        for deal in deals_fb:
            if deal.position_id == ticket:
                pnl += deal.profit + deal.swap + deal.commission  # SUMA DE NUEVO

Si la primera consulta trae el deal de ENTRADA pero el de CIERRE todavia no propago al
historial del broker, close_price queda en 0 => se entra al fallback => y el fallback
vuelve a sumar los mismos deals SIN resetear pnl. La comision de entrada se cuenta dos
veces y el P&L queda mas negativo que la realidad.

POR QUE IMPORTA MAS QUE OTROS BUGS: mt5_pnl es la columna que TODO el proyecto trata como
verdad (broker-truth). Toda medicion filtra `mt5_pnl IS NOT NULL` y decide con ese numero.

FRECUENCIA HISTORICA: NO MEDIBLE. La comision implicita solo se puede reconstruir con el
lote, y trade_archive no lo guarda. En las 5 filas del buffer vivo que si lo tienen, la
comision implicita da $3,00-$4,00 por lote por lado, consistente con IC Markets Raw
Spread (~$3,50) => sin senal de doble conteo ahi. El fix va por merito de codigo.

Correr: python tools/test_commission_double_count_v3533.py
"""
import logging
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.broker.mt5_executor import MT5Executor, MAGIC_NUMBER  # noqa: E402

logging.disable(logging.CRITICAL)

TICKET = 1850578652
SID = 999


class Deal:
    """Deal de MT5. entry=0 -> apertura, entry=1 -> cierre."""
    def __init__(self, entry, profit, commission, price, swap=0.0, position_id=TICKET):
        self.entry = entry
        self.profit = profit
        self.commission = commission
        self.swap = swap
        self.price = price
        self.position_id = position_id


# Un trade real: abre pagando comision, cierra con +$1.00 bruto y paga la otra mitad.
DEAL_APERTURA = Deal(entry=0, profit=0.0, commission=-0.35, price=1.16000)
DEAL_CIERRE = Deal(entry=1, profit=1.00, commission=-0.35, price=1.16100)
# P&L NETO correcto = 1.00 - 0.35 - 0.35 = +0.30
PNL_CORRECTO = 0.30


class FakeMT5:
    """Doble del modulo MT5. `deals_por_posicion` simula lo que devuelve la consulta
    directa; `deals_por_tiempo` lo que devuelve el fallback. Poder darles contenido
    DISTINTO es justamente lo que permite reproducir la ventana del bug."""

    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1

    def __init__(self, deals_por_posicion, deals_por_tiempo):
        self._dp = deals_por_posicion
        self._dt = deals_por_tiempo

    def positions_get(self, **kw):
        return ()          # la posicion ya cerro

    def orders_get(self, **kw):
        return ()

    def history_deals_get(self, *args, **kw):
        if 'position' in kw:
            return tuple(self._dp)
        return tuple(self._dt)      # llamada por (time_from, time_to) = el fallback

    def symbol_info_tick(self, symbol):
        return type('T', (), {'bid': 1.16100, 'ask': 1.16110, 'time': 0})()

    def order_send(self, req):
        return type('R', (), {'retcode': self.TRADE_RETCODE_DONE, 'order': 1, 'deal': 1})()


class SyncHarness(unittest.TestCase):
    """Corre sync_closed_positions real capturando lo que escribiria en la DB."""

    def _correr(self, deals_por_posicion, deals_por_tiempo):
        import src.common.db as dbmod
        capturado = {}

        orig_get = dbmod.get_strategies_with_open_mt5
        orig_upd = dbmod.update_mt5_close
        # shape real: (id, ticket, direction, entry, sl, tp, lot, created, title,
        #              step, fill, hwm, conf, trigger_type)
        dbmod.get_strategies_with_open_mt5 = lambda: [
            (SID, TICKET, 'CALL', 1.16, 1.1585, 1.1650, 0.01, '', 'test', 0, 1.16000,
             0.0, 70, 'structure')]
        dbmod.update_mt5_close = lambda sid, pnl, close_price: capturado.update(
            sid=sid, pnl=pnl, close_price=close_price)
        try:
            ex = MT5Executor(logger=logging.getLogger('t'))
            ex._mt5 = FakeMT5(deals_por_posicion, deals_por_tiempo)
            ex.connected = True
            ex.kill_switch = False
            ex.sync_closed_positions()
        finally:
            dbmod.get_strategies_with_open_mt5 = orig_get
            dbmod.update_mt5_close = orig_upd
        return capturado


class TestCasoNormal(SyncHarness):
    """Control: el camino feliz NO puede cambiar. Es el 99% de los cierres."""

    def test_ambos_deals_presentes(self):
        cap = self._correr([DEAL_APERTURA, DEAL_CIERRE], [DEAL_APERTURA, DEAL_CIERRE])
        self.assertAlmostEqual(cap.get('pnl'), PNL_CORRECTO, places=6,
                               msg="el caso normal debe dar el P&L neto exacto")
        self.assertAlmostEqual(cap.get('close_price'), 1.16100, places=5)


class TestElBug(SyncHarness):
    """LA VENTANA: la consulta por posicion trae solo la apertura; el fallback por tiempo
    ya ve las dos. Antes del fix la comision de entrada se contaba dos veces."""

    def test_no_duplica_la_comision_de_entrada(self):
        cap = self._correr([DEAL_APERTURA], [DEAL_APERTURA, DEAL_CIERRE])
        self.assertAlmostEqual(
            cap.get('pnl'), PNL_CORRECTO, places=6,
            msg=f"esperaba {PNL_CORRECTO:+.2f} y dio {cap.get('pnl')}: la comision de "
                f"entrada se conto dos veces (seria -0.05 con el bug)")

    def test_el_precio_de_cierre_llega_del_fallback(self):
        cap = self._correr([DEAL_APERTURA], [DEAL_APERTURA, DEAL_CIERRE])
        self.assertAlmostEqual(cap.get('close_price'), 1.16100, places=5)


class TestOtrosCaminos(SyncHarness):
    """Los demas caminos del calculo siguen funcionando."""

    def test_consulta_por_posicion_vacia_usa_el_fallback(self):
        cap = self._correr([], [DEAL_APERTURA, DEAL_CIERRE])
        self.assertAlmostEqual(cap.get('pnl'), PNL_CORRECTO, places=6)

    def test_ningun_deal_en_ninguna_via(self):
        """Sin deals no hay P&L que calcular; el precio cae al tick actual."""
        cap = self._correr([], [])
        self.assertAlmostEqual(cap.get('pnl'), 0.0, places=6)
        self.assertAlmostEqual(cap.get('close_price'), 1.16100, places=5)

    def test_el_fallback_ignora_deals_de_OTRA_posicion(self):
        ajeno = Deal(entry=1, profit=99.0, commission=-9.0, price=1.19999,
                     position_id=777777)
        cap = self._correr([DEAL_APERTURA], [DEAL_APERTURA, DEAL_CIERRE, ajeno])
        self.assertAlmostEqual(cap.get('pnl'), PNL_CORRECTO, places=6,
                               msg="un deal de otro ticket no puede entrar al P&L")

    def test_swap_se_suma_una_sola_vez(self):
        ap = Deal(entry=0, profit=0.0, commission=-0.35, price=1.16000, swap=-0.10)
        ci = Deal(entry=1, profit=1.00, commission=-0.35, price=1.16100, swap=-0.05)
        cap = self._correr([ap], [ap, ci])
        self.assertAlmostEqual(cap.get('pnl'), 1.00 - 0.70 - 0.15, places=6)

    def test_perdedor_no_se_infla(self):
        """El bug hacia los P&L MAS negativos: un perdedor tambien tiene que dar exacto."""
        ap = Deal(entry=0, profit=0.0, commission=-0.35, price=1.16000)
        ci = Deal(entry=1, profit=-2.00, commission=-0.35, price=1.15800)
        cap = self._correr([ap], [ap, ci])
        self.assertAlmostEqual(cap.get('pnl'), -2.70, places=6)


class TestEstructuraDelCodigo(unittest.TestCase):
    """Fija el fix en el fuente para que un refactor no reintroduzca la acumulacion."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'src', 'broker', 'mt5_executor.py'),
                  encoding='utf-8') as fh:
            cls.src = fh.read()

    def _bloque(self):
        i = self.src.find('COMISION-DOBLE GUARD v3.53.3')
        self.assertNotEqual(i, -1, "no se encontro el marcador del fix")
        crudo = self.src[i:i + 2200]
        return '\n'.join(ln for ln in crudo.splitlines()
                         if not ln.strip().startswith('#'))

    def test_el_fallback_no_acumula_sobre_el_pnl_previo(self):
        blk = self._bloque()
        self.assertNotIn('pnl +=', blk,
                         "el fallback NO puede acumular sobre el pnl ya calculado: "
                         "ahi vivia el doble conteo")


if __name__ == '__main__':
    unittest.main(verbosity=2)
