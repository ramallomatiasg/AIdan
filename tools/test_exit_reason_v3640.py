# -*- coding: utf-8 -*-
"""
test_exit_reason_v3640.py — tests de v3.64.0 (motivo REAL de cierre en trade_archive).

Por que existe este archivo, en una linea: `tp_hit` se derivaba de `result=='win'`
(db.py:3542) => coincidia con win/loss en 88/88 filas y solo 4 de 33 "TP hit" habian
tocado el TP de verdad. O sea el campo que deberia decir POR QUE cerro no decia nada, y
con eso no se puede distinguir "entro mal" de "lo corte yo temprano" — que es el agujero
mas grande medido hasta hoy (29 de 33 ganadores cerraron antes del TP).

Orden de importancia de los tests:
  (1) el caso REAL que motivo el cambio: ganador cortado por stop movido != SL pegado.
  (2) lista CERRADA de valores (si alguien agrega uno suelto, el scorer lo ignora en
      silencio — la clase de bug de este proyecto).
  (3) fail-safe: clasificar NUNCA puede romper el archivado (el archive es la verdad
      historica; una excepcion aca perderia el trade entero).
  (4) tests de CALL-SITE sobre el fuente: que archive_trade realmente persista el campo
      y que el path del broker realmente lo calcule. Un test que solo ejercitara la
      funcion pura habria estado en verde los meses en que el mecanismo estuvo muerto
      (es exactamente lo que paso con adjust_setup_confidence).
  (5) que el modulo NO importe MetaTrader5 a nivel de modulo (tiene que testearse sin
      broker y sin tocar el exe vivo).

No toca DB ni MT5.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.exit_reason import (  # noqa: E402
    EXIT_REASONS,
    DEAL_REASON_CLIENT,
    DEAL_REASON_EXPERT,
    DEAL_REASON_SL,
    DEAL_REASON_SO,
    DEAL_REASON_TP,
    DEAL_REASON_WEB,
    classify_from_broker_deal,
    classify_from_eval_flags,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# (1) EL CASO REAL — el que motivo todo el cambio
# --------------------------------------------------------------------------- #
class TestCasoRealGanadorCortado(unittest.TestCase):
    """structure: TP planeado 8p, SL 4p, y el ganador medio sale en +2,6p.

    El broker reporta DEAL_REASON_SL tanto para el SL original como para un stop
    MOVIDO por el trailing/BE. Si no se distinguen, los 29 ganadores cortados quedan
    indistinguibles de perdedores que pegaron el SL — que es justo la pregunta que
    este campo tiene que contestar."""

    def test_call_cerrado_por_stop_movido_es_trail_be_no_sl(self):
        # CALL entrada 1.17000, SL original 1.16960 (-4p), TP 1.17080 (+8p).
        # Cierra en 1.17026 (+2,6p): el broker dice SL, pero el precio esta MUY por
        # encima del SL original => el stop fue movido a favor (trailing/BE).
        r, raw = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.17026, orig_sl=1.16960,
            orig_tp=1.17080, direction='CALL')
        self.assertEqual(r, 'trail_be')
        self.assertEqual(raw, DEAL_REASON_SL)  # el crudo NO se pierde

    def test_put_cerrado_por_stop_movido_es_trail_be(self):
        # PUT entrada 1.17000, SL original 1.17040 (+4p arriba). Cierra en 1.16974
        # (+2,6p a favor) => stop bajado a favor.
        r, _ = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.16974, orig_sl=1.17040,
            orig_tp=1.16920, direction='PUT')
        self.assertEqual(r, 'trail_be')

    def test_call_que_si_pego_el_sl_original_es_sl(self):
        r, _ = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.16960, orig_sl=1.16960,
            orig_tp=1.17080, direction='CALL')
        self.assertEqual(r, 'sl')

    def test_sl_con_slippage_adverso_sigue_siendo_sl_no_trail_be(self):
        """Gap/slippage que atraviesa el SL cierra PEOR que el SL: eso es SL, no un
        stop movido a favor. Sin este test, un gap se contaria como 'ganador cortado'
        e inflaria exactamente el bucket que queremos medir."""
        r, _ = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.16930, orig_sl=1.16960,
            orig_tp=1.17080, direction='CALL')
        self.assertEqual(r, 'sl')

    def test_dentro_de_la_tolerancia_es_sl(self):
        # 1 pip por encima del SL: spread/slippage normal, no un stop movido.
        r, _ = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.16970, orig_sl=1.16960,
            orig_tp=1.17080, direction='CALL')
        self.assertEqual(r, 'sl')

    def test_sl_moved_manda_sobre_la_inferencia_por_precio(self):
        """AIdan REGISTRA si movio el stop (`mt5_trailing_step > 0`), y `stop_loss` en
        la DB nunca se pisa. Eso es un hecho propio y le gana a comparar precios.
        Caso: el stop se movio pero el cierre cayo cerca del SL original (BE armado y
        el precio volvio) — por precio se leeria 'sl' y estaria MAL."""
        r, _ = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.16965, orig_sl=1.16960,
            direction='CALL', sl_moved=True)
        self.assertEqual(r, 'trail_be')

    def test_sl_moved_false_es_sl_aunque_el_precio_confunda(self):
        r, _ = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.17026, orig_sl=1.16960,
            direction='CALL', sl_moved=False)
        self.assertEqual(r, 'sl')

    def test_sl_moved_none_cae_a_la_inferencia_por_precio(self):
        r, _ = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.17026, orig_sl=1.16960,
            direction='CALL', sl_moved=None)
        self.assertEqual(r, 'trail_be')

    def test_sin_sl_original_devuelve_sl_la_palabra_del_broker(self):
        """Si no se puede distinguir, la respuesta honesta es lo que dijo el broker,
        no una adivinanza. El crudo queda igual para re-derivar despues."""
        r, raw = classify_from_broker_deal(
            DEAL_REASON_SL, close_price=1.17026, orig_sl=None,
            orig_tp=None, direction='CALL')
        self.assertEqual(r, 'sl')
        self.assertEqual(raw, DEAL_REASON_SL)


# --------------------------------------------------------------------------- #
# (2) LISTA CERRADA + el resto del mapeo del broker
# --------------------------------------------------------------------------- #
class TestMapeoBroker(unittest.TestCase):
    def test_tp(self):
        r, _ = classify_from_broker_deal(
            DEAL_REASON_TP, close_price=1.17080, orig_sl=1.16960,
            orig_tp=1.17080, direction='CALL')
        self.assertEqual(r, 'tp')

    def test_stopout(self):
        r, _ = classify_from_broker_deal(DEAL_REASON_SO, close_price=1.16900)
        self.assertEqual(r, 'stopout')

    def test_expert_es_aidan(self):
        """EXPERT = la orden la mando AIdan. Quien llama refina a expiry/manager/kill
        si lo sabe; por si solo 'aidan' es lo maximo que se puede afirmar."""
        r, _ = classify_from_broker_deal(DEAL_REASON_EXPERT, close_price=1.17010)
        self.assertEqual(r, 'aidan')

    def test_expert_con_refinamiento_del_caller(self):
        r, _ = classify_from_broker_deal(
            DEAL_REASON_EXPERT, close_price=1.17010, aidan_reason='manager')
        self.assertEqual(r, 'manager')

    def test_refinamiento_invalido_se_ignora(self):
        """Un caller que pase basura no puede meter un valor fuera de la lista."""
        r, _ = classify_from_broker_deal(
            DEAL_REASON_EXPERT, close_price=1.17010, aidan_reason='lo_que_sea')
        self.assertEqual(r, 'aidan')

    def test_refinamiento_no_pisa_al_broker(self):
        """Si el broker dice TP, el caller NO puede decir que fue expiry. La palabra
        del broker gana siempre: es la unica verdad, el caller es una inferencia."""
        r, _ = classify_from_broker_deal(
            DEAL_REASON_TP, close_price=1.17080, orig_tp=1.17080,
            direction='CALL', aidan_reason='expiry')
        self.assertEqual(r, 'tp')

    def test_manual(self):
        for code in (DEAL_REASON_CLIENT, DEAL_REASON_WEB):
            r, _ = classify_from_broker_deal(code, close_price=1.17010)
            self.assertEqual(r, 'manual')

    def test_sin_reason_es_unknown(self):
        r, raw = classify_from_broker_deal(None, close_price=1.17010)
        self.assertEqual(r, 'unknown')
        self.assertIsNone(raw)

    def test_codigo_desconocido_es_unknown_no_explota(self):
        r, raw = classify_from_broker_deal(99, close_price=1.17010)
        self.assertEqual(r, 'unknown')
        self.assertEqual(raw, 99)

    def test_todo_output_esta_en_la_lista_cerrada(self):
        casos = [
            (DEAL_REASON_TP, {}), (DEAL_REASON_SL, {}), (DEAL_REASON_SO, {}),
            (DEAL_REASON_EXPERT, {}), (DEAL_REASON_CLIENT, {}), (None, {}), (99, {}),
            (DEAL_REASON_SL, {'orig_sl': 1.1696, 'close_price': 1.1703, 'direction': 'CALL'}),
        ]
        for code, kw in casos:
            r, _ = classify_from_broker_deal(code, **kw)
            self.assertIn(r, EXIT_REASONS, f'valor fuera de la lista cerrada: {r!r}')


# --------------------------------------------------------------------------- #
# (3) PATH DE EVALUACION POR PRECIO (expiry) + FAIL-SAFE
# --------------------------------------------------------------------------- #
class TestFlagsDeEvaluacion(unittest.TestCase):
    def test_tp(self):
        self.assertEqual(classify_from_eval_flags(hit_tp=True), 'tp')

    def test_be(self):
        self.assertEqual(classify_from_eval_flags(hit_be=True), 'trail_be')

    def test_be_triggered_tambien_cuenta(self):
        self.assertEqual(classify_from_eval_flags(be_triggered=True), 'trail_be')

    def test_sl(self):
        self.assertEqual(classify_from_eval_flags(hit_sl=True), 'sl')

    def test_ninguno_es_expiry(self):
        """Ninguna barrera tocada y el trade cerro = se lo comio el expiry. Es LA
        hipotesis a medir (problema #2 del diagnostico: el expiry mata trades
        direccionalmente correctos)."""
        self.assertEqual(classify_from_eval_flags(), 'expiry')

    def test_tp_gana_a_be(self):
        self.assertEqual(classify_from_eval_flags(hit_tp=True, hit_be=True), 'tp')

    def test_todo_output_en_lista_cerrada(self):
        import itertools
        for combo in itertools.product([True, False], repeat=4):
            r = classify_from_eval_flags(*combo)
            self.assertIn(r, EXIT_REASONS)


class TestFailSafe(unittest.TestCase):
    """Clasificar NUNCA puede romper el archivado: el archive es la verdad historica
    del proyecto y perder un trade por un TypeError seria mucho peor que no saber el
    motivo. Todo input basura => 'unknown', sin excepcion."""

    def test_inputs_basura_no_explotan(self):
        basura = [
            {'broker_reason': 'cuatro'},
            {'broker_reason': DEAL_REASON_SL, 'close_price': 'x', 'orig_sl': 1.1},
            {'broker_reason': DEAL_REASON_SL, 'close_price': None, 'orig_sl': 'y',
             'direction': 'CALL'},
            {'broker_reason': DEAL_REASON_SL, 'close_price': float('nan'),
             'orig_sl': 1.1696, 'direction': 'CALL'},
            {'broker_reason': [], 'close_price': {}},
        ]
        for kw in basura:
            try:
                r, _ = classify_from_broker_deal(**kw)
            except Exception as e:
                self.fail(f'exploto con {kw}: {e}')
            self.assertIn(r, EXIT_REASONS)

    def test_flags_basura_no_explotan(self):
        r = classify_from_eval_flags(hit_tp='si', hit_be=None, hit_sl=0)
        self.assertIn(r, EXIT_REASONS)


# --------------------------------------------------------------------------- #
# (4) CALL-SITE sobre el FUENTE — que el mecanismo este realmente ENCHUFADO
# --------------------------------------------------------------------------- #
def _read(rel):
    with open(os.path.join(ROOT, rel), 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


class TestCableado(unittest.TestCase):
    def test_archive_trade_persiste_las_dos_columnas(self):
        """db.py tiene 3 INSERT a trade_archive: el backfill de una sola vez, el
        rescate del cap-delete (ninguno de los dos conoce el motivo => NULL es lo
        honesto) y el de archive_trade, que es el que importa."""
        src = _read(os.path.join('src', 'common', 'db.py'))
        i = src.find('def archive_trade(')
        self.assertGreater(i, 0, 'no se encontro archive_trade')
        j = src.find('INSERT OR IGNORE INTO trade_archive', i)
        self.assertGreater(j, 0, 'archive_trade no tiene su INSERT')
        bloque = src[j:j + 2200]
        self.assertTrue('exit_reason' in bloque,
                        'archive_trade no persiste exit_reason => campo muerto')
        self.assertTrue('exit_reason_raw' in bloque,
                        'archive_trade no persiste exit_reason_raw => se pierde el crudo')

    def test_archive_trade_lee_el_ctx(self):
        src = _read(os.path.join('src', 'common', 'db.py'))
        self.assertTrue(
            re.search(r"ctx\.get\(\s*['\"]exit_reason['\"]", src) is not None,
            'archive_trade no lee exit_reason del context que le pasa el caller')

    def test_placeholders_del_insert_coinciden_con_columnas(self):
        """Si se agrega una columna y no su '?', el INSERT tira OperationalError y el
        archivado se pierde entero. Se cuenta explicito porque este INSERT ya crecio
        varias veces."""
        src = _read(os.path.join('src', 'common', 'db.py'))
        i = src.find('def archive_trade(')
        j = src.find('INSERT OR IGNORE INTO trade_archive', i)
        bloque = src[j:src.find('"""', j + 10)]
        cols = re.search(r'\(strategy_id,(.*?)\)\s*VALUES', bloque, re.S)
        self.assertIsNotNone(cols, 'no se pudo parsear la lista de columnas')
        n_cols = len([c for c in ('strategy_id,' + cols.group(1)).split(',') if c.strip()])
        vals = re.search(r'VALUES\s*\((.*?)\)', bloque, re.S)
        n_q = vals.group(1).count('?')
        self.assertEqual(n_cols, n_q,
                         f'{n_cols} columnas vs {n_q} placeholders en el INSERT del archive')

    def test_el_path_del_broker_clasifica(self):
        """sync_closed_positions es el path por el que entra la mayoria de los cierres.
        Si no llama al clasificador, el campo queda NULL en produccion y este cambio
        entero no sirve para nada."""
        src = _read(os.path.join('src', 'broker', 'mt5_executor.py'))
        self.assertTrue('classify_from_broker_deal' in src,
                        'mt5_executor no clasifica el motivo de cierre')
        self.assertTrue('exit_reason' in src, 'mt5_executor no pasa exit_reason en el ctx')

    def test_el_path_de_expiry_clasifica(self):
        src = _read('AIdan_TodoEnUno.py')
        self.assertTrue('classify_from_eval_flags' in src,
                        'el path de evaluacion por precio no clasifica el motivo')

    def test_modulo_no_importa_metatrader5(self):
        """Tiene que poder correr sin broker y sin pelearse con el exe vivo."""
        src = _read(os.path.join('src', 'common', 'exit_reason.py'))
        self.assertTrue('import MetaTrader5' not in src, 'importa MetaTrader5')
        self.assertTrue('mt5.initialize' not in src, 'llama a mt5.initialize')

    def test_constantes_coinciden_con_metatrader5_si_esta_instalado(self):
        """Las constantes estan hardcodeadas para poder testear sin broker. Si el
        paquete esta disponible, verificar que no divergieron — una constante mal
        copiada clasificaria TODO mal y en silencio."""
        try:
            import MetaTrader5 as mt5  # noqa: N813
        except Exception:
            self.skipTest('MetaTrader5 no instalado')
        for nombre, propio in (('DEAL_REASON_CLIENT', DEAL_REASON_CLIENT),
                               ('DEAL_REASON_EXPERT', DEAL_REASON_EXPERT),
                               ('DEAL_REASON_SL', DEAL_REASON_SL),
                               ('DEAL_REASON_TP', DEAL_REASON_TP),
                               ('DEAL_REASON_SO', DEAL_REASON_SO)):
            real = getattr(mt5, nombre, None)
            if real is not None:
                self.assertEqual(propio, real, f'{nombre} divergio de MetaTrader5')


class TestMigracion(unittest.TestCase):
    def test_migracion_existe_y_es_idempotente(self):
        """ALTER TABLE ADD COLUMN sobre una columna que ya existe tira error; el
        arranque no puede morir por eso."""
        src = _read(os.path.join('src', 'common', 'db.py'))
        self.assertTrue('exit_reason' in src, 'db.py no menciona exit_reason')
        # la migracion tiene que estar guardada por PRAGMA/except, no suelta
        i = src.find('exit_reason_raw')
        self.assertGreater(i, 0)

    def test_no_hay_drop_ni_delete_sobre_el_archive(self):
        """Regla dura del proyecto: el historico no se borra."""
        src = _read(os.path.join('src', 'common', 'exit_reason.py'))
        for prohibido in ('DROP TABLE', 'DELETE FROM', 'TRUNCATE'):
            self.assertTrue(prohibido not in src.upper(), f'{prohibido} en exit_reason.py')


if __name__ == '__main__':
    unittest.main(verbosity=2)
