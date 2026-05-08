"""
Benchmark de modelos LLM disponibles para post-trade analysis.

Compara: latencia, calidad JSON output, consistencia.
Test sobre 3 trades reales:
  - Trade aligned WIN (caso bueno)
  - Trade counter-HTF LOSS (caso problemático identificable)
  - Trade expiry LOSS (caso edge)

Output: tabla comparativa + recomendación de modelo default.

Uso:
    python tools/benchmark_llm_models.py
    python tools/benchmark_llm_models.py --models qwen2.5:7b,qwen2.5:14b
"""
import argparse
import json
import os
import sys
import time
import requests

OLLAMA_URL = "http://localhost:11434"

# Test cases reales del archivo de trades
TEST_CASES = [
    {
        'name': 'M15 CALL aligned WIN (+$2.16)',
        'trade': {
            'result': 'win', 'pips': 2.5, 'direction': 'CALL', 'trigger_type': 'm15_structure',
            'entry_price': 1.17709, 'exit_price': 1.17734, 'stop_loss': 1.17559, 'take_profit': 1.17895,
            'sl_pips': 15.0, 'tp_pips': 18.6, 'session': 'ny', 'rsi': 60.0,
            'trend': 'bullish', 'trend_strength': 'moderate', 'htf_bias': 'bullish',
            'volatility': 'normal', 'news_title': '[M15-STRUCT] Continuacion alcista',
            'confidence': 80.0, 'duration_min': 35.0, 'mt5_pnl': 2.16,
        }
    },
    {
        'name': 'NEWS CALL counter-HTF LOSS (-$2.60)',
        'trade': {
            'result': 'loss', 'pips': -1.8, 'direction': 'CALL', 'trigger_type': 'news',
            'entry_price': 1.17018, 'exit_price': 1.17000, 'stop_loss': 1.16979, 'take_profit': 1.17084,
            'sl_pips': 3.9, 'tp_pips': 6.6, 'session': 'ny', 'rsi': 46.1,
            'trend': 'bearish', 'trend_strength': 'moderate', 'htf_bias': 'bearish',
            'volatility': 'low', 'news_title': "ECB Doesn't See Enough Yet to Warrant Rate Hike",
            'confidence': 60.5, 'duration_min': 15.0, 'mt5_pnl': -2.6,
        }
    },
    {
        'name': 'PUT structure expiry LOSS (-$0.80)',
        'trade': {
            'result': 'loss', 'pips': -0.0, 'direction': 'PUT', 'trigger_type': 'structure',
            'entry_price': 1.17573, 'exit_price': 1.17574, 'stop_loss': 1.17628, 'take_profit': 1.17512,
            'sl_pips': 5.4, 'tp_pips': 6.2, 'session': 'ny', 'rsi': 34.9,
            'trend': 'bearish', 'trend_strength': 'moderate', 'htf_bias': 'bullish',
            'volatility': 'low', 'news_title': '[ESTRUCTURA] Continuacion bajista',
            'confidence': 78.0, 'duration_min': 15.0, 'mt5_pnl': -0.8,
        }
    },
]

PROMPT_TEMPLATE = """Trade EUR/USD post-mortem analysis. JSON only.
Result: {result} ({pips}p, ${mt5_pnl})
Direction: {direction} (conf {confidence})
Entry: {entry_price} SL: {stop_loss} ({sl_pips}p) TP: {take_profit} ({tp_pips}p)
Context: trend={trend} {trend_strength}, htf_bias={htf_bias}, RSI {rsi}, vol {volatility}
News: "{news_title}"
Duration: {duration_min}min, session {session}, trigger {trigger_type}

Return JSON: {{
  "entry_quality": "good|fair|poor",
  "key_lesson": "<1 sentence what to learn>",
  "root_cause": "<why it failed or succeeded, 1-2 sentences>",
  "sl_action": "widen|tighten|keep",
  "recommended_sl_pips": <number 0-20>,
  "recommended_tp_pips": <number 0-40>
}}"""


def test_model(model, trade, num_ctx=2048, timeout=180):
    """Test un modelo con un trade. Returns (time, parsed_dict, raw_output)."""
    prompt = PROMPT_TEMPLATE.format(**trade)
    t0 = time.time()
    try:
        r = requests.post(f'{OLLAMA_URL}/api/generate',
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'format': 'json',
                'keep_alive': '5m',
                'options': {
                    'temperature': 0.3,
                    'top_p': 0.9,
                    'num_predict': 400,
                    'num_ctx': num_ctx,
                }
            },
            timeout=timeout)
        elapsed = time.time() - t0
        if r.status_code != 200:
            return elapsed, None, f'HTTP {r.status_code}: {r.text[:200]}'
        text = r.json().get('response', '')
        # Strip <think> tags
        if '<think>' in text:
            after = text.split('</think>')
            if len(after) > 1:
                text = after[-1].strip()
        try:
            parsed = json.loads(text)
            return elapsed, parsed, text
        except json.JSONDecodeError:
            return elapsed, None, f'PARSE FAIL: {text[:300]}'
    except requests.exceptions.Timeout:
        return time.time()-t0, None, f'TIMEOUT >{timeout}s'
    except Exception as e:
        return time.time()-t0, None, f'ERROR: {e}'


def evaluate_quality(parsed, expected_result):
    """Heuristic quality score 0-100 sobre el output parseado."""
    if not parsed:
        return 0
    score = 0
    # Required fields present
    required = ['entry_quality', 'key_lesson', 'root_cause']
    score += sum(15 for f in required if parsed.get(f)) // 1  # 0-45

    # Entry quality consistent with result
    if expected_result == 'win' and parsed.get('entry_quality') in ('good', 'fair'):
        score += 15
    elif expected_result == 'loss' and parsed.get('entry_quality') in ('fair', 'poor'):
        score += 15

    # Lesson length reasonable
    lesson = parsed.get('key_lesson', '')
    if 20 < len(lesson) < 200:
        score += 10

    # Root cause specific (not generic)
    rc = parsed.get('root_cause', '').lower()
    generic_phrases = ['market conditions', 'sentiment', 'unexpected', 'volatility', 'price moved against']
    is_specific = not any(p in rc for p in generic_phrases) or len(rc) > 80
    if is_specific:
        score += 10

    # Numeric SL/TP recommendations
    if isinstance(parsed.get('recommended_sl_pips'), (int, float)):
        score += 10

    return min(score, 100)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--models', default='qwen2.5:7b,qwen2.5:14b,qwen3:4b,deepseek-r1:14b',
                   help='comma-separated model names')
    p.add_argument('--timeout', type=int, default=120)
    args = p.parse_args()

    models = [m.strip() for m in args.models.split(',')]

    # Verify available
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=5).json()
        available = {m['name'] for m in r.get('models', [])}
        models_to_test = [m for m in models if m in available or m + ':latest' in available]
        skipped = [m for m in models if m not in models_to_test]
        if skipped:
            print(f'Skipping (not installed): {skipped}')
        if not models_to_test:
            print('No models available. Install with: ollama pull <model>')
            return
    except Exception as e:
        print(f'Could not query Ollama: {e}')
        return

    print(f'\n=== Benchmark LLM Models ({len(models_to_test)} models, {len(TEST_CASES)} cases) ===\n')

    results = {}
    for model in models_to_test:
        print(f'\n--- Testing {model} ---')
        results[model] = {'cases': [], 'total_time': 0, 'parse_success': 0, 'avg_quality': 0}
        for case in TEST_CASES:
            elapsed, parsed, raw = test_model(model, case['trade'], timeout=args.timeout)
            quality = evaluate_quality(parsed, case['trade']['result'])
            results[model]['cases'].append({
                'case': case['name'],
                'time': elapsed,
                'parsed': bool(parsed),
                'quality': quality,
                'output': parsed,
                'raw': raw if not parsed else None,
            })
            results[model]['total_time'] += elapsed
            if parsed:
                results[model]['parse_success'] += 1
                results[model]['avg_quality'] += quality
            status = f'{elapsed:.1f}s'
            if parsed:
                status += f' Q={quality}/100'
                if parsed.get('key_lesson'):
                    status += f' lesson="{parsed["key_lesson"][:60]}..."'
            else:
                status += f' FAIL: {(raw or "")[:80]}'
            print(f'  [{case["name"][:35]}] {status}')

        if results[model]['parse_success']:
            results[model]['avg_quality'] /= results[model]['parse_success']

    # Summary
    print(f'\n\n=== SUMMARY ===')
    print(f'{"Model":<25}{"Avg Time":>12}{"Parse OK":>12}{"Avg Quality":>15}{"Recommendation":>20}')
    print('-' * 90)
    for model, r in results.items():
        avg_t = r['total_time'] / len(TEST_CASES)
        parse = f"{r['parse_success']}/{len(TEST_CASES)}"
        quality = f"{r['avg_quality']:.0f}/100" if r['parse_success'] else 'N/A'
        # Recommendation
        if r['parse_success'] == 0:
            rec = 'UNUSABLE'
        elif avg_t > 60:
            rec = 'TOO SLOW'
        elif avg_t < 10 and r['avg_quality'] >= 70:
            rec = 'GOOD'
        elif r['avg_quality'] >= 80:
            rec = 'BEST QUALITY'
        elif avg_t < 5:
            rec = 'FAST OK'
        else:
            rec = 'OK'
        print(f'{model:<25}{avg_t:>11.1f}s{parse:>12}{quality:>15}{rec:>20}')


if __name__ == '__main__':
    main()
