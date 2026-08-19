"""Tests del cableado de `adjust_setup_confidence` (v3.57.0).

El cambio existia desde v3.31.0 (implementado, con lista cerrada de change_types,
guard-rails y validacion por shadow) y **no se podia aplicar jamas**:
`get_confidence_adjustment_for_signal` no se llamaba desde ningun lado. Este
archivo cubre las dos mitades: que la funcion calcula bien, y que sigue estando
ENCHUFADA en el unico camino por el que nacen todos los trades.

No toca la DB de produccion: los filtros activos se monkeypatchean.
"""

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimizer import change_manager as cm


def _patch_filters(monkeypatch, filters):
    monkeypatch.setattr(cm, 'get_active_meta_filters', lambda: list(filters), raising=True)


SIG = {'direction': 'CALL', 'confidence': 70, 'trigger_type': 'm15_structure',
       'setup_type': 'trend_continuation_bull', 'session': 'ny', 'hour_utc': 16,
       'day_of_week': 2, 'htf_bias': 'bullish'}


def test_delta_se_aplica_al_setup_que_matchea(monkeypatch):
    _patch_filters(monkeypatch, [{'filter_type': 'adjust_setup_confidence',
                                  'params': {'setup_type': 'trend_continuation_bull',
                                             'delta': -7}}])
    assert cm.get_confidence_adjustment_for_signal(SIG) == -7


def test_delta_no_se_aplica_a_otro_setup(monkeypatch):
    _patch_filters(monkeypatch, [{'filter_type': 'adjust_setup_confidence',
                                  'params': {'setup_type': 'momentum_expansion',
                                             'delta': -7}}])
    assert cm.get_confidence_adjustment_for_signal(SIG) == 0


def test_varios_filtros_se_suman(monkeypatch):
    _patch_filters(monkeypatch, [
        {'filter_type': 'adjust_setup_confidence',
         'params': {'setup_type': 'trend_continuation_bull', 'delta': -5}},
        {'filter_type': 'adjust_setup_confidence',
         'params': {'setup_type': 'trend_continuation_bull', 'delta': +2}},
        {'filter_type': 'block_setup_type', 'params': {'setup_type': 'x'}},
    ])
    assert cm.get_confidence_adjustment_for_signal(SIG) == -3


def test_sin_filtros_activos_devuelve_cero(monkeypatch):
    _patch_filters(monkeypatch, [])
    assert cm.get_confidence_adjustment_for_signal(SIG) == 0


def test_setup_type_vacio_no_matchea_por_accidente(monkeypatch):
    """El bug original era de DATOS: con `setup_type` vacio el match nunca ocurria.
    Ahora que se puebla, hay que garantizar lo contrario: un setup vacio NO debe
    matchear un filtro con setup_type definido."""
    _patch_filters(monkeypatch, [{'filter_type': 'adjust_setup_confidence',
                                  'params': {'setup_type': 'trend_continuation_bull',
                                             'delta': -7}}])
    assert cm.get_confidence_adjustment_for_signal(dict(SIG, setup_type='')) == 0


def test_error_al_leer_filtros_no_propaga(monkeypatch):
    def _boom():
        raise RuntimeError("DB caida")
    monkeypatch.setattr(cm, 'get_active_meta_filters', _boom, raising=True)
    assert cm.get_confidence_adjustment_for_signal(SIG) == 0


# ───────────────────── tests de CABLEADO (mutacion) ─────────────────────
#
# El bug no era de logica sino de que nadie llamaba a la funcion. Un test que
# solo ejercite la funcion habria pasado en verde durante los 5 meses en que el
# mecanismo estuvo muerto. Estos miran el call-site.

def _db_src():
    return io.open('src/common/db.py', encoding='utf-8').read()


def test_add_auto_strategy_invoca_el_ajuste_de_confianza():
    src = _db_src()
    assert 'get_confidence_adjustment_for_signal' in src, (
        "se desconecto el ajuste del meta-optimizer: el change_type "
        "`adjust_setup_confidence` vuelve a ser inaplicable")


def test_add_auto_strategy_invoca_la_retrospectiva():
    src = _db_src()
    assert 'pre_trade_retrospective' in src and 'save_pre_trade_retrospective' in src


def test_el_ajuste_esta_clampeado_y_no_puede_anular_la_senal():
    """Un delta grande no debe poder llevar la confianza a 0 ni arriba de 99: el
    ajuste es un nudge, no una via lateral para vetar el trade."""
    src = _db_src()
    assert 'max(1, min(99, float(confidence) + _meta_delta + _retro_delta))' in src


@pytest.mark.parametrize('fn', ['get_similar_trades', 'get_directional_lessons',
                                'add_directional_lesson', 'save_pre_trade_retrospective'])
def test_funciones_del_loop_existen(fn):
    import src.common.db as db
    assert callable(getattr(db, fn, None)), f"falta {fn} en db.py"
