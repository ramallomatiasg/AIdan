"""P1 del registro de propuestas: el detector `structure` en ORO e INDICES (read-only).

Criterio declarado ANTES de medir: docs/p1_otro_instrumento_criterio.md.

Idea: misma logica, misma geometria relativa, distinto costo. Cada instrumento se mide
en PSEUDO-PIPS = mediana del rango M15 del instrumento / mediana del de EURUSD (en pips)
=> la vela mediana "mide" lo mismo en todos, las constantes de technical.py quedan en
la misma proporcion y el perfil vivo de M15 (SL 15 / TP 60 / 3 velas) se aplica tal
cual. Lo unico que cambia es el COSTO expresado en pseudo-pips (la hipotesis).

Piezas del arnes de Fase 2 IMPORTADAS (simulate, evaluate_session, fetch_with_retry,
SESSIONS, load_live_params); el loop del detector es el de run_job con pip=pseudo-pip.

No toca la DB de produccion para escribir (get_setup_win_rates se congela en un
snapshot, como en Fase 2). MT5 SOLO en --build-cache, y solo con AIdan cerrado.

Uso:
  python tools/backtest_p1_instrumentos.py --build-cache   # baja velas (AIdan cerrado)
  python tools/backtest_p1_instrumentos.py                 # mide (sin MT5)
"""
import argparse
import json
import os
import random
import statistics as stats
import sys
import time
from copy import deepcopy
from datetime import datetime
from multiprocessing import Pool
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import tools.backtest_fase2 as f2  # noqa: E402
from tools.backtest_h4_d1 import SESSIONS, load_live_params, setup_logger  # noqa: E402
from tools.backtest_multi_symbol import simulate  # noqa: E402

ANCHOR = 'EURUSD'
NEW = ['XAUUSD', 'USTEC', 'US30', 'DE40']
SYMS = [ANCHOR] + NEW
# Comision IC Markets Raw, USD por lote ROUND-TURN (declarado en el criterio).
COMM_RT_USD = {'EURUSD': 7.0, 'XAUUSD': 7.0, 'USTEC': 0.0, 'US30': 0.0, 'DE40': 0.0}
EURUSD_SPREAD_FLOOR = 0.00001          # 0,1p: TCA real (la vela trae 0)
PROFILE = dict(f2.PROFILE_LIVE)        # SL 15 / TP 60 / hold 3 / conf 60
SESSION = 'london'
COUNT = 150_000
MIN_N = 50_000
CONTROL_REPS = 200
CACHE = os.path.join(ROOT, '.cache_p1', 'M15')


def build_cache(logger):
    import MetaTrader5 as mt5
    import numpy as np
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    os.makedirs(CACHE, exist_ok=True)
    for sym in SYMS:
        mt5.symbol_select(sym, True)
        i = mt5.symbol_info(sym)
        if i is None:
            logger.warning(f"{sym}: symbol_info None -> EXCLUIDO")
            continue
        r = f2.fetch_with_retry(mt5, sym, mt5.TIMEFRAME_M15, COUNT, MIN_N, logger)
        n = 0 if r is None else len(r)
        if n < MIN_N:
            logger.warning(f"{sym}: solo {n} velas -> EXCLUIDO")
            continue
        np.save(os.path.join(CACHE, f'{sym}.npy'), r)
        meta = {'point': i.point, 'digits': i.digits,
                'contract_size': i.trade_contract_size, 'n': n,
                'desde': str(datetime.utcfromtimestamp(int(r[0]['time']))),
                'hasta': str(datetime.utcfromtimestamp(int(r[-1]['time'])))}
        with open(os.path.join(CACHE, f'{sym}.meta.json'), 'w') as f:
            json.dump(meta, f)
        logger.info(f"{sym}: {n} velas M15 {meta['desde']} -> {meta['hasta']}")
    mt5.shutdown()


def load(sym):
    import numpy as np
    r = np.load(os.path.join(CACHE, f'{sym}.npy'))
    if os.environ.get('P1_SMOKE'):          # solo para probar el tool, nunca para medir
        r = r[-int(os.environ['P1_SMOKE']):]
    with open(os.path.join(CACHE, f'{sym}.meta.json')) as f:
        meta = json.load(f)
    candles = [{'open': float(x['open']), 'high': float(x['high']),
                'low': float(x['low']), 'close': float(x['close']),
                'time_unix': int(x['time'])} for x in r]
    spread_px = [float(x['spread']) * meta['point'] for x in r]
    return candles, spread_px, meta


def median_range(candles):
    return stats.median(c['high'] - c['low'] for c in candles)


def cost_pp(sym, i, spread_px, meta, pp):
    sp = spread_px[i]
    if sym == ANCHOR:
        sp = max(sp, EURUSD_SPREAD_FLOOR)
    comm_px = COMM_RT_USD[sym] / meta['contract_size']
    return (sp + comm_px) / pp


def crosses_rollover(candles, i, j):
    # tiempos de vela = hora SERVER (UTC+3) => rollover = cambio de dia server
    d0 = datetime.utcfromtimestamp(candles[i]['time_unix']).date()
    d1 = datetime.utcfromtimestamp(candles[j]['time_unix']).date()
    return d0 != d1


def run_sym(job):
    sym, pp, params = job
    import logging
    import numpy as np
    logging.disable(logging.CRITICAL)
    logger = logging.getLogger('p1')
    t0 = time.perf_counter()
    candles, spread_px, meta = load(sym)

    from src.analyzer.technical import TechnicalAnalyzer
    import src.analyzer.technical as tech_mod
    import src.common.db as _dbmod
    _wr = _dbmod.get_setup_win_rates()
    _dbmod.get_setup_win_rates = lambda: _wr

    class _FakeTuner:
        def __init__(self, *a, **k):
            pass

        def get_params(self):
            return dict(params)

    _fixed = dict(SESSIONS[SESSION])
    analyzer = TechnicalAnalyzer(logger)
    analyzer._cache_ttl = 0
    analyzer._dedup_window_sec = f2.DEDUP_SEC['M15']
    escala = 0.0001 / pp

    netos, times, n_long, n_roll, n_err, first_err = [], [], 0, 0, 0, None
    for i in range(f2.WARMUP, len(candles) - 1):
        sl_ = [{**c, 'open': c['open'] * escala, 'high': c['high'] * escala,
                'low': c['low'] * escala, 'close': c['close'] * escala}
               for c in candles[i - f2.WARMUP + 1:i + 1]]
        analyzer._fetch_candles = lambda s=sl_: deepcopy(s)
        analyzer._cache.clear()
        try:
            with patch('src.optimizer.auto_tuner.AutoTuner', _FakeTuner), \
                 patch.object(tech_mod.time, 'time', return_value=candles[i]['time_unix']), \
                 patch.object(TechnicalAnalyzer, 'get_session_info',
                              staticmethod(lambda: dict(_fixed))):
                sigs = analyzer.detect_structure_signals(
                    min_confidence=PROFILE['min_confidence'])
        except Exception as e:
            n_err += 1
            first_err = first_err or repr(e)
            continue
        for s in sigs:
            out = simulate(i, candles, s['direction'], PROFILE['sl_pips'],
                           PROFILE['tp_pips'], PROFILE['hold'], pp)
            netos.append(out['pips'] - cost_pp(sym, i, spread_px, meta, pp))
            times.append(candles[i]['time_unix'])
            n_long += s['direction'] == 'CALL'
            n_roll += crosses_rollover(candles, i, out['exit_idx'])

    bars = len(candles) - f2.WARMUP - 1
    if n_err > 0.05 * bars:   # FAIL-LOUD: 0 senales por excepcion != "no hay edge"
        raise RuntimeError(f"{sym}: detector fallo en {n_err}/{bars}: {first_err}")

    n = len(netos)
    p_long = n_long / n if n else 0.5
    rng = random.Random(f'{sym}|p1')
    control = []
    if n:
        for _ in range(CONTROL_REPS):
            tot = 0.0
            for _ in range(n):
                k = rng.randint(f2.WARMUP, len(candles) - 2)
                d = 'CALL' if rng.random() < p_long else 'PUT'
                r = simulate(k, candles, d, PROFILE['sl_pips'], PROFILE['tp_pips'],
                             PROFILE['hold'], pp)
                tot += r['pips'] - cost_pp(sym, k, spread_px, meta, pp)
            control.append((round(tot, 3), n))
    costs = [cost_pp(sym, k, spread_px, meta, pp)
             for k in range(f2.WARMUP, len(candles) - 1, 50)]
    return {'symbol': sym, 'n': n, 'n_err': n_err, 'p_long': round(p_long, 4),
            'netos': np.asarray(netos, dtype=np.float32),
            'times': np.asarray(times, dtype=np.int64), 'control': control,
            't_first': candles[f2.WARMUP]['time_unix'], 't_last': candles[-1]['time_unix'],
            'pseudo_pip': pp, 'cost_med_pp': round(stats.median(costs), 3),
            'rollover_frac': round(n_roll / n, 4) if n else 0.0,
            'desde': meta['desde'], 'hasta': meta['hasta'],
            'secs': round(time.perf_counter() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build-cache', action='store_true')
    ap.add_argument('--workers', type=int, default=5)
    a = ap.parse_args()
    logger = setup_logger()
    if a.build_cache:
        build_cache(logger)
        return

    avail = [s for s in SYMS if os.path.exists(os.path.join(CACHE, f'{s}.npy'))]
    if ANCHOR not in avail:
        sys.exit('falta EURUSD en el cache (ancla): correr --build-cache')
    eu_c, _, _ = load(ANCHOR)
    eu_range_pips = median_range(eu_c) / 0.0001
    pps = {s: median_range(load(s)[0]) / eu_range_pips for s in avail}
    params, _ = load_live_params(logger)
    jobs = [(s, pps[s], params) for s in avail]
    with Pool(min(a.workers, len(jobs))) as pool:
        rows = pool.map(run_sym, jobs)

    print('=' * 78)
    print(f'P1 — structure en otros instrumentos (M15, perfil vivo en pseudo-pips, sesion {SESSION})')
    print(f'rango M15 mediano EURUSD = {eu_range_pips:.2f}p => 1 pseudo-pip = rango/{eu_range_pips:.2f}')
    print('=' * 78)
    print(f"{'sym':8}{'n':>8}{'neto/tr':>9}{'costo pp':>10}{'ctrl med':>10}{'%roll':>7}  periodo")
    for r in rows:
        ctrl = sorted(t / c for t, c in r['control']) if r['control'] else [float('nan')]
        avg = float(r['netos'].mean()) if r['n'] else float('nan')
        print(f"{r['symbol']:8}{r['n']:>8}{avg:>9.3f}{r['cost_med_pp']:>10.3f}"
              f"{ctrl[len(ctrl)//2]:>10.3f}{100*r['rollover_frac']:>6.1f}%  "
              f"{r['desde'][:10]} -> {r['hasta'][:10]}")
    anc = f2.evaluate_session([r for r in rows if r['symbol'] == ANCHOR])
    new = f2.evaluate_session([r for r in rows if r['symbol'] in NEW])
    pos = sum(1 for r in rows if r['symbol'] in NEW and r['n'] and r['netos'].mean() > 0)
    print('-' * 78)
    print(f"ANCLA EURUSD: neto {anc.get('pooled_neto')} (debe ~ -1,0 +- 0,3 o el tool esta mal)")
    keys = ['n', 'pooled_neto', 'ci95', 'mitad_1', 'mitad_2', 'control_p95', 'control_mediana',
            'cond_1_pooled_pos', 'cond_2_ci_lo_pos', 'cond_3_dos_mitades', 'cond_4_supera_control']
    print('POOL 4 NUEVOS: ' + ' | '.join(f'{k}={new.get(k)}' for k in keys))
    ok = new.get('veredicto') == 'PASA' and pos >= 3
    print(f'instrumentos nuevos con neto>0: {pos}/4')
    print(f"VEREDICTO: {'PASA' if ok else 'NO PASA'}"
          + ('' if ok else (' (le gana al control)' if new.get('cond_4_supera_control')
                            else ' (no le gana al control)')))
    out = os.path.join(ROOT, 'docs', 'p1_resultado.json')
    with open(out, 'w') as f:
        json.dump({'anchor': anc, 'pool_new': new, 'pos_new': pos, 'veredicto': 'PASA' if ok else 'NO PASA',
                   'por_sym': [{k: v for k, v in r.items() if k not in ('netos', 'times', 'control')}
                               for r in rows]}, f, indent=2, default=float)
    print(f'-> {out}')


if __name__ == '__main__':
    main()
