import sys
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import requests

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.common.config import Config
from src.common.logging_setup import setup_logging
from src.common.db import (init_db, get_stats, get_recent_alerts, record_signal_result,
                           get_performance_stats, get_active_strategies, record_strategy_result,
                           get_strategy_performance, get_detailed_trade_history,
                           get_setup_win_rates, get_learned_lessons, toggle_strategy_pause,
                           get_post_trade_analyses, get_post_trade_stats,
                           get_planned_strategies, get_strategy_performance_by_track)
from src.analyzer.technical import TechnicalAnalyzer
from src.analyzer.mtf_analyzer import MTFAnalyzer
from src.analyzer.smc import SMCEngine
from src.common.db import today_ar

logger = setup_logging(__name__, Config.LOG_LEVEL)


# Groq API helper (free, Llama 70B)
_groq_status = {"ok": True, "last_error": "", "last_error_time": None}

def _call_groq(messages, temperature=0.75, max_tokens=600, model=None):
    """Call Groq API with automatic key rotation on rate limit.

    model: defaults to GROQ_MODEL_CHAT (faster llama-3.1-8b-instant for chat use cases).
    Pass model=Config.GROQ_MODEL explicitly for analytical tasks needing the 70B.
    """
    keys = Config.GROQ_API_KEYS if hasattr(Config, 'GROQ_API_KEYS') else [Config.GROQ_API_KEY]
    keys = [k for k in keys if k]
    if not keys:
        return None

    chosen_model = model or getattr(Config, 'GROQ_MODEL_CHAT', Config.GROQ_MODEL)

    for i, api_key in enumerate(keys):
        try:
            resp = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                json={
                    'model': chosen_model,
                    'messages': messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'stream': False
                },
                timeout=30
            )
            if resp.status_code == 200:
                content = resp.json()['choices'][0]['message']['content']
                logger.info(f"Groq response OK (key {i+1}/{len(keys)}, {len(content)} chars)")
                _groq_status["ok"] = True
                _groq_status["last_error"] = ""
                return content
            elif resp.status_code == 429 and i < len(keys) - 1:
                logger.warning(f"Groq key {i+1} rate limited, trying key {i+2}...")
                continue
            else:
                error_msg = resp.text[:300]
                _groq_status["last_error"] = f"HTTP {resp.status_code}: {error_msg}"
                _groq_status["last_error_time"] = __import__('datetime').datetime.now().isoformat()
                if resp.status_code == 401:
                    logger.warning(f"Groq key {i+1} invalid, trying next..." if i < len(keys) - 1 else f"All Groq keys failed")
                    if i < len(keys) - 1:
                        continue
                    _groq_status["ok"] = False
                elif resp.status_code == 429:
                    logger.warning(f"Groq rate limit on all keys. Usando Ollama como fallback.")
                else:
                    logger.warning(f"Groq error {resp.status_code}: {error_msg}")
                return None
        except Exception as e:
            _groq_status["last_error"] = str(e)
            _groq_status["last_error_time"] = __import__('datetime').datetime.now().isoformat()
            if i < len(keys) - 1:
                logger.warning(f"Groq key {i+1} failed ({e}), trying next...")
                continue
            logger.warning(f"Groq unavailable: {e}")
            return None
    return None

app = FastAPI(title="Financial News Monitor API", version=Config.VERSION)

@app.get("/version")
def get_version():
    return {"version": Config.VERSION}

# UTC ISO helper — SQLite stores "2026-03-17 13:44:18.439" without timezone
def _utc_iso(ts_str):
    """Convert SQLite timestamp (stored as Buenos Aires UTC-3) to ISO 8601 for JS Date() parsing."""
    if not ts_str:
        return ts_str
    return ts_str.replace(' ', 'T').split('.')[0] + '-03:00'

def _published_iso(ts_str):
    """Convert published_at (already UTC from RSS feeds) to ISO 8601."""
    if not ts_str:
        return ts_str
    return ts_str.replace(' ', 'T').split('.')[0] + 'Z'

# Vision model detection
_vision_model_cache = {'model': None, 'checked': 0}
def _get_vision_model():
    """Detect best available vision model in Ollama."""
    import time
    now = time.time()
    if _vision_model_cache['model'] and (now - _vision_model_cache['checked']) < 300:
        return _vision_model_cache['model']
    try:
        resp = requests.get('http://localhost:11434/api/tags', timeout=5)
        if resp.status_code == 200:
            models = [m['name'] for m in resp.json().get('models', [])]
            # Prefer llama3.2-vision > llava > minicpm-v
            for candidate in ['llama3.2-vision', 'llava:latest', 'llava', 'minicpm-v', 'bakllava']:
                for m in models:
                    if candidate in m:
                        _vision_model_cache['model'] = m
                        _vision_model_cache['checked'] = now
                        logger.info(f"Vision model detected: {m}")
                        return m
    except Exception as e:
        logger.warning(f"Vision model check failed: {e}")
    _vision_model_cache['checked'] = now
    return None

# Technical analyzer singleton
_tech_analyzer = None
def get_tech():
    global _tech_analyzer
    if _tech_analyzer is None:
        _tech_analyzer = TechnicalAnalyzer(logger)
    return _tech_analyzer

# Auto-tuner singleton
_auto_tuner = None
def get_tuner():
    global _auto_tuner
    if _auto_tuner is None:
        from src.optimizer.auto_tuner import AutoTuner
        _auto_tuner = AutoTuner(logger)
    return _auto_tuner

# SMC engine singleton
_smc_engine = None
def get_smc():
    global _smc_engine
    if _smc_engine is None:
        mtf = MTFAnalyzer(logger)
        _smc_engine = SMCEngine(logger, mtf)
    return _smc_engine

# Configurar CORS para permitir peticiones desde PyWebView y navegadores
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Detectar si estamos en ejecutable o desarrollo
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.join(os.path.dirname(__file__), '../..')

# Montar carpeta static para servir archivos estáticos
static_path = os.path.join(base_path, 'static')
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Servir dashboard en la raíz
# v3.27.2: agregar Cache-Control no-cache para forzar reload de HTML siempre
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

@app.get("/")
async def root():
    """Servir dashboard multi-theme con chat"""
    dashboard_path = os.path.join(base_path, 'dashboard_multi_theme.html')
    logger.info(f"Intentando servir: {dashboard_path}")
    logger.info(f"Existe: {os.path.exists(dashboard_path)}")
    if os.path.exists(dashboard_path):
        logger.info("✓ Sirviendo dashboard_multi_theme.html")
        return FileResponse(dashboard_path, media_type="text/html", headers=NO_CACHE_HEADERS)
    dashboard_path = os.path.join(base_path, 'dashboard_retro.html')
    if os.path.exists(dashboard_path):
        logger.info("⚠ Sirviendo dashboard_retro.html (fallback)")
        return FileResponse(dashboard_path, media_type="text/html", headers=NO_CACHE_HEADERS)
    dashboard_path = os.path.join(os.path.dirname(__file__), '../../dashboard.html')
    if os.path.exists(dashboard_path):
        logger.info("⚠ Sirviendo dashboard.html (fallback)")
        return FileResponse(dashboard_path, media_type="text/html", headers=NO_CACHE_HEADERS)
    logger.error("❌ No se encontró ningún dashboard")
    return {"message": "Dashboard not found"}

@app.get("/ai-status")
async def ai_status():
    """Report which AI backend is active"""
    has_groq = bool(Config.GROQ_API_KEY)
    has_ollama = False
    try:
        r = requests.get('http://localhost:11434/api/tags', timeout=3)
        has_ollama = r.status_code == 200
    except Exception:
        pass  # Ollama not running — expected
    groq_healthy = has_groq and _groq_status["ok"]
    primary = "groq" if groq_healthy else ("ollama" if has_ollama else "keywords")
    result = {
        "primary": primary,
        "groq_available": has_groq,
        "groq_healthy": groq_healthy,
        "ollama_available": has_ollama,
        "model": Config.GROQ_MODEL if groq_healthy else "llama3.1:8b"
    }
    if _groq_status["last_error"]:
        result["groq_error"] = _groq_status["last_error"]
        result["groq_error_time"] = _groq_status["last_error_time"]
    # v3.21.0 — GPU monitor status
    try:
        from src.common.gpu_monitor import get_gpu_state
        result["gpu"] = get_gpu_state()
    except Exception as e:
        result["gpu"] = {"available": False, "reason": str(e)}
    return JSONResponse(result)


@app.get("/telegram/test")
async def telegram_test():
    """v3.23.0 — Test conexion Telegram bot. GET para verificar setup."""
    try:
        from src.common.telegram_alerts import test_connection
        return JSONResponse(test_connection())
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/telegram/status")
async def telegram_status():
    """v3.23.0 — Status del modulo telegram (configurado o no)."""
    try:
        from src.common.telegram_alerts import is_configured
        return JSONResponse({"configured": is_configured()})
    except Exception as e:
        return JSONResponse({"configured": False, "error": str(e)})


@app.get("/gpu-status")
async def gpu_status():
    """v3.21.0 — GPU utilization + LLM pause flag for gaming-aware mode."""
    try:
        from src.common.gpu_monitor import get_gpu_state
        return JSONResponse({"status": "success", "data": get_gpu_state(force_refresh=True)})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# Servir página About
@app.get("/about")
async def about():
    """Servir página sobre el desarrollador"""
    about_path = os.path.join(base_path, 'about.html')
    if os.path.exists(about_path):
        return FileResponse(about_path, media_type="text/html")
    return {"message": "About page not found"}


# v3.30.4 — Theme editor: standalone HTML con color pickers + sliders.
# Live preview del dashboard. Inspirado en approach Thariq (Anthropic):
# HTML interactivo como output format en lugar de Markdown estatico.
@app.get("/theme-editor")
async def theme_editor():
    """Editor visual de paleta de colores y tokens CSS del dashboard."""
    # Buscar en tools/ (dev) o base_path (frozen exe)
    candidates = [
        os.path.join(base_path, 'tools', 'dashboard_theme_editor.html'),
        os.path.join(base_path, 'dashboard_theme_editor.html'),
        os.path.join(os.path.dirname(base_path), 'tools', 'dashboard_theme_editor.html'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="text/html", headers=NO_CACHE_HEADERS)
    return {"message": "Theme editor no encontrado", "tried": candidates}


# v3.30.6 — What-if simulator: HTML interactivo sobre trade_archive REAL.
# Sliders/checkboxes para filtros que recomputan WR/PF/PnL al instante sobre
# 165+ trades historicos. Inspirado en Thariq/Anthropic — HTML interactivo
# en lugar de Markdown estatico. Permite responder: "que hubiera pasado si
# hubiera tenido X filtro activo?"
@app.get("/what-if")
async def what_if():
    """Sirve el HTML del what-if simulator."""
    candidates = [
        os.path.join(base_path, 'what_if_simulator.html'),
        os.path.join(base_path, 'tools', 'what_if_simulator.html'),
        os.path.join(os.path.dirname(base_path), 'tools', 'what_if_simulator.html'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="text/html", headers=NO_CACHE_HEADERS)
    return JSONResponse({"message": "What-if simulator no encontrado", "tried": candidates})


@app.get("/trade-archive-data")
async def trade_archive_data():
    """Returns trade_archive data como JSON para consumir client-side
    desde el what-if simulator. Filtra trades con mt5_pnl NULL (no completados)."""
    import sqlite3
    from src.common.db import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, direction, result, pips, sl_pips, tp_pips,
               confidence, impact_score, trigger_type, setup_type, htf_bias,
               rsi_at_entry, avg_range_pips, session, hour_utc, day_of_week,
               mt5_pnl, market_trend, trend_strength, volatility,
               sl_hit, tp_hit, profile_name, archived_at
        FROM trade_archive
        WHERE result IN ('win', 'loss') AND mt5_pnl IS NOT NULL
        ORDER BY archived_at DESC
    """)
    cols = [d[0] for d in cur.description]
    trades = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return JSONResponse({'trades': trades, 'count': len(trades)},
                        headers=NO_CACHE_HEADERS)


# v3.30.7 — /backtest-report removido (reemplazado por /what-if que usa
# data REAL de trade_archive en vez de backtest sintetico).


# v3.31.0 — Meta-optimization endpoints
@app.get("/pending-changes")
async def list_pending_changes(status: str = None, limit: int = 50):
    """Lista pending_changes filtrados por status (proposed/shadow_validating/validated/applied/reverted/rejected)."""
    try:
        from src.common.db import get_pending_changes
        changes = get_pending_changes(status=status, limit=limit)
        return JSONResponse({'count': len(changes), 'changes': changes}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/pending-changes/{change_id}")
async def get_pending_change_detail(change_id: int):
    """Detalle de un pending_change + audit trail + shadow stats."""
    try:
        from src.common.db import (
            get_pending_change as _get,
            get_change_history,
            evaluate_shadow_trades_for_change,
        )
        change = _get(change_id)
        if not change:
            return JSONResponse({'error': 'not found'}, status_code=404)
        history = get_change_history(change_id)
        shadow_stats = evaluate_shadow_trades_for_change(change_id)
        return JSONResponse({
            'change': change,
            'history': history,
            'shadow_stats': shadow_stats,
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.post("/pending-changes/{change_id}/approve")
async def approve_pending_change(change_id: int):
    """Manualmente aprueba un cambio (skip shadow validation). Lo aplica al live.
    Solo para uso del user via dashboard. Use sparingly.
    """
    try:
        from src.optimizer.change_manager import apply_change, ChangeManagerError
        result = apply_change(change_id, force=True)
        return JSONResponse({'ok': result.get('applied', False), **result}, headers=NO_CACHE_HEADERS)
    except ChangeManagerError as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)


@app.post("/pending-changes/{change_id}/revert")
async def revert_pending_change(change_id: int):
    """Manualmente revierte un cambio aplicado."""
    try:
        from src.optimizer.change_manager import revert_change, ChangeManagerError
        result = revert_change(change_id, reason='manual_revert_via_api')
        return JSONResponse({'ok': result.get('reverted', False), **result}, headers=NO_CACHE_HEADERS)
    except ChangeManagerError as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)


@app.post("/pending-changes/{change_id}/reject")
async def reject_pending_change(change_id: int, reason: str = "manual_reject"):
    """Marca un pending_change como rechazado (no se aplicara)."""
    try:
        from src.common.db import update_pending_change_status, get_pending_change
        change = get_pending_change(change_id)
        if not change:
            return JSONResponse({'error': 'not found'}, status_code=404)
        if change.get('status') in ('applied', 'reverted'):
            return JSONResponse({'error': f"cannot reject from status={change.get('status')}"}, status_code=400)
        update_pending_change_status(change_id, 'rejected', rejected_reason=reason)
        return JSONResponse({'ok': True}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)


@app.post("/pending-changes/{change_id}/start-shadow")
async def start_shadow(change_id: int):
    """Promover proposed -> shadow_validating. Inicia el ciclo de validacion."""
    try:
        from src.common.db import update_pending_change_status, get_pending_change
        change = get_pending_change(change_id)
        if not change:
            return JSONResponse({'error': 'not found'}, status_code=404)
        if change.get('status') != 'proposed':
            return JSONResponse({'error': f"can only start shadow from proposed (current={change.get('status')})"}, status_code=400)
        update_pending_change_status(change_id, 'shadow_validating')
        return JSONResponse({'ok': True}, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'ok': False, 'error': str(e)}, status_code=500)


@app.get("/meta-optimization-status")
async def meta_optimization_status():
    """Resumen del estado del meta-optimizer: contadores por status + baseline + active filters."""
    try:
        from src.common.db import (
            get_pending_changes,
            get_active_meta_filters,
            get_baseline_stats,
        )
        statuses = ['proposed', 'shadow_validating', 'validated', 'applied', 'reverted', 'rejected']
        counts = {s: len(get_pending_changes(status=s, limit=500)) for s in statuses}
        active = get_active_meta_filters()
        baseline = get_baseline_stats(lookback_trades=50)
        return JSONResponse({
            'counts_by_status': counts,
            'active_filters_count': len(active),
            'active_filters': active,
            'baseline_last_50': baseline,
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/position-manager/state")
async def position_manager_state():
    """v3.36.0 — Estado del Position Manager: config + posiciones abiertas con su
    ultima decision logueada."""
    try:
        import sqlite3
        from src.common.db import DB_PATH
        from src.common.config import Config
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Posiciones abiertas + ultima decision del manager
        cur.execute("""
            SELECT a.id, a.direction, a.trigger_type, a.mt5_ticket, a.confidence,
                   a.mt5_fill_price, a.created_at, a.expiry_minutes
            FROM auto_strategies a
            WHERE a.mt5_status = 'filled' AND a.mt5_ticket IS NOT NULL
            ORDER BY a.created_at DESC
        """)
        open_pos = []
        for r in cur.fetchall():
            d = dict(r)
            cur2 = conn.execute("""
                SELECT action, reason, progress_pips, hwm_pips, tp_pct,
                       time_in_trade_min, decision_source, created_at
                FROM position_manager_log WHERE strategy_id = ?
                ORDER BY id DESC LIMIT 1
            """, (d['id'],))
            last = cur2.fetchone()
            d['last_decision'] = dict(last) if last else None
            open_pos.append(d)
        conn.close()
        return JSONResponse({
            'mode': getattr(Config, 'POSITION_MANAGER_MODE', 'log'),
            'llm_enabled': getattr(Config, 'POSITION_MANAGER_LLM', False),
            'interval_sec': getattr(Config, 'POSITION_MANAGER_INTERVAL', 15),
            'max_hold_min': {
                'm5': getattr(Config, 'MAX_HOLD_MIN_M5', 90),
                'm15': getattr(Config, 'MAX_HOLD_MIN_M15', 120),
                'h1': getattr(Config, 'MAX_HOLD_MIN_H1', 240),
            },
            'open_positions': open_pos,
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/position-manager/stats")
async def position_manager_stats(limit: int = 200):
    """v3.36.0 — Agregados del log del Position Manager: conteo por accion,
    cuantas ejecutadas, rules vs llm, y feed reciente de decisiones de cierre."""
    try:
        import sqlite3
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM position_manager_log")
        total = cur.fetchone()[0]
        cur.execute("SELECT action, COUNT(*) n FROM position_manager_log GROUP BY action")
        by_action = {r['action']: r['n'] for r in cur.fetchall()}
        cur.execute("SELECT decision_source, COUNT(*) n FROM position_manager_log GROUP BY decision_source")
        by_source = {r['decision_source']: r['n'] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM position_manager_log WHERE executed = 1")
        executed = cur.fetchone()[0]
        # Feed: TODAS las decisiones recientes (HOLD + closes). HOLDs ya estan
        # throttleadas en el thread (cambio de accion o cada 5min), no satura.
        cur.execute("""
            SELECT strategy_id, ticket, mode, action, reason, decision_source,
                   progress_pips, hwm_pips, tp_pct, time_in_trade_min, executed, created_at
            FROM position_manager_log
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        recent = [dict(r) for r in cur.fetchall()]
        # Compat: tambien expone solo-cierres para clientes viejos
        recent_closes = [r for r in recent if r['action'] != 'HOLD']
        conn.close()
        return JSONResponse({
            'total_decisions': total,
            'by_action': by_action,
            'by_source': by_source,
            'executed_closes': executed,
            'recent_decisions': recent,
            'recent_close_decisions': recent_closes,
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/bounce-entry/stats")
async def bounce_entry_stats(limit: int = 50):
    """v3.39.0 — Shadow log del filtro skip-bounce-entry: cuantos trades habria
    saltado y si esos (bounce) terminaron peor que los demas."""
    try:
        import sqlite3
        from src.common.db import DB_PATH
        from src.common.config import Config
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) n, SUM(is_bounce) b, SUM(skipped) sk FROM bounce_entry_log")
        agg = cur.fetchone()
        total, bounces, skipped = agg['n'] or 0, agg['b'] or 0, agg['sk'] or 0
        # cruzar las decisiones bounce con el resultado real del trade (shadow validation)
        cur.execute("""
            SELECT b.is_bounce, a.mt5_pnl
            FROM bounce_entry_log b JOIN auto_strategies a ON a.id = b.strategy_id
            WHERE a.mt5_pnl IS NOT NULL
        """)
        rows = cur.fetchall()
        def wr(grp):
            v = [r['mt5_pnl'] for r in rows if r['is_bounce'] == grp]
            if not v: return {'n': 0, 'wr': None, 'pnl': 0}
            return {'n': len(v), 'wr': round(sum(1 for x in v if x > 0)/len(v)*100, 1), 'pnl': round(sum(v), 2)}
        cur.execute("""
            SELECT strategy_id, direction, trigger_type, entry_candle_open,
                   entry_candle_close, is_bounce, mode, skipped, created_at
            FROM bounce_entry_log ORDER BY id DESC LIMIT ?
        """, (limit,))
        recent = [dict(r) for r in cur.fetchall()]
        conn.close()
        return JSONResponse({
            'mode': getattr(Config, 'SKIP_BOUNCE_ENTRY', 'shadow'),
            'total_decisions': total,
            'bounce_would_skip': bounces,
            'actually_skipped': skipped,
            'outcome_bounce': wr(1),       # los que habria saltado: ¿perdieron?
            'outcome_nonbounce': wr(0),    # los que dejo pasar: ¿ganaron?
            'recent': recent,
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@app.get("/ml-predictor/status")
async def ml_predictor_status():
    """v3.35.0 — Diagnostic: estado del modelo ML de confidence.
    Muestra si los modelos cargaron correctamente y si el flag esta activo.
    """
    try:
        from src.optimizer.confidence_predictor import get_predictor_info
        info = get_predictor_info()
        return JSONResponse(info, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'enabled': False, 'error': str(e)}, headers=NO_CACHE_HEADERS)


@app.get("/ml-predictor/test")
async def ml_predictor_test():
    """v3.35.0 — Test: ejecutar predict_confidence con signal sintetico.
    Util para verificar que el modelo funciona end-to-end.
    """
    try:
        from src.optimizer.confidence_predictor import predict_confidence
        import os
        # Forzar flag para test (no afecta runtime real)
        old_flag = os.environ.get('USE_ML_CONFIDENCE', '')
        os.environ['USE_ML_CONFIDENCE'] = 'true'
        try:
            # Signal de prueba: news bullish en sesión NY con features típicos
            test_signal = {
                'trigger_type': 'news',
                'direction': 'CALL',
                'session': 'ny',
                'htf_bias': 'bullish',
                'market_trend': 'bullish',
                'trend_strength': 'moderate',
                'volatility': 'normal',
                'rsi_at_entry': 55.0,
                'avg_range_pips': 3.5,
                'hour_utc': 14,
                'day_of_week': 2,
                # enriched (will use medians from training if missing)
            }
            result_news = predict_confidence(test_signal)
            test_signal['trigger_type'] = 'm15_structure'
            result_m15 = predict_confidence(test_signal)
            test_signal['trigger_type'] = 'structure'
            result_structure = predict_confidence(test_signal)
        finally:
            if old_flag:
                os.environ['USE_ML_CONFIDENCE'] = old_flag
            else:
                os.environ.pop('USE_ML_CONFIDENCE', None)
        return JSONResponse({
            'test_signal': {'trigger': 'news/m15/structure', 'direction': 'CALL', 'session': 'ny', 'htf': 'bullish'},
            'predictions': {
                'news': result_news,
                'm15_structure': result_m15,
                'structure': result_structure,
            },
            'note': 'news/m15 should return int 0-100, structure should return None (no model)',
        }, headers=NO_CACHE_HEADERS)
    except Exception as e:
        return JSONResponse({'error': str(e)}, headers=NO_CACHE_HEADERS)


@app.get("/meta-optimization")
async def meta_optimization_dashboard():
    """Sirve el HTML del dashboard de meta-optimization."""
    candidates = [
        os.path.join(base_path, 'meta_optimization.html'),
        os.path.join(base_path, 'tools', 'meta_optimization.html'),
        os.path.join(os.path.dirname(base_path), 'tools', 'meta_optimization.html'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="text/html", headers=NO_CACHE_HEADERS)
    return JSONResponse({"message": "Meta-optimization dashboard no encontrado", "tried": candidates})


@app.get("/position-manager")
async def position_manager_dashboard():
    """v3.36.0 — Sirve el HTML del dashboard del Position Manager."""
    candidates = [
        os.path.join(base_path, 'position_manager.html'),
        os.path.join(base_path, 'tools', 'position_manager.html'),
        os.path.join(os.path.dirname(base_path), 'tools', 'position_manager.html'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return FileResponse(p, media_type="text/html", headers=NO_CACHE_HEADERS)
    return JSONResponse({"message": "Position manager dashboard no encontrado", "tried": candidates})


# v3.31.2 — Manual nightly analyst trigger (replacement for scheduled task)
import threading as _threading

_NIGHTLY_STATE = {
    'running': False,
    'started_at': None,
    'finished_at': None,
    'last_result': None,
    'last_log_tail': None,
    'last_changes_created': [],
    'lock': _threading.Lock(),
}


def _find_nightly_script():
    """Find nightly_analyst.py absolute path (dev vs frozen exe).
    Frozen mode: .exe lives in F:\\AIdan\\dist\\, source en F:\\AIdan\\tools\\."""
    import sys as _sys
    candidates = [
        os.path.join(base_path, 'tools', 'nightly_analyst.py'),
        os.path.join(os.path.dirname(base_path), 'tools', 'nightly_analyst.py'),
        os.path.join(os.getcwd(), 'tools', 'nightly_analyst.py'),
    ]
    # Frozen exe: .exe en dist/ → project root es os.path.dirname(dist)
    if getattr(_sys, 'frozen', False):
        exe_dir = os.path.dirname(_sys.executable)
        candidates.extend([
            os.path.join(exe_dir, 'tools', 'nightly_analyst.py'),
            os.path.join(os.path.dirname(exe_dir), 'tools', 'nightly_analyst.py'),
        ])
    # Hardcoded fallback: F:\AIdan\tools\nightly_analyst.py (instalacion default)
    candidates.append(r'F:\AIdan\tools\nightly_analyst.py')

    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _find_python_exe():
    """Find a real Python interpreter. In frozen mode, sys.executable es AIdan.exe,
    asi que necesitamos buscar python.exe por separado."""
    import sys as _sys
    import shutil as _shutil
    if not getattr(_sys, 'frozen', False):
        # Dev mode: sys.executable es python.exe directo
        return _sys.executable
    # Frozen: buscar python.exe en PATH o ubicaciones tipicas
    py = _shutil.which('python') or _shutil.which('python.exe')
    if py:
        return py
    py = _shutil.which('python3') or _shutil.which('python3.exe')
    if py:
        return py
    # Hardcoded fallbacks (typical Windows installs)
    for p in [
        r'C:\Program Files\Python311\python.exe',
        r'C:\Program Files\Python312\python.exe',
        r'C:\Program Files\Python310\python.exe',
        r'C:\Python311\python.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python311\python.exe'),
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python312\python.exe'),
    ]:
        if os.path.exists(p):
            return p
    return None


def _run_nightly_in_thread(force_close_aidan=True, model=None):
    """Background thread: ejecuta nightly_analyst.py, captura output, actualiza estado."""
    import subprocess as _sub
    from datetime import datetime as _dt
    state = _NIGHTLY_STATE
    state['running'] = True
    state['started_at'] = _dt.now().isoformat()
    state['finished_at'] = None
    state['last_result'] = None
    state['last_log_tail'] = None
    state['last_changes_created'] = []

    script = _find_nightly_script()
    if not script:
        state['running'] = False
        state['finished_at'] = _dt.now().isoformat()
        state['last_result'] = 'error: nightly_analyst.py not found'
        return

    python_exe = _find_python_exe()
    if not python_exe:
        state['running'] = False
        state['finished_at'] = _dt.now().isoformat()
        state['last_result'] = 'error: no se encontro python.exe (instalar Python 3.10+)'
        return

    cmd = [python_exe, script]
    if force_close_aidan:
        cmd.append('--force')
    if model:
        cmd.extend(['--model', model])

    try:
        # Capturar pending_changes pre-run para detectar nuevos
        from src.common.db import get_pending_changes as _gpc
        before = set(c['id'] for c in _gpc(limit=500))

        r = _sub.run(cmd, capture_output=True, text=True, timeout=900, encoding='utf-8', errors='replace')

        # Detectar pending_changes nuevos
        after = _gpc(limit=500)
        new_changes = [c for c in after if c['id'] not in before]

        state['last_changes_created'] = [
            {'id': c['id'], 'change_type': c['change_type'],
             'params_json': c.get('params_json', ''),
             'reasoning': (c.get('reasoning', '') or '')[:200],
             'source': c.get('source', ''), 'status': c.get('status', '')}
            for c in new_changes
        ]

        # Leer log tail (ultimas 30 lineas)
        try:
            log_path = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'nightly_analyst.log')
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                state['last_log_tail'] = ''.join(lines[-30:])
        except Exception:
            state['last_log_tail'] = '(log file not accessible)'

        if r.returncode == 0:
            state['last_result'] = f'success ({len(new_changes)} changes created)'
        else:
            state['last_result'] = f'exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}'
    except _sub.TimeoutExpired:
        state['last_result'] = 'timeout (>15 min)'
    except Exception as e:
        state['last_result'] = f'error: {e}'
    finally:
        state['running'] = False
        from datetime import datetime as _dt
        state['finished_at'] = _dt.now().isoformat()


@app.post("/nightly-analyst/run")
async def trigger_nightly_analyst(model: str = None):
    """Manualmente dispara una sesion del nightly analyst. Corre en background;
    cliente debe hacer polling a /nightly-analyst/status para ver progreso.

    Query params:
        model: opus | groq | ollama:MODEL_NAME (force specific model, default auto)
    """
    with _NIGHTLY_STATE['lock']:
        if _NIGHTLY_STATE['running']:
            return JSONResponse({
                'ok': False,
                'error': 'Analyst already running',
                'started_at': _NIGHTLY_STATE['started_at'],
            }, status_code=409)

        # Validate model param (if provided)
        if model and model not in ('opus', 'groq') and not model.startswith('ollama:'):
            return JSONResponse({'ok': False, 'error': f'Invalid model: {model}'}, status_code=400)

        # Spawn thread
        t = _threading.Thread(target=_run_nightly_in_thread,
                              kwargs={'force_close_aidan': True, 'model': model},
                              daemon=True, name='NightlyAnalystManual')
        t.start()

    return JSONResponse({'ok': True, 'started': True, 'message': 'Analyst running in background, poll /nightly-analyst/status'},
                        headers=NO_CACHE_HEADERS)


@app.get("/nightly-analyst/status")
async def nightly_analyst_status():
    """Returns current state of nightly analyst (running, last result, last changes)."""
    s = _NIGHTLY_STATE
    return JSONResponse({
        'running': s['running'],
        'started_at': s['started_at'],
        'finished_at': s['finished_at'],
        'last_result': s['last_result'],
        'last_log_tail': s['last_log_tail'],
        'last_changes_created': s['last_changes_created'],
    }, headers=NO_CACHE_HEADERS)

@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    logger.info("API starting up...")
    init_db()
    # Restore last session (auto-login + auto-connect MT5)
    if _try_auto_login():
        logger.info("Session restored from last login")
    _try_auto_mt5()

@app.get("/health")
async def health():
    """Health check endpoint"""
    from datetime import datetime
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

_price_cache = {"price": 0, "ts": 0}

@app.get("/price")
async def get_price():
    """Fast price endpoint — Yahoo Finance real-time (same source as candles/strategies).
    Local cache 3s to avoid hammering."""
    import time as _time
    now = _time.time()
    if now - _price_cache["ts"] < 3 and _price_cache["price"] > 0:
        return JSONResponse({"price": _price_cache["price"]})
    try:
        # Primary: Yahoo Finance real-time price (free, no key, ~200ms)
        for host in ['query2.finance.yahoo.com', 'query1.finance.yahoo.com']:
            try:
                resp = requests.get(
                    f"https://{host}/v8/finance/chart/EURUSD=X",
                    params={'interval': '1m', 'range': '1m'},
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=5
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                result = data.get('chart', {}).get('result', [])
                if not result:
                    continue
                quotes = result[0].get('indicators', {}).get('quote', [{}])[0]
                closes = quotes.get('close', [])
                p = 0
                for c in reversed(closes):
                    if c is not None and c > 0:
                        p = round(float(c), 5)
                        break
                if p == 0:
                    p = result[0].get('meta', {}).get('regularMarketPrice', 0)
                    if p > 0:
                        p = round(float(p), 5)
                if p > 0:
                    _price_cache["price"] = p
                    _price_cache["ts"] = now
                    return JSONResponse({"price": p})
            except Exception:
                continue
        # Fallback: market_state cache
        tech = get_tech()
        state = tech.get_market_state()
        p = state.get('price', 0)
        if p > 0:
            _price_cache["price"] = round(p, 5)
            _price_cache["ts"] = now
        return JSONResponse({"price": _price_cache["price"]})
    except Exception:
        return JSONResponse({"price": _price_cache["price"] or 0}, status_code=503)

@app.get("/stats")
async def get_dashboard_stats():
    """Get system statistics"""
    try:
        stats = get_stats()
        return JSONResponse({
            "status": "success",
            "data": stats
        })
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

@app.get("/recent-alerts")
async def get_recent_alerts_endpoint(limit: int = 50):
    """Get recent HIGH impact alerts with EUR/USD analysis (max 20) - AI only"""
    try:
        alerts = get_recent_alerts(min(limit, 20))

        formatted_alerts = []
        for row in alerts:
            alert_id, impact_score, alert_level, sent_at, title, url, explanation, eur_usd_impact, market_implications, analysis_method, should_operate, direction, confidence = row[:13]
            published_at = row[13] if len(row) > 13 else None
            alert_result = row[14] if len(row) > 14 else None
            alert_pips = row[15] if len(row) > 15 else None
            price_at_alert = row[16] if len(row) > 16 else None
            formatted_alerts.append({
                "id": alert_id,
                "impact_score": impact_score,
                "level": alert_level,
                "sent_at": _utc_iso(sent_at),
                "published_at": _published_iso(published_at) if published_at else None,
                "title": title,
                "url": url,
                "explanation": explanation,
                "eur_usd_impact": eur_usd_impact,
                "market_implications": market_implications,
                "analysis_method": analysis_method or 'keywords',
                "should_operate": bool(should_operate),
                "direction": direction or 'NEUTRAL',
                "confidence": confidence or 50,
                "alert_result": alert_result,
                "alert_pips": alert_pips,
                "price_at_alert": price_at_alert,
            })

        return JSONResponse({
            "status": "success",
            "count": len(formatted_alerts),
            "data": formatted_alerts
        })
    except Exception as e:
        logger.error(f"Error getting alerts: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

@app.get("/recent-news")
async def get_recent_news_endpoint(limit: int = 200):
    """Get recent news"""
    try:
        from src.common.db import DB_PATH
        import sqlite3

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # v3.27.0: LEFT JOIN con alerts para incluir direction/confidence/impact
        # ORDER BY fetched_at DESC (mas estable que published_at que puede estar mal)
        cursor.execute("""
            SELECT n.id, n.title, n.url, n.fetched_at, n.language, n.tags, n.published_at,
                   a.direction, a.confidence, a.impact_score, a.alert_level, a.alert_result
            FROM news n
            LEFT JOIN alerts a ON a.news_id = n.id
            ORDER BY n.fetched_at DESC
            LIMIT ?
        """, (limit,))

        news_items = []
        for row in cursor.fetchall():
            news_id, title, url, fetched_at, language, tags = row[:6]
            published_at = row[6]
            direction = row[7]
            confidence = row[8]
            impact_score = row[9]
            alert_level = row[10]
            alert_result = row[11]
            news_items.append({
                "id": news_id,
                "title": title,
                "url": url,
                "fetched_at": _utc_iso(fetched_at),
                "published_at": _published_iso(published_at) if published_at else None,
                "language": language,
                "tags": tags,
                # v3.27.0: campos de alerta si la news fue analizada
                "direction": direction,           # 'CALL'|'PUT'|'NEUTRAL'|None
                "confidence": confidence,         # 0-100 o None
                "impact_score": impact_score,     # 0-100 o None
                "alert_level": alert_level,       # 'BAJA'|'MEDIA'|'ALTA' o None
                "alert_result": alert_result,     # 'win'|'loss'|'break_even' o None
            })

        conn.close()

        return JSONResponse({
            "status": "success",
            "count": len(news_items),
            "data": news_items
        })
    except Exception as e:
        logger.error(f"Error getting news: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

# Performance / Win-rate endpoints
class SignalResultRequest(BaseModel):
    alert_id: int
    result: str  # 'win', 'loss', 'skip'
    market_context: Optional[dict] = None

@app.post("/signal-result")
async def post_signal_result(request: SignalResultRequest):
    """Record whether a trading signal was correct, with market context for learning"""
    if request.result not in ('win', 'loss', 'skip'):
        return JSONResponse({"status": "error", "message": "Invalid result. Use: win, loss, skip"}, status_code=400)
    try:
        # Auto-capture current market state if not provided
        ctx = request.market_context or {}
        if not ctx.get('exit_price'):
            try:
                tech = get_tech()
                market = tech.get_market_state()
                if market.get('source') != 'fallback':
                    ctx['exit_price'] = market['price']
                    ctx['market_trend'] = market.get('trend', '')
                    ctx['rsi_at_entry'] = market.get('rsi', 0)
                    # Get HTF bias from SMC
                    try:
                        smc = get_smc()
                        smc.update()
                        status = smc.get_status()
                        ctx['htf_bias'] = status.get('htf_bias', '')
                    except Exception:
                        pass  # SMC optional
            except Exception:
                pass  # context enrichment optional
        record_signal_result(request.alert_id, request.result, ctx)
        return JSONResponse({"status": "success"})
    except Exception as e:
        logger.error(f"Error recording signal result: {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/performance")
async def get_performance():
    """Get win/loss performance statistics"""
    try:
        stats = get_performance_stats()
        return JSONResponse({"status": "success", "data": stats})
    except Exception as e:
        logger.error(f"Error getting performance: {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# ===== STRATEGY CREATOR ENDPOINTS =====
class StrategyDefinition(BaseModel):
    name: Optional[str] = "Sin nombre"
    trend: Optional[str] = "any"
    trend_strength: Optional[str] = "any"
    rsi_zone: Optional[str] = "any"
    momentum: Optional[str] = "any"
    price_vs_ma: Optional[str] = "any"
    min_impact: int = 50
    min_confidence: int = 60
    direction: Optional[str] = "any"
    max_trades_per_hour: int = 3
    stop_loss_pips: float = 5.0
    take_profit_pips: float = 10.0

@app.post("/strategy/backtest")
async def backtest_strategy(strategy: StrategyDefinition):
    """Backtest a strategy against all matching alerts"""
    try:
        import sqlite3
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Query ALL alerts matching the strategy filters (with or without results)
        query = """
            SELECT a.id, a.impact_score, a.confidence, a.direction,
                   a.should_operate, a.alert_sent_at, a.eur_usd_impact,
                   a.market_implications, a.explanation, n.title,
                   sr.result
            FROM alerts a
            JOIN news n ON a.news_id = n.id
            LEFT JOIN signal_results sr ON sr.alert_id = a.id
            WHERE 1=1
        """
        params = []

        if strategy.min_impact > 0:
            query += " AND a.impact_score >= ?"
            params.append(strategy.min_impact)
        if strategy.min_confidence > 0:
            query += " AND a.confidence >= ?"
            params.append(strategy.min_confidence)
        if strategy.direction and strategy.direction != "any":
            query += " AND a.direction = ?"
            params.append(strategy.direction.upper())

        query += " ORDER BY a.alert_sent_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Build signal list
        signals = []
        for r in rows:
            signals.append({
                "id": r[0], "score": r[1], "confidence": r[2],
                "direction": r[3], "should_operate": bool(r[4]),
                "time": r[5], "impact": r[6] or "",
                "action": r[7] or "", "explanation": r[8] or "",
                "title": r[9], "result": r[10]  # None if no result yet
            })

        # Stats from ALL matching signals
        total_matching = len(signals)
        operable = [s for s in signals if s["should_operate"]]
        non_operable = [s for s in signals if not s["should_operate"]]

        # Stats from signals WITH results
        with_results = [s for s in signals if s["result"] in ("win", "loss")]
        wins = sum(1 for s in with_results if s["result"] == "win")
        losses = sum(1 for s in with_results if s["result"] == "loss")
        skips = sum(1 for s in signals if s["result"] == "skip")
        pending = sum(1 for s in signals if s["result"] is None)
        total_rated = wins + losses
        win_rate = round(wins / total_rated * 100, 1) if total_rated > 0 else 0

        # Profit calculation
        expected_profit = (wins * strategy.take_profit_pips) - (losses * strategy.stop_loss_pips)
        profit_factor = round(
            (wins * strategy.take_profit_pips) / max(losses * strategy.stop_loss_pips, 0.1), 2
        ) if total_rated > 0 else 0

        # Avg confidence of matching signals
        avg_conf = round(sum(s["confidence"] for s in signals) / max(len(signals), 1), 1)
        avg_score = round(sum(s["score"] for s in signals) / max(len(signals), 1), 1)

        # Direction breakdown
        dir_breakdown = {}
        for s in signals:
            d = s["direction"]
            if d not in dir_breakdown:
                dir_breakdown[d] = {"total": 0, "wins": 0, "losses": 0}
            dir_breakdown[d]["total"] += 1
            if s["result"] == "win":
                dir_breakdown[d]["wins"] += 1
            elif s["result"] == "loss":
                dir_breakdown[d]["losses"] += 1

        return JSONResponse({
            "status": "success",
            "data": {
                "total_matching": total_matching,
                "operable": len(operable),
                "non_operable": len(non_operable),
                "with_results": total_rated,
                "wins": wins,
                "losses": losses,
                "skips": skips,
                "pending": pending,
                "win_rate": win_rate,
                "expected_profit_pips": round(expected_profit, 1),
                "profit_factor": profit_factor,
                "avg_confidence": avg_conf,
                "avg_score": avg_score,
                "direction_breakdown": dir_breakdown,
                "signals": signals[:50],  # Last 50
                "strategy_summary": f"Score≥{strategy.min_impact} | Conf≥{strategy.min_confidence}% | Dir={strategy.direction} | SL={strategy.stop_loss_pips} TP={strategy.take_profit_pips}"
            }
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/strategy/save")
async def save_strategy(strategy: StrategyDefinition):
    """Save a strategy configuration"""
    try:
        import sqlite3, json
        from datetime import datetime
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO strategies (name, config, created_at)
            VALUES (?, ?, ?)
        """, (strategy.name, json.dumps(strategy.dict()), datetime.now()))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/strategies")
async def list_strategies():
    """List saved strategies"""
    try:
        import sqlite3, json
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, config, created_at, COALESCE(is_active, 0) FROM strategies ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        strategies = [{"id": r[0], "name": r[1], "config": json.loads(r[2]), "created_at": _utc_iso(r[3]), "is_active": bool(r[4])} for r in rows]
        return JSONResponse({"status": "success", "data": strategies})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/strategy/{strategy_id}/activate")
async def activate_strategy(strategy_id: int):
    """Set a strategy as active (deactivate others)"""
    try:
        import sqlite3
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE strategies SET is_active = 0")  # deactivate all
        cursor.execute("UPDATE strategies SET is_active = 1 WHERE id = ?", (strategy_id,))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.delete("/strategy/{strategy_id}")
async def delete_strategy(strategy_id: int):
    """Delete a saved strategy"""
    try:
        import sqlite3
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        conn.commit()
        conn.close()
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/data-source")
async def get_data_source():
    """Get current price data source info"""
    try:
        from src.common.price_feed import get_last_source, _get_twelve_data_key
        has_key = bool(_get_twelve_data_key())
        return JSONResponse({
            "status": "success",
            "data": {
                "current_source": get_last_source(),
                "twelvedata_configured": has_key,
                "sources_available": ["twelvedata", "yahoo"] if has_key else ["yahoo"],
                "note": "Twelve Data ofrece precios más precisos para forex" if not has_key else None
            }
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/price-compare")
async def price_compare():
    """Compare prices from all available sources for debugging spread differences."""
    from src.common.price_feed import _fetch_fxcm, _fetch_twelvedata, _fetch_yahoo, _get_twelve_data_key, _map_interval_to_yahoo
    results = {}
    try:
        fxcm = _fetch_fxcm('5min', 5)
        if fxcm:
            results['fxcm'] = {'close': fxcm[-1]['close'], 'high': fxcm[-1]['high'], 'low': fxcm[-1]['low'], 'datetime': fxcm[-1]['datetime']}
    except Exception as e:
        results['fxcm'] = {'error': str(e)}
    try:
        key = _get_twelve_data_key()
        if key:
            td = _fetch_twelvedata('5min', 5, key)
            if td:
                results['twelvedata'] = {'close': td[-1]['close'], 'high': td[-1]['high'], 'low': td[-1]['low'], 'datetime': td[-1]['datetime']}
    except Exception as e:
        results['twelvedata'] = {'error': str(e)}
    try:
        yh_int, yh_rng = _map_interval_to_yahoo('5min', 5)
        yh = _fetch_yahoo(yh_int, yh_rng)
        if yh:
            results['yahoo'] = {'close': yh[-1]['close'], 'high': yh[-1]['high'], 'low': yh[-1]['low'], 'datetime': yh[-1]['datetime']}
    except Exception as e:
        results['yahoo'] = {'error': str(e)}

    # Calculate spreads between all source pairs
    closes = {k: v['close'] for k, v in results.items() if 'close' in v}
    if len(closes) >= 2:
        keys = list(closes.keys())
        spreads = {}
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                pair = f"{keys[i]}_vs_{keys[j]}"
                spread_pips = abs(closes[keys[i]] - closes[keys[j]]) / 0.0001
                spreads[pair] = round(spread_pips, 1)
        results['spreads_pips'] = spreads

    return JSONResponse({"status": "success", "data": results})

@app.get("/market-state")
async def get_market_state():
    """Get current EUR/USD technical analysis state"""
    try:
        tech = get_tech()
        state = dict(tech.get_market_state())  # copy to avoid mutating cache
        state.pop('_ts', None)
        # Include data source info and last 60 candles for toast chart
        try:
            from src.common.price_feed import get_last_source
            state['data_source'] = get_last_source()
        except Exception:
            state['data_source'] = 'unknown'
        try:
            candles = tech._fetch_candles()
            if candles:
                state['candles'] = [
                    {'open': c['open'], 'close': c['close'],
                     'high': c['high'], 'low': c['low']}
                    for c in candles[-60:]
                ]
        except Exception:
            pass
        return JSONResponse({"status": "success", "data": state})
    except Exception as e:
        logger.error(f"Error getting market state: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ── Auto-Strategy Endpoints ──

@app.get("/structure-status")
async def structure_status():
    """Report what the structure scanner is monitoring"""
    try:
        tech = get_tech()
        market = tech.get_market_state()
        if market.get('source') == 'fallback':
            return JSONResponse({"status": "success", "data": {"watching": "Sin datos de mercado", "active": False}})
        structures = market.get('chart_structures', {})
        supports = structures.get('supports', [])
        resistances = structures.get('resistances', [])
        price = market['price']
        watching_parts = []
        if resistances:
            nearest_res = min(resistances, key=lambda r: abs(price - r))
            dist_r = (nearest_res - price) * 10000
            watching_parts.append(f"Res {nearest_res:.5f} ({dist_r:+.1f}p)")
        if supports:
            nearest_sup = min(supports, key=lambda s: abs(price - s))
            dist_s = (nearest_sup - price) * 10000
            watching_parts.append(f"Sop {nearest_sup:.5f} ({dist_s:+.1f}p)")
        watching_parts.append(f"RSI {market['rsi']:.0f}")
        watching_parts.append(f"Tend {market['trend']}")
        return JSONResponse({"status": "success", "data": {
            "watching": " | ".join(watching_parts),
            "active": True,
            "price": market['price'],
            "rsi": market['rsi'],
            "trend": market['trend'],
            "supports": supports,
            "resistances": resistances
        }})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/auto-strategies")
async def list_auto_strategies():
    """Get active auto-generated strategies (max 6) + today's archived trades.

    v3.19.2: Combina auto_strategies (cap 6 activas) + trade_archive del dia AR
    para que la lista del dashboard muestre todos los trades del dia, no solo
    los ultimos 6. Bug observado: M15 trade #403 (3W) desaparecio del filtro
    M15 al activarse el cap.
    """
    try:
        rows = get_active_strategies(6)
        strategies = []
        for r in rows:
            # Parse candles snapshot if available
            snapshot = None
            if len(r) > 15 and r[15]:
                try:
                    import json as _json
                    from datetime import datetime as _dt, timezone as _tz
                    AR_OFFSET = -3 * 3600  # UTC-3 Argentina — match dashboard /candles
                    raw = _json.loads(r[15])
                    snapshot = []
                    for c in raw:
                        # Handle both compact {o,h,l,c,t} and full {open,high,low,close,time} formats
                        ts = c.get('time') or c.get('t') or 0
                        if isinstance(ts, str) and '-' in ts:
                            try:
                                ts = int(_dt.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=_tz.utc).timestamp())
                            except Exception:
                                ts = 0
                        else:
                            try:
                                ts = int(float(ts))
                            except (ValueError, TypeError):
                                ts = 0
                        ts = (ts // 300) * 300 + AR_OFFSET  # Align to 5min + AR timezone
                        snapshot.append({
                            "time": ts,
                            "open": c.get('open') or c.get('o', 0),
                            "high": c.get('high') or c.get('h', 0),
                            "low": c.get('low') or c.get('l', 0),
                            "close": c.get('close') or c.get('c', 0)
                        })
                    # Smooth gaps: open = prev close
                    for si in range(1, len(snapshot)):
                        pc = snapshot[si - 1]['close']
                        snapshot[si]['open'] = pc
                        if pc > snapshot[si]['high']:
                            snapshot[si]['high'] = pc
                        if pc < snapshot[si]['low']:
                            snapshot[si]['low'] = pc
                except Exception:
                    pass
            mt5_fill = r[21] if len(r) > 21 else None
            strategies.append({
                "id": r[0], "alert_id": r[1], "news_title": r[2],
                "direction": r[3],
                "entry_price": mt5_fill if mt5_fill else r[4],  # Show real fill price when available
                "stop_loss": r[5], "take_profit": r[6],
                "confidence": r[7], "impact_score": r[8],
                "expiry_minutes": r[9], "status": r[10],
                "created_at": _utc_iso(str(r[11])) if r[11] else None,
                "expires_at": _utc_iso(str(r[12])) if r[12] else None,
                "result": r[13],
                "trigger_type": r[14] if len(r) > 14 else "news",
                "candles_snapshot": snapshot,
                "profile_name": r[16] if len(r) > 16 else None,
                "mt5_ticket": r[17] if len(r) > 17 else None,
                "mt5_lot": r[18] if len(r) > 18 else None,
                "mt5_status": r[19] if len(r) > 19 else None,
                "mt5_pnl": r[20] if len(r) > 20 else None,
                # Pre-planner fields
                "event_time": r[22] if len(r) > 22 else None,
                "planning_reasoning": r[23] if len(r) > 23 else None,
                "entry_strategy": r[24] if len(r) > 24 else None,
                "risk_level": r[25] if len(r) > 25 else None,
                "sl_pips": r[26] if len(r) > 26 else None,
                "tp_pips": r[27] if len(r) > 27 else None,
            })

        # v3.19.2 — Append today's archived trades (NOT in current strategies list)
        # to fix the cap-6 disappearance bug for M15 strategies.
        # v3.30.2: query optimizada para usar idx_trade_archive_archived.
        # Antes: WHERE datetime(created_at,'-3hours') >= date('now','-3hours')
        #        - funcion sobre columna inhibe index, full scan.
        # Ahora: WHERE archived_at >= datetime('now','-1 day')
        #        - usa index, <1ms.
        try:
            import sqlite3 as _sql
            from src.common.db import DB_PATH
            existing_ids = {s['id'] for s in strategies}
            _conn = _sql.connect(DB_PATH)
            _cur = _conn.cursor()
            _cur.execute("""
                SELECT strategy_id, direction, result, mt5_pnl, trigger_type, news_title,
                       created_at, confidence, impact_score, profile_name,
                       entry_price, exit_price, stop_loss, take_profit, sl_pips, tp_pips
                FROM trade_archive
                WHERE archived_at >= datetime('now', '-1 day')
                ORDER BY strategy_id DESC
                LIMIT 30
            """)
            for ar in _cur.fetchall():
                sid = ar[0]
                if sid in existing_ids:
                    continue  # already in active list
                strategies.append({
                    "id": sid, "alert_id": None, "news_title": ar[5] or "",
                    "direction": ar[1],
                    "entry_price": ar[10],
                    "stop_loss": ar[12], "take_profit": ar[13],
                    "confidence": ar[7], "impact_score": ar[8],
                    "expiry_minutes": None,
                    "status": ('auto_win' if ar[2] == 'win' else ('auto_loss' if ar[2] == 'loss' else 'expired')),
                    "created_at": _utc_iso(str(ar[6])) if ar[6] else None,
                    "expires_at": None,
                    "result": ar[2],
                    "trigger_type": ar[4] or "news",
                    "candles_snapshot": None,
                    "profile_name": ar[9],
                    "mt5_ticket": None,
                    "mt5_lot": None,
                    "mt5_status": "closed",
                    "mt5_pnl": ar[3],
                    "from_archive": True,
                    "sl_pips": ar[14],
                    "tp_pips": ar[15],
                })
            _conn.close()
        except Exception as _ae:
            logger.debug(f"Archive merge: {_ae}")

        return JSONResponse({"status": "success", "data": strategies, "count": len(strategies)})
    except Exception as e:
        logger.error(f"Error listing auto-strategies: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

class StrategyResultRequest(BaseModel):
    strategy_id: int
    result: str  # 'win', 'loss', 'skip'
    market_context: Optional[dict] = None

@app.post("/strategy-result")
async def post_strategy_result(req: StrategyResultRequest):
    """Record win/loss/skip for an auto-strategy with market context"""
    if req.result not in ('win', 'loss', 'skip'):
        return JSONResponse({"status": "error", "message": "Invalid result"}, status_code=400)
    # Auto-capture market state
    ctx = req.market_context or {}
    if not ctx.get('exit_price'):
        try:
            tech = get_tech()
            market = tech.get_market_state()
            if market.get('source') != 'fallback':
                ctx['exit_price'] = market['price']
                ctx['market_trend'] = market.get('trend', '')
                ctx['rsi_at_entry'] = market.get('rsi', 0)
                try:
                    smc = get_smc()
                    smc.update()
                    status = smc.get_status()
                    ctx['htf_bias'] = status.get('htf_bias', '')
                except Exception:
                    pass  # SMC optional
        except Exception:
            pass  # context enrichment optional
    record_strategy_result(req.strategy_id, req.result, ctx)
    return JSONResponse({"status": "success"})

@app.post("/auto-strategy/{strategy_id}/toggle-pause")
async def toggle_pause(strategy_id: int):
    """Toggle pause/resume for an auto-strategy"""
    try:
        new_status = toggle_strategy_pause(strategy_id)
        if new_status is None:
            return JSONResponse({"status": "error", "message": "Strategy not found or cannot be paused"}, status_code=400)
        return JSONResponse({"status": "ok", "new_status": new_status})
    except Exception as e:
        logger.error(f"Error toggling pause for #{strategy_id}: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/planned-strategies")
async def list_planned_strategies():
    """Get pre-planned strategies for upcoming events"""
    try:
        strategies = get_planned_strategies()
        return JSONResponse({"status": "success", "data": strategies, "count": len(strategies)})
    except Exception as e:
        logger.error(f"Error fetching planned strategies: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/post-trade-analysis")
async def list_post_trade_analysis():
    """Get recent post-trade analyses from Gemma 4"""
    try:
        analyses = get_post_trade_analyses(20)
        stats = get_post_trade_stats()
        return JSONResponse({"status": "success", "data": analyses, "stats": stats})
    except Exception as e:
        logger.error(f"Error fetching post-trade analyses: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/generate-report")
async def generate_report():
    """Generate and upload daily report to Google Sheets"""
    try:
        from src.reports.daily_report import generate_daily_report
        result = generate_daily_report()
        return JSONResponse(result)
    except ImportError:
        return JSONResponse({"status": "error", "message": "gspread not installed"}, status_code=500)
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/strategy-performance")
async def strategy_perf():
    """Get win/loss stats for auto-strategies"""
    return JSONResponse({"status": "success", "data": get_strategy_performance()})


@app.get("/strategy-performance-by-track")
async def strategy_perf_by_track():
    """v3.19.0 - Stats segmentadas Track A (M5) vs Track B (M15) para comparativa dual-track."""
    return JSONResponse({"status": "success", "data": get_strategy_performance_by_track()})


@app.get("/equity-curve")
async def equity_curve(days: int = 30):
    """v3.28.0 — Equity curve: balance over time computed from trade_archive.

    Returns: {points: [{timestamp, balance, pnl_acum, trade_id}], baseline}
    """
    try:
        from src.common.db import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(f"""
            SELECT strategy_id, mt5_pnl, archived_at
            FROM trade_archive
            WHERE archived_at >= datetime('now', '-{int(days)} days')
              AND mt5_pnl IS NOT NULL
            ORDER BY archived_at ASC
        """)
        rows = cur.fetchall()
        conn.close()
        baseline = 1000.0
        points = []
        running = 0.0
        for sid, pnl, ts in rows:
            running += float(pnl or 0)
            points.append({
                'timestamp': ts,
                'balance': round(baseline + running, 2),
                'pnl_acum': round(running, 2),
                'trade_id': sid,
            })
        return JSONResponse({
            'status': 'success',
            'data': {
                'points': points,
                'baseline': baseline,
                'final_balance': round(baseline + running, 2),
                'total_pnl': round(running, 2),
                'count': len(points),
            }
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/slippage-stats")
async def slippage_stats(days: int = 7):
    """v3.28.0 — Slippage tracking stats."""
    try:
        from src.common.slippage_tracker import get_slippage_stats
        return JSONResponse({"status": "success", "data": get_slippage_stats(days=days)})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/consensus-state")
async def consensus_state():
    """v3.28.0 — Recent consensus tracker state (debug)."""
    try:
        from src.common.consensus_tracker import get_recent_state
        events = get_recent_state()
        return JSONResponse({"status": "success", "data": [
            {'ts': ts, 'track': track, 'direction': direction}
            for ts, track, direction in events
        ]})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/wr-heatmap")
async def wr_heatmap(mode: str = 'weekday', days: int = 30):
    """v3.29.1 — Heatmap WR. Dos modos:
    - mode='weekday' (default): agrega por dia de semana (Lun-Vie) x hora UTC
    - mode='date': por fecha calendario ultimos N dias x hora UTC

    Returns: {mode, rows: [{label, hours: {h: {wins, total, wr}}, day_total: {wins, total, wr}}]}
    """
    try:
        from src.common.db import DB_PATH
        import sqlite3
        from datetime import datetime
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        if mode == 'date':
            # Por fecha calendario: ultimos N dias
            cur.execute(f"""
                SELECT date(datetime(created_at,'-3 hours')) as d, hour_utc, result, COUNT(*)
                FROM trade_archive
                WHERE result IN ('win', 'loss')
                  AND created_at >= date('now', '-{int(days)} days')
                  AND hour_utc IS NOT NULL
                GROUP BY d, hour_utc, result
                ORDER BY d DESC
            """)
            rows_data = cur.fetchall()
            # Agg into rows ordered by date desc
            row_map = {}  # date_str -> {hours: {}, day_total: {}}
            for date_str, hour, result, count in rows_data:
                if not date_str: continue
                try: hour = int(hour)
                except: continue
                if date_str not in row_map:
                    row_map[date_str] = {'hours': {}, 'wins': 0, 'losses': 0}
                row = row_map[date_str]
                if hour not in row['hours']:
                    row['hours'][hour] = {'wins': 0, 'total': 0}
                row['hours'][hour]['total'] += count
                if result == 'win':
                    row['hours'][hour]['wins'] += count
                    row['wins'] += count
                else:
                    row['losses'] += count
            # Format output
            out_rows = []
            total_trades = 0
            for date_str, row in row_map.items():
                # Calc WR por hora
                for h, cell in row['hours'].items():
                    cell['wr'] = round((cell['wins'] / cell['total'] * 100) if cell['total'] else 0, 1)
                # Day total
                d_total = row['wins'] + row['losses']
                d_wr = round((row['wins'] / d_total * 100) if d_total else 0, 1)
                # Friendly label: 9 May (Sáb)
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    day_short = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'][dt.weekday()]
                    label = f"{dt.day}/{dt.month} {day_short}"
                except Exception:
                    label = date_str
                out_rows.append({
                    'label': label,
                    'date': date_str,
                    'hours': row['hours'],
                    'day_total': {'wins': row['wins'], 'losses': row['losses'], 'total': d_total, 'wr': d_wr},
                })
                total_trades += d_total
            conn.close()
            return JSONResponse({'status': 'success', 'data': {
                'mode': 'date',
                'rows': out_rows,
                'total': total_trades,
            }})

        # mode='weekday' (default)
        cur.execute("""
            SELECT day_of_week, hour_utc, result, COUNT(*)
            FROM trade_archive
            WHERE result IN ('win', 'loss')
              AND day_of_week IS NOT NULL AND hour_utc IS NOT NULL
            GROUP BY day_of_week, hour_utc, result
        """)
        rows_data = cur.fetchall()
        conn.close()
        day_names = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie'}
        row_map = {}
        for dow_str, hour, result, count in rows_data:
            try:
                dow = int(dow_str); hour = int(hour)
            except: continue
            if dow not in day_names: continue
            day = day_names[dow]
            if day not in row_map:
                row_map[day] = {'hours': {}, 'wins': 0, 'losses': 0}
            row = row_map[day]
            if hour not in row['hours']:
                row['hours'][hour] = {'wins': 0, 'total': 0}
            row['hours'][hour]['total'] += count
            if result == 'win':
                row['hours'][hour]['wins'] += count
                row['wins'] += count
            else:
                row['losses'] += count
        out_rows = []
        total_trades = 0
        for day_label in ['Lun', 'Mar', 'Mié', 'Jue', 'Vie']:
            row = row_map.get(day_label, {'hours': {}, 'wins': 0, 'losses': 0})
            for h, cell in row['hours'].items():
                cell['wr'] = round((cell['wins'] / cell['total'] * 100) if cell['total'] else 0, 1)
            d_total = row['wins'] + row['losses']
            d_wr = round((row['wins'] / d_total * 100) if d_total else 0, 1)
            out_rows.append({
                'label': day_label,
                'hours': row['hours'],
                'day_total': {'wins': row['wins'], 'losses': row['losses'], 'total': d_total, 'wr': d_wr},
            })
            total_trades += d_total
        return JSONResponse({'status': 'success', 'data': {
            'mode': 'weekday',
            'rows': out_rows,
            'total': total_trades,
        }})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/filter-contribution")
async def filter_contribution():
    """v3.29.0 — Análisis: cada filtro, cuántos trades hubiera bloqueado y PnL impact.

    Para cada filtro activo en el sistema, simulamos sobre trade_archive:
    - ¿cuántos trades cumplen el criterio del filtro?
    - ¿cuál es el PnL acumulado de ESOS trades?
    - 'saved_pnl' positivo = filtro bloqueó perdedores (bueno)
    - 'saved_pnl' negativo = filtro hubiera bloqueado ganadores (malo)
    """
    try:
        from src.common.db import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT direction, confidence, impact_score, htf_bias, market_trend,
                   avg_range_pips, mt5_pnl, sl_pips, tp_pips, trigger_type
            FROM trade_archive
            WHERE result IN ('win', 'loss')
              AND mt5_pnl IS NOT NULL
        """)
        rows = cur.fetchall()
        conn.close()
        total = len(rows)

        def filter_stats(name, predicate):
            blocked = [r for r in rows if predicate(r)]
            n = len(blocked)
            saved = -sum((r[6] or 0) for r in blocked)  # positivo si bloqueó perdedores
            return {'name': name, 'would_block': n, 'saved_pnl': round(saved, 2)}

        filters = [
            filter_stats('ATR floor (<2.5p)', lambda r: (r[5] or 99) < 2.5),
            filter_stats('ATR ceiling (>6p)', lambda r: (r[5] or 0) > 6.0),
            filter_stats('Min conf (<60)', lambda r: (r[1] or 100) < 60),
            filter_stats('Conf ceiling (>=80)', lambda r: (r[1] or 0) >= 80),
            filter_stats('Counter-HTF (CALL+bear / PUT+bull)',
                         lambda r: ((r[0] == 'CALL' and (r[3] or '') == 'bearish') or
                                    (r[0] == 'PUT' and (r[3] or '') == 'bullish'))),
            filter_stats('Counter-both (HTF+M5 ambos contra)',
                         lambda r: (((r[0] == 'CALL' and (r[3] or '') == 'bearish' and (r[4] or '') == 'bearish') or
                                    (r[0] == 'PUT' and (r[3] or '') == 'bullish' and (r[4] or '') == 'bullish')))),
            filter_stats('SIM A (fully aligned)',
                         lambda r: ((r[0] == 'CALL' and (r[3] or '') == 'bullish' and (r[4] or '') == 'bullish') or
                                    (r[0] == 'PUT' and (r[3] or '') == 'bearish' and (r[4] or '') == 'bearish'))),
            filter_stats('Impact score (<55)', lambda r: (r[2] or 100) < 55),
            filter_stats('pre_planned trigger', lambda r: (r[9] or '') == 'pre_planned'),
        ]
        # Sort by absolute saved_pnl
        filters.sort(key=lambda f: abs(f['saved_pnl']), reverse=True)
        return JSONResponse({'status': 'success', 'data': {'filters': filters, 'total_archive': total}})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

_candles_cache = {"data": [], "last_fetch": 0}

def _convert_candles_to_lw(candles):
    """Convert raw candles to Lightweight Charts format.
    Timestamps shifted to Argentina (UTC-3) for display."""
    from datetime import datetime as _dt, timezone as _tz
    AR_OFFSET = -3 * 3600  # UTC-3 Argentina
    lw_candles = []
    for c in candles:
        ts = c.get('datetime', c.get('timestamp', 0))
        try:
            ts_int = int(float(ts))
        except (ValueError, TypeError):
            try:
                dt = _dt.strptime(str(ts), '%Y-%m-%d %H:%M:%S').replace(tzinfo=_tz.utc)
                ts_int = int(dt.timestamp())
            except Exception:
                continue
        ts_aligned = (ts_int // 300) * 300 + AR_OFFSET
        lw_candles.append({
            "time": ts_aligned,
            "open": round(c['open'], 6), "high": round(c['high'], 6),
            "low": round(c['low'], 6), "close": round(c['close'], 6)
        })
    # Remove duplicate timestamps (keep last occurrence)
    seen = {}
    for candle in lw_candles:
        seen[candle['time']] = candle
    result = sorted(seen.values(), key=lambda x: x['time'])
    return result

@app.get("/candles")
async def get_candles():
    """Get EUR/USD candle data for Lightweight Charts (cached, refreshes every 60s).
    Priority: MT5 (best quality) → Yahoo Finance fallback."""
    import time as _time
    try:
        now = _time.time()
        # Refresh every 60s
        if now - _candles_cache["last_fetch"] > 60 or not _candles_cache["data"]:
            candles = None

            # 1. Try MT5 first (best quality, real broker data)
            MIN_GOOD_CANDLES = 40  # Minimum for a useful chart
            try:
                mt5 = _get_mt5()
                if mt5 and mt5.is_ready():
                    candles = mt5.get_candles(timeframe='5min', count=100)
                    if candles and len(candles) >= MIN_GOOD_CANDLES:
                        logger.info(f"Candles from MT5: {len(candles)}")
                    elif candles:
                        logger.info(f"MT5 returned only {len(candles)} candles (warming up), trying Yahoo supplement")
                        candles = None  # Force Yahoo fallback for now
            except Exception as e:
                logger.warning(f"MT5 candles failed: {e}")

            # 2. Fallback to Yahoo/price_feed
            if not candles:
                tech = get_tech()
                candles = tech._fetch_candles()
                if candles:
                    logger.info(f"Candles from price_feed: {len(candles)}")

            if candles and len(candles) > 5:
                _candles_cache["data"] = _convert_candles_to_lw(candles)
                _candles_cache["last_fetch"] = now
                logger.info(f"Candles cache refreshed: {len(_candles_cache['data'])} candles")

        if not _candles_cache["data"]:
            return JSONResponse({"status": "error", "message": "No candle data"}, status_code=503)

        return JSONResponse({"status": "success", "data": _candles_cache["data"]})
    except Exception as e:
        logger.error(f"Error fetching candles: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ── Auto-Tuner Endpoints ──

@app.get("/tuner-status")
async def tuner_status():
    """Get current auto-tuner optimization status"""
    try:
        t = get_tuner()
        status = t.get_status()
        return JSONResponse({"status": "success", "data": status})
    except Exception as e:
        logger.error(f"Tuner status error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/tuner-run")
async def tuner_run():
    """Force an auto-tuner optimization cycle"""
    try:
        t = get_tuner()
        result = t.run_optimization(force=True)
        return JSONResponse({"status": "success", "data": result})
    except Exception as e:
        logger.error(f"Tuner run error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/blocked-setups")
async def blocked_setups():
    """Get list of setup types blocked by the auto-tuner"""
    try:
        t = get_tuner()
        return JSONResponse({"status": "success", "data": t.get_blocked_setups()})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ── SMC Endpoints ──

@app.get("/smc-state")
async def smc_state():
    """Get full SMC multi-timeframe state"""
    try:
        smc = get_smc()
        smc.update()
        status = smc.get_status()
        mtf = smc.get_mtf_state() or {}

        # Format for frontend
        data = {
            'status': status.get('status', 'no_data'),
            'message': status.get('message', ''),
            'htf_bias': status.get('htf_bias', 'neutral'),
            'timeframes': {}
        }

        for tf in ['H1', 'M15', 'M5']:
            s = mtf.get(tf, {})
            struct = s.get('structure', [])
            data['timeframes'][tf] = {
                'trend': s.get('trend', 'unknown'),
                'last_swing_high': s.get('last_swing_high'),
                'last_swing_low': s.get('last_swing_low'),
                'ma9': s.get('ma9', 0),
                'ma21': s.get('ma21', 0),
                'structure': [{'type': p['type'], 'price': p['price']} for p in struct[-4:]],
                'bos': s.get('bos'),
            }

        # Zones
        zones = smc.get_zones() or {}
        data['zones'] = {
            'demand': [],
            'supply': []
        }
        for tf in ['H1', 'M15', 'M5']:
            for z in zones.get(tf, []):
                entry = {
                    'top': z['top'], 'bottom': z['bottom'],
                    'timeframe': tf, 'strength': z['strength'],
                    'touches': z['touches']
                }
                if z['type'] == 'demand':
                    data['zones']['demand'].append(entry)
                else:
                    data['zones']['supply'].append(entry)

        # Confirmation details
        data['nearest_demand'] = status.get('nearest_demand', [])
        data['nearest_supply'] = status.get('nearest_supply', [])
        data['active_zone'] = status.get('active_zone')
        data['m5_bos'] = status.get('m5_bos')

        return JSONResponse({"status": "success", "data": data})
    except Exception as e:
        logger.error(f"SMC state error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/smc-rules")
async def get_smc_rules():
    """Get current SMC rules"""
    import json
    rules_path = os.path.join('config', 'smc_rules.json')
    try:
        if os.path.exists(rules_path):
            with open(rules_path, 'r', encoding='utf-8') as f:
                return JSONResponse({"status": "success", "data": json.load(f)})
        return JSONResponse({"status": "success", "data": {}})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.put("/smc-rules")
async def update_smc_rules(request: Request):
    """Update SMC rules"""
    import json
    rules_path = os.path.join('config', 'smc_rules.json')
    try:
        body = await request.json()
        os.makedirs('config', exist_ok=True)
        with open(rules_path, 'w', encoding='utf-8') as f:
            json.dump(body, f, indent=2, ensure_ascii=False)
        # Reload in SMC engine
        global _smc_engine
        _smc_engine = None
        return JSONResponse({"status": "success", "message": "Reglas SMC actualizadas"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# Modelos para chat con Ollama
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    context: Optional[List[ChatMessage]] = []
    image_base64: Optional[str] = None

# ── Economic Calendar (Forex Factory free JSON) ──
_calendar_cache = {"events": [], "ts": 0}
_CAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

def _fetch_calendar_events():
    """Fetch economic calendar from Forex Factory free JSON.
    v3.40.4: FF limita a ~1 load/hora por IP. El cache viejo solo cacheaba exitos (`and events`),
    asi que con events vacio re-fetcheaba CADA ciclo -> auto-ban 429. Ahora cachea el intento por
    1h SIEMPRE (exito o fallo) + User-Agent de navegador + loguea respuestas no-200 (antes silencio)."""
    import time as _time
    now = _time.time()
    if now - _calendar_cache["ts"] < 3600:
        return _calendar_cache["events"]
    _calendar_cache["ts"] = now  # marca el intento ya: respeta el rate-limit aunque falle

    try:
        resp = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                            headers=_CAL_HEADERS, timeout=10)
        if resp.status_code == 200:
            all_events = resp.json()
            from datetime import datetime, timezone, timedelta
            ar_tz = timezone(timedelta(hours=-3))
            today = datetime.now(ar_tz).strftime('%Y-%m-%d')
            tomorrow = (datetime.now(ar_tz) + timedelta(days=1)).strftime('%Y-%m-%d')

            filtered = []
            for ev in all_events:
                country = ev.get('country', '')
                impact = ev.get('impact', '')
                if country not in ('USD', 'EUR'):
                    continue
                if impact not in ('High', 'Medium'):
                    continue

                event_date = ev.get('date', '')[:10]
                if event_date not in (today, tomorrow):
                    continue

                filtered.append({
                    'date': ev.get('date', ''),
                    'time': ev.get('date', '')[11:16] if len(ev.get('date', '')) > 15 else '',
                    'currency': country,
                    'event': ev.get('title', ''),
                    'impact': impact,
                    'forecast': ev.get('forecast', ''),
                    'previous': ev.get('previous', ''),
                    'actual': ev.get('actual', '')
                })

            _calendar_cache["events"] = filtered
            return filtered
        else:
            logger.warning(f"Calendar feed non-200: HTTP {resp.status_code} (FF rate-limit/throttle) — usando cache ({len(_calendar_cache['events'])} ev); reintento en 1h")
    except Exception as e:
        logger.warning(f"Calendar fetch failed: {e}")

    return _calendar_cache["events"]

@app.get("/calendar")
async def get_calendar():
    events = _fetch_calendar_events()
    return JSONResponse({"status": "success", "events": events})

@app.get("/chat-context")
async def get_chat_context():
    """Obtener contexto actual del sistema para el chat"""
    try:
        from src.common.db import DB_PATH
        import sqlite3

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT impact_score, level, title, explanation, eur_usd_impact
            FROM alerts
            ORDER BY sent_at DESC
            LIMIT 5
        """)
        alerts = cursor.fetchall()

        cursor.execute("""
            SELECT title, fetched_at
            FROM news
            ORDER BY fetched_at DESC
            LIMIT 10
        """)
        news = cursor.fetchall()

        conn.close()

        return JSONResponse({
            "status": "success",
            "alerts": alerts,
            "news": news
        })
    except Exception as e:
        logger.error(f"Error getting chat context: {str(e)}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/chat")
async def chat_with_ollama(request: ChatRequest):
    """Chat con Ollama optimizado para scalping EUR/USD"""
    try:
        from src.common.db import DB_PATH
        import sqlite3

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Últimas 8 alertas con datos completos
        cursor.execute("""
            SELECT a.impact_score, a.alert_level, n.title, a.eur_usd_impact,
                   a.direction, a.confidence, a.explanation, a.market_implications,
                   a.alert_sent_at
            FROM alerts a
            JOIN news n ON a.news_id = n.id
            ORDER BY a.alert_sent_at DESC
            LIMIT 8
        """)
        alerts_data = cursor.fetchall()

        # Últimas 10 noticias recientes
        cursor.execute("""
            SELECT title, fetched_at, summary
            FROM news
            ORDER BY fetched_at DESC
            LIMIT 10
        """)
        recent_news = cursor.fetchall()

        # Stats generales
        cursor.execute("SELECT COUNT(*) FROM news")
        total_news = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM alerts")
        total_alerts = cursor.fetchone()[0]

        # Performance stats
        cursor.execute("""
            SELECT
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                COUNT(*) as total
            FROM signal_results WHERE result != 'skip'
        """)
        perf_row = cursor.fetchone()
        wins = perf_row[0] or 0 if perf_row else 0
        losses = perf_row[1] or 0 if perf_row else 0
        perf_total = perf_row[2] or 0 if perf_row else 0
        win_rate = round(wins / perf_total * 100, 1) if perf_total > 0 else 0

        # Detailed trade history for AI learning (individual trades, not just averages)
        patterns_text = ""
        try:
            trade_history = get_detailed_trade_history(30)
            if trade_history:
                patterns_text = f"\n📊 HISTORIAL DE TRADES ({len(trade_history)} operaciones, más reciente primero):\n"
                for i, t in enumerate(trade_history[:15]):  # Show 15 most recent individually
                    result_icon = '✅' if t['result'] == 'win' else '❌'
                    pips_str = f"{t['pips']:+.1f}p" if t['pips'] else ''
                    htf_str = f"HTF:{t['htf_bias']}" if t['htf_bias'] else ''
                    setup_str = t['setup_type'].replace('_', ' ') if t['setup_type'] else t['trigger_type']
                    patterns_text += (
                        f"  #{i+1} {result_icon} {t['result'].upper()} {t['direction']} | "
                        f"Conf:{t['confidence']:.0f}% | {setup_str} | "
                        f"RSI:{t['rsi']:.0f} | Trend:{t['market_trend']} | {htf_str} {pips_str}\n"
                    )

                # Computed patterns
                lessons = get_learned_lessons()
                if lessons:
                    patterns_text += lessons + "\n"
                patterns_text += "  IMPORTANTE: Usá estos datos concretos para calibrar recomendaciones. Si un setup tiene <40% WR, advertí al trader.\n"
        except Exception as e:
            logger.warning(f"Trade history for chat failed: {e}")

        # Auto-strategies del día
        cursor.execute("""
            SELECT s.direction, s.entry_price, s.stop_loss, s.take_profit,
                   s.confidence, s.impact_score, s.status, s.news_title,
                   s.created_at, sr.result
            FROM auto_strategies s
            LEFT JOIN strategy_results sr ON s.id = sr.strategy_id
            WHERE date(s.created_at) = date(?)
            ORDER BY s.created_at DESC LIMIT 6
        """, (today_ar(),))
        strategy_rows = cursor.fetchall()

        conn.close()

        # Formatear estrategias
        strategies_text = ""
        if strategy_rows:
            strategies_text = "\n\n🎯 AUTO-ESTRATEGIAS DEL DÍA:\n"
            for direction, entry, sl, tp, conf, impact, status, title, created, result in strategy_rows:
                result_str = f" → Resultado: {result.upper()}" if result else ""
                strategies_text += f"  → {direction} @ {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | Conf: {conf:.0f}%{result_str}\n"
                strategies_text += f"    Status: {status} | Noticia: {title[:60]}\n"
            strat_perf = get_strategy_performance()
            if strat_perf.get('total', 0) > 0:
                be_str = f"/{strat_perf.get('break_evens', 0)}BE" if strat_perf.get('break_evens', 0) > 0 else ""
                strategies_text += f"  📊 Estrategias: {strat_perf['wins']}W/{strat_perf['losses']}L{be_str} | WR: {strat_perf['win_rate']}%\n"

        # Formatear alertas para el contexto
        alerts_text = ""
        if alerts_data:
            alerts_text = "\n\n📊 ALERTAS ACTIVAS DEL SISTEMA (más recientes primero):\n"
            for score, level, title, eur_impact, direction, confidence, explanation, implications, sent_at in alerts_data:
                alerts_text += f"  → [{level}] {direction} | Confianza: {confidence:.0f}% | Score: {score}/100\n"
                alerts_text += f"    Noticia: {title[:80]}\n"
                if explanation:
                    alerts_text += f"    Análisis: {explanation[:120]}\n"
                if implications:
                    alerts_text += f"    Acción: {implications[:100]}\n"
                alerts_text += f"    Hora: {sent_at}\n\n"

        # Formatear noticias recientes
        news_text = ""
        if recent_news:
            news_text = "\n📰 NOTICIAS RECIENTES:\n"
            for item in recent_news:
                title = item[0]
                fetched = item[1]
                summary = item[2] if len(item) > 2 and item[2] else ""
                news_text += f"  • {title[:90]} ({fetched})\n"
                if summary:
                    news_text += f"    Resumen: {summary[:150]}\n"

        # Performance text
        perf_text = f"\n📈 TU RENDIMIENTO: {wins}W / {losses}L | Win Rate: {win_rate}%\n" if perf_total > 0 else ""

        # Technical analysis context
        tech_text = ""
        try:
            tech = get_tech()
            market = tech.get_market_state()
            if market.get('source') != 'fallback':
                tech_text = f"""

📊 ANÁLISIS TÉCNICO EN VIVO (EUR/USD 5min):
- Precio: {market['price']:.5f}
- Tendencia: {market['trend'].upper()} ({market['trend_strength']})
- RSI(14): {market['rsi']:.1f} ({market['rsi_zone']})
- MA9: {market['ma_fast']:.5f} | MA21: {market['ma_slow']:.5f}
- Precio vs MA: {market['price_vs_ma']}
- Momentum: {market['momentum']}
- Volatilidad: {market['volatility']}
- Rango promedio: {market.get('avg_range_pips', 0):.1f} pips"""
                structures = market.get('chart_structures', {})
                if structures:
                    sups = ', '.join(f'{s:.5f}' for s in structures.get('supports', []))
                    ress = ', '.join(f'{r:.5f}' for r in structures.get('resistances', []))
                    tech_text += f"""
- Soportes: {sups or 'N/A'}
- Resistencias: {ress or 'N/A'}
- Bollinger: Upper {structures.get('bb_upper', 0):.5f} | Middle {structures.get('bb_middle', 0):.5f} | Lower {structures.get('bb_lower', 0):.5f}
- Posición: {structures.get('price_position', 'N/A')}"""
                tech_text += """
IMPORTANTE: Usá estos datos técnicos para CONTRASTAR con las noticias. Si las noticias dicen CALL pero la tendencia es bajista fuerte, mencionalo. Analizá soportes/resistencias cercanos."""
                # Add raw candles for pattern detection
                try:
                    candles_text = get_tech().get_candles_text(15)
                    if candles_text:
                        tech_text += candles_text
                except Exception as ce:
                    logger.warning(f"Candles text for chat failed: {ce}")
        except Exception as e:
            logger.warning(f"Tech context for chat failed: {e}")

        # SMC multi-timeframe context
        smc_text = ""
        try:
            smc = get_smc()
            smc.update()
            smc_text = smc.get_chat_context()
        except Exception as e:
            logger.warning(f"SMC context for chat failed: {e}")

        # Economic calendar context - real events from Forex Factory
        calendar_text = ""
        try:
            from datetime import datetime, timezone, timedelta
            ar_tz = timezone(timedelta(hours=-3))
            now_ar = datetime.now(ar_tz)
            day_names = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                         'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
            day_en = now_ar.strftime('%A')
            today_str = f"{day_names.get(day_en, day_en)} {now_ar.strftime('%d/%m/%Y')}"
            hour_now = now_ar.strftime('%H:%M')

            events = _fetch_calendar_events()
            events_text = ""
            if events:
                for ev in events:
                    impact_icon = "\U0001f534" if ev['impact'] == 'High' else "\U0001f7e1"
                    actual_str = f" | Actual: {ev['actual']}" if ev.get('actual') else ""
                    forecast_str = f" | Previsión: {ev['forecast']}" if ev.get('forecast') else ""
                    prev_str = f" | Anterior: {ev['previous']}" if ev.get('previous') else ""
                    events_text += f"\n  {impact_icon} {ev['time']} UTC | {ev['currency']} | {ev['event']}{forecast_str}{prev_str}{actual_str}"

            calendar_text = f"""

\U0001f4c5 CALENDARIO ECONÓMICO (Hoy es {today_str}, hora actual: {hour_now} AR):
{events_text if events_text else '  No se pudieron obtener eventos. Recomendá al usuario revisar el CALENDARIO ECONÓMICO en el dashboard.'}

REGLAS PARA EVENTOS:
- NO operar 5 min antes y después de eventos \U0001f534 ALTO impacto
- Esperar el pullback post-noticia, no entrar en el spike
- Si un evento importante está cerca (< 30 min), ADVERTÍ al trader con urgencia
- Eventos clave: decisiones tasas Fed/ECB, NFP, IPC (CPI), PIB, PMI, declaraciones Powell/Lagarde
- Mencioná los eventos próximos SIEMPRE que el usuario pregunte sobre el mercado"""
        except Exception as e:
            logger.warning(f"Calendar context failed: {e}")

        # Construir historial de conversación
        conversation_history = ""
        if request.context:
            for msg in request.context:
                role_label = "Usuario" if msg.role == "user" else "AIdan"
                conversation_history += f"{role_label}: {msg.content}\n"

        conversation_history += f"Usuario: {request.message}\n"

        if request.image_base64:
            conversation_history += "[El usuario adjuntó una IMAGEN/GRÁFICO de trading para que analices. Describí lo que ves en el gráfico: patrones de velas, indicadores, niveles, tendencia, y dá tu opinión de trading basada en lo visual.]\n"

        # System prompt ULTRA optimizado para scalping
        system_context = f"""Sos AIdan, un trader profesional de SCALPING en EUR/USD con opciones binarias. Tu trabajo es ayudar al usuario a tomar decisiones de trading en tiempo real.

PERFIL DE EXPERTISE:
- Scalping EUR/USD en velas de 1 a 5 minutos
- Opciones binarias: CALL (sube) o PUT (baja)
- Análisis técnico rápido: RSI, EMA 9/21, Bollinger Bands, VWAP
- Patrones de velas: engulfing, pin bar, doji, hammer, morning/evening star
- Price action: soportes, resistencias, niveles psicológicos (1.0800, 1.0850, 1.0900)
- Gestión de riesgo: máximo 2-3% por operación, nunca más
- Spread normal EUR/USD: 0.5-1.0 pips
- Horarios óptimos: Londres 8:00-12:00 CET, NY 14:30-18:00 CET, overlap 14:30-17:00 CET

DATOS EN TIEMPO REAL DEL SISTEMA:
- Noticias monitoreadas: {total_news}
- Alertas generadas: {total_alerts}{perf_text}{patterns_text}{tech_text}{smc_text}{calendar_text}{alerts_text}{news_text}{strategies_text}

CÓMO RESPONDÉS:
1. Español rioplatense, directo, sin rodeos
2. Si preguntan "opero o no" → respondé SÍ o NO primero, después explicá
3. Siempre incluí: dirección (CALL/PUT), timeframe sugerido, stop loss en pips, nivel de confianza
4. Si no hay señal clara → "**NO OPERAR**" sin vueltas
5. **negrita** para acciones clave y decisiones
6. *cursiva* para advertencias y riesgos
7. Respuestas de 3-8 líneas. Más solo si piden detalle
8. Si el usuario comparte un gráfico/imagen: analizá patrones visibles, tendencia, indicadores, y dá tu recomendación
9. SIEMPRE contraponé lo que dicen las noticias con lo que muestra el gráfico. Si hay contradicción, mencionalo
10. Tenés los datos OHLCV de las últimas 15 velas 5min de EUR/USD. Mencioná patrones detectados (engulfing, pin bar, doji, hammer) y si confirman o contradicen la señal fundamental. Citá precios concretos.
10. Si el usuario tiene mal win-rate, sugerí ajustes de estrategia
11. Números concretos siempre: pips, %, probabilidades, minutos
12. NO saludar si ya hay conversación previa
13. Terminá apenas des la info. Sin despedidas ni "¿algo más?"
14. Si hay auto-estrategias activas, mencioná si tu análisis confirma o contradice la estrategia

METODOLOGÍA SMC (Smart Money Concepts) - SOS UN COACH DE DISCIPLINA:
Tu prioridad es que el trader RESPETE la metodología y NO se auto-sabotee:
1. SIEMPRE mencioná la tendencia del timeframe mayor (H1/M15) ANTES de cualquier recomendación
2. NUNCA recomendés entrada sin confirmación en temporalidad menor (M5)
3. Si preguntan por un CALL pero H1 es bajista → ADVERTÍ primero, enfáticamente
4. Mencioná la zona de demanda/oferta activa más cercana (si hay)
5. Confirmación = nuevo HH en M5 (para CALL) o nuevo LL en M5 (para PUT) en zona relevante
6. Sin confirmación → respondé "ESPERANDO CONFIRMACIÓN - NO ENTRAR"
7. Frases de disciplina: "Disciplina > Cantidad", "Mejor perder oportunidad que capital"
8. El precio puede irse y no volver a zona — eso NO es una operación perdida, es disciplina
9. Recordá: TODO impulso tiene corrección. En tendencia alcista HTF, buscá zonas de demanda en retrocesos
10. Solo operar A FAVOR de la tendencia HTF. Contra-tendencia = prohibido salvo confluencia extrema

ESTRATEGIA SCALPING QUE RECOMENDÁS:
- Entrada: Confirmación con HTF trend + zona demanda/oferta + BOS o HH/LL en M5
- Expiración: 2-3 min para momentum fuerte, 5 min para confirmación
- NO operar en los primeros 5 min de una noticia de alto impacto (spread se ensancha)
- Esperar el pullback post-noticia, no entrar en el spike
- Mejor momento: 15:00-17:00 CET (overlap Londres-NY, máximo volumen)
- Evitar: Viernes después de 18:00, domingo apertura, feriados USA/EU

CONVERSACIÓN:
{conversation_history}

AIdan:"""

        # Split system prompt for DeepSeek messages format
        system_message = system_context.split("CONVERSACIÓN:")[0].strip()
        user_message = request.message
        if request.image_base64:
            user_message += "\n[El usuario adjuntó un GRÁFICO de trading. Analizá patrones, tendencia, indicadores visibles y dá tu recomendación.]"

        # Build messages array for DeepSeek
        ds_messages = [{"role": "system", "content": system_message}]
        if request.context:
            for msg in request.context[-8:]:
                ds_messages.append({"role": msg.role, "content": msg.content})
        ds_messages.append({"role": "user", "content": user_message})

        assistant_message = None
        model_used = None

        # Try DeepSeek first (no image support on free tier)
        total_chars = sum(len(m.get('content', '')) for m in ds_messages)
        logger.info(f"Chat context: {len(ds_messages)} messages, {total_chars} chars total")
        if not request.image_base64:
            result = _call_groq(ds_messages, temperature=0.75, max_tokens=600)
            if result:
                assistant_message = result
                model_used = f"groq-{getattr(Config, 'GROQ_MODEL_CHAT', Config.GROQ_MODEL)}"

        # Fallback to Ollama (using /api/chat with messages format)
        if not assistant_message:
            logger.warning("Groq failed, falling back to Ollama")
            import random
            ollama_model = 'llama3.1:8b'
            # Condensed system prompt for 8b model (4096 ctx limit)
            ollama_system = f"""Sos AIdan, trader profesional de scalping EUR/USD. Respondé en español argentino, directo y conciso.
{calendar_text}
{tech_text}
{smc_text}
{strategies_text}

REGLAS: Usá SOLO los datos de arriba. NO inventes eventos ni noticias. Si no tenés datos, decí que no hay info disponible. Respondé en 3-8 líneas."""
            ollama_messages = [
                {"role": "system", "content": ollama_system},
            ]
            if request.context:
                for msg in request.context[-6:]:
                    ollama_messages.append({"role": msg.role, "content": msg.content})
            ollama_messages.append({"role": "user", "content": user_message})

            ollama_payload = {
                'model': ollama_model,
                'messages': ollama_messages,
                'stream': False,
                'options': {
                    'temperature': 0.75, 'top_p': 0.9,
                    'num_predict': 500, 'num_ctx': 4096,
                    'seed': random.randint(1, 999999)
                }
            }

            # Image → vision model
            if request.image_base64:
                vision_model = _get_vision_model()
                if not vision_model:
                    return JSONResponse({
                        "status": "error",
                        "message": "No hay modelo de visión instalado. Ejecutá: ollama pull llava"
                    }, status_code=503)
                ollama_payload['model'] = vision_model
                ollama_messages[-1]["images"] = [request.image_base64]
                ollama_payload['options']['num_predict'] = 800
                logger.info(f"Using {vision_model} for image analysis")

            response = requests.post('http://localhost:11434/api/chat',
                json=ollama_payload, timeout=90)

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return JSONResponse({
                    "status": "error",
                    "message": "IA no disponible. Verificá Ollama o configurá DEEPSEEK_API_KEY."
                }, status_code=503)

            assistant_message = response.json().get('message', {}).get('content', '').strip()
            model_used = ollama_payload['model']

        return JSONResponse({
            "status": "success",
            "message": assistant_message,
            "model": model_used
        })

    except requests.exceptions.ConnectionError:
        logger.error("No se pudo conectar a Ollama")
        return JSONResponse({
            "status": "error",
            "message": "❌ Ollama no está corriendo. Inicia Ollama primero."
        }, status_code=503)
    except Exception as e:
        logger.error(f"Error en chat: {str(e)}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

# ── MT5 Endpoints ──

_mt5_executor = None

def _get_mt5():
    global _mt5_executor
    return _mt5_executor

def set_mt5_executor(executor):
    global _mt5_executor
    _mt5_executor = executor

@app.get("/mt5/status")
async def mt5_status():
    mt5 = _get_mt5()
    from src.common.db import get_mt5_config, get_mt5_daily_pnl
    config = get_mt5_config()

    if not mt5 or not mt5.connected:
        return JSONResponse({"status": "success", "data": {
            "connected": False, "enabled": False, "kill_switch": False,
            "account": None, "config": config, "daily_pnl": 0, "positions": 0,
        }})

    account = mt5.get_account_info()
    positions = mt5.check_positions()
    daily_pnl = get_mt5_daily_pnl()

    return JSONResponse({"status": "success", "data": {
        "connected": mt5.connected,
        "enabled": not mt5.kill_switch,
        "kill_switch": mt5.kill_switch,
        "account": account,
        "config": config,
        "daily_pnl": round(daily_pnl, 2),
        "positions": len(positions),
    }})

@app.get("/mt5/positions")
async def mt5_positions():
    mt5 = _get_mt5()
    if not mt5 or not mt5.connected:
        return JSONResponse({"status": "success", "data": []})
    positions = mt5.check_positions()
    return JSONResponse({"status": "success", "data": positions})

@app.post("/mt5/toggle")
async def mt5_toggle(request: Request):
    mt5 = _get_mt5()
    if not mt5:
        return JSONResponse({"status": "error", "message": "MT5 not initialized"}, status_code=400)
    body = await request.json()
    enabled = body.get("enabled", True)
    mt5.toggle(enabled)
    # When kill switch activated: evaluate strategies using real MT5 PnL
    if not enabled:
        try:
            import sqlite3, MetaTrader5 as _mt5_mod
            from src.common.db import DB_PATH, now_ar
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            # Find strategies with open MT5 positions
            cursor.execute("""
                SELECT id, mt5_ticket, direction, entry_price FROM auto_strategies
                WHERE mt5_status = 'filled' AND status IN ('active', 'expired')
            """)
            for sid, ticket, direction, entry_price in cursor.fetchall():
                pnl = 0.0
                close_price = 0.0
                try:
                    deals = _mt5_mod.history_deals_get(position=ticket)
                    if deals:
                        for d in deals:
                            if d.entry == 1:
                                pnl += d.profit + d.swap + d.commission
                                close_price = d.price
                except Exception:
                    pass
                result = 'auto_win' if pnl > 0 else 'auto_loss'
                conn.execute("""
                    UPDATE auto_strategies SET status=?, mt5_status='closed', mt5_pnl=?, mt5_close_price=?
                    WHERE id=?
                """, (result, round(pnl, 2), close_price, sid))
                logger.info(f"Kill switch eval: #{sid} → {result} PnL=${pnl:.2f}")
            # Cancel unexecuted active strategies (never reached MT5)
            cancelled = conn.execute("""
                UPDATE auto_strategies SET status = 'cancelled'
                WHERE status = 'active' AND (mt5_status IS NULL OR mt5_ticket IS NULL)
            """).rowcount
            if cancelled:
                logger.info(f"Kill switch: cancelled {cancelled} unexecuted strategies")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Kill switch strategy cleanup error: {e}")
    return JSONResponse({"status": "success", "enabled": not mt5.kill_switch})

@app.post("/mt5/connect")
async def mt5_connect(request: Request):
    mt5 = _get_mt5()
    if not mt5:
        from src.broker.mt5_executor import MT5Executor
        mt5 = MT5Executor(logger)
        set_mt5_executor(mt5)

    body = await request.json()
    account = body.get("account")
    password = body.get("password")
    server = body.get("server", "ICMarketsSC-Demo")

    if not account or not password:
        return JSONResponse({"status": "error", "message": "account and password required"}, status_code=400)

    try:
        success = mt5.reconnect(account, password, server)
        if success:
            # Save MT5 credentials for auto-reconnect on restart
            from src.common.db import save_last_session
            save_last_session(mt5_account=account, mt5_password=password, mt5_server=server)
            info = mt5.get_account_info()
            return JSONResponse({"status": "success", "data": info})
        else:
            # Try to get more details
            err_detail = ""
            try:
                import MetaTrader5 as _mt5
                err_detail = str(_mt5.last_error())
            except Exception:
                pass  # MT5 not available
            return JSONResponse({"status": "error", "message": f"Connection failed: {err_detail}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Exception: {e}"}, status_code=500)

@app.get("/mt5/diagnose")
async def mt5_diagnose():
    """Diagnostic endpoint — tests each MT5 step independently."""
    steps = []
    try:
        import MetaTrader5 as mt5mod
        steps.append({"step": "import", "ok": True})
    except Exception as e:
        steps.append({"step": "import", "ok": False, "error": str(e)})
        return JSONResponse({"status": "error", "steps": steps})

    # Find terminal path
    from src.broker.mt5_executor import _find_mt5_terminal
    term_path = _find_mt5_terminal()
    steps.append({"step": "find_terminal", "path": term_path or "NOT FOUND"})

    # Try initialize with path
    try:
        mt5mod.shutdown()  # clean state
        if term_path:
            init_ok = mt5mod.initialize(term_path)
            steps.append({"step": "initialize(path)", "ok": init_ok, "error": str(mt5mod.last_error())})
        else:
            init_ok = mt5mod.initialize()
            steps.append({"step": "initialize()", "ok": init_ok, "error": str(mt5mod.last_error())})
    except Exception as e:
        steps.append({"step": "initialize", "ok": False, "error": str(e)})
        return JSONResponse({"status": "error", "steps": steps})

    if not init_ok:
        return JSONResponse({"status": "error", "steps": steps})

    # Try login
    try:
        from src.common.config import Config
        acct = Config.MT5_ACCOUNT or 0
        pwd = Config.MT5_PASSWORD or ""
        srv = Config.MT5_SERVER or "ICMarketsSC-Demo"
        login_ok = mt5mod.login(acct, pwd, srv)
        steps.append({"step": "login", "ok": login_ok, "error": str(mt5mod.last_error()), "account": acct, "server": srv})
    except Exception as e:
        steps.append({"step": "login", "ok": False, "error": str(e)})

    if login_ok:
        info = mt5mod.account_info()
        if info:
            steps.append({"step": "account_info", "ok": True, "balance": info.balance, "login": info.login})
        mt5mod.shutdown()

    return JSONResponse({"status": "success" if login_ok else "error", "steps": steps})

@app.get("/mt5/config")
async def mt5_config_get():
    from src.common.db import get_mt5_config
    config = get_mt5_config()
    return JSONResponse({"status": "success", "data": config})

@app.post("/mt5/config")
async def mt5_config_update(request: Request):
    from src.common.db import update_mt5_config, get_mt5_config
    body = await request.json()
    update_mt5_config(
        risk_percent=body.get("risk_percent"),
        max_positions=body.get("max_positions"),
        max_lot=body.get("max_lot"),
    )
    return JSONResponse({"status": "success", "data": get_mt5_config()})

@app.get("/mt5/history")
async def mt5_history():
    from src.common.db import DB_PATH, now_ar, today_ar
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, direction, entry_price, mt5_ticket, mt5_lot, mt5_pnl,
               mt5_close_price, mt5_status, mt5_closed_at, news_title
        FROM auto_strategies
        WHERE mt5_status = 'closed' AND date(mt5_closed_at) = date(?)
        ORDER BY mt5_closed_at DESC
    """, (now_ar(),))
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "strategy_id": r[0], "direction": r[1], "entry_price": r[2],
            "ticket": r[3], "lot": r[4], "pnl": r[5],
            "close_price": r[6], "status": r[7], "closed_at": str(r[8]),
            "title": r[9]
        })
    return JSONResponse({"status": "success", "data": result})

# ===== LEARNING ENGINE ENDPOINTS =====

_learning_engine = None

def set_learning_engine(engine):
    global _learning_engine
    _learning_engine = engine

def _get_learner():
    global _learning_engine
    return _learning_engine

@app.get("/learning/status")
async def learning_status():
    learner = _get_learner()
    if not learner:
        from src.common.db import get_archive_stats
        stats = get_archive_stats()
        return JSONResponse({"status": "success", "data": {
            "mode": "offline", "market_open": False,
            "archive_total": stats['total'], "overall_wr": stats['win_rate'],
            "avg_pips": stats['avg_pips'], "total_pips": stats['total_pips'],
            "recent_insights_count": 0,
        }})
    return JSONResponse({"status": "success", "data": learner.get_status()})

@app.get("/learning/insights")
async def learning_insights():
    from src.common.db import get_learning_insights
    insights = get_learning_insights(30)
    return JSONResponse({"status": "success", "data": insights})

@app.get("/learning/metrics")
async def learning_metrics(period: str = 'daily', metric: str = None):
    from src.common.db import get_learning_metrics
    metrics = get_learning_metrics(metric_name=metric, period=period, limit=60)
    return JSONResponse({"status": "success", "data": metrics})

@app.get("/learning/report")
async def learning_report():
    from src.common.db import get_learning_insights
    reports = [i for i in get_learning_insights(50) if i.get('category') == 'report']
    latest = reports[0] if reports else None
    return JSONResponse({"status": "success", "data": latest})

@app.get("/learning/session-analysis")
async def learning_session_analysis():
    learner = _get_learner()
    if not learner:
        return JSONResponse({"status": "success", "data": {}})
    return JSONResponse({"status": "success", "data": learner.get_session_heatmap()})

@app.get("/learning/sl-tp-analysis")
async def learning_sl_tp_analysis():
    learner = _get_learner()
    if not learner:
        return JSONResponse({"status": "success", "data": {}})
    return JSONResponse({"status": "success", "data": learner.get_sl_tp_analysis()})

@app.get("/learning/archive")
async def learning_archive():
    from src.common.db import get_archive_stats
    stats = get_archive_stats()
    return JSONResponse({"status": "success", "data": stats})

# ===== AUTH ENDPOINTS =====

_logged_in_user = None

def get_logged_in_user():
    global _logged_in_user
    return _logged_in_user

# ── Auto-login from saved session on startup ──
def _try_auto_login():
    """Attempt to restore last login session from DB."""
    global _logged_in_user
    try:
        from src.common.db import get_last_session
        session = get_last_session()
        if session and session.get('last_username') and session.get('last_password_hash'):
            username = session['last_username']
            pwd_hash = session['last_password_hash']
            # Verify against Supabase using stored hash
            from src.cloud.shared_learning import authenticate_user_by_hash
            ok, msg, user_data = authenticate_user_by_hash(username, pwd_hash)
            if ok:
                _logged_in_user = {'username': username, 'id': user_data.get('id')}
                logger.info(f"Auto-login restored: {username}")
                # Re-enable shared learning
                from src.common.db import update_shared_learning_config
                update_shared_learning_config(instance_name=f"AIdan-{username}", enabled=True)
                learner = _get_learner()
                if learner:
                    shared = learner.get_shared_learning()
                    if shared:
                        shared.reload_config()
                        shared.register_instance()
                return True
            else:
                logger.info(f"Auto-login failed for {username}: {msg}")
    except Exception as e:
        logger.debug(f"Auto-login skipped: {e}")
    return False

# ── Auto-connect MT5 from saved credentials ──
def _try_auto_mt5():
    """Attempt to reconnect MT5 from saved credentials."""
    try:
        from src.common.db import get_last_session
        session = get_last_session()
        if session and session.get('mt5_account') and session.get('mt5_password'):
            mt5 = _get_mt5()
            if not mt5:
                from src.broker.mt5_executor import MT5Executor
                mt5 = MT5Executor(logger)
                set_mt5_executor(mt5)
            if not mt5.connected:
                success = mt5.reconnect(session['mt5_account'], session['mt5_password'], session.get('mt5_server', 'ICMarketsSC-Demo'))
                if success:
                    logger.info(f"Auto-connect MT5: account {session['mt5_account']}")
                    return True
                else:
                    logger.info(f"Auto-connect MT5 failed for account {session['mt5_account']}")
    except Exception as e:
        logger.debug(f"Auto-connect MT5 skipped: {e}")
    return False

@app.post("/auth/login")
async def auth_login(request: Request):
    global _logged_in_user
    body = await request.json()
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''
    if not username or not password:
        return JSONResponse({"status": "error", "message": "Usuario y clave requeridos"})
    try:
        from src.cloud.shared_learning import authenticate_user
        ok, msg, user_data = authenticate_user(username, password)
        if ok:
            logger.info(f"Login OK: {username}")
            _logged_in_user = {'username': username, 'id': user_data.get('id')}
            # Save session for auto-login on restart
            from src.common.db import save_last_session
            save_last_session(username=username, password_hash=user_data.get('password_hash', ''))
            # Auto-enable shared learning with this username
            from src.common.db import update_shared_learning_config
            update_shared_learning_config(instance_name=f"AIdan-{username}", enabled=True)
            # Reload shared learning config
            learner = _get_learner()
            if learner:
                shared = learner.get_shared_learning()
                if shared:
                    shared.reload_config()
                    shared.register_instance()
            return JSONResponse({"status": "success", "message": msg, "data": {"username": username}})
        else:
            logger.warning(f"Login FAILED: {username} — {msg}")
            return JSONResponse({"status": "error", "message": msg})
    except Exception as e:
        logger.error(f"Login ERROR: {username} — {e}")
        return JSONResponse({"status": "error", "message": f"Error: {str(e)}"})

@app.get("/auth/status")
async def auth_status():
    global _logged_in_user
    if _logged_in_user:
        mt5 = _get_mt5()
        mt5_connected = mt5.connected if mt5 else False
        return JSONResponse({"status": "success", "data": {"logged_in": True, "username": _logged_in_user['username'], "mt5_connected": mt5_connected}})
    return JSONResponse({"status": "success", "data": {"logged_in": False, "mt5_connected": False}})

@app.post("/auth/change-password")
async def auth_change_password(request: Request):
    global _logged_in_user
    if not _logged_in_user:
        return JSONResponse({"status": "error", "message": "No hay sesion activa"})
    body = await request.json()
    old_pwd = body.get('old_password', '')
    new_pwd = body.get('new_password', '')
    try:
        from src.cloud.shared_learning import change_password
        ok, msg = change_password(_logged_in_user['username'], old_pwd, new_pwd)
        return JSONResponse({"status": "success" if ok else "error", "message": msg})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

@app.post("/auth/logout")
async def auth_logout():
    """Logout: clear session but keep MT5 credentials saved."""
    global _logged_in_user
    _logged_in_user = None
    from src.common.db import clear_last_session
    clear_last_session()
    return JSONResponse({"status": "success", "message": "Sesion cerrada"})

@app.post("/auth/disconnect")
async def auth_disconnect():
    """Full disconnect: logout + disconnect MT5 + clear all saved state."""
    global _logged_in_user
    _logged_in_user = None
    # Disconnect MT5
    mt5 = _get_mt5()
    if mt5 and mt5.connected:
        mt5.disconnect()
        logger.info("MT5 disconnected by user")
    # Clear all saved session data
    from src.common.db import save_last_session, clear_last_session
    clear_last_session()
    save_last_session(mt5_account=0, mt5_password='', mt5_server='')
    return JSONResponse({"status": "success", "message": "Desconectado completamente"})

# ===== SHARED LEARNING ENDPOINTS =====

@app.get("/shared-learning/config")
async def shared_learning_config_get():
    from src.common.db import get_shared_learning_config
    config = get_shared_learning_config()
    # Mask the key for security (show first 8 + last 4 chars)
    key = config.get('supabase_key', '')
    if key and len(key) > 12:
        config['supabase_key_masked'] = key[:8] + '...' + key[-4:]
    else:
        config['supabase_key_masked'] = key
    return JSONResponse({"status": "success", "data": config})


@app.post("/shared-learning/config")
async def shared_learning_config_update(request: Request):
    from src.common.db import update_shared_learning_config, get_shared_learning_config
    body = await request.json()
    update_shared_learning_config(
        supabase_url=body.get("supabase_url"),
        supabase_key=body.get("supabase_key"),
        instance_name=body.get("instance_name"),
        enabled=body.get("enabled"),
    )
    # Reload config in shared learning instance
    learner = _get_learner()
    if learner:
        shared = learner.get_shared_learning()
        if shared:
            shared.reload_config()
            # Test connection if enabling
            if body.get("enabled"):
                ok, msg = shared.test_connection()
                if ok:
                    shared.register_instance()
                config = get_shared_learning_config()
                return JSONResponse({"status": "success", "data": config, "connection": {"ok": ok, "message": msg}})
    config = get_shared_learning_config()
    return JSONResponse({"status": "success", "data": config})


@app.get("/shared-learning/status")
async def shared_learning_status():
    learner = _get_learner()
    if learner:
        shared = learner.get_shared_learning()
        if shared:
            return JSONResponse({"status": "success", "data": shared.get_status()})
    # Fallback: return config-only status
    from src.common.db import get_shared_learning_config
    config = get_shared_learning_config()
    return JSONResponse({"status": "success", "data": {
        "enabled": config.get('enabled', False),
        "configured": bool(config.get('supabase_url')),
        "instance_id": config.get('instance_id', ''),
        "instance_name": config.get('instance_name', ''),
        "last_sync": config.get('last_sync', ''),
        "tables_ok": False,
        "trades_synced": 0,
        "trades_remote": 0,
    }})


@app.post("/shared-learning/sync")
async def shared_learning_sync():
    learner = _get_learner()
    if not learner:
        return JSONResponse({"status": "error", "message": "Learning engine not available"})
    shared = learner.get_shared_learning()
    if not shared or not shared.enabled:
        return JSONResponse({"status": "error", "message": "Shared learning not enabled"})
    try:
        synced = shared.sync_trades()
        return JSONResponse({"status": "success", "data": {"trades_synced": synced}})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})


@app.post("/shared-learning/test-connection")
async def shared_learning_test():
    learner = _get_learner()
    if learner:
        shared = learner.get_shared_learning()
        if shared:
            shared.reload_config()
            ok, msg = shared.test_connection()
            return JSONResponse({"status": "success", "data": {"ok": ok, "message": msg}})
    return JSONResponse({"status": "error", "message": "Shared learning not initialized"})


@app.post("/shared-learning/setup-tables")
async def shared_learning_setup_tables():
    learner = _get_learner()
    if learner:
        shared = learner.get_shared_learning()
        if shared:
            shared.reload_config()
            ok, msg = shared.setup_tables()
            return JSONResponse({"status": "success", "data": {"ok": ok, "message": msg}})
    return JSONResponse({"status": "error", "message": "Shared learning not initialized"})


@app.get("/shared-learning/sql-script")
async def shared_learning_sql_script():
    """Return the SQL script for creating Supabase tables (for manual setup)."""
    sql = """-- AIdan Shared Learning Tables
-- Run this in Supabase SQL Editor (https://supabase.com/dashboard → SQL Editor)

CREATE TABLE IF NOT EXISTS instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_sync TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS shared_trades (
    id BIGSERIAL PRIMARY KEY,
    instance_id UUID REFERENCES instances(id),
    local_strategy_id INTEGER,
    direction TEXT,
    result TEXT,
    pips REAL,
    sl_pips REAL,
    tp_pips REAL,
    sl_hit BOOLEAN,
    tp_hit BOOLEAN,
    confidence REAL,
    trigger_type TEXT,
    setup_type TEXT,
    session TEXT,
    hour_utc INTEGER,
    day_of_week INTEGER,
    htf_bias TEXT,
    market_trend TEXT,
    trend_strength REAL,
    rsi_at_entry REAL,
    volatility REAL,
    news_category TEXT,
    mt5_pnl REAL,
    created_at TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(instance_id, local_strategy_id)
);

CREATE TABLE IF NOT EXISTS shared_insights (
    id BIGSERIAL PRIMARY KEY,
    category TEXT,
    insight TEXT,
    data JSONB,
    min_trades INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);"""
    return JSONResponse({"status": "success", "data": {"sql": sql}})


# Run with: uvicorn src.admin.main:app --host 0.0.0.0 --port 8000
