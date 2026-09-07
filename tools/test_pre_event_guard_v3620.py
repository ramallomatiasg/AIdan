"""v3.62.0 — Tests del GUARD PRE-EVENTO para news (clase #969).

El caso: #969 fue un CALL de news sobre una nota PREVIA al NFP ("Locked and loaded for
non-farm payrolls"), 12,8 min ANTES del dato, con SL de 4p. El spike lo paso por arriba
34p: -29,1p = -$29,40 (5,5% de la cuenta). El event-window lo vio (in_window=1) pero
news esta exento por diseno (jugada POST-dato). Este guard cubre el caso PRE-dato.

Se testea (a) la decision pura (`news_pre_event_block`) con el caso real y sus bordes,
(b) que el default de la perilla sea la ventana previa del event-window (el 15 no es
un numero nuevo), y (c) el CALL-SITE en el monolito: que exista, que corte con
`return None`, que marque `skipped_pre_event`, que vaya DESPUES del log del event-window
(la medicion del shadow no cambia) y ANTES del spread guardian (antes de cualquier orden).
Un test que solo ejercitara la funcion habria quedado en verde con el mecanismo
desconectado — la clase de bug de `adjust_setup_confidence` (5 meses muerto).

Correr con: python tools/test_pre_event_guard_v3620.py
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.common.event_window import news_pre_event_block, WIN_BEFORE  # noqa: E402

# Fila REAL de event_window_log del #969 (4-sep-2026 09:17 AR).
PROX_969 = {'in_window': True, 'mins_to_next': 12.8, 'next_event': 'Average Hourly Earnings m/m',
            'next_impact': 'High', 'next_currency': 'USD'}


class TestDecision(unittest.TestCase):

    def test_caso_969_bloquea(self):
        blk, ev, mins = news_pre_event_block(PROX_969, 'news', 15.0)
        self.assertTrue(blk)
        self.assertEqual(ev, 'Average Hourly Earnings m/m')
        self.assertAlmostEqual(mins, 12.8)

    def test_post_dato_sigue_exento(self):
        """Esa ES la jugada de news: solo el evento ADELANTE bloquea."""
        prox = {'in_window': True, 'mins_since_prev': 4.0, 'prev_impact': 'High',
                'prev_event': 'Non-Farm Employment Change',
                'mins_to_next': 300.0, 'next_impact': 'High', 'next_event': 'FOMC'}
        self.assertFalse(news_pre_event_block(prox, 'news', 15.0)[0])

    def test_medium_no_bloquea(self):
        prox = dict(PROX_969, next_impact='Medium')
        self.assertFalse(news_pre_event_block(prox, 'news', 15.0)[0])

    def test_borde_de_la_ventana(self):
        self.assertTrue(news_pre_event_block(dict(PROX_969, mins_to_next=15.0), 'news', 15.0)[0])
        self.assertFalse(news_pre_event_block(dict(PROX_969, mins_to_next=15.1), 'news', 15.0)[0])
        self.assertTrue(news_pre_event_block(dict(PROX_969, mins_to_next=0.0), 'news', 15.0)[0])

    def test_otros_triggers_no_son_su_trabajo(self):
        """structure/m15/h1/smc los cubre el event-window; pre_planned y calendar juegan
        el evento por diseno."""
        for trig in ('structure', 'm15_structure', 'h1_structure', 'smc',
                     'pre_planned', 'calendar', None, ''):
            self.assertFalse(news_pre_event_block(PROX_969, trig, 15.0)[0], trig)

    def test_sin_calendario_fail_open(self):
        """Un feed caido no puede apagar news entero en silencio."""
        self.assertFalse(news_pre_event_block({}, 'news', 15.0)[0])
        self.assertFalse(news_pre_event_block(None, 'news', 15.0)[0])
        self.assertFalse(news_pre_event_block({'in_window': False}, 'news', 15.0)[0])
        self.assertFalse(news_pre_event_block({'next_impact': 'High'}, 'news', 15.0)[0])

    def test_apagado_con_cero(self):
        self.assertFalse(news_pre_event_block(PROX_969, 'news', 0)[0])
        self.assertFalse(news_pre_event_block(PROX_969, 'news', None)[0])
        self.assertFalse(news_pre_event_block(PROX_969, 'news', 'basura')[0])

    def test_mins_como_string_no_explota(self):
        self.assertTrue(news_pre_event_block(dict(PROX_969, mins_to_next='12.8'), 'news', 15.0)[0])
        self.assertFalse(news_pre_event_block(dict(PROX_969, mins_to_next='x'), 'news', 15.0)[0])


class TestPerilla(unittest.TestCase):

    def test_default_es_la_ventana_previa_del_event_window(self):
        """El 15 NO es un numero nuevo: es WIN_BEFORE['High'] desde v3.40.14."""
        from src.common.config import Config
        self.assertEqual(float(Config.NEWS_PRE_EVENT_GUARD_MIN), float(WIN_BEFORE['High']))

    def test_env_pisa_el_default(self):
        src = open(os.path.join(ROOT, 'src', 'common', 'config.py'), encoding='utf-8').read()
        self.assertRegex(src, r'NEWS_PRE_EVENT_GUARD_MIN\s*=\s*float\(os\.getenv\("NEWS_PRE_EVENT_GUARD_MIN",\s*"15"\)\)')

    def test_documentada_en_env_example(self):
        env = open(os.path.join(ROOT, '.env.example'), encoding='utf-8').read()
        self.assertIn('NEWS_PRE_EVENT_GUARD_MIN', env)


class TestCallSite(unittest.TestCase):
    """El monolito tiene que LLAMAR al guard, en el lugar correcto."""

    @classmethod
    def setUpClass(cls):
        cls.src = open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8').read()
        # Recortar a _try_mt5_execute (desde su def hasta el spread guardian).
        m = re.search(r'def _try_mt5_execute\(', cls.src)
        assert m, 'no encuentro _try_mt5_execute'
        cls.fn = cls.src[m.start():]
        cls.i_log_ew = cls.fn.find('log_event_window(sid, _ew_trig, direction')
        cls.i_guard = cls.fn.find('news_pre_event_block(')
        cls.i_spread = cls.fn.find('is_spread_acceptable(')
        cls.i_open = cls.fn.find('mt5_exec.open_position(')

    def test_el_guard_se_llama(self):
        self.assertGreater(self.i_guard, 0, 'news_pre_event_block no se llama desde _try_mt5_execute')

    def test_va_despues_del_log_del_event_window(self):
        """La fila de event_window_log se escribe igual: la medicion del shadow no cambia."""
        self.assertGreater(self.i_log_ew, 0)
        self.assertGreater(self.i_guard, self.i_log_ew)

    def test_va_antes_de_cualquier_orden(self):
        self.assertGreater(self.i_spread, 0)
        self.assertLess(self.i_guard, self.i_spread)
        if self.i_open > 0:
            self.assertLess(self.i_guard, self.i_open)

    def test_corta_con_return_none_y_marca_skipped(self):
        block = self.fn[self.i_guard:self.i_spread]
        self.assertIn("status='skipped_pre_event'", block)
        self.assertIn('return None', block)
        # el marcado solo pisa 'active' (no reescribe un trade ya ejecutado)
        self.assertIn("AND status='active'", block)

    def test_lee_la_perilla_de_config(self):
        block = self.fn[:self.i_spread]
        self.assertIn("getattr(Config, 'NEWS_PRE_EVENT_GUARD_MIN'", block)

    def test_skipped_pre_event_lo_cubre_el_guard_v3536(self):
        """auto_evaluate no pisa status que empiecen con 'skipped' => no aparece como perdido."""
        db_src = open(os.path.join(ROOT, 'src', 'common', 'db.py'), encoding='utf-8').read()
        self.assertIn("startswith('skipped')", db_src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
