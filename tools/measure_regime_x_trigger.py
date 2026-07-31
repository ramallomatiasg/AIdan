# -*- coding: utf-8 -*-
"""
measure_regime_x_trigger.py  (READ-ONLY, no escribe a la DB)

Frente REGIMEN x TRIGGER: decide si vale construir el detector de regimen.

Por cada posicion cerrada (broker-truth, magic AIdan):
  - emparejo deals por position_id (entry d.entry==0, exit d.entry==1).
  - REGIMEN mecanico de los ~60min PREVIOS al entry, cortando a open_ts-300s
    (REGLA CRITICA 12 Jun: nunca incluir la vela en formacion al entry = lookahead):
      * ATR = avg(high-low) en pips de esas velas M5.
      * eficiencia direccional = |close_fin - close_ini| / sum(|close_i - close_i-1|).
      * etiqueta tendencia/transicion/chop por eficiencia; vol alta/baja por ATR (mediana).
  - cruzo REGIMEN x trigger_type (de la DB por strategy_id) -> WR/PnL por celda.

Gate de la casa: significance.verify_finding(n, wins, baseline_wr=WR_universo).
baseline = WR del universo de posiciones cerradas (no el 0.374 fijo).
Default = RUIDO si n<25 o el CI 95% cruza el baseline.
"""
import os
import sys
import time
import sqlite3
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAGIC_NUMBER = 20260402
DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
SYMBOL = 'EURUSD'
PIP = 0.0001

LOOKBACK_MIN = 60          # ~60min previos al entry
# cortar >=N s antes del open (anti-lookahead, leccion 12 Jun). Override por env
# para reproducir el test de sensibilidad: CUT_BEFORE_S=360 / =600 -> si un hallazgo
# pasa el gate a 300 pero NO a 360/600, es artefacto de la vela en formacion (lookahead).
CUT_BEFORE_S = int(os.environ.get('CUT_BEFORE_S', '300'))
EFF_TREND = 0.40           # eficiencia > 0.40 -> tendencia
EFF_CHOP = 0.25            # eficiencia < 0.25 -> chop


def pair_positions(mt5):
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
            'pnl': round(pnl, 2),
        })
    positions.sort(key=lambda p: p['open_ts'])
    return positions


def regime_for(mt5, open_ts, offset_s):
    """Regimen mecanico de los LOOKBACK_MIN previos, cortando a open_ts-CUT_BEFORE_S.

    copy_rates_range usa epoch del server (mismo que d.time) => alineo en epoch
    server directamente (open_ts ya es server time). Corto el rango a
    open_ts-CUT_BEFORE_S para no tocar la vela en formacion (lookahead)."""
    cut = open_ts - CUT_BEFORE_S
    start = cut - LOOKBACK_MIN * 60
    # copy_rates_range exige datetimes tz-aware UTC; los candle.time vienen en
    # epoch del server (= la misma escala de d.time/open_ts) => construyo UTC-aware
    # desde el epoch server directamente. (naive datetime devuelve 0 filas).
    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5,
                                 datetime.fromtimestamp(start, tz=timezone.utc),
                                 datetime.fromtimestamp(cut, tz=timezone.utc))
    if rates is None or len(rates) < 6:
        return None
    # guard extra anti-lookahead: descartar cualquier vela cuyo open caiga >= cut
    rates = [r for r in rates if r['time'] < cut]
    if len(rates) < 6:
        return None
    atr = sum((r['high'] - r['low']) for r in rates) / len(rates) / PIP
    net = abs(rates[-1]['close'] - rates[0]['close'])
    path = sum(abs(rates[i]['close'] - rates[i - 1]['close']) for i in range(1, len(rates)))
    eff = (net / path) if path > 0 else 0.0
    if eff > EFF_TREND:
        trend = 'tendencia'
    elif eff < EFF_CHOP:
        trend = 'chop'
    else:
        trend = 'transicion'
    return {'atr': atr, 'eff': eff, 'trend': trend}


def fmt(subset):
    n = len(subset)
    if n == 0:
        return 'n=  0  WR= --  PnL=    0.00', 0, 0, 0.0
    w = sum(1 for p in subset if p['pnl'] > 0)
    pnl = round(sum(p['pnl'] for p in subset), 2)
    return f"n={n:3d}  WR={round(100*w/n):3d}%  PnL={pnl:+8.2f}", n, w, pnl


def gate(n, wins, baseline):
    from src.optimizer.significance import verify_finding
    direction = 'worse' if (wins / n) < baseline else 'better'
    r = verify_finding(n, wins, baseline_wr=baseline, direction=direction)
    return r, direction


def main():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print('No pude attachear MT5:', mt5.last_error()); return
    out = []
    try:
        tick = mt5.symbol_info_tick(SYMBOL)
        offset_s = round((tick.time - time.time()) / 1800.0) * 1800
        out.append(f'offset server-vs-local: {offset_s}s ({offset_s/3600.0:.1f}h)')

        positions = pair_positions(mt5)
        out.append(f'posiciones cerradas (broker-truth): {len(positions)}')

        # trigger_type por sid (trade_archive principal, auto_strategies fallback)
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        trig = {}
        for tbl, key in (('trade_archive', 'strategy_id'), ('auto_strategies', 'id')):
            try:
                for sid, tt in conn.execute(f"SELECT {key}, trigger_type FROM {tbl} WHERE trigger_type IS NOT NULL"):
                    if sid is not None and sid not in trig:
                        trig[sid] = tt
            except Exception:
                pass
        conn.close()

        # asignar regimen + trigger
        kept = []
        no_candles = 0
        no_trig = 0
        for p in positions:
            reg = regime_for(mt5, p['open_ts'], offset_s)
            if reg is None:
                no_candles += 1
                continue
            p['reg'] = reg
            p['trigger'] = trig.get(p['sid'], 'unknown')
            if p['trigger'] == 'unknown' or p['sid'] is None:
                no_trig += 1
            kept.append(p)

        out.append(f'con candles M5 previas: {len(kept)}  (sin candles: {no_candles}, sin trigger en DB: {no_trig})')

        line, n_all, w_all, _ = fmt(kept)
        baseline = w_all / n_all if n_all else 0.374
        out.append(f'UNIVERSO medible: {line}  -> baseline WR={baseline:.3f}')

        # mediana ATR para split vol alta/baja
        atrs = sorted(p['reg']['atr'] for p in kept)
        med_atr = atrs[len(atrs) // 2] if atrs else 0.0
        out.append(f'ATR mediana ventana previa: {med_atr:.2f}p (split vol alta/baja)')
        for p in kept:
            p['vol'] = 'alta' if p['reg']['atr'] >= med_atr else 'baja'

        # ── marginal por REGIMEN (eficiencia) ──
        out.append('\n=== MARGINAL por REGIMEN (eficiencia direccional) ===')
        regime_rows = []
        for rg in ('tendencia', 'transicion', 'chop'):
            sub = [p for p in kept if p['reg']['trend'] == rg]
            line, n, w, pnl = fmt(sub)
            tag = 'RUIDO'
            if n >= 25:
                r, d = gate(n, w, baseline)
                tag = f"{'SIG' if r.significant else 'RUIDO'} ({d} p={r.p_value:.3f} CI[{r.ci_low:.2f},{r.ci_high:.2f}])"
            out.append(f'  {rg:11s}: {line}  -> {tag}')
            regime_rows.append((f'regimen={rg}', n, w, pnl, tag))

        # ── marginal por VOL ──
        out.append('\n=== MARGINAL por VOLATILIDAD (ATR vs mediana) ===')
        for vl in ('alta', 'baja'):
            sub = [p for p in kept if p['vol'] == vl]
            line, n, w, pnl = fmt(sub)
            tag = 'RUIDO'
            if n >= 25:
                r, d = gate(n, w, baseline)
                tag = f"{'SIG' if r.significant else 'RUIDO'} ({d} p={r.p_value:.3f} CI[{r.ci_low:.2f},{r.ci_high:.2f}])"
            out.append(f'  vol {vl:5s}: {line}  -> {tag}')

        # ── marginal por TRIGGER ──
        out.append('\n=== MARGINAL por TRIGGER ===')
        triggers = sorted(set(p['trigger'] for p in kept))
        for tt in triggers:
            sub = [p for p in kept if p['trigger'] == tt]
            line, n, w, pnl = fmt(sub)
            tag = 'RUIDO'
            if n >= 25:
                r, d = gate(n, w, baseline)
                tag = f"{'SIG' if r.significant else 'RUIDO'} ({d} p={r.p_value:.3f} CI[{r.ci_low:.2f},{r.ci_high:.2f}])"
            out.append(f'  {tt:16s}: {line}  -> {tag}')

        # ── MATRIZ REGIMEN x TRIGGER ──
        out.append('\n=== MATRIZ  REGIMEN x TRIGGER  (la pregunta) ===')
        sig_cells = []
        for tt in triggers:
            for rg in ('tendencia', 'transicion', 'chop'):
                sub = [p for p in kept if p['trigger'] == tt and p['reg']['trend'] == rg]
                line, n, w, pnl = fmt(sub)
                tag = ''
                if n >= 25:
                    r, d = gate(n, w, baseline)
                    ok = r.significant
                    tag = f"  -> {'*** SIG' if ok else 'RUIDO'} ({d} p={r.p_value:.3f} CI[{r.ci_low:.2f},{r.ci_high:.2f}])"
                    if ok:
                        sig_cells.append(f"{tt} x {rg}: {line} | {d} p={r.p_value:.3f}")
                elif n > 0:
                    tag = '  (n<25, no se testea)'
                out.append(f'  {tt:16s} x {rg:11s}: {line}{tag}')

        # ── MATRIZ REGIMEN x VOL x TRIGGER (4 celdas de regimen-vol mas finas) — solo si hay n ──
        out.append('\n=== REGIMEN x VOL  (sin trigger, mas n por celda) ===')
        for rg in ('tendencia', 'transicion', 'chop'):
            for vl in ('alta', 'baja'):
                sub = [p for p in kept if p['reg']['trend'] == rg and p['vol'] == vl]
                line, n, w, pnl = fmt(sub)
                tag = ''
                if n >= 25:
                    r, d = gate(n, w, baseline)
                    tag = f"  -> {'*** SIG' if r.significant else 'RUIDO'} ({d} p={r.p_value:.3f} CI[{r.ci_low:.2f},{r.ci_high:.2f}])"
                    if r.significant:
                        sig_cells.append(f"{rg} x vol {vl}: {line} | {d} p={r.p_value:.3f}")
                elif n > 0:
                    tag = '  (n<25)'
                out.append(f'  {rg:11s} x vol {vl:5s}: {line}{tag}')

        out.append('\n=== CELDAS QUE PASARON EL GATE ===')
        if sig_cells:
            for c in sig_cells:
                out.append('  ' + c)
        else:
            out.append('  NINGUNA. Ninguna celda regimen x trigger separa del baseline con n>=25 y CI sin cruzar.')

        out.append('\n--- CAVEATS ---')
        out.append('1. Muestra historica SUCIA (mezcla v3.6->v3.40, phantom-pnl viejo).')
        out.append('2. Regimen RECONSTRUIDO retrospectivamente (mecanico, anti-lookahead -300s) — no medido en vivo.')
        out.append('3. baseline = WR universo medible (no 0.374 fijo).')
    finally:
        mt5.shutdown()
    print('\n'.join(out))


if __name__ == '__main__':
    main()
