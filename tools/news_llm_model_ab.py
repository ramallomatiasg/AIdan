# -*- coding: utf-8 -*-
"""
news_llm_model_ab.py — ¿un modelo MEJOR encuentra senal donde el anterior no encontro?

READ-ONLY sobre la DB (solo SELECT). No manda ordenes, no toca produccion. Llama a Groq.

═══ POR QUE EXISTE ═══════════════════════════════════════════════════════════

En julio, measure_news_llm_error.py midio el juicio direccional del LLM de news con
llama-3.3-70b y dio: discriminacion -1pp (Fisher p=0,845) y hit 52% contra 61% de la
mejor regla constante => NO discrimina, y es ANTI-SKILL.

El 16-ago Groq dio de baja ese modelo. El reemplazo (gpt-oss-120b) puntua mas alto en
benchmarks publicos. La pregunta del user: ¿un modelo mejor / especializado no deberia
ver senales que el anterior no vio?

═══ QUE MIDE, Y QUE NO ═══════════════════════════════════════════════════════

PRIMARIO: la discriminacion del MODELO NUEVO, sobre las mismas alertas historicas y con
EXACTAMENTE el mismo outcome que uso el medidor de julio (se lee de su dump CSV; no se
recalcula el anclaje de velas — esa divergencia silenciosa ya invirtio la realidad una vez
en este proyecto, caso bounce).

    discriminacion = P(subio | CALL) - P(subio | PUT)     (Fisher, inmune al drift)

Se eligio esta metrica y no un head-to-head contra el 70B como titular por una razon
honesta: **el 70B esta dado de baja y NO se puede re-correr**. Sus predicciones guardadas
salieron del prompt vigente en su momento, que cambio entre abril y hoy (el propio medidor
marca "contaminacion de version del prompt" por mes). Comparar contra ellas mezcla cambio
de modelo con cambio de prompt.

La pregunta se contesta igual SIN esa comparacion: si el modelo nuevo tampoco discrimina,
entonces no es el modelo — es la tarea. El numero del 70B se reporta como CONTEXTO.

═══ CRITERIO DECLARADO ANTES DE CORRER ═══════════════════════════════════════

  - "NO es el modelo, es la tarea"  si |edge| < 10pp  O  Fisher p >= 0,05
  - "el modelo SI importa"          si edge >= +10pp  Y  Fisher p < 0,05
  - Se reporta tambien hit direccional vs la mejor-constante del periodo (61%): si el
    modelo nuevo tampoco le gana al drift, sigue siendo ANTI-SKILL.

LIMITES declarados: el prompt de hoy no es el de abril; el universo son las alertas que el
70B ya marco direccionales (si el 70B se callaba, esa noticia no esta) => esto mide juicio
sobre un universo pre-filtrado por el modelo viejo, no la tarea entera.

Uso:
    python tools/measure_news_llm_error.py            # con NEWS_DUMP_CSV=<ruta>
    python tools/news_llm_model_ab.py --truth <ruta csv> [--limit N] [--model X]
"""
import argparse
import csv
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
DEADBAND = 2.0          # mismo que el medidor de julio
THROTTLE_S = 2.2        # free tier: ~30 req/min


def fisher_2x2(a, b, c, d):
    """p two-sided de Fisher para [[a,b],[c,d]] sin scipy."""
    from math import lgamma

    def lc(n, k):
        return lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)

    n = a + b + c + d
    r1, c1 = a + b, a + c
    obs = lc(r1, a) + lc(n - r1, c1 - a) - lc(n, c1)
    tot = 0.0
    lo = max(0, c1 - (n - r1))
    hi = min(r1, c1)
    import math
    for x in range(lo, hi + 1):
        l = lc(r1, x) + lc(n - r1, c1 - x) - lc(n, c1)
        if l <= obs + 1e-9:
            tot += math.exp(l)
    return min(1.0, tot)


def discriminate(pairs, label):
    """pairs = [(direction, subio_bool)] -> imprime y devuelve el edge en puntos."""
    call = [s for d, s in pairs if d == 'CALL']
    put = [s for d, s in pairs if d == 'PUT']
    if not call or not put:
        print(f'  {label}: sin ambas direcciones (CALL={len(call)} PUT={len(put)})')
        return None, None
    pc = sum(call) / len(call)
    pp = sum(put) / len(put)
    edge = (pc - pp) * 100
    p = fisher_2x2(sum(call), len(call) - sum(call), sum(put), len(put) - sum(put))
    print(f'  {label}')
    print(f'      CALL: n={len(call):<4} P(subio|CALL)={pc*100:.0f}%')
    print(f'      PUT : n={len(put):<4} P(subio|PUT )={pp*100:.0f}%')
    print(f'      edge = {edge:+.0f} puntos   (Fisher p={p:.4f})')
    return edge, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--truth', required=True, help='CSV de measure_news_llm_error.py')
    ap.add_argument('--limit', type=int, default=0, help='0 = todas')
    ap.add_argument('--model', default=None)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    from src.common.config import Config
    import requests
    model = a.model or Config.GROQ_MODEL

    # ── verdad: se LEE, no se recalcula ────────────────────────────────────
    truth = []
    with open(a.truth, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            mkt = float(r['mkt_pips'])
            if abs(mkt) <= DEADBAND:
                continue                      # ventana no decisiva (igual que julio)
            truth.append({'id': int(r['alert_id']), 'dir70': r['dir_70b'],
                          'subio': mkt > 0, 'month': r['month'], 'mkt': mkt})
    print(f'verdad cargada: {len(truth)} alertas decisivas (|move| > {DEADBAND}p)')

    # ── titulo + resumen de cada alerta ───────────────────────────────────
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    ids = [t['id'] for t in truth]
    meta = {}
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        q = ("SELECT a.id, n.title, n.summary FROM alerts a LEFT JOIN news n "
             "ON a.news_id=n.id WHERE a.id IN (%s)" % ','.join('?' * len(chunk)))
        for r in conn.execute(q, chunk):
            meta[r['id']] = (r['title'] or '', r['summary'] or '')
    conn.close()

    truth = [t for t in truth if meta.get(t['id'], ('', ''))[0]]
    if a.limit:
        truth = truth[-a.limit:]            # los MAS RECIENTES, no cherry-pick
    print(f'con titulo disponible: {len(truth)}  | modelo: {model}')
    print('=' * 78)

    # ── prompt: el REAL de produccion ─────────────────────────────────────
    import logging
    from src.analyzer.news_analyzer import NewsAnalyzer
    log = logging.getLogger('ab')
    log.addHandler(logging.NullHandler())
    na = NewsAnalyzer.__new__(NewsAnalyzer)
    na.logger = log
    key = Config.GROQ_API_KEYS[0]

    out_path = a.out or os.path.join(os.path.dirname(a.truth), 'news_ab_new.csv')
    fout = open(out_path, 'w', newline='', encoding='utf-8')
    w = csv.writer(fout)
    w.writerow(['alert_id', 'month', 'dir_70b', 'dir_new', 'subio', 'mkt_pips'])

    got, errs, t_ini = 0, 0, time.time()
    for k, t in enumerate(truth, 1):
        title, summary = meta[t['id']]
        prompt = na._build_analysis_prompt(title, summary)
        dir_new = None
        for attempt in range(4):
            try:
                r = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': f'Bearer {key}',
                             'Content-Type': 'application/json'},
                    json={'model': model,
                          'messages': [
                              {'role': 'system',
                               'content': 'Sos un analista experto de forex EUR/USD. '
                                          'Respondé SOLO con JSON válido.'},
                              {'role': 'user', 'content': prompt}],
                          'temperature': 0.3, 'max_tokens': 3000,
                          'reasoning_effort': getattr(Config, 'GROQ_REASONING_EFFORT', 'low'),
                          'stream': False},
                    timeout=90)
                if r.status_code == 429:
                    time.sleep(8 * (attempt + 1))
                    continue
                if r.status_code != 200:
                    break
                c = r.json()['choices'][0]['message'].get('content') or ''
                c = re.sub(r'<think>.*?</think>', '', c, flags=re.S).strip()
                if not c:
                    break
                parsed = na._parse_ai_result(t['id'], c, 'ab')
                if parsed:
                    dir_new = parsed.get('direction')
                break
            except Exception:
                time.sleep(3)
        if dir_new in ('CALL', 'PUT'):
            got += 1
            w.writerow([t['id'], t['month'], t['dir70'], dir_new,
                        int(t['subio']), t['mkt']])
            fout.flush()
        else:
            errs += 1
        if k % 25 == 0:
            el = time.time() - t_ini
            print(f'  [{k}/{len(truth)}] utiles={got} sin_direccion={errs} '
                  f'| {el/60:.1f} min | ETA {(el/k)*(len(truth)-k)/60:.0f} min')
        time.sleep(THROTTLE_S)
    fout.close()

    # ── resultado ─────────────────────────────────────────────────────────
    rows = list(csv.DictReader(open(out_path, encoding='utf-8')))
    print('=' * 78)
    print(f'  RESULTADO — n={len(rows)} alertas con direccion de los DOS modelos')
    print('=' * 78)
    new_pairs = [(r['dir_new'], r['subio'] == '1') for r in rows]
    old_pairs = [(r['dir_70b'], r['subio'] == '1') for r in rows]

    print('\n[TITULAR] modelo NUEVO:')
    e_new, p_new = discriminate(new_pairs, model)
    print('\n[CONTEXTO] modelo VIEJO sobre las MISMAS filas (prompt de su epoca):')
    e_old, p_old = discriminate(old_pairs, 'llama-3.3-70b-versatile (guardado)')

    subio = sum(1 for r in rows if r['subio'] == '1')
    base = max(subio, len(rows) - subio) / len(rows) * 100 if rows else 0
    hit_new = sum(1 for r in rows if (r['dir_new'] == 'CALL') == (r['subio'] == '1'))
    hit_old = sum(1 for r in rows if (r['dir_70b'] == 'CALL') == (r['subio'] == '1'))
    print(f'\n[DRIFT] mejor-constante del subset = {base:.0f}%')
    print(f'    hit modelo NUEVO = {hit_new/len(rows)*100:.0f}%')
    print(f'    hit modelo VIEJO = {hit_old/len(rows)*100:.0f}%')
    agree = sum(1 for r in rows if r['dir_new'] == r['dir_70b'])
    print(f'\n[ACUERDO] los dos modelos coinciden en {agree/len(rows)*100:.0f}% de las alertas')

    print('\n' + '=' * 78)
    if e_new is None:
        print('  VEREDICTO: sin datos suficientes')
    elif abs(e_new) < 10 or (p_new is not None and p_new >= 0.05):
        print('  VEREDICTO (criterio pre-declarado): NO ES EL MODELO, ES LA TAREA.')
        print('  El modelo nuevo tampoco discrimina => cambiar de LLM no arregla news.')
    else:
        print('  VEREDICTO (criterio pre-declarado): EL MODELO SI IMPORTA.')
        print('  edge >= 10pp con p < 0,05 => la hipotesis "no es el modelo" queda refutada.')
    print('=' * 78)
    print(f'csv: {out_path}')


if __name__ == '__main__':
    main()
