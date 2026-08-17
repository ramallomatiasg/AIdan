"""
test_m15_atr_floor_v3550.py — tests de la perilla M15_ATR_FLOOR (v3.55.0).

No toca la DB ni MT5. Verifica tres cosas, y la tercera es la que importa:

  1. Config.M15_ATR_FLOOR existe, es float y su DEFAULT es 5.0 (o sea: rebuildear
     sin tocar el .env NO cambia el comportamiento).
  2. La env var la pisa de verdad (se re-importa el modulo con el env seteado).
  3. TEST DE MUTACION sobre el gate del loop: se extrae la condicion real del
     archivo y se comprueba que con piso 8 deja pasar 8.1 y frena 7.9. Si alguien
     vuelve a hardcodear 5.0 en el loop, este test falla — que es el unico modo
     de que la perilla no sea decorativa.

Uso:  python tools/test_m15_atr_floor_v3550.py
"""
import importlib
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

FALLOS = []


def check(nombre, cond, detalle=""):
    if cond:
        print(f"  OK   {nombre}")
    else:
        print(f"  FALLA {nombre}  {detalle}")
        FALLOS.append(nombre)


def _reload_config(env_value):
    """Re-importa Config con M15_ATR_FLOOR seteado (o borrado) en el entorno."""
    prev = os.environ.get("M15_ATR_FLOOR")
    if env_value is None:
        os.environ.pop("M15_ATR_FLOOR", None)
    else:
        os.environ["M15_ATR_FLOOR"] = env_value
    try:
        import src.common.config as cfg
        importlib.reload(cfg)
        return cfg.Config.M15_ATR_FLOOR
    finally:
        if prev is None:
            os.environ.pop("M15_ATR_FLOOR", None)
        else:
            os.environ["M15_ATR_FLOOR"] = prev


def test_default_no_cambia_comportamiento():
    print("\n1) default = 5.0 (rebuild sin tocar .env no cambia nada)")
    # OJO: si el .env del repo ya define M15_ATR_FLOOR, load_dotenv lo mete en el
    # entorno y el default del codigo queda tapado. Se lee el default del SOURCE.
    src = open(os.path.join(ROOT, "src", "common", "config.py"), encoding="utf-8").read()
    m = re.search(r'M15_ATR_FLOOR\s*=\s*float\(os\.getenv\(\s*"M15_ATR_FLOOR"\s*,\s*"([\d.]+)"\s*\)\)', src)
    check("Config declara M15_ATR_FLOOR con default literal", m is not None)
    if m:
        check("el default es 5.0", m.group(1) == "5.0", f"es {m.group(1)}")

    val = _reload_config(None)
    check("el valor cargado es float", isinstance(val, float), f"tipo {type(val)}")


def test_env_pisa():
    print("\n2) la env var manda")
    check("M15_ATR_FLOOR=8 -> 8.0", _reload_config("8") == 8.0)
    check("M15_ATR_FLOOR=6.5 -> 6.5", _reload_config("6.5") == 6.5)


def test_mutacion_del_gate():
    print("\n3) MUTACION: el gate del loop usa la perilla, no un 5.0 hardcodeado")
    mono = open(os.path.join(ROOT, "AIdan_TodoEnUno.py"), encoding="utf-8").read()

    check("el loop ya no compara contra 5.0 literal",
          "if _m15_atr >= 5.0:" not in mono,
          "sigue el hardcode viejo")
    check("el loop lee Config.M15_ATR_FLOOR",
          "getattr(Config, 'M15_ATR_FLOOR', 5.0)" in mono)

    m = re.search(r"_m15_atr_floor = (getattr\(Config, 'M15_ATR_FLOOR', 5\.0\))", mono)
    check("se pudo extraer la asignacion del piso", m is not None)

    m2 = re.search(r"if (_m15_atr >= _m15_atr_floor):", mono)
    check("se pudo extraer la condicion del gate", m2 is not None)

    if m2:
        # Se evalua la condicion REAL del archivo, no una copia escrita a mano.
        cond = m2.group(1)
        for atr, piso, esperado in ((8.1, 8.0, True), (7.9, 8.0, False),
                                    (5.1, 5.0, True), (4.9, 5.0, False),
                                    (8.0, 8.0, True)):
            got = eval(cond, {}, {"_m15_atr": atr, "_m15_atr_floor": piso})
            check(f"ATR {atr} con piso {piso} -> {'pasa' if esperado else 'frena'}",
                  got is esperado, f"dio {got}")

    check("el skip se loguea (no es un silencio)",
          "M15_ATR_FLOOR" in mono and "sin scan (chop)" in mono)
    check("el log del skip esta throttleado",
          "_last_m15_floor_log" in mono)


def main():
    print("=" * 66)
    print("TESTS M15_ATR_FLOOR (v3.55.0)")
    print("=" * 66)
    test_default_no_cambia_comportamiento()
    test_env_pisa()
    test_mutacion_del_gate()
    print("\n" + "=" * 66)
    if FALLOS:
        print(f"FALLARON {len(FALLOS)}: {FALLOS}")
        return 1
    print("TODO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
