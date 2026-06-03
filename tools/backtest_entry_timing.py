"""
backtest_entry_timing.py — ¿Esperar la confirmacion (no entrar sobre la vela de
retroceso) rescata los trades del tipo #565?

Idea (del user, 3 Jun): cuando AIdan entra con la direccion correcta PERO sobre
una vela de retroceso (ej PUT entrando sobre vela verde de rebote), suele
stopearse antes de que el movimiento bueno llegue. Hipotesis: si en vez de
entrar ahi, ESPERA una vela de confirmacion (que cierre en la direccion del
trade) y entra desde mejor precio, mejora el resultado.

Metodo:
- Para cada trade del archive: traer velas M5 de MT5 alrededor del entry.
- Anclar la vela de entrada por entry_price (cae dentro de [low,high]) — robusto
  ante el offset de timezone del server MT5.
- Clasificar "bounce entry": la vela de entrada va EN CONTRA de la direccion.
- Simular 2 escenarios con las MISMAS distancias SL/TP (en pips):
  A) ACTUAL: entrar en la vela de entrada.
  B) WAIT: desde la vela de entrada, esperar la 1ra vela que CONFIRMA direccion
     (cierra en la direccion del trade), entrar en su close.
- Comparar A vs B SOLO sobre los bounce-entries (donde la regla actuaria).

Caveats: backtest infla ~20-30% (sin spread/slippage variable). Sirve para
señal RELATIVA (¿ayuda o no?), no para PnL absoluto. Si la muestra de bounce-
entries es chica, el resultado va al gate de significancia igual.
"""
import os, sys, argparse
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PIP = 0.0001
H = 18  # velas forward a simular (~90 min M5)


def connect_mt5():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    return mt5


def fetch_window(mt5, center_dt_utc, hours_back=2, hours_fwd=4):
    """Trae velas M5 en una ventana alrededor de center (en UTC aprox)."""
    frm = center_dt_utc - timedelta(hours=hours_back)
    to = center_dt_utc + timedelta(hours=hours_fwd)
    rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, frm, to)
    if rates is None or len(rates) == 0:
        return []
    return [{'o': float(r['open']), 'h': float(r['high']), 'l': float(r['low']),
             'c': float(r['close']), 't': int(r['time'])} for r in rates]


def find_entry_idx(candles, entry_price, expected_t):
    """Vela de entrada = la que contiene entry_price en [l,h] y esta mas cerca
    en tiempo de expected_t (unix). Robusto ante offset de TZ del server."""
    best, best_d = None, None
    for i, c in enumerate(candles):
        if c['l'] - 0.5 * PIP <= entry_price <= c['h'] + 0.5 * PIP:
            d = abs(c['t'] - expected_t)
            if best_d is None or d < best_d:
                best, best_d = i, d
    return best


def sim_forward(candles, start_idx, entry, direction, sl_pips, tp_pips):
    """Walk forward desde start_idx+1. Devuelve pips (TP=+tp, SL=-sl, expiry=close-entry)."""
    sl = entry + sl_pips * PIP if direction == 'PUT' else entry - sl_pips * PIP
    tp = entry - tp_pips * PIP if direction == 'PUT' else entry + tp_pips * PIP
    end = min(start_idx + 1 + H, len(candles))
    for i in range(start_idx + 1, end):
        c = candles[i]
        if direction == 'PUT':
            if c['h'] >= sl: return -sl_pips, 'SL'
            if c['l'] <= tp: return tp_pips, 'TP'
        else:
            if c['l'] <= sl: return -sl_pips, 'SL'
            if c['h'] >= tp: return tp_pips, 'TP'
    # expiry: exit al close de la ultima vela del horizonte
    last = candles[end - 1]['c'] if end > start_idx + 1 else entry
    pips = (entry - last) / PIP if direction == 'PUT' else (last - entry) / PIP
    return round(pips, 1), 'expiry'


def confirms(candle, direction):
    """La vela confirma la direccion del trade (cierra a favor)."""
    return candle['c'] < candle['o'] if direction == 'PUT' else candle['c'] > candle['o']


def sim_limit_pullback(candles, ei, direction, sl_pips, tp_pips, max_wait=5):
    """Variante 'entrar desde mejor precio': pone orden limite en el extremo de la
    vela de rebote (PUT: short desde el high; CALL: long desde el low). Si el precio
    llega ahi en <=max_wait velas, entra; si no, skip (None)."""
    limit = candles[ei]['h'] if direction == 'PUT' else candles[ei]['l']
    for j in range(ei + 1, min(ei + 1 + max_wait, len(candles))):
        cj = candles[j]
        hit = cj['h'] >= limit if direction == 'PUT' else cj['l'] <= limit
        if hit:
            return sim_forward(candles, j, limit, direction, sl_pips, tp_pips)[0]
    return None  # nunca volvio al nivel -> trade evitado


def era_of(created):
    """Bucket de epoca por fecha (para detectar contaminacion cross-version)."""
    d = str(created)[:10]
    if d < '2026-05-01':
        return '1_abril'
    if d < '2026-05-20':
        return '2_may1-19'
    if d < '2026-05-29':
        return '3_may20-28'
    return '4_post-limpieza'  # gates off + ML off (v3.38.x)


def is_bounce(entry_candle, direction):
    """Vela de entrada va EN CONTRA de la direccion (retroceso)."""
    return entry_candle['c'] > entry_candle['o'] if direction == 'PUT' else entry_candle['c'] < entry_candle['o']


def main():
    import sqlite3
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    from src.common.db import DB_PATH
    mt5 = connect_mt5()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id, created_at, direction, entry_price, sl_pips, tp_pips, mt5_pnl
           FROM trade_archive
           WHERE mt5_pnl IS NOT NULL AND entry_price>0 AND sl_pips>0 AND tp_pips>0
           ORDER BY created_at""")
    rows = c.fetchall()
    conn.close()
    if args.limit:
        rows = rows[-args.limit:]

    # recolectar por trade: (era, is_bounce, actual, wait, limit)
    recs = []
    nonbounce = []
    no_data = 0
    for tid, created, direction, entry, slp, tpp, pnl in rows:
        try:
            dt_ar = datetime.strptime(str(created).split('.')[0], '%Y-%m-%d %H:%M:%S')
            dt_utc = dt_ar + timedelta(hours=3)
        except Exception:
            continue
        candles = fetch_window(mt5, dt_utc)
        if len(candles) < 5:
            no_data += 1; continue
        ei = find_entry_idx(candles, entry, int(dt_utc.timestamp()))
        if ei is None or ei >= len(candles) - 2:
            no_data += 1; continue
        ec = candles[ei]
        a_pips, _ = sim_forward(candles, ei, entry, direction, slp, tpp)
        era = era_of(created)
        if is_bounce(ec, direction):
            # WAIT confirmacion
            wi = None
            for j in range(ei + 1, min(ei + 6, len(candles))):
                if confirms(candles[j], direction):
                    wi = j; break
            w_pips = sim_forward(candles, wi, candles[wi]['c'], direction, slp, tpp)[0] if (wi is not None and wi < len(candles) - 2) else None
            # LIMIT pullback (entrar desde mejor precio)
            l_pips = sim_limit_pullback(candles, ei, direction, slp, tpp)
            recs.append({'era': era, 'bounce': True, 'actual': a_pips, 'wait': w_pips, 'limit': l_pips})
        else:
            recs.append({'era': era, 'bounce': False, 'actual': a_pips})
            nonbounce.append(a_pips)

    def stats(lst):
        v = [x for x in lst if x is not None]
        if not v: return (0, 0, 0, 0)
        n = len(v); wins = sum(1 for x in v if x > 0)
        return (n, wins / n * 100, sum(v), sum(v) / n)

    bounce = [r for r in recs if r['bounce']]
    print(f"\n{'='*64}\nBACKTEST entry-timing — contaminacion + variantes de espera\n{'='*64}")
    print(f"Trades procesados: {len(rows)} | sin data MT5: {no_data}\n")

    # 1) Bounce vs non-bounce GLOBAL
    nb = stats(nonbounce); a = stats([r['actual'] for r in bounce])
    print("GLOBAL:")
    print(f"  Non-bounce: n={nb[0]} WR {nb[1]:.0f}% avg {nb[3]:+.2f}p")
    print(f"  Bounce:     n={a[0]} WR {a[1]:.0f}% avg {a[3]:+.2f}p\n")

    # 2) POR EPOCA (clave: detectar contaminacion cross-version)
    print("POR EPOCA (bounce vs non-bounce) — si el efecto se sostiene post-limpieza, NO es artefacto:")
    print(f"  {'epoca':<18}{'NB n':>5}{'NB WR':>7}{'NB avg':>8}  |{'B n':>5}{'B WR':>7}{'B avg':>8}")
    for era in ['1_abril', '2_may1-19', '3_may20-28', '4_post-limpieza']:
        nbs = stats([r['actual'] for r in recs if r['era'] == era and not r['bounce']])
        bs = stats([r['actual'] for r in recs if r['era'] == era and r['bounce']])
        print(f"  {era:<18}{nbs[0]:>5}{nbs[1]:>6.0f}%{nbs[3]:>+8.2f}  |{bs[0]:>5}{bs[1]:>6.0f}%{bs[3]:>+8.2f}")

    # 3) VARIANTES sobre bounce-entries
    print("\nVARIANTES sobre bounce-entries (que hacer con ellas):")
    print(f"  A) Entrar igual (actual):       n={a[0]} WR {a[1]:.0f}% avg {a[3]:+.2f}p  total {a[2]:+.1f}p")
    w = stats([r['wait'] for r in bounce]); w_skip = sum(1 for r in bounce if r['wait'] is None)
    print(f"  B) Esperar confirmacion:        n={w[0]} WR {w[1]:.0f}% avg {w[3]:+.2f}p  total {w[2]:+.1f}p  (+{w_skip} evitados)")
    l = stats([r['limit'] for r in bounce]); l_skip = sum(1 for r in bounce if r['limit'] is None)
    print(f"  C) Entrar desde mejor precio:   n={l[0]} WR {l[1]:.0f}% avg {l[3]:+.2f}p  total {l[2]:+.1f}p  (+{l_skip} evitados)")
    print(f"  D) Saltarlos (skip):            n=0  -> evita {a[2]:+.1f}p de perdida")
    mt5.shutdown()


if __name__ == '__main__':
    main()
