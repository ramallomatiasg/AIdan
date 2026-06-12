# -*- coding: utf-8 -*-
"""v3.40.14 — Conciencia de eventos del calendario (capa de MEDICION, no de bloqueo).

get_event_proximity() devuelve la distancia (en minutos) al evento economico
HIGH/MEDIUM de USD/EUR mas cercano, hacia adelante y hacia atras, usando el
/calendar local (que cachea Forex Factory 1h; revivido en v3.40.4 tras el
auto-ban por hammering).

Ventana de evento (parametros iniciales, a calibrar con la data del shadow):
  HIGH:   15 min antes -> 30 min despues
  MEDIUM:  5 min antes -> 15 min despues

Uso: hook en _try_mt5_execute (cubre ejecucion normal Y retry). En modo shadow
solo se loguea a event_window_log — clasificacion EN el momento (leccion bounce),
para medir en 2-4 semanas como rinden las entradas cerca de eventos por trigger.
"""
import time
import requests
from datetime import datetime, timezone

# Ventanas por impacto (minutos)
WIN_BEFORE = {'High': 15.0, 'Medium': 5.0}
WIN_AFTER = {'High': 30.0, 'Medium': 15.0}

_cache = {'events': [], 'ts': 0.0}
_CACHE_TTL = 600  # 10 min; /calendar ya cachea FF 1h


def _get_events():
    now = time.time()
    if now - _cache['ts'] < _CACHE_TTL:
        return _cache['events']
    _cache['ts'] = now  # marca el intento (no martillar si falla)
    try:
        resp = requests.get('http://localhost:8000/calendar', timeout=4)
        if resp.status_code == 200:
            raw = resp.json().get('events', [])
            parsed = []
            for ev in raw:
                try:
                    dt = datetime.fromisoformat(str(ev.get('date', '')).replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    parsed.append({
                        'utc': dt.astimezone(timezone.utc),
                        'impact': ev.get('impact', ''),
                        'event': ev.get('event', ''),
                        'currency': ev.get('currency', ''),
                    })
                except Exception:
                    continue
            _cache['events'] = parsed
    except Exception:
        pass
    return _cache['events']


def get_event_proximity():
    """Proximidad al evento mas cercano. {} si no hay data de calendario
    (feed caido != sin eventos; el caller no debe inferir nada en ese caso)."""
    events = _get_events()
    if not events:
        return {}
    now = datetime.now(timezone.utc)
    nxt = prv = None
    for e in events:
        d_min = (e['utc'] - now).total_seconds() / 60.0
        if d_min >= 0:
            if nxt is None or d_min < nxt[0]:
                nxt = (d_min, e)
        else:
            if prv is None or -d_min < prv[0]:
                prv = (-d_min, e)
    out = {}
    in_window = False
    if nxt:
        out.update({'mins_to_next': round(nxt[0], 1), 'next_event': nxt[1]['event'],
                    'next_impact': nxt[1]['impact'], 'next_currency': nxt[1]['currency']})
        if nxt[0] <= WIN_BEFORE.get(nxt[1]['impact'], 0):
            in_window = True
    if prv:
        out.update({'mins_since_prev': round(prv[0], 1), 'prev_event': prv[1]['event'],
                    'prev_impact': prv[1]['impact'], 'prev_currency': prv[1]['currency']})
        if prv[0] <= WIN_AFTER.get(prv[1]['impact'], 0):
            in_window = True
    out['in_window'] = in_window
    return out
