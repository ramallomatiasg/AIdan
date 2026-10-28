"""
shadow_binaria.py — P13b: SHADOW en vivo de A1 (reversión a 2σ) como opción binaria, sobre el precio de Deriv.

NO OPERA. No existe la llamada `buy` en este módulo (test sobre el fuente). No toca MT5 ni la DB de AIdan:
escribe solo en su propia base `%APPDATA%/AIdan/state/binary_shadow.db`.
Criterio declarado ANTES de juntar: docs/p13b_shadow_binaria_criterio.md (0aa3233). Leer con
`python tools/score_shadow_binaria.py`.

Qué hace, en cada cierre de vela M5 de lunes a viernes 07:00-16:00 UTC:
  1. Pide las últimas velas M5 de cada instrumento a la API pública de Deriv.
  2. Calcula A1 con `gen_A1` (importada, la misma función de los backtests).
  3. Si hay señal y no hay otra abierta en ese instrumento, guarda el último tick como entrada y la expiración
     a +15 min. Además pide la cotización (proposal) y guarda el payout real: por el endpoint público de la API
     nueva de Deriv (sin app_id ni cuenta, desde el 28-oct) o, si hay `DERIV_APP_ID` en el entorno, por la vieja.
  4. Resuelve las señales vencidas con el último tick <= expiración.

Uso:
    pythonw tools/shadow_binaria.py              # lo lanza la tarea programada; corre hasta las 16:20 UTC
    python tools/shadow_binaria.py --once --ignore-window --db <tmp.db>   # prueba: un ciclo ya
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import traceback

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.screen_generators import gen_A1  # noqa: E402

SYMBOLS = ['frxEURUSD', 'frxGBPUSD', 'frxUSDJPY', 'frxAUDUSD', 'frxUSDCHF', 'frxUSDCAD',
           'frxEURGBP', 'frxEURJPY', 'frxGBPJPY', 'frxAUDJPY']
ENDPOINTS = ['red.derivws.com', 'ws.derivws.com', 'green.derivws.com', 'blue.derivws.com']
PUBLIC_APP_ID = '1089'          # sirve para velas y ticks; NO para cotizaciones (verificado 23-oct)
PUBLIC_V1_WS = 'wss://api.derivws.com/trading/v1/options/ws/public'   # API nueva: SÍ cotiza sin app_id (28-oct)
WINDOW_UTC = (7, 16)            # lunes a viernes, [07:00, 16:00) UTC
RESOLVE_GRACE_MIN = 20          # sigue vivo hasta 16:20 UTC para resolver las últimas
GRAN = 300
EXPIRY_SEC = 900
STAKE = 10
CANDLES = 40
STALE_SEC = 600
AFTER_CLOSE_SEC = 8


def state_dir():
    return os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state')


def default_db():
    return os.path.join(state_dir(), 'binary_shadow.db')


SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    candle_epoch INTEGER NOT NULL,
    created_utc TEXT NOT NULL,
    z REAL,
    direction TEXT NOT NULL,
    entry_spot REAL,
    entry_epoch INTEGER,
    expiry_epoch INTEGER,
    exit_spot REAL,
    exit_epoch INTEGER,
    outcome TEXT,
    app_id_used TEXT,
    proposal_payout REAL,
    proposal_ask REAL,
    proposal_spot REAL,
    proposal_error TEXT,
    UNIQUE(symbol, candle_epoch)
);
"""


def open_db(path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def in_window(now_utc):
    return now_utc.weekday() < 5 and WINDOW_UTC[0] <= now_utc.hour < WINDOW_UTC[1]


def a1_direction(closes):
    """+1 CALL / -1 PUT / 0 sin señal para la ÚLTIMA vela, con gen_A1 tal cual."""
    c = np.asarray(closes, dtype=np.float64)
    if c.size < 20:
        return 0, float('nan')
    idx, dirs = gen_A1(c, c, c, c, None, None)
    ma = c[-20:].mean()
    sd = c[-20:].std()
    z = (c[-1] - ma) / sd if sd > 0 else 0.0
    if idx.size and idx[-1] == c.size - 1:
        return int(dirs[-1]), float(z)
    return 0, float(z)


def outcome(direction, entry, exit_):
    if exit_ is None or entry is None:
        return None
    if exit_ == entry:
        return 'tie'
    up = exit_ > entry
    return 'win' if (up and direction == 'CALL') or (not up and direction == 'PUT') else 'loss'


class Api:
    def __init__(self, app_id):
        self.app_id = app_id
        self.ws = None
        self.session = None
        self.rid = 0

    async def __aenter__(self):
        import aiohttp
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, connect=15))
        last = None
        for host in ENDPOINTS:
            try:
                self.ws = await self.session.ws_connect(f'wss://{host}/websockets/v3?app_id={self.app_id}',
                                                        timeout=aiohttp.ClientWSTimeout(ws_close=15),
                                                        heartbeat=30)
                self.host = host
                return self
            except Exception as e:      # el 520 de Cloudflare en algunos hosts es habitual
                last = e
        await self.session.close()
        raise ConnectionError(f'ningún endpoint de Deriv respondió: {last!r}')

    async def __aexit__(self, *a):
        if self.ws is not None:
            await self.ws.close()
        await self.session.close()

    async def call(self, req, timeout=20):
        self.rid += 1
        req = dict(req, req_id=self.rid)
        await self.ws.send_json(req)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            msg = await asyncio.wait_for(self.ws.receive_json(), timeout=max(0.1, end - time.monotonic()))
            if msg.get('req_id') == self.rid:
                return msg
        raise TimeoutError(f'sin respuesta a {req}')

    async def server_time(self):
        return int((await self.call({'time': 1}))['time'])

    async def candles(self, sym):
        r = await self.call({'ticks_history': sym, 'style': 'candles', 'granularity': GRAN, 'count': CANDLES,
                             'end': 'latest'})
        if 'error' in r:
            raise RuntimeError(r['error'].get('message'))
        return r.get('candles') or []

    async def ticks(self, sym, end='latest', start=None, count=None):
        req = {'ticks_history': sym, 'style': 'ticks', 'end': end}
        if start is not None:
            req['start'] = start
        if count is not None:
            req['count'] = count
        r = await self.call(req)
        if 'error' in r:
            raise RuntimeError(r['error'].get('message'))
        h = r.get('history') or {}
        return list(zip(h.get('times', []), h.get('prices', [])))

    async def proposal(self, sym, contract_type):
        r = await self.call({'proposal': 1, 'amount': STAKE, 'basis': 'stake', 'contract_type': contract_type,
                             'currency': 'USD', 'duration': EXPIRY_SEC // 60, 'duration_unit': 'm',
                             'symbol': sym})
        if 'error' in r:
            return None, r['error'].get('message')
        p = r['proposal']
        return dict(payout=float(p['payout']), ask=float(p['ask_price']), spot=float(p['spot'])), None


class PublicQuoter(Api):
    """Cotizaciones con la API NUEVA de Deriv: su endpoint público cotiza `proposal` SIN app_id ni cuenta
    (verificado 28-oct: EUR/USD Rise 15 min, stake 10 ⇒ payout 17,92). Solo cotiza: no hay `buy` en el módulo."""

    def __init__(self):
        super().__init__('public-v1')

    async def __aenter__(self):
        import aiohttp
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, connect=15))
        try:
            self.ws = await self.session.ws_connect(PUBLIC_V1_WS, timeout=aiohttp.ClientWSTimeout(ws_close=15),
                                                    heartbeat=30)
        except Exception:
            await self.session.close()
            raise
        return self

    async def proposal(self, sym, contract_type):
        r = await self.call({'proposal': 1, 'amount': STAKE, 'basis': 'stake', 'contract_type': contract_type,
                             'currency': 'USD', 'duration': EXPIRY_SEC // 60, 'duration_unit': 'm',
                             'underlying_symbol': sym})
        if 'error' in r:
            return None, r['error'].get('message')
        p = r['proposal']
        return dict(payout=float(p['payout']), ask=float(p['ask_price']), spot=float(p['spot'])), None


async def resolve_pending(api, conn, now_epoch):
    rows = conn.execute("SELECT id, symbol, direction, entry_spot, expiry_epoch FROM signals "
                        "WHERE outcome IS NULL AND expiry_epoch <= ?", (now_epoch - 5,)).fetchall()
    for sid, sym, d, entry, exp in rows:
        try:
            tk = await api.ticks(sym, end=exp, start=exp - 180)
        except Exception as e:
            print(f'  resolver #{sid} {sym}: {e}')
            continue
        tk = [(t, p) for t, p in tk if t <= exp]
        if not tk:
            conn.execute("UPDATE signals SET outcome='void' WHERE id=?", (sid,))
            print(f'  #{sid} {sym}: sin ticks antes de la expiración -> void')
            continue
        t, p = tk[-1]
        oc = outcome(d, entry, float(p))
        conn.execute("UPDATE signals SET exit_spot=?, exit_epoch=?, outcome=? WHERE id=?", (float(p), int(t), oc, sid))
        print(f'  #{sid} {sym} {d} {entry} -> {p}: {oc}')
    conn.commit()


async def scan(api, conn, quote_app):
    now = await api.server_time()
    for sym in SYMBOLS:
        try:
            cs = await api.candles(sym)
        except Exception as e:
            print(f'  {sym}: velas no disponibles ({e})')
            continue
        cs = [c for c in cs if int(c['epoch']) + GRAN <= now]           # solo velas cerradas
        if len(cs) < 21:
            continue
        last = cs[-1]
        if now - (int(last['epoch']) + GRAN) > STALE_SEC:
            continue                                                     # mercado parado / feriado
        d, z = a1_direction([float(c['close']) for c in cs])
        if not d:
            continue
        if conn.execute("SELECT 1 FROM signals WHERE symbol=? AND outcome IS NULL", (sym,)).fetchone():
            continue
        tk = await api.ticks(sym, count=1)
        if not tk:
            continue
        te, pe = tk[-1]
        direction = 'CALL' if d > 0 else 'PUT'
        prop, perr = (None, 'sin cotizador (no conectó)')
        if quote_app is not None:
            prop, perr = await quote_app.proposal(sym, direction)
        try:
            conn.execute("INSERT INTO signals (symbol, candle_epoch, created_utc, z, direction, entry_spot, "
                         "entry_epoch, expiry_epoch, app_id_used, proposal_payout, proposal_ask, proposal_spot, "
                         "proposal_error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (sym, int(last['epoch']), dt.datetime.utcnow().isoformat(timespec='seconds'), z,
                          direction, float(pe), int(te), int(te) + EXPIRY_SEC,
                          quote_app.app_id if quote_app else None,
                          prop and prop['payout'], prop and prop['ask'], prop and prop['spot'], perr))
            conn.commit()
            pay = f" payout {prop['payout']:.2f}/{STAKE}" if prop else f' ({perr})'
            print(f'  SEÑAL {sym} {direction} z={z:+.2f} entrada {pe}{pay}')
        except sqlite3.IntegrityError:
            pass


async def cycle(conn, ignore_window, app_id):
    async with Api(PUBLIC_APP_ID) as api:
        quote = None
        try:
            # con app_id propio, la API vieja; si no, el endpoint público de la API nueva (no hace falta registrar nada)
            cand = Api(app_id) if app_id else PublicQuoter()
            try:
                await cand.__aenter__()
                quote = cand
            except Exception as e:
                print(f'  cotizador no disponible ({e!r}): la señal se guarda sin payout')
            now_epoch = await api.server_time()
            await resolve_pending(api, conn, now_epoch)
            if ignore_window or in_window(dt.datetime.utcnow()):
                await scan(api, conn, quote)
        finally:
            if quote is not None and quote.ws is not None:
                await quote.__aexit__()


def seconds_to_next_close():
    now = time.time()
    return (GRAN - now % GRAN) + AFTER_CLOSE_SEC


def run(db, once, ignore_window):
    conn = open_db(db)
    app_id = os.environ.get('DERIV_APP_ID') or None
    print(f'=== shadow_binaria {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC  db={db}  '
          f'payout={"app_id propio" if app_id else "endpoint público de la API nueva"} ===')
    end = dt.datetime.utcnow().replace(hour=WINDOW_UTC[1], minute=RESOLVE_GRACE_MIN, second=0, microsecond=0)
    while True:
        try:
            asyncio.run(cycle(conn, ignore_window, app_id))
        except Exception as e:
            print(f'  ciclo fallido: {e!r}')       # fail-loud en el log, sigue al próximo cierre
        if once or dt.datetime.utcnow() >= end:
            break
        time.sleep(seconds_to_next_close())
    n = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    print(f'=== fin. señales totales en la base: {n} ===')


def load_env():
    """Lee DERIV_APP_ID del .env de AIdan (%APPDATA%/AIdan/.env o el del repo) si no está en el entorno."""
    if os.environ.get('DERIV_APP_ID'):
        return
    for p in (os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', '.env'), os.path.join(ROOT, '.env')):
        if os.path.exists(p):
            with open(p, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.strip().startswith('DERIV_APP_ID='):
                        os.environ['DERIV_APP_ID'] = line.split('=', 1)[1].strip().strip('"\'')
                        return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--ignore-window', action='store_true')
    ap.add_argument('--db', default=None)
    a = ap.parse_args()
    load_env()
    db = a.db or default_db()
    if a.once:
        run(db, True, a.ignore_window)
        return
    os.makedirs(state_dir(), exist_ok=True)
    log = os.path.join(state_dir(), f'binary_shadow_{dt.datetime.utcnow():%Y%m%d}.log')
    with open(log, 'a', encoding='utf-8', buffering=1) as f:   # pythonw no tiene consola
        sys.stdout = sys.stderr = f
        try:
            if dt.datetime.utcnow().weekday() >= 5:
                print('fin de semana: no corre')
                return
            run(db, False, a.ignore_window)
        except Exception:
            traceback.print_exc()


if __name__ == '__main__':
    main()
