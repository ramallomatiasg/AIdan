"""
Tests del helper de offset server-UTC (tools/mt5_server_offset.py), 20-sep-2026.

El bug que cubren: con el mercado cerrado `tick.time - time.time()` da ~-44h y el
scorer puntuaba ventanas de OTRO dia con numeros plausibles. En orden de importancia:
  (1) tick viejo SIN cache => error, nunca un numero;
  (2) tick fresco => offset correcto y se cachea;
  (3) tick viejo CON cache => usa el cache;
  (4) override manual;
  (5) test de FUENTE: ningun tool de tools/ vuelve a la formula cruda.
No tocan DB ni MT5.
"""
import glob
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mt5_server_offset import derive_offset_s, StaleTickError  # noqa: E402

NOW = 1789936519.0            # dom 20-sep-2026 20:35 UTC (la corrida contaminada)
FRIDAY_CLOSE_TICK = 1789775819  # vie 18-sep 23:56:59 hora server (+3h) => -44,6h de NOW
THURSDAY = NOW - 3 * 86400    # jue 17-sep 20:35 UTC, mercado abierto
# Caso real del 10-oct: corrida a las 00:08:59 UTC del sabado, ultimo tick 23:59:5x server
SAT_AFTER_CLOSE = 1791590939.0
OCT9_CLOSE_TICK = 1791590939 - 9 * 60 + 10800  # 23:59:59 server => raw = -9 min


class TestOffset(unittest.TestCase):
    def setUp(self):
        self.cache = os.path.join(HERE, '.test_offset_cache.json')
        if os.path.exists(self.cache):
            os.remove(self.cache)

    def tearDown(self):
        if os.path.exists(self.cache):
            os.remove(self.cache)

    def test_1_tick_viejo_sin_cache_aborta(self):
        # El caso EXACTO del 20-sep: la formula cruda daba -160200 (~-44,5h) y seguia.
        with self.assertRaises(StaleTickError):
            derive_offset_s(FRIDAY_CLOSE_TICK, now=NOW, cache_path=self.cache)
        self.assertFalse(os.path.exists(self.cache), 'un tick viejo no debe escribir cache')

    def test_2_tick_fresco_deriva_y_cachea(self):
        # 17-oct: NOW es domingo pre-apertura (mercado cerrado) => el "fresco" va en jueves
        NOW = THURSDAY
        off = derive_offset_s(NOW + 3 * 3600 + 17, now=NOW, cache_path=self.cache)
        self.assertEqual(off, 10800)
        with open(self.cache, encoding='utf-8') as f:
            self.assertEqual(json.load(f)['offset_s'], 10800)
        # invierno del broker (+2h) tambien es fresco
        self.assertEqual(derive_offset_s(NOW + 2 * 3600 - 40, now=NOW, cache_path=self.cache), 7200)

    def test_3_tick_viejo_con_cache_usa_cache(self):
        derive_offset_s(NOW - 3 * 86400 + 10800, now=NOW - 3 * 86400, cache_path=self.cache)  # medido el jueves
        self.assertEqual(derive_offset_s(FRIDAY_CLOSE_TICK, now=NOW, cache_path=self.cache), 10800)

    def test_7_cierre_reciente_no_se_cachea_como_offset_0(self):
        # sin cache: tiene que abortar, no devolver 0 (lo que paso el 10-oct)
        with self.assertRaises(StaleTickError):
            derive_offset_s(OCT9_CLOSE_TICK, now=SAT_AFTER_CLOSE, cache_path=self.cache)
        self.assertFalse(os.path.exists(self.cache))

    def test_8_cierre_reciente_con_cache_bueno_usa_cache(self):
        derive_offset_s(THURSDAY + 10800, now=THURSDAY, cache_path=self.cache)
        self.assertEqual(derive_offset_s(OCT9_CLOSE_TICK, now=SAT_AFTER_CLOSE,
                                         cache_path=self.cache), 10800)

    def test_9_cache_con_offset_imposible_se_ignora(self):
        with open(self.cache, 'w', encoding='utf-8') as f:
            json.dump({'offset_s': 0, 'measured_at_utc': 1791590939}, f)
        with self.assertRaises(StaleTickError):
            derive_offset_s(FRIDAY_CLOSE_TICK, now=NOW, cache_path=self.cache)

    def test_10_offset_fuera_de_icmarkets_no_se_acepta_en_semana(self):
        with self.assertRaises(StaleTickError):
            derive_offset_s(THURSDAY - 1800, now=THURSDAY, cache_path=self.cache)

    def test_4_override_manual(self):
        self.assertEqual(derive_offset_s(0, now=NOW, override_hours=3, cache_path=self.cache), 10800)
        self.assertEqual(derive_offset_s(0, now=NOW, override_hours=2.5, cache_path=self.cache), 9000)

    def test_5_fuente_ningun_tool_usa_la_formula_cruda(self):
        # Si alguien vuelve a `round((tick.time - time.time()) / 1800.0) * 1800` en un
        # scorer, este test falla: la formula solo puede vivir en el helper.
        pat = re.compile(r'tick\.time\s*-\s*_?(?:time|_t|_time)\.time\(\)')
        culpables = []
        for path in glob.glob(os.path.join(HERE, '*.py')):
            if os.path.basename(path) in ('mt5_server_offset.py', os.path.basename(__file__)):
                continue
            with open(path, encoding='utf-8', errors='replace') as f:
                if pat.search(f.read()):
                    culpables.append(os.path.basename(path))
        self.assertEqual(culpables, [], f'formula cruda de offset fuera del helper: {culpables}')

    def test_6_scorers_importan_el_helper(self):
        for name in ('score_shadow_trader.py', 'score_rejected_signals.py',
                     'score_d1_shadow.py', 'measure_atr_percentile_floor.py'):
            with open(os.path.join(HERE, name), encoding='utf-8') as f:
                self.assertIn('mt5_offset_s', f.read(), name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
