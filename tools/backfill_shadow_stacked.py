"""
backfill_shadow_stacked.py — Evaluar el EFECTO COMBINADO de aplicar
multiple pending_changes simultaneamente sobre trade_archive.

User insight (19 may): si auto_applier aplica cambios secuencialmente,
pueden contrarrestarse o solaparse. El shadow validation individual
NO captura esto.

Este script:
1. Carga pending_changes con status='shadow_validating'
2. Evalua TODAS las combinaciones (single + pairs + triples + all)
3. Para cada combo, aplica TODOS sus filtros simultaneamente al archive
4. Reporta PF/PnL resultante por combo
5. Identifica el mejor combo (no solo el mejor cambio individual)
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from itertools import combinations

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.common.db import DB_PATH
from src.optimizer.shadow_runner import _passes_change_filter


def load_pending_changes(conn):
    """Load all changes that COULD be applied (shadow_validating + validated + applied)."""
    cur = conn.cursor()
    cur.execute("""SELECT id, change_type, params_json, status
                   FROM pending_changes
                   WHERE status IN ('shadow_validating', 'validated', 'applied')
                   ORDER BY id""")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_archive_trades(conn):
    cur = conn.cursor()
    cur.execute("""SELECT id, strategy_id, direction, result,
                          mt5_pnl, sl_pips, tp_pips, sl_hit, tp_hit,
                          confidence, trigger_type, setup_type,
                          htf_bias, session, hour_utc, day_of_week,
                          avg_range_pips, entry_price, stop_loss, take_profit
                   FROM trade_archive
                   WHERE result IN ('win', 'loss') AND mt5_pnl IS NOT NULL""")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def trade_to_signal(t):
    return {
        'direction': t.get('direction', ''),
        'confidence': t.get('confidence') or 0,
        'trigger_type': t.get('trigger_type') or '',
        'setup_type': t.get('setup_type') or t.get('trigger_type') or '',
        'session': t.get('session') or '',
        'hour_utc': t.get('hour_utc'),
        'day_of_week': t.get('day_of_week'),
        'htf_bias': t.get('htf_bias') or '',
        'avg_range_pips': t.get('avg_range_pips') or 0,
    }


def applies_combo(trade, combo_changes):
    """True si el trade PASA todos los filtros del combo (ningun cambio lo bloquea)."""
    signal = trade_to_signal(trade)
    for change in combo_changes:
        params = json.loads(change['params_json'] or '{}')
        passes, _ = _passes_change_filter(signal, change['change_type'], params)
        if not passes:
            return False
    return True


def evaluate_combo(trades, combo_changes):
    """Aplica todos los filtros del combo. Retorna stats de los que SOBREVIVEN."""
    survived = [t for t in trades if applies_combo(t, combo_changes)]
    n = len(survived)
    if n == 0:
        return {'n': 0, 'wr': 0, 'pf': 0, 'pnl': 0, 'wins': 0, 'losses': 0}
    pnls = [t.get('mt5_pnl', 0) or 0 for t in survived]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    pf = gw / gl if gl > 0 else (999 if gw > 0 else 0)
    return {
        'n': n, 'wins': wins, 'losses': n - wins,
        'wr': round(wins * 100 / n, 1),
        'pf': round(pf, 2),
        'pnl': round(sum(pnls), 2),
    }


def main():
    conn = sqlite3.connect(DB_PATH)
    print("=" * 90)
    print(f"BACKFILL SHADOW APILADO (combinaciones) — {datetime.now()}")
    print("=" * 90)

    changes = load_pending_changes(conn)
    trades = load_archive_trades(conn)
    print(f"\nCambios candidatos: {len(changes)}")
    for c in changes:
        params = json.loads(c['params_json'] or '{}')
        print(f"  #{c['id']:2d} {c['change_type']:22s} {params}")
    print(f"Trades archivo: {len(trades)}")

    # Baseline (sin filtros)
    baseline = evaluate_combo(trades, [])
    print(f"\nBASELINE (sin filtros): {baseline['n']} trades, WR {baseline['wr']:.1f}%, PF {baseline['pf']:.2f}, PnL ${baseline['pnl']:+.2f}")

    # Evaluar combinaciones por tamano
    print(f"\n{'Size':>4s} {'Combo (change IDs)':35s} {'n':>4s} {'WR':>5s} {'PF':>5s} {'PnL':>8s} {'ΔPnL':>8s}")
    print("-" * 95)

    all_results = []
    for size in range(1, min(len(changes) + 1, 5)):  # max 4 cambios apilados
        for combo in combinations(changes, size):
            stats = evaluate_combo(trades, combo)
            combo_ids = ','.join(f"#{c['id']}" for c in combo)
            delta_pnl = stats['pnl'] - baseline['pnl']
            all_results.append({
                'size': size, 'ids': combo_ids,
                'stats': stats, 'delta_pnl': delta_pnl,
                'combo': combo,
            })

    # Top 15 por delta_pnl
    print("\n--- TOP 15 COMBOS POR MEJOR PnL ---")
    for r in sorted(all_results, key=lambda x: -x['delta_pnl'])[:15]:
        s = r['stats']
        marker = '★' if r['delta_pnl'] > 50 else ('✓' if r['delta_pnl'] > 30 else '~')
        print(f"  {r['size']:>4d} {r['ids']:35s} {s['n']:>4d} {s['wr']:>4.1f}% {s['pf']:>5.2f} ${s['pnl']:+7.2f} ${r['delta_pnl']:+7.2f} {marker}")

    # Top 5 por mejor PF (cualidad)
    print("\n--- TOP 5 COMBOS POR MEJOR PF ---")
    for r in sorted(all_results, key=lambda x: -x['stats']['pf'])[:5]:
        s = r['stats']
        if s['n'] < 20: continue  # exigir muestra >= 20
        print(f"  {r['size']:>4d} {r['ids']:35s} {s['n']:>4d} {s['wr']:>4.1f}% {s['pf']:>5.2f} ${s['pnl']:+7.2f} ${r['delta_pnl']:+7.2f}")

    # All-in: aplicar todos
    all_changes_stats = evaluate_combo(trades, changes)
    print(f"\n--- TODOS APLICADOS A LA VEZ ---")
    print(f"  Aplicar TODOS ({len(changes)}): {all_changes_stats['n']} trades, WR {all_changes_stats['wr']:.1f}%, PF {all_changes_stats['pf']:.2f}, PnL ${all_changes_stats['pnl']:+.2f}")
    print(f"  Delta vs baseline: ${all_changes_stats['pnl'] - baseline['pnl']:+.2f}")
    print(f"  Trades bloqueados: {baseline['n'] - all_changes_stats['n']} ({(baseline['n'] - all_changes_stats['n'])*100/baseline['n']:.0f}%)")

    # Mejor single vs mejor combo
    print(f"\n--- COMPARACION: SINGLES vs COMBOS ---")
    singles = [r for r in all_results if r['size'] == 1]
    best_single = max(singles, key=lambda x: x['delta_pnl'])
    best_overall = max(all_results, key=lambda x: x['delta_pnl'])
    print(f"  Mejor cambio individual: {best_single['ids']} ΔPnL ${best_single['delta_pnl']:+.2f} (size 1)")
    print(f"  Mejor combo total      : {best_overall['ids']} ΔPnL ${best_overall['delta_pnl']:+.2f} (size {best_overall['size']})")
    extra_value = best_overall['delta_pnl'] - best_single['delta_pnl']
    if extra_value > 0:
        print(f"  ★ APILAR aporta extra ${extra_value:+.2f} vs solo el mejor individual")
    else:
        print(f"  ⚠ Apilar NO aporta valor adicional (overlap o cancellation)")

    conn.close()


if __name__ == '__main__':
    main()
