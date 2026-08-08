"""v3.52.0 — Tests del cap del umbral de break-even por track.

Verifica la LOGICA del cap (la formula que corre en el trailing thread) contra los
casos REALES de h1 medidos el 8-ago, mas los controles de que m15/M5 no se tocan.

No necesita MT5 ni la DB de produccion: replica la formula y la alimenta con los
numeros observados. Correr con: python tools/test_be_cap_v3520.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PIP = 0.0001
BE_TRIGGER = 0.50          # constante viva del trailing thread
BE_OFFSET_PIPS = 1.0       # v3.40.19


def be_threshold_pips(tp_pips, trigger_type, cap_pips, cap_tracks):
    """Replica exacta de la formula del trailing thread (AIdan_TodoEnUno.py).

    be_threshold = tp_distance * BE_TRIGGER, capeado a cap_pips si el track aplica.
    Devuelve el umbral en PIPS (el thread trabaja en precio; el factor se cancela).
    """
    tp_distance = tp_pips * PIP
    be_threshold = tp_distance * BE_TRIGGER
    cap_dist = cap_pips * PIP if cap_pips > 0 else None
    if cap_dist and cap_tracks and trigger_type in cap_tracks:
        be_threshold = min(be_threshold, cap_dist)
    return be_threshold / PIP


DEFAULT_CAP = 5.0
DEFAULT_TRACKS = {'h1_structure'}


class TestBeCapH1(unittest.TestCase):
    """El caso que motivo el cambio."""

    def test_h1_sin_cap_arma_a_27p_inalcanzable(self):
        """Comportamiento previo: TP 54p => BE a 27p. HWM max historico = 26.3p."""
        thr = be_threshold_pips(54.0, 'h1_structure', 0, set())
        self.assertAlmostEqual(thr, 27.0, places=3)
        self.assertGreater(thr, 26.3, "el BE quedaba por encima del mejor HWM de la historia")

    def test_h1_con_cap_arma_a_5p(self):
        thr = be_threshold_pips(54.0, 'h1_structure', DEFAULT_CAP, DEFAULT_TRACKS)
        self.assertAlmostEqual(thr, 5.0, places=3)

    def test_los_6_perdedores_reales_ahora_arman(self):
        """Perdedores h1 que tocaron >=5p a favor y cerraron negativo (8-ago).

        (strategy_id, hwm_pips, pips_cierre). Con el cap los 6 arman BE => cierran
        en +1p (BE_OFFSET) en vez de en negativo.
        """
        casos = [(877, 11.0, -2.5), (858, 10.8, -1.4), (721, 8.4, -0.5),
                 (747, 7.8, -5.6), (764, 5.7, -2.3), (772, 5.2, -3.9)]
        thr = be_threshold_pips(54.0, 'h1_structure', DEFAULT_CAP, DEFAULT_TRACKS)
        for sid, hwm, cierre in casos:
            with self.subTest(sid=sid):
                self.assertGreaterEqual(hwm, thr, f"#{sid} deberia armar el BE")
                # cerro por debajo del BE => paso por +1p en la bajada => el BE lo agarra
                self.assertLess(cierre, BE_OFFSET_PIPS,
                                f"#{sid} cerro debajo del BE, el stop lo habria tomado")

    def test_los_8_ganadores_reales_NO_se_cortan(self):
        """Ganadores h1 que tocaron >=5p: ninguno bajo de +3.9p => nunca volvieron
        al BE de +1p => el cap no los corta. Es el control que valida el cambio."""
        casos = [(835, 26.3, 16.5), (704, 18.5, 3.9), (773, 12.5, 8.4), (851, 12.0, 10.4),
                 (844, 10.7, 6.5), (701, 10.2, 9.6), (588, 10.0, 7.8), (657, 5.8, 3.9)]
        for sid, hwm, cierre in casos:
            with self.subTest(sid=sid):
                self.assertGreater(cierre, BE_OFFSET_PIPS,
                                   f"#{sid} cerro arriba del BE => el stop NO lo toco")

    def test_h1_con_tp_chico_no_se_afloja(self):
        """Monotonia: si el TP fuera chico (BE a 3p), el cap de 5p NO debe atrasarlo."""
        thr = be_threshold_pips(6.0, 'h1_structure', DEFAULT_CAP, DEFAULT_TRACKS)
        self.assertAlmostEqual(thr, 3.0, places=3)


class TestOtrosTracksIntactos(unittest.TestCase):
    """m15 es el motor (+$32.64): no se toca. M5 tampoco."""

    def test_m15_no_cambia(self):
        sin_cap = be_threshold_pips(18.0, 'm15_structure', 0, set())
        con_cap = be_threshold_pips(18.0, 'm15_structure', DEFAULT_CAP, DEFAULT_TRACKS)
        self.assertAlmostEqual(sin_cap, 9.0, places=3)
        self.assertAlmostEqual(con_cap, 9.0, places=3)

    def test_m5_no_cambia(self):
        sin_cap = be_threshold_pips(5.0, 'structure', 0, set())
        con_cap = be_threshold_pips(5.0, 'structure', DEFAULT_CAP, DEFAULT_TRACKS)
        self.assertAlmostEqual(sin_cap, 2.5, places=3)
        self.assertAlmostEqual(con_cap, 2.5, places=3)

    def test_news_y_smc_no_cambian(self):
        for trk, tp in (('news', 7.7), ('smc', 12.0)):
            with self.subTest(track=trk):
                self.assertAlmostEqual(
                    be_threshold_pips(tp, trk, 0, set()),
                    be_threshold_pips(tp, trk, DEFAULT_CAP, DEFAULT_TRACKS), places=3)


class TestMonotonia(unittest.TestCase):
    """El min() nunca puede ATRASAR el BE. Es la garantia de seguridad del cambio."""

    def test_nunca_afloja_en_ningun_caso(self):
        for tp in (2, 5, 7.7, 12, 18, 40, 54, 63, 100):
            for trk in ('h1_structure', 'm15_structure', 'structure', 'news', 'smc'):
                sin_cap = be_threshold_pips(tp, trk, 0, set())
                con_cap = be_threshold_pips(tp, trk, DEFAULT_CAP, DEFAULT_TRACKS)
                with self.subTest(tp=tp, track=trk):
                    self.assertLessEqual(con_cap, sin_cap + 1e-9,
                                         "el cap solo puede adelantar el BE")


class TestApagado(unittest.TestCase):
    """Reversa por env sin rebuild."""

    def test_cap_cero_apaga(self):
        self.assertAlmostEqual(
            be_threshold_pips(54.0, 'h1_structure', 0, DEFAULT_TRACKS), 27.0, places=3)

    def test_lista_vacia_apaga(self):
        self.assertAlmostEqual(
            be_threshold_pips(54.0, 'h1_structure', DEFAULT_CAP, set()), 27.0, places=3)

    def test_track_none_no_crashea(self):
        """row[13] puede venir NULL en filas viejas."""
        self.assertAlmostEqual(
            be_threshold_pips(54.0, None, DEFAULT_CAP, DEFAULT_TRACKS), 27.0, places=3)


class TestConfigReal(unittest.TestCase):
    """La config que se shipea es la que se midio."""

    def test_defaults(self):
        from src.common.config import Config
        self.assertEqual(Config.BE_TRIGGER_MAX_PIPS, 5.0)
        self.assertEqual(Config.BE_TRIGGER_MAX_TRACKS, 'h1_structure')

    def test_query_devuelve_trigger_type_en_indice_13(self):
        """El trailing thread lee row[13]. Si el SELECT cambia de orden, esto lo caza."""
        import re
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'src', 'common', 'db.py'), encoding='utf-8').read()
        m = re.search(r'def get_strategies_with_open_mt5.*?SELECT (.*?)\s+FROM', src, re.S)
        self.assertIsNotNone(m, "no se encontro la query")
        cols = [c.strip() for c in m.group(1).replace('\n', ' ').split(',')]
        self.assertEqual(cols[13], 'trigger_type',
                         f"trigger_type debe quedar en el indice 13, esta en {cols}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
