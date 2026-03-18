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
                           get_strategy_performance)
from src.analyzer.technical import TechnicalAnalyzer

logger = setup_logging(__name__, Config.LOG_LEVEL)

app = FastAPI(title="Financial News Monitor API", version="1.0.0")

# UTC ISO helper — SQLite stores "2026-03-17 13:44:18.439" without timezone
def _utc_iso(ts_str):
    """Convert SQLite timestamp to UTC ISO 8601 for correct JS Date() parsing."""
    if not ts_str:
        return ts_str
    return ts_str.replace(' ', 'T').rstrip('Z') + 'Z'

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

# Configurar CORS para permitir peticiones desde PyWebView y navegadores
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
@app.get("/")
async def root():
    """Servir dashboard multi-theme con chat"""
    dashboard_path = os.path.join(base_path, 'dashboard_multi_theme.html')
    logger.info(f"Intentando servir: {dashboard_path}")
    logger.info(f"Existe: {os.path.exists(dashboard_path)}")
    if os.path.exists(dashboard_path):
        logger.info("✓ Sirviendo dashboard_multi_theme.html")
        return FileResponse(dashboard_path, media_type="text/html")
    dashboard_path = os.path.join(base_path, 'dashboard_retro.html')
    if os.path.exists(dashboard_path):
        logger.info("⚠ Sirviendo dashboard_retro.html (fallback)")
        return FileResponse(dashboard_path, media_type="text/html")
    dashboard_path = os.path.join(os.path.dirname(__file__), '../../dashboard.html')
    if os.path.exists(dashboard_path):
        logger.info("⚠ Sirviendo dashboard.html (fallback)")
        return FileResponse(dashboard_path, media_type="text/html")
    logger.error("❌ No se encontró ningún dashboard")
    return {"message": "Dashboard not found"}

# Servir página About
@app.get("/about")
async def about():
    """Servir página sobre el desarrollador"""
    about_path = os.path.join(base_path, 'about.html')
    if os.path.exists(about_path):
        return FileResponse(about_path, media_type="text/html")
    return {"message": "About page not found"}

@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    logger.info("API starting up...")
    init_db()

@app.get("/health")
async def health():
    """Health check endpoint"""
    from datetime import datetime
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    })

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
        for alert_id, impact_score, alert_level, sent_at, title, url, explanation, eur_usd_impact, market_implications, analysis_method, should_operate, direction, confidence in alerts:
            formatted_alerts.append({
                "id": alert_id,
                "impact_score": impact_score,
                "level": alert_level,
                "sent_at": _utc_iso(sent_at),
                "title": title,
                "url": url,
                "explanation": explanation,
                "eur_usd_impact": eur_usd_impact,
                "market_implications": market_implications,
                "analysis_method": analysis_method or 'keywords',
                "should_operate": bool(should_operate),
                "direction": direction or 'NEUTRAL',
                "confidence": confidence or 50
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

        cursor.execute("""
            SELECT id, title, url, fetched_at, language, tags
            FROM news
            ORDER BY fetched_at DESC
            LIMIT ?
        """, (limit,))

        news_items = []
        for news_id, title, url, fetched_at, language, tags in cursor.fetchall():
            news_items.append({
                "id": news_id,
                "title": title,
                "url": url,
                "fetched_at": _utc_iso(fetched_at),
                "language": language,
                "tags": tags
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

@app.post("/signal-result")
async def post_signal_result(request: SignalResultRequest):
    """Record whether a trading signal was correct"""
    if request.result not in ('win', 'loss', 'skip'):
        return JSONResponse({"status": "error", "message": "Invalid result. Use: win, loss, skip"}, status_code=400)
    try:
        record_signal_result(request.alert_id, request.result)
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
        """, (strategy.name, json.dumps(strategy.dict()), datetime.utcnow()))
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
        cursor.execute("SELECT id, name, config, created_at FROM strategies ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        strategies = [{"id": r[0], "name": r[1], "config": json.loads(r[2]), "created_at": _utc_iso(r[3])} for r in rows]
        return JSONResponse({"status": "success", "data": strategies})
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

@app.get("/market-state")
async def get_market_state():
    """Get current EUR/USD technical analysis state"""
    try:
        tech = get_tech()
        state = tech.get_market_state()
        # Remove internal cache timestamp
        state.pop('_ts', None)
        return JSONResponse({"status": "success", "data": state})
    except Exception as e:
        logger.error(f"Error getting market state: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ── Auto-Strategy Endpoints ──

@app.get("/auto-strategies")
async def list_auto_strategies():
    """Get active auto-generated strategies (max 6)"""
    try:
        rows = get_active_strategies(6)
        strategies = []
        for r in rows:
            strategies.append({
                "id": r[0], "alert_id": r[1], "news_title": r[2],
                "direction": r[3], "entry_price": r[4],
                "stop_loss": r[5], "take_profit": r[6],
                "confidence": r[7], "impact_score": r[8],
                "expiry_minutes": r[9], "status": r[10],
                "created_at": _utc_iso(str(r[11])) if r[11] else None,
                "expires_at": _utc_iso(str(r[12])) if r[12] else None,
                "result": r[13]
            })
        return JSONResponse({"status": "success", "data": strategies, "count": len(strategies)})
    except Exception as e:
        logger.error(f"Error listing auto-strategies: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

class StrategyResultRequest(BaseModel):
    strategy_id: int
    result: str  # 'win', 'loss', 'skip'

@app.post("/strategy-result")
async def post_strategy_result(req: StrategyResultRequest):
    """Record win/loss/skip for an auto-strategy"""
    if req.result not in ('win', 'loss', 'skip'):
        return JSONResponse({"status": "error", "message": "Invalid result"}, status_code=400)
    record_strategy_result(req.strategy_id, req.result)
    return JSONResponse({"status": "success"})

@app.get("/strategy-performance")
async def strategy_perf():
    """Get win/loss stats for auto-strategies"""
    return JSONResponse({"status": "success", "data": get_strategy_performance()})

@app.get("/candles")
async def get_candles():
    """Get EUR/USD candle data for Lightweight Charts"""
    try:
        tech = get_tech()
        candles = tech._fetch_from_yahoo()
        if not candles:
            return JSONResponse({"status": "error", "message": "No candle data"}, status_code=503)
        # Convert to Lightweight Charts format: [{time (unix), open, high, low, close}]
        lw_candles = []
        for c in candles:
            ts = c.get('datetime', c.get('timestamp', 0))
            try:
                ts_int = int(float(ts))
            except (ValueError, TypeError):
                continue
            lw_candles.append({
                "time": ts_int,
                "open": round(c['open'], 5), "high": round(c['high'], 5),
                "low": round(c['low'], 5), "close": round(c['close'], 5)
            })
        return JSONResponse({"status": "success", "data": lw_candles})
    except Exception as e:
        logger.error(f"Error fetching candles: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# Modelos para chat con Ollama
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    context: Optional[List[ChatMessage]] = []
    image_base64: Optional[str] = None

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

        # Detailed win/loss patterns for AI learning
        cursor.execute("""
            SELECT sr.result, a.direction, a.confidence, a.impact_score, n.title
            FROM signal_results sr
            JOIN alerts a ON sr.alert_id = a.id
            JOIN news n ON a.news_id = n.id
            WHERE sr.result IN ('win', 'loss')
            ORDER BY sr.recorded_at DESC
            LIMIT 20
        """)
        pattern_rows = cursor.fetchall()
        patterns_text = ""
        if pattern_rows:
            win_p = [r for r in pattern_rows if r[0] == 'win']
            loss_p = [r for r in pattern_rows if r[0] == 'loss']
            patterns_text = "\n📊 PATRONES DE OPERACIONES DEL TRADER:\n"
            if win_p:
                avg_conf_w = sum(r[2] for r in win_p) / len(win_p)
                avg_imp_w = sum(r[3] for r in win_p) / len(win_p)
                dirs_w = set(r[1] for r in win_p)
                patterns_text += f"  Wins ({len(win_p)}): Conf promedio {avg_conf_w:.0f}%, Impact promedio {avg_imp_w:.0f}, Dirs: {','.join(dirs_w)}\n"
            if loss_p:
                avg_conf_l = sum(r[2] for r in loss_p) / len(loss_p)
                avg_imp_l = sum(r[3] for r in loss_p) / len(loss_p)
                dirs_l = set(r[1] for r in loss_p)
                patterns_text += f"  Losses ({len(loss_p)}): Conf promedio {avg_conf_l:.0f}%, Impact promedio {avg_imp_l:.0f}, Dirs: {','.join(dirs_l)}\n"
            patterns_text += "  Usá estos patrones para calibrar tus recomendaciones.\n"

        conn.close()

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
- Rango promedio: {market.get('avg_range_pips', 0):.1f} pips
IMPORTANTE: Usá estos datos técnicos para CONTRASTAR con las noticias. Si las noticias dicen CALL pero la tendencia es bajista fuerte, mencionalo."""
        except Exception as e:
            logger.warning(f"Tech context for chat failed: {e}")

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
- Alertas generadas: {total_alerts}{perf_text}{patterns_text}{tech_text}{alerts_text}{news_text}

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
10. Si el usuario tiene mal win-rate, sugerí ajustes de estrategia
11. Números concretos siempre: pips, %, probabilidades, minutos
12. NO saludar si ya hay conversación previa
13. Terminá apenas des la info. Sin despedidas ni "¿algo más?"

ESTRATEGIA SCALPING QUE RECOMENDÁS:
- Entrada: Confirmación con 2+ señales (ej: pin bar + RSI sobrecompra + resistencia)
- Expiración: 2-3 min para momentum fuerte, 5 min para confirmación
- NO operar en los primeros 5 min de una noticia de alto impacto (spread se ensancha)
- Esperar el pullback post-noticia, no entrar en el spike
- Mejor momento: 15:00-17:00 CET (overlap Londres-NY, máximo volumen)
- Evitar: Viernes después de 18:00, domingo apertura, feriados USA/EU

CONVERSACIÓN:
{conversation_history}

AIdan:"""

        # Construir payload para Ollama
        ollama_payload = {
            'model': 'llama3.1:8b',
            'prompt': system_context,
            'stream': False,
            'options': {
                'temperature': 0.6,
                'top_p': 0.9,
                'num_predict': 500
            }
        }

        # Si hay imagen, usar modelo con visión
        if request.image_base64:
            vision_model = _get_vision_model()
            if not vision_model:
                return JSONResponse({
                    "status": "error",
                    "message": "No hay modelo de visión instalado. Ejecutá en terminal:\n  ollama pull llava\nY volvé a intentar."
                }, status_code=503)
            ollama_payload['model'] = vision_model
            ollama_payload['images'] = [request.image_base64]
            ollama_payload['options']['num_predict'] = 800
            logger.info(f"Using {vision_model} for image analysis")

        # Llamar a Ollama
        response = requests.post(
            'http://localhost:11434/api/generate',
            json=ollama_payload,
            timeout=90
        )

        if response.status_code != 200:
            logger.error(f"Ollama error: {response.status_code}")
            error_msg = "Ollama no disponible. Asegurate de que esté corriendo."
            if request.image_base64:
                error_msg = f"El modelo de visión no pudo procesar la imagen. Probá sin imagen o instalá otro modelo con: ollama pull llava"
            return JSONResponse({
                "status": "error",
                "message": error_msg
            }, status_code=503)

        result = response.json()
        assistant_message = result.get('response', '').strip()

        return JSONResponse({
            "status": "success",
            "message": assistant_message,
            "model": ollama_payload['model']
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

# Run with: uvicorn src.admin.main:app --host 0.0.0.0 --port 8000
