# -*- coding: utf-8 -*-
"""
calibrate_confidence.py — Ola 2 de la auditoria (31-jul): la confianza NO es una probabilidad.

Medido en la auditoria: Brier con conf/100 = 0.369 vs 0.230 de predecir la CONSTANTE 0.37
=> el numero es ~60% PEOR que no tener numero. Tiene ranking debil (monotono de 60 en
adelante) pero cero valor probabilistico. El fix principista NO es tocar la formula de
dynamic_conf (regla: no tocar con <300 trades limpios) sino ENVOLVERLA con una calibracion
de Platt (2 parametros: a, b -> P(win) = sigmoid(a*conf_z + b)), que es viable a n~150.

CRITERIO PRE-DECLARADO (antes de mirar el resultado, para no auto-enganarse):
  se activa SOLO si el Brier held-out baja de 0.230 (la constante). Si empata o sube, la
  conclusion honesta es "la confianza no tiene senal aprendible todavia" y NO se activa.

Split CRONOLOGICO (nunca aleatorio: seria lookahead sobre un sistema que cambia de version).

READ-ONLY (solo SELECT). No necesita MT5.
Uso: python tools/calibrate_confidence.py
Env: CLEAN_FROM (default 2026-06-20, post-fixes), TEST_FRAC (default 0.30)
"""
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
CLEAN_FROM = os.getenv('CLEAN_FROM', '2026-06-20')
TEST_FRAC = float(os.getenv('TEST_FRAC', '0.30'))
GATE_BRIER = 0.230  # la constante medida en la auditoria


def load(conn, track=None):
    q = """SELECT confidence, result, trigger_type, created_at
           FROM trade_archive
           WHERE result IN ('win','loss') AND confidence IS NOT NULL AND confidence > 0
             AND created_at >= ? AND trigger_type != 'mt5_recovered'
           ORDER BY created_at"""
    rows = conn.execute(q, (CLEAN_FROM,)).fetchall()
    out = [{'conf': float(r[0]), 'y': 1 if r[1] == 'win' else 0,
            'track': r[2], 'ts': r[3]} for r in rows]
    if track:
        out = [x for x in out if x['track'] == track]
    return out


def brier(probs, ys):
    if not ys:
        return None
    return sum((p - y) ** 2 for p, y in zip(probs, ys)) / len(ys)


def logloss(probs, ys):
    if not ys:
        return None
    eps = 1e-9
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                for p, y in zip(probs, ys)) / len(ys)


def fit_platt(xs, ys, iters=800, lr=0.15):
    """Regresion logistica de 1 feature por gradiente (sin sklearn, 2 params)."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    mu = sum(xs) / n
    sd = (sum((x - mu) ** 2 for x in xs) / n) ** 0.5 or 1.0
    zs = [(x - mu) / sd for x in xs]
    base = sum(ys) / n
    base = min(max(base, 1e-3), 1 - 1e-3)
    a, b = 0.0, math.log(base / (1 - base))
    for _ in range(iters):
        ga = gb = 0.0
        for z, y in zip(zs, ys):
            p = 1.0 / (1.0 + math.exp(-(a * z + b)))
            e = p - y
            ga += e * z
            gb += e
        a -= lr * ga / n
        b -= lr * gb / n
    return (a, b, mu, sd)


def apply_platt(params, conf):
    a, b, mu, sd = params
    z = (conf - mu) / (sd or 1.0)
    return 1.0 / (1.0 + math.exp(-(a * z + b)))


def reliability(probs, ys, label):
    print('    %s — fiabilidad por bucket de P predicha:' % label)
    buckets = [(0.0, 0.30), (0.30, 0.35), (0.35, 0.40), (0.40, 0.45), (0.45, 1.01)]
    for lo, hi in buckets:
        idx = [i for i, p in enumerate(probs) if lo <= p < hi]
        if not idx:
            continue
        pm = sum(probs[i] for i in idx) / len(idx)
        ym = sum(ys[i] for i in idx) / len(idx)
        print('      P[%.2f-%.2f) n=%3d  predicha=%.3f  real=%.3f' % (lo, hi, len(idx), pm, ym))


def run(data, label):
    n = len(data)
    if n < 40:
        print('\n### %s — n=%d: insuficiente, se saltea ###' % (label, n))
        return None
    cut = int(n * (1 - TEST_FRAC))
    tr, te = data[:cut], data[cut:]
    print('\n' + '=' * 74)
    print('### %s — n=%d (train %d hasta %s | test %d desde %s) ###' % (
        label, n, len(tr), tr[-1]['ts'][:10], len(te), te[0]['ts'][:10]))
    print('=' * 74)
    base_tr = sum(x['y'] for x in tr) / len(tr)
    base_te = sum(x['y'] for x in te) / len(te)
    print('  WR train=%.1f%%  WR test=%.1f%%' % (100 * base_tr, 100 * base_te))

    ys_te = [x['y'] for x in te]

    # (1) lo que hace HOY: conf/100 como si fuera probabilidad
    raw = [x['conf'] / 100.0 for x in te]
    b_raw = brier(raw, ys_te)

    # (2) la vara: constante = WR del train (sin mirar el test)
    const = [base_tr] * len(te)
    b_const = brier(const, ys_te)

    # (3) Platt entrenado SOLO en train
    params = fit_platt([x['conf'] for x in tr], [x['y'] for x in tr])
    platt = [apply_platt(params, x['conf']) for x in te]
    b_platt = brier(platt, ys_te)

    print('\n  BRIER held-out (mas bajo = mejor):')
    print('    conf/100 crudo (lo de hoy) : %.4f' % b_raw)
    print('    constante (WR del train)   : %.4f   <-- la vara a batir' % b_const)
    print('    Platt (a=%.3f b=%.3f)      : %.4f' % (params[0], params[1], b_platt))
    print('    gate pre-declarado         : %.4f' % GATE_BRIER)
    print('\n  LOGLOSS held-out: crudo=%.4f  const=%.4f  platt=%.4f' % (
        logloss(raw, ys_te), logloss(const, ys_te), logloss(platt, ys_te)))
    print('\n  rango de P que produce Platt en test: [%.3f, %.3f]' % (min(platt), max(platt)))
    reliability(platt, ys_te, 'Platt')

    passed = (b_platt < GATE_BRIER) and (b_platt < b_const)
    print('\n  >>> VEREDICTO %s: %s' % (
        label,
        'PASA (Platt %.4f < gate %.4f y < constante %.4f) -> se puede activar' % (
            b_platt, GATE_BRIER, b_const) if passed else
        'NO PASA (Platt %.4f vs gate %.4f / constante %.4f) -> NO activar' % (
            b_platt, GATE_BRIER, b_const)))
    return {'label': label, 'n': n, 'b_raw': b_raw, 'b_const': b_const,
            'b_platt': b_platt, 'passed': passed, 'params': params}


def main():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    print('DB: %s' % DB_PATH)
    print('CLEAN_FROM=%s  TEST_FRAC=%.2f  gate Brier<%.3f' % (CLEAN_FROM, TEST_FRAC, GATE_BRIER))
    res = []
    allr = run(load(conn), 'TODOS los tracks')
    if allr:
        res.append(allr)
    for tk in ['m15_structure', 'structure']:
        r = run(load(conn, tk), tk)
        if r:
            res.append(r)
    print('\n' + '=' * 74)
    print('RESUMEN')
    print('=' * 74)
    for r in res:
        print('  %-18s n=%3d  crudo=%.4f  const=%.4f  platt=%.4f  %s' % (
            r['label'], r['n'], r['b_raw'], r['b_const'], r['b_platt'],
            'PASA' if r['passed'] else 'NO PASA'))
    if not any(r['passed'] for r in res):
        print('\n  Ninguna capa pasa el gate => la conclusion honesta es que la confianza no')
        print('  tiene senal probabilistica aprendible a este n. NO se activa la calibracion.')
        print('  (Lo que SI queda medido: conf/100 crudo es mucho peor que la constante =>')
        print('   no usar la confianza como probabilidad en ningun calculo, p.ej. sizing.)')
    conn.close()


if __name__ == '__main__':
    main()
