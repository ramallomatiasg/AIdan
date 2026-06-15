# -*- coding: utf-8 -*-
"""
measure_streak_recency.py — Medidor READ-ONLY del frente RACHA / RECENCIA.
Generaliza el cooldown <=5min post-perdida (YA activado, 24% WR conocido) hacia
3 dimensiones DISTINTAS:

  (a) PROFUNDIDAD de racha perdedora INMEDIATAMENTE previa (0,1,2,3,4+ perdidas
      seguidas justo antes del open). ¿La 3ra perdida seguida predice la 4ta?
  (b) MINUTOS desde el ULTIMO trade (cualquier resultado) -> buckets.
  (c) MINUTOS desde la ultima GANANCIA -> buckets. ¿Operar lejos de la ultima
      ganancia es malo (sequia de wins)?

Fuente: DEALS del broker (verdad), pareados por position_id. Magic AIdan.
Gate de la casa: significance.verify_finding(n, wins, baseline_wr=WR_universo).
Default = RUIDO si n<25 o el CI 95% cruza el baseline.

REGLA CRITICA (leccion 12 Jun): no se usa NINGUNA vela para clasificar (todo es
sobre la secuencia de resultados/timestamps del broker) => no hay riesgo de
lookahead. NO escribe a la DB.
"""
import os
import sys
import re
import bisect
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAGIC_NUMBER = 20260402
DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
SYMBOL = 'EURUSD'


def pair_positions(mt5):
    """Deals del broker -> posiciones cerradas, ordenadas por open_ts."""
    deals = mt5.history_deals_get(datetime(2026, 4, 1), datetime.now() + timedelta(days=2))
    if deals is None:
        return []
    by_pos = defaultdict(list)
    for d in deals:
        if d.magic == MAGIC_NUMBER and d.symbol == SYMBOL:
            by_pos[d.position_id].append(d)
    positions = []
    for pid, ds in by_pos.items():
        entries = [d for d in ds if d.entry == 0]
        exits = [d for d in ds if d.entry == 1]
        if not entries or not exits:
            continue
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
        })
    positions.sort(key=lambda p: p['open_ts'])
    return positions


def fmt_stats(subset):
    n = len(subset)
    if n == 0:
        return 'n=  0  WR=  -  PnL=   +0.00', 0, 0
    w = sum(1 for p in subset if p['pnl'] > 0)
    pnl = round(sum(p['pnl'] for p in subset), 2)
    return f"n={n:3d}  WR={round(100*w/n):3d}%  PnL={pnl:+8.2f}", n, w


def gate(n, wins, baseline):
    try:
        from src.optimizer.significance import verify_finding
        r = verify_finding(n, wins, baseline_wr=baseline, direction='auto')
        tag = 'SIGNIFICATIVO' if r.significant else 'RUIDO'
        return (f"    gate: p={r.p_value:.3f} CI=[{r.ci_low:.2f},{r.ci_high:.2f}] "
                f"({r.direction}) vs base {baseline:.2f} -> {tag}")
    except Exception as ex:
        return f"    gate: error {ex}"


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
            print('Muestra demasiado chica. Abortando.'); return
        line, n_all, w_all = fmt_stats(positions)
        baseline = w_all / n_all
        print(f'UNIVERSO: {line}  (baseline WR universo {baseline:.4f})')

        # Pre-computar, en orden temporal, el estado previo al open de cada pos.
        # streak_prior = nro de PERDIDAS consecutivas justo antes (cerradas antes del open).
        # Para respetar causalidad usamos close_ts de las posiciones anteriores;
        # una pos cuenta como "previa" si cerro antes de que esta abriera.
        closes_sorted = sorted(positions, key=lambda p: p['close_ts'])

        # Para cada posicion, secuencia de resultados de las posiciones YA CERRADAS
        # al momento de su open_ts. Recorremos en orden de open y mantenemos
        # un puntero a las cerradas.
        # Construimos lista (close_ts, pnl) ordenada por close_ts.
        closed_seq = [(p['close_ts'], p['pnl']) for p in closes_sorted]
        close_ts_list = [c for c, _ in closed_seq]

        def prior_state(p):
            """Devuelve (streak_perdidas_seguidas, min_desde_ultimo_trade,
            min_desde_ultima_ganancia) usando solo trades cerrados antes del open."""
            i = bisect.bisect_left(close_ts_list, p['open_ts'])
            prior = closed_seq[:i]  # cerrados antes de este open
            if not prior:
                return None, None, None
            # racha perdedora inmediata (desde el final hacia atras)
            streak = 0
            for _, pnl in reversed(prior):
                if pnl < 0:
                    streak += 1
                else:
                    break
            last_trade_ts = max(c for c, _ in prior)
            min_since_trade = (p['open_ts'] - last_trade_ts) / 60.0
            win_closes = [c for c, pnl in prior if pnl > 0]
            min_since_win = ((p['open_ts'] - max(win_closes)) / 60.0) if win_closes else None
            return streak, min_since_trade, min_since_win

        states = {id(p): prior_state(p) for p in positions}

        # ── (a) PROFUNDIDAD de racha perdedora previa ──────────────────────────
        print('\n=== (a) PROFUNDIDAD de racha perdedora INMEDIATAMENTE previa ===')
        print('  (streak = # perdidas seguidas cerradas justo antes del open)')
        by_streak = defaultdict(list)
        for p in positions:
            st = states[id(p)][0]
            if st is None:
                continue
            key = st if st < 4 else 4  # 4 = "4 o mas"
            by_streak[key].append(p)
        for k in sorted(by_streak):
            lbl = f'{k}+ perdidas seguidas' if k == 4 else f'{k} perdidas seguidas '
            line, n, w = fmt_stats(by_streak[k])
            print(f'  tras {lbl}: {line}')
            if n >= 25:
                print(gate(n, w, baseline))
        # Mirada acumulada: ">=2 seguidas" y ">=3 seguidas" (la pregunta del user)
        print('  -- acumulado (>= X perdidas seguidas justo antes) --')
        for thr in (2, 3):
            sub = [p for p in positions
                   if states[id(p)][0] is not None and states[id(p)][0] >= thr]
            line, n, w = fmt_stats(sub)
            print(f'  >= {thr} perdidas seguidas: {line}')
            if n >= 25:
                print(gate(n, w, baseline))

        # ── (b) MINUTOS desde el ultimo trade ──────────────────────────────────
        print('\n=== (b) MINUTOS desde el ULTIMO trade (cualquier resultado) ===')
        gap_buckets = [(0, 15, '0-15min'), (15, 60, '15-60min'),
                       (60, 180, '60-180min'), (180, 1440, '3-24h'),
                       (1440, 9e9, '>24h (dia nuevo)')]
        for lo, hi, lbl in gap_buckets:
            sub = [p for p in positions
                   if states[id(p)][1] is not None and lo <= states[id(p)][1] < hi]
            line, n, w = fmt_stats(sub)
            print(f'  {lbl:18s}: {line}')
            if n >= 25:
                print(gate(n, w, baseline))

        # ── (c) MINUTOS desde la ultima GANANCIA (sequia de wins) ──────────────
        print('\n=== (c) MINUTOS desde la ultima GANANCIA (sequia de wins) ===')
        win_buckets = [(0, 60, '<1h desde win'), (60, 240, '1-4h'),
                       (240, 720, '4-12h'), (720, 2880, '12-48h'),
                       (2880, 9e9, '>48h sin ganar')]
        never_won = [p for p in positions if states[id(p)][2] is None and states[id(p)][1] is not None]
        for lo, hi, lbl in win_buckets:
            sub = [p for p in positions
                   if states[id(p)][2] is not None and lo <= states[id(p)][2] < hi]
            line, n, w = fmt_stats(sub)
            print(f'  {lbl:18s}: {line}')
            if n >= 25:
                print(gate(n, w, baseline))
        line, n, w = fmt_stats(never_won)
        print(f'  sin win previo aun : {line}')
        if n >= 25:
            print(gate(n, w, baseline))

        print('\n--- CAVEATS ---')
        print('1. Muestra historica SUCIA (mezcla v3.6->v3.40, phantom-pnl viejo, regimenes).')
        print('   INPUT de checkpoint, NO un auto-aplicar.')
        print('2. El cooldown <=5min post-perdida YA esta activado: solapa con la racha de 1.')
        print('   Lo nuevo aca es la racha PROFUNDA (>=2/3) y la RECENCIA (gap / sequia de wins).')
        print('3. Default de la casa: RUIDO salvo que el gate diga SIGNIFICATIVO.')
        print('4. Sin velas usadas => sin riesgo de lookahead (todo secuencia broker).')
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
