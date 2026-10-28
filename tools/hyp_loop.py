"""
hyp_loop.py — P22: loop de hipótesis. La IA propone (lista cerrada), el arnés prueba con 3 etapas
(descubrimiento → reserva → shadow hacia adelante) y TODO lo probado vuelve como memoria a la próxima vuelta.

Read-only respecto de AIdan: sin MT5, no toca la DB de AIdan, no manda órdenes. Escribe solo en
`%APPDATA%/AIdan/state/hypothesis_loop.db`. Criterio declarado ANTES de medir: docs/p22_loop_hipotesis_criterio.md.

Uso:
    python tools/hyp_loop.py --cycle               # una vuelta: control, propone (Groq), valida, evalúa, shadows
    python tools/hyp_loop.py --cycle --n 8         # cuántas hipótesis evaluar como máximo
    python tools/hyp_loop.py --spec file.json      # vuelta con hipótesis escritas a mano (sin LLM)
    python tools/hyp_loop.py --report              # memoria: qué se probó, qué pasó, qué familias cerraron
    python tools/hyp_loop.py --control             # solo el control positivo/negativo del arnés
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import hyp_data as hd  # noqa: E402

DISC = ('1999-01-01', '2014-12-31')
HOLD_START = '2015-01-01'
HORIZONS = [5, 10, 20]
MARKUP = 0.01                    # margen anual del broker sobre el swap, siempre en contra
MIN_ACTIVE = 30
BLOCK = 4
BOOT = 5000
N_CONTROL = 200
CLOSE_AFTER = 3                  # familia cerrada tras 3 variantes que no pasan A
SHADOW_MIN = 26
SEED = 20261028

# Lo que el proyecto ya refutó ANTES de este loop (contexto para la IA; no bloquea por sí solo).
PRIOR_LESSONS = [
    'Precio intradía M5/M15 (rupturas, structure, SMC de Leo, rango asiático, NR7): peor que el azar, 2020-26.',
    'Reversión a 2σ intradía: le gana al azar pero el costo se la come.',
    'Momentum de 60 días semanal (TSMOM) en 20 pares: perdió, 2020-26 (datos MT5).',
    'Carry de FX con y sin filtro de tendencia, semanal: ~0, el precio se come el swap, 2020-26.',
    'Donchian 20/55 en D1 (seguir y contrariar la ruptura): sin edge en FX 2020-26.',
    'Fin de mes (rebalanceo), pre-FOMC en índices, lead-lag de la cesta USD: no pasaron.',
    'LLMs decidiendo dirección por noticias: peor que seguir la deriva.',
]


# ── registro ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, data_end TEXT, control_json TEXT,
    source TEXT, n_proposed INTEGER, n_valid INTEGER, n_evaluated INTEGER, notes TEXT);
CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER, created_at TEXT, source TEXT,
    family TEXT, variant TEXT, spec_json TEXT, rationale TEXT, status TEXT, reason TEXT,
    disc_json TEXT, hold_json TEXT, shadow_json TEXT, promoted_at TEXT);
"""


def default_db():
    return os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state', 'hypothesis_loop.db')


def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ── hipótesis: forma canónica, familia, validación ───────────────────────────

def stance(cond, position):
    """'sigue' si la posición va para el mismo lado que la feature alta, 'contraria' si va al revés."""
    up = cond['op'] == '>'
    return 'sigue' if up == (position == 'long_fx') else 'contraria'


def family_of(spec):
    return '+'.join(sorted(f"{c['feature']}:{stance(c, spec['position'])}" for c in spec['conditions']))


def variant_of(spec):
    conds = sorted((c['feature'], c['op'], float(c['threshold'])) for c in spec['conditions'])
    raw = json.dumps([family_of(spec), spec['pairs'], int(spec['horizon']), conds, spec['position'],
                      bool(spec.get('symmetric'))])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def validate(spec, closed, seen_variants, cycle_families):
    """Devuelve (ok, motivo). Lista cerrada: todo lo que no está en el catálogo se rechaza."""
    try:
        if spec.get('pairs') not in hd.CCYS + ['ALL']:
            return False, f"moneda inválida: {spec.get('pairs')}"
        conds = spec.get('conditions') or []
        if not 1 <= len(conds) <= 2:
            return False, 'hace falta 1 o 2 condiciones'
        feats = [c.get('feature') for c in conds]
        if len(set(feats)) != len(feats):
            return False, 'condiciones sobre la misma feature'
        for c in conds:
            if c.get('feature') not in hd.CATALOG:
                return False, f"feature fuera del catálogo: {c.get('feature')}"
            if c.get('op') not in ('>', '<'):
                return False, f"operador inválido: {c.get('op')}"
            if float(c.get('threshold')) not in hd.CATALOG[c['feature']][1]:
                return False, f"umbral fuera de la lista para {c['feature']}: {c.get('threshold')}"
        if spec.get('position') not in ('long_fx', 'short_fx'):
            return False, f"posición inválida: {spec.get('position')}"
        if spec.get('symmetric'):
            if len(conds) != 1 or conds[0]['op'] != '>' or float(conds[0]['threshold']) < 0:
                return False, 'simétrica: 1 condición, operador > y umbral >= 0'
        if int(spec.get('horizon', 0)) not in HORIZONS:
            return False, f"horizonte inválido: {spec.get('horizon')}"
        if len((spec.get('rationale') or '').strip()) < 20:
            return False, 'falta el mecanismo (quién paga y por qué)'
    except (TypeError, ValueError, AttributeError) as e:
        return False, f'forma inválida: {e}'
    fam = family_of(spec)
    if fam in closed:
        return False, f'familia cerrada (ya falló {CLOSE_AFTER} veces): {fam}'
    if variant_of(spec) in seen_variants:
        return False, 'duplicado exacto de una ya probada'
    if fam in cycle_families:
        return False, 'misma familia que otra de esta vuelta'
    return True, ''


# ── evaluación ───────────────────────────────────────────────────────────────

def _cond_mask(df, c):
    v = df[c['feature']].to_numpy(dtype=float)
    thr = float(c['threshold'])
    with np.errstate(invalid='ignore'):
        return (v > thr) if c['op'] == '>' else (v < thr)


def raw_positions(df, spec):
    """Posición diaria de la regla (+1 compra la moneda, −1 la vende, 0 afuera)."""
    sign = 1 if spec['position'] == 'long_fx' else -1
    if spec.get('symmetric'):
        c = spec['conditions'][0]
        v = df[c['feature']].to_numpy(dtype=float)
        thr = float(c['threshold'])
        with np.errstate(invalid='ignore'):
            return np.where(v > thr, sign, np.where(v < -thr, -sign, 0)).astype(float)
    m = np.ones(len(df), dtype=bool)
    for c in spec['conditions']:
        m &= _cond_mask(df, c)
    return np.where(m, sign, 0).astype(float)


def legs(panel, ccy, h, start, end, after=None):
    """Para una moneda y horizonte: índices de los períodos (no se pisan) y sus retornos, costos y swap."""
    df = panel[ccy]
    idx = df.index
    lo = idx.searchsorted(pd.Timestamp(start))
    hi = idx.searchsorted(pd.Timestamp(end), side='right')
    if after is not None:
        lo = max(lo, idx.searchsorted(pd.Timestamp(after), side='right'))
    anchors = np.arange(lo, hi - h, h)
    if anchors.size == 0:
        return None
    fx = df['fx'].to_numpy(dtype=float)
    q = df['quoted'].to_numpy(dtype=float)
    ret = np.log(fx[anchors + h] / fx[anchors])
    cost = hd.COST_PIPS[ccy] * hd.PIP[ccy] / q[anchors]                     # ida y vuelta, en fracción
    days = (idx[anchors + h] - idx[anchors]).days.to_numpy(dtype=float)
    rd = df['rate_diff'].to_numpy(dtype=float)[anchors]
    carry = np.nan_to_num(rd) / 100.0 * days / 365.0
    mark = MARKUP * days / 365.0
    ok = np.isfinite(ret) & np.isfinite(cost)
    return dict(anchors=anchors[ok], dates=idx[anchors[ok]], ret=ret[ok], cost=cost[ok],
                carry=carry[ok], mark=mark[ok])


def net_series(leg, pos):
    """Neto por período de una moneda con posiciones `pos` (costo de cada cambio a mitad de ida y vuelta)."""
    n = pos.size
    prev = np.concatenate([[0.0], pos[:-1]])
    change_cost = np.abs(pos - prev) * leg['cost'] / 2.0
    net = pos * leg['ret'] + pos * leg['carry'] - np.abs(pos) * leg['mark']
    # el costo de salir (pos pasa a 0) se carga al último período con posición; el de entrar, al que abre
    attrib = np.where(pos != 0, np.arange(n), np.arange(n) - 1)
    for i in range(n):
        if change_cost[i] > 0 and attrib[i] >= 0:
            net[attrib[i]] -= change_cost[i]
    if n and pos[-1] != 0:                                    # cierre al final del tramo
        net[-1] -= abs(pos[-1]) * leg['cost'][-1] / 2.0
    return net


def portfolio(per_ccy):
    """Promedio por período de las monedas con posición. per_ccy: lista de (dates, pos, net)."""
    frames = []
    for dates, pos, net in per_ccy:
        frames.append(pd.DataFrame({'d': dates, 'net': np.where(pos != 0, net, np.nan)}))
    if not frames:
        return np.array([]), []
    allf = pd.concat(frames)
    g = allf.groupby('d')['net'].mean().dropna().sort_index()
    return g.to_numpy(), list(g.index)


def block_boot_means(x, rng, n=BOOT, block=BLOCK):
    if x.size < block * 2:
        return np.array([x.mean()] * 10)
    nb = int(np.ceil(x.size / block))
    starts = rng.integers(0, x.size - block + 1, (n, nb))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n, -1)[:, :x.size]
    return x[idx].mean(axis=1)


def stats(x, rng):
    if x.size == 0:
        return dict(n=0, mean_bps=None)
    bm = block_boot_means(x, rng)
    half = x.size // 2
    return dict(n=int(x.size), mean_bps=float(x.mean() * 1e4), ci_lo_bps=float(np.percentile(bm, 2.5) * 1e4),
                ci_hi_bps=float(np.percentile(bm, 97.5) * 1e4),
                half1_bps=float(x[:half].mean() * 1e4) if half else None,
                half2_bps=float(x[half:].mean() * 1e4) if half else None,
                p_one_sided=float((bm <= 0).mean()),
                t=float(x.mean() / (x.std(ddof=1) / np.sqrt(x.size))) if x.size > 2 and x.std() > 0 else 0.0)


def evaluate(panel, spec, start, end, after=None, pos_override=None, control=False, rng=None):
    """Evalúa la regla en [start, end]. `pos_override(ccy, leg, df) -> pos` reemplaza la regla (controles)."""
    rng = rng or np.random.default_rng(SEED)
    h = int(spec['horizon'])
    ccys = hd.CCYS if spec['pairs'] == 'ALL' else [spec['pairs']]
    built = []
    for c in ccys:
        leg = legs(panel, c, h, start, end, after)
        if leg is None:
            continue
        if pos_override is not None:
            pos = pos_override(c, leg, panel[c])
        else:
            pos = raw_positions(panel[c], spec)[leg['anchors']]
        built.append((c, leg, pos))
    x, _ = portfolio([(leg['dates'], pos, net_series(leg, pos)) for _, leg, pos in built])
    out = stats(x, rng)
    if control and x.size:
        ctrl = []
        for _ in range(N_CONTROL):
            per = []
            for _, leg, pos in built:
                k = int(rng.integers(max(1, pos.size // 10), max(2, pos.size - pos.size // 10)))
                sp = np.roll(pos, k)
                per.append((leg['dates'], sp, net_series(leg, sp)))
            cx, _ = portfolio(per)
            ctrl.append(cx.mean() * 1e4 if cx.size else np.nan)
        out['control_p95_bps'] = float(np.nanpercentile(ctrl, 95))
    return out


def gate_a(s):
    checks = {
        '1_n>=30': s['n'] >= MIN_ACTIVE,
        '2_media>0': (s.get('mean_bps') or 0) > 0,
        '3_CI_inf>0': (s.get('ci_lo_bps') or -1) > 0,
        '4_dos_mitades>0': (s.get('half1_bps') or -1) > 0 and (s.get('half2_bps') or -1) > 0,
        '5_gana_al_azar': (s.get('mean_bps') or -1e9) > (s.get('control_p95_bps') or 1e9),
    }
    return all(checks.values()), checks


def gate_b(s, k):
    checks = {'media>0': (s.get('mean_bps') or 0) > 0, f'p<0.05/{k}': (s.get('p_one_sided', 1)) < 0.05 / k}
    return all(checks.values()), checks


# ── control positivo / negativo ──────────────────────────────────────────────

def run_controls(panel, rng=None):
    rng = rng or np.random.default_rng(SEED)
    base = dict(pairs='EUR', horizon=5, position='long_fx', conditions=[])

    def oracle(acc):
        def f(c, leg, df):
            truth = np.sign(leg['ret'])
            flip = rng.random(truth.size) > acc
            return np.where(flip, -truth, truth).astype(float)
        return f

    def ar_noise(c, leg, df):
        e = rng.standard_normal(leg['ret'].size)
        z = np.zeros_like(e)
        for i in range(1, e.size):
            z[i] = 0.75 * z[i - 1] + e[i]
        return np.sign(z)

    pos_s = evaluate(panel, base, *DISC, pos_override=oracle(0.60), control=True, rng=rng)
    pos_ok, _ = gate_a(pos_s)
    null_pass = 0
    for _ in range(20):
        s = evaluate(panel, base, *DISC, pos_override=ar_noise, control=True, rng=rng)
        null_pass += gate_a(s)[0]
    ok = bool(pos_ok and null_pass <= 3)
    return dict(ok=ok, positive_60pct_passes=bool(pos_ok), positive_mean_bps=pos_s.get('mean_bps'),
                null_passes_of_20=int(null_pass))


# ── memoria ──────────────────────────────────────────────────────────────────

def memory(conn):
    rows = conn.execute("SELECT * FROM hypotheses WHERE status != 'rechazada'").fetchall()
    fam = {}
    feat = {f: dict(n=0, passA=0, best=None, worst=None) for f in hd.CATALOG}
    variants = set()
    for r in rows:
        variants.add(r['variant'])
        spec = json.loads(r['spec_json'])
        d = json.loads(r['disc_json']) if r['disc_json'] else None
        passed = r['status'] not in ('falló_A', 'propuesta')
        f = fam.setdefault(r['family'], dict(n=0, passA=0, best=None))
        f['n'] += 1
        f['passA'] += passed
        m = d.get('mean_bps') if d else None
        if m is not None:
            f['best'] = m if f['best'] is None else max(f['best'], m)
        for c in spec['conditions']:
            e = feat[c['feature']]
            e['n'] += 1
            e['passA'] += passed
            if m is not None:
                e['best'] = m if e['best'] is None else max(e['best'], m)
                e['worst'] = m if e['worst'] is None else min(e['worst'], m)
    closed = {k for k, v in fam.items() if v['passA'] == 0 and v['n'] >= CLOSE_AFTER}
    few = sum(1 for r in rows if r['disc_json'] and json.loads(r['disc_json']).get('n', 0) < MIN_ACTIVE)
    return dict(families=fam, features=feat, closed=closed, variants=variants, few=few)


def memory_text(mem):
    lines = ['FEATURES (veces probada / pasaron descubrimiento / mejor y peor neto en bps por período):']
    for f, e in sorted(mem['features'].items(), key=lambda kv: kv[1]['n']):
        b = '-' if e['best'] is None else f"{e['best']:+.1f}"
        w = '-' if e['worst'] is None else f"{e['worst']:+.1f}"
        lines.append(f"  {f}: {e['n']} / {e['passA']} / mejor {b} peor {w}  — {hd.CATALOG[f][0]}")
    lines.append('FAMILIAS CERRADAS (no proponer nada de estas): ' + (', '.join(sorted(mem['closed'])) or 'ninguna'))
    tested = [f"{k} ({v['n']} variantes, {v['passA']} pasaron)" for k, v in mem['families'].items()
              if k not in mem['closed']]
    lines.append('FAMILIAS YA PROBADAS Y ABIERTAS: ' + ('; '.join(tested) or 'ninguna'))
    lines.append('LO QUE EL PROYECTO YA REFUTÓ ANTES DE ESTE LOOP:')
    lines += [f'  - {x}' for x in PRIOR_LESSONS]
    return '\n'.join(lines)


# ── proponente (Groq) ────────────────────────────────────────────────────────

def llm_propose(mem, n):
    import requests
    from src.common.config import Config
    catalog = '\n'.join(f"  {k} [fuente: {hd.SOURCE[k]}]: {v[0]}. Umbrales permitidos: {v[1]}"
                        for k, v in hd.CATALOG.items())
    untested = [f for f, e in mem['features'].items() if e['n'] == 0]
    phase = (f"Todavía hay features sin probar: {', '.join(untested)}. Priorizalas." if untested else
             "Todas las features ya se probaron solas y ninguna alcanzó. AHORA: al menos 3 de cada 4 hipótesis tienen "
             "que COMBINAR 2 condiciones de FUENTES distintas, y cuando el mecanismo es de una moneda puntual (petróleo "
             "-> CAD, tasas de Japón -> JPY, riesgo -> AUD/NZD contra JPY/CHF) usá esa moneda, no ALL. El espejo de una "
             "idea (el otro extremo de la feature con la posición opuesta) es la MISMA familia: no lo propongas.")
    prompt = f"""Sos un investigador cuantitativo. Proponé {n + 4} hipótesis NUEVAS y DISTINTAS entre sí para operar
monedas contra el USD (EUR, JPY, GBP, CHF, CAD, AUD, NZD) con horizonte de días, usando SOLO este catálogo:
{catalog}

Formato de cada hipótesis (JSON):
{{"pairs": "EUR|JPY|GBP|CHF|CAD|AUD|NZD|ALL", "conditions": [{{"feature": "...", "op": ">" o "<", "threshold": número de la lista}}]
 (1 o 2 condiciones, se cumplen las dos), "position": "long_fx" (comprar la moneda contra USD) o "short_fx",
 "symmetric": false (o true con 1 condición, op ">" y umbral >= 0: arriba del umbral la posición, debajo de -umbral la contraria),
 "horizon": 5|10|20 (días hábiles), "rationale": "mecanismo económico: quién paga este premio y por qué"}}
Todas las features de moneda están orientadas a la moneda extranjera: positivo = la moneda viene fuerte / está más cara / sus especuladores están largos.

Memoria de TODO lo probado hasta ahora (aprendé de esto: no repitas familias cerradas, explorá features poco
probadas, y si una feature mostró algo de información probá combinarla con OTRA fuente de datos distinta):
{memory_text(mem)}

{phase}
Reglas: cada hipótesis de una FAMILIA distinta (familia = features + si sigue o contraría la feature; cambiar
umbral, horizonte o moneda NO es una idea nueva). Preferí combinar dos fuentes distintas (posicionamiento + tasas,
tasas + otros mercados, etc.). El mecanismo tiene que explicar quién pierde plata del otro lado.
Una hipótesis necesita >= 30 períodos con posición en 1999-2014 o no puede pasar (ya pasaron {mem['few']} que
quedaron cortas): con 2 condiciones en una sola moneda usá umbrales moderados (0, ±0.5, ±1), no extremos.
Respondé SOLO un JSON: {{"hypotheses": [ ... ]}}"""
    keys = [k for k in getattr(Config, 'GROQ_API_KEYS', []) if k] or [Config.GROQ_API_KEY]
    last = None
    for key in [k for k in keys for _ in range(3)]:            # cada key hasta 3 veces (límite por minuto)
        try:
            r = requests.post('https://api.groq.com/openai/v1/chat/completions',
                              headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                              json={'model': getattr(Config, 'GROQ_MODEL', 'openai/gpt-oss-120b'),
                                    'messages': [{'role': 'user', 'content': prompt}],
                                    'temperature': 0.8, 'max_tokens': 5000, 'reasoning_effort': 'medium',
                                    'response_format': {'type': 'json_object'}},
                              timeout=180)
            if r.status_code == 200:
                content = r.json()['choices'][0]['message']['content']
                return json.loads(content).get('hypotheses', []), 'groq:' + Config.GROQ_MODEL
            last = f'{r.status_code} {r.text[:200]}'
            if r.status_code == 429:
                time.sleep(65)
        except Exception as e:
            last = repr(e)
    raise RuntimeError(f'Groq no respondió: {last}')


# ── vuelta ───────────────────────────────────────────────────────────────────

def score_shadows(conn, panel, data_end):
    out = []
    for r in conn.execute("SELECT * FROM hypotheses WHERE status = 'shadow'").fetchall():
        spec = json.loads(r['spec_json'])
        s = evaluate(panel, spec, r['promoted_at'], data_end, after=r['promoted_at'])
        verdict = None
        if s['n'] >= SHADOW_MIN:
            verdict = 'candidata' if (s['mean_bps'] or 0) > 0 else 'falló_shadow'
        conn.execute('UPDATE hypotheses SET shadow_json=?, status=COALESCE(?, status) WHERE id=?',
                     (json.dumps(s), verdict, r['id']))
        out.append((r['id'], r['family'], s, verdict))
    conn.commit()
    return out


def cycle(conn, panel, specs, source, n_max):
    data_end = str(max(df.index[-1] for df in panel.values()).date())
    rng = np.random.default_rng(SEED)
    ctrl = run_controls(panel, rng)
    cur = conn.execute('INSERT INTO cycles (started_at, data_end, control_json, source) VALUES (?,?,?,?)',
                       (dt.datetime.now().isoformat(timespec='seconds'), data_end, json.dumps(ctrl), source))
    cid = cur.lastrowid
    print(f"control del arnés: positivo 60% {'PASA' if ctrl['positive_60pct_passes'] else 'NO PASA'} "
          f"({ctrl['positive_mean_bps']:+.1f} bps) · ruido pasó {ctrl['null_passes_of_20']}/20 ⇒ "
          f"{'OK' if ctrl['ok'] else 'VUELTA ANULADA'}")
    if not ctrl['ok']:
        conn.execute("UPDATE cycles SET notes='control falló: vuelta anulada' WHERE id=?", (cid,))
        conn.commit()
        return
    mem = memory(conn)
    valid, fams = [], set()
    now = dt.datetime.now().isoformat(timespec='seconds')
    for spec in specs:
        ok, why = validate(spec, mem['closed'], mem['variants'], fams)
        if ok:
            fams.add(family_of(spec))
            valid.append(spec)
        else:
            conn.execute('INSERT INTO hypotheses (cycle_id, created_at, source, family, variant, spec_json, '
                         'rationale, status, reason) VALUES (?,?,?,?,?,?,?,?,?)',
                         (cid, now, source, _safe_family(spec), None, json.dumps(spec),
                          spec.get('rationale') if isinstance(spec, dict) else None, 'rechazada', why))
    # exploración antes que refinamiento: primero las que usan features menos probadas
    # y, una vez probada cada feature, primero las que combinan dos FUENTES distintas (confluencia)
    valid.sort(key=lambda s: (min(mem['features'][c['feature']]['n'] for c in s['conditions']),
                              -len({hd.SOURCE[c['feature']] for c in s['conditions']})))
    chosen = valid[:n_max]
    k_hold = conn.execute('SELECT COUNT(*) FROM hypotheses WHERE hold_json IS NOT NULL').fetchone()[0]
    print(f'propuestas {len(specs)} · válidas {len(valid)} · se evalúan {len(chosen)}')
    for spec in chosen:
        hid = conn.execute('INSERT INTO hypotheses (cycle_id, created_at, source, family, variant, spec_json, '
                           'rationale, status) VALUES (?,?,?,?,?,?,?,?)',
                           (cid, now, source, family_of(spec), variant_of(spec), json.dumps(spec),
                            spec['rationale'], 'propuesta')).lastrowid
        conn.commit()                                          # pre-declarada antes de mirar
        sa = evaluate(panel, spec, *DISC, control=True, rng=rng)
        pa, ca = gate_a(sa)
        sa['checks'] = ca
        status, hold, promoted = 'falló_A', None, None
        if pa:
            k_hold += 1
            sb = evaluate(panel, spec, HOLD_START, data_end, rng=rng)
            pb, cb = gate_b(sb, k_hold)
            sb['checks'] = cb
            hold = json.dumps(sb)
            status = 'shadow' if pb else 'falló_B'
            promoted = data_end if pb else None
        conn.execute('UPDATE hypotheses SET status=?, disc_json=?, hold_json=?, promoted_at=? WHERE id=?',
                     (status, json.dumps(sa), hold, promoted, hid))
        conn.commit()
        m = sa.get('mean_bps')
        print(f"  #{hid} [{status}] {family_of(spec)} · {spec['pairs']} h{spec['horizon']} · "
              f"n={sa['n']} neto {m if m is None else round(m, 1)} bps "
              f"CI [{sa.get('ci_lo_bps', 0):+.1f}, {sa.get('ci_hi_bps', 0):+.1f}] azar p95 "
              f"{sa.get('control_p95_bps', float('nan')):+.1f}")
    conn.execute('UPDATE cycles SET n_proposed=?, n_valid=?, n_evaluated=? WHERE id=?',
                 (len(specs), len(valid), len(chosen), cid))
    conn.commit()
    for hid, fam, s, verdict in score_shadows(conn, panel, data_end):
        print(f"  shadow #{hid} {fam}: n={s['n']} neto {s.get('mean_bps')} ⇒ {verdict or 'juntando'}")


def _safe_family(spec):
    try:
        return family_of(spec)
    except Exception:
        return None


def report(conn):
    mem = memory(conn)
    tot = conn.execute("SELECT status, COUNT(*) FROM hypotheses GROUP BY status").fetchall()
    cyc = conn.execute('SELECT COUNT(*), MAX(started_at) FROM cycles').fetchone()
    print('=' * 78)
    print(f'LOOP DE HIPÓTESIS (P22) — {cyc[0]} vueltas, última {cyc[1]}')
    print('=' * 78)
    print('  por estado: ' + ' · '.join(f'{s} {n}' for s, n in tot))
    print(memory_text(mem))
    for r in conn.execute("SELECT id, family, pairs, status FROM (SELECT id, family, status, "
                          "json_extract(spec_json,'$.pairs') AS pairs FROM hypotheses) "
                          "WHERE status IN ('shadow','candidata','falló_B','falló_shadow')").fetchall():
        print(f"  #{r['id']} {r['status']}: {r['family']} ({r['pairs']})")


def main():
    if sys.stdout is None:                     # pythonw (tarea programada): todo a un log en state/
        log = os.path.join(os.environ.get('APPDATA', '.'), 'AIdan', 'state',
                           f'hyp_loop_{dt.date.today():%Y%m%d}.log')
        sys.stdout = sys.stderr = open(log, 'a', encoding='utf-8')
        print(f'--- {dt.datetime.now().isoformat(timespec="seconds")} {" ".join(sys.argv[1:])}')
    try:                                       # consola de Windows (cp1252)
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--cycle', action='store_true')
    ap.add_argument('--spec')
    ap.add_argument('--report', action='store_true')
    ap.add_argument('--control', action='store_true')
    ap.add_argument('--n', type=int, default=8)
    ap.add_argument('--db', default=default_db())
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    conn = connect(a.db)
    if a.report:
        report(conn)
        return
    panel = hd.build_panel(refresh=a.refresh)
    if a.control:
        print(json.dumps(run_controls(panel), indent=1))
        return
    if a.spec:
        with open(a.spec, encoding='utf-8') as f:
            specs, source = json.load(f), 'manual'
    elif a.cycle:
        specs, source = llm_propose(memory(conn), a.n)
    else:
        ap.print_help()
        return
    cycle(conn, panel, specs, source, a.n)
    report(conn)


if __name__ == '__main__':
    main()
