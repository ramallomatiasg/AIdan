# -*- coding: utf-8 -*-
"""
measure_dist_to_level.py — RETRO read-only (Paso 0 del diseno Grupo B, 17-jul).

Pregunta: la DISTANCIA precio<->nivel al fill (cruda y normalizada por ATR) separa
ganar/perder DENTRO de cada track? Usa level_quality_log (key_level de cada senal de
structure ejecutada) JOIN trade_archive (entry_price + mt5_pnl REAL) — o sea NO re-simula
nada, mide con P&L de verdad. Gateado por level_touches>=2 (nivel validado).

Hallazgo 17-jul (n=74): el edge vive en la entrada PEGADA al nivel:
  <=0.5 ATR -> 65% WR (+$24, p=0.006)  vs  >1 ATR -> ~37% WR (baseline, negativo).
El lever es TIGHTEN (breakout window ~1 ATR), NO widen. Refuto la premisa "ensanchar
ayuda a h1/m15". A esa fecha n<25 en la celda estrella (a 2 trades del gate) -> re-correr
en cada checkpoint hasta que verify_finding pase (n>=25 y CI que no cruce baseline 37.4%).

Uso: python tools/measure_dist_to_level.py
READ-ONLY (solo SELECT). No necesita MT5.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.optimizer.significance import verify_finding  # noqa: E402

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')


def _load(conn):
    rows = conn.execute(
        """SELECT l.direction, l.level_touches, l.key_level, a.entry_price, a.trigger_type,
                  a.result, a.mt5_pnl, a.avg_range_pips
           FROM level_quality_log l JOIN trade_archive a ON a.strategy_id = l.strategy_id
           WHERE a.entry_price > 0 AND l.key_level > 0 AND a.mt5_pnl IS NOT NULL
                 AND l.level_touches >= 2"""
    ).fetchall()
    data = []
    for r in rows:
        dist = abs(r['entry_price'] - r['key_level']) * 10000
        atr = r['avg_range_pips'] or 0
        data.append({
            'track': r['trigger_type'], 'dist': dist,
            'datr': (dist / atr) if atr > 0 else None,
            'win': r['result'] == 'win', 'pnl': r['mt5_pnl'],
        })
    return data


def _report(rows, label):
    if not rows:
        print(f'  {label:24} n=0')
        return
    n = len(rows)
    w = sum(1 for x in rows if x['win'])
    p = sum(x['pnl'] for x in rows)
    print(f'  {label:24} n={n:>3} WR={round(100*w/n):>3}% PnL={round(p,1):>8}')


def _sig(rows, label, min_n=15):
    n = len(rows)
    if n < min_n:
        return
    w = sum(1 for x in rows if x['win'])
    print(f'  {label}: {verify_finding(n, w)}')


def main():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    data = _load(conn)
    print(f'Total joinable (touches>=2): {len(data)}')

    for track in ['m15_structure', 'h1_structure', 'structure', 'smc']:
        sub = [x for x in data if x['track'] == track]
        if not sub:
            continue
        print(f'\n=== {track} (n={len(sub)}) — dist RAW (pips) ===')
        _report([x for x in sub if x['dist'] <= 3], 'dist<=3p')
        _report([x for x in sub if 3 < x['dist'] <= 7], 'dist 3-7p')
        _report([x for x in sub if x['dist'] > 7], 'dist>7p')

    alld = [x for x in data if x['datr'] is not None]
    print(f'\n=== TODOS los tracks — dist/ATR (normalizada) (n={len(alld)}) ===')
    _report([x for x in alld if x['datr'] <= 0.5], 'dist<=0.5 ATR')
    _report([x for x in alld if 0.5 < x['datr'] <= 1.0], 'dist 0.5-1.0 ATR')
    _report([x for x in alld if 1.0 < x['datr'] <= 2.0], 'dist 1.0-2.0 ATR')
    _report([x for x in alld if x['datr'] > 2.0], 'dist>2.0 ATR')

    print('\n=== SIGNIFICANCIA (verify_finding vs baseline 37.4%) ===')
    _sig([x for x in alld if x['datr'] <= 0.5], 'dist<=0.5ATR (celda estrella)')
    _sig([x for x in alld if x['datr'] <= 1.0], 'dist<=1.0ATR')
    _sig([x for x in alld if x['datr'] > 1.0], 'dist>1.0ATR')
    print('\n  (Activar TIGHTEN solo si la celda pegada pasa el gate: n>=25 y CI que no cruza.)')
    conn.close()


if __name__ == '__main__':
    main()
