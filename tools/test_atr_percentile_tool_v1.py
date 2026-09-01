"""
test_atr_percentile_tool_v1.py - tests de `measure_atr_percentile_floor.py`.

Lo que protegen, en orden de importancia:

  1. QUE EL ATR SEA EL DE PRODUCCION. Si el tool calcula el ATR distinto que
     `technical.py`, la comparacion "piso fijo vs percentil" no mide el gate real y el
     numero sale plausible pero falso - el modo de falla favorito de este proyecto.
     Incluye un TEST DE MUTACION: lee el bloque de ATR de `technical.py` y falla si
     produccion cambia la formula, para que el tool no quede stale en silencio.

  2. QUE EL PERCENTIL SEA CAUSAL. Un percentil que mira velas futuras da un resultado
     buenisimo y mentiroso. Se verifica que el valor en la vela i NO cambia cuando se
     modifican las velas posteriores.

  3. QUE EL SCRIPT NO ESCRIBA. Es read-only por contrato; se chequea sobre el fuente
     que todas las conexiones sean `mode=ro` y que no haya INSERT/UPDATE/DELETE.

No toca la DB de produccion ni MT5.
"""
import contextlib
import io
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.measure_atr_percentile_floor import (  # noqa: E402
    ATR_PERIOD, atr_at, build_series, pct_rank, wilson,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL_SRC = os.path.join(ROOT, 'tools', 'measure_atr_percentile_floor.py')
TECH_SRC = os.path.join(ROOT, 'src', 'analyzer', 'technical.py')

fails = []


def check(name, cond, detail=''):
    if cond:
        print(f"  [ok]  {name}")
    else:
        print(f"  [FAIL] {name} {detail}")
        fails.append(name)


def mk(seq):
    """seq de (open, high, low, close) -> candles del tool (velas M15 consecutivas)."""
    t0 = datetime(2026, 8, 3, 0, 0, 0)
    return [{'ts': t0 + timedelta(minutes=15 * n), 'open': o, 'high': h, 'low': l, 'close': c}
            for n, (o, h, l, c) in enumerate(seq)]


# ======================================================================================
print("1) el ATR del tool == el ATR de produccion")
# ======================================================================================

def prod_atr(candles, i):
    """Re-implementacion INDEPENDIENTE de technical.py:218-227 sobre las velas [0..i].
    Escrita a mano desde el fuente, no importada: si el tool y esto coinciden, el tool
    replica la formula; si importaramos la misma funcion el test seria vacio."""
    sub = candles[:i + 1]
    atr_period = min(14, len(sub) - 1)
    trs = []
    for k in range(-atr_period, 0):
        h, l = sub[k]['high'], sub[k]['low']
        prev_c = sub[k - 1]['close']
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)) * 10000)
    return round(sum(trs) / len(trs), 1) if trs else 0


# velas con gaps a proposito: el TR de produccion usa el cierre previo justamente por eso
seq = []
px = 1.1600
for n in range(40):
    gap = 0.0008 if n % 7 == 0 else 0.0    # gap cada 7 velas
    o = px + gap
    h = o + 0.0004 + 0.00002 * n
    l = o - 0.0003
    c = o + 0.0001
    seq.append((o, h, l, c))
    px = c
candles = mk(seq)

mismatches = [(i, atr_at(candles, i), prod_atr(candles, i))
              for i in range(20, len(candles))
              if atr_at(candles, i) != prod_atr(candles, i)]
check("ATR identico a produccion en 20 velas con gaps", not mismatches,
      f"-> primeras diferencias: {mismatches[:3]}")

check("usa periodo 14 como produccion", ATR_PERIOD == 14, f"(es {ATR_PERIOD})")
check("con historia corta usa min(14, i) y no explota",
      atr_at(candles, 3) is not None and atr_at(candles, 0) is None)

# TEST DE MUTACION: si produccion cambia su formula, este test avisa.
tech = open(TECH_SRC, encoding='utf-8', errors='ignore').read()
block = re.search(r"atr_period = min\((\d+), len\(candles\) - 1\)(.{0,700}?)"
                  r"avg_range = sum\(true_ranges\) / len\(true_ranges\)",
                  tech, re.S)
check("el bloque de ATR de technical.py sigue teniendo la forma esperada", block is not None,
      "-> produccion cambio su ATR: revisar atr_at() del tool ANTES de correrlo")
if block:
    check("produccion sigue usando periodo 14", block.group(1) == '14',
          f"-> produccion usa {block.group(1)}, el tool usa {ATR_PERIOD}")
    body = block.group(2)
    check("produccion sigue usando True Range con el cierre previo",
          'abs(h - prev_c)' in body and 'abs(l - prev_c)' in body and 'max(h - l' in body)
    check("produccion sigue convirtiendo a pips con *10000", '* 10000' in body)
    check("produccion sigue promediando (no EMA/Wilder)", 'sum(true_ranges)' in tech)

# ======================================================================================
print()
print("2) el percentil es CAUSAL (no mira el futuro)")
# ======================================================================================
base = build_series(candles, 20)
pct_at_25 = {i: p for i, _ts, _a, p in
             [(x[0], None, x[2], x[3]) for x in base] if i == 25}

# mutar SOLO las velas posteriores a la 25 y verificar que el percentil de la 25 no cambia
mutated = mk(seq)
for j in range(26, len(mutated)):
    mutated[j]['high'] += 0.0050
    mutated[j]['low'] -= 0.0050
after = build_series(mutated, 20)
pct_after_25 = {i: p for i, _ts, _a, p in
                [(x[0], None, x[2], x[3]) for x in after] if i == 25}
check("percentil de la vela 25 invariante al mutar las velas 26+",
      pct_at_25 == pct_after_25, f"-> antes {pct_at_25} despues {pct_after_25}")

changed = [i for (i, _t, _a, p), (i2, _t2, _a2, p2) in zip(base, after)
           if i == i2 and i <= 25 and p != p2]
check("ninguna vela <= 25 cambio su percentil", not changed, f"-> cambiaron {changed[:5]}")

# el percentil necesita ventana minima: las primeras velas no deben inventar un numero
early_defined = [i for i, _t, _a, p in build_series(candles, 100) if p is not None and i < 25]
check("con lookback 100 no se emite percentil sobre una ventana insuficiente",
      not early_defined, f"-> emitio en {early_defined[:5]}")


# velas largas para las secciones 6 y 7 (~2,5 meses de M15 => C1 evaluable)
import random as _rnd  # noqa: E402
_rnd.seed(20260901)
_seq_long, _px = [], 1.1600
for _n in range(7000):
    # regimen alternado a proposito: tramos "muertos" y tramos "vivos", que es lo que
    # C1 tiene que poder distinguir
    _amp = 0.00012 if (_n // 1400) % 2 == 0 else 0.00055
    _o = _px
    _h = _o + _amp * (0.5 + _rnd.random())
    _l = _o - _amp * (0.5 + _rnd.random())
    _c = _l + (_h - _l) * _rnd.random()
    _seq_long.append((_o, _h, _l, _c))
    _px = _c
candles_long = mk(_seq_long)

# ======================================================================================
print()
print("3) pct_rank: empates y bordes")
# ======================================================================================
check("valor por debajo de todo -> 0", pct_rank(1.0, [2.0, 3.0, 4.0]) == 0.0)
check("valor por encima de todo -> 100", pct_rank(9.0, [2.0, 3.0, 4.0]) == 100.0)
check("empates cuentan medio (3.9 en [3.9]*4) -> 50",
      pct_rank(3.9, [3.9, 3.9, 3.9, 3.9]) == 50.0)
check("ventana vacia -> None", pct_rank(3.0, []) is None)
check("monotono", pct_rank(2.5, [1, 2, 3, 4]) < pct_rank(3.5, [1, 2, 3, 4]))

# ======================================================================================
print()
print("4) el script es READ-ONLY por contrato")
# ======================================================================================
src = open(TOOL_SRC, encoding='utf-8', errors='ignore').read()
conns = re.findall(r"sqlite3\.connect\(([^)]*)\)", src)
check("hay al menos una conexion a la DB", len(conns) >= 1)
check("TODAS las conexiones usan mode=ro",
      all('mode=ro' in c and 'uri=True' in c for c in conns),
      f"-> {[c for c in conns if 'mode=ro' not in c]}")
code = re.sub(r'""".*?"""', '', src, flags=re.S)   # sacar docstrings
code = re.sub(r'#.*', '', code)                    # sacar comentarios
writes = [w for w in ('INSERT ', 'UPDATE ', 'DELETE ', 'ALTER ', 'DROP ', 'CREATE ')
          if w in code.upper()]
check("no hay sentencias de escritura en el codigo", not writes, f"-> {writes}")
check("no importa MetaTrader5 a nivel de modulo (el modo offline no debe pedirlo)",
      not re.search(r"^import MetaTrader5", src, re.M))

# ======================================================================================
print()
print("5) wilson: mismo metodo que el resto del proyecto")
# ======================================================================================
check("n=0 -> (0,0)", wilson(0, 0) == (0.0, 0.0))
lo, hi = wilson(9, 33)                     # el bucket >8p real
check("CI de 9/33 contiene la proporcion", lo < 100 * 9 / 33 < hi, f"-> [{lo}-{hi}]")
check("mas n estrecha el CI",
      (wilson(50, 200)[1] - wilson(50, 200)[0]) < (wilson(5, 20)[1] - wilson(5, 20)[0]))

# ======================================================================================
print()
print("6) la GRILLA compara el mismo periodo (fix del review)")
# ======================================================================================
from tools.measure_atr_percentile_floor import (  # noqa: E402
    GRID_LOOKBACK, common_start, min_window,
)

check("lookback grande arranca mas tarde que chico",
      min_window(200) > min_window(50))
check("common_start cubre a la celda mas exigente de la grilla",
      common_start(GRID_LOOKBACK) > min_window(max(GRID_LOOKBACK)))
# la propiedad que importa: en common_start TODAS las celdas ya emiten percentil
starts = {lb: next((i for i, _t, _a, p in build_series(candles_long, lb) if p is not None), None)
          for lb in GRID_LOOKBACK}
cs = common_start(GRID_LOOKBACK)
check("en common_start todas las celdas ya tienen percentil",
      all(v is not None and v <= cs for v in starts.values()), f"-> arranques {starts}, cs={cs}")


# ======================================================================================
print()
print("7) SMOKE de la rama MT5 (velas sinteticas, sin MT5)")
# ======================================================================================
# Esta rama es la que el user va a correr el sabado con AIdan cerrado. Si revienta, se
# pierde la ventana de mercado cerrado => se ejercita entera aca con velas fabricadas.
from tools.measure_atr_percentile_floor import (  # noqa: E402
    report_frequency, report_separation,
)

buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        c1, c3, series = report_frequency(candles_long)
        c2 = report_separation(series)
    crashed = None
except Exception as e:      # noqa: BLE001 - el punto del smoke es cazar CUALQUIER throw
    crashed = f"{type(e).__name__}: {e}"
    c1 = c3 = c2 = series = None

check("report_frequency + report_separation corren sin excepcion", crashed is None,
      f"-> {crashed}")
out = buf.getvalue()
if crashed is None:
    check("C1 se evalua (2+ meses de velas sinteticas)", c1 in (True, False),
          f"-> devolvio {c1}")
    check("C3 se evalua", c3 in (True, False), f"-> devolvio {c3}")
    check("imprime la tabla por mes", "dispersion mes-a-mes" in out)
    check("imprime la grilla completa", "grilla completa" in out)
    check("imprime el solapamiento de C3", "solo el percentil" in out)
    check("la serie tiene percentiles definidos",
          sum(1 for _i, _t, _a, p in series if p is not None) > 100)
    # C2 corre contra la DB REAL (read-only). Con velas sinteticas el ATR no va a
    # coincidir con avg_range_pips => lo esperable es que el control fail-loud ABORTE.
    # Eso es exactamente lo que se quiere verificar: que aborta en vez de reportar.
    check("C2 no devuelve un veredicto positivo sobre velas falsas", c2 is not True,
          f"-> devolvio {c2}")
    check("si hubo cruces, el fail-loud se activo o no hubo muestra",
          ("ABORTADO" in out) or ("0 cruces" in out) or ("mapeo de timestamps OK" in out))

print()
if fails:
    print(f"RESULTADO: {len(fails)} FALLA(S) -> {fails}")
else:
    print("RESULTADO: todo verde.")
sys.exit(1 if fails else 0)
