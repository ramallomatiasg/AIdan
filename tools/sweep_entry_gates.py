"""
sweep_entry_gates.py — Backlog #2: tuning de los Entry Quality Gates (v3.34.0).

Los gates actuales (technical.py): bloquean un trade structure si
  velocity_5c_aligned > 6.0p   O   body_atr_ratio > 1.3
Ambos thresholds fueron elegidos a ojo. Este sweep recorre
  vel  in {3,4,5,6,7,8}
  body in {1.1,1.2,1.3,1.4,1.5}
= 30 combinaciones, sobre trade_archive (resultados reales) + features enriquecidos.

Para cada combo:
  - survivors = trades que PASAN ambos gates (vel<=vt AND body<=bt)
  - blocked   = trades que algun gate removeria
  - mide WR/PF/PnL de survivors (lo que quedaria operando)
  - corre el GATE DE SIGNIFICANCIA sobre el set BLOQUEADO: ¿esos trades son
    significativamente PEORES que baseline? (si si -> el gate remueve perdedores reales)
Rankea por PF de survivors.

CAVEATS (honestos, mismos que el backtest H1/M15):
  - El archive solo tiene trades TOMADOS. Los gates solo REMUEVEN, nunca agregan,
    asi que el sweep mide "de lo que tomamos, que conviene sacar". No mide trades
    que gates mas laxos hubieran agregado (no existen en el archive).
  - Trades tomados bajo filtros historicos heterogeneos (sesgo de seleccion).
  - Sin friccion variable. PF de survivors infla ~ vs produccion real.
NO aplicar ningun combo al live sin que el blocked-set pase significancia.
"""
import csv
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.db import DB_PATH
from src.optimizer.significance import verify_finding, compute_baseline_wr

ENRICHED_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'trade_archive_enriched.csv')

VEL_GRID = [3, 4, 5, 6, 7, 8]
BODY_GRID = [1.1, 1.2, 1.3, 1.4, 1.5]


def load_data(trigger_filter=None):
    """Join enriched features (por trade_id) con trade_archive (outcome).
    Returns list de dicts: {pnl, vel_aligned, body_atr, trigger}."""
    # 1. enriched features
    feats = {}
    with open(ENRICHED_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                tid = int(float(row['trade_id']))
                feats[tid] = {
                    'vel_aligned': float(row.get('velocity_5c_aligned') or 0),
                    'body_atr': float(row.get('body_atr_ratio') or 0),
                }
            except (ValueError, TypeError):
                continue

    # 2. outcomes desde trade_archive — probamos join por id y por strategy_id
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""SELECT id, strategy_id, mt5_pnl, trigger_type
                   FROM trade_archive WHERE mt5_pnl IS NOT NULL""")
    rows = cur.fetchall()
    conn.close()

    # Detectar la mejor clave de join (la que matchea mas)
    match_by_id = sum(1 for r in rows if r[0] in feats)
    match_by_sid = sum(1 for r in rows if r[1] in feats)
    key_idx = 0 if match_by_id >= match_by_sid else 1

    data = []
    for r in rows:
        k = r[key_idx]
        if k not in feats:
            continue
        if trigger_filter and r[3] != trigger_filter:
            continue
        data.append({
            'pnl': float(r[2]),
            'vel_aligned': feats[k]['vel_aligned'],
            'body_atr': feats[k]['body_atr'],
            'trigger': r[3],
        })
    return data, ('id' if key_idx == 0 else 'strategy_id'), (match_by_id, match_by_sid)


def metrics(trades):
    """WR, PF, PnL, n, wins de una lista de trades."""
    n = len(trades)
    if n == 0:
        return {'n': 0, 'wins': 0, 'wr': 0, 'pf': 0, 'pnl': 0}
    wins = sum(1 for t in trades if t['pnl'] > 0)
    gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gl = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
    pf = gp / gl if gl > 0 else (999 if gp > 0 else 0)
    return {'n': n, 'wins': wins, 'wr': wins / n, 'pf': pf,
            'pnl': sum(t['pnl'] for t in trades)}


def run_sweep(trigger_filter=None):
    data, join_key, matches = load_data(trigger_filter)
    baseline_wr = compute_baseline_wr()

    print(f"Join key: {join_key} (matches id={matches[0]}, sid={matches[1]})")
    print(f"Trades cargados: {len(data)}" + (f" (filtro trigger={trigger_filter})" if trigger_filter else " (todos)"))
    base = metrics(data)
    print(f"BASELINE (sin gates): n={base['n']} WR={base['wr']*100:.1f}% PF={base['pf']:.2f} PnL=${base['pnl']:.2f}")
    print(f"Baseline WR archive completo: {baseline_wr*100:.2f}%\n")

    results = []
    for vt in VEL_GRID:
        for bt in BODY_GRID:
            survivors = [t for t in data if t['vel_aligned'] <= vt and t['body_atr'] <= bt]
            blocked = [t for t in data if not (t['vel_aligned'] <= vt and t['body_atr'] <= bt)]
            s = metrics(survivors)
            b = metrics(blocked)
            # Significancia: el set BLOQUEADO es significativamente peor que baseline?
            sig = verify_finding(b['n'], b['wins'], baseline_wr=baseline_wr, direction='worse')
            results.append({
                'vel': vt, 'body': bt,
                'surv_n': s['n'], 'surv_wr': s['wr'], 'surv_pf': s['pf'], 'surv_pnl': s['pnl'],
                'blk_n': b['n'], 'blk_wr': b['wr'],
                'blk_significant': sig.significant, 'blk_pval': sig.p_value,
                'blk_verdict': sig.verdict,
            })

    # Rankear por PF de survivors
    results.sort(key=lambda r: r['surv_pf'], reverse=True)

    print(f"{'vel':>3} {'body':>4} | {'surv_n':>6} {'surv_WR':>7} {'surv_PF':>7} {'surv_PnL':>9} | {'blk_n':>5} {'blk_WR':>6} {'blk_sig?':>8}")
    print('-' * 78)
    cur_marker = ''
    for r in results:
        marker = ' <-- ACTUAL (6/1.3)' if (r['vel'] == 6 and r['body'] == 1.3) else ''
        sig_str = 'SI' if r['blk_significant'] else 'ruido'
        print(f"{r['vel']:>3} {r['body']:>4} | {r['surv_n']:>6} {r['surv_wr']*100:>6.1f}% {r['surv_pf']:>7.2f} ${r['surv_pnl']:>8.2f} | "
              f"{r['blk_n']:>5} {r['blk_wr']*100:>5.1f}% {sig_str:>8}{marker}")

    print('\n' + '=' * 78)
    print("VEREDICTO:")
    # El mejor combo cuyo blocked-set sea SIGNIFICATIVAMENTE peor (gate justificado)
    valid = [r for r in results if r['blk_significant'] and r['blk_n'] >= 25]
    actual = next((r for r in results if r['vel'] == 6 and r['body'] == 1.3), None)
    if actual:
        print(f"  Gate ACTUAL (6/1.3): survivors PF={actual['surv_pf']:.2f} WR={actual['surv_wr']*100:.1f}% "
              f"(n={actual['surv_n']}) | blocked significativo: {'SI' if actual['blk_significant'] else 'NO (ruido)'}")
    if valid:
        best = max(valid, key=lambda r: r['surv_pf'])
        print(f"  Mejor combo CON blocked-set significativo: vel={best['vel']} body={best['body']} "
              f"-> survivors PF={best['surv_pf']:.2f} WR={best['surv_wr']*100:.1f}% (n={best['surv_n']})")
        print(f"    blocked n={best['blk_n']} WR={best['blk_wr']*100:.1f}% p={best['blk_pval']:.4f}")
    else:
        print("  NINGUN combo tiene un blocked-set estadisticamente significativo.")
        print("  -> Los gates actuales NO estan removiendo perdedores de forma distinguible del ruido.")
        print("  -> Recomendacion: NO tunear gates con esta muestra. Esperar mas trades.")
    return results


if __name__ == '__main__':
    trig = sys.argv[1] if len(sys.argv) > 1 else None
    run_sweep(trigger_filter=trig)
