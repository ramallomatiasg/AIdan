"""Tests de v3.61.1 - guard de EDAD de la senal en la ejecucion (clase #625).

Que cubre y por que:

* El guard vive dentro de un closure del monolito (_try_mt5_execute) => no se
  puede unit-testear la funcion directamente. Se sigue el patron de
  test_m15_atr_floor_v3550: tests de MUTACION que extraen la condicion REAL del
  fuente y la verifican. Un test que solo probara "una funcion parecida" habria
  estado en verde con el guard desconectado — el sintoma clasico del proyecto.
* Default 10 min y no otra cosa: es el MISMO umbral que el event-window usa
  desde v3.40.14 para etiquetar "senal VIEJA" — no se invento un numero nuevo
  sobre n=11.
* pre_planned y calendar EXENTOS: esperan su event_time por diseno; un guard
  sin la exencion los mataria a todos (se ejecutan SOLO por el retry).
* El status 'skipped_stale' tiene que quedar protegido por el guard de v3.53.6
  (que evita que auto_evaluate_strategy lo pise con 'auto_loss') — se verifica
  que ese guard use un patron que lo cubra.

No toca la DB de produccion ni MT5.
"""

import io
import os
import re
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _leer(path):
    return io.open(os.path.join(ROOT, path), encoding='utf-8').read()


class TestPerillaConfig(unittest.TestCase):
    def test_default_es_10(self):
        import importlib
        env = {k: v for k, v in os.environ.items() if k != 'SIGNAL_MAX_AGE_MIN'}
        with mock.patch.dict(os.environ, env, clear=True):
            import src.common.config as cfg
            importlib.reload(cfg)
            self.assertEqual(cfg.Config.SIGNAL_MAX_AGE_MIN, 10.0,
                             "el default tiene que ser 10 (el umbral del event-window "
                             "de v3.40.14), no un numero nuevo")

    def test_env_var_pisa(self):
        import importlib
        with mock.patch.dict(os.environ, {'SIGNAL_MAX_AGE_MIN': '25'}, clear=False):
            import src.common.config as cfg
            importlib.reload(cfg)
            self.assertEqual(cfg.Config.SIGNAL_MAX_AGE_MIN, 25.0)

    def test_cero_apaga(self):
        import importlib
        with mock.patch.dict(os.environ, {'SIGNAL_MAX_AGE_MIN': '0'}, clear=False):
            import src.common.config as cfg
            importlib.reload(cfg)
            self.assertEqual(cfg.Config.SIGNAL_MAX_AGE_MIN, 0.0)


class TestGuardEnElFuente(unittest.TestCase):
    """Tests de mutacion sobre AIdan_TodoEnUno.py: el guard existe, esta en el
    lugar correcto y con la forma correcta."""

    @classmethod
    def setUpClass(cls):
        cls.src = _leer('AIdan_TodoEnUno.py')
        # el bloque del guard completo
        i = cls.src.find('STALE-signal guard')
        assert i > 0, "no se encuentra el guard en el fuente"
        cls.i_guard = i
        cls.bloque = cls.src[max(0, i - 3000):i + 1500]

    def test_el_guard_existe_dentro_de_try_mt5_execute(self):
        i_def = self.src.find('def _try_mt5_execute')
        self.assertGreater(i_def, 0)
        # el proximo def despues de _try_mt5_execute delimita el closure
        i_next = self.src.find('\n            def ', i_def + 10)
        self.assertTrue(i_def < self.i_guard < i_next,
                        "el guard tiene que vivir DENTRO de _try_mt5_execute, que es "
                        "el unico punto por el que pasan la ejecucion normal Y el retry")

    def test_lee_la_perilla_y_no_hardcodea(self):
        self.assertIn("getattr(Config, 'SIGNAL_MAX_AGE_MIN'", self.bloque,
                      "el umbral tiene que salir de Config (env, sin rebuild)")
        self.assertIn('if _max_age > 0', self.bloque,
                      "0 tiene que apagar el guard")

    def test_exime_pre_planned_y_calendar(self):
        m = re.search(r"not in \(([^)]*)\)", self.bloque)
        self.assertIsNotNone(m, "no se encuentra la lista de exentos")
        exentos = m.group(1)
        self.assertIn("'pre_planned'", exentos,
                      "pre_planned espera su event_time por diseno y se ejecuta SOLO "
                      "por el retry: sin exencion el guard lo mata siempre")
        self.assertIn("'calendar'", exentos)

    def test_marca_skipped_stale_y_corta(self):
        self.assertIn("status='skipped_stale'", self.bloque)
        # el return None tiene que estar despues del UPDATE, dentro del guard
        i_upd = self.bloque.find("skipped_stale")
        i_ret = self.bloque.find("return None", i_upd)
        self.assertGreater(i_ret, i_upd,
                           "el guard tiene que devolver None despues de marcar el status")

    def test_solo_pisa_status_active(self):
        self.assertIn("AND status='active'", self.bloque,
                      "el UPDATE no puede pisar un status que ya conto otra cosa "
                      "(la leccion de v3.53.6)")

    def test_condicion_de_edad_es_mayor_estricto(self):
        self.assertIn('_age_min > _max_age', self.bloque,
                      "la condicion real cambio de forma; revisar que siga comparando "
                      "edad contra el umbral")

    def test_el_guard_corre_antes_del_cooldown(self):
        """El orden importa: una senal vieja no debe gastar el cooldown ni el
        bounce-log — se descarta primero por edad."""
        i_cd = self.src.find('COOLDOWN POST-PERDIDA')
        self.assertGreater(i_cd, 0)
        self.assertLess(self.i_guard, i_cd,
                        "el guard de edad quedo DESPUES del cooldown")


class TestSkipStatusProtegido(unittest.TestCase):
    def test_v3536_cubre_skipped_stale(self):
        """El guard de v3.53.6 evita que auto_evaluate_strategy pise el status de
        una senal skipeada. Tiene que cubrir 'skipped_stale' — hoy lo hace via
        startswith('skipped'). Si alguien lo cambia a una lista cerrada sin
        incluirlo, 'skipped_stale' apareceria como perdida falsa en el dashboard."""
        src = _leer(os.path.join('src', 'common', 'db.py'))
        i = src.find('_skip_status = None')
        self.assertGreater(i, 0, "desaparecio el guard de v3.53.6")
        ventana = src[i:i + 600]
        cubierto = ("startswith('skipped')" in ventana) or ("'skipped_stale'" in ventana)
        self.assertTrue(cubierto,
                        "el guard de v3.53.6 ya no cubre 'skipped_stale'")


class TestLogicaDeEdad(unittest.TestCase):
    """La condicion, extraida y ejecutada con valores del caso real."""

    @staticmethod
    def _guard_bloquea(age_min, max_age, trigger):
        # replica exacta de la condicion del fuente
        if max_age <= 0:
            return False
        if trigger in ('pre_planned', 'calendar'):
            return False
        return age_min > max_age

    def test_caso_625_queda_bloqueado(self):
        # #625: m15_structure, 27,6 min sin fill, ejecutada dentro de un spike
        self.assertTrue(self._guard_bloquea(27.6, 10, 'm15_structure'))

    def test_fill_normal_pasa(self):
        # el 98% de los fills: edad ~0
        self.assertFalse(self._guard_bloquea(0.1, 10, 'news'))

    def test_pre_planned_viejo_pasa(self):
        self.assertFalse(self._guard_bloquea(300.0, 10, 'pre_planned'))

    def test_apagado_no_bloquea_nada(self):
        self.assertFalse(self._guard_bloquea(999.0, 0, 'news'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
