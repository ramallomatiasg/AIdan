"""v3.51.0 — verificacion de las 2 perillas de news (READ-ONLY, no toca la DB).

PERILLA 1: piso de expiry para news -> rompe el lazo TP<->expiry, el TP crece.
PERILLA 2: el soft-expiry que ve el Position Manager para news queda anclado en 15min
           -> CLOSE_PROTECT sigue cortando perdedores cuando corta hoy.

Corre standalone:  python tools/test_news_expiry_v3510.py
"""
import importlib
import os
import re
import sys
import logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
logging.basicConfig(level=logging.CRITICAL)

from src.common.config import Config
from src.analyzer.technical import TechnicalAnalyzer
from src.broker.position_manager import PositionManager, PositionContext

ta = TechnicalAnalyzer(logging.getLogger('t'))
PIP = 0.0001
fails = []


def check(name, cond, detail=''):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail else ''))
    if not cond:
        fails.append(name)


def _reload_news_floor(env_value):
    """Re-importa Config con NEWS_MIN_EXPIRY_MIN seteado (o borrado) en el entorno.

    Restaura SIEMPRE el valor previo y vuelve a recargar: el resto del test lee
    Config y no tiene que quedar contaminado por esto.
    """
    prev = os.environ.get("NEWS_MIN_EXPIRY_MIN")
    if env_value is None:
        os.environ.pop("NEWS_MIN_EXPIRY_MIN", None)
    else:
        os.environ["NEWS_MIN_EXPIRY_MIN"] = env_value
    try:
        import src.common.config as _cfg
        importlib.reload(_cfg)
        return _cfg.Config.NEWS_MIN_EXPIRY_MIN
    finally:
        if prev is None:
            os.environ.pop("NEWS_MIN_EXPIRY_MIN", None)
        else:
            os.environ["NEWS_MIN_EXPIRY_MIN"] = prev
        import src.common.config as _cfg2
        importlib.reload(_cfg2)


def sl_tp(profile, atr, direction='CALL', price=1.1550):
    ms = {'avg_range_pips': atr, 'chart_structures': {'supports': [], 'resistances': []}}
    return ta.compute_adaptive_sl_tp(direction, price, ms, profile, trigger_type='news')


# El profile activo real (de la DB) NO trae expiry_minutes -> ese es el bug del lazo.
BASE = {'stop_loss_pips': 3.5, 'take_profit_pips': 20.0}


def news_profile(floor):
    """Replica exacta de lo que hace la rama de news en AIdan_TodoEnUno tras v3.51.0."""
    p = BASE
    if floor > 15:
        p = dict(BASE)
        p['expiry_minutes'] = floor
    return p


def news_expiry(tp_pips, atr, floor):
    """Replica del calculo de expiry_min de la rama de news tras v3.51.0."""
    atr = atr if atr > 0 else 5.0
    e = max(15, int(tp_pips / atr * 5))
    e = max(e, floor)
    return min(e, max(60, floor))


print("\n=== PERILLA 1 — el TP crece y el expiry deja de clavarse en 15 ===")
# ATR medio real de los 12 news post-fix
for atr in (2.0, 2.7, 3.6, 4.6):
    off = sl_tp(news_profile(15), atr)
    on = sl_tp(news_profile(45), atr)
    e_off = news_expiry(off['tp_pips'], atr, 15)
    e_on = news_expiry(on['tp_pips'], atr, 45)
    check(f"ATR {atr}p: TP {off['tp_pips']}p -> {on['tp_pips']}p, expiry {e_off}min -> {e_on}min",
          on['tp_pips'] >= off['tp_pips'] and e_on == 45,
          f"R:R 1:{off['rr_ratio']} -> 1:{on['rr_ratio']}")

print("\n=== el SL (= el riesgo en dolares) NO cambia ===")
for atr in (2.0, 2.7, 3.6, 4.6):
    off, on = sl_tp(news_profile(15), atr), sl_tp(news_profile(45), atr)
    check(f"ATR {atr}p: SL {off['sl_pips']}p == {on['sl_pips']}p", off['sl_pips'] == on['sl_pips'])

print("\n=== MONOTONICO: nunca empeora el TP vs hoy (en ningun ATR) ===")
worse = [a for a in [x / 10 for x in range(10, 121)]
         if sl_tp(news_profile(45), a)['tp_pips'] < sl_tp(news_profile(15), a)['tp_pips']]
check("ningun ATR entre 1.0 y 12.0 baja el TP", not worse, f"{len(worse)} casos peores")

print("\n=== el piso no rompe el techo de 60min ni el caso ATR=0 ===")
check("TP grande + ATR chico no pasa de 60min", news_expiry(30.0, 2.0, 45) == 60,
      f"expiry={news_expiry(30.0, 2.0, 45)}")
check("ATR=0 usa el fallback 5.0 y respeta el piso", news_expiry(7.7, 0, 45) == 45)

print("\n=== APAGADO por env (NEWS_MIN_EXPIRY_MIN=0 o 15) => identico a v3.50.4 ===")
for floor in (0, 15):
    same = all(sl_tp(news_profile(floor), a)['tp_pips'] == sl_tp(news_profile(15), a)['tp_pips']
               for a in (2.0, 2.7, 3.6, 4.6))
    e = news_expiry(6.8, 2.7, floor)
    check(f"floor={floor}: TP identico y expiry={e}min", same and e == 15)

print("\n=== el profile NO se muta (el resto de la rama de news lo sigue usando) ===")
orig = {'stop_loss_pips': 3.5, 'take_profit_pips': 20.0, 'min_confidence': 60, 'min_impact': 50}
snapshot = dict(orig)
p = dict(orig); p['expiry_minutes'] = 45          # lo que hace el codigo
sl_tp(p, 2.7)
check("el dict original queda intacto", orig == snapshot, str(orig))
check("min_confidence/min_impact sobreviven en la copia",
      p['min_confidence'] == 60 and p['min_impact'] == 50)

print("\n=== PERILLA 2 — CLOSE_PROTECT sigue cortando a los 15min ===")
pm = PositionManager(profit_lock_arm=0.60, profit_lock_keep=0.60)


def ctx(trigger, expiry_min, t_in_trade, progress_p, anchor=15):
    base = float(expiry_min)
    if (trigger or '').lower() == 'news' and anchor > 0:
        base = float(min(expiry_min, anchor))          # replica del codigo
    return PositionContext(
        strategy_id=1, direction='CALL', fill_price=1.1550,
        current_price=1.1550 + progress_p * PIP,
        tp_distance=7.7 * PIP, sl_distance=3.9 * PIP,
        progress=progress_p * PIP, hwm=max(0.0, progress_p * PIP),
        time_in_trade_min=t_in_trade, base_expiry_min=base,
        max_hold_min=90.0, momentum_aligned_pips=-2.0,
        atr_pips=2.7, trigger_type=trigger,
    )


d = pm.evaluate(ctx('news', 45, 20, -1.8))
check("news perdiendo -1.8p a los 20min -> CLOSE_PROTECT (como hoy)",
      d.action == 'CLOSE_PROTECT', d.action)

d = pm.evaluate(ctx('news', 45, 20, -1.8, anchor=0))
check("MISMO caso con la perilla 2 APAGADA -> HOLD (el riesgo que evita)",
      d.action == 'HOLD', d.action)

d = pm.evaluate(ctx('news', 45, 10, -1.8))
check("news perdiendo antes de los 15min -> HOLD (no adelanta el corte)",
      d.action == 'HOLD', d.action)

print("\n=== el ganador SI se beneficia: sigue vivo pasado el expiry viejo ===")
d = pm.evaluate(ctx('news', 45, 30, +2.5))
check("news ganando +2.5p a los 30min -> HOLD/EXTEND (antes moria al expiry)",
      d.action == 'HOLD', f"{d.action} | {d.reason[:60]}")

print("\n=== no toca a los otros tracks ===")
for trig, exp in (('m15_structure', 45), ('structure', 15), ('h1_structure', 180), ('smc', 30)):
    base_on = ctx(trig, exp, 20, -1.8).base_expiry_min
    check(f"{trig}: base_expiry_min sigue siendo {exp}", base_on == float(exp), str(base_on))

print("\n=== MAX_HOLD sigue siendo el backstop ===")
d = pm.evaluate(ctx('news', 45, 95, -1.0))
check("news a los 95min -> CLOSE_MAXHOLD (M5 = 90min)", d.action == 'CLOSE_MAXHOLD', d.action)

print("\n=== Config expone las dos perillas ===")
# OJO (28-ago-2026): estos checks miraban Config.NEWS_MIN_EXPIRY_MIN == 45, o sea
# el valor EFECTIVO. Eso estaba mal: load_dotenv mete el .env en el entorno, asi
# que en cuanto la perilla se gira de verdad (se giro a 15 el 28-ago, tras el
# veredicto pre-declarado que no paso) el test se ponia rojo sin que hubiera
# ninguna regresion. Lo que hay que fijar es el DEFAULT DEL CODIGO -- "rebuildear
# sin tocar el .env no cambia el comportamiento" -- y eso se lee del SOURCE.
# Mismo patron que tools/test_m15_atr_floor_v3550.py, que ya tenia este problema
# resuelto (default 5.0 en el codigo, 8.0 en el .env).
_cfg_src = open(os.path.join(ROOT, 'src', 'common', 'config.py'), encoding='utf-8').read()

for _name, _default in (("NEWS_MIN_EXPIRY_MIN", "45"), ("NEWS_PM_BASE_EXPIRY_MIN", "15")):
    _m = re.search(
        r'%s\s*=\s*int\(os\.getenv\(\s*"%s"\s*,\s*"(\d+)"\s*\)\)' % (_name, _name),
        _cfg_src)
    check(f"Config declara {_name} con default literal", _m is not None)
    if _m:
        check(f"  su default en el codigo es {_default}", _m.group(1) == _default,
              f"es {_m.group(1)}")
    check(f"  Config.{_name} es int", isinstance(getattr(Config, _name), int),
          f"efectivo={getattr(Config, _name)!r}")

# La env var tiene que pisar de verdad; si no, la perilla es decorativa.
for _val, _exp in (("15", 15), ("0", 0), ("45", 45)):
    _got = _reload_news_floor(_val)
    check(f"NEWS_MIN_EXPIRY_MIN={_val} -> {_exp}", _got == _exp, str(_got))

# El valor EFECTIVO de hoy se INFORMA, no se afirma: cambia con el .env a
# proposito. <=15 = perilla apagada (news se comporta como en v3.50.4).
print(f"  info  valor efectivo hoy: NEWS_MIN_EXPIRY_MIN={Config.NEWS_MIN_EXPIRY_MIN} "
      f"({'APAGADA' if Config.NEWS_MIN_EXPIRY_MIN <= 15 else 'ACTIVA'}), "
      f"NEWS_PM_BASE_EXPIRY_MIN={Config.NEWS_PM_BASE_EXPIRY_MIN}")

print("\n" + ("TODO OK" if not fails else f"{len(fails)} FALLARON: {fails}"))
sys.exit(1 if fails else 0)
