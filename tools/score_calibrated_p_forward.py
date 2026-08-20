"""
score_calibrated_p_forward.py — Scorer READ-ONLY de la fase registro de la
P calibrada (v3.59.0).

Que mide: los trades cerrados que nacieron CON calibrated_p en entry_context
(clasificados en el momento, no reconstruidos) contra el gate pre-declarado.
La prediccion es la del fit CONGELADO del 20-ago (el que paso el gate con
Brier held-out 0.2214); aca se verifica si sostiene hacia adelante.

Gate pre-declarado para ACTIVAR (usar la P en alguna decision):
  1. n >= 40 cerrados forward con calibrated_p
  2. Brier(calibrated_p) < Brier(constante = train WR congelado 0.4615)
  3. Brier(calibrated_p) < 0.230 (el gate absoluto de calibrate_confidence.py)
Si con n >= 60 no pasa -> se borra el modulo y la conclusion es que el PASA
del 20-ago fue artefacto del test chico (~29 filas). No buscarle la vuelta.

0 filas + trades m15 nuevos cerrados = el hook de add_auto_strategy murio
(buscar "calibrated_p no registrada" en aidan.log) — el sintoma clasico de
subsistema muerto en silencio.

Uso: python tools/score_calibrated_p_forward.py
No toca la DB (solo SELECT). No requiere MT5.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer.confidence_calibration import FROZEN_PARAMS

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
GATE_BRIER = 0.230
GATE_MIN_N = 40
GIVE_UP_N = 60


def brier(probs, ys):
    return sum((p - y) ** 2 for p, y in zip(probs, ys)) / len(ys)


def main():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    print('DB: %s' % DB_PATH)

    for track, params in FROZEN_PARAMS.items():
        train_wr = params['train_wr']
        print('\n' + '=' * 74)
        print('### %s — forward de la P calibrada (fit congelado %s) ###'
              % (track, params['fitted_at']))
        print('=' * 74)

        # Cerrados con prediccion registrada al nacer (broker-truth).
        rows = conn.execute(
            """SELECT a.entry_context, t.result, t.mt5_pnl, t.created_at
               FROM trade_archive t
               JOIN auto_strategies a ON a.id = t.strategy_id
               WHERE t.trigger_type = ? AND t.result IN ('win','loss')
                 AND t.mt5_pnl IS NOT NULL
                 AND a.entry_context LIKE '%calibrated_p%'
               ORDER BY t.created_at""", (track,)).fetchall()

        # Pendientes (registradas, todavia sin cierre) — para ver que el hook vive.
        pending = conn.execute(
            """SELECT COUNT(*) FROM auto_strategies
               WHERE trigger_type = ? AND entry_context LIKE '%calibrated_p%'""",
            (track,)).fetchone()[0]

        deployed = params.get('deployed_at', params['fitted_at'])
        closed_since = conn.execute(
            """SELECT COUNT(*) FROM trade_archive
               WHERE trigger_type = ? AND result IN ('win','loss')
                 AND created_at >= ?""", (track, deployed)).fetchone()[0]

        print('  registradas (total, abiertas o no): %d' % pending)
        if pending == 0 and closed_since > 0:
            print('  *** ALERTA: hay %d trades %s creados desde el deploy (%s) y CERO'
                  % (closed_since, track, deployed))
            print('      registros -> el hook de add_auto_strategy puede estar MUERTO.')
            print('      Buscar "calibrated_p no registrada" en aidan.log.')

        if not rows:
            print('  cerrados con calibrated_p: 0 -> nada que medir todavia.')
            continue

        probs, ys = [], []
        for ctx_json, result, _pnl, _ts in rows:
            try:
                p = json.loads(ctx_json).get('calibrated_p')
            except (TypeError, ValueError):
                p = None
            if p is None:
                continue
            probs.append(float(p))
            ys.append(1 if result == 'win' else 0)

        n = len(probs)
        if n == 0:
            print('  cerrados con calibrated_p parseable: 0.')
            continue

        b_platt = brier(probs, ys)
        b_const = brier([train_wr] * n, ys)
        wr_fwd = sum(ys) / n
        print('  cerrados forward: n=%d  (%s -> %s)' % (n, rows[0][3][:10], rows[-1][3][:10]))
        print('  WR forward=%.1f%%  (train congelado=%.1f%%)' % (100 * wr_fwd, 100 * train_wr))
        print('  BRIER forward:  calibrada=%.4f  constante=%.4f  gate=%.3f'
              % (b_platt, b_const, GATE_BRIER))

        print('  fiabilidad por bucket de P predicha:')
        for lo, hi in [(0.0, 0.35), (0.35, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 1.01)]:
            idx = [i for i, p in enumerate(probs) if lo <= p < hi]
            if not idx:
                continue
            pm = sum(probs[i] for i in idx) / len(idx)
            ym = sum(ys[i] for i in idx) / len(idx)
            print('    P[%.2f-%.2f) n=%3d  predicha=%.3f  real=%.3f' % (lo, hi, len(idx), pm, ym))

        if n < GATE_MIN_N:
            print('\n  >>> n=%d < %d -> SIN VEREDICTO (no concluir, seguir juntando).' % (n, GATE_MIN_N))
        else:
            passed = (b_platt < b_const) and (b_platt < GATE_BRIER)
            if passed:
                print('\n  >>> PASA el gate forward -> se puede discutir darle una decision '
                      '(empezar por UNA, la mas chica).')
            elif n >= GIVE_UP_N:
                print('\n  >>> NO PASA con n>=%d -> borrar el modulo; el PASA del 20-ago '
                      'era artefacto del test chico.' % GIVE_UP_N)
            else:
                print('\n  >>> NO PASA todavia (n=%d) -> re-medir mas adelante; a n>=%d se decide.'
                      % (n, GIVE_UP_N))

    conn.close()


if __name__ == '__main__':
    main()
