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
from src.common.db import init_db, get_stats, get_recent_alerts

logger = setup_logging(__name__, Config.LOG_LEVEL)

app = FastAPI(title="Financial News Monitor API", version="1.0.0")

# Configurar CORS para permitir peticiones desde PyWebView y navegadores
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todas las origins (localhost, file://, etc)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Detectar si estamos en ejecutable o desarrollo
if getattr(sys, 'frozen', False):
    # Estamos en ejecutable PyInstaller
    base_path = sys._MEIPASS
else:
    # Estamos en desarrollo
    base_path = os.path.join(os.path.dirname(__file__), '../..')

# Montar carpeta static para servir archivos estáticos (imágenes, etc)
static_path = os.path.join(base_path, 'static')
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Servir dashboard en la raíz
@app.get("/")
async def root():
    """Servir dashboard multi-theme con chat"""
    # Primero intentar el nuevo dashboard multi-theme
    dashboard_path = os.path.join(base_path, 'dashboard_multi_theme.html')
    logger.info(f"Intentando servir: {dashboard_path}")
    logger.info(f"Existe: {os.path.exists(dashboard_path)}")
    if os.path.exists(dashboard_path):
        logger.info("✓ Sirviendo dashboard_multi_theme.html")
        return FileResponse(dashboard_path, media_type="text/html")
    # Fallback al dashboard retro
    dashboard_path = os.path.join(base_path, 'dashboard_retro.html')
    if os.path.exists(dashboard_path):
        logger.info("⚠ Sirviendo dashboard_retro.html (fallback)")
        return FileResponse(dashboard_path, media_type="text/html")
    # Fallback al dashboard original
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
    """Get recent HIGH impact alerts with EUR/USD analysis (max 20) - AI only"""
    try:
        alerts = get_recent_alerts(min(limit, 20))  # Max 20
        
        formatted_alerts = []
        for alert_id, impact_score, alert_level, sent_at, title, url, explanation, eur_usd_impact, market_implications, analysis_method, should_operate, direction, confidence in alerts:
            formatted_alerts.append({
                "id": alert_id,
                "impact_score": impact_score,
                "level": alert_level,
                "sent_at": sent_at,
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

# Modelos para chat con Ollama
class ChatMessage(BaseModel):
    role: str  # 'user' o 'assistant'
    content: str

class ChatRequest(BaseModel):
    message: str
    context: Optional[List[ChatMessage]] = []
    image_base64: Optional[str] = None  # Para soporte de imágenes

@app.get("/chat-context")
async def get_chat_context():
    """Obtener contexto actual del sistema para el chat"""
    try:
        from src.common.db import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Últimas 5 alertas
        cursor.execute("""
            SELECT impact_score, level, title, explanation, eur_usd_impact
            FROM alerts
            ORDER BY sent_at DESC
            LIMIT 5
        """)
        alerts = cursor.fetchall()
        
        # Últimas 10 noticias
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
    """Chat con Ollama manteniendo contexto de conversación"""
    try:
        # Obtener contexto actual del sistema
        from src.common.db import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Últimas 3 alertas - CORREGIDO: usando JOIN con news
        cursor.execute("""
            SELECT a.impact_score, a.alert_level, n.title, a.eur_usd_impact
            FROM alerts a
            JOIN news n ON a.news_id = n.id
            ORDER BY a.alert_sent_at DESC
            LIMIT 3
        """)
        alerts_data = cursor.fetchall()
        
        # Stats generales
        cursor.execute("SELECT COUNT(*) FROM news")
        total_news = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM alerts")
        total_alerts = cursor.fetchone()[0]
        
        conn.close()
        
        # Formatear alertas para el contexto
        alerts_text = ""
        if alerts_data:
            alerts_text = "\n\nÚLTIMAS ALERTAS DEL SISTEMA:\n"
            for score, level, title, eur_impact in alerts_data:
                alerts_text += f"- [{level}] {title[:80]}... (Score: {score}, EUR/USD: {eur_impact[:50] if eur_impact else 'N/A'})\n"
        
        # Construir el prompt con contexto completo
        conversation_history = ""
        if request.context:
            # Incluir toda la conversación previa
            for msg in request.context:
                role_label = "Usuario" if msg.role == "user" else "AIdan"
                conversation_history += f"{role_label}: {msg.content}\n"
        
        # Agregar el nuevo mensaje del usuario
        conversation_history += f"Usuario: {request.message}\n"
        
        # Agregar contexto de imagen si existe
        if request.image_base64:
            conversation_history += "[Usuario adjuntó una imagen/gráfico para análisis]\n"
        
        # Prompt mejorado: NO saludos ni presentaciones si ya hay contexto
        system_context = f"""Sos AIdan. Ya estás en una conversación activa.

DATOS DEL SISTEMA:
- Noticias totales: {total_news}
- Alertas generadas: {total_alerts}{alerts_text}

REGLAS ABSOLUTAS:
1. NO SALUDAR. NO presentarte otra vez si ya hay mensajes previos.
2. Español rioplatense directo.
3. Respuestas CORTAS: 2-3 líneas máximo.
4. Números concretos: pips, %, probabilidades.
5. **negrita** para acciones clave (CALL, PUT, OPERAR).
6. *cursiva* para advertencias.
7. Terminar apenas des la info. Sin despedidas ni preguntas de cierre.

CONVERSACIÓN:
{conversation_history}

AIdan:"""
        
        # Construir payload para Ollama
        ollama_payload = {
            'model': 'llama3.1:8b',
            'prompt': system_context,
            'stream': False,
            'options': {
                'temperature': 0.7,
                'top_p': 0.9,
                'num_predict': 150
            }
        }
        
        # Si hay imagen, agregar soporte para modelos con visión (llava)
        if request.image_base64:
            ollama_payload['model'] = 'llava:latest'
            ollama_payload['images'] = [request.image_base64]
            ollama_payload['options']['num_predict'] = 200  # Más tokens para análisis de imágenes
            logger.info(f"Using llava model for image analysis")
        
        # Llamar a Ollama
        response = requests.post(
            'http://localhost:11434/api/generate',
            json=ollama_payload,
            timeout=45
        )
        
        if response.status_code != 200:
            logger.error(f"Ollama error: {response.status_code}")
            return JSONResponse({
                "status": "error",
                "message": "Ollama no disponible. Asegúrate de que esté corriendo."
            }, status_code=503)
        
        result = response.json()
        assistant_message = result.get('response', '').strip()
        
        return JSONResponse({
            "status": "success",
            "message": assistant_message,
            "model": "llama3.1:8b"
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
