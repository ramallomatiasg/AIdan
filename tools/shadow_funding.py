"""
shadow_funding.py — P19: SHADOW en papel del carry de funding (P15), con datos públicos de Binance en vivo.

NO OPERA: no hay ninguna llamada que mande órdenes (solo GET a endpoints públicos; test sobre el fuente). No toca MT5
ni la DB de AIdan: escribe solo en `%APPDATA%/AIdan/state/funding_shadow.db`.
Criterio declarado ANTES de juntar: docs/p19_shadow_funding_criterio.md.

Cada corrida:
  1. FOTO: bid/ask de spot y perpetuo + marca + último funding de las 6 principales, y la decisión que tomaría la
     regla de P15 con el funding conocido hasta ahora (media 7 días ≥ 0,005% entra, < 0 sale).
  2. LIBRO: reconstruye desde SHADOW_START con el motor `simulate` de P15 (importado) y reporta contra el criterio.

Uso:
    python tools/shadow_funding.py                # foto + reporte (lo que corre la tarea)
    python tools/shadow_funding.py --report       # solo reporte, sin foto
    python tools/shadow_funding.py --db <tmp.db>  # prueba
"""
import argparse
import datetime as dt
import os
import sqlite3
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import backtest_p15_funding as p15  # noqa: E402

SYMS = p15.MAIN
SHADOW_START_MS = int(dt.datetime(2026, 10, 27, tzinfo=dt.timezone.utc).timestamp() * 1000)
WARMUP_MS = p15.WINDOW_MS + p15.P8H
READ_90 = SHADOW_START_MS + 90 * 86400 * 1000
DECIDE_180 = SHADOW_START_MS + 180 * 86400 * 1000
SLIP_ASSUMED = 0.0002                       # P15: 0,02% por lado y pata

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    ts_ms INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    spot_bid REAL, spot_ask REAL, perp_bid REAL, perp_ask REAL, mark REAL,
    last_funding REAL, next_funding_ms INTEGER,
    signal_7d REAL,
    decision TEXT,
    half_spread_sum REAL,
    error TEXT
);
"""


def default_db():
    return os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state', 'funding_shadow.db')


def fetch_funding(sym, start, end):
    out = []
    while start < end:
        r = p15._get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}USDT&startTime={start}&limit=1000')
        if not r:
            break
        out += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r if int(x['fundingTime']) < end]
        if len(r) < 1000:
            break
        start = int(r[-1]['fundingTime']) + 1
    return out


def fetch_klines(sym, perp, start, end):
    base = 'https://fapi.binance.com/fapi/v1/klines' if perp else 'https://api.binance.com/api/v3/klines'
    r = p15._get(f'{base}?symbol={sym}USDT&interval=8h&startTime={start}&limit=1000')
    # solo velas ya abiertas (el open es lo que usa el motor) y anteriores a `end`
    return [(int(x[0]), float(x[1])) for x in r if int(x[0]) < end]


def signal_7d(funding, t):
    """Media del funding de los 7 días previos a t, por cada 8 h (igual que `simulate`)."""
    if not funding or funding[0][0] > t - p15.WINDOW_MS:
        return None
    v = [f for ft, f in funding if t - p15.WINDOW_MS <= ft < t]
    return sum(v) / 21.0


def snapshot(conn, data, now_ms):
    rows = 0
    for s in SYMS:
        try:
            sb = p15._get(f'https://api.binance.com/api/v3/ticker/bookTicker?symbol={s}USDT')
            fb = p15._get(f'https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol={s}USDT')
            pi = p15._get(f'https://fapi.binance.com/fapi/v1/premiumIndex?symbol={s}USDT')
            sbid, sask = float(sb['bidPrice']), float(sb['askPrice'])
            fbid, fask = float(fb['bidPrice']), float(fb['askPrice'])
            hs = (sask - sbid) / (sask + sbid) + (fask - fbid) / (fask + fbid)
            sig = signal_7d(data[s]['funding'], now_ms)
            dec = None if sig is None else ('in' if sig >= p15.ENTER else ('out' if sig < p15.EXIT else 'hold'))
            conn.execute('INSERT INTO snapshots (ts_utc, ts_ms, symbol, spot_bid, spot_ask, perp_bid, perp_ask, mark,'
                         ' last_funding, next_funding_ms, signal_7d, decision, half_spread_sum) '
                         'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (dt.datetime.utcfromtimestamp(now_ms / 1000).isoformat(), now_ms, s, sbid, sask, fbid,
                          fask, float(pi['markPrice']), float(pi['lastFundingRate']), int(pi['nextFundingTime']),
                          sig, dec, hs))
            rows += 1
        except Exception as e:  # una moneda caída no tumba la foto de las otras, pero queda registrada
            conn.execute('INSERT INTO snapshots (ts_utc, ts_ms, symbol, error) VALUES (?,?,?,?)',
                         (dt.datetime.utcfromtimestamp(now_ms / 1000).isoformat(), now_ms, s, repr(e)[:300]))
    conn.commit()
    return rows


def book(data, now_ms):
    """Libro en papel desde SHADOW_START con el motor de P15. Devuelve retornos de cartera por período + detalle."""
    grid = np.arange(SHADOW_START_MS, now_ms - now_ms % p15.P8H + 1, p15.P8H, dtype=np.int64).tolist()
    if len(grid) < 2:
        return None, {}, grid
    rs, det = [], {}
    for s in SYMS:
        r, comp, tot = p15.simulate(data[s], grid)
        rs.append(r)
        det[s] = (tot, comp)
    return np.mean(rs, axis=0), det, grid


def live_state(data, grid):
    """Estado in/out de cada moneda según el libro, en cada punto del grid (para el criterio 3)."""
    out = {}
    for s in SYMS:
        st = 'out'
        states = {}
        for t in grid:
            sig = signal_7d(data[s]['funding'], t)
            if sig is not None:
                if st == 'out' and sig >= p15.ENTER:
                    st = 'in'
                elif st == 'in' and sig < p15.EXIT:
                    st = 'out'
            states[t] = st
        out[s] = states
    return out


def hurdle_last():
    import csv
    with open(os.path.join(ROOT, 'docs', 'p11_policy_rates.csv')) as f:
        rows = list(csv.DictReader(f))
    return float(rows[-1]['USD']) / 100.0, rows[-1]['month']


def report(conn, data, now_ms):
    port, det, grid = book(data, now_ms)
    days = (now_ms - SHADOW_START_MS) / 86400000
    print('=' * 76)
    print('SHADOW FUNDING (P19) — carry de funding en papel, regla de P15 congelada, Binance público')
    print('=' * 76)
    print(f'  desde {dt.datetime.utcfromtimestamp(SHADOW_START_MS / 1000):%Y-%m-%d} · {days:.1f} días · '
          f'lectura a 90 d ({dt.datetime.utcfromtimestamp(READ_90 / 1000):%Y-%m-%d}) · '
          f'decisión a 180 d ({dt.datetime.utcfromtimestamp(DECIDE_180 / 1000):%Y-%m-%d})')
    hr, hm = hurdle_last()
    ann = None
    if port is not None and port.size:
        ann = float(port.mean() * p15.PER_YEAR)
        print(f'  libro: {port.size} períodos de 8 h · anualizado {ann:+.2%} sobre el capital · tasa libre {hr:.2%} ({hm})')
        for s, (tot, c) in det.items():
            print(f"    {s:5s} neto {tot:+.3%}  funding {c['funding']:+.5f} base {c['base']:+.5f} "
                  f"costo {c['cost']:.4f} (x nocional)  entradas {c['trades']}")
    else:
        print('  libro: todavía sin períodos completos')
    snaps = conn.execute('SELECT ts_ms, symbol, decision, half_spread_sum FROM snapshots WHERE error IS NULL').fetchall()
    errs = conn.execute('SELECT COUNT(*) FROM snapshots WHERE error IS NOT NULL').fetchone()[0]
    hs = [x[3] for x in snaps if x[3] is not None]
    med = float(np.median(hs)) if hs else None
    print(f'  fotos: {len(snaps)} filas ({errs} con error)' +
          (f' · medio spread spot+perp mediana {med:.4%} (asumido {SLIP_ASSUMED:.2%})' if med is not None else ''))
    agree = comp = 0
    if snaps and grid:
        st = live_state(data, grid)
        for ts, s, d, _ in snaps:
            if d not in ('in', 'out'):
                continue
            k = max((t for t in grid if t <= ts), default=None)
            if k is None:
                continue
            comp += 1
            agree += st[s][k] == d
    print(f'  decisiones foto vs libro: {agree}/{comp} comparables')
    c1 = ann is not None and ann > hr
    c2 = med is not None and med <= SLIP_ASSUMED
    c3 = comp > 0 and agree / comp >= 0.95
    for k, v in (('1_premio_vivo (anual > tasa libre)', c1), ('2_ejecucion (medio spread <= 0,02%)', c2),
                 ('3_sin_futuro (foto = libro >= 95%)', c3)):
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    if now_ms < READ_90:
        print('  >>> SIN VEREDICTO (antes de la lectura de 90 días)')
    elif now_ms < DECIDE_180:
        print('  >>> LECTURA INTERMEDIA (la decisión es a los 180 días)')
    else:
        print(f"  >>> {'PASA' if (c1 and c2 and c3) else 'NO PASA'} (criterio de 180 días)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true', help='solo reporte, sin foto')
    ap.add_argument('--db', default=default_db())
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.db)), exist_ok=True)
    conn = sqlite3.connect(a.db)
    conn.executescript(SCHEMA)
    now_ms = int(time.time() * 1000)
    data = {}
    for s in SYMS:
        st = SHADOW_START_MS - WARMUP_MS
        data[s] = dict(funding=fetch_funding(s, st, now_ms), spot=fetch_klines(s, False, st, now_ms),
                       perp=fetch_klines(s, True, st, now_ms))
    if not a.report:
        n = snapshot(conn, data, now_ms)
        print(f'  foto: {n}/{len(SYMS)} monedas')
    report(conn, data, now_ms)
    conn.close()


if __name__ == '__main__':
    main()
