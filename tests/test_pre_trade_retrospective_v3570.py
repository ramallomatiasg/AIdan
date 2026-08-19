"""Tests de la retrospectiva PRE-decision y del loop direccional (v3.57.0).

NO tocan la DB de produccion ni MT5: `get_similar_trades` / `get_directional_lessons`
se monkeypatchean. La regla del proyecto (v3.53.6) es que un test jamas escriba en
la DB viva — ya paso una vez y sus filas coparon el panel.

Incluye un TEST DE MUTACION: extrae del codigo la condicion real del gate de
`derive_directional_lesson` y falla si alguien relaja el criterio de las 3
condiciones sin actualizar los tests.
"""

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import pre_trade_retrospective as ptr
from src.analyzer.post_trade_analyzer import derive_directional_lesson


# ─────────────────────────── helpers ───────────────────────────

def _trade(direction, pnl):
    return {'direction': direction, 'mt5_pnl': pnl}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Cada test arranca con las perillas en default y sin lecciones."""
    for k in ('RETRO_MODE', 'RETRO_MIN_N', 'RETRO_MIN_PER_SIDE', 'RETRO_FULL_N',
              'RETRO_MAX_DELTA', 'RETRO_LOOKBACK'):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr('src.common.db.get_directional_lessons',
                        lambda **kw: [], raising=True)


def _patch_similar(monkeypatch, rows):
    monkeypatch.setattr('src.common.db.get_similar_trades',
                        lambda **kw: list(rows), raising=True)


SIG = {'direction': 'CALL', 'trigger_type': 'm15_structure',
       'setup_type': 'trend_continuation_bull', 'volatility': 'normal', 'confidence': 70}


# ─────────────────── familias direccion-neutras ───────────────────

def test_familia_agrupa_los_dos_lados_del_mismo_patron():
    assert ptr.setup_family('trend_continuation_bull') == 'trend_continuation'
    assert ptr.setup_family('trend_continuation_bear') == 'trend_continuation'
    assert ptr.setup_family('breakout_resistance') == ptr.setup_family('breakdown_support')


def test_setup_desconocido_es_su_propia_familia():
    assert ptr.setup_family('momentum_expansion') == 'momentum_expansion'
    assert ptr.setup_family('') == ''


def test_family_members_incluye_ambos_lados():
    m = ptr.family_members('trend_continuation')
    assert 'trend_continuation_bull' in m and 'trend_continuation_bear' in m


# ───────────────────────── veredictos ─────────────────────────

def test_muestra_chica_no_emite_delta(monkeypatch):
    _patch_similar(monkeypatch, [_trade('CALL', -1)] * 3)
    out = ptr.evaluate(SIG)
    assert out['verdict'] == 'insufficient'
    assert out['conf_delta'] == 0 and out['conf_delta_suggested'] == 0


def test_contrarian_cuando_la_opuesta_pagaba(monkeypatch):
    # este lado pierde, el otro gana, ambos con n >= min_per_side
    rows = [_trade('CALL', -2)] * 5 + [_trade('PUT', +3)] * 5
    _patch_similar(monkeypatch, rows)
    out = ptr.evaluate(SIG)
    assert out['verdict'] == 'contrarian'
    assert out['conf_delta_suggested'] < 0


def test_aligned_cuando_este_lado_pagaba(monkeypatch):
    _patch_similar(monkeypatch, [_trade('CALL', +2)] * 8)
    out = ptr.evaluate(SIG)
    assert out['verdict'] == 'aligned'
    assert out['conf_delta_suggested'] > 0


def test_shadow_es_el_default_y_no_aplica_delta(monkeypatch):
    _patch_similar(monkeypatch, [_trade('CALL', -2)] * 5 + [_trade('PUT', +3)] * 5)
    out = ptr.evaluate(SIG)
    assert out['mode'] == 'shadow'
    assert out['conf_delta_suggested'] < 0
    assert out['conf_delta'] == 0, "en shadow el delta NO se aplica"


def test_active_si_aplica_delta(monkeypatch):
    monkeypatch.setenv('RETRO_MODE', 'active')
    _patch_similar(monkeypatch, [_trade('CALL', -2)] * 5 + [_trade('PUT', +3)] * 5)
    out = ptr.evaluate(SIG)
    assert out['conf_delta'] == out['conf_delta_suggested'] < 0


def test_off_no_consulta_nada(monkeypatch):
    def _boom(**kw):
        raise AssertionError("con RETRO_MODE=off no se debe consultar la DB")
    monkeypatch.setenv('RETRO_MODE', 'off')
    monkeypatch.setattr('src.common.db.get_similar_trades', _boom, raising=True)
    assert ptr.evaluate(SIG)['verdict'] == 'off'


def test_delta_respeta_el_tope(monkeypatch):
    monkeypatch.setenv('RETRO_MODE', 'active')
    monkeypatch.setenv('RETRO_MAX_DELTA', '8')
    # muestra grande y lecciones a mansalva: aun asi no puede pasar el tope
    monkeypatch.setattr('src.common.db.get_directional_lessons',
                        lambda **kw: [{'id': i} for i in range(50)], raising=True)
    _patch_similar(monkeypatch, [_trade('CALL', -2)] * 30 + [_trade('PUT', +3)] * 30)
    out = ptr.evaluate(SIG)
    assert -8 <= out['conf_delta'] <= 8


def test_el_delta_escala_con_la_muestra(monkeypatch):
    monkeypatch.setenv('RETRO_MODE', 'active')
    _patch_similar(monkeypatch, [_trade('CALL', -2)] * 3 + [_trade('PUT', +3)] * 3)
    chico = ptr.evaluate(SIG)['conf_delta']
    _patch_similar(monkeypatch, [_trade('CALL', -2)] * 15 + [_trade('PUT', +3)] * 15)
    grande = ptr.evaluate(SIG)['conf_delta']
    assert abs(grande) > abs(chico), "n mayor tiene que mover mas que n chico"


def test_nunca_bloquea_ni_invierte(monkeypatch):
    """La restriccion #1 del user: no bajar frecuencia. El contrato de salida no
    tiene ninguna clave que pueda vetar la senal ni cambiar su direccion."""
    monkeypatch.setenv('RETRO_MODE', 'active')
    _patch_similar(monkeypatch, [_trade('CALL', -9)] * 20 + [_trade('PUT', +9)] * 20)
    out = ptr.evaluate(SIG)
    prohibidas = {'block', 'blocked', 'skip', 'veto', 'direction_override', 'flip'}
    assert not (prohibidas & set(out)), f"clave de bloqueo en la salida: {out.keys()}"


def test_error_no_propaga_y_queda_registrado(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("DB caida")
    monkeypatch.setattr('src.common.db.get_similar_trades', _boom, raising=True)
    out = ptr.evaluate(SIG)
    assert out['verdict'] == 'error' and out['conf_delta'] == 0
    assert 'DB caida' in out['reason']


def test_direccion_invalida_es_error(monkeypatch):
    _patch_similar(monkeypatch, [])
    out = ptr.evaluate(dict(SIG, direction='LATERAL'))
    assert out['verdict'] == 'error'


# ──────────────── leccion direccional (post-trade) ────────────────

def test_leccion_solo_con_las_tres_condiciones():
    # perdio + nunca a favor + pego SL  => leccion
    assert derive_directional_lesson('CALL', -3.0, 5.0, 0.4, -5.2, 5.5, True)
    # gano => no
    assert derive_directional_lesson('CALL', +3.0, 5.0, 0.4, -5.2, 5.5, True) is None
    # se puso a favor => no (fue gestion, no direccion)
    assert derive_directional_lesson('CALL', -3.0, 55.0, 9.0, -5.2, 5.5, True) is None
    # no pego el SL => no (ruido/expiry)
    assert derive_directional_lesson('CALL', -3.0, 5.0, 0.4, -1.1, 5.5, False) is None


def test_leccion_apunta_a_la_direccion_opuesta():
    assert derive_directional_lesson('CALL', -3.0, 0, 0, -5.2, 5.5, True)['better_direction'] == 'PUT'
    assert derive_directional_lesson('PUT', -3.0, 0, 0, -5.2, 5.5, True)['better_direction'] == 'CALL'


def test_leccion_valores_basura_no_explota():
    assert derive_directional_lesson('CALL', 'nan', None, None, None, 'x', True) is None
    assert derive_directional_lesson(None, -3.0, 0, 0, -5.2, 5.5, True) is None
    assert derive_directional_lesson('CALL', -3.0, 0, 0, -5.2, 0, True) is None


# ───────────────────── test de MUTACION ─────────────────────

def test_mutacion_el_gate_de_la_leccion_sigue_exigiendo_las_tres():
    """Extrae la condicion REAL del codigo y la evalua. Si alguien relaja el
    criterio (p.ej. saca `not hit_sl`), este test falla en vez de que la tabla se
    llene de lecciones sin sustento."""
    src = io.open('src/analyzer/post_trade_analyzer.py', encoding='utf-8').read()
    needle = "if _pnl >= 0 or _pct >= LESSON_POOR_PCT_TP or not hit_sl:"
    assert needle in src, (
        "cambio el gate de derive_directional_lesson. Las 3 condiciones "
        "(perdio / nunca a favor / pego SL) son el unico motivo por el que la "
        "afirmacion 'la opuesta era la correcta' no es una opinion. Si se relaja, "
        "actualizar estos tests A PROPOSITO.")
    assert 'LESSON_POOR_PCT_TP = 20.0' in src
