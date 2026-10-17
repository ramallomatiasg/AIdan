"""
Offset hora-servidor-MT5 vs UTC, ROBUSTO a mercado cerrado.

Por que existe (20-sep-2026): los 3 scorers de shadow derivaban el offset como
`tick.time - time.time()` redondeado a 30 min. Con el mercado ABIERTO eso da el
offset real (ICMarkets: +2h/+3h). Con el mercado CERRADO el ultimo tick es el del
cierre del viernes => la resta da ~-44h el domingo, el redondeo la acepta, y cada
ventana que puntua el scorer cae ~2 dias antes. Las corridas del 13-sep y 20-sep
(sabado/domingo) escribieron outcomes de ventanas equivocadas: 64 'open' del shadow
trader (media -11,5 y -33,9p, contra -4p de las corridas limpias) y 267 filas del
shadow book. Nadie fallo: el numero era PLAUSIBLE. La clase de bug del proyecto.

Regla:
  1. Si el tick es FRESCO (server - ahora dentro de [-1h, +5h], el rango que puede
     dar un broker EET con DST) => ese es el offset, y se CACHEA en
     tools/.mt5_server_offset.json.
  2. Si el tick esta viejo (mercado cerrado) => se usa el cache, o el override
     `--server-offset-hours`, o se ABORTA con error legible. Nunca un numero
     plausible.
Un test de fuente verifica que ningun scorer vuelva a la formula cruda.

17-oct-2026 — guardas: (a) con el mercado FX cerrado (vie >=20:45 a dom <21:00 UTC) nunca
se deriva, (b) solo se aceptan offsets posibles de ICMarkets (+2h/+3h). El offset server-UTC
REAL es +3h (verano) y eso esta bien.
⚠️ PERO OJO, verificado el 17-oct: `mt5.copy_rates_range` toma un datetime NAIVE como hora
LOCAL de la PC (AR, UTC-3) y le suma 3h. Los scorers que arman `srv_start = utc + offset`
naive piden la ventana 3h TARDE con este offset. Con offset 0 (el "bug" del cache del 10-oct)
la ventana caia justo por casualidad. Arreglo pendiente de OK: pasar datetimes tz-aware.
"""
import json
import os
import time as _time

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.mt5_server_offset.json')
FRESH_MIN_S = -3600        # el server nunca deberia estar mas de 1h DETRAS de UTC
FRESH_MAX_S = 5 * 3600     # ni mas de 5h adelante (EET+DST = +3h)
ALLOWED_OFFSETS_S = (7200, 10800)  # ICMarkets (EET): +2h invierno / +3h verano


def market_closed_utc(now):
    """Ventana de fin de semana del FX en UTC (con margen): vie >=20:45 a dom <21:00."""
    t = _time.gmtime(now)
    mins = t.tm_hour * 60 + t.tm_min
    if t.tm_wday == 4 and mins >= 20 * 60 + 45:
        return True
    if t.tm_wday == 5:
        return True
    if t.tm_wday == 6 and mins < 21 * 60:
        return True
    return False


class StaleTickError(RuntimeError):
    pass


def derive_offset_s(tick_time, now=None, override_hours=None, cache_path=CACHE_PATH):
    """Devuelve el offset server-UTC en segundos (multiplo de 1800) o lanza StaleTickError."""
    if override_hours is not None:
        return int(round(float(override_hours) * 2) * 1800)
    now = _time.time() if now is None else now
    raw = float(tick_time) - float(now)
    off = int(round(raw / 1800.0) * 1800)
    if (FRESH_MIN_S <= raw <= FRESH_MAX_S and off in ALLOWED_OFFSETS_S
            and not market_closed_utc(now)):
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump({'offset_s': off, 'measured_at_utc': int(now)}, f)
        except OSError:
            pass
        return off
    # tick viejo: mercado cerrado o feed muerto
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding='utf-8') as f:
                cached = json.load(f)
            off = int(cached['offset_s'])
            if off not in ALLOWED_OFFSETS_S:
                raise ValueError(f"offset cacheado imposible: {off}s")
            print(f"  [offset] tick viejo ({raw/3600:.1f}h): mercado cerrado, "
                  f"uso el offset cacheado {off/3600:+.1f}h (medido {cached.get('measured_at_utc')})")
            return off
        except (OSError, ValueError, KeyError, TypeError):
            pass
    raise StaleTickError(
        f"el ultimo tick es de hace {-raw/3600:.1f}h (mercado cerrado) y no hay offset "
        f"cacheado. Correr una vez con mercado abierto, o pasar --server-offset-hours N "
        f"(ICMarkets: 3 en verano, 2 en invierno). NO se puntua con un offset inventado.")


def mt5_offset_s(mt5, symbol="EURUSD", override_hours=None):
    """Helper para los scorers: toma el tick de MT5 (ya inicializado) y deriva el offset."""
    tick = mt5.symbol_info_tick(symbol)
    if override_hours is None and (not tick or not getattr(tick, 'time', 0)):
        raise StaleTickError("sin tick: no se puede derivar el offset del server")
    return derive_offset_s(tick.time if tick else 0, override_hours=override_hours)
