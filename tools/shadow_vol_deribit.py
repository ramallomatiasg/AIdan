"""
shadow_vol_deribit.py — P39b: SHADOW en papel de la prima de volatilidad (P39) con precios REALES de Deribit.

NO OPERA: solo GET a endpoints públicos de Deribit y Binance, sin cuenta ni claves (test sobre el fuente). No toca MT5
ni la DB de AIdan: escribe solo en `%APPDATA%/AIdan/state/vol_shadow.db`.
Criterio declarado ANTES de juntar: docs/p39b_shadow_vol_criterio.md (ca23af9).

Cada corrida (la tarea `aidan-shadow-vol`, una vez por día):
  1. DIAGNÓSTICO: straddle ATM a ~30 días de BTC y ETH ⇒ IV bid/ask/mark y brecha DVOL − IV bid.
  2. LIBRO: por moneda, liquida al vencimiento, rebalancea la cobertura delta o abre el ciclo nuevo (regla de P39).
  3. REPORTE contra el criterio.

Uso:
    python tools/shadow_vol_deribit.py                # corrida completa (lo que corre la tarea)
    python tools/shadow_vol_deribit.py --report       # solo reporte
    python tools/shadow_vol_deribit.py --db <tmp.db>  # prueba
"""
import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import time
import urllib.request

CURS = ('BTC', 'ETH')
ANCHOR = dt.datetime(2026, 11, 13, tzinfo=dt.timezone.utc)
CYCLE_D = 30
EXP_MIN, EXP_MAX, EXP_TARGET = 20, 45, 30
H = 30                                  # días de realizada previa (P39)
HEDGE_COST = 0.0007                     # taker 0,05% + deslizamiento 0,02%
FEE_IN, FEE_OUT, FEE_CAP = 0.0003, 0.00015, 0.125
PROXY_COST = 2.0                        # costo del proxy de P39, en puntos de vol
DAY_MS = 86400000
HOSTS = ('https://www.deribit.com/api/v2/public/', 'https://api.binance.com/api/v3/',
         'https://fapi.binance.com/fapi/v1/')
DERIBIT_METHODS = ('get_index_price', 'get_instruments', 'ticker', 'get_volatility_index_data',
                   'get_delivery_prices')

SCHEMA = """
CREATE TABLE IF NOT EXISTS diag (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT, ts_ms INTEGER, cur TEXT,
    expiry_ms INTEGER, days REAL, strike REAL, fwd REAL, idx REAL,
    c_bid_iv REAL, c_ask_iv REAL, c_mark_iv REAL, p_bid_iv REAL, p_ask_iv REAL, p_mark_iv REAL,
    dvol_now REAL, gap_bid REAL, error TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cur TEXT, cycle INTEGER, status TEXT,
    opened_ms INTEGER, dvol_open REAL, rv_prev REAL,
    expiry_ms INTEGER, strike REAL, call TEXT, put TEXT, c_bid REAL, p_bid REAL, idx0 REAL, fwd0 REAL,
    iv_mark0 REAL, premium_usd REAL, fee_in_usd REAL, vega_usd REAL,
    hedge_pos REAL DEFAULT 0, hedge_px REAL, hedge_pnl REAL DEFAULT 0, hedge_cost REAL DEFAULT 0,
    funding_paid REAL DEFAULT 0, last_ms INTEGER, runs INTEGER DEFAULT 0,
    settle_px REAL, payoff_usd REAL, fee_out_usd REAL, pnl_usd REAL, pnl_pct REAL, pnl_vol REAL,
    rv_fwd REAL, proxy_vol REAL, closed_ms INTEGER, note TEXT
);
CREATE TABLE IF NOT EXISTS hedge_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id INTEGER, ts_ms INTEGER, perp_px REAL, iv REAL,
    delta REAL, new_pos REAL, traded REAL, cost REAL, funding REAL, mtm_usd REAL
);
"""


# ── red (solo lectura) ───────────────────────────────────────────────────────

def _get(url):
    assert url.startswith(HOSTS), url
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                return json.load(r)
        except Exception:
            if k == 3:
                raise
            time.sleep(2 + 3 * k)


def deribit(method, query):
    assert method in DERIBIT_METHODS, method
    return _get(f'{HOSTS[0]}{method}?{query}')['result']


def spot_opens(cur, start_ms, end_ms):
    """Precio de apertura de las velas de 8 h del spot de Binance (mismo dato que P39), [(t, p)]."""
    out, s = [], start_ms
    while s < end_ms:
        r = _get(f'{HOSTS[1]}klines?symbol={cur}USDT&interval=8h&startTime={s}&endTime={end_ms}&limit=1000')
        if not r:
            break
        out += [(int(x[0]), float(x[1])) for x in r]
        if len(r) < 1000:
            break
        s = int(r[-1][0]) + 1
    return out


def perp_mark(cur):
    return float(_get(f'{HOSTS[2]}premiumIndex?symbol={cur}USDT')['markPrice'])


def funding_between(cur, a_ms, b_ms):
    r = _get(f'{HOSTS[2]}fundingRate?symbol={cur}USDT&startTime={a_ms + 1}&endTime={b_ms}&limit=1000')
    return [(int(x['fundingTime']), float(x['fundingRate']), float(x.get('markPrice') or 0)) for x in r]


# ── cálculos puros (con tests) ───────────────────────────────────────────────

def realized_vol(opens, a_ms, b_ms, days):
    """Anualizada con retornos de 8 h cuyo cierre cae en (a, b], igual que P39: RV² = Σr² · 365/días."""
    rs = [math.log(p1 / p0) for (t0, p0), (t1, p1) in zip(opens, opens[1:]) if a_ms < t1 <= b_ms]
    if len(rs) < days * 3 - 3:
        return None
    return math.sqrt(sum(r * r for r in rs) * 365.0 / days) * 100


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def b76(fwd, k, t_years, iv_pct):
    """Black-76 sin tasa: (delta call, delta put, vega USD por 1 punto de vol, por 1 unidad de subyacente)."""
    s = iv_pct / 100 * math.sqrt(t_years)
    d1 = (math.log(fwd / k) + 0.5 * s * s) / s
    vega = fwd * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) * math.sqrt(t_years) / 100
    return _ncdf(d1), _ncdf(d1) - 1, vega


def pick_expiry(expiries_ms, now_ms):
    best = None
    for e in sorted(set(expiries_ms)):
        d = (e - now_ms) / DAY_MS
        if EXP_MIN <= d <= EXP_MAX:
            key = (abs(d - EXP_TARGET), -d)
            if best is None or key < best[0]:
                best = (key, e)
    return None if best is None else best[1]


def deribit_fee(underlying_usd, option_usd, rate):
    return min(rate * underlying_usd, FEE_CAP * option_usd)


def straddle_payoff(settle, strike):
    return abs(settle - strike)


def proxy_vol(dvol, rv_fwd):
    iv = dvol / 100
    return (iv * iv - (rv_fwd / 100) ** 2) / (2 * iv) * 100 - PROXY_COST


# ── mercado ──────────────────────────────────────────────────────────────────

def atm_straddle(cur, now_ms):
    ins = deribit('get_instruments', f'currency={cur}&kind=option&expired=false')
    exp = pick_expiry([i['expiration_timestamp'] for i in ins], now_ms)
    if exp is None:
        raise RuntimeError('sin vencimiento en [20, 45] días')
    by_k = {}
    for i in ins:
        if i['expiration_timestamp'] == exp:
            by_k.setdefault(i['strike'], {})[i['option_type']] = i['instrument_name']
    pairs = {k: v for k, v in by_k.items() if 'call' in v and 'put' in v}
    probe = deribit('ticker', 'instrument_name=' + next(iter(pairs.values()))['call'])
    fwd = probe['underlying_price']
    k = min(pairs, key=lambda x: (abs(x - fwd), x))
    c = deribit('ticker', 'instrument_name=' + pairs[k]['call'])
    p = deribit('ticker', 'instrument_name=' + pairs[k]['put'])
    return dict(expiry=exp, days=(exp - now_ms) / DAY_MS, strike=k, call=pairs[k]['call'], put=pairs[k]['put'],
                fwd=c['underlying_price'], idx=c['index_price'], c=c, p=p)


def dvol_now(cur, now_ms):
    r = deribit('get_volatility_index_data', f'currency={cur}&start_timestamp={now_ms - 3 * 3600000}'
                f'&end_timestamp={now_ms}&resolution=60')['data']
    return r[-1][4] if r else None


def dvol_day_open(cur, day_ms):
    r = deribit('get_volatility_index_data', f'currency={cur}&start_timestamp={day_ms}'
                f'&end_timestamp={day_ms + DAY_MS}&resolution=1D')['data']
    for t, o, *_ in r:
        if int(t) == day_ms:
            return o
    return None


def delivery_price(cur, expiry_ms):
    day = dt.datetime.fromtimestamp(expiry_ms / 1000, dt.timezone.utc).date().isoformat()
    for x in deribit('get_delivery_prices', f'index_name={cur.lower()}_usd&count=10')['data']:
        if x['date'] == day:
            return x['delivery_price']
    return None


# ── libro ────────────────────────────────────────────────────────────────────

def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def run_diag(conn, cur, now_ms):
    try:
        s = atm_straddle(cur, now_ms)
        dv = dvol_now(cur, now_ms)
        c, p = s['c'], s['p']
        gap = dv - (c['bid_iv'] + p['bid_iv']) / 2 if dv and c['bid_iv'] and p['bid_iv'] else None
        conn.execute('INSERT INTO diag (ts_utc, ts_ms, cur, expiry_ms, days, strike, fwd, idx, c_bid_iv, c_ask_iv,'
                     ' c_mark_iv, p_bid_iv, p_ask_iv, p_mark_iv, dvol_now, gap_bid) VALUES '
                     '(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (_iso(now_ms), now_ms, cur, s['expiry'], s['days'], s['strike'], s['fwd'], s['idx'],
                      c['bid_iv'], c['ask_iv'], c['mark_iv'], p['bid_iv'], p['ask_iv'], p['mark_iv'], dv, gap))
        return s
    except Exception as e:
        conn.execute('INSERT INTO diag (ts_utc, ts_ms, cur, error) VALUES (?,?,?,?)', (_iso(now_ms), now_ms, cur,
                                                                                      repr(e)[:300]))
        return None
    finally:
        conn.commit()


def _iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec='seconds')


def rebalance(conn, tr, cur, now_ms, final=False):
    px = perp_mark(cur)
    fund = sum(r * tr['hedge_pos'] * (m or px) for _, r, m in funding_between(cur, tr['last_ms'], now_ms))
    pnl = tr['hedge_pos'] * (px - tr['hedge_px'])
    iv, mtm, new = None, None, 0.0
    if not final:
        c = deribit('ticker', 'instrument_name=' + tr['call'])
        p = deribit('ticker', 'instrument_name=' + tr['put'])
        iv = (c['mark_iv'] + p['mark_iv']) / 2
        t_y = max(tr['expiry_ms'] - now_ms, 3600000) / DAY_MS / 365
        dc, dp, _ = b76(c['underlying_price'], tr['strike'], t_y, iv)
        new = dc + dp                    # el straddle vendido tiene delta −(dc+dp) ⇒ perpetuo largo dc+dp
        mtm = tr['premium_usd'] - (c['mark_price'] + p['mark_price']) * c['index_price']
    traded = abs(new - tr['hedge_pos'])
    cost = traded * px * HEDGE_COST
    conn.execute('UPDATE trades SET hedge_pos=?, hedge_px=?, hedge_pnl=hedge_pnl+?, hedge_cost=hedge_cost+?,'
                 ' funding_paid=funding_paid+?, last_ms=?, runs=runs+1 WHERE id=?',
                 (new, px, pnl, cost, fund, now_ms, tr['id']))
    conn.execute('INSERT INTO hedge_log (trade_id, ts_ms, perp_px, iv, delta, new_pos, traded, cost, funding,'
                 ' mtm_usd) VALUES (?,?,?,?,?,?,?,?,?,?)',
                 (tr['id'], now_ms, px, iv, -new, new, traded, cost, fund, mtm))
    conn.commit()


def settle(conn, tr, cur, now_ms):
    s = delivery_price(cur, tr['expiry_ms'])
    if s is None:
        return False
    rebalance(conn, tr, cur, now_ms, final=True)
    tr = conn.execute('SELECT * FROM trades WHERE id=?', (tr['id'],)).fetchone()
    pay = straddle_payoff(s, tr['strike'])
    fee_out = deribit_fee(s, pay, FEE_OUT) if pay > 0 else 0.0
    pnl = (tr['premium_usd'] - tr['fee_in_usd'] - pay - fee_out + tr['hedge_pnl'] - tr['hedge_cost']
           - tr['funding_paid'])
    days = (tr['expiry_ms'] - tr['opened_ms']) / DAY_MS
    opens = spot_opens(cur, tr['opened_ms'] - DAY_MS, tr['expiry_ms'] + DAY_MS)
    rv = realized_vol(opens, tr['opened_ms'], tr['expiry_ms'], days)
    prx = proxy_vol(tr['dvol_open'], rv) if rv else None
    conn.execute('UPDATE trades SET status=?, settle_px=?, payoff_usd=?, fee_out_usd=?, pnl_usd=?, pnl_pct=?,'
                 ' pnl_vol=?, rv_fwd=?, proxy_vol=?, closed_ms=? WHERE id=?',
                 ('closed', s, pay, fee_out, pnl, pnl / tr['idx0'] * 100, pnl / tr['vega_usd'], rv, prx, now_ms,
                  tr['id']))
    conn.commit()
    return True


def maybe_open(conn, cur, now_ms, s):
    cycle = int((now_ms - ANCHOR.timestamp() * 1000) // (CYCLE_D * DAY_MS))
    if cycle < 0 or conn.execute('SELECT 1 FROM trades WHERE cur=? AND cycle=?', (cur, cycle)).fetchone():
        return
    day_ms = now_ms - now_ms % DAY_MS
    dvol0 = dvol_day_open(cur, day_ms)
    opens = spot_opens(cur, day_ms - (H + 1) * DAY_MS, day_ms + 1)
    rv = realized_vol(opens, day_ms - H * DAY_MS, day_ms, H)
    if dvol0 is None or rv is None or s is None:
        return                                       # sin dato: reintenta en la próxima corrida
    if dvol0 <= rv:
        conn.execute('INSERT INTO trades (cur, cycle, status, opened_ms, dvol_open, rv_prev, note) VALUES'
                     ' (?,?,?,?,?,?,?)', (cur, cycle, 'out', now_ms, dvol0, rv, 'DVOL <= realizada previa'))
        conn.commit()
        return
    c, p = s['c'], s['p']
    if not c.get('best_bid_price') or not p.get('best_bid_price'):
        return                                       # sin bid: reintenta
    idx = c['index_price']
    prem = (c['best_bid_price'] + p['best_bid_price']) * idx
    fee = sum(deribit_fee(idx, b * idx, FEE_IN) for b in (c['best_bid_price'], p['best_bid_price']))
    iv0 = (c['mark_iv'] + p['mark_iv']) / 2
    _, _, vega = b76(s['fwd'], s['strike'], s['days'] / 365, iv0)
    cur_id = conn.execute(
        'INSERT INTO trades (cur, cycle, status, opened_ms, dvol_open, rv_prev, expiry_ms, strike, call, put, c_bid,'
        ' p_bid, idx0, fwd0, iv_mark0, premium_usd, fee_in_usd, vega_usd, hedge_pos, hedge_px, last_ms) VALUES'
        ' (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (cur, cycle, 'open', now_ms, dvol0, rv, s['expiry'], s['strike'], s['call'], s['put'], c['best_bid_price'],
         p['best_bid_price'], idx, s['fwd'], iv0, prem, fee, 2 * vega, 0.0, perp_mark(cur), now_ms)).lastrowid
    conn.commit()
    rebalance(conn, conn.execute('SELECT * FROM trades WHERE id=?', (cur_id,)).fetchone(), cur, now_ms)


def run(conn, now_ms):
    for cur in CURS:
        s = run_diag(conn, cur, now_ms)
        try:
            tr = conn.execute("SELECT * FROM trades WHERE cur=? AND status='open'", (cur,)).fetchone()
            if tr is not None:
                if now_ms >= tr['expiry_ms']:
                    if not settle(conn, tr, cur, now_ms):
                        continue
                else:
                    rebalance(conn, tr, cur, now_ms)
                    continue
            maybe_open(conn, cur, now_ms, s)
        except Exception as e:
            conn.execute('INSERT INTO diag (ts_utc, ts_ms, cur, error) VALUES (?,?,?,?)',
                         (_iso(now_ms), now_ms, cur, 'libro: ' + repr(e)[:290]))
            conn.commit()


def _median(x):
    x = sorted(x)
    return None if not x else (x[len(x) // 2] if len(x) % 2 else (x[len(x) // 2 - 1] + x[len(x) // 2]) / 2)


def report(conn):
    print('P39b shadow de volatilidad (criterio docs/p39b_shadow_vol_criterio.md)')
    for cur in CURS:
        rows = conn.execute('SELECT gap_bid, c_ask_iv - c_bid_iv AS sc, p_ask_iv - p_bid_iv AS sp FROM diag '
                            'WHERE cur=? AND gap_bid IS NOT NULL', (cur,)).fetchall()
        err = conn.execute('SELECT COUNT(*) FROM diag WHERE cur=? AND error IS NOT NULL', (cur,)).fetchone()[0]
        g = _median([r['gap_bid'] for r in rows])
        sp = _median([(r['sc'] + r['sp']) / 2 for r in rows])
        print(f"  {cur} diagnóstico: {len(rows)} días, brecha DVOL − IV bid mediana "
              f"{'—' if g is None else f'{g:+.2f}'} pts (umbral 1,5), spread bid-ask IV mediano "
              f"{'—' if sp is None else f'{sp:.2f}'} pts, errores {err}")
    tr = conn.execute("SELECT * FROM trades ORDER BY id").fetchall()
    for t in tr:
        if t['status'] == 'out':
            print(f"  #{t['id']} {t['cur']} ciclo {t['cycle']}: afuera (DVOL {t['dvol_open']:.1f} <= RV {t['rv_prev']:.1f})")
        elif t['status'] == 'open':
            print(f"  #{t['id']} {t['cur']} ciclo {t['cycle']}: ABIERTA {t['call']}/{t['put']} prima "
                  f"${t['premium_usd']:.0f} cobertura {t['hedge_pos']:+.2f} ({t['runs']} rebalanceos)")
        else:
            print(f"  #{t['id']} {t['cur']} ciclo {t['cycle']}: cerrada {t['pnl_vol']:+.2f} pts real vs proxy "
                  f"{t['proxy_vol'] if t['proxy_vol'] is None else round(t['proxy_vol'], 2)}  ${t['pnl_usd']:+.0f}")
    closed = [t for t in tr if t['status'] == 'closed']
    if closed:
        mv = sum(t['pnl_vol'] for t in closed) / len(closed)
        mu = sum(t['pnl_usd'] / t['idx0'] for t in closed) / len(closed) * 100
        dif = [t['pnl_vol'] - t['proxy_vol'] for t in closed if t['proxy_vol'] is not None]
        print(f"  cerradas n={len(closed)} (decide a n>=18, ~13-nov-2027): media {mv:+.2f} pts, {mu:+.3f}% del "
              f"índice; real − proxy {sum(dif) / len(dif) if dif else float('nan'):+.2f} pts (umbral −2)")


def default_db():
    return os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state', 'vol_shadow.db')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true')
    ap.add_argument('--db', default=default_db())
    a = ap.parse_args()
    conn = connect(a.db)
    if not a.report:
        run(conn, int(time.time() * 1000))
    report(conn)


if __name__ == '__main__':
    main()
