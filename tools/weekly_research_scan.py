"""
weekly_research_scan.py — Busqueda semanal de MEJORA (read-only, 0 cambios).

Complemento de `audit_code_patterns.py`: aquel busca BUGS leyendo codigo; este busca
EDGE leyendo la data real del broker (`trade_archive.mt5_pnl`) y verifica que el LOOP
de aprendizaje siga vivo. Nace del pedido del user (11-sep-2026): que la rutina de los
sabados, ademas de auditar codigo, busque de forma exhaustiva como mejorar las
predicciones, los tiempos de entrada, los niveles y el aprendizaje sobre si mismo.

QUE HACE (4 bloques):
  [A] SALUD DEL LOOP DE APRENDIZAJE — tripwires de "hook muerto": cada mecanismo que
      escribe (TCA, MFE/MAE, retrospectiva, lecciones direccionales, calibrated_p,
      shadow book, shadow trader, D1) tiene que haber escrito filas en los ultimos 7
      dias si hubo trades. La clase de bug que mas daño hizo aca es "subsistema muerto
      en silencio" (M15 2 semanas, SMC, el reversal, log_fill meses). Esto lo caza.
  [B] TERMOMETRO POR TRACK — 30 y 60 dias: n, WR, PnL, CI95 de Wilson, y el WR que
      cada track NECESITA para empatar (avg win / avg loss reales). Dice donde sangra.
  [C] BATERIA DE HIPOTESIS — barre buckets de ~15 features (hora, sesion, dia,
      confianza, volatilidad, alineacion con HTF/tendencia, RSI, ATR, eficiencia de
      Kaufman, edad de la señal, setup_type, calibrated_p, distancia MFE...) y pasa
      CADA celda por el gate de la casa (`significance.verify_finding`: n>=25 + CI95
      que NO cruce el baseline). Reporta SOLO las que pasan. Las que pasan se cruzan
      contra la lista de lo YA MEDIDO/REFUTADO (para no re-proponer lo que ya se
      descarto) y contra el BASELINE de la corrida anterior (para decir que es NUEVO).
  [D] GESTION (MFE/MAE reales) — ¿cuanto se pusieron a favor los perdedores antes de
      perder? Separa "entro mal" (nunca a favor) de "gestiono mal" (a favor y devolvio).
      Es medicion, no propuesta: los mecanismos de gestion de h1 ya se midieron y se
      refutaron (profit-lock, capear el trailing, achicar el TP — ver historial).

QUE NO HACE: no toca la DB (todas las conexiones `mode=ro`), no usa MetaTrader5, no
aplica nada. Un bucket que pasa el gate es PERMISO PARA INVESTIGAR (shadow, clasificacion
en el momento), NO para operar. La carga de la prueba la tiene el cambio.

BASELINE: `tools/.weekly_research_baseline.json` guarda las celdas que pasaron el gate
en la ultima corrida. Exit 0 = nada nuevo paso el gate. Exit 1 = hay al menos una celda
NUEVA que pasa (mirarla a mano). `--no-update` no reescribe el baseline.

LIMITES DECLARADOS:
  - Barrer ~150 celdas con alpha 0,05 produce ~7 falsos positivos POR AZAR. Por eso el
    gate exige ademas CI95 que no cruce (mas duro que p<0,05) y por eso una celda que
    pasa se trata como hipotesis a llevar a shadow, nunca como hallazgo.
  - Las features se clasificaron EN EL MOMENTO (entry_context, columnas del archive),
    no reconstruidas. Las columnas nuevas (mfe/mae, efficiency_ratio, signal_age)
    existen desde v3.58.x (19-ago) => n chico por meses; el script lo dice.
  - El baseline de WR es el LIFETIME del archive (recalculado en cada corrida), no el
    37,4% congelado del 29-may.
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.optimizer.significance import verify_finding, MIN_N  # noqa: E402

DB_PATH = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'financial_news.db')
BASELINE_PATH = os.path.join(ROOT, 'tools', '.weekly_research_baseline.json')

# ── LO YA MEDIDO: celdas que pasan el gate pero que YA se decidieron. Se muestran con
#    su veredicto al lado para no volver a proponerlas. Clave = prefijo de la celda.
YA_MEDIDO = {
    'hour_utc':      'hour gate REMOVIDO (ruido, jun-2026): no re-proponer bloquear horas sin shadow',
    'session':       'todas las sesiones pierden (11-may); sesion sola no separa',
    'conf_bucket':   'conf cruda NO es monotona (conf 90+ 0% WR, 40-49 43%); Platt en fase registro v3.59.0',
    'cooldown':      'cooldown <=5min ACTIVO desde v3.40.15 (re-validado 3x)',
    'atr_bucket:m15': 'M15_ATR_FLOOR=8 ACTIVO (v3.55.0); lectura ~1-oct; no afinar el umbral sobre esta muestra',
    'htf_align':     'bias-fresh/alineado = PEOR (exhaustion), bias rezagado REFUTADO como culpable (jun)',
    'trigger_type:news': 'news: user decidio NO apagar (7-sep); lever = TP capado, no expiry ni direccion',
    'level_touches': 'niveles <5 toques NO existen (mito refutado jul); castigo flojo m15 v3.50.0 midiendose',
    'setup_type':    'adjust_setup_confidence cableado v3.57.0; requiere shadow del meta-optimizer',
}


def ro(path=DB_PATH):
    return sqlite3.connect(f'file:{path}?mode=ro', uri=True)


def wilson(w, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0, c - h), min(1, c + h))


def hdr(t):
    print('\n' + '=' * 72)
    print(t)
    print('=' * 72)


# ────────────────────────── [A] salud del loop ──────────────────────────
def check_loop_health(c, days=7):
    hdr(f'[A] SALUD DEL LOOP DE APRENDIZAJE (ultimos {days} dias)')
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    trades = c.execute("SELECT COUNT(*) FROM trade_archive WHERE mt5_pnl IS NOT NULL AND created_at>=?",
                       (since,)).fetchone()[0]
    m15 = c.execute("SELECT COUNT(*) FROM trade_archive WHERE trigger_type='m15_structure' AND created_at>=?",
                    (since,)).fetchone()[0]
    print(f'  trades cerrados con P&L real: {trades}  (m15: {m15})')
    problems = []

    def row(name, n, expected_if, note=''):
        flag = 'OK '
        if expected_if and n == 0:
            flag = '!! '
            problems.append(name)
        print(f'  {flag}{name:<38} {n:>5}  {note}')

    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]  # noqa: E731
    row('slippage_log (TCA, v3.58.0)', q("SELECT COUNT(*) FROM slippage_log WHERE timestamp>=?", since),
        trades > 0, 'debe ~= fills')
    row('mfe_pips poblado en archive', q("SELECT COUNT(*) FROM trade_archive WHERE mfe_pips IS NOT NULL AND created_at>=?", since),
        trades > 0, 'debe ~= trades')
    row('signal_age_at_fill_min poblado', q("SELECT COUNT(*) FROM trade_archive WHERE signal_age_at_fill_min IS NOT NULL AND created_at>=?", since),
        trades > 0)
    row('pre_trade_retrospective (v3.57.0)', q("SELECT COUNT(*) FROM pre_trade_retrospective WHERE created_at>=?", since),
        trades > 0, 'una por señal')
    row('directional_lessons (perdedores SL)', q("SELECT COUNT(*) FROM directional_lessons WHERE created_at>=?", since),
        False, 'solo crece con perdedores que pegan SL sin ir a favor')
    row('calibrated_p en entry_context (m15)',
        q("SELECT COUNT(*) FROM trade_archive WHERE trigger_type='m15_structure' AND created_at>=? AND entry_context LIKE '%calibrated_p%'", since),
        m15 > 0, 'debe = trades m15')
    row('rejected_signals (shadow book)', q("SELECT COUNT(*) FROM rejected_signals WHERE created_at>=?", since), trades > 0)
    row('shadow_trader_log (LLM en papel)', q("SELECT COUNT(*) FROM shadow_trader_log WHERE created_at>=?", since), trades > 0)
    row('d1_shadow_log (track D)', q("SELECT COUNT(*) FROM d1_shadow_log WHERE created_at>=?", since), False, '~2-3/mes esperado')
    row('learning_insights (post-trade LLM)', q("SELECT COUNT(*) FROM learning_insights WHERE created_at>=?", since), False, 'depende de Ollama')
    row('event_window_log', q("SELECT COUNT(*) FROM event_window_log WHERE created_at>=?", since), trades > 0)
    # scorers sin correr: filas sin puntuar
    unscored = q("SELECT COUNT(*) FROM shadow_trader_log WHERE scored_at IS NULL AND kind='open' AND decision!='NONE'")
    unscored_rs = q("SELECT COUNT(*) FROM rejected_signals WHERE scored_at IS NULL")
    print(f'  ..  sin puntuar: shadow_trader open={unscored} · rejected_signals={unscored_rs}'
          f'  (los scorers necesitan MT5 => correr con AIdan cerrado)')
    pc = c.execute("SELECT status, COUNT(*) FROM pending_changes GROUP BY 1").fetchall()
    print(f'  ..  meta-optimizer pending_changes: {dict(pc)}  (0 applied = el gate rechazando, no un fallo)')
    if problems:
        print(f'\n  >> HOOKS POSIBLEMENTE MUERTOS: {problems}. Buscar WARNING en aidan.log antes de alarmar.')
    return problems


# ────────────────────────── [B] termometro ──────────────────────────
def thermometer(c, base_wr):
    hdr('[B] TERMOMETRO POR TRACK (broker-truth)')
    for days in (30, 60):
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        rows = c.execute("""
            SELECT trigger_type, COUNT(*), SUM(result='win'), ROUND(SUM(mt5_pnl),2),
                   AVG(CASE WHEN mt5_pnl>0 THEN mt5_pnl END), AVG(CASE WHEN mt5_pnl<0 THEN -mt5_pnl END)
            FROM trade_archive WHERE mt5_pnl IS NOT NULL AND created_at>=?
            GROUP BY 1 ORDER BY 4""", (since,)).fetchall()
        print(f'\n  ultimos {days} dias  (baseline lifetime WR {base_wr*100:.1f}%)')
        print(f'  {"track":<15}{"n":>4}{"WR":>7}{"CI95":>16}{"PnL$":>9}{"avgW":>7}{"avgL":>7}{"WR_BE":>7}')
        tot = 0
        for t, n, w, pnl, aw, al in rows:
            lo, hi = wilson(w or 0, n)
            be = (al / (aw + al)) if aw and al else float('nan')
            tot += pnl or 0
            print(f'  {t:<15}{n:>4}{(w or 0)/n*100:>6.0f}%  [{lo*100:>4.0f}-{hi*100:>4.0f}%]{pnl:>9.2f}'
                  f'{(aw or 0):>7.2f}{(al or 0):>7.2f}{be*100:>6.0f}%')
        print(f'  {"TOTAL":<15}{"":>4}{"":>7}{"":>16}{tot:>9.2f}   (WR_BE = WR necesario para empatar)')


# ────────────────────────── [C] bateria de hipotesis ──────────────────────────
def _bucket_conf(v):
    if v is None: return None
    v = float(v)
    return f'{int(v//10)*10}-{int(v//10)*10+9}'


def _bucket_num(v, edges, labels):
    if v is None: return None
    v = float(v)
    for e, l in zip(edges, labels):
        if v < e: return l
    return labels[-1]


def _align(direction, bias):
    if not bias or bias in ('neutral', 'none', ''): return 'neutral'
    up = bias.lower().startswith('bull') or bias.lower() == 'up'
    return 'with' if (direction == 'CALL') == up else 'against'


def load_trades(c):
    rows = c.execute("""
        SELECT trigger_type, direction, result, mt5_pnl, confidence, volatility, htf_bias, market_trend,
               rsi_at_entry, avg_range_pips, session, hour_utc, day_of_week, setup_type, entry_context,
               mfe_pips, mae_pips, signal_age_at_fill_min, tp_pips, sl_pips, pips, created_at
        FROM trade_archive WHERE mt5_pnl IS NOT NULL""").fetchall()
    out = []
    for r in rows:
        (trig, d, res, pnl, conf, vol, bias, trend, rsi, atr, sess, hour, dow, setup, ec,
         mfe, mae, age, tp, sl, pips, created) = r
        try:
            ecd = json.loads(ec) if ec else {}
        except Exception:
            ecd = {}
        out.append(dict(
            trig=trig or '?', d=d, win=(res == 'win'), pnl=pnl or 0.0, conf=conf, vol=vol or ecd.get('volatility'),
            bias=bias or ecd.get('htf_bias'), trend=trend or ecd.get('trend'), rsi=rsi if rsi is not None else ecd.get('rsi'),
            atr=atr if atr else ecd.get('avg_range_pips'), sess=sess, hour=hour, dow=dow,
            setup=setup or ecd.get('setup_type'), er=ecd.get('efficiency_ratio'), cp=ecd.get('calibrated_p'),
            lat=ecd.get('news_latency_min'), mfe=mfe, mae=mae, age=age, tp=tp, sl=sl, pips=pips, created=created,
        ))
    return out


def hypotheses(c, trades, base_wr, baseline_cells):
    hdr('[C] BATERIA DE HIPOTESIS — solo celdas que PASAN el gate (n>=%d + CI95 sin cruzar)' % MIN_N)
    # (nombre, funcion de bucket). Las features van a celdas globales y por track.
    feats = [
        ('hour_utc',   lambda t: t['hour'] if t['hour'] is not None else None),
        ('session',    lambda t: t['sess']),
        ('dow',        lambda t: t['dow']),
        ('conf_bucket', lambda t: _bucket_conf(t['conf'])),
        ('volatility', lambda t: t['vol']),
        ('htf_align',  lambda t: _align(t['d'], t['bias'])),
        ('trend_align', lambda t: _align(t['d'], t['trend'])),
        ('rsi_zone',   lambda t: _bucket_num(t['rsi'], [30, 45, 55, 70], ['<30', '30-45', '45-55', '55-70', '>=70'])),
        ('atr_bucket', lambda t: _bucket_num(t['atr'], [3, 5, 8, 12], ['<3', '3-5', '5-8', '8-12', '>=12'])),
        ('efficiency_ratio', lambda t: _bucket_num(t['er'], [0.2, 0.4, 0.6], ['<0.2', '0.2-0.4', '0.4-0.6', '>=0.6'])),
        ('signal_age_min', lambda t: _bucket_num(t['age'], [0.5, 2, 10], ['<0.5', '0.5-2', '2-10', '>=10'])),
        ('setup_type', lambda t: t['setup']),
        ('calibrated_p', lambda t: _bucket_num(t['cp'], [0.35, 0.45, 0.55], ['<0.35', '0.35-0.45', '0.45-0.55', '>=0.55'])),
        ('news_latency_min', lambda t: _bucket_num(t['lat'], [3, 6, 10], ['<3', '3-6', '6-10', '>=10'])),
        ('direction',  lambda t: t['d']),
        ('trigger_type', lambda t: t['trig']),
    ]
    cells = defaultdict(lambda: [0, 0, 0.0])  # key -> [n, wins, pnl]
    for t in trades:
        for name, fn in feats:
            b = fn(t)
            if b is None or b == '':
                continue
            for scope in ('all', t['trig']):
                k = f'{name}:{scope}:{b}'
                cell = cells[k]
                cell[0] += 1; cell[1] += int(t['win']); cell[2] += t['pnl']
    passed, tested, small = [], 0, 0
    for k, (n, w, pnl) in cells.items():
        if n < MIN_N:
            small += 1
            continue
        tested += 1
        r = verify_finding(n, w, baseline_wr=base_wr)
        if r.significant:
            passed.append((k, n, w, pnl, r))
    passed.sort(key=lambda x: x[4].p_value)
    print(f'  celdas totales {len(cells)} · con n>={MIN_N}: {tested} · descartadas por n chico: {small}'
          f' · esperadas por AZAR con alpha 0,05: ~{tested*0.05:.1f}')
    new_keys = []
    for k, n, w, pnl, r in passed:
        tag = 'NUEVA ' if k not in baseline_cells else '      '
        if k not in baseline_cells:
            new_keys.append(k)
        note = ''
        for pref, txt in YA_MEDIDO.items():
            if k.startswith(pref) or (':' in pref and pref.split(':')[0] in k and pref.split(':')[1] in k):
                note = f'  <- ya medido: {txt}'
                break
        print(f'  {tag}{k:<45} n={n:>3} WR={w/n*100:>4.0f}% CI[{r.ci_low*100:.0f}-{r.ci_high*100:.0f}]'
              f' p={r.p_value:.3f} PnL={pnl:>8.2f} ({r.direction}){note}')
    if not passed:
        print('  (ninguna celda pasa el gate)')
    dropped = [k for k in baseline_cells if k not in {p[0] for p in passed}]
    if dropped:
        print(f'\n  dejaron de pasar desde la corrida anterior ({len(dropped)}): {dropped[:8]}{"..." if len(dropped)>8 else ""}'
              f'  <- inestable = probablemente era ruido')
    return [p[0] for p in passed], new_keys


# ────────────────────────── [D] gestion: MFE/MAE ──────────────────────────
def management(trades):
    hdr('[D] GESTION — excursion real de los PERDEDORES (mfe_pips, desde v3.58.1)')
    by = defaultdict(list)
    for t in trades:
        if t['mfe'] is not None and not t['win']:
            by[t['trig']].append(t)
    if not by:
        print('  sin filas con mfe_pips todavia'); return
    print(f'  {"track":<15}{"n_loss":>7}{"nunca>+1p":>11}{"MFE>=30%TP":>12}{"MFE>=50%TP":>12}{"med MFE":>9}{"med MAE":>9}')
    for trig, ts in sorted(by.items()):
        n = len(ts)
        never = sum(1 for t in ts if (t['mfe'] or 0) < 1.0)
        f30 = sum(1 for t in ts if t['tp'] and t['mfe'] >= 0.3 * t['tp'])
        f50 = sum(1 for t in ts if t['tp'] and t['mfe'] >= 0.5 * t['tp'])
        mfes = sorted(t['mfe'] for t in ts); maes = sorted(t['mae'] or 0 for t in ts)
        print(f'  {trig:<15}{n:>7}{never:>8} ({never/n*100:>3.0f}%){f30:>7} ({f30/n*100:>3.0f}%){f50:>7} ({f50/n*100:>3.0f}%)'
              f'{mfes[n//2]:>9.1f}{maes[n//2]:>9.1f}')
    print('  lectura: "nunca>+1p" alto = ENTRA mal (direccion/timing) · "MFE>=50%TP" alto = GESTIONA mal (devolvio).'
          '\n  h1: profit-lock/trailing cap/TP chico YA refutados (8-10 ago) — no re-proponer sin data nueva.'
          '\n  n<25 por track = descriptivo, no accionable.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--no-update', action='store_true', help='no reescribir el baseline')
    ap.add_argument('--db', default=DB_PATH)
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print('DB no encontrada:', a.db); return 2
    c = ro(a.db)
    hdr('BUSQUEDA SEMANAL DE MEJORA — AIdan (read-only)')
    n, w, pnl = c.execute("SELECT COUNT(*), SUM(result='win'), ROUND(SUM(mt5_pnl),2) FROM trade_archive WHERE mt5_pnl IS NOT NULL").fetchone()
    base_wr = w / n
    print(f'  archive lifetime: n={n} WR={base_wr*100:.1f}% PnL={pnl}  (este WR es el baseline del gate)')

    problems = check_loop_health(c)
    thermometer(c, base_wr)
    trades = load_trades(c)
    baseline = {}
    if os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH, encoding='utf-8') as f:
            baseline = json.load(f)
    passed, new_keys = hypotheses(c, trades, base_wr, set(baseline.get('cells', [])))
    management(trades)

    hdr('RESULTADO')
    if problems:
        print(f'  !! {len(problems)} hook(s) sin filas en 7 dias: {problems}')
    if new_keys:
        print(f'  {len(new_keys)} celda(s) NUEVA(s) pasan el gate => hipotesis a llevar a SHADOW, no a produccion:')
        for k in new_keys: print('    -', k)
    else:
        print('  nada nuevo pasa el gate. La data esta como la semana pasada.')
    if not a.no_update:
        with open(BASELINE_PATH, 'w', encoding='utf-8') as f:
            json.dump({'updated': datetime.now().isoformat(timespec='seconds'), 'baseline_wr': base_wr,
                       'cells': sorted(passed)}, f, indent=1, ensure_ascii=False)
    return 1 if (new_keys or problems) else 0


if __name__ == '__main__':
    sys.exit(main())
