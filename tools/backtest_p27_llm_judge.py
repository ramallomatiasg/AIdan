"""
backtest_p27_llm_judge.py — P27: ¿un LLM con contexto COMPLETO, como juez de cada señal de AIdan, separa las que
ganan de las que pierden? Prueba sobre trades REALES pasados (broker-truth).

Criterio declarado ANTES de medir: docs/p27_llm_judge_criterio.md. Leer contra eso.

READ-ONLY respecto de AIdan: la DB de producción se abre `mode=ro`; no usa MT5 (las velas salen del cache M1 de
P23, `.cache_p23/EURUSD_M1.npy`, resampleadas a M5/M15/H1/H4/D1). Escribe solo en su base propia
`%APPDATA%/AIdan/state/llm_judge_retro.db` (respuestas cacheadas: la corrida se puede cortar y retomar).

Lo que ve el juez, por trade (todo relativo, SIN fechas ni precios absolutos para que no reconozca el día):
  - la señal: dirección, track, SL y TP en pips;
  - hora UTC y día de la semana;
  - velas cerradas ANTES de la entrada en 5 temporalidades, en pips contra el último precio;
  - ATR14 por temporalidad, máx/mín de ayer y de hoy, distancia al redondo de 50 pips más cercano.
No ve: la confianza de AIdan ni sus etiquetas (trend/momentum/htf_bias) — la 1ra prueba (shadow trader) mostró que
las repetía como loro —, ni noticias (los títulos traen fechas y nombres).

Placebo: la misma señal con las velas de OTRO trade al azar (semilla fija). Si el juez separa igual de bien con
velas equivocadas, no está leyendo el gráfico.

Uso:
    python tools/backtest_p27_llm_judge.py --smoke 3      # arma 3 contextos y los imprime (sin LLM)
    python tools/backtest_p27_llm_judge.py --run          # juzga lo que falte (retoma), main + placebo
    python tools/backtest_p27_llm_judge.py --report       # evalúa el criterio con lo juzgado
"""
import argparse
import datetime as dt
import json
import os
import random
import sqlite3
import sys
import time

import numpy as np
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)


M1_FILE = os.path.join(ROOT, '.cache_p23', 'EURUSD_M1.npy')
PROD_DB = os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state', 'financial_news.db')
OWN_DB = os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state', 'llm_judge_retro.db')
OUT = os.path.join(ROOT, 'docs', 'p27_llm_judge_resultado.json')

N_TRADES = 300
CUTOFF_AR = '2026-10-09 18:00'          # el cache M1 termina el 9-oct 23:56 server
AR_TO_SERVER_H = 6                      # verificado: entrada vs cierre M1, mediana 0,4 pips (5h: 5,1 · 7h: 3,6)
PIP = 0.0001
TFS = [('D1', 86400, 20), ('H4', 14400, 30), ('H1', 3600, 36), ('M15', 900, 32), ('M5', 300, 36)]
PLACEBO_SEED = 20261104
BACKEND = 'ollama'                     # local: el límite gratis de Groq (200k tokens/día) no alcanza (ver criterio)
MODEL = 'gpt-oss:20b'
EFFORT = 'medium'                       # 'high' agotó 6.000 tokens pensando sin contestar (prueba del 4-nov)
OLLAMA_URL = 'http://localhost:11434/api/chat'
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
MIN_N = 250
VETO_BAND = (0.15, 0.85)

SYSTEM = (
    'You are the risk judge of an automated EUR/USD trading system. The system proposes a trade; you decide '
    'whether it should be TAKEN or VETOED. Judge only from the data given. Round-trip cost is about 1.3 pips. '
    'Respond ONLY with valid JSON, no markdown.'
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS judgments (
    strategy_id INTEGER NOT NULL,
    variant TEXT NOT NULL,              -- 'main' | 'placebo'
    candles_from INTEGER,               -- strategy_id cuyas velas se usaron (placebo != propio)
    decision TEXT,                      -- TAKE | VETO | NULL si falló
    confidence REAL,
    reasoning TEXT,
    model TEXT, effort TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER,
    error TEXT,
    created_at TEXT,
    PRIMARY KEY (strategy_id, variant)
);
"""


# ---------------------------------------------------------------- datos

def load_trades():
    c = sqlite3.connect(f'file:{PROD_DB}?mode=ro', uri=True)
    rows = c.execute(
        "SELECT strategy_id, direction, trigger_type, sl_pips, tp_pips, created_at, mt5_pnl, pips "
        "FROM trade_archive WHERE mt5_pnl IS NOT NULL AND created_at < ? "
        "ORDER BY created_at DESC LIMIT ?", (CUTOFF_AR, N_TRADES)).fetchall()
    c.close()
    out = []
    for sid, d, trig, slp, tpp, ca, pnl, pips in rows:
        t_srv = int((dt.datetime.fromisoformat(ca) + dt.timedelta(hours=AR_TO_SERVER_H))
                    .replace(tzinfo=dt.timezone.utc).timestamp())
        out.append(dict(sid=int(sid), direction=d, track=trig, sl=slp, tp=tpp, created_ar=ca, t=t_srv,
                        pnl=float(pnl), pips=pips))
    return sorted(out, key=lambda x: x['t'])


def load_m1():
    m = np.load(M1_FILE)
    return dict(t=m['time'].astype(np.int64), o=m['open'].astype(float), h=m['high'].astype(float),
                l=m['low'].astype(float), c=m['close'].astype(float))


def bars_before(M, t, size, count):
    """Velas de `size` segundos COMPLETAMENTE cerradas antes de t (sin mirar el futuro), de más vieja a más nueva."""
    end = np.searchsorted(M['t'], t - 60, side='right')     # M1 cuyo minuto terminó antes de t
    if end == 0:
        return []
    last_closed_bucket = (t // size) * size                  # el bucket de t está en formación: se excluye
    lo_t = last_closed_bucket - size * (int(count * 1.5) + 5) - 3 * 86400   # margen para fines de semana y feriados
    start = np.searchsorted(M['t'], lo_t)
    tt = M['t'][start:end]
    keys = (tt // size) * size
    out = []
    for k in np.unique(keys):
        if k >= last_closed_bucket:
            continue
        sel = slice(start + np.searchsorted(keys, k), start + np.searchsorted(keys, k, side='right'))
        out.append((int(k), M['o'][sel][0], M['h'][sel].max(), M['l'][sel].min(), M['c'][sel][-1]))
    return out[-count:]


def atr(bars, n=14):
    if len(bars) < 2:
        return None
    tr = [max(b[2], prev[4]) - min(b[3], prev[4]) for prev, b in zip(bars, bars[1:])]
    return float(np.mean(tr[-n:])) / PIP


def build_context(M, t):
    """Texto con la foto del mercado ANTES de t. None si faltan datos."""
    i = np.searchsorted(M['t'], t - 60, side='right') - 1
    if i < 0 or t - M['t'][i] > 900:
        return None, None
    ref = M['c'][i]
    lines = []
    dims = {}
    for name, size, count in TFS:
        b = bars_before(M, t, size, count)
        if len(b) < count * 0.8:
            return None, None
        a = atr(b)
        dims[name] = a
        lines.append(f"\n{name} candles, oldest to newest (open high low close, pips vs current price; ATR14 {a:.1f}p):")
        lines += [f"{(o - ref) / PIP:+.1f} {(h - ref) / PIP:+.1f} {(l - ref) / PIP:+.1f} {(c - ref) / PIP:+.1f}"
                  for _, o, h, l, c in b]
    d1 = bars_before(M, t, 86400, 2)
    day0 = (t // 86400) * 86400
    j0 = np.searchsorted(M['t'], day0)
    extra = []
    if d1:
        _, o, h, l, c = d1[-1]
        extra.append(f"yesterday high {(h - ref) / PIP:+.1f}, low {(l - ref) / PIP:+.1f}")
    if i >= j0:
        extra.append(f"today so far high {(M['h'][j0:i + 1].max() - ref) / PIP:+.1f}, "
                     f"low {(M['l'][j0:i + 1].min() - ref) / PIP:+.1f}")
    r50 = round(ref / 0.005) * 0.005
    extra.append(f"nearest 50-pip round number at {(r50 - ref) / PIP:+.1f}")
    return '\n'.join(lines) + '\n\nLevels (pips vs current price): ' + '; '.join(extra), ref


def load_calendar():
    """P27b: la foto del calendario que AIdan registró al ejecutar cada trade (`event_window_log`, 1ra fila)."""
    c = sqlite3.connect(f'file:{PROD_DB}?mode=ro', uri=True)
    out = {}
    for sid, nxt, imp, mins, prev, pimp, since in c.execute(
            'SELECT strategy_id, next_event, next_impact, mins_to_next, prev_event, prev_impact, mins_since_prev '
            'FROM event_window_log ORDER BY id'):
        out.setdefault(int(sid), dict(next=nxt, next_impact=imp, mins_to_next=mins, prev=prev, prev_impact=pimp,
                                      mins_since_prev=since))
    c.close()
    return out


def calendar_line(cal):
    parts = []
    if cal['next'] and cal['mins_to_next'] is not None:
        parts.append(f"next scheduled event '{cal['next']}' ({cal['next_impact']} impact) in "
                     f"{cal['mins_to_next']:.0f} min")
    else:
        parts.append('no high/medium-impact event scheduled soon')
    if cal['prev'] and cal['mins_since_prev'] is not None:
        parts.append(f"previous event '{cal['prev']}' ({cal['prev_impact']} impact) {cal['mins_since_prev']:.0f} min ago")
    return 'Economic calendar (USD/EUR): ' + '; '.join(parts) + '.'


def build_prompt(trade, ctx, cal=None):
    hour_utc = ((trade['t'] - 3 * 3600) // 3600) % 24       # server UTC+3 en todo el período (jun-oct)
    dow = dt.datetime.utcfromtimestamp(trade['t']).strftime('%A')
    return (
        f"Proposed trade: {trade['direction']} ({'buy' if trade['direction'] == 'CALL' else 'sell'}) EUR/USD now.\n"
        f"Strategy track: {trade['track']}. Stop loss {trade['sl']} pips, take profit {trade['tp']} pips.\n"
        f"Time: {hour_utc:02d}:00 UTC, {dow}.\n"
        + (calendar_line(cal) + '\n' if cal else '') +
        f"{ctx}\n\n"
        "Read the multi-timeframe structure, the levels and the volatility, and decide if this specific trade has "
        "positive expected value after costs. TAKE or VETO.\n"
        'Answer JSON: {"decision": "TAKE"|"VETO", "confidence": 0-100, "reasoning": "<max 300 chars>"}'
    )


# ---------------------------------------------------------------- LLM

def groq_keys():
    from src.common.config import Config
    return [k for k in (getattr(Config, 'GROQ_API_KEYS', None) or [getattr(Config, 'GROQ_API_KEY', '')]) if k]


def ask_ollama(prompt):
    """(dict|None, usage, error) con el modelo local. Un reintento si la respuesta no se puede leer."""
    last = None
    for _ in range(2):
        try:
            r = requests.post(OLLAMA_URL, json={
                'model': MODEL, 'stream': False, 'think': EFFORT,
                'options': {'temperature': 0.2, 'num_ctx': 16384},
                'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}]},
                timeout=900)
        except Exception as e:
            last = repr(e)[:200]
            time.sleep(5)
            continue
        if r.status_code != 200:
            last = f'HTTP {r.status_code}: {r.text[:200]}'
            time.sleep(5)
            continue
        j = r.json()
        usage = {'prompt_tokens': j.get('prompt_eval_count'), 'completion_tokens': j.get('eval_count')}
        d = parse(j.get('message', {}).get('content', ''))
        if d:
            return d, usage, None
        last = 'respuesta sin JSON válido'
    return None, {}, last


def ask(prompt, keys, state):
    """(dict|None, usage, error). Rota keys; ante 429 espera lo que diga el header y sigue."""
    if BACKEND == 'ollama':
        return ask_ollama(prompt)
    for _ in range(len(keys) * 4):
        k = keys[state['k'] % len(keys)]
        try:
            r = requests.post(GROQ_URL, headers={'Authorization': f'Bearer {k}', 'Content-Type': 'application/json'},
                              json={'model': 'openai/gpt-oss-120b', 'reasoning_effort': EFFORT, 'temperature': 0.2,
                                    'max_tokens': 6000,
                                    'messages': [{'role': 'system', 'content': SYSTEM},
                                                 {'role': 'user', 'content': prompt}]}, timeout=120)
        except Exception as e:
            time.sleep(5)
            last = repr(e)[:200]
            continue
        if r.status_code == 200:
            j = r.json()
            text = j['choices'][0]['message'].get('content') or ''
            return parse(text), j.get('usage', {}), None
        last = f'HTTP {r.status_code}: {r.text[:200]}'
        if r.status_code == 429:
            state['k'] += 1
            wait = r.headers.get('retry-after')
            if state['k'] % len(keys) == 0:      # dimos la vuelta a todas las keys: esperar
                time.sleep(min(float(wait) if wait else 30, 600))
            continue
        time.sleep(3)
    return None, {}, last


def parse(text):
    t = (text or '').strip()
    a, b = t.find('{'), t.rfind('}')
    if a < 0 or b <= a:
        return None
    try:
        d = json.loads(t[a:b + 1])
    except ValueError:
        return None
    dec = str(d.get('decision', '')).upper()
    if dec not in ('TAKE', 'VETO'):
        return None
    try:
        conf = max(0.0, min(100.0, float(d.get('confidence', 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return dict(decision=dec, confidence=conf, reasoning=str(d.get('reasoning', ''))[:400])


def placebo_map(trades):
    """Para cada trade, las velas de OTRO trade (derangement con semilla fija)."""
    ids = [x['sid'] for x in trades]
    rng = random.Random(PLACEBO_SEED)
    while True:
        p = ids[:]
        rng.shuffle(p)
        if all(a != b for a, b in zip(ids, p)):
            return dict(zip(ids, p))


# ---------------------------------------------------------------- corrida

def own_db():
    os.makedirs(os.path.dirname(OWN_DB), exist_ok=True)
    c = sqlite3.connect(OWN_DB)
    c.executescript(SCHEMA)
    return c


def run(limit=None, variants=('main', 'placebo')):
    trades = load_trades()
    M = load_m1()
    by = {x['sid']: x for x in trades}
    pmap = placebo_map(trades)
    cal = load_calendar() if 'calendar' in variants else {}
    keys = groq_keys() if BACKEND == 'groq' else []
    db = own_db()
    state = {'k': 0}
    done = {(r[0], r[1]) for r in db.execute('SELECT strategy_id, variant FROM judgments WHERE decision IS NOT NULL')}
    jobs = [(x['sid'], v) for x in trades for v in variants
            if (x['sid'], v) not in done and (v != 'calendar' or x['sid'] in cal)]
    print(f'{len(trades)} trades · faltan {len(jobs)} juicios · keys {len(keys)}', flush=True)
    for n, (sid, var) in enumerate(jobs[:limit] if limit else jobs, 1):
        src = sid if var == 'main' else pmap[sid]
        ctx, _ = build_context(M, by[src]['t'])
        if ctx is None:
            db.execute('INSERT OR REPLACE INTO judgments (strategy_id, variant, candles_from, error, created_at) '
                       'VALUES (?,?,?,?,?)', (sid, var, src, 'sin velas', dt.datetime.now().isoformat()))
            db.commit()
            continue
        d, usage, err = ask(build_prompt(by[sid], ctx, cal.get(sid) if var == 'calendar' else None), keys, state)
        db.execute('INSERT OR REPLACE INTO judgments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   (sid, var, src, d and d['decision'], d and d['confidence'], d and d['reasoning'], MODEL, EFFORT,
                    usage.get('prompt_tokens'), usage.get('completion_tokens'),
                    err if d is None else None, dt.datetime.now().isoformat()))
        db.commit()
        if n % 10 == 0:
            print(f'  {n}/{len(jobs)}', flush=True)


def evaluate(rows, label):
    """rows: [(pnl, decision, t)]. Devuelve métricas de separación TAKE vs VETO."""
    take = np.array([p for p, d, _ in rows if d == 'TAKE'])
    veto = np.array([p for p, d, _ in rows if d == 'VETO'])
    n = len(rows)
    if take.size < 5 or veto.size < 5:
        return dict(label=label, n=n, take=int(take.size), veto=int(veto.size), diff=None)
    rng = np.random.default_rng(PLACEBO_SEED)
    boots = np.array([rng.choice(take, take.size).mean() - rng.choice(veto, veto.size).mean() for _ in range(5000)])
    rows_t = sorted(rows, key=lambda r: r[2])
    half = n // 2

    def d_of(rr):
        a = [p for p, d, _ in rr if d == 'TAKE']
        b = [p for p, d, _ in rr if d == 'VETO']
        return (np.mean(a) - np.mean(b)) if a and b else float('nan')
    return dict(label=label, n=n, take=int(take.size), veto=int(veto.size), veto_rate=veto.size / n,
                take_mean=float(take.mean()), veto_mean=float(veto.mean()), take_total=float(take.sum()),
                all_total=float(take.sum() + veto.sum()), diff=float(take.mean() - veto.mean()),
                ci=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                halves=[float(d_of(rows_t[:half])), float(d_of(rows_t[half:]))])


def report():
    trades = {x['sid']: x for x in load_trades()}
    db = own_db()
    res = {}
    for var in ('main', 'placebo'):
        rows = [(trades[s]['pnl'], d, trades[s]['t']) for s, d in
                db.execute('SELECT strategy_id, decision FROM judgments WHERE variant=? AND decision IS NOT NULL',
                           (var,)) if s in trades]
        res[var] = evaluate(rows, var)
    m, p = res['main'], res['placebo']
    errs = db.execute('SELECT variant, COUNT(*) FROM judgments WHERE decision IS NULL GROUP BY variant').fetchall()
    print('=' * 80)
    print('P27 — juez LLM con contexto completo sobre trades reales de AIdan (USD por trade, broker-truth)')
    print('=' * 80)
    for r in (m, p):
        if r.get('diff') is None:
            print(f"  {r['label']:8} n={r['n']} take={r['take']} veto={r['veto']} — muestra insuficiente")
            continue
        print(f"  {r['label']:8} n={r['n']} veto {r['veto_rate']:.0%} · TAKE {r['take_mean']:+.2f} vs VETO "
              f"{r['veto_mean']:+.2f} · diferencia {r['diff']:+.2f} CI [{r['ci'][0]:+.2f}, {r['ci'][1]:+.2f}] · "
              f"mitades {r['halves'][0]:+.2f}/{r['halves'][1]:+.2f} · total TAKE ${r['take_total']:+.2f} "
              f"vs todo ${r['all_total']:+.2f}")
    print(f'  fallidos: {errs}')
    if m.get('diff') is None or p.get('diff') is None:
        print('  >>> SIN VEREDICTO (falta muestra)')
        return
    crit = {
        f'1_n>={MIN_N}': m['n'] >= MIN_N,
        '2_veto_entre_15_y_85%': VETO_BAND[0] <= m['veto_rate'] <= VETO_BAND[1],
        '3_TAKE>VETO_CI_inf>0': m['ci'][0] > 0,
        '4_dos_mitades>0': all(h > 0 for h in m['halves']),
        '5_placebo_separa_menos': p['diff'] < m['diff'] and p['ci'][0] <= 0,
    }
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f"  >>> {'PASA' if ok else 'NO PASA'}")
    out = dict(criterio='docs/p27_llm_judge_criterio.md', main=m, placebo=p, criterios=crit, PASA=ok)
    out['P27b'] = report_calendar(trades, db)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, default=float)


def report_calendar(trades, db):
    """P27b: juez + calendario. Criterio en docs/p27_llm_judge_criterio.md (sección P27b)."""
    dec = {}
    for s, v, d in db.execute("SELECT strategy_id, variant, decision FROM judgments "
                              "WHERE variant IN ('main','calendar') AND decision IS NOT NULL"):
        dec.setdefault(s, {})[v] = d
    print('-' * 80)
    print('P27b — mismo juez + calendario económico registrado en el momento')
    rows = [(trades[s]['pnl'], d['calendar'], trades[s]['t']) for s, d in dec.items()
            if 'calendar' in d and s in trades]
    c = evaluate(rows, 'calendar')
    if c.get('diff') is None:
        print(f"  calendar n={c['n']} — muestra insuficiente / SIN VEREDICTO")
        return c
    pair = [(trades[s]['pnl'], d['calendar'] == 'TAKE', d['main'] == 'TAKE') for s, d in dec.items()
            if 'calendar' in d and 'main' in d and s in trades]
    pnl = np.array([x[0] for x in pair])
    tc = np.array([x[1] for x in pair])
    tm = np.array([x[2] for x in pair])

    def sep(idx, take):
        a, b = pnl[idx][take[idx]], pnl[idx][~take[idx]]
        return (a.mean() - b.mean()) if a.size and b.size else np.nan
    rng = np.random.default_rng(PLACEBO_SEED)
    allidx = np.arange(len(pair))
    gain = sep(allidx, tc) - sep(allidx, tm)
    bs = []
    for _ in range(5000):
        ii = rng.integers(0, len(pair), len(pair))
        bs.append(sep(ii, tc) - sep(ii, tm))
    bs = np.array([x for x in bs if np.isfinite(x)])
    gci = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    print(f"  calendar n={c['n']} veto {c['veto_rate']:.0%} · TAKE {c['take_mean']:+.2f} vs VETO {c['veto_mean']:+.2f}"
          f" · diferencia {c['diff']:+.2f} CI [{c['ci'][0]:+.2f}, {c['ci'][1]:+.2f}]"
          f" · mitades {c['halves'][0]:+.2f}/{c['halves'][1]:+.2f}")
    print(f"  aporte del calendario sobre P27 (mismos {len(pair)} trades): {gain:+.2f} CI [{gci[0]:+.2f}, {gci[1]:+.2f}]")
    cal = load_calendar()
    near = [i for i, (s, d) in enumerate((s, d) for s, d in dec.items() if 'calendar' in d and 'main' in d
                                         and s in trades)
            if cal.get(s) and ((cal[s]['next_impact'] == 'High' and (cal[s]['mins_to_next'] or 1e9) <= 60) or
                               (cal[s]['prev_impact'] == 'High' and (cal[s]['mins_since_prev'] or 1e9) <= 30))]
    if near:
        ni = np.array(near)
        print(f"  [desc] cerca de evento alto: n={ni.size} · veto con calendario {1 - tc[ni].mean():.0%} vs sin "
              f"{1 - tm[ni].mean():.0%} · separación con {sep(ni, tc):+.2f} vs sin {sep(ni, tm):+.2f}")
    crit = {
        f'1_n>={MIN_N}': c['n'] >= MIN_N,
        '2_veto_entre_15_y_85%': VETO_BAND[0] <= c['veto_rate'] <= VETO_BAND[1],
        '3_TAKE>VETO_CI_inf>0': c['ci'][0] > 0,
        '4_dos_mitades>0': all(h > 0 for h in c['halves']),
        '5_aporta_sobre_P27_CI_inf>0': gci[0] > 0,
    }
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f"  >>> P27b {'PASA' if ok else 'NO PASA'}")
    return dict(c, aporte=float(gain), aporte_ci=gci, n_cerca_evento=len(near), criterios=crit, PASA=ok)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--smoke', type=int)
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--report', action='store_true')
    ap.add_argument('--variants', default='main,placebo', help="main,placebo | calendar (P27b)")
    a = ap.parse_args()
    if a.smoke:
        trades = load_trades()
        M = load_m1()
        for x in trades[-a.smoke:]:
            ctx, ref = build_context(M, x['t'])
            print(build_prompt(x, ctx) if ctx else f"#{x['sid']} sin velas")
            print('-' * 60)
        print(f'{len(trades)} trades, {trades[0]["created_ar"]} -> {trades[-1]["created_ar"]}')
    if a.run:
        run(a.limit, tuple(a.variants.split(',')))
    if a.report:
        report()


if __name__ == '__main__':
    main()
