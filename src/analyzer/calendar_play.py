"""
calendar_play.py — v3.63.0: SHADOW del "calendar play" (operar el DATO, no el articulo).

Que mide: lo que un trader discrecional hace de verdad con las noticias — mira el
calendario, sabe a que hora sale el dato (NFP, CPI, tasas) y se posiciona ALREDEDOR de
esa hora. AIdan nunca tuvo eso: su track `news` reacciona a ARTICULOS del RSS (74 de 76
trades medidos no correspondian a ningun evento del calendario) y perdio −$178 lifetime.

Que hace este modulo, por evento HIGH de USD/EUR del calendario (Forex Factory via
/calendar local):
  - a T−60s toma bid/ask (el "pre": precio y spread en calma);
  - desde T hasta T+3min muestrea el tick cada ~1s, despues cada ~10s hasta T+15min;
  - guarda la RUTA (bid/ask por offset), la excursion maxima hacia arriba y hacia abajo
    (3 y 15 min), el cierre a +1/+3/+5/+15 min y el spread maximo del primer minuto;
  - a T+20min intenta completar `actual` (FF si ya refresco; si no, el titulo de
    Forexlive "X vs Y expected" en la tabla `news`) y lo deja en la fila.

Que NO hace, por construccion: no crea estrategias, no manda ordenes, no toca
`auto_strategies`. Este archivo no importa nada que ejecute (hay test sobre el fuente).
Es MEDICION para responder, con numeros propios y clasificados EN EL MOMENTO:
  (1) ¿el precio se mueve en la direccion de la sorpresa (actual vs forecast) lo
      suficiente para pagar spread+comision entrando a +15-60s?
  (2) ¿cuanto se ensancha el spread en el release? (solo se puede medir en vivo — la TCA
      en calma da 0,10p y no dice nada de ese segundo).
  (3) ¿cuanta parte del movimiento ya paso a +60s? (research: ~80% en 3 min).

Por que la muestra crece rapido: son ~10 releases HIGH USD/EUR por mes, por CALENDARIO,
no por trades — n=30 en ~3 meses. Ningun otro shadow del proyecto acumula asi.

Gate pre-declarado (tools/score_calendar_play.py): n>=25 eventos con `actual` y sorpresa
no nula; el movimiento a favor de la sorpresa a +5 min, NETO de spread real + 1,3p de
comision, con media Y mediana > 0 y CI95 que no cruce cero. Si a n>=40 no pasa =>
CALENDAR_PLAY_MODE=off y se cierra la puerta con data.

Limites declarados:
  - `forecast`/`previous` vienen del feed FF tal cual (strings con %, K, M): el parser
    es best-effort; si no parsea, la fila queda con la ruta pero sin sorpresa (se reporta).
  - El signo "bueno para el USD" depende del indicador (desempleo alto = malo). El scorer
    lleva una lista chica de indicadores INVERSOS; lo que no esta en la lista se asume
    directo y se declara.
  - Varios eventos a la misma hora (NFP + tasa de desempleo + salarios) comparten la
    ruta de precio: una fila por evento, misma ruta. El scorer los agrupa por release_ts
    para no contar el mismo movimiento 3 veces.
"""
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger('calendar_play')

PIP = 0.0001
PRE_OFFSET_S = 60            # snapshot "pre" a T-60s
DENSE_UNTIL_S = 180          # muestreo ~1s hasta T+3min
TOTAL_UNTIL_S = 900          # despues ~10s hasta T+15min
ACTUAL_AFTER_S = 1200        # a T+20min intentar completar `actual`
CLOSE_OFFSETS = (60, 180, 300, 900)
CAL_URL = 'http://localhost:8000/calendar'
CAL_TTL_S = 600
IMPACTS = ('High',)
CURRENCIES = ('USD', 'EUR')

_cal_cache = {'ts': 0.0, 'events': []}


# ───────────────────────────── parsing ─────────────────────────────
_NUM = re.compile(r'([-+]?\d+(?:[.,]\d+)?)\s*([%KMBkmb])?')


def parse_number(s):
    """'2.9%' -> 2.9 · '263K' -> 263000 · '-0.1' -> -0.1 · '' -> None."""
    if s is None:
        return None
    m = _NUM.search(str(s).replace(',', '.'))
    if not m:
        return None
    v = float(m.group(1))
    suf = (m.group(2) or '').upper()
    return v * {'K': 1e3, 'M': 1e6, 'B': 1e9}.get(suf, 1.0)


_VS = re.compile(
    r'([-+]?\d+(?:[.,]\d+)?\s*[%KMBkmb]?)\s+(?:vs\.?|versus|against)\s+'
    r'([-+]?\d+(?:[.,]\d+)?\s*[%KMBkmb]?)\s*(?:expected|exp\.?|estimate|est\.?|consensus|forecast)',
    re.IGNORECASE)


def parse_vs_title(title):
    """Titulo Forexlive 'US August CPI +2.9% vs +2.9% expected' -> (actual, expected) o None."""
    if not title:
        return None
    m = _VS.search(title)
    if not m:
        return None
    a, e = parse_number(m.group(1)), parse_number(m.group(2))
    if a is None or e is None:
        return None
    return a, e


_STOP = {'the', 'of', 'and', 'us', 'u.s.', 'eurozone', 'euro', 'area', 'zone', 'm/m', 'y/y',
         'q/q', 'final', 'prelim', 'flash', 'core', 'change', 'rate', 'index', 'data'}


def title_matches_event(news_title, event_title):
    """Match por keywords (cota inferior declarada): >=1 palabra significativa compartida."""
    def words(t):
        return {w for w in re.findall(r'[a-z][a-z.]+', (t or '').lower()) if len(w) > 2 and w not in _STOP}
    a, b = words(news_title), words(event_title)
    if not a or not b:
        return False
    return len(a & b) >= 1


def event_key(ev):
    return f"{ev.get('event','')}|{int(ev['release_ts'])}"


# ───────────────────────────── calendario ─────────────────────────────
def fetch_events(now=None):
    """Eventos HIGH USD/EUR con release_ts (epoch UTC). Cache 10 min. [] si el feed no responde
    (feed caido != sin eventos; el loop simplemente no hace nada)."""
    now = now or time.time()
    if now - _cal_cache['ts'] < CAL_TTL_S:
        return _cal_cache['events']
    _cal_cache['ts'] = now
    try:
        r = requests.get(CAL_URL, timeout=4)
        if r.status_code != 200:
            return _cal_cache['events']
        out = []
        for ev in r.json().get('events', []):
            if ev.get('impact') not in IMPACTS or ev.get('currency') not in CURRENCIES:
                continue
            try:
                dt = datetime.fromisoformat(str(ev.get('date', '')).replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            e = dict(ev)
            e['release_ts'] = dt.timestamp()
            out.append(e)
        _cal_cache['events'] = out
    except Exception as e:
        logger.warning(f"calendar_play: /calendar no responde: {e}")
    return _cal_cache['events']


# ───────────────────────────── ruta de precio ─────────────────────────────
def summarize_path(pre_bid, pre_ask, samples):
    """samples: [(t_off_s, bid, ask)]. Devuelve el resumen en pips vs el mid del 'pre'.
    up = el precio subio (EURUSD), down = bajo. Todo en pips positivos salvo los closes."""
    pre_mid = (pre_bid + pre_ask) / 2.0
    out = {'max_up_3m': 0.0, 'max_down_3m': 0.0, 'max_up_15m': 0.0, 'max_down_15m': 0.0,
           'spread_max_60s': (pre_ask - pre_bid) / PIP, 'pre_spread': (pre_ask - pre_bid) / PIP}
    closes = {}
    for t, bid, ask in samples:
        mid = (bid + ask) / 2.0
        d = (mid - pre_mid) / PIP
        if t <= DENSE_UNTIL_S:
            out['max_up_3m'] = max(out['max_up_3m'], d)
            out['max_down_3m'] = max(out['max_down_3m'], -d)
        out['max_up_15m'] = max(out['max_up_15m'], d)
        out['max_down_15m'] = max(out['max_down_15m'], -d)
        if t <= 60:
            out['spread_max_60s'] = max(out['spread_max_60s'], (ask - bid) / PIP)
        for off in CLOSE_OFFSETS:
            # ultimo sample <= offset
            if t <= off:
                closes[off] = d
    for off in CLOSE_OFFSETS:
        out[f'close_{off // 60}m'] = round(closes.get(off, 0.0), 1)
    for k in ('max_up_3m', 'max_down_3m', 'max_up_15m', 'max_down_15m', 'spread_max_60s', 'pre_spread'):
        out[k] = round(out[k], 1)
    return out


def _tick(get_exec):
    try:
        ex = get_exec()
        if ex is None:
            return None
        t = ex.get_tick()
        if t and t.get('bid') and t.get('ask'):
            return float(t['bid']), float(t['ask'])
    except Exception:
        return None
    return None


def record_release(events_same_ts, get_exec, db, sleep=time.sleep, clock=time.time):
    """Bloquea el thread ~16 min alrededor de UN release (varios eventos a la misma hora
    comparten la ruta). Escribe una fila por evento via db.log_calendar_play. `sleep`/`clock`
    inyectables para tests."""
    T = float(events_same_ts[0]['release_ts'])
    # 1) pre a T-60s
    wait = T - PRE_OFFSET_S - clock()
    if wait > 0:
        sleep(wait)
    pre = _tick(get_exec)
    if pre is None:
        logger.warning(f"calendar_play: sin tick pre para {events_same_ts[0].get('event')} — no se registra")
        return None
    pre_bid, pre_ask = pre
    # 2) esperar T
    wait = T - clock()
    if wait > 0:
        sleep(wait)
    samples = []
    while True:
        off = clock() - T
        if off > TOTAL_UNTIL_S:
            break
        tk = _tick(get_exec)
        if tk:
            samples.append((round(off, 1), tk[0], tk[1]))
        sleep(1.0 if off < DENSE_UNTIL_S else 10.0)
    summ = summarize_path(pre_bid, pre_ask, samples)
    keys = []
    for ev in events_same_ts:
        k = event_key(ev)
        keys.append(k)
        db.log_calendar_play(
            event_key=k, event_title=ev.get('event', ''), currency=ev.get('currency', ''),
            impact=ev.get('impact', ''), release_ts=int(T),
            forecast=ev.get('forecast', ''), previous=ev.get('previous', ''),
            actual=ev.get('actual', '') or None,
            pre_bid=pre_bid, pre_ask=pre_ask, samples_json=json.dumps(samples), **summ)
        logger.info(f"calendar_play SHADOW: {ev.get('currency')} {ev.get('event')} "
                    f"pre_spread={summ['pre_spread']}p spread_max60s={summ['spread_max_60s']}p "
                    f"up3m={summ['max_up_3m']} down3m={summ['max_down_3m']} close5m={summ['close_5m']} (NO opera)")
    return keys


def resolve_actual(events_same_ts, db, news_rows_fn):
    """A T+20min: completar `actual`. Prefiere FF (si /calendar ya refresco con actual),
    si no parsea el titulo de Forexlive ('X vs Y expected') dentro de [T, T+10min]."""
    T = float(events_same_ts[0]['release_ts'])
    _cal_cache['ts'] = 0.0  # forzar refresh
    fresh = {event_key(e): e for e in fetch_events()}
    for ev in events_same_ts:
        k = event_key(ev)
        ff = fresh.get(k, {}).get('actual')
        if ff:
            db.update_calendar_play_actual(k, str(ff), 'ff')
            continue
        try:
            for title in news_rows_fn(T, T + 600):
                if not title_matches_event(title, ev.get('event', '')):
                    continue
                parsed = parse_vs_title(title)
                if parsed:
                    db.update_calendar_play_actual(k, str(parsed[0]), 'forexlive', str(parsed[1]))
                    break
        except Exception as e:
            logger.warning(f"calendar_play: resolve_actual fallo para {k}: {e}")


# ───────────────────────────── loop ─────────────────────────────
def _loop(get_exec, db, mode):
    pending_actual = []  # [(events_same_ts, due_ts)]
    logger.info(f"calendar_play: modo={mode} (shadow: registra la ruta del precio en cada release HIGH USD/EUR, NO opera)")
    while True:
        try:
            now = time.time()
            # completar actuals vencidos
            for item in list(pending_actual):
                if now >= item[1]:
                    resolve_actual(item[0], db, db.news_titles_between)
                    pending_actual.remove(item)
            groups = {}
            for ev in fetch_events(now):
                T = ev['release_ts']
                if T - PRE_OFFSET_S - 15 <= now <= T - PRE_OFFSET_S + 5 and not db.calendar_play_already_logged(event_key(ev)):
                    groups.setdefault(int(T), []).append(ev)
            for T, evs in groups.items():
                keys = record_release(evs, get_exec, db)
                if keys:
                    pending_actual.append((evs, T + ACTUAL_AFTER_S))
        except Exception as e:
            logger.error(f"calendar_play loop error: {e}")
        time.sleep(5)


def start(get_exec, db, mode):
    """Lanza el thread daemon. mode='off' => no arranca (devuelve None)."""
    if (mode or 'shadow').lower() == 'off':
        logger.info("calendar_play: OFF")
        return None
    t = threading.Thread(target=_loop, args=(get_exec, db, mode), daemon=True, name='CalendarPlayShadow')
    t.start()
    return t
