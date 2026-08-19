"""Tests del toggle del track news (v3.57.0).

El toggle corta la EJECUCION de news sin borrar el track ni dejar de medirlo.
Estos tests fijan las dos propiedades que importan y que son faciles de romper
sin darse cuenta:

  1. **El default es ON.** Un rebuild sin tocar `.env` no debe cambiar el
     comportamiento. El user decidio el 7-ago "news NO se apaga, se arregla" y hay
     un veredicto pre-declarado para ~28 ago: apagarlo por accidente en un rebuild
     arruinaria esa lectura.
  2. **El gate corta ANTES de `add_auto_strategy` y DESPUES de guardar el alert**,
     para que la habilidad direccional del LLM se siga midiendo apagado.

Se leen del fuente (test de mutacion): el gate vive dentro de un loop de 4.400
lineas con GUI y threads, no es invocable de forma aislada sin montar todo.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = io.open('AIdan_TodoEnUno.py', encoding='utf-8').read()
GATE = "os.getenv('ENABLE_NEWS_TRACK', 'true')"


def test_el_gate_existe():
    assert GATE in SRC, "desaparecio el toggle ENABLE_NEWS_TRACK del track news"


def test_el_default_es_ON():
    """`'true'` como default: rebuild sin .env = news sigue operando."""
    assert "'ENABLE_NEWS_TRACK', 'true'" in SRC
    assert "'ENABLE_NEWS_TRACK', 'false'" not in SRC


def test_apaga_con_los_valores_falsy_habituales():
    """Se acepta 0/false/no/off (y mayusculas): el user va a escribir esto a mano
    en el .env, no debe importar el capricho de la palabra."""
    i = SRC.index(GATE)
    linea = SRC[i:i + 300]
    for v in ("'0'", "'false'", "'no'", "'off'"):
        assert v in linea, f"falta el valor falsy {v}"
    assert '.strip().lower()' in linea, "sin normalizar, 'False' o ' false' no apagarian"


def test_el_gate_corta_antes_de_crear_el_trade():
    """El `elif` del toggle tiene que estar ANTES del `else:` que llama a
    `add_auto_strategy`, si no el trade se crea igual."""
    i_gate = SRC.index(GATE)
    i_add = SRC.index('sid = add_auto_strategy(', i_gate)
    entre = SRC[i_gate:i_add]
    assert entre.count('else:') == 1, (
        "el gate ya no es la rama inmediatamente anterior a la creacion del trade")


def test_documentado_en_env_example():
    env = io.open('.env.example', encoding='utf-8').read()
    assert 'ENABLE_NEWS_TRACK' in env, "perilla no documentada en .env.example"
    assert 'RETRO_MODE' in env
