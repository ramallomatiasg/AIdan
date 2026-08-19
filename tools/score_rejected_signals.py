"""
score_rejected_signals.py — SHADOW BOOK scorer (v3.58.2, PRFS).

Completa el outcome forward de cada fila de `rejected_signals` (la unica tabla que
este script escribe — es SU tabla de instrumentacion) y reporta:

  1. reason='atr_floor' (sin direccion — el gate skipea el scan entero):
     movimiento ABSOLUTO de la ventana rechazada en el horizonte (45 min).
     CRITERIO PRE-DECLARADO (19-ago): un ganador de m15 recorre ~7,8p en promedio.
       - mediana de abs_move < 7,8p  => el gate no costo nada: en esas ventanas no
         habia recorrido para pagar un trade, en NINGUNA direccion.
       - mediana >= 7,8p             => el gate esta bloqueando ventanas con energia;
         mirar net_drift antes de concluir (rango ancho + drift ~0 = chop violento,
         que sigue siendo lo que el gate debe filtrar).

  2. reasons direccionales ('counter_both', 'active_opposite' — señal formada):
     excursion favorable vs adversa segun el lado rechazado.
       saved  = adv >= fav              (el rechazo evito un trade que iba en contra)
       missed = fav >= 7,8p y fav > adv (habia recorrido a favor y se dejo pasar)
     SAVE-TO-MISS = saved/missed. Referencia externa (arXiv 2607.02830): filtros
     sanos reportan >= 3,7:1 conservador. < 1,0 con n>=25 = el filtro bloquea mas
     ganadores que perdedores => revisarlo. NO actuar con n<25 (gate del proyecto).

Metodologia: excursion sobre velas M5 de MT5, SIN re-simular SL/TP (doctrina del
proyecto, misma que score_d1_shadow.py). Timestamps: created_at esta en hora AR;
las velas MT5 en hora del server — el offset se deriva del tick en vivo (mismo
patron que get_daily_pnl, robusto a DST del broker).

Requiere MT5. `--dry-run` no escribe outcomes.
"""
import argparse
import os
import sqlite3
import statistics
import sys
import time as _time
from datetime import datetime, timedelta

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
PIP = 0.0001
WINNER_PIPS = 7.8   # ganador medio de m15 (pre-declarado, no ajustar sobre la muestra)
MIN_N = 25          # gate del proyecto


def _parse_ar(ts):
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(str(ts).split('+')[0].strip(), fmt)
        except ValueError:
            continue
    return None


def score_pending(dry_run=False):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        return 0

    tick = mt5.symbol_info_tick("EURUSD")
    if not tick or not getattr(tick, 'time', 0):
        print("Sin tick — no se puede derivar el offset del server. Abortando scoring.")
        mt5.shutdown()
        return 0
    offset_s = round((tick.time - _time.time()) / 1800.0) * 1800  # server - UTC

    conn = sqlite3.connect(DB, timeout=15.0)
    rows = conn.execute("""
        SELECT id, direction, price, horizon_min, created_at
        FROM rejected_signals WHERE scored_at IS NULL""").fetchall()

    scored = 0
    for rid, direction, price, horizon, created_at in rows:
        ar_dt = _parse_ar(created_at)
        if ar_dt is None or not price:
            continue
        horizon = horizon or 45
        # AR = UTC-3; server = UTC + offset
        utc_start = ar_dt + timedelta(hours=3)
        if datetime.utcnow() < utc_start + timedelta(minutes=horizon + 5):
            continue  # horizonte no vencido
        srv_start = utc_start + timedelta(seconds=offset_s)
        srv_end = srv_start + timedelta(minutes=horizon)
        rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, srv_start, srv_end)
        if rates is None or len(rates) == 0:
            continue  # finde/feriado o historia no bajada aun: queda pendiente
        hi = max(float(r['high']) for r in rates)
        lo = min(float(r['low']) for r in rates)
        close = float(rates[-1]['close'])
        abs_move = (hi - lo) / PIP
        net = (close - price) / PIP
        if direction == 'CALL':
            fav, adv = (hi - price) / PIP, (price - lo) / PIP
            net_dir = net
        elif direction == 'PUT':
            fav, adv = (price - lo) / PIP, (hi - price) / PIP
            net_dir = -net
        else:
            fav = adv = None
            net_dir = net
        if not dry_run:
            conn.execute("""UPDATE rejected_signals
                SET fav_pips=?, adv_pips=?, abs_move_pips=?, net_drift_pips=?,
                    scored_at=datetime('now')
                WHERE id=?""",
                (round(fav, 1) if fav is not None else None,
                 round(adv, 1) if adv is not None else None,
                 round(abs_move, 1), round(net_dir, 1), rid))
        scored += 1
    if not dry_run:
        conn.commit()
    conn.close()
    mt5.shutdown()
    return scored


def report():
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    total = conn.execute("SELECT COUNT(*) FROM rejected_signals").fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM rejected_signals WHERE scored_at IS NULL").fetchone()[0]
    print(f"\nSHADOW BOOK — {total} rechazos registrados, {pending} sin outcome todavia")
    if total == 0:
        print("(la tabla se puebla desde v3.58.2: gate de ATR de m15 + counter-both + "
              "active_opposite. 0 filas + dias de chop = hook muerto -> revisar WARNING "
              "'shadow book' / 'log_rejected_signal FAILED' en aidan.log)")
        return

    # 1) atr_floor — sin direccion
    rows = conn.execute("""SELECT abs_move_pips, net_drift_pips FROM rejected_signals
        WHERE reason='atr_floor' AND scored_at IS NOT NULL""").fetchall()
    if rows:
        moves = [r[0] for r in rows]
        drifts = [abs(r[1]) for r in rows if r[1] is not None]
        med = statistics.median(moves)
        pct_energy = 100.0 * sum(1 for m in moves if m >= WINNER_PIPS) / len(moves)
        print(f"\n[atr_floor] n={len(rows)} ventanas skipeadas con outcome")
        line = (f"  abs_move: mediana {med:.1f}p | >= {WINNER_PIPS}p (recorrido de "
                f"ganador): {pct_energy:.0f}%")
        if drifts:
            line += f" | drift mediano {statistics.median(drifts):.1f}p"
        print(line)
        if len(rows) < MIN_N:
            print(f"  -> n<{MIN_N}: sin veredicto (no concluir).")
        elif med < WINNER_PIPS:
            print(f"  -> mediana {med:.1f}p < {WINNER_PIPS}p: en las ventanas skipeadas no "
                  f"habia recorrido para pagar un trade. El gate NO esta costando nada.")
        else:
            print(f"  -> mediana {med:.1f}p >= {WINNER_PIPS}p: las ventanas skipeadas tienen "
                  f"energia. Mirar drift: rango ancho + drift ~0 = chop violento (el gate "
                  f"igual hace su trabajo); drift alto = el gate bloquea tendencia (problema).")

    # 2) direccionales — save-to-miss
    for reason in ('counter_both', 'active_opposite'):
        rows = conn.execute("""SELECT fav_pips, adv_pips FROM rejected_signals
            WHERE reason=? AND scored_at IS NOT NULL AND fav_pips IS NOT NULL""",
            (reason,)).fetchall()
        if not rows:
            continue
        saved = sum(1 for f, a in rows if a >= f)
        missed = sum(1 for f, a in rows if f >= WINNER_PIPS and f > a)
        ratio = 'inf' if missed == 0 else f"{saved / missed:.1f}"
        print(f"\n[{reason}] n={len(rows)} señales rechazadas con outcome")
        print(f"  fav mediana {statistics.median([r[0] for r in rows]):.1f}p | "
              f"adv mediana {statistics.median([r[1] for r in rows]):.1f}p")
        print(f"  saved={saved} missed={missed} -> save-to-miss = {ratio}:1")
        if len(rows) < MIN_N:
            print(f"  -> n<{MIN_N}: sin veredicto.")
        elif missed and saved / missed < 1.0:
            print(f"  -> ratio < 1: este filtro bloquea mas ganadores que perdedores. "
                  f"Revisarlo (con el gate de significancia, no de una).")
        else:
            print(f"  -> el filtro se paga (referencia externa: >= 3,7:1 es un filtro sano).")
    conn.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='no escribe outcomes')
    args = ap.parse_args()
    n = score_pending(dry_run=args.dry_run)
    suffix = ' (dry-run, sin escribir)' if args.dry_run else ''
    print(f"Outcomes calculados en esta corrida: {n}{suffix}")
    report()
