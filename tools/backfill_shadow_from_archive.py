"""
backfill_shadow_from_archive.py — Regenerar shadow_strategies + shadow_trades
para todos los pending_changes en status='shadow_validating' usando trade_archive
como fuente de verdad.

Por que: el shadow runner tenia bug (v3.31.7-) que pasaba hour_utc=None,
session='', setup_type='' al filter. Los shadow_strategies que se crearon
NUNCA disparaban filtros block_hour/block_session/block_setup correctamente.

Despues del fix v3.31.8, podemos pre-calentar usando el archive: cada trade
del archive tiene sus features completas (hour_utc, session, setup_type, etc)
Y su outcome REAL conocido. No necesitamos simular — usamos el pnl real.

Resultado: en vez de esperar 3-5 dias para 30 shadow_trades por cambio,
tenemos 200+ shadow_trades de un saque -> validation inmediata.

Uso:
    python tools/backfill_shadow_from_archive.py            # dry-run (no escribe)
    python tools/backfill_shadow_from_archive.py --commit   # ejecuta de verdad
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.common.db import DB_PATH
from src.optimizer.shadow_runner import _passes_change_filter


def load_pending_changes(conn):
    """Get pending_changes en status='shadow_validating'."""
    cur = conn.cursor()
    cur.execute("""SELECT id, change_type, params_json
                   FROM pending_changes WHERE status='shadow_validating'""")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def load_archive_trades(conn):
    """Get trades de archive con resultado y feature completos."""
    cur = conn.cursor()
    cur.execute("""SELECT id, strategy_id, direction, result, pips, sl_pips, tp_pips,
                          sl_hit, tp_hit, confidence, trigger_type, setup_type,
                          market_trend, trend_strength, rsi_at_entry, htf_bias,
                          volatility, avg_range_pips, session, hour_utc, day_of_week,
                          mt5_pnl, entry_price, stop_loss, take_profit, created_at
                   FROM trade_archive
                   WHERE result IN ('win', 'loss')
                     AND mt5_pnl IS NOT NULL
                   ORDER BY id""")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def trade_to_signal_dict(trade):
    """Convert trade_archive row a signal dict que entiende _passes_change_filter."""
    return {
        'direction': trade.get('direction', ''),
        'entry_price': trade.get('entry_price', 0),
        'stop_loss': trade.get('stop_loss', 0),
        'take_profit': trade.get('take_profit', 0),
        'sl_pips': trade.get('sl_pips') or 0,
        'tp_pips': trade.get('tp_pips') or 0,
        'confidence': trade.get('confidence') or 0,
        'trigger_type': trade.get('trigger_type') or '',
        # setup_type: si vacio, fallback a trigger_type (consistente con fix v3.31.8)
        'setup_type': trade.get('setup_type') or trade.get('trigger_type') or '',
        'session': trade.get('session') or '',
        'hour_utc': trade.get('hour_utc'),
        'day_of_week': trade.get('day_of_week'),
        'htf_bias': trade.get('htf_bias') or '',
        'avg_range_pips': trade.get('avg_range_pips') or 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', action='store_true', help='Ejecutar writes (default: dry-run)')
    parser.add_argument('--clear-existing', action='store_true', help='Borrar shadow_strategies viejos antes (recomendado para consistencia)')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("=" * 70)
    print(f"BACKFILL SHADOW FROM ARCHIVE — {datetime.now()}")
    print(f"Modo: {'COMMIT' if args.commit else 'DRY-RUN'}")
    print("=" * 70)

    # 1. Pending changes
    changes = load_pending_changes(conn)
    print(f"\nPending changes activos (shadow_validating): {len(changes)}")
    for c in changes:
        params = json.loads(c['params_json'] or '{}')
        print(f"  #{c['id']:2d} {c['change_type']:22s} {params}")

    if not changes:
        print("Sin cambios pendientes. Nada que hacer.")
        return

    # 2. Trade archive
    trades = load_archive_trades(conn)
    print(f"\nTrade archive (resultados conocidos): {len(trades)}")
    if not trades:
        print("Sin trades en archive. Aborting.")
        return

    # 3. Procesar cada cambio
    print(f"\n=== Procesando {len(changes)} cambios contra {len(trades)} trades ===")

    summary = {}
    for change in changes:
        change_id = change['id']
        try:
            params = json.loads(change['params_json'] or '{}')
        except Exception:
            print(f"  #{change_id}: params_json invalid, skip")
            continue

        # Limpiar shadow_strategies/trades viejos si --clear-existing
        if args.commit and args.clear_existing:
            cur.execute("""DELETE FROM shadow_trades WHERE shadow_strategy_id IN (
                           SELECT id FROM shadow_strategies WHERE pending_change_id=?)""",
                        (change_id,))
            n_st_del = cur.rowcount
            cur.execute("DELETE FROM shadow_strategies WHERE pending_change_id=?", (change_id,))
            n_ss_del = cur.rowcount
            print(f"  #{change_id}: cleared {n_ss_del} shadow_strategies + {n_st_del} shadow_trades")

        # Para cada trade del archive, evaluar contra el filtro
        n_taken = 0
        n_skipped = 0
        n_skip_dup = 0
        gw_taken = 0.0
        gl_taken = 0.0
        wins_taken = 0
        for trade in trades:
            signal = trade_to_signal_dict(trade)
            passes, skip_reason = _passes_change_filter(signal, change['change_type'], params)
            decision = 'taken' if passes else 'skipped'

            if args.commit:
                # Dedup: si ya existe shadow_strategy con este base_strategy_id, skip
                strategy_id = trade.get('strategy_id') or trade.get('id')
                cur.execute("""SELECT id FROM shadow_strategies
                               WHERE pending_change_id=? AND base_strategy_id=?""",
                            (change_id, strategy_id))
                if cur.fetchone():
                    n_skip_dup += 1
                    continue

                # Insertar shadow_strategy
                cur.execute("""INSERT INTO shadow_strategies (
                    pending_change_id, base_strategy_id, config_overrides_json,
                    direction, entry_price, stop_loss, take_profit, sl_pips, tp_pips,
                    confidence, trigger_type, setup_type, session, hour_utc,
                    day_of_week, htf_bias, avg_range_pips,
                    shadow_decision, skip_reason, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    change_id, strategy_id, change['params_json'],
                    signal['direction'], signal['entry_price'], signal['stop_loss'],
                    signal['take_profit'], signal['sl_pips'], signal['tp_pips'],
                    signal['confidence'], signal['trigger_type'], signal['setup_type'],
                    signal['session'], signal['hour_utc'], signal['day_of_week'],
                    signal['htf_bias'], signal['avg_range_pips'],
                    decision, skip_reason, trade.get('created_at') or datetime.utcnow().isoformat()
                ))
                ss_id = cur.lastrowid

                # Si decision='taken', insertar shadow_trade con outcome REAL del archive
                if decision == 'taken':
                    cur.execute("""INSERT INTO shadow_trades (
                        shadow_strategy_id, simulated_exit_price, simulated_pnl,
                        simulated_pips, sl_hit, tp_hit, expiry_hit, exit_reason
                    ) VALUES (?,?,?,?,?,?,?,?)""", (
                        ss_id,
                        0,  # no tenemos exit_price exacto del archive aqui
                        trade.get('mt5_pnl', 0),
                        trade.get('pips', 0),
                        trade.get('sl_hit') or 0,
                        trade.get('tp_hit') or 0,
                        1 if not (trade.get('sl_hit') or trade.get('tp_hit')) else 0,
                        'sl' if trade.get('sl_hit') else ('tp' if trade.get('tp_hit') else 'expiry')
                    ))

            # Stats (sea dry-run o commit)
            if decision == 'taken':
                n_taken += 1
                pnl = trade.get('mt5_pnl', 0) or 0
                if pnl > 0:
                    gw_taken += pnl
                    wins_taken += 1
                else:
                    gl_taken += abs(pnl)
            else:
                n_skipped += 1

        # PF/WR proyectado
        pf = gw_taken / gl_taken if gl_taken > 0 else (999 if gw_taken > 0 else 0)
        wr = wins_taken * 100 / n_taken if n_taken > 0 else 0
        summary[change_id] = {
            'type': change['change_type'], 'params': params,
            'taken': n_taken, 'skipped': n_skipped, 'dup': n_skip_dup,
            'wins_taken': wins_taken, 'wr': wr, 'pf': pf,
            'gw': gw_taken, 'gl': gl_taken,
            'pnl': round(gw_taken - gl_taken, 2)
        }

    # 4. Actualizar shadow_pf/shadow_trades_count en pending_changes si --commit
    if args.commit:
        for change_id, s in summary.items():
            cur.execute("""UPDATE pending_changes
                           SET shadow_trades_count=?, shadow_pf=?, shadow_wr=?
                           WHERE id=?""",
                        (s['taken'], round(s['pf'], 2), round(s['wr'], 1), change_id))
        conn.commit()

    # 5. Print summary
    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)
    # Get baseline para comparar
    cur.execute("""SELECT mt5_pnl FROM trade_archive WHERE result IN ('win','loss')
                   AND mt5_pnl IS NOT NULL""")
    pnls = [r[0] for r in cur.fetchall() if r[0] is not None]
    n_total = len(pnls)
    bw = sum(1 for p in pnls if p > 0)
    bgw = sum(p for p in pnls if p > 0)
    bgl = abs(sum(p for p in pnls if p < 0))
    baseline_pf = bgw / bgl if bgl > 0 else 0
    baseline_wr = bw * 100 / n_total if n_total else 0
    print(f"Baseline (archive completo): {n_total} trades, WR {baseline_wr:.1f}%, PF {baseline_pf:.2f}, PnL ${sum(pnls):+.2f}")
    print(f"{'#':>3s} {'tipo':22s} {'params':40s} {'taken':>5s} {'skip':>5s} {'WR':>5s} {'PF':>5s} {'PnL':>8s} {'Δ PF':>6s}")
    print("-" * 110)
    for change_id, s in sorted(summary.items()):
        delta_pf = s['pf'] - baseline_pf
        verdict = '✓✓' if delta_pf > 0.15 else ('✓' if delta_pf > 0 else ('~' if delta_pf > -0.05 else '✗'))
        print(f"  {change_id:>2d} {s['type']:22s} {str(s['params'])[:40]:40s} {s['taken']:>5d} {s['skipped']:>5d} {s['wr']:>4.1f}% {s['pf']:>5.2f} ${s['pnl']:+7.2f} {delta_pf:>+6.2f} {verdict}")
    print()
    print(f"Threshold para auto-validate: shadow PF >= baseline + 0.15 = {baseline_pf + 0.15:.2f}")
    print(f"Cambios que cruzarian el threshold: {sum(1 for s in summary.values() if s['pf'] >= baseline_pf + 0.15)}")

    if not args.commit:
        print("\n⚠ DRY-RUN — agregar --commit para aplicar los writes.")

    conn.close()


if __name__ == '__main__':
    main()
