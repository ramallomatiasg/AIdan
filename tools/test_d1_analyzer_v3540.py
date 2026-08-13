"""
test_d1_analyzer_v3540.py — tests del analyzer D1 (track D shadow).

NO toca la DB de produccion ni la red: todo con dobles. Es deliberado — el
11-ago un test escribio 30 filas en la DB real por correr una funcion de
verdad con el harness parcheado a medias (v3.53.6).

Cubre:
  1. El profile es coherente (R:R 2, expiry = 10 dias de mercado).
  2. Los overrides de la subclase (label, cache TTL, dedup).
  3. FAIL-CLOSED: solo MT5, y validando el ESPACIADO real de las velas
     (no una etiqueta que otro thread puede pisar).
  4. Que se pide el interval '1d' y no '1day' (MT5 solo entiende '1d';
     el resto de las fuentes usan '1day' — la trampa de nombres).
  5. Que None se degrada a "sin señales" y NO a una excepcion.
  6. Test de mutacion sobre el guard estructural.
"""
import os
import sys
import logging
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.analyzer.technical_d1 import (  # noqa: E402
    TechnicalAnalyzerD1, D1_PROFILE, D1_INTERVAL)

def _iso(ts):
    """Mismo formato que escribe el path de MT5 (price_feed.py:153)."""
    from datetime import datetime, timezone
    return str(datetime.fromtimestamp(ts, tz=timezone.utc))


# Velas diarias bien formadas: espaciado 86400s y datetime ISO.
FAKE_CANDLES = [{'open': 1.15, 'high': 1.16, 'low': 1.14, 'close': 1.155,
                 'datetime': _iso(1700000000 + i * 86400)} for i in range(100)]


def _logger():
    lg = logging.getLogger('test_d1')
    lg.addHandler(logging.NullHandler())
    lg.setLevel(logging.CRITICAL)
    return lg


class TestD1Profile(unittest.TestCase):

    def test_rr_ratio_es_2(self):
        rr = D1_PROFILE['take_profit_pips'] / D1_PROFILE['stop_loss_pips']
        self.assertEqual(rr, 2.0, "el backtest se corrio con R:R 2")

    def test_sl_coherente_con_atr_diario(self):
        # ATR-14 mediano medido en D1 = 71,6p. SL = 1,5xATR ~ 107p.
        self.assertGreater(D1_PROFILE['stop_loss_pips'], 71.6,
                           "un SL por debajo de 1 ATR diario es ruido")
        self.assertLess(D1_PROFILE['stop_loss_pips'], 71.6 * 2.5)

    def test_expiry_es_diez_dias_de_mercado(self):
        self.assertEqual(D1_PROFILE['expiry_minutes'], 10 * 1440)

    def test_interval_es_el_que_entiende_mt5(self):
        # price_feed.py:117 mapea '1d' -> TIMEFRAME_D1. La clave '1day' la
        # usan Yahoo/FXCM/TwelveData y MT5 la ignora (devolveria None).
        self.assertEqual(D1_INTERVAL, '1d')


class TestD1Subclase(unittest.TestCase):

    def setUp(self):
        self.a = TechnicalAnalyzerD1(_logger())

    def test_overrides(self):
        self.assertEqual(self.a.timeframe_label, 'D1')
        self.assertEqual(self.a._cache_ttl, 300)
        self.assertEqual(self.a._dedup_window_sec, 172800)  # 2 dias

    def test_dedup_mas_largo_que_la_vela(self):
        self.assertGreaterEqual(self.a._dedup_window_sec, 86400,
                                "un nivel diario no puede re-disparar el mismo dia")


class TestFuenteSoloMT5(unittest.TestCase):
    """Desde v3.54.0 se llama a _fetch_mt5 DIRECTO, no a fetch_candles(): asi no
    se paga la cadena de fallback (Yahoo+TwelveData+FXCM, ~30s bloqueando el
    ciclo vivo) para despues tirar el resultado, y no se depende del global
    get_last_source(), que otro thread puede pisar."""

    def _run(self, candles):
        a = TechnicalAnalyzerD1(_logger())
        with patch('src.common.price_feed._fetch_mt5', return_value=candles):
            return a._fetch_candles()

    def test_velas_diarias_de_mt5_pasan(self):
        r = self._run(FAKE_CANDLES)
        self.assertIsNotNone(r)
        self.assertEqual(len(r), 100)

    def test_mt5_sin_datos(self):
        self.assertIsNone(self._run(None))
        self.assertIsNone(self._run([]))

    def test_muestra_corta_se_rechaza(self):
        self.assertIsNone(self._run(FAKE_CANDLES[:20]))

    def test_no_llama_a_la_cadena_de_fallback(self):
        """El bug que se arreglo: fetch_candles() recorre Yahoo/TwelveData/FXCM
        aunque el resultado se vaya a descartar.

        Se usa AST y no busqueda de texto: los docstrings y comentarios del
        modulo MENCIONAN fetch_candles y get_last_source para explicar por que
        NO se usan, y un assertNotIn sobre el texto matchea esa prosa. Es el
        mismo error que cometi en test_startup_eval_guard_v3532.
        """
        import ast
        import src.analyzer.technical_d1 as mod
        arbol = ast.parse(open(mod.__file__, encoding='utf-8').read())

        importados = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.ImportFrom) and 'price_feed' in (n.module or ''):
                importados.update(a.name for a in n.names)
        self.assertIn('_fetch_mt5', importados)
        self.assertNotIn('fetch_candles', importados,
                         "fetch_candles arrastra la cadena de fallback")
        self.assertNotIn('get_last_source', importados,
                         "no debe depender del global compartido entre threads")

        llamadas = {n.func.id for n in ast.walk(arbol)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertNotIn('get_last_source', llamadas)


class TestDegradacionSinFuente(unittest.TestCase):
    """None debe leerse como 'no escanear', nunca como excepcion."""

    def test_detect_structure_signals_devuelve_lista_vacia(self):
        a = TechnicalAnalyzerD1(_logger())
        with patch.object(TechnicalAnalyzerD1, '_fetch_candles', return_value=None):
            try:
                sigs = a.detect_structure_signals(min_confidence=60)
            except Exception as e:
                self.fail(f"None no debe propagar excepcion: {type(e).__name__}: {e}")
        self.assertEqual(sigs, [], "sin velas no hay señales, y no hay crash")

    def test_get_market_state_cae_a_fallback(self):
        a = TechnicalAnalyzerD1(_logger())
        with patch.object(TechnicalAnalyzerD1, '_fetch_candles', return_value=None):
            st = a.get_market_state()
        self.assertEqual(st.get('source'), 'fallback')


class TestBloqueShadowNoOpera(unittest.TestCase):
    """EL test que importa: el bloque D1 del monolito no puede crear estrategia
    ni mandar orden. La frontera es add_auto_strategy (linea ~3685 del molde H1)."""

    @classmethod
    def setUpClass(cls):
        src = open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8').read()
        # rindex, NO index: el mismo texto aparece dos veces (el comentario de la
        # inicializacion del analyzer y el del bloque del loop). Con index se
        # capturaba medio servicio y el test fallaba por codigo ajeno.
        ini = src.rindex('Track D: swing DIARIO (D1) en SHADOW')
        fin = src.index('except Exception as _d1_e', ini)
        bloque = src[ini:fin]
        # Sacar comentarios: si no, el texto que EXPLICA que no llamamos a
        # add_auto_strategy hace matchear el test. Es el error exacto que cometi
        # en test_startup_eval_guard_v3532.
        cls.codigo = '\n'.join(l for l in bloque.splitlines()
                               if not l.strip().startswith('#'))
        cls.bloque_crudo = bloque

    def test_no_crea_estrategia(self):
        self.assertNotIn('add_auto_strategy', self.codigo)

    def test_no_manda_orden(self):
        self.assertNotIn('_try_mt5_execute', self.codigo)

    def test_no_escribe_en_tablas_del_vivo(self):
        for prohibido in ('log_level_quality', 'update_mt5_', 'archive_trade',
                          'record_signal_result', 'auto_evaluate'):
            self.assertNotIn(prohibido, self.codigo, f"el shadow no debe tocar {prohibido}")

    def test_si_loguea_al_shadow(self):
        self.assertIn('_d1_log(', self.codigo)
        self.assertIn('_d1_seen(', self.codigo)

    def test_usa_alias_locales_no_nombres_de_modulo(self):
        # `datetime` y `Config` no existen a nivel de modulo en el monolito.
        self.assertIn('from datetime import datetime as _d1_dt', self.codigo)
        self.assertNotIn('_dt_mod', self.codigo)

    def test_except_loguea_como_error_no_lo_traga(self):
        # La clase de bug que mato a M15 (v3.33.0) y SMC (v3.50.4).
        src = open(os.path.join(ROOT, 'AIdan_TodoEnUno.py'), encoding='utf-8').read()
        i = src.index('except Exception as _d1_e')
        cola = src[i:i + 200]
        self.assertIn('logger.error', cola)
        self.assertNotIn('pass', cola.split('\n')[1])

    def test_throttle_se_marca_antes_de_trabajar(self):
        # Si se marcara despues, un fallo reintentaria cada 10s en vez de cada 900s.
        i_if = self.codigo.index('_last_d1_scan) >= D1_SCAN_INTERVAL')
        i_set = self.codigo.index('_last_d1_scan = time.time()', i_if)
        i_fetch = self.codigo.index('_fetch_candles()', i_if)
        self.assertLess(i_set, i_fetch)

    def test_respeta_el_modo_off(self):
        self.assertIn("_d1_mode != 'off'", self.codigo,
                      "debe ser != 'off' y NO == 'active', si no el shadow no corre")

    def test_prefijo_d1_en_las_variables(self):
        """Colision de nombres: M15 usa _top/_tk y H1 usa _h1_top/_tk en el MISMO
        scope de funcion. El D1 tiene que prefijar todo."""
        import re
        asignadas = set(re.findall(r'^\s*(_[a-z0-9_]+)\s*=', self.codigo, re.M))
        self.assertTrue(asignadas, "el regex no encontro ninguna asignacion (test roto)")
        for v in asignadas:
            self.assertTrue(v.startswith('_d1') or v.startswith('_last_d1'),
                            f"variable sin prefijo _d1: {v} (puede pisar a M15/H1)")


class TestDbShadowAislada(unittest.TestCase):
    """DB TEMPORAL. Nunca produccion (incidente v3.53.6: un test escribio 30 filas
    reales por parchear el harness a medias)."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        import sqlite3
        import src.common.db as dbmod
        cls.dbmod = dbmod
        cls._orig_path, cls._orig_conn = dbmod.DB_PATH, dbmod._connect
        cls.tmp = os.path.join(tempfile.mkdtemp(), 'd1test.db')
        dbmod.DB_PATH = cls.tmp
        dbmod._connect = lambda *a, **k: sqlite3.connect(cls.tmp, timeout=15)
        dbmod.init_db()
        cls.sqlite3 = sqlite3

    @classmethod
    def tearDownClass(cls):
        cls.dbmod.DB_PATH = cls._orig_path
        cls.dbmod._connect = cls._orig_conn

    def _con(self):
        return self.sqlite3.connect(self.tmp)

    def test_tabla_tiene_fav_y_adv(self):
        cols = [r[1] for r in self._con().execute("PRAGMA table_info(d1_shadow_log)")]
        # Medir solo lo favorable sobreestima el edge (leccion de fade-chop).
        self.assertIn('outcome_fav_pips', cols)
        self.assertIn('outcome_adv_pips', cols)
        self.assertIn('d1_candle_ts', cols)

    def test_insert_e_idempotencia(self):
        ts = 1786000000
        self.assertFalse(self.dbmod.d1_shadow_already_logged(ts))
        self.dbmod.log_d1_shadow(ts, 'PUT', 'breakdown_support', 1.152, 1.155, 4,
                                 71.6, 38.0, 'bearish', 'bearish', 72, 107.0, 214.0,
                                 [{'close': 1.152}])
        self.assertTrue(self.dbmod.d1_shadow_already_logged(ts))

    def test_created_at_en_hora_AR_no_UTC(self):
        """Si queda en UTC, el scorer da numeros plausibles y FALSOS (v3.40.11)."""
        import datetime as dt
        ts = 1786000123
        self.dbmod.log_d1_shadow(ts, 'CALL', 'breakout_resistance', 1.16, 1.159, 3,
                                 70.0, 55.0, 'bullish', 'bullish', 68, 105.0, 210.0, [])
        raw = self._con().execute(
            "SELECT created_at FROM d1_shadow_log WHERE d1_candle_ts = ?", (ts,)
        ).fetchone()[0]
        delta = abs((dt.datetime.fromisoformat(raw) - self.dbmod.now_ar()).total_seconds())
        self.assertLess(delta, 120, f"created_at desfasado {delta:.0f}s (3h = UTC)")

    def test_db_caida_no_rompe_el_scan(self):
        orig = self.dbmod._connect
        self.dbmod._connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caida"))
        try:
            self.dbmod.log_d1_shadow(1, 'PUT', 'x', 1, 1, 1, 1, 1, 'a', 'b', 1, 1, 1, [])
            # ante error de lectura devuelve True: perder una fila del shadow no
            # cuesta nada, duplicarla ensucia el n del scorer.
            self.assertTrue(self.dbmod.d1_shadow_already_logged(1))
        finally:
            self.dbmod._connect = orig


class TestValidacionEstructural(unittest.TestCase):
    """El guard que NO depende de get_last_source() (global compartido entre
    threads: el dashboard llama a fetch_candles desde otro thread y puede
    pisar la etiqueta entre nuestro fetch y nuestra lectura)."""

    def setUp(self):
        self.a = TechnicalAnalyzerD1(_logger())

    @staticmethod
    def _velas(step_seg, n=40, iso=True):
        from datetime import datetime, timezone
        base = 1700000000
        out = []
        for i in range(n):
            t = base + i * step_seg
            dtxt = (str(datetime.fromtimestamp(t, tz=timezone.utc)) if iso else str(t))
            out.append({'open': 1.15, 'high': 1.16, 'low': 1.14,
                        'close': 1.155, 'datetime': dtxt})
        return out

    def test_diarias_pasan(self):
        self.assertTrue(self.a._son_velas_diarias(self._velas(86400)))

    def test_cinco_minutos_se_rechazan(self):
        """El escenario exacto del bug: Yahoo devuelve M5 etiquetado como 1d."""
        self.assertFalse(self.a._son_velas_diarias(self._velas(300)))

    def test_h1_y_h4_se_rechazan(self):
        self.assertFalse(self.a._son_velas_diarias(self._velas(3600)))
        self.assertFalse(self.a._son_velas_diarias(self._velas(14400)))

    def test_fin_de_semana_no_rompe(self):
        """Gaps de 3 dias viernes->lunes: la MEDIANA aguanta, el promedio no."""
        v = self._velas(86400, n=40)
        from datetime import datetime, timezone
        # cada 5 velas, un salto de finde
        t = 1700000000
        v = []
        for i in range(40):
            t += 86400 * (3 if i % 5 == 0 else 1)
            v.append({'open': 1.15, 'high': 1.16, 'low': 1.14, 'close': 1.155,
                      'datetime': str(datetime.fromtimestamp(t, tz=timezone.utc))})
        self.assertTrue(self.a._son_velas_diarias(v))

    def test_datetime_no_iso_se_rechaza(self):
        """Yahoo escribe el epoch crudo como string, no ISO."""
        self.assertFalse(self.a._son_velas_diarias(self._velas(86400, iso=False)))

    def test_falta_la_clave_datetime(self):
        self.assertFalse(self.a._son_velas_diarias([{'close': 1.1}] * 30))

    def test_fetch_rechaza_velas_no_diarias_aunque_vengan_de_mt5(self):
        """Defensa en profundidad: aunque la fuente sea MT5 por construccion,
        si el espaciado no es diario no se scanea."""
        from unittest.mock import patch as _p
        with _p('src.common.price_feed._fetch_mt5', return_value=self._velas(300)):
            self.assertIsNone(self.a._fetch_candles())


if __name__ == '__main__':

    unittest.main(verbosity=2)
