"""
LLM Benchmark Harness — Auditoría de modelos para AIdan.

Compara modelos candidatos (Groq + Ollama) en las tareas reales de AIdan
usando datos históricos de la DB. Output: CSV con métricas por modelo.

Tareas:
  audit       — Re-audita strategies cerradas; correlaciona predicción con resultado real
  post_trade  — Re-analiza trades cerrados; mide latencia + JSON validity
  news        — Re-scorea noticias recientes; mide latencia + dirección vs trade outcome

Uso:
  python tools/llm_benchmark.py --task audit --models groq:llama-3.3-70b-versatile,groq:openai/gpt-oss-120b,ollama:gemma4:latest --n 50
  python tools/llm_benchmark.py --task post_trade --models ollama:gemma4:latest,ollama:qwen2.5:7b --n 30
  python tools/llm_benchmark.py --task news --models groq:llama-3.3-70b-versatile,groq:qwen/qwen3-32b --n 40

Modelos se especifican como provider:name. Provider es 'groq' u 'ollama'.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# Path setup so we can import from src/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
from src.common.config import Config

DB_PATH = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'financial_news.db')
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
OLLAMA_URL = Config.OLLAMA_URL or 'http://localhost:11434'

# ---------------------------------------------------------------------------
# Generic call wrappers — same prompt, different backends
# ---------------------------------------------------------------------------

def call_groq(model, prompt, system='', temperature=0.3, max_tokens=400, json_mode=False):
    # Some models reject response_format json_object — disable for those
    if any(p in model.lower() for p in ('gpt-oss', 'qwen3', 'qwen-3', 'compound')):
        json_mode = False
    keys = [k for k in (Config.GROQ_API_KEYS if hasattr(Config, 'GROQ_API_KEYS') else [Config.GROQ_API_KEY]) if k]
    last_err = None
    for key in keys:
        try:
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': system or 'You are a helpful assistant.'},
                    {'role': 'user', 'content': prompt},
                ],
                'temperature': temperature,
                'max_tokens': max_tokens,
                'stream': False,
            }
            if json_mode:
                payload['response_format'] = {'type': 'json_object'}
            t0 = time.time()
            r = requests.post(
                GROQ_URL,
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                json=payload,
                timeout=45,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                d = r.json()
                text = d['choices'][0]['message']['content']
                tokens = d.get('usage', {}).get('total_tokens', 0)
                return {'ok': True, 'text': text, 'latency_ms': elapsed_ms, 'tokens': tokens, 'error': None}
            elif r.status_code in (429, 401):
                last_err = f'HTTP {r.status_code}'
                continue
            else:
                return {'ok': False, 'text': '', 'latency_ms': elapsed_ms, 'tokens': 0, 'error': f'HTTP {r.status_code}: {r.text[:120]}'}
        except Exception as e:
            last_err = str(e)
            continue
    return {'ok': False, 'text': '', 'latency_ms': 0, 'tokens': 0, 'error': last_err or 'all keys failed'}


def call_ollama(model, prompt, temperature=0.3, num_predict=400, json_format=True):
    try:
        t0 = time.time()
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': temperature,
                'top_p': 0.9,
                'num_predict': num_predict,
            },
        }
        if json_format:
            payload['format'] = 'json'
        r = requests.post(f'{OLLAMA_URL}/api/generate', json=payload, timeout=120)
        elapsed_ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            d = r.json()
            return {
                'ok': True,
                'text': d.get('response', ''),
                'latency_ms': elapsed_ms,
                'tokens': d.get('eval_count', 0),
                'error': None,
            }
        return {'ok': False, 'text': '', 'latency_ms': elapsed_ms, 'tokens': 0, 'error': f'HTTP {r.status_code}'}
    except Exception as e:
        return {'ok': False, 'text': '', 'latency_ms': 0, 'tokens': 0, 'error': str(e)}


def call_model(spec, prompt, **kw):
    """spec is 'provider:model'. Returns dict with ok/text/latency_ms/tokens/error."""
    if ':' not in spec:
        raise ValueError(f"Bad model spec: {spec}. Use 'groq:name' or 'ollama:name'.")
    provider, name = spec.split(':', 1)
    if provider == 'groq':
        kw.pop('num_predict', None)
        kw.pop('json_format', None)
        return call_groq(name, prompt, **kw)
    if provider == 'ollama':
        # ollama doesn't accept system prompts the same way; merge
        if 'system' in kw:
            sys_msg = kw.pop('system')
            prompt = f"{sys_msg}\n\n{prompt}" if sys_msg else prompt
        # remap params
        kw.pop('max_tokens', None)
        kw.pop('json_mode', None)
        return call_ollama(name, prompt, **kw)
    raise ValueError(f'Unknown provider: {provider}')


# ---------------------------------------------------------------------------
# JSON extraction (robust to chain-of-thought prefixes from R1-style models)
# ---------------------------------------------------------------------------
def extract_json(text):
    if not text:
        return None
    # Strip reasoning model <think>...</think> blocks
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<think>.*$', '', text, flags=re.DOTALL)  # unclosed think
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    s = text.find('{')
    e = text.rfind('}') + 1
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e])
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Task: AUDIT — ground truth from trade outcome
# ---------------------------------------------------------------------------
AUDIT_PROMPT = """Eres un auditor de trading para EUR/USD M5.
Analiza esta senal y decide si es buena operacion.

Contexto:
- Direccion: {direction}
- Precio entrada: {entry_price}
- Tendencia M5: {trend} ({trend_strength})
- HTF bias: {htf_bias}
- RSI: {rsi}
- Volatilidad: {volatility}
- Setup: {trigger_type}
- Session: {session}
- Confianza algoritmica: {confidence}%
- SL: {sl_pips}p, TP: {tp_pips}p

Responde SOLO en JSON:
{{"agree": true, "confidence_adjustment": 0, "risk_flag": "none", "reasoning": "1 linea"}}

Reglas:
- agree: true si la operacion tiene sentido, false si no
- confidence_adjustment: entre -20 y +15
- risk_flag: "none" | "high_risk" | "counter_trend" | "overextended"
"""


def load_audit_samples(n):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, direction, entry_price, market_trend, trend_strength, htf_bias,
               rsi_at_entry, volatility, trigger_type, session, confidence,
               sl_pips, tp_pips, result, mt5_pnl
        FROM trade_archive
        WHERE result IN ('win','loss')
          AND htf_bias IS NOT NULL AND htf_bias != ''
        ORDER BY id DESC LIMIT ?
    """, (n,))
    rows = []
    for r in c.fetchall():
        rows.append({
            'id': r[0], 'direction': r[1], 'entry_price': r[2],
            'trend': r[3] or 'unknown', 'trend_strength': r[4] or 'N/A',
            'htf_bias': r[5], 'rsi': round(r[6] or 50, 1),
            'volatility': r[7] or 'normal',
            'trigger_type': r[8] or 'unknown', 'session': r[9] or 'unknown',
            'confidence': round(r[10] or 50, 1),
            'sl_pips': round(r[11] or 0, 1), 'tp_pips': round(r[12] or 0, 1),
            'result': r[13], 'mt5_pnl': r[14] or 0,
        })
    conn.close()
    return rows


def task_audit(models, n):
    samples = load_audit_samples(n)
    print(f"[audit] {len(samples)} muestras")
    results = {m: {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, 'errors': 0,
                   'lat_ms': [], 'tokens': [], 'json_ok': 0, 'pnl_agree': 0, 'pnl_disagree': 0}
               for m in models}

    for s in samples:
        prompt = AUDIT_PROMPT.format(**s)
        outcome_win = (s['result'] == 'win')
        for m in models:
            # Reasoning models need extra tokens for <think> blocks
            mt = 2000 if any(p in m.lower() for p in ('qwen3', 'qwen-3', 'gpt-oss')) else 200
            np = 2000 if any(p in m.lower() for p in ('deepseek-r1', 'qwen3')) else 200
            res = call_model(m, prompt, temperature=0.2, max_tokens=mt, num_predict=np,
                             system='Sos un auditor de trading. Respondé solo JSON válido.', json_mode=True)
            if not res['ok']:
                results[m]['errors'] += 1
                print(f"  [{m}] err on #{s['id']}: {res['error']}")
                continue
            results[m]['lat_ms'].append(res['latency_ms'])
            results[m]['tokens'].append(res['tokens'])
            parsed = extract_json(res['text'])
            if parsed is None:
                results[m]['errors'] += 1
                continue
            results[m]['json_ok'] += 1
            agree = bool(parsed.get('agree', True))
            # Confusion matrix: agree=True (model says good) vs win=True (actual good)
            if agree and outcome_win:        results[m]['tp'] += 1
            elif agree and not outcome_win:  results[m]['fp'] += 1
            elif not agree and not outcome_win: results[m]['tn'] += 1
            else:                             results[m]['fn'] += 1
            # PnL impact: avg pnl when model agrees vs disagrees
            if agree: results[m]['pnl_agree'] += s['mt5_pnl']
            else:     results[m]['pnl_disagree'] += s['mt5_pnl']
            print(f"  [{m}] #{s['id']} {s['direction']} {s['result']:5s} pnl=${s['mt5_pnl']:+.2f} -> agree={agree} flag={parsed.get('risk_flag','?')}")
    return results


# ---------------------------------------------------------------------------
# Task: POST_TRADE — measure JSON validity, latency, and lesson quality (manual review later)
# ---------------------------------------------------------------------------
POST_TRADE_PROMPT = """Analiza este trade EUR/USD M5 cerrado y genera insights.

- Resultado: {result} ({pips}p, ${mt5_pnl})
- Direccion: {direction}, Trigger: {trigger_type}
- Entry: {entry_price}, Exit: {exit_price}, SL: {stop_loss}, TP: {take_profit}
- SL: {sl_pips}p, TP: {tp_pips}p
- Session: {session}, RSI: {rsi}, Trend M5: {trend}, HTF: {htf_bias}
- Volatilidad: {volatility}, Confianza original: {confidence}%

Responde SOLO JSON:
{{"entry_quality": "good", "exit_quality": "good", "timing_assessment": "acceptable", "key_lesson": "1 linea accionable", "confidence_was": "accurate"}}

Reglas:
- entry_quality, exit_quality: "good"|"fair"|"poor"
- timing_assessment: "optimal"|"acceptable"|"poor"
- confidence_was: "overestimated"|"accurate"|"underestimated"
- key_lesson: 1 oracion accionable
"""


def load_post_trade_samples(n):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, direction, entry_price, exit_price, stop_loss, take_profit,
               sl_pips, tp_pips, pips, result, mt5_pnl, session, rsi_at_entry,
               market_trend, htf_bias, volatility, trigger_type, confidence
        FROM trade_archive
        WHERE result IN ('win','loss') AND htf_bias IS NOT NULL AND htf_bias != ''
        ORDER BY id DESC LIMIT ?
    """, (n,))
    rows = []
    for r in c.fetchall():
        rows.append({
            'id': r[0], 'direction': r[1], 'entry_price': r[2], 'exit_price': r[3],
            'stop_loss': r[4], 'take_profit': r[5],
            'sl_pips': round(r[6] or 0, 1), 'tp_pips': round(r[7] or 0, 1),
            'pips': round(r[8] or 0, 1), 'result': r[9], 'mt5_pnl': r[10] or 0,
            'session': r[11] or 'unknown', 'rsi': round(r[12] or 50, 1),
            'trend': r[13] or 'unknown', 'htf_bias': r[14] or 'neutral',
            'volatility': r[15] or 'normal', 'trigger_type': r[16] or 'unknown',
            'confidence': round(r[17] or 50, 1),
        })
    conn.close()
    return rows


def task_post_trade(models, n):
    samples = load_post_trade_samples(n)
    print(f"[post_trade] {len(samples)} muestras")
    results = {m: {'json_ok': 0, 'errors': 0, 'lat_ms': [], 'tokens': [],
                   'qual_distribution': {}, 'lessons': []} for m in models}
    for s in samples:
        prompt = POST_TRADE_PROMPT.format(**s)
        for m in models:
            res = call_model(m, prompt, temperature=0.3, max_tokens=300, num_predict=300, json_mode=True)
            if not res['ok']:
                results[m]['errors'] += 1
                continue
            results[m]['lat_ms'].append(res['latency_ms'])
            results[m]['tokens'].append(res['tokens'])
            parsed = extract_json(res['text'])
            if parsed is None:
                results[m]['errors'] += 1
                continue
            results[m]['json_ok'] += 1
            eq = parsed.get('entry_quality', '?')
            results[m]['qual_distribution'][eq] = results[m]['qual_distribution'].get(eq, 0) + 1
            lesson = str(parsed.get('key_lesson', ''))[:120]
            results[m]['lessons'].append((s['id'], s['result'], lesson))
            print(f"  [{m}] #{s['id']} {s['result']:5s} -> eq={eq} | {lesson[:80]}")
    return results


# ---------------------------------------------------------------------------
# Task: NEWS — measure JSON validity + latency + agreement-with-trade-outcome
# ---------------------------------------------------------------------------
NEWS_PROMPT = """Sos un analista de forex EUR/USD. Analiza esta noticia y devolve JSON con scoring.

Titulo: {title}
Resumen: {summary}

Responde SOLO JSON:
{{"impact_score": 60, "level": "MEDIA", "should_operate": true, "direction": "CALL", "confidence": 65}}

Reglas:
- impact_score: 0-100 (relevancia para EUR/USD)
- level: "ALTA"(>=70) | "MEDIA"(40-69) | "BAJA"(<40)
- direction: "CALL" (EUR sube) | "PUT" (EUR baja) | "NEUTRAL"
- should_operate: true si direction != NEUTRAL y confidence >= 50
- confidence: 0-100 en la prediccion
"""


def load_news_samples(n):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Schema may vary; query columns defensively
    c.execute("PRAGMA table_info(news)")
    cols = [r[1] for r in c.fetchall()]
    title_col = 'title' if 'title' in cols else 'titulo'
    summary_col = 'summary' if 'summary' in cols else 'descripcion' if 'descripcion' in cols else None
    sel = f"id, {title_col}" + (f", {summary_col}" if summary_col else "")
    c.execute(f"SELECT {sel} FROM news ORDER BY id DESC LIMIT ?", (n,))
    rows = []
    for r in c.fetchall():
        rows.append({
            'id': r[0],
            'title': r[1] or '',
            'summary': (r[2] if summary_col and len(r) > 2 else '') or '',
        })
    conn.close()
    return rows


def task_news(models, n):
    samples = load_news_samples(n)
    print(f"[news] {len(samples)} muestras")
    results = {m: {'json_ok': 0, 'errors': 0, 'lat_ms': [], 'tokens': [],
                   'should_operate_count': 0, 'directions': {}} for m in models}
    for s in samples:
        prompt = NEWS_PROMPT.format(**s)
        for m in models:
            res = call_model(m, prompt, temperature=0.3, max_tokens=300, num_predict=300,
                             system='Respondé solo JSON válido.', json_mode=True)
            if not res['ok']:
                results[m]['errors'] += 1
                continue
            results[m]['lat_ms'].append(res['latency_ms'])
            results[m]['tokens'].append(res['tokens'])
            parsed = extract_json(res['text'])
            if parsed is None:
                results[m]['errors'] += 1
                continue
            results[m]['json_ok'] += 1
            if parsed.get('should_operate'):
                results[m]['should_operate_count'] += 1
            d = parsed.get('direction', '?')
            results[m]['directions'][d] = results[m]['directions'].get(d, 0) + 1
            print(f"  [{m}] #{s['id']} -> {parsed.get('level','?')} {d} c={parsed.get('confidence','?')}")
    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def avg(xs):
    return sum(xs) / len(xs) if xs else 0


def summarize_audit(results, n_samples):
    print("\n" + "=" * 80)
    print("AUDIT — Confusion matrix (agree-with-signal vs actual win)")
    print("=" * 80)
    rows = []
    for m, r in results.items():
        total = r['tp'] + r['fp'] + r['tn'] + r['fn']
        precision = r['tp'] / (r['tp'] + r['fp']) if (r['tp'] + r['fp']) else 0
        recall = r['tp'] / (r['tp'] + r['fn']) if (r['tp'] + r['fn']) else 0
        accuracy = (r['tp'] + r['tn']) / total if total else 0
        # Useful metric: when model says "good" (agree), what's the actual WR?
        wr_when_agree = r['tp'] / (r['tp'] + r['fp']) if (r['tp'] + r['fp']) else 0
        wr_when_disagree = r['fn'] / (r['fn'] + r['tn']) if (r['fn'] + r['tn']) else 0
        rows.append({
            'model': m, 'samples': total, 'json_ok': r['json_ok'],
            'errors': r['errors'], 'avg_lat_ms': int(avg(r['lat_ms'])),
            'avg_tokens': int(avg(r['tokens'])),
            'tp': r['tp'], 'fp': r['fp'], 'tn': r['tn'], 'fn': r['fn'],
            'accuracy_pct': f"{accuracy*100:.0f}",
            'precision_pct': f"{precision*100:.0f}",
            'wr_when_agree_pct': f"{wr_when_agree*100:.0f}",
            'wr_when_disagree_pct': f"{wr_when_disagree*100:.0f}",
            'pnl_when_agree': f"{r['pnl_agree']:.2f}",
            'pnl_when_disagree': f"{r['pnl_disagree']:.2f}",
        })
        print(f"\n{m}:")
        print(f"  samples={total}  json_ok={r['json_ok']}  errors={r['errors']}  avg_lat={int(avg(r['lat_ms']))}ms")
        print(f"  TP={r['tp']} FP={r['fp']} TN={r['tn']} FN={r['fn']}")
        print(f"  accuracy={accuracy*100:.0f}%  WR-when-AGREE={wr_when_agree*100:.0f}%  WR-when-DISAGREE={wr_when_disagree*100:.0f}%")
        print(f"  PnL agree=${r['pnl_agree']:.2f}  disagree=${r['pnl_disagree']:.2f}")
    return rows


def summarize_post_trade(results, n_samples):
    print("\n" + "=" * 80)
    print("POST_TRADE — JSON validity + latency + lesson samples")
    print("=" * 80)
    rows = []
    for m, r in results.items():
        rows.append({
            'model': m, 'json_ok': r['json_ok'], 'errors': r['errors'],
            'avg_lat_ms': int(avg(r['lat_ms'])),
            'avg_tokens': int(avg(r['tokens'])),
            'qual_distribution': json.dumps(r['qual_distribution']),
        })
        print(f"\n{m}: json_ok={r['json_ok']}/{n_samples} errors={r['errors']} avg_lat={int(avg(r['lat_ms']))}ms")
        print(f"  entry_quality dist: {r['qual_distribution']}")
        print(f"  Sample lessons (first 3):")
        for tid, res, lesson in r['lessons'][:3]:
            print(f"    #{tid} {res}: {lesson}")
    return rows


def summarize_news(results, n_samples):
    print("\n" + "=" * 80)
    print("NEWS — JSON validity + latency + direction distribution")
    print("=" * 80)
    rows = []
    for m, r in results.items():
        rows.append({
            'model': m, 'json_ok': r['json_ok'], 'errors': r['errors'],
            'avg_lat_ms': int(avg(r['lat_ms'])),
            'avg_tokens': int(avg(r['tokens'])),
            'should_operate_count': r['should_operate_count'],
            'directions': json.dumps(r['directions']),
        })
        print(f"\n{m}: json_ok={r['json_ok']}/{n_samples} errors={r['errors']} avg_lat={int(avg(r['lat_ms']))}ms")
        print(f"  should_operate={r['should_operate_count']}/{n_samples}  dirs={r['directions']}")
    return rows


def write_csv(task, rows):
    if not rows:
        return
    out = ROOT / f"bench_{task}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"\nCSV -> {out}")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True, choices=['audit', 'post_trade', 'news'])
    ap.add_argument('--models', required=True, help='comma-separated provider:name list')
    ap.add_argument('--n', type=int, default=30)
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(',') if m.strip()]
    print(f"DB: {DB_PATH}")
    print(f"Task: {args.task}  N={args.n}  Models: {models}\n")

    if args.task == 'audit':
        results = task_audit(models, args.n)
        rows = summarize_audit(results, args.n)
    elif args.task == 'post_trade':
        results = task_post_trade(models, args.n)
        rows = summarize_post_trade(results, args.n)
    else:
        results = task_news(models, args.n)
        rows = summarize_news(results, args.n)

    write_csv(args.task, rows)


if __name__ == '__main__':
    main()
