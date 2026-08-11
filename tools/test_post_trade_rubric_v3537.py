# -*- coding: utf-8 -*-
"""Tests v3.53.7 — la rubrica del post-trade, calculada en codigo.

El A/B (tools/ab_post_trade_prompt.py) probo que el modelo de 7B no aplica de
forma fiable una rubrica que tiene escrita adelante (23-77% de adherencia), asi
que las 5 etiquetas categoricas pasaron a `derive_quality()`. Estos tests fijan
esa rubrica y verifican que separa lo que tiene que separar.

DB temporal para el helper. No necesita MT5 ni Ollama.
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer.post_trade_analyzer import derive_quality  # noqa: E402

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('  OK   ' if cond else '  FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''))


# ── La rubrica ───────────────────────────────────────────────────────────────
print('\n[1] entry_quality: mide si el precio llego a irse a favor')
check('80% del TP -> good', derive_quality(80, 10, 8, 70, False)['entry_quality'] == 'good')
check('50% exacto -> good (borde)', derive_quality(50, 10, 5, 70, False)['entry_quality'] == 'good')
check('35% -> fair', derive_quality(35, 10, 3, 70, False)['entry_quality'] == 'fair')
check('20% exacto -> fair (borde)', derive_quality(20, 10, 2, 70, False)['entry_quality'] == 'fair')
check('5% -> poor (nunca se puso a favor)', derive_quality(5, 10, 0.5, 70, False)['entry_quality'] == 'poor')
check('0% -> poor', derive_quality(0, 0, 0, 70, False)['entry_quality'] == 'poor')

print('\n[2] exit_quality: mide cuanto del pico se devolvio')
check('devolvio 10% -> good', derive_quality(60, 10, 8, 70, False)['exit_quality'] == 'good')
check('devolvio 50% -> fair', derive_quality(60, 50, 8, 70, False)['exit_quality'] == 'fair')
check('devolvio 90% -> poor', derive_quality(60, 90, 8, 70, False)['exit_quality'] == 'poor')
check('pico < 1 pip -> fair (no habia nada que gestionar)',
      derive_quality(5, 100, 0.4, 70, False)['exit_quality'] == 'fair')

print('\n[3] confidence_was: contrasta la confianza declarada contra el recorrido')
check('conf 90 y 10% del TP -> overestimated',
      derive_quality(10, 0, 1, 90, False)['confidence_was'] == 'overestimated')
check('conf 60 y 80% del TP -> underestimated',
      derive_quality(80, 0, 8, 60, False)['confidence_was'] == 'underestimated')
check('conf 70 y 40% del TP -> accurate',
      derive_quality(40, 0, 4, 70, False)['confidence_was'] == 'accurate')
check('conf 75 exacto y 24% -> overestimated (borde)',
      derive_quality(24, 0, 2, 75, False)['confidence_was'] == 'overestimated')

print('\n[4] sl_action: "keep" por default, con dos excepciones medibles')
check('default -> keep', derive_quality(30, 20, 3, 70, False)['sl_action'] == 'keep')
check('toco SL habiendo llegado al 45% -> widen (el stop corto algo que iba bien)',
      derive_quality(45, 100, 4, 70, True)['sl_action'] == 'widen')
check('nunca paso del 5% -> tighten (murio de entrada)',
      derive_quality(5, 100, 0.5, 70, True)['sl_action'] == 'tighten')
check('toco SL pero solo llego al 25% -> NO widen',
      derive_quality(25, 100, 2, 70, True)['sl_action'] == 'keep')
# el reflejo que rompimos: un perdedor tipico NO debe pedir widen
perdedores_tipicos = [(19, 100, 1.8), (12, 100, 1.2), (30, 100, 3.0), (0, 0, 0.0)]
n_widen = sum(1 for p, d, m in perdedores_tipicos
              if derive_quality(p, d, m, 70, True)['sl_action'] == 'widen')
check('ningun perdedor tipico pide widen (el prompt viejo pedia 90%)', n_widen == 0, f'widen={n_widen}')

# ── Contra los trades REALES ────────────────────────────────────────────────
print('\n[5] Sobre los trades reales: ¿separa dentro del mismo resultado?')
DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = [dict(r) for r in conn.execute("""
    SELECT t.result, t.pips, t.tp_pips, t.confidence, t.sl_hit,
           (SELECT MAX(hwm_pips) FROM position_manager_log p
            WHERE p.strategy_id=t.strategy_id) mfe
    FROM trade_archive t
    WHERE t.mt5_pnl IS NOT NULL AND t.created_at >= '2026-06-20'
      AND t.result IN ('win','loss') AND t.tp_pips > 0""")]
rows = [r for r in rows if r['mfe'] is not None]
conn.close()

etiq = []
for r in rows:
    mfe = float(r['mfe'])
    pct_tp = 100.0 * mfe / r['tp_pips']
    dev = max(0.0, mfe - float(r['pips'] or 0))
    pct_dev = (100.0 * dev / mfe) if mfe > 0 else 0
    d = derive_quality(pct_tp, pct_dev, mfe, float(r['confidence'] or 0), bool(r['sl_hit']))
    etiq.append((r['result'], d, pct_tp))

perd = [(d, p) for res, d, p in etiq if res == 'loss']
gana = [(d, p) for res, d, p in etiq if res == 'win']
print(f"  n={len(etiq)} ({len(gana)} win / {len(perd)} loss)")

# LO QUE IMPORTA: entre los perdedores, distinguir entrada mala de gestion mala
entrada_mala = sum(1 for d, p in perd if d['entry_quality'] == 'poor')
gestion_mala = sum(1 for d, p in perd if d['entry_quality'] != 'poor' and d['exit_quality'] == 'poor')
print(f"  PERDEDORES: entrada mala {entrada_mala} · llegaron a estar bien y lo devolvieron {gestion_mala}")
check('la rubrica parte a los perdedores en dos grupos (no los mete a todos en uno)',
      entrada_mala > 0 and gestion_mala > 0, f'{entrada_mala}/{gestion_mala}')
check('coincide con el hallazgo de v3.53.2 (la mayoria nunca llega a mitad de camino)',
      entrada_mala > len(perd) * 0.4, f'{entrada_mala}/{len(perd)}')

# y ningun campo colapsa a un solo valor (el pecado del prompt viejo)
for campo in ('entry_quality', 'exit_quality', 'confidence_was', 'sl_action'):
    vals = {}
    for res, d, p in etiq:
        vals[d[campo]] = vals.get(d[campo], 0) + 1
    dom = max(vals.values())
    check(f'{campo} no colapsa (dominante {100*dom/len(etiq):.0f}%)',
          dom / len(etiq) < 0.80, f'{vals}')

# ── El helper de excursion ───────────────────────────────────────────────────
print('\n[6] get_trade_excursion sobre DB temporal')
tmp = os.path.join(tempfile.mkdtemp(prefix='aidan_pt3537_'), 'test.db')
c = sqlite3.connect(tmp)
c.execute("""CREATE TABLE position_manager_log (strategy_id INTEGER, hwm_pips REAL, created_at TEXT)""")
c.execute("""CREATE TABLE auto_strategies (id INTEGER PRIMARY KEY, mt5_high_water REAL)""")
for h, t in ((1.0, '2026-08-11 10:00:00'), (7.5, '2026-08-11 10:05:00'), (7.5, '2026-08-11 10:20:00')):
    c.execute("INSERT INTO position_manager_log VALUES (500, ?, ?)", (h, t))
c.execute("INSERT INTO auto_strategies VALUES (600, 4.2)")   # sin filas de PM
c.commit(); c.close()

import src.common.db as dbmod
_orig = dbmod._connect
dbmod._connect = lambda *a, **k: sqlite3.connect(tmp, timeout=15.0)
e = dbmod.get_trade_excursion(500)
check('lee el pico del position_manager_log', e and e['mfe_pips'] == 7.5, str(e))
check('calcula cuando llego al pico', e and e['mins_to_peak'] == 5.0, str(e))
check('calcula la duracion', e and e['duration_min'] == 20.0, str(e))
e2 = dbmod.get_trade_excursion(600)
check('cae al mt5_high_water si el PM no logueo', e2 and e2['mfe_pips'] == 4.2, str(e2))
check('estrategia inexistente -> None', dbmod.get_trade_excursion(9999) is None)
dbmod._connect = _orig

print('\n' + '=' * 60)
ok = sum(1 for _, c_, _ in RESULTS if c_)
print(f'{ok}/{len(RESULTS)} OK')
for n, c_, d in RESULTS:
    if not c_:
        print(f'  FAIL: {n}  {d}')
sys.exit(0 if ok == len(RESULTS) else 1)
