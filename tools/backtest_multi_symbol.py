"""
backtest_multi_symbol.py — FASE 1: ¿el edge de D1 generaliza fuera de EUR/USD?

READ-ONLY. No escribe en la DB, no manda ordenes, no toca produccion. Solo lee
velas historicas de MT5.

═══ POR QUE EXISTE ═══════════════════════════════════════════════════════════

El track D1 da 2,3 señales/mes en EUR/USD => el gate de n=25 tarda ~11 meses.
Eso no es una propiedad del setup, es la consecuencia de medir en UN par. El
backtest original tenia una sola linea con "EURUSD" hardcodeado.

Corriendo los mismos 7 años sobre 20 pares, la evidencia pasa de ~200 señales a
~4.000 en una tarde. Y contesta lo que ninguna cantidad de espera en EUR/USD
puede contestar: si el edge era del SETUP o del PAR.

La lista de 20 pares esta declarada en docs/fase1_pares_declarados.md y
commiteada ANTES de esta corrida, con el criterio de exito. Si se eligen los
pares despues de ver resultados, el hallazgo no vale nada.

═══ LO QUE HAY QUE HACER BIEN POR SIMBOLO (y el original no hacia) ════════════

1. PIP SIZE. Los pares JPY tienen digits=3 (point=0.001) contra digits=5 de los
   demas. Un pip son 0.01 en JPY y 0.0001 en el resto. Usar 0.0001 para todos
   daria pips 100x mal en 5 de los 20 pares — y el error seria INVISIBLE porque
   los numeros siguen pareciendo plausibles.

2. SWAP. Es la razon #1 por la que D1 quedo en shadow, y es POR PAR Y POR LADO:
   EURUSD long paga -0,83 pips/noche pero USDJPY long COBRA +0,81. Con hold medio
   de 8 dias eso es ~13 pips de diferencia sobre un edge de ~14. Se lee de
   symbol_info y se aplica segun la direccion real de cada trade.

3. COMISION. IC Raw cobra ~$3,50/lote/lado => en pips depende del pip VALUE de
   cada par, que no es constante. Se estima con
   trade_tick_value/trade_tick_size, y si MT5 no lo da se cae al 0,8p de EUR/USD
   dejandolo dicho en el reporte (no en silencio).

Todo lo demas se deja EXACTAMENTE igual que en backtest_h4_d1.py (misma
deteccion, mismo SL/TP relativo al ATR, mismo hold, misma variante 'naive', mismos
params vivos): el objetivo es aislar UNA variable, el instrumento.

═══ CAVEATS HEREDADOS (siguen valiendo, no se arreglan aca) ══════════════════

  - Solo trigger 'structure' (sin news/smc/pre_planned).
  - Sin los filtros del loop vivo => la frecuencia real seria MENOR.
  - Sin spread variable, slippage ni latencia.
  - htf_bias = None.
  - Un backtest tipico INFLA 20-30% vs real con friccion.
  - "Funciona en 15 pares" NO es 15x la confianza: los pares del G8 comparten
    factores (el dolar, el risk-on). El pooled es indicativo, no independiente.

Uso:
    python tools/backtest_multi_symbol.py                  # los 20 declarados
    python tools/backtest_multi_symbol.py --symbols EURUSD,USDJPY
    python tools/backtest_multi_symbol.py --session off    # 1 sesion (mas rapido)
"""
import argparse
import csv
import json
import os
import statistics as stats
import sys
from copy import deepcopy
from datetime import datetime
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

# Se reusa TODO lo que ya estaba probado del backtest de D1. Si eso cambia, esto
# cambia con el — a proposito: no se duplica la logica de medicion.
from tools.backtest_h4_d1 import (  # noqa: E402
    PROFILES, SESSIONS, assert_sessions_match_prod, build_scaled_params,
    load_live_params, setup_logger,
)

# Declarados en docs/fase1_pares_declarados.md ANTES de correr. No reordenar por
# resultado.
SYMBOLS_FASE1 = [
    # majors (7)
    'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY',
    # crosses (13)
    'EURGBP', 'EURJPY', 'EURCHF', 'EURAUD', 'EURCAD', 'EURNZD',
    'GBPJPY', 'GBPCHF', 'GBPAUD', 'AUDJPY', 'AUDNZD', 'AUDCAD', 'CADJPY',
]

CANDLES = 2000
COMMISSION_USD_PER_LOT_SIDE = 3.50      # IC Markets Raw Spread
LOT = 0.01                              # el lote que la cuenta puede operar
COMMISSION_PIPS_FALLBACK = 0.8          # el de EUR/USD, si MT5 no da tick value


def symbol_spec(sym):
    """Pip size, valor del pip y swap por noche EN PIPS, leidos del broker.

    pip != point: en un par de 5 digits el point es 0.00001 y el pip 0.0001.
    En los JPY (3 digits) el point es 0.001 y el pip 0.01.
    """
    import MetaTrader5 as mt5
    # initialize() es idempotente. Va aca porque symbol_spec() se llama ANTES de
    # fetch_d1() y sin terminal conectada symbol_info devuelve None — que se veia
    # igual que "el par no existe" y hacia fallar los 20 pares en silencio.
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    # El simbolo tiene que estar en Market Watch para que symbol_info traiga specs.
    mt5.symbol_select(sym, True)
    i = mt5.symbol_info(sym)
    if i is None:
        return None
    pip = 10 * i.point if i.digits in (3, 5) else i.point

    # Valor de 1 pip para LOT lotes, en la moneda de la cuenta.
    pip_value = None
    if i.trade_tick_value and i.trade_tick_size:
        pip_value = i.trade_tick_value * (pip / i.trade_tick_size) * LOT

    if pip_value and pip_value > 0:
        # round-turn = 2 lados
        comm_pips = (COMMISSION_USD_PER_LOT_SIDE * LOT * 2) / pip_value
        comm_src = 'tick_value'
    else:
        comm_pips, comm_src = COMMISSION_PIPS_FALLBACK, 'FALLBACK(EURUSD)'

    return {
        'symbol': sym, 'digits': i.digits, 'pip': pip,
        'pip_value_usd': pip_value,
        'commission_pips': round(comm_pips, 3), 'commission_source': comm_src,
        # symbol_info.swap_* viene en points => /10 son pips
        'swap_long_pips': i.swap_long / 10.0,
        'swap_short_pips': i.swap_short / 10.0,
        'spread_points': i.spread,
    }


def fetch_d1(sym, count=CANDLES):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    if not mt5.symbol_select(sym, True):
        return None
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, count)
    if rates is None or len(rates) < 400:
        return None
    return [{
        'open': float(r['open']), 'high': float(r['high']),
        'low': float(r['low']), 'close': float(r['close']),
        'datetime': str(datetime.utcfromtimestamp(int(r['time']))),
        'time_unix': int(r['time']),
    } for r in rates]


def atr_at(candles, idx, pip, period=14):
    lo = max(0, idx - period + 1)
    rngs = [(c['high'] - c['low']) / pip for c in candles[lo:idx + 1]]
    return stats.mean(rngs) if rngs else 0.0


def simulate(entry_idx, candles, direction, sl_pips, tp_pips, hold, pip):
    """Igual que el original: si una vela toca SL y TP, asume SL (conservador)."""
    entry = candles[entry_idx]['close']
    if direction == 'CALL':
        sl_p, tp_p = entry - sl_pips * pip, entry + tp_pips * pip
    else:
        sl_p, tp_p = entry + sl_pips * pip, entry - tp_pips * pip
    end = min(entry_idx + 1 + hold, len(candles))
    for j in range(entry_idx + 1, end):
        c = candles[j]
        if direction == 'CALL':
            sl_hit, tp_hit = c['low'] <= sl_p, c['high'] >= tp_p
        else:
            sl_hit, tp_hit = c['high'] >= sl_p, c['low'] <= tp_p
        if sl_hit:
            return {'result': 'sl', 'exit_idx': j, 'pips': -float(sl_pips)}
        if tp_hit:
            return {'result': 'tp', 'exit_idx': j, 'pips': float(tp_pips)}
    last = candles[end - 1]['close']
    pips = (last - entry) / pip if direction == 'CALL' else (entry - last) / pip
    return {'result': 'hold_end', 'exit_idx': end - 1, 'pips': round(pips, 1)}


def run_symbol(sym, params, session, logger):
    spec = symbol_spec(sym)
    if spec is None:
        return {'symbol': sym, 'error': 'symbol_info None'}
    candles = fetch_d1(sym)
    if candles is None:
        return {'symbol': sym, 'error': 'sin velas D1 suficientes'}

    from src.analyzer.technical import TechnicalAnalyzer
    import src.analyzer.technical as tech_mod

    prof = PROFILES['D1']
    pip = spec['pip']
    warmup = 100

    analyzer = TechnicalAnalyzer(logger)
    analyzer._cache_ttl = 0
    analyzer._dedup_window_sec = 172800

    class _FakeTuner:
        def __init__(self, *a, **k):
            pass

        def get_params(self):
            return dict(params)

    _fixed = dict(SESSIONS[session])
    session_patch = patch.object(TechnicalAnalyzer, 'get_session_info',
                                 staticmethod(lambda: dict(_fixed)))

    # OJO: technical.py razona en 0.0001 por pip (esta escrito para EUR/USD). Para
    # los JPY se re-escalan los precios al espacio de "1 pip = 0.0001" antes de
    # pasarlos al detector, y los pips que salen ya son pips reales. Sin esto el
    # detector veria movimientos 100x mas chicos y no disparia casi nunca.
    escala = 0.0001 / pip
    sigs_out = []

    for i in range(warmup, len(candles) - 1):
        sl_ = candles[max(0, i - warmup + 1):i + 1]
        if escala != 1.0:
            sl_ = [{**c, 'open': c['open'] * escala, 'high': c['high'] * escala,
                    'low': c['low'] * escala, 'close': c['close'] * escala}
                   for c in sl_]
        analyzer._fetch_candles = lambda s=sl_: deepcopy(s)
        analyzer._cache.clear()
        # NO se limpia _triggered_levels: el dedup de 2 dias tiene que seguir
        # funcionando igual que en backtest_h4_d1.py. Limpiarlo daba 199 señales en
        # EUR/USD contra las 186 del baseline — o sea, medir otra cosa. Es la misma
        # clase de divergencia silenciosa que rompio el baseline del D1.
        try:
            with patch('src.optimizer.auto_tuner.AutoTuner', _FakeTuner), \
                 patch.object(tech_mod.time, 'time', return_value=candles[i]['time_unix']), \
                 session_patch:
                sigs = analyzer.detect_structure_signals(
                    min_confidence=prof['min_confidence'])
        except Exception:
            continue

        for s in sigs:
            a = atr_at(candles, i, pip)
            if a <= 0:
                continue
            sl_pips = round(a * prof['sl_atr_mult'], 1)
            tp_pips = round(sl_pips * prof['rr'], 1)
            out = simulate(i, candles, s['direction'], sl_pips, tp_pips,
                           prof['hold_candles'], pip)
            noches = (candles[out['exit_idx']]['time_unix']
                      - candles[i]['time_unix']) / 86400.0
            swap = (spec['swap_long_pips'] if s['direction'] == 'CALL'
                    else spec['swap_short_pips']) * noches
            neto = out['pips'] - spec['commission_pips'] + swap
            sigs_out.append({
                'symbol': sym, 'datetime': candles[i]['datetime'],
                'direction': s['direction'], 'setup_type': s.get('setup_type', '?'),
                'confidence': s.get('confidence', 0), 'atr': round(a, 1),
                'sl_pips': sl_pips, 'tp_pips': tp_pips, 'result': out['result'],
                'pips': out['pips'], 'noches': round(noches, 1),
                'swap_pips': round(swap, 2), 'neto_pips': round(neto, 2),
            })

    return aggregate(sym, spec, sigs_out, candles)


def _pf(vals):
    gw = sum(v for v in vals if v > 0)
    gl = abs(sum(v for v in vals if v < 0))
    return round(gw / gl, 2) if gl > 0 else None


def aggregate(sym, spec, sigs, candles):
    n = len(sigs)
    span = (candles[-1]['time_unix'] - candles[100]['time_unix']) / 86400.0
    r = {'symbol': sym, 'n': n, 'span_days': round(span),
         'commission_pips': spec['commission_pips'],
         'commission_source': spec['commission_source'],
         'swap_long_pips': round(spec['swap_long_pips'], 3),
         'swap_short_pips': round(spec['swap_short_pips'], 3),
         'digits': spec['digits'], 'spread_points': spec['spread_points']}
    if n == 0:
        r['note'] = 'sin señales'
        return r

    brutos = [s['pips'] for s in sigs]
    con_com = [s['pips'] - spec['commission_pips'] for s in sigs]
    netos = [s['neto_pips'] for s in sigs]

    r.update({
        'por_mes': round(n / (span / 30.0), 2),
        'avg_bruto': round(stats.mean(brutos), 2),
        'avg_com': round(stats.mean(con_com), 2),
        'avg_neto': round(stats.mean(netos), 2),
        'wr_com': round(sum(1 for v in con_com if v > 0) / n * 100, 1),
        'wr_neto': round(sum(1 for v in netos if v > 0) / n * 100, 1),
        'pf_com': _pf(con_com), 'pf_neto': _pf(netos),
        'pips_neto_total': round(sum(netos), 1),
        'swap_medio': round(stats.mean([s['swap_pips'] for s in sigs]), 2),
        'noches_medias': round(stats.mean([s['noches'] for s in sigs]), 1),
        'longs': sum(1 for s in sigs if s['direction'] == 'CALL'),
    })
    mid = n // 2
    for tag, part in (('h1', netos[:mid]), ('h2', netos[mid:])):
        if part:
            r[f'avg_neto_{tag}'] = round(stats.mean(part), 2)
    r['_signals'] = sigs
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbols', default=','.join(SYMBOLS_FASE1))
    ap.add_argument('--session', choices=list(SESSIONS), default='off',
                    help="conf_adj del paso 7. 'off' = el mismo con el que se "
                         "reprodujo el titular de EUR/USD (default).")
    ap.add_argument('--params', choices=['default', 'live'], default='live')
    args = ap.parse_args()

    syms = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    logger = setup_logger()

    print('=' * 78)
    print(f'FASE 1 — ¿GENERALIZA EL EDGE DE D1?  {datetime.now():%Y-%m-%d %H:%M}')
    print('=' * 78)
    print(f'{len(syms)} pares declarados en docs/fase1_pares_declarados.md')
    print(f'params={args.params}  sesion={args.session}  velas={CANDLES}  lote={LOT}')
    print('Comision y swap POR PAR (leidos del broker). Pip size por digits.')

    assert_sessions_match_prod()
    if args.params == 'live':
        params, diff = load_live_params(logger)
        print(f'params vivos: {len(diff)} clave(s) distintas del default')
    else:
        from src.optimizer.auto_tuner import DEFAULT_PARAMS
        params = dict(DEFAULT_PARAMS)

    res = []
    for k, s in enumerate(syms, 1):
        print(f'\n[{k}/{len(syms)}] {s} ...', end=' ', flush=True)
        try:
            r = run_symbol(s, params, args.session, logger)
        except Exception as e:
            r = {'symbol': s, 'error': str(e)[:80]}
        if r.get('error'):
            print(f"ERROR: {r['error']}")
        elif r.get('n', 0) == 0:
            print('sin señales')
        else:
            print(f"n={r['n']}  avg_neto={r['avg_neto']:+.2f}p  "
                  f"PF={r['pf_neto']}  WR={r['wr_neto']}%")
        res.append(r)

    ok = [r for r in res if r.get('n', 0) > 0]

    print('\n' + '=' * 78)
    print('TABLA COMPLETA — orden declarado, NO por resultado')
    print('=' * 78)
    print(f"{'par':9s}{'n':>5s}{'/mes':>6s}{'com':>6s}{'swap':>7s}"
          f"{'avgBrut':>9s}{'avgCom':>8s}{'avgNeto':>9s}{'PFneto':>8s}{'WR':>7s}")
    for r in res:
        if r.get('n', 0) == 0:
            print(f"{r['symbol']:9s}  {r.get('error') or 'sin señales'}")
            continue
        print(f"{r['symbol']:9s}{r['n']:>5d}{r['por_mes']:>6.1f}"
              f"{r['commission_pips']:>6.2f}{r['swap_medio']:>7.2f}"
              f"{r['avg_bruto']:>9.2f}{r['avg_com']:>8.2f}{r['avg_neto']:>9.2f}"
              f"{str(r['pf_neto']):>8s}{r['wr_neto']:>6.1f}%")

    if ok:
        pos_com = [r for r in ok if r['avg_com'] > 0]
        pos_neto = [r for r in ok if r['avg_neto'] > 0]
        todas = [s for r in ok for s in r['_signals']]
        pooled_com = [s['pips'] - next(x['commission_pips'] for x in ok
                                       if x['symbol'] == s['symbol']) for s in todas]
        pooled_neto = [s['neto_pips'] for s in todas]

        print('\n' + '-' * 78)
        print('VEREDICTO (criterio pre-declarado: >=13/20 positivos net-comision Y pooled positivo)')
        print('-' * 78)
        print(f"  pares medidos            : {len(ok)}/{len(syms)}")
        print(f"  positivos neto COMISION  : {len(pos_com)}/{len(ok)}"
              f"   -> {[r['symbol'] for r in pos_com]}")
        print(f"  positivos neto +SWAP     : {len(pos_neto)}/{len(ok)}"
              f"   -> {[r['symbol'] for r in pos_neto]}")
        print(f"  POOLED n={len(todas)}: avg neto comision {stats.mean(pooled_com):+.2f}p"
              f"  |  avg neto +swap {stats.mean(pooled_neto):+.2f}p"
              f"  |  PF neto {_pf(pooled_neto)}")
        print(f"  señales/mes sumando los {len(ok)} pares: "
              f"{sum(r['por_mes'] for r in ok):.1f}  "
              f"(EUR/USD solo: {next((r['por_mes'] for r in ok if r['symbol']=='EURUSD'), 0):.1f})")
        generaliza = len(pos_com) >= 13 and stats.mean(pooled_com) > 0 and stats.mean(pooled_neto) > 0
        print(f"\n  => {'GENERALIZA (cumple el criterio declarado)' if generaliza else 'NO CUMPLE el criterio declarado'}")

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    jp = os.path.join(ROOT, f'backtest_multi_{ts}.json')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump([{k: v for k, v in r.items() if k != '_signals'} for r in res],
                  f, indent=2, ensure_ascii=False, default=str)
    cp = os.path.join(ROOT, f'backtest_multi_{ts}.csv')
    with open(cp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['symbol', 'datetime', 'direction', 'setup_type', 'confidence',
                    'atr', 'sl_pips', 'tp_pips', 'result', 'pips', 'noches',
                    'swap_pips', 'neto_pips'])
        for r in ok:
            for s in r['_signals']:
                w.writerow([s[k] for k in ('symbol', 'datetime', 'direction',
                                           'setup_type', 'confidence', 'atr',
                                           'sl_pips', 'tp_pips', 'result', 'pips',
                                           'noches', 'swap_pips', 'neto_pips')])
    print(f'\nJSON: {jp}\nCSV : {cp}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
