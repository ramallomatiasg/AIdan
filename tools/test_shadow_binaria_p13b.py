"""
test_shadow_binaria_p13b.py — tests del shadow P13b (A1 como binaria sobre Deriv) y su scorer.

NO toca la red, MT5 ni la DB de producción: todo con una base temporal.

Cubre, en orden de importancia:
  1. FRONTERA: el módulo no puede comprar ni tocar AIdan. Regex sobre el fuente: sin la llamada 'buy', sin
     MetaTrader5, sin financial_news.db; la base por default es la suya.
  2. La señal es la de los backtests: a1_direction coincide con gen_A1 en cada punto de una serie.
  3. outcome: CALL/PUT ganan y pierden en el sentido correcto, empate aparte.
  4. Horario líquido: lunes a viernes 07-16 UTC.
  5. El scorer: veredicto PROVISORIO sin payout, PASA / NO PASA con payout, y que lea con mode=ro.
"""
import datetime as dt
import os
import re
import sqlite3
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import tools.shadow_binaria as sb  # noqa: E402
import tools.score_shadow_binaria as sc  # noqa: E402
from tools.screen_generators import gen_A1  # noqa: E402

SRC = open(os.path.join(ROOT, 'tools', 'shadow_binaria.py'), encoding='utf-8').read()
SCORER = open(os.path.join(ROOT, 'tools', 'score_shadow_binaria.py'), encoding='utf-8').read()


class Frontera(unittest.TestCase):
    def test_no_compra(self):
        self.assertIsNone(re.search(r"""['"]buy['"]""", SRC), 'el shadow no puede tener la llamada buy')
        self.assertNotIn('buy_contract', SRC)

    def test_no_toca_aidan(self):
        self.assertNotIn('MetaTrader5', SRC)
        self.assertNotIn('financial_news.db', SRC)
        self.assertTrue(sb.default_db().endswith('binary_shadow.db'))

    def test_scorer_read_only(self):
        self.assertIn('mode=ro', SCORER)
        self.assertIsNone(re.search(r'\b(INSERT|UPDATE|DELETE|ALTER)\b', SCORER))


class Senal(unittest.TestCase):
    def test_igual_a_gen_A1(self):
        rng = np.random.default_rng(1)
        c = 1.1 + np.cumsum(rng.normal(0, 0.0003, 3000))
        idx, dirs = gen_A1(c, c, c, c, None, None)
        sig = dict(zip(idx.tolist(), dirs.tolist()))
        hits = 0
        for i in range(25, c.size):
            d, _ = sb.a1_direction(c[i - 39 if i >= 39 else 0:i + 1])
            self.assertEqual(d, sig.get(i, 0), f'vela {i}')
            hits += d != 0
        self.assertGreater(hits, 20, 'la serie de prueba tiene que tener señales')

    def test_pocas_velas(self):
        self.assertEqual(sb.a1_direction([1.0] * 10)[0], 0)


class Outcome(unittest.TestCase):
    def test_call_put(self):
        self.assertEqual(sb.outcome('CALL', 1.0, 1.1), 'win')
        self.assertEqual(sb.outcome('CALL', 1.0, 0.9), 'loss')
        self.assertEqual(sb.outcome('PUT', 1.0, 0.9), 'win')
        self.assertEqual(sb.outcome('PUT', 1.0, 1.1), 'loss')
        self.assertEqual(sb.outcome('PUT', 1.0, 1.0), 'tie')
        self.assertIsNone(sb.outcome('PUT', 1.0, None))


class Ventana(unittest.TestCase):
    def test_horario(self):
        lun = dt.datetime(2026, 10, 26)
        self.assertTrue(sb.in_window(lun.replace(hour=7)))
        self.assertTrue(sb.in_window(lun.replace(hour=15, minute=59)))
        self.assertFalse(sb.in_window(lun.replace(hour=16)))
        self.assertFalse(sb.in_window(lun.replace(hour=6, minute=59)))
        self.assertFalse(sb.in_window(dt.datetime(2026, 10, 24, 10)))   # sábado


class Scorer(unittest.TestCase):
    def rows(self, n, hit, payout=None, ask=10.0):
        k = int(round(n * hit))
        return [('frxEURUSD', '2026-10-26T10:00:00', 'win' if i < k else 'loss', payout, ask if payout else None)
                for i in range(n)]

    def test_sin_veredicto_n_chico(self):
        self.assertTrue(sc.evaluate(self.rows(100, 0.6))['veredicto'].startswith('SIN VEREDICTO'))

    def test_provisorio_sin_payout(self):
        ev = sc.evaluate(self.rows(2000, 0.57))
        self.assertTrue(ev['provisorio'])
        self.assertIn('PROVISORIO', ev['veredicto'])

    def test_pasa_con_payout(self):
        ev = sc.evaluate(self.rows(2000, 0.58, payout=19.0))      # payout 90% ⇒ break-even 52,6%
        self.assertEqual(ev['veredicto'], 'PASA')

    def test_no_pasa_con_payout_bajo(self):
        ev = sc.evaluate(self.rows(2000, 0.54, payout=18.0))      # payout 80% ⇒ break-even 55,6%
        self.assertTrue(ev['veredicto'].startswith('NO PASA'))

    def test_empates_no_puntuan(self):
        rows = self.rows(10, 0.5) + [('frxEURUSD', '2026-10-26T10:00:00', 'tie', None, None)]
        ev = sc.evaluate(rows)
        self.assertEqual((ev['n'], ev['ties']), (10, 1))

    def test_db_temporal(self):
        with tempfile.TemporaryDirectory() as d:
            conn = sb.open_db(os.path.join(d, 'x.db'))
            conn.execute("INSERT INTO signals (symbol, candle_epoch, created_utc, direction) VALUES (?,?,?,?)",
                         ('frxEURUSD', 1, '2026-10-26T10:00:00', 'CALL'))
            conn.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO signals (symbol, candle_epoch, created_utc, direction) VALUES (?,?,?,?)",
                             ('frxEURUSD', 1, '2026-10-26T10:05:00', 'PUT'))
            conn.close()


if __name__ == '__main__':
    unittest.main()
