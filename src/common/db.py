import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = "state/financial_news.db"

def init_db():
    """Initialize database with required tables"""
    os.makedirs("state", exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # News table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY,
            url TEXT UNIQUE,
            title TEXT,
            summary TEXT,
            language TEXT,
            entities TEXT,
            tags TEXT,
            fetched_at TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)
    
    # Alerts table - UPDATED con explicación, EUR/USD impact, y should_operate
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY,
            news_id INTEGER,
            impact_score INTEGER,
            alert_level TEXT,
            explanation TEXT,
            eur_usd_impact TEXT,
            market_implications TEXT,
            analysis_method TEXT,
            should_operate INTEGER DEFAULT 0,
            direction TEXT,
            confidence REAL,
            alert_sent_at TIMESTAMP,
            telegram_message_id INTEGER,
            FOREIGN KEY(news_id) REFERENCES news(id)
        )
    """)
    
    # Processing errors table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY,
            error_type TEXT,
            error_message TEXT,
            occurred_at TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def add_news(url, title, summary, language, entities, tags):
    """Add news to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO news (url, title, summary, language, entities, tags, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (url, title, summary, language, entities, tags, datetime.utcnow()))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None  # Duplicate URL
    finally:
        conn.close()

def get_unprocessed_news():
    """Get news that hasn't been analyzed yet"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, url, title, summary, entities, tags 
        FROM news 
        WHERE processed_at IS NULL 
        ORDER BY fetched_at DESC
    """)
    
    results = cursor.fetchall()
    conn.close()
    return results

def mark_news_processed(news_id):
    """Mark news as processed"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE news SET processed_at = ? WHERE id = ?", 
                   (datetime.utcnow(), news_id))
    conn.commit()
    conn.close()

def add_alert(news_id, impact_score, alert_level, explanation, eur_usd_impact, market_implications, analysis_method='keywords', should_operate=False, direction='NEUTRAL', confidence=50):
    """Log an alert with detailed information including AI decision"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alerts (news_id, impact_score, alert_level, explanation, eur_usd_impact, market_implications, analysis_method, should_operate, direction, confidence, alert_sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (news_id, impact_score, alert_level, explanation, eur_usd_impact, market_implications, analysis_method, 1 if should_operate else 0, direction, confidence, datetime.utcnow()))
    conn.commit()
    conn.close()

def get_recent_alerts(limit=50):
    """Get recent alerts - only AI-analyzed with ALTA level"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Solo traer alertas ALTA analizadas por IA (Ollama)
    cursor.execute("""
        SELECT a.id, a.impact_score, a.alert_level, a.alert_sent_at, 
               n.title, n.url, a.explanation, a.eur_usd_impact, a.market_implications, 
               a.analysis_method, a.should_operate, a.direction, a.confidence
        FROM alerts a
        JOIN news n ON a.news_id = n.id
        WHERE a.alert_level = 'ALTA' AND a.analysis_method = 'ollama'
        ORDER BY a.alert_sent_at DESC
        LIMIT ?
    """, (min(limit, 20),))  # Max 20
    
    results = cursor.fetchall()
    conn.close()
    return results

def get_stats():
    """Get system statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM news")
    total_news = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM alerts")
    total_alerts = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM news 
        WHERE fetched_at > datetime('now', '-1 hour')
    """)
    news_last_hour = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_news": total_news,
        "total_alerts": total_alerts,
        "news_last_hour": news_last_hour
    }

def cleanup_old_data(hours=72):
    """Remove data older than specified hours"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cutoff_date = datetime.utcnow() - timedelta(hours=hours)
    
    cursor.execute("DELETE FROM alerts WHERE alert_sent_at < ?", (cutoff_date,))
    cursor.execute("DELETE FROM news WHERE fetched_at < ?", (cutoff_date,))
    
    conn.commit()
    conn.close()
