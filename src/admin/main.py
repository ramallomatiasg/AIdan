import sys
import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.common.config import Config
from src.common.logging_setup import setup_logging
from src.common.db import init_db, get_stats, get_recent_alerts

logger = setup_logging(__name__, Config.LOG_LEVEL)

app = FastAPI(title="Financial News Monitor API", version="1.0.0")

# Montar carpeta static para servir archivos estáticos (imágenes, etc)
static_path = os.path.join(os.path.dirname(__file__), '../../static')
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Servir dashboard en la raíz
@app.get("/")
async def root():
    """Servir dashboard.html"""
    dashboard_path = os.path.join(os.path.dirname(__file__), '../../dashboard_retro.html')
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    # Fallback al dashboard original
    dashboard_path = os.path.join(os.path.dirname(__file__), '../../dashboard.html')
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    return {"message": "Dashboard not found"}

# Servir página About
@app.get("/about")
async def about():
    """Servir página sobre el desarrollador"""
    about_path = os.path.join(os.path.dirname(__file__), '../../about.html')
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
    return JSONResponse({
        "status": "healthy",
        "timestamp": str(os.popen("python -c \"from datetime import datetime; print(datetime.utcnow().isoformat())\"").read().strip() or "2026-02-25T00:00:00")
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
    """Get recent HIGH impact alerts with EUR/USD analysis (max 20)"""
    try:
        alerts = get_recent_alerts(min(limit, 20))  # Max 20
        
        formatted_alerts = []
        for alert_id, impact_score, alert_level, sent_at, title, url, explanation, eur_usd_impact, market_implications in alerts:
            formatted_alerts.append({
                "id": alert_id,
                "impact_score": impact_score,
                "level": alert_level,
                "sent_at": sent_at,
                "title": title,
                "url": url,
                "explanation": explanation,
                "eur_usd_impact": eur_usd_impact,
                "market_implications": market_implications
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
                "fetched_at": fetched_at,
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

# Run with: uvicorn src.admin.main:app --host 0.0.0.0 --port 8000
