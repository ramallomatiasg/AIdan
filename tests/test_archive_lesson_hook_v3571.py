"""La leccion direccional no debe depender del LLM (v3.57.1).

POR QUE ESTE ARCHIVO EXISTE
---------------------------
En v3.57.0 la leccion se derivaba SOLO dentro de `analyze_closed_trade`, que
devuelve None ante cualquier problema de Ollama (timeout, HTTP != 200, GPU
ocupada via `should_pause_llm`, JSON invalido). Un lazo de aprendizaje
100 % determinista quedaba de rehen de un modelo de 7B: con Ollama caido
`directional_lessons` deja de crecer y la retrospectiva pre-trade se queda ciega
**sin que nada falle**. Es la clase de bug que ya mato a M15 dos semanas, a SMC,
al reversal y al loop de aprendizaje durante meses.

v3.57.1 la deriva tambien en `archive_trade`, que corre para todo trade cerrado
y no depende de ningun servicio externo.

Los tests son de CALL-SITE ademas de logica: el bug no era que la funcion
estuviera mal, era DONDE se llamaba. Un test que solo ejercite la funcion pasa en
verde con el mecanismo muerto.
"""

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer.post_trade_analyzer import derive_directional_lesson


def _db_src():
    return io.open('src/common/db.py', encoding='utf-8').read()


# ─────────────────────── cableado en el path de archivo ───────────────────────

def test_archive_trade_deriva_la_leccion():
    src = _db_src()
    i = src.index('def archive_trade(')
    j = src.index('\ndef ', i + 10)          # fin de la funcion
    cuerpo = src[i:j]
    assert 'derive_directional_lesson' in cuerpo, (
        "archive_trade dejo de derivar la leccion => el lazo vuelve a depender de "
        "que Ollama este arriba")
    assert 'add_directional_lesson' in cuerpo


def _codigo_de(nombre):
    """Cuerpo de una funcion de db.py SIN comentarios.

    Mirar el texto crudo daria falsos positivos: el propio comentario del hook
    explica de que se independizo y nombra `analyze_closed_trade`."""
    src = _db_src()
    i = src.index(f'def {nombre}(')
    j = src.index('\ndef ', i + 10)
    return '\n'.join(l.split('#')[0] for l in src[i:j].split('\n'))


def test_el_hook_no_depende_de_ollama():
    """El path de archivo no debe llamar nada que necesite red."""
    cuerpo = _codigo_de('archive_trade')
    for prohibido in ('analyze_closed_trade', 'requests.', 'OLLAMA_URL', 'GEMMA_MODEL'):
        assert prohibido not in cuerpo, (
            f"archive_trade referencia {prohibido!r}: el hook volveria a colgar del LLM")


def test_el_hook_usa_el_MFE_real_cuando_existe():
    """Sin excursion real, `max(0,pips)` confunde un problema de GESTION con uno de
    DIRECCION (un trade que llego al 60% del TP y se dio vuelta entraria como
    leccion). El hook tiene que pedir la excursion antes de caer a la cota."""
    src = _db_src()
    i = src.index('def archive_trade(')
    j = src.index('\ndef ', i + 10)
    cuerpo = src[i:j]
    assert 'get_trade_excursion' in cuerpo
    assert 'max(0.0, _pips)' in cuerpo, "falta el fallback declarado"


def test_el_hook_falla_ruidoso():
    """WARNING con stack, nunca `pass` ni `debug`: si esto se rompe en silencio, el
    unico lazo de aprendizaje vivo deja de alimentarse y nadie se entera."""
    src = _db_src()
    i = src.index('leccion direccional #{strategy_id} no derivada en archive')
    ventana = src[i - 200:i + 200]
    assert 'warning' in ventana and 'exc_info=True' in ventana


def test_la_idempotencia_esta_declarada_en_el_schema():
    """Los dos paths (archivo y LLM) pueden escribir la misma leccion. Lo unico que
    hace segura esa redundancia es el UNIQUE index + INSERT OR IGNORE."""
    src = _db_src()
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS idx_dirlesson_sid' in src
    i = src.index('def add_directional_lesson(')
    j = src.index('\ndef ', i + 10)
    assert 'INSERT OR IGNORE' in src[i:j]


# ─────────── logica: los casos que el E2E no pudo cubrir (rate limit) ───────────

@pytest.mark.parametrize('pnl,pct_tp,hit_sl,espera', [
    (-3.10,   0.0, True,  True),    # perdio, nunca a favor, pego SL => leccion
    (+4.20,   0.0, True,  False),   # GANADOR: nunca genera leccion
    (-3.10,  60.0, True,  False),   # se puso a favor => fue GESTION, no direccion
    (-3.10,   0.0, False, False),   # no pego el SL => ruido/expiry, no direccion
    (-0.01,  19.9, True,  True),    # borde: justo debajo del umbral de 20%
    (-0.01,  20.0, True,  False),   # borde: justo en el umbral => NO
])
def test_matriz_de_decision(pnl, pct_tp, hit_sl, espera):
    got = derive_directional_lesson('CALL', pnl, pct_tp, 0.5, -6.2, 6.0, hit_sl)
    assert (got is not None) is espera, f"pnl={pnl} pct_tp={pct_tp} hit_sl={hit_sl}"


def test_el_ganador_nunca_genera_leccion_en_ninguna_direccion():
    for d in ('CALL', 'PUT'):
        assert derive_directional_lesson(d, +4.20, 0.0, 0.0, -6.2, 6.0, True) is None
