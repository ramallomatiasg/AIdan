"""
nightly_analyst.py — LLM-driven analyst nocturno (19:00 AR via Task Scheduler).

Workflow:
1. Detecta proceso AIdan.exe corriendo. Si si: espera hasta 30min para que
   se cierre (el user normalmente lo cierra ~19:00 AR). Si tras 30min sigue,
   ejecuta con modelo cloud only (no usa Ollama local para evitar VRAM contention).
2. Detecta modelo LLM disponible segun jerarquia:
   1. Claude Code CLI (Opus 4.7 1M) — best
   2. Groq llama-3.3-70b-versatile — cloud free fallback
   3. Ollama deepseek-r1:14b (solo si VRAM libre)
   4. Ollama deepseek-r1:7b
   5. Ollama qwen2.5:7b
3. Genera input JSON con stats últimas 24h, 7d, 30d.
4. Invoca modelo con prompt template apropiado.
5. Parsea output JSON → escribe pending_changes via create_pending_change().
6. Telegram alert breve con conclusion + cambios propuestos.

Uso:
    python tools/nightly_analyst.py                  # auto-detect modelo, fecha actual
    python tools/nightly_analyst.py --force          # skip espera de AIdan close
    python tools/nightly_analyst.py --model groq     # force modelo especifico
    python tools/nightly_analyst.py --dry-run        # genera input pero NO invoca LLM ni escribe DB
"""
import argparse
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

LOG_FILE = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'nightly_analyst.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

TZ_AR = timezone(timedelta(hours=-3))


# ─── Model detection ──────────────────────────────────────────────────────

def _claude_cli_available():
    """Verifica si Claude Code CLI esta disponible (Opus 4.7)."""
    claude_exe = shutil.which('claude')
    if not claude_exe:
        return False
    try:
        # Try simple version check
        r = subprocess.run([claude_exe, '--version'], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _groq_available():
    """Verifica si Groq API responde."""
    try:
        from src.common.config import Config
        import requests
        if not Config.GROQ_API_KEY:
            return False
        # Quick ping
        r = requests.get('https://api.groq.com/openai/v1/models',
                        headers={'Authorization': f'Bearer {Config.GROQ_API_KEY}'},
                        timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_available_with_model(model_name):
    """Verifica si Ollama corriendo + modelo `model_name` instalado."""
    try:
        from src.common.config import Config
        import requests
        r = requests.get(f'{Config.OLLAMA_URL}/api/tags', timeout=5)
        if r.status_code != 200:
            return False
        installed = [m.get('name', '') for m in r.json().get('models', [])]
        return any(model_name in m for m in installed)
    except Exception:
        return False


def _vram_free_gb():
    """Get VRAM libre en GB via nvidia-smi. Returns 0 si no disponible."""
    try:
        r = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,nounits,noheader'],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            mb = int(r.stdout.strip().split('\n')[0])
            return mb / 1024
    except Exception:
        pass
    return 0


def _aidan_running():
    """Returns True si AIdan.exe esta corriendo."""
    try:
        r = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq AIdan.exe', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=5
        )
        return 'AIdan.exe' in r.stdout
    except Exception:
        return False


def detect_model(force_model=None):
    """Detect best available model. Returns tuple (model_id, kind).
    kind in {'claude_cli', 'groq', 'ollama'}.
    """
    if force_model:
        if force_model == 'opus' and _claude_cli_available():
            return 'opus', 'claude_cli'
        if force_model == 'groq' and _groq_available():
            return 'llama-3.3-70b-versatile', 'groq'
        if force_model.startswith('ollama:'):
            mname = force_model.split(':', 1)[1]
            if _ollama_available_with_model(mname):
                return mname, 'ollama'
        # Force fallback if requested model unavailable
        logger.warning(f"Forced model '{force_model}' unavailable, falling back to auto")

    # Auto-detection: priority order
    if _claude_cli_available():
        return 'opus', 'claude_cli'
    if _groq_available():
        return 'llama-3.3-70b-versatile', 'groq'

    aidan_running = _aidan_running()
    vram_gb = _vram_free_gb()

    # deepseek-r1:14b necesita ~9GB. Solo si AIdan no corre o VRAM libre >12GB.
    if (not aidan_running or vram_gb > 12) and _ollama_available_with_model('deepseek-r1:14b'):
        return 'deepseek-r1:14b', 'ollama'

    # deepseek-r1:7b necesita ~5GB. Compatible con AIdan running si VRAM libre >7GB.
    if vram_gb > 7 and _ollama_available_with_model('deepseek-r1:7b'):
        return 'deepseek-r1:7b', 'ollama'

    # Last resort: qwen2.5:7b
    if _ollama_available_with_model('qwen2.5:7b'):
        return 'qwen2.5:7b', 'ollama'

    return None, None


# ─── Stats generation ──────────────────────────────────────────────────────

def generate_stats_input():
    """Genera stats estructurado para el LLM analyst.
    Returns dict con stats 24h/7d/30d por buckets de conf/trigger/hora/session.
    """
    from src.common.db import DB_PATH, get_baseline_stats
    # Get baseline FIRST (opens/closes own conn) to avoid conflict
    baseline = get_baseline_stats(lookback_trades=50)

    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    def _query_trades(since_days):
        """Get trades from auto_strategies (last 1d typically) + trade_archive (historical).
        Returns list of dicts.
        """
        cutoff = (datetime.now(TZ_AR) - timedelta(days=since_days)).strftime('%Y-%m-%d %H:%M:%S')
        trades = []
        # auto_strategies (recent, not archived)
        cur.execute("""
            SELECT id, direction, status, mt5_pnl, confidence, trigger_type,
                   created_at,
                   CAST(strftime('%H', created_at) AS INTEGER) AS hour_utc
            FROM auto_strategies
            WHERE created_at >= ?
            AND status IN ('auto_win', 'auto_loss')
            AND mt5_pnl IS NOT NULL
        """, (cutoff,))
        for r in cur.fetchall():
            trades.append(dict(r))
        # trade_archive (all)
        cur.execute("""
            SELECT id, direction, result AS status, mt5_pnl, confidence, trigger_type,
                   session, hour_utc, day_of_week, htf_bias, setup_type, avg_range_pips,
                   created_at
            FROM trade_archive
            WHERE created_at >= ? AND result IN ('win', 'loss') AND mt5_pnl IS NOT NULL
        """, (cutoff,))
        for r in cur.fetchall():
            trades.append(dict(r))
        return trades

    def _agg(trades, by_key):
        """Aggregate trades by key. Returns dict {key: {n, wins, pnl}}."""
        agg = {}
        for t in trades:
            k = t.get(by_key)
            if k is None or k == '':
                k = '_unknown'
            if k not in agg:
                agg[k] = {'n': 0, 'wins': 0, 'pnl': 0.0, 'gw': 0.0, 'gl': 0.0}
            agg[k]['n'] += 1
            pnl = t.get('mt5_pnl') or 0
            agg[k]['pnl'] += pnl
            if (t.get('status') == 'win') or (t.get('status') == 'auto_win') or pnl > 0:
                agg[k]['wins'] += 1
                if pnl > 0:
                    agg[k]['gw'] += pnl
            else:
                if pnl < 0:
                    agg[k]['gl'] += abs(pnl)
        # Compute WR + PF
        for k, d in agg.items():
            d['wr'] = round(d['wins'] / d['n'] * 100, 1) if d['n'] > 0 else 0
            d['pf'] = round(d['gw'] / d['gl'], 2) if d['gl'] > 0 else (999 if d['gw'] > 0 else 0)
            d['pnl'] = round(d['pnl'], 2)
            del d['gw']
            del d['gl']
        return agg

    def _conf_bucket(c):
        if c is None: return '_unknown'
        if c < 30: return '0-29'
        if c < 40: return '30-39'
        if c < 50: return '40-49'
        if c < 60: return '50-59'
        if c < 70: return '60-69'
        if c < 80: return '70-79'
        if c < 90: return '80-89'
        return '90-100'

    def _build_summary(days):
        trades = _query_trades(days)
        # Compute conf bucket on the fly
        for t in trades:
            t['conf_bucket'] = _conf_bucket(t.get('confidence'))
        return {
            'total_trades': len(trades),
            'by_trigger': _agg(trades, 'trigger_type'),
            'by_conf_bucket': _agg(trades, 'conf_bucket'),
            'by_hour_utc': _agg(trades, 'hour_utc'),
            'by_session': _agg(trades, 'session'),
            'by_htf_bias': _agg(trades, 'htf_bias'),
            'by_direction': _agg(trades, 'direction'),
        }

    # Existing active filters + recent applied changes (LLM no debe re-proponer)
    cur.execute("""
        SELECT id, filter_type, params_json FROM active_meta_filters WHERE active = 1
    """)
    active_filters = [{'id': r[0], 'type': r[1], 'params': r[2]} for r in cur.fetchall()]

    cur.execute("""
        SELECT id, change_type, params_json, status, proposed_at
        FROM pending_changes WHERE status IN ('proposed', 'shadow_validating', 'validated', 'applied')
        ORDER BY proposed_at DESC LIMIT 20
    """)
    open_changes = [{'id': r[0], 'type': r[1], 'params': r[2], 'status': r[3], 'proposed_at': r[4]}
                    for r in cur.fetchall()]

    # Build summaries BEFORE closing conn (closures need cur)
    last_24h = _build_summary(1)
    last_7d = _build_summary(7)
    last_30d = _build_summary(30)

    conn.close()

    return {
        'generated_at': datetime.now(TZ_AR).isoformat(),
        'baseline_last_50': baseline,
        'last_24h': last_24h,
        'last_7d': last_7d,
        'last_30d': last_30d,
        'active_meta_filters': active_filters,
        'open_pending_changes': open_changes,
        'guard_rails_note': 'No proponer cambios sobre: mt5_config, risk_percent, max_lot, daily_loss_limit, kill_switch, MT5 credentials, Groq API keys, dynamic_conf formula. Solo change_types soportados.',
        'supported_change_types': [
            'block_setup_type', 'block_conf_bucket', 'block_hour_utc',
            'block_session', 'block_pattern', 'tune_optimizer_param',
            'adjust_setup_confidence', 'adjust_min_confidence_per_track',
        ],
    }


# ─── Model invocation ──────────────────────────────────────────────────────

def _load_prompt(kind, model_name):
    """Load prompt template segun kind del modelo."""
    prompts_dir = os.path.join(ROOT, 'tools', 'prompts')
    paths = []
    if kind == 'claude_cli':
        paths.append(os.path.join(prompts_dir, 'nightly_opus.md'))
    elif kind == 'groq':
        paths.append(os.path.join(prompts_dir, 'nightly_groq.md'))
    elif kind == 'ollama':
        paths.append(os.path.join(prompts_dir, 'nightly_ollama.md'))
    paths.append(os.path.join(prompts_dir, 'nightly_default.md'))
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()
    raise FileNotFoundError(f"No prompt template found for kind={kind} (tried {paths})")


def invoke_claude_cli(stats_json, prompt_template):
    """Invoca Claude CLI con prompt + stats. Returns LLM response as text.
    v3.31.6: fix '--input-file' (no existe en CLI). Usar stdin para prompts largos
    + --bare para evitar inicializacion de hooks/skills/CLAUDE.md auto-load."""
    claude_exe = shutil.which('claude')
    if not claude_exe:
        raise RuntimeError("claude CLI not found")

    # Concat prompt + stats data inline
    full_prompt = prompt_template + "\n\n## DATA INPUT (JSON):\n```json\n" + json.dumps(stats_json, indent=2) + "\n```\n"

    # claude --print recibe prompt via stdin (mas robusto que arg para prompts largos)
    # Sin --bare: usa OAuth/keychain del user logueado (igual que claude interactivo).
    # --dangerously-skip-permissions: evita prompt de aprobacion (no edita archivos,
    # solo response text del LLM).
    cmd = [claude_exe, '--print', '--dangerously-skip-permissions',
           '--model', 'claude-opus-4-5']
    try:
        r = subprocess.run(cmd, input=full_prompt, capture_output=True, text=True,
                          timeout=600, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            err = (r.stderr or r.stdout or '')[:500]
            raise RuntimeError(f"claude CLI exit {r.returncode}: {err}")
        return r.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("claude CLI timeout (10 min)")


def invoke_groq(stats_json, prompt_template, model_name='llama-3.3-70b-versatile'):
    """Invoca Groq API. Returns LLM response as text."""
    from src.common.config import Config
    import requests
    full_prompt = prompt_template + "\n\n## DATA INPUT (JSON):\n```json\n" + json.dumps(stats_json) + "\n```\n"
    r = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {Config.GROQ_API_KEY}', 'Content-Type': 'application/json'},
        json={
            'model': model_name,
            'messages': [
                {'role': 'system', 'content': 'Eres un trading systems analyst. Output JSON estricto.'},
                {'role': 'user', 'content': full_prompt},
            ],
            'temperature': 0.2,
            'max_tokens': 4096,
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Groq API {r.status_code}: {r.text[:300]}")
    return r.json()['choices'][0]['message']['content']


def invoke_ollama(stats_json, prompt_template, model_name):
    """Invoca Ollama local."""
    from src.common.config import Config
    import requests
    full_prompt = prompt_template + "\n\n## DATA INPUT (JSON):\n```json\n" + json.dumps(stats_json) + "\n```\n"
    r = requests.post(
        f'{Config.OLLAMA_URL}/api/generate',
        json={
            'model': model_name,
            'prompt': full_prompt,
            'stream': False,
            'options': {'temperature': 0.2, 'num_ctx': 16384},
        },
        timeout=600,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Ollama {r.status_code}: {r.text[:300]}")
    return r.json().get('response', '')


# ─── Output parsing ──────────────────────────────────────────────────────

def parse_llm_output(raw_output):
    """Parsea output del LLM extrayendo JSON array de cambios propuestos.
    Tolerante a texto extra alrededor del JSON.
    """
    if not raw_output:
        return None, "empty_output"

    # Strategy 1: try direct JSON parse
    try:
        return json.loads(raw_output), None
    except Exception:
        pass

    # Strategy 2: find ```json ... ``` block
    import re
    m = re.search(r'```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```', raw_output, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1)), None
        except Exception as e:
            return None, f"json parse failed in code block: {e}"

    # Strategy 3: extract first JSON array/object
    m = re.search(r'(\[.*?\]|\{.*?\})', raw_output, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1)), None
        except Exception as e:
            return None, f"json parse failed in extracted block: {e}"

    return None, "no JSON found in output"


def persist_changes(changes_list, source):
    """Persist parsed changes to pending_changes table.
    Returns list of created change ids.

    v3.38.0 — Gate de significancia adversarial ANTES de persistir. Cada
    propuesta de block/adjust de subset pasa por verify_change_proposal: si el
    hallazgo no es estadisticamente distinguible del baseline (n<25 o CI cruza
    el WR base), se RECHAZA y no se crea el pending_change (no gasta ciclos de
    shadow validation en ruido). change_types no verificables (tune_optimizer_param,
    block_pattern) pasan sin gate. Ver CLAUDE.md "Metodologia de trabajo con IA".
    """
    from src.common.db import create_pending_change, SUPPORTED_CHANGE_TYPES
    try:
        from src.optimizer.significance import verify_change_proposal, compute_baseline_wr
        _baseline = compute_baseline_wr()
        _sig_available = True
    except Exception as _se:
        logger.warning(f"Significance gate no disponible: {_se} — persistiendo sin verificar")
        _sig_available = False
    created = []
    rejected_noise = []
    for c in (changes_list or []):
        try:
            ct = c.get('change_type', '')
            if ct not in SUPPORTED_CHANGE_TYPES:
                logger.warning(f"Skipping unsupported change_type: {ct}")
                continue
            params = c.get('params', {})
            reasoning = c.get('reasoning', '')

            # v3.38.0 — Gate de significancia
            if _sig_available:
                sig = verify_change_proposal(ct, params, baseline_wr=_baseline)
                if sig is not None and not sig.significant:
                    logger.info(f"RECHAZADO por significancia ({ct} {params}): {sig.summary()}")
                    rejected_noise.append({'change_type': ct, 'params': params,
                                           'reason': sig.reason, 'summary': sig.summary()})
                    continue
                if sig is not None:
                    logger.info(f"Significancia OK ({ct}): {sig.summary()}")
                    # Anota la evidencia en el reasoning para audit trail
                    reasoning = f"{reasoning} [SIG: {sig.summary()}]"

            cid = create_pending_change(
                change_type=ct,
                params_json=params,
                reasoning=reasoning,
                source=source,
            )
            created.append(cid)
            logger.info(f"Created pending_change #{cid} ({ct}): {params}")
        except Exception as e:
            logger.warning(f"Failed to persist change {c}: {e}")
            continue
    if rejected_noise:
        logger.info(f"Significancia: {len(rejected_noise)} propuesta(s) rechazada(s) por ruido de muestra chica")
    # Exponer rechazos para el reporte/Telegram
    persist_changes.last_rejected = rejected_noise
    return created


def _send_telegram_summary(model_used, stats_24h, proposed_changes):
    """Telegram alert breve con conclusion del analyst."""
    try:
        from src.common.telegram_alerts import send_alert, is_configured
        if not is_configured():
            return
        now_str = datetime.now(TZ_AR).strftime('%d %b')
        n24 = stats_24h.get('total_trades', 0)
        # Compute WR 24h
        triggers = stats_24h.get('by_trigger', {})
        total_wins = sum(t.get('wins', 0) for t in triggers.values())
        wr = round(total_wins / n24 * 100, 1) if n24 > 0 else 0
        model_safe = str(model_used).replace('_', '\\_')

        if not proposed_changes:
            msg = (f"Analyst 19:00 — sin cambios — {now_str}\n"
                   f"Modelo: {model_safe} / Trades 24h: {n24} (WR {wr}%)\n"
                   f"No se proponen ajustes.")
            send_alert(msg, level='INFO')
            return

        # First change como ejemplo
        first = proposed_changes[0]
        ct = str(first.get('change_type', '')).replace('_', '\\_')
        params_short = json.dumps(first.get('params', {}))[:50].replace('_', '\\_')

        msg = (f"Analyst 19:00 — {now_str}\n"
               f"Modelo: {model_safe} / Trades 24h: {n24} (WR {wr}%)\n"
               f"Propuesta ({len(proposed_changes)}): {ct} {params_short}\n"
               f"Estado: shadow validation 7-14d")
        send_alert(msg, level='INFO')
    except Exception as e:
        logger.debug(f"telegram summary: {e}")


def _log_cost(model_used, tokens_in=None, tokens_out=None):
    """Log cost a archivo LOCAL solamente (NO Telegram)."""
    try:
        cost_file = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'nightly_costs.log')
        with open(cost_file, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now(TZ_AR).isoformat()} | model={model_used} | tokens_in={tokens_in} | tokens_out={tokens_out}\n")
    except Exception:
        pass


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Skip espera de AIdan close')
    parser.add_argument('--model', default=None, help='Force specific model: opus / groq / ollama:MODEL_NAME')
    parser.add_argument('--dry-run', action='store_true', help='Genera stats input pero NO invoca LLM ni escribe DB')
    parser.add_argument('--max-changes', type=int, default=3, help='Max cambios a proponer (default 3)')
    args = parser.parse_args()

    logger.info(f"=== Nightly analyst started ({datetime.now(TZ_AR).isoformat()}) ===")

    # 1. Si AIdan corriendo y no --force, esperar hasta 30 min
    if not args.force and _aidan_running():
        logger.info("AIdan running, waiting up to 30 min for user to close it...")
        waited = 0
        while waited < 1800 and _aidan_running():
            time.sleep(30)
            waited += 30
        if _aidan_running():
            logger.warning("AIdan still running after 30 min, proceeding with cloud-only models")

    # 2. Detect model
    model_id, kind = detect_model(force_model=args.model)
    if not model_id:
        logger.error("No LLM available (cloud or local). Aborting.")
        return 1
    logger.info(f"Selected model: {model_id} ({kind})")

    # 3. Generate stats input
    try:
        stats = generate_stats_input()
    except Exception as e:
        logger.error(f"Failed to generate stats input: {e}")
        return 1

    # Save input snapshot (for debugging / replay)
    snapshot_path = os.path.join(
        os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state',
        f"nightly_input_{datetime.now(TZ_AR).strftime('%Y%m%d_%H%M')}.json"
    )
    try:
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, default=str)
        logger.info(f"Stats snapshot saved: {snapshot_path}")
    except Exception:
        pass

    if args.dry_run:
        logger.info("--dry-run: skipping LLM invocation and DB writes")
        print(json.dumps(stats, indent=2, default=str))
        return 0

    # 4. Invoke con FALLBACK DE RUNTIME (v3.40.26).
    # Antes: si el modelo elegido fallaba EN LA INVOCACION (ej. claude CLI 401 de auth),
    # hacia return 1 y moria — el fallback solo existia en la SELECCION (binario presente).
    # Ahora: si el elegido falla, cae a Groq -> Ollama (Groq tiene keys hardcodeadas).
    def _invoke_kind(_kind, _mid):
        _pr = _load_prompt(_kind, _mid)
        if _kind == 'claude_cli':
            return invoke_claude_cli(stats, _pr)
        if _kind == 'groq':
            return invoke_groq(stats, _pr, model_name=_mid)
        if _kind == 'ollama':
            return invoke_ollama(stats, _pr, model_name=_mid)
        raise RuntimeError(f"Unknown model kind: {_kind}")

    _chain = [(kind, model_id)]
    if kind != 'groq' and _groq_available():
        _chain.append(('groq', 'llama-3.3-70b-versatile'))
    if kind != 'ollama':
        try:
            _chain.append(('ollama', Config.GEMMA_MODEL))
        except Exception:
            pass

    raw = None
    for _k, _m in _chain:
        try:
            raw = _invoke_kind(_k, _m)
            if raw:
                if (_k, _m) != (kind, model_id):
                    logger.info(f"Fallback: {kind}/{model_id} fallo -> usando {_k}/{_m}")
                    kind, model_id = _k, _m  # reflejar el modelo REAL en source/telegram
                break
        except Exception as e:
            logger.error(f"LLM invocation failed ({_k}/{_m}): {e}")
            raw = None
            continue
    if not raw:
        logger.error("Todos los modelos del fallback fallaron (claude/groq/ollama)")
        return 1

    logger.info(f"LLM raw response ({len(raw)} chars): {raw[:200]}...")

    # 5. Parse + persist
    changes, err = parse_llm_output(raw)
    if err:
        logger.error(f"Parse error: {err}. Raw: {raw[:500]}")
        # No proposed changes, still send Telegram con "sin cambios"
        _send_telegram_summary(model_id, stats.get('last_24h', {}), [])
        return 1

    # Normalize: if dict with key 'changes' or 'proposals', extract list
    if isinstance(changes, dict):
        for k in ('changes', 'proposals', 'proposed', 'pending_changes'):
            if k in changes and isinstance(changes[k], list):
                changes = changes[k]
                break
        if isinstance(changes, dict):
            changes = []  # treat single object as no list

    # Limit to max
    if isinstance(changes, list):
        changes = changes[:args.max_changes]
    else:
        changes = []

    source = f"nightly_{kind}_{model_id.replace(':', '_').replace('-', '_')}"
    created = persist_changes(changes, source)
    rejected = getattr(persist_changes, 'last_rejected', [])

    logger.info(f"Created {len(created)} pending_changes: {created}")
    if rejected:
        logger.info(f"Significancia rechazo {len(rejected)} propuesta(s) por ruido: "
                    + "; ".join(f"{r['change_type']} ({r['summary']})" for r in rejected))
    _log_cost(model_id)
    _send_telegram_summary(model_id, stats.get('last_24h', {}), changes)

    return 0


if __name__ == '__main__':
    sys.exit(main())
