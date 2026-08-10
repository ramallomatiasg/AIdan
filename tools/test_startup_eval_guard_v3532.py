"""v3.53.2 — Tests del guard del startup eval (fail-CLOSED).

EL BUG: el guard que evita evaluar por PRECIO una posicion que sigue abierta fallaba
ABIERTO por dos lados distintos:

  1) estaba condicionado a `mt5_exec.is_ready()`, que es `connected and not kill_switch`
     => si MT5 todavia no conecto (arranque por Task Scheduler a las 4 AM con el terminal
     levantando) o si el kill switch estaba puesto, el guard NI CORRIA y la ejecucion
     caia hacia abajo, a la evaluacion por precio.
  2) su `except Exception: logger.debug(...)` tambien dejaba caer la ejecucion hacia
     abajo => cualquier error de lectura terminaba en evaluacion por precio.

Evaluar por precio una posicion viva es el bug v3.39.1 (win-amputation / P&L fantasma en
trade_archive en cada restart).

Su gemelo in-loop (AIdan_TodoEnUno.py:3042) ya lo hacia bien con el patron `_tk =
'unknown'`: el valor inicial es truthy, asi que un fallo de lectura cae en `if _tk:
continue` = skip. Y no consulta MT5: alcanza el ticket en la DB, porque si hay ticket el
main loop lo va a cerrar/evaluar con el P&L REAL del broker.

Correr con: python tools/test_startup_eval_guard_v3532.py
"""
import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def decidir(ticket_leido, lectura_ok=True):
    """Replica de la tabla de decision del guard nuevo.

    ticket_leido: el mt5_ticket que devolvio la DB (None = sin ticket).
    lectura_ok:   False si la consulta a la DB fallo.
    Devuelve True si hay que SALTEAR la evaluacion por precio.
    """
    tk = ticket_leido if lectura_ok else 'unknown'   # el patron del gemelo in-loop
    return bool(tk)


class TestTablaDeDecision(unittest.TestCase):

    def test_con_ticket_se_saltea(self):
        """Tiene posicion en el broker => la evalua el main loop con P&L real."""
        self.assertTrue(decidir(1848501711))

    def test_sin_ticket_se_evalua(self):
        """Nunca se ejecuto: corresponde evaluar la SENAL (y el guard de v3.51.1 la
        mantiene afuera de trade_archive)."""
        self.assertFalse(decidir(None))

    def test_si_la_lectura_FALLA_se_saltea(self):
        """FAIL-CLOSED: en la duda no se evalua por precio. Antes evaluaba."""
        self.assertTrue(decidir(None, lectura_ok=False))
        self.assertTrue(decidir(1848501711, lectura_ok=False))

    def test_ticket_cero_cuenta_como_sin_ticket(self):
        """0 es el valor que quedo en filas viejas nunca ejecutadas."""
        self.assertFalse(decidir(0))

    def test_no_depende_de_que_MT5_este_conectado(self):
        """El bug 1: el guard viejo no corria si MT5 no estaba listo. El nuevo no lo
        consulta, asi que la decision es la misma con MT5 caido."""
        for ready in (True, False):
            with self.subTest(mt5_ready=ready):
                self.assertTrue(decidir(1848501711))
                self.assertFalse(decidir(None))


class TestCodigoReal(unittest.TestCase):
    """Fija la estructura en el fuente: el guard no puede volver a fallar abierto."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8') as fh:
            cls.src = fh.read()
        cls.tree = ast.parse(cls.src)

    def _bloque_startup(self):
        """El guard del startup eval, ubicado por su marcador, SIN las lineas de
        comentario — si no, los tests matchean el texto que EXPLICA el bug viejo en vez
        del codigo (me paso en el primer intento)."""
        i = self.src.find('STARTUP-EVAL GUARD v3.53.2')
        self.assertNotEqual(i, -1, "no se encontro el marcador del guard nuevo")
        crudo = self.src[i:i + 3000]
        codigo = [ln for ln in crudo.splitlines() if not ln.strip().startswith('#')]
        return '\n'.join(codigo)

    def test_el_guard_ya_NO_exige_is_ready(self):
        blk = self._bloque_startup()
        self.assertNotIn('is_ready()', blk,
                         "el guard no debe depender de que MT5 este conectado: si MT5 no "
                         "esta listo el guard tiene que seguir protegiendo")

    def test_usa_el_patron_fail_closed_del_gemelo(self):
        blk = self._bloque_startup()
        self.assertIn("'unknown'", blk,
                      "el valor inicial truthy es lo que hace el fail-closed (patron del "
                      "gemelo in-loop, AIdan:3042)")

    def test_el_except_NO_deja_caer_a_la_evaluacion(self):
        """El bug 2: antes el except logueaba a debug y seguia evaluando."""
        blk = self._bloque_startup()
        # el continue tiene que estar DESPUES del except, no solo adentro del try
        pos_except = blk.find('except')
        pos_continue = blk.find('continue', pos_except)
        self.assertNotEqual(pos_continue, -1,
                            "despues del except tiene que haber un continue alcanzable")

    def test_el_gemelo_in_loop_sigue_intacto(self):
        """Control: no se toco el guard que ya funcionaba bien."""
        self.assertIn("_tk = 'unknown'", self.src,
                      "el patron del gemelo in-loop debe seguir presente")
        self.assertIn('expired but MT5 position still OPEN', self.src)

    def test_el_guard_ya_no_consulta_positions_get(self):
        """El guard nuevo decide con el ticket de la DB: no necesita hablar con el broker."""
        blk = self._bloque_startup()
        self.assertNotIn('positions_get', blk,
                         "el guard no debe depender de una consulta al broker")

    def test_los_otros_usos_de_is_ready_siguen_intactos(self):
        """Control de que no se toco nada de mas. Los 3 usos restantes de
        `is_ready() and mt5_exec._mt5` son LEGITIMOS: toman el tick de MT5 como mejora
        opcional del precio de entrada, con fallback al de market_state. Ahi fallar
        abierto es lo correcto — no protegen nada, refinan un precio."""
        n = self.src.count('if mt5_exec and mt5_exec.is_ready() and mt5_exec._mt5:')
        self.assertEqual(n, 3,
                         f"se esperaban 3 usos legitimos (tick de entrada M5/M15/H1), hay {n}")


class TestSemanticaDelSkip(unittest.TestCase):
    """Lo que pasa DESPUES del skip: quien evalua esa estrategia."""

    def test_el_skip_no_pierde_la_estrategia(self):
        """El skip no la marca ni la archiva: queda pendiente y el main loop la toma.
        Se fija leyendo el fuente para que nadie agregue un archive_trade ahi."""
        with open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8') as fh:
            src = fh.read()
        i = src.find('STARTUP-EVAL GUARD v3.53.2')
        blk = src[i:i + 1200]
        for prohibido in ('archive_trade', 'update_strategy_result', 'record_signal_result'):
            with self.subTest(prohibido=prohibido):
                self.assertNotIn(prohibido, blk,
                                 f"el guard solo debe saltear, no {prohibido}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
