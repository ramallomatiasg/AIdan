# -*- coding: utf-8 -*-
"""
measure_entry_suspects.py — Medidor READ-ONLY de los 2 sospechosos de calidad de entrada
(forense 10 Jun 2026). NO escribe a la DB, NO cambia comportamiento. Solo imprime un reporte.

Sospechoso A — RE-ENTRADA TRAS PERDIDA (cooldown):
    ¿Los trades abiertos a los pocos minutos de una perdida rinden peor?
    Fuente: historial de DEALS de MT5 (verdad del broker, timestamps exactos).
    Los gaps son RELATIVOS (cierre->apertura) => inmune a problemas de timezone.

Sospechoso B — BIAS MACRO RESAGADO:
    ¿Los trades que entraron con htf_bias contradicho por la deriva REAL de las
    2h previas (bias 'bullish' con el precio cayendo fuerte, o viceversa) rinden peor?
    Bias por trade: trade_archive.htf_bias (solo M5/news/smc historico; m15/h1
    quedaron vacios por el bug del doble-encode arreglado en v3.40.11).
    Deriva previa: candles M5 del broker alineadas a los timestamps de los deals
    (misma convencion de epoch en ambos lados => alineacion consistente; la deriva
    se mide sobre ~2h, robusta a +/-1 vela).

Veredicto por el gate de la casa (significance.verify_finding): binomial one-sided
+ Wilson CI 95%. Default = RUIDO si n<25 o el CI cruza el baseline.

CAVEAT GRANDE (imprimido tambien al final): la muestra es la pila historica SUCIA
(mezcla de versiones v3.6->v3.40, phantom-pnl pre-v3.40.0, regimenes distintos).
Un hallazgo aca es INPUT para el checkpoint, NO un auto-aplicar.
"""
import os
import sys
import sqlite3
import re
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAGIC_NUMBER = 20260402
DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
SYMBOL = 'EURUSD'
PIP = 0.0001

# Umbrales de medicion
COOLDOWN_BUCKETS_MIN = [2, 5, 10, 15]   # re-entrada <= X min tras una perdida
DRIFT_WINDOW_MIN = 120                   # deriva previa: 2 horas
DRIFT_STRONG_PIPS = 10.0                 # |deriva| >= 10p = senal direccional fuerte


def pair_positions(mt5):
    """Deals del broker -> posiciones cerradas {sid, dir, open_ts, close_ts, pnl}."""
    deals = mt5.history_deals_get(datetime(2026, 4, 1), datetime.now() + timedelta(days=2))
    if deals is None:
        return []
    by_pos = defaultdict(list)
    for d in deals:
        if d.magic == MAGIC_NUMBER and d.symbol == SYMBOL:
            by_pos[d.position_id].append(d)
    positions = []
    for pid, ds in by_pos.items():
        entries = [d for d in ds if d.entry == 0]   # DEAL_ENTRY_IN
        exits = [d for d in ds if d.entry == 1]     # DEAL_ENTRY_OUT
        if not entries or not exits:
            continue  # posicion aun abierta o data incompleta
        e = entries[0]
        sid = None
        m = re.search(r'AIdan #(\d+)', e.comment or '')
        if m:
            sid = int(m.group(1))
        pnl = sum(d.profit + d.swap + d.commission for d in ds)
        positions.append({
            'sid': sid,
            'direction': 'CALL' if e.type == 0 else 'PUT',
            'open_ts': e.time,
            'close_ts': max(d.time for d in exits),
            'pnl': round(pnl, 2),
            'entry_price': e.price,
        })
    positions.sort(key=lambda p: p['open_ts'])
    return positions


def fmt_stats(subset):
    n = len(subset)
    if n == 0:
        return 'n=0', 0, 0
    w = sum(1 for p in subset if p['pnl'] > 0)
    pnl = round(sum(p['pnl'] for p in subset), 2)
    return f"n={n:3d}  WR={round(100*w/n):3d}%  PnL={pnl:+8.2f}", n, w


def gate(label, n, wins, baseline):
    """Pasa el hallazgo por el gate adversarial de la casa."""
    try:
        from src.optimizer.significance import verify_finding
        r = verify_finding(n, wins, baseline_wr=baseline, direction='worse')
        return (f"    gate[{label}]: p={r.p_value:.3f} CI=[{r.ci_low:.2f},{r.ci_high:.2f}] "
                f"vs base {baseline:.2f} -> {'SIGNIFICATIVO' if r.significant else 'RUIDO'} ({r.reason})")
    except Exception as ex:
        return f"    gate[{label}]: error {ex}"


def main():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print('MetaTrader5 package no disponible'); return
    if not mt5.initialize():
        print(f'No pude attachear al terminal MT5: {mt5.last_error()}'); return
    try:
        positions = pair_positions(mt5)
        print(f'Posiciones cerradas (deals broker, magic AIdan): {len(positions)}')
        if len(positions) < 30:
            print('Muestra demasiado chica para medir nada. Abortando.'); return
        line, n_all, w_all = fmt_stats(positions)
        overall_wr = w_all / n_all
        print(f'UNIVERSO: {line}  (baseline interno {overall_wr:.3f})')

        # ── Sospechoso A: re-entrada tras perdida ─────────────────────────────
        print('\n=== SOSPECHOSO A: re-entrada tras perdida (cooldown) ===')
        loss_closes = sorted(p['close_ts'] for p in positions if p['pnl'] < 0)
        import bisect
        def mins_since_prior_loss(p):
            i = bisect.bisect_left(loss_closes, p['open_ts'])
            if i == 0:
                return None
            return (p['open_ts'] - loss_closes[i - 1]) / 60.0

        gaps = [(p, mins_since_prior_loss(p)) for p in positions]
        for bmax in COOLDOWN_BUCKETS_MIN:
            sub = [p for p, g in gaps if g is not None and g <= bmax]
            line, n, w = fmt_stats(sub)
            print(f'  abierto <= {bmax:2d}min tras perdida: {line}')
            if n >= 10:
                print(gate(f'<={bmax}min', n, w, overall_wr))
        rest = [p for p, g in gaps if g is None or g > COOLDOWN_BUCKETS_MIN[-1]]
        line, _, _ = fmt_stats(rest)
        print(f'  resto (>{COOLDOWN_BUCKETS_MIN[-1]}min o sin perdida previa): {line}')

        # ── Sospechoso B: bias macro resagado ────────────────────────────────
        print('\n=== SOSPECHOSO B: htf_bias resagado vs deriva real previa (2h) ===')
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        bias_by_sid = {}
        for sid, hb in conn.execute(
                "SELECT strategy_id, htf_bias FROM trade_archive "
                "WHERE htf_bias IN ('bullish','bearish')"):
            bias_by_sid[sid] = hb
        conn.close()
        with_bias = [p for p in positions if p['sid'] in bias_by_sid]
        print(f'  trades con htf_bias en archive: {len(with_bias)} '
              f'(m15/h1 historicos NO tienen bias por el bug del doble-encode)')

        def prior_drift_pips(p):
            t_open = datetime.utcfromtimestamp(p['open_ts'])
            rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5,
                                         t_open - timedelta(minutes=DRIFT_WINDOW_MIN + 15),
                                         t_open - timedelta(minutes=1))
            if rates is None or len(rates) < 6:
                return None
            return (rates[-1]['close'] - rates[0]['close']) / PIP

        stale, fresh, flat, nodata = [], [], [], 0
        for p in with_bias:
            d = prior_drift_pips(p)
            if d is None:
                nodata += 1
                continue
            bias = bias_by_sid[p['sid']]
            if abs(d) < DRIFT_STRONG_PIPS:
                flat.append(p)
            elif (bias == 'bullish' and d <= -DRIFT_STRONG_PIPS) or \
                 (bias == 'bearish' and d >= DRIFT_STRONG_PIPS):
                stale.append(p)   # bias contradicho por la deriva real reciente
            else:
                fresh.append(p)   # bias confirmado por la deriva
        print(f'  (sin candles para {nodata} trades viejos — fuera del historial M5 del terminal)' if nodata else '', end='')
        if nodata: print()
        for name, sub in (('BIAS STALE (deriva 2h lo contradice >=10p)', stale),
                          ('BIAS FRESH (deriva 2h lo confirma >=10p) ', fresh),
                          ('deriva plana (<10p, bias no testeado)    ', flat)):
            line, n, w = fmt_stats(sub)
            print(f'  {name}: {line}')
            if name.startswith('BIAS STALE') and n >= 10:
                print(gate('stale', n, w, overall_wr))

        # ── Sospechoso C: ¿entra TARDE o entra MAL? (delay señal→fill + drift de precio) ──
        print('\n=== SOSPECHOSO C: ¿tarde o mal? (delay senal->fill y precio corrido al fill) ===')
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        meta = {}
        for tbl, key in (('trade_archive', 'strategy_id'), ('auto_strategies', 'id')):
            try:
                for sid, ca, ep in conn.execute(f"SELECT {key}, created_at, entry_price FROM {tbl} WHERE created_at IS NOT NULL"):
                    if sid is not None and sid not in meta:
                        meta[sid] = (ca, ep)
            except Exception:
                pass
        conn.close()
        import time as _t
        from datetime import datetime as _dt2
        tick = None
        try:
            import MetaTrader5 as _mt5b
            tick = _mt5b.symbol_info_tick(SYMBOL)
        except Exception:
            pass
        offset_s = round(((tick.time if tick else 0) - _t.time()) / 1800.0) * 1800 if tick else 6 * 1800
        delays, drifts = [], []
        for p in positions:
            m = meta.get(p['sid'])
            if not m or not m[0]:
                continue
            try:
                c0 = _dt2.strptime(str(m[0]).split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
            except Exception:
                continue
            fill_ar = _dt2.utcfromtimestamp(p['open_ts'] - offset_s) - timedelta(hours=3)
            delay = (fill_ar - c0).total_seconds() / 60.0
            if -3 <= delay <= 300:
                delays.append((p, delay))
            if m[1]:
                # drift>0 = fill MAS ALLA del precio de la senal en la direccion del trade
                # (CALL llenado mas arriba / PUT mas abajo) = persiguio el precio.
                drift = (p['entry_price'] - m[1]) / PIP * (1 if p['direction'] == 'CALL' else -1)
                if abs(drift) <= 50:
                    drifts.append((p, drift))
        print(f'  (con metadata en DB: delay={len(delays)}, drift={len(drifts)} de {len(positions)} posiciones)')
        print('  -- POR DELAY senal->fill --')
        for lo, hi, lbl in ((-3, 1, 'fill inmediato (<1min)'), (1, 5, '1-5min'), (5, 15, '5-15min'), (15, 9e9, '>15min (retry tardio)')):
            sub = [p for p, v in delays if lo <= v < hi]
            line, n, w = fmt_stats(sub)
            print(f'  {lbl:24s}: {line}')
            if n >= 10 and lo >= 1:
                print(gate(f'delay{lbl}', n, w, overall_wr))
        print('  -- POR DRIFT de precio al fill --')
        for lo, hi, lbl in ((-9e9, -3, 'mejor precio (<-3p)'), (-3, 3, 'al precio planeado'), (3, 9e9, 'PERSIGUIO (>+3p)')):
            sub = [p for p, v in drifts if lo <= v < hi]
            line, n, w = fmt_stats(sub)
            print(f'  {lbl:24s}: {line}')
            if n >= 10 and lbl != 'al precio planeado':
                print(gate(f'drift{lbl}', n, w, overall_wr))

        print('\n--- CAVEATS (leer antes de actuar) ---')
        print('1. Muestra historica SUCIA (mezcla v3.6->v3.40, phantom-pnl viejo, regimenes).')
        print('   Esto es INPUT de checkpoint, NO un auto-aplicar.')
        print('2. Sospechoso B solo cubre M5/news/smc (m15/h1 sin bias historico por el bug).')
        print('3. Default de la casa: RUIDO salvo que el gate diga SIGNIFICATIVO.')
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
