"""
test_calendar_play_actual_v3651.py — v3.65.1: el shadow calendar play nunca completaba `actual`.

NO toca la DB de produccion ni la red ni MT5 (la consulta de `news_titles_between` se prueba
contra una SQLite temporal).

Las 3 causas, una por clase:
  1. `news_titles_between` formateaba los limites con espacio y `published_at` se guarda con 'T'
     ⇒ comparando como texto, toda nota del mismo dia quedaba FUERA del BETWEEN ⇒ [] siempre.
  2. El parser 'X vs Y expected' exigia el numero pegado al 'vs' ⇒ '+0.5% m/m vs ...' no parseaba.
  3. Las decisiones de tasas no traen 'vs expected' ⇒ no habia como completarlas.
  + guarda de pais: un dato de Canada/Italia a la misma hora no puede ser el actual de EE.UU./eurozona.
Los titulos son los REALES de la tabla `news` (oct-2026).
"""
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.analyzer import calendar_play as cp  # noqa: E402
from src.common import db as dbmod  # noqa: E402


class TestNewsTitlesBetween(unittest.TestCase):
    def test_encuentra_notas_con_T(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 't.db')
        c = sqlite3.connect(path)
        c.execute('CREATE TABLE news (title TEXT, published_at TEXT)')
        c.executemany('INSERT INTO news VALUES (?,?)', [
            ('FOMC decision Oct 28: Rates left unchanged', '2026-10-28T18:00:03'),
            ('nota vieja', '2026-10-28T17:00:00'),
            ('formato con espacio', '2026-10-28 18:05:00')])
        c.commit()
        c.close()
        orig = dbmod.DB_PATH
        try:
            dbmod.DB_PATH = path
            got = dbmod.news_titles_between(1793210400, 1793210400 + 600)  # 28-oct 18:00 UTC
        finally:
            dbmod.DB_PATH = orig
        self.assertEqual(got, ['FOMC decision Oct 28: Rates left unchanged', 'formato con espacio'])


class TestParserAmpliado(unittest.TestCase):
    def test_calificadores_reales(self):
        self.assertEqual(cp.parse_vs_title('US September PCE core inflation +0.5% m/m vs +0.3% expected'),
                         (0.5, 0.3))
        self.assertEqual(cp.parse_vs_title('Italy October preliminary CPI +5.4% vs +4.6% y/y expected'),
                         (5.4, 4.6))
        a, e = cp.parse_vs_title('US September advance goods trade balance -134.9 billion vs -130.2 billion expected')
        self.assertAlmostEqual(a, -134.9e9, delta=1)
        self.assertAlmostEqual(e, -130.2e9, delta=1)
        self.assertEqual(cp.parse_vs_title('US New home sales for September 0.676M annualized vs 0.650M estimate'),
                         (676000.0, 650000.0))
        self.assertEqual(cp.parse_vs_title('US August Federal budget deficit $167 billion vs $404 billion expected'),
                         (167e9, 404e9))

    def test_los_viejos_siguen(self):
        self.assertEqual(cp.parse_vs_title('US August CPI +2.9% vs +2.9% expected'), (2.9, 2.9))
        self.assertEqual(cp.parse_vs_title('US initial jobless claims 194K vs 199K expected'), (194000.0, 199000.0))
        self.assertIsNone(cp.parse_vs_title('Oil: Private survey of inventory shows a headline crude oil draw vs build expected'))


class TestTasas(unittest.TestCase):
    def test_sin_cambio(self):
        self.assertEqual(cp.parse_rate_title('FOMC decision Oct 28: Rates left unchanged', 'USD', '4.00%'), '4.00%')
        self.assertEqual(cp.parse_rate_title('ECB rate decision: No change in rates', 'EUR', '2.65%'), '2.65%')
        self.assertEqual(cp.parse_rate_title('Fed Leaves Rates Unchanged, Cook and Hammack Dissent', 'USD', '4.00%'),
                         '4.00%')

    def test_movimiento(self):
        self.assertEqual(cp.parse_rate_title('FOMC decision: Fed cuts rates to 3.75%-4.00%', 'USD', '4.25%'), '4.00%')
        self.assertEqual(cp.parse_rate_title('ECB rate decision: hikes by 25 bps', 'EUR', '2.65%'), '2.90%')
        self.assertEqual(cp.parse_rate_title('ECB rate decision: Hike to 2.90%', 'EUR', '2.65%'), '2.90%')

    def test_otro_banco_o_comentario(self):
        # BoC a la misma hora / otro banco: no es la decision de ESE banco
        self.assertIsNone(cp.parse_rate_title('Bank of Canada rate decision: Hike to 2.50%', 'USD', '4.00%'))
        self.assertIsNone(cp.parse_rate_title('ECB rate decision: No change in rates', 'USD', '4.00%'))
        # comentario sin decision
        self.assertIsNone(cp.parse_rate_title("Fed's Waller: rates should stay unchanged for now", 'USD', '4.00%'))
        self.assertIsNone(cp.parse_rate_title('The market is pricing in a 78% chance of a Fed hike', 'USD', '4.00%'))

    def test_evento_de_tasa(self):
        self.assertTrue(cp.is_rate_event({'event': 'Federal Funds Rate'}))
        self.assertTrue(cp.is_rate_event({'event': 'Main Refinancing Rate'}))
        self.assertFalse(cp.is_rate_event({'event': 'Unemployment Rate'}))
        self.assertFalse(cp.is_rate_event({'event': 'FOMC Press Conference'}))


class TestPais(unittest.TestCase):
    def test_guarda(self):
        self.assertTrue(cp.foreign_title('Canada August retail sales +1.2% vs +1.3% expected', 'USD'))
        self.assertFalse(cp.foreign_title('US September retail sales +0.4% vs +0.3% expected', 'USD'))
        self.assertTrue(cp.foreign_title('Italy October preliminary CPI +5.4% vs +4.6% y/y expected', 'EUR'))
        self.assertFalse(cp.foreign_title('Eurozone October flash CPI +2.1% vs +2.0% expected', 'EUR'))


class _DB:
    def __init__(self):
        self.calls = []

    def update_calendar_play_actual(self, *a):
        self.calls.append(a)


class TestResolveActual(unittest.TestCase):
    def setUp(self):
        self._fe = cp.fetch_events
        cp.fetch_events = lambda now=None: []      # el feed FF real no trae actual

    def tearDown(self):
        cp.fetch_events = self._fe

    def test_fomc_real(self):
        db = _DB()
        titles = ['FOMC decision Oct 28: Rates left unchanged', 'The full statement from the October 2026 FOMC rate decision']
        evs = [{'event': 'Federal Funds Rate', 'currency': 'USD', 'release_ts': 1793210400,
                'forecast': '4.00%', 'previous': '4.00%'},
               {'event': 'FOMC Statement', 'currency': 'USD', 'release_ts': 1793210400, 'forecast': '', 'previous': ''}]
        cp.resolve_actual(evs, db, lambda a, b: titles)
        self.assertEqual(db.calls, [('Federal Funds Rate|1793210400', '4.00%', 'forexlive_rate')])

    def test_dato_no_toma_el_de_canada(self):
        db = _DB()
        titles = ['Canada August retail sales +1.2% vs +1.3% expected',
                  'US September retail sales +0.4% vs +0.3% expected']
        evs = [{'event': 'Retail Sales m/m', 'currency': 'USD', 'release_ts': 1, 'forecast': '0.3%', 'previous': ''}]
        cp.resolve_actual(evs, db, lambda a, b: titles)
        self.assertEqual(db.calls, [('Retail Sales m/m|1', '0.4', 'forexlive', '0.3')])


if __name__ == '__main__':
    unittest.main()
