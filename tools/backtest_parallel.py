"""
Backtest paralelo de combinaciones de filtros sobre trade_archive.

Aprovecha tus 8 cores: cada combinación de parámetros se evalúa en
proceso separado. Para 1000 combinaciones, esto baja de ~30 min serial
a ~4 min con 8 cores.

Uso:
    python tools/backtest_parallel.py
    python tools/backtest_parallel.py --workers 4    # usar menos cores
    python tools/backtest_parallel.py --top 20       # mostrar top 20
    python tools/backtest_parallel.py --track m5     # solo M5

Output: top N combinaciones de filtros ordenadas por PF*PnL,
descartando las con muestra menor a min_trades.

NOTA: este es backtest TEÓRICO — asume que filtrar trades retroactivamente
de trade_archive equivale a no haberlos tomado en producción. Es válido
para comparación relativa entre filtros, no para predecir PnL absoluto.
"""
import argparse
import json
import multiprocessing as mp
import os
import sqlite3
import sys
import time
from itertools import product

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')


def load_trades(track='all'):
    """Carga trades del archive con features completos para backtesting."""
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    cur = conn.cursor()

    where_track = ''
    if track == 'm5':
        where_track = "AND trigger_type NOT LIKE 'm15_%' AND trigger_type NOT LIKE 'h1_%'"
    elif track == 'm15':
        where_track = "AND trigger_type LIKE 'm15_%'"
    elif track == 'h1':
        where_track = "AND trigger_type LIKE 'h1_%'"

    cur.execute(f"""
        SELECT direction, result, pips, sl_pips, tp_pips,
               confidence, impact_score, trigger_type, htf_bias,
               rsi_at_entry, avg_range_pips, session, hour_utc, day_of_week,
               mt5_pnl, market_trend, trend_strength, volatility, sl_hit, tp_hit
        FROM trade_archive
        WHERE result IN ('win', 'loss')
          AND mt5_pnl IS NOT NULL
          AND avg_range_pips > 0
          AND htf_bias IS NOT NULL AND htf_bias != ''
          {where_track}
    """)
    cols = [d[0] for d in cur.description]
    trades = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return trades


def apply_filters(trades, params):
    """Aplica un set de filtros y devuelve subset que hubiera pasado."""
    out = []
    for t in trades:
        # Min confidence
        if params['min_conf'] is not None and t['confidence'] < params['min_conf']:
            continue
        # Conf ceiling (block alta conf)
        if params['conf_ceiling'] is not None and t['confidence'] >= params['conf_ceiling']:
            continue
        # ATR floor
        if params['atr_floor'] is not None and t['avg_range_pips'] < params['atr_floor']:
            continue
        # ATR ceiling
        if params['atr_ceiling'] is not None and t['avg_range_pips'] > params['atr_ceiling']:
            continue
        # Block counter-HTF
        if params['block_counter_htf']:
            htf = t['htf_bias']
            if htf and htf != 'neutral':
                if t['direction'] == 'CALL' and htf == 'bearish':
                    continue
                if t['direction'] == 'PUT' and htf == 'bullish':
                    continue
        # Block counter-trend (M5 trend vs direction)
        if params['block_counter_trend']:
            tr = t['market_trend']
            if tr and tr != 'neutral':
                if t['direction'] == 'CALL' and tr == 'bearish':
                    continue
                if t['direction'] == 'PUT' and tr == 'bullish':
                    continue
        # Block specific impact range
        if params['min_impact'] is not None and t['impact_score'] < params['min_impact']:
            continue

        out.append(t)
    return out


def compute_stats(trades):
    """Calcula PF, WR, PnL, etc."""
    if not trades:
        return {
            'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'sum_pnl': 0.0, 'avg_pnl': 0,
            'avg_win': 0, 'avg_loss': 0, 'profit_factor': 0,
            'score': -999  # ranking score
        }
    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    sum_pnl = sum(t['mt5_pnl'] or 0 for t in trades)
    sum_wins = sum(t['mt5_pnl'] or 0 for t in wins)
    sum_losses = abs(sum(t['mt5_pnl'] or 0 for t in losses))
    pf = sum_wins / sum_losses if sum_losses > 0 else (999 if sum_wins > 0 else 0)
    wr = len(wins) / len(trades) * 100

    # Score: combina PF, PnL, y muestra (penaliza muestras chicas)
    # PF * PnL * sqrt(min(n, 50)/50)
    import math
    sample_factor = math.sqrt(min(len(trades), 50) / 50)
    score = pf * sum_pnl * sample_factor if sum_pnl > 0 else -abs(sum_pnl)

    return {
        'total': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(wr, 1),
        'sum_pnl': round(sum_pnl, 2),
        'avg_pnl': round(sum_pnl / len(trades), 2),
        'avg_win': round(sum_wins / len(wins), 2) if wins else 0,
        'avg_loss': round(-sum_losses / len(losses), 2) if losses else 0,
        'profit_factor': round(pf, 2),
        'score': round(score, 2),
    }


# Worker function (top-level for multiprocessing pickle)
_TRADES_CACHE = None


def _init_worker(track):
    global _TRADES_CACHE
    _TRADES_CACHE = load_trades(track)


def evaluate_combo(params):
    """Worker: evalúa una combo de parámetros."""
    global _TRADES_CACHE
    filtered = apply_filters(_TRADES_CACHE, params)
    stats = compute_stats(filtered)
    stats['params'] = params
    return stats


def walk_forward_validate(trades, params, train_pct=0.7):
    """Train/test split: optimiza sobre primeros train_pct, valida sobre el resto.
    Detecta overfitting si test PnL << train PnL."""
    n = len(trades)
    split = int(n * train_pct)
    train = trades[:split]
    test = trades[split:]
    train_filtered = apply_filters(train, params)
    test_filtered = apply_filters(test, params)
    return {
        'train': compute_stats(train_filtered),
        'test': compute_stats(test_filtered),
        'overfitting_score': (
            compute_stats(train_filtered)['profit_factor'] -
            compute_stats(test_filtered)['profit_factor']
        )  # >1.0 = overfitting probable
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=8, help='# cores')
    p.add_argument('--top', type=int, default=15, help='top N to display')
    p.add_argument('--min-trades', type=int, default=10, help='min trades to consider valid')
    p.add_argument('--track', default='all', choices=['all', 'm5', 'm15', 'h1'])
    p.add_argument('--validate', action='store_true', help='walk-forward validation top result')
    args = p.parse_args()

    print(f'=== Backtest paralelo AIdan ===')
    print(f'Workers: {args.workers} cores')
    print(f'Track: {args.track}')

    # Load baseline
    trades_all = load_trades(args.track)
    print(f'Trades disponibles: {len(trades_all)}')
    if len(trades_all) < args.min_trades:
        print(f'ERROR: muestra muy chica ({len(trades_all)} < {args.min_trades})')
        return

    # Baseline (sin filtros)
    base = compute_stats(trades_all)
    print(f'Baseline (sin filtros adicionales):')
    print(f'  n={base["total"]} WR={base["win_rate"]}% PnL=${base["sum_pnl"]} PF={base["profit_factor"]}')
    print()

    # Define grid de parametros
    grid = {
        'min_conf': [None, 50, 55, 60, 65, 70],
        'conf_ceiling': [None, 75, 80, 85, 90],
        'atr_floor': [None, 1.5, 2.0, 2.5, 3.0],
        'atr_ceiling': [None, 5.0, 6.0, 7.0, 8.0],
        'block_counter_htf': [False, True],
        'block_counter_trend': [False, True],
        'min_impact': [None, 50, 60, 70],
    }

    keys = list(grid.keys())
    combos = list(product(*grid.values()))
    print(f'Combinaciones a evaluar: {len(combos)}')
    print(f'Estimacion serial: ~{len(combos) * 0.05 / 60:.1f} min, paralelo: ~{len(combos) * 0.05 / args.workers / 60:.1f} min')
    print()

    param_dicts = [dict(zip(keys, c)) for c in combos]

    t0 = time.time()
    with mp.Pool(args.workers, initializer=_init_worker, initargs=(args.track,)) as pool:
        results = pool.map(evaluate_combo, param_dicts)
    elapsed = time.time() - t0
    print(f'Completado en {elapsed:.1f}s ({len(combos)/elapsed:.0f} combos/s)')
    print()

    # Filter: muestra suficiente
    valid = [r for r in results if r['total'] >= args.min_trades]
    print(f'Combos validos (n>={args.min_trades}): {len(valid)}')
    if not valid:
        print('Sin combos validos. Bajar --min-trades.')
        return

    # Sort by score
    valid.sort(key=lambda r: r['score'], reverse=True)

    # Display top N
    print(f'\n=== TOP {args.top} (ordenado por PF * PnL * sample_factor) ===')
    print(f'{"Rank":<5}{"Score":>8}{"PF":>6}{"WR":>6}{"PnL":>9}{"n":>5}  Filters')
    print('-' * 100)
    for i, r in enumerate(valid[:args.top], 1):
        params_str = ', '.join(f"{k}={v}" for k, v in r['params'].items() if v not in (None, False))
        if not params_str:
            params_str = '(sin filtros)'
        pnl_str = f"${r['sum_pnl']:+.2f}"
        print(f'{i:<5}{r["score"]:>8.2f}{r["profit_factor"]:>6.2f}{r["win_rate"]:>5.0f}%{pnl_str:>9}{r["total"]:>5}  {params_str[:80]}')

    print('\n=== Mejor combo detalle ===')
    best = valid[0]
    print(json.dumps(best, indent=2))

    # Walk-forward validation: detectar overfitting
    if args.validate:
        print('\n=== WALK-FORWARD VALIDATION (top 5) ===')
        print('Si train PF >> test PF -> overfitting. Diferencia >0.5 es señal de alarma.')
        print(f'{"Rank":<5}{"Train PF":>10}{"Test PF":>10}{"Test n":>8}{"Test PnL":>10}{"Diff":>8}  Status')
        print('-' * 80)
        for i, r in enumerate(valid[:5], 1):
            wf = walk_forward_validate(trades_all, r['params'])
            diff = wf['train']['profit_factor'] - wf['test']['profit_factor']
            test_pnl = wf['test']['sum_pnl']
            test_n = wf['test']['total']
            status = 'OK' if diff < 0.3 else ('WARN' if diff < 0.7 else 'OVERFIT')
            print(f'{i:<5}{wf["train"]["profit_factor"]:>10.2f}{wf["test"]["profit_factor"]:>10.2f}{test_n:>8}{test_pnl:>+9.2f}{diff:>+8.2f}  {status}')

        # Show winner: highest test PF with reasonable n
        valid_test = []
        for r in valid[:50]:
            wf = walk_forward_validate(trades_all, r['params'])
            if wf['test']['total'] >= 5:  # min sample en test
                r['test_pf'] = wf['test']['profit_factor']
                r['test_pnl'] = wf['test']['sum_pnl']
                r['test_n'] = wf['test']['total']
                r['overfit_diff'] = wf['train']['profit_factor'] - wf['test']['profit_factor']
                valid_test.append(r)
        if valid_test:
            valid_test.sort(key=lambda r: r['test_pf'] * r['test_pnl'] if r['test_pnl'] > 0 else -abs(r['test_pnl']), reverse=True)
            print(f'\n=== TOP 5 robust (mejor test_PF, n_test>=5) ===')
            print(f'{"Rank":<5}{"Test PF":>10}{"Test PnL":>10}{"Test n":>8}{"Diff":>8}  Filters')
            print('-' * 100)
            for i, r in enumerate(valid_test[:5], 1):
                params_str = ', '.join(f"{k}={v}" for k, v in r['params'].items() if v not in (None, False))
                print(f'{i:<5}{r["test_pf"]:>10.2f}{r["test_pnl"]:>+9.2f}{r["test_n"]:>8}{r["overfit_diff"]:>+8.2f}  {params_str[:75]}')


if __name__ == '__main__':
    main()
