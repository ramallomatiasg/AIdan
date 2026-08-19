"""El post-trade ve el razonamiento de la entrada (v3.57.2).

QUE CIERRA
----------
Hasta v3.57.1 el lazo iba en un solo sentido:

    post-trade -> directional_lessons -> retrospectiva pre-trade

El post-trade nunca veia lo que la entrada habia mirado, asi que no podia decir
*"el PUT era correcto, pero por Y razon que no estabas considerando"* — que es
textual lo que se pidio. Ahora el prompt recibe los NUMEROS de la comparacion
historica y el modelo devuelve `missed_factor` contra una lista cerrada.

POR QUE NUMEROS Y NO EL VEREDICTO MASTICADO: si al modelo se le pasara "la
opuesta pagaba", lo repetiria como loro. Es el error de la hoja de respuestas que
ya documento v3.53.7 (entry_quality='good' en el 93 % de los PERDEDORES).
"""

import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer.post_trade_analyzer import POST_TRADE_PROMPT


def _pta_src():
    return io.open('src/analyzer/post_trade_analyzer.py', encoding='utf-8').read()


# ───────────────────────────── el prompt ─────────────────────────────

def test_el_prompt_tiene_el_bloque_de_la_entrada():
    assert '{retro_block}' in POST_TRADE_PROMPT
    assert 'LO QUE AIdan MIRO AL ENTRAR' in POST_TRADE_PROMPT


def test_el_prompt_pide_missed_factor_con_lista_cerrada():
    assert 'missed_factor' in POST_TRADE_PROMPT
    for v in ('tendencia', 'htf', 'rsi', 'volatilidad', 'sesion', 'nivel',
              'noticia', 'ninguno'):
        assert v in POST_TRADE_PROMPT, f"falta la opcion {v!r} en el prompt"


def test_ninguno_esta_explicitamente_permitido():
    """Sin esto el modelo inventa un factor siempre, porque siente que debe
    contestar algo. No todo perdedor tenia una senal ignorada."""
    assert '"ninguno" es una respuesta VALIDA' in POST_TRADE_PROMPT


def test_el_prompt_no_le_da_el_veredicto_masticado():
    """Al modelo se le pasan numeros, no el juicio: si leyera 'contrarian' o
    'la opuesta pagaba' lo repetiria en la leccion sin analizarlo."""
    i = POST_TRADE_PROMPT.index('LO QUE AIdan MIRO AL ENTRAR')
    bloque = POST_TRADE_PROMPT[i:i + 200]
    for filtrado in ('contrarian', 'aligned', 'la opuesta pagaba'):
        assert filtrado not in bloque


def test_todos_los_placeholders_se_llenan():
    """Un placeholder sin su clave en `ctx` tira KeyError y mata el post-trade
    entero — en silencio, porque el except de arriba devuelve None."""
    from src.analyzer.post_trade_analyzer import derive_quality
    src = _pta_src()
    ph = set(re.findall(r'\{(\w+)\}', POST_TRADE_PROMPT))
    i = src.index('def analyze_closed_trade(')
    cuerpo = src[i:src.index("prompt = POST_TRADE_PROMPT.format(**ctx)", i)]
    # Las categoricas no aparecen como literal: entran via `ctx.update(derived)`.
    derivadas = set(derive_quality(0, 0, 0, 50, False))
    faltan = [p for p in ph if f"'{p}'" not in cuerpo and p not in derivadas]
    assert not faltan, f"placeholders sin poblar antes del format(): {faltan}"


def test_retro_block_se_asigna_antes_del_format():
    src = _pta_src()
    i = src.index('def analyze_closed_trade(')
    assert (src.index("ctx['retro_block']", i)
            < src.index("prompt = POST_TRADE_PROMPT.format(**ctx)", i)), \
        "retro_block se asigna DESPUES del format => KeyError garantizado"


def test_retro_block_tiene_default_si_no_hubo_retrospectiva():
    src = _pta_src()
    i = src.index("ctx['retro_block'] =")
    assert 'no se evaluo' in src[i:i + 200]


# ────────────────────── validacion de missed_factor ──────────────────────

def test_missed_factor_valida_contra_lista_cerrada():
    src = _pta_src()
    assert 'VALID_MISSED' in src
    i = src.index('VALID_MISSED = (')
    for v in ('tendencia', 'htf', 'rsi', 'volatilidad', 'sesion', 'nivel',
              'noticia', 'ninguno'):
        assert f"'{v}'" in src[i:i + 300]


def test_valor_invalido_cae_a_vacio_no_a_ninguno():
    """Hay que poder distinguir 'el modelo dijo que no faltaba nada' ('ninguno')
    de 'el modelo contesto cualquier cosa' (''). Si los dos casos colapsan en
    'ninguno', la tasa de adherencia del modelo es inauditable — que es como el
    A/B de v3.53.7 descubrio que el 7B copiaba la hoja de respuestas."""
    src = _pta_src()
    i = src.index("'missed_factor': (")
    frag = src[i:i + 400]
    assert "else ''" in frag, "un valor fuera de la lista debe caer a '', no a 'ninguno'"


def test_se_persiste_como_COLUMNA_no_solo_en_el_json():
    """Un campo que hay que sacar con json_extract no se agrega en la practica.
    Ese es el destino de los 10.736 insights del LearningEngine."""
    db = io.open('src/common/db.py', encoding='utf-8').read()
    assert 'ADD COLUMN missed_factor' in db, "falta la migracion"
    i = db.index('INSERT INTO post_trade_analysis')
    j = db.index('"""', i)
    assert 'missed_factor' in db[i:j], "la columna no se escribe en el INSERT"


def test_el_insert_tiene_tantos_placeholders_como_columnas():
    """Agregar una columna y olvidar el `?` es el bug clasico de este cambio."""
    db = io.open('src/common/db.py', encoding='utf-8').read()
    i = db.index('INSERT INTO post_trade_analysis')
    sql = db[i:db.index('"""', i)]
    cols = sql[sql.index('(') + 1:sql.index(')')].split(',')
    marks = sql[sql.rindex('VALUES ('):].count('?')
    assert len(cols) == marks, f"{len(cols)} columnas vs {marks} placeholders"


# ─────────────────────────── lectura del lazo ───────────────────────────

def test_existe_el_getter_del_razonamiento_de_entrada():
    import src.common.db as db
    assert callable(getattr(db, 'get_pre_trade_retrospective', None))


def test_el_getter_no_explota_si_falta_la_tabla():
    """Una DB vieja que no paso por init_db no debe tumbar el post-trade."""
    db = io.open('src/common/db.py', encoding='utf-8').read()
    i = db.index('def get_pre_trade_retrospective(')
    cuerpo = db[i:db.index('\ndef ', i + 10)]
    assert 'OperationalError' in cuerpo and 'return None' in cuerpo
