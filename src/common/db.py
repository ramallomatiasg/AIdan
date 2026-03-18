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

    # Signal results table for win-rate tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_results (
            id INTEGER PRIMARY KEY,
            alert_id INTEGER UNIQUE,
            result TEXT CHECK(result IN ('win', 'loss', 'skip')),
            recorded_at TIMESTAMP,
            FOREIGN KEY(alert_id) REFERENCES alerts(id)
        )
    """)

    # Strategies table for strategy creator
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            config TEXT,
            created_at TIMESTAMP
        )
    """)

    # Auto-generated strategies from high-impact news
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_strategies (
            id INTEGER PRIMARY KEY,
            alert_id INTEGER UNIQUE,
            news_title TEXT,
            direction TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            confidence REAL,
            impact_score INTEGER,
            expiry_minutes INTEGER DEFAULT 5,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY(alert_id) REFERENCES alerts(id)
        )
    """)

    # Strategy voting results
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategy_results (
            id INTEGER PRIMARY KEY,
            strategy_id INTEGER UNIQUE,
            result TEXT CHECK(result IN ('win', 'loss', 'skip')),
            recorded_at TIMESTAMP,
            FOREIGN KEY(strategy_id) REFERENCES auto_strategies(id)
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
    
    # Traer alertas MEDIA y ALTA (score >= 50)
    cursor.execute("""
        SELECT a.id, a.impact_score, a.alert_level, a.alert_sent_at,
               n.title, n.url, a.explanation, a.eur_usd_impact, a.market_implications,
               a.analysis_method, a.should_operate, a.direction, a.confidence
        FROM alerts a
        JOIN news n ON a.news_id = n.id
        WHERE a.impact_score >= 50
          AND date(a.alert_sent_at) = date('now')
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

def record_signal_result(alert_id, result):
    """Record whether a trading signal was correct"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO signal_results (alert_id, result, recorded_at)
            VALUES (?, ?, ?)
        """, (alert_id, result, datetime.utcnow()))
        conn.commit()
    finally:
        conn.close()

def get_performance_stats():
    """Get win/loss/skip statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM signal_results WHERE result = 'win'")
    wins = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM signal_results WHERE result = 'loss'")
    losses = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM signal_results WHERE result = 'skip'")
    skips = cursor.fetchone()[0]
    conn.close()
    total_decided = wins + losses
    win_rate = (wins / total_decided * 100) if total_decided > 0 else 0
    return {
        'wins': wins,
        'losses': losses,
        'skips': skips,
        'total': total_decided,
        'win_rate': round(win_rate, 1)
    }

def cleanup_old_data(hours=72):
    """Remove data older than specified hours"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff_date = datetime.utcnow() - timedelta(hours=hours)

    cursor.execute("DELETE FROM alerts WHERE alert_sent_at < ?", (cutoff_date,))
    cursor.execute("DELETE FROM news WHERE fetched_at < ?", (cutoff_date,))
    cursor.execute("DELETE FROM strategy_results WHERE strategy_id NOT IN (SELECT id FROM auto_strategies)")
    cursor.execute("DELETE FROM auto_strategies WHERE created_at < ?", (cutoff_date,))

    conn.commit()
    conn.close()

# ── Auto-Strategy functions ──

def add_auto_strategy(alert_id, news_title, direction, entry_price, stop_loss, take_profit, confidence, impact_score, expiry_minutes=5):
    """Add auto-generated strategy, enforcing max 6 cap"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Enforce 6-strategy cap
        cursor.execute("SELECT COUNT(*) FROM auto_strategies")
        count = cursor.fetchone()[0]
        if count >= 6:
            # Delete oldest + their votes
            cursor.execute("""
                DELETE FROM strategy_results WHERE strategy_id IN (
                    SELECT id FROM auto_strategies ORDER BY created_at ASC LIMIT ?
                )
            """, (count - 5,))
            cursor.execute("""
                DELETE FROM auto_strategies WHERE id IN (
                    SELECT id FROM auto_strategies ORDER BY created_at ASC LIMIT ?
                )
            """, (count - 5,))

        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=expiry_minutes)
        cursor.execute("""
            INSERT INTO auto_strategies
            (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
             confidence, impact_score, expiry_minutes, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """, (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
              confidence, impact_score, expiry_minutes, now, expires_at))
        conn.commit()
        return cursor.lastrowid
    except Exception:
        return None
    finally:
        conn.close()

def get_active_strategies(limit=6):
    """Get recent auto-strategies with vote status"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Expire old ones first
    cursor.execute("""
        UPDATE auto_strategies SET status = 'expired'
        WHERE expires_at < ? AND status = 'active'
    """, (datetime.utcnow(),))
    conn.commit()

    cursor.execute("""
        SELECT s.id, s.alert_id, s.news_title, s.direction, s.entry_price,
               s.stop_loss, s.take_profit, s.confidence, s.impact_score,
               s.expiry_minutes, s.status, s.created_at, s.expires_at,
               sr.result
        FROM auto_strategies s
        LEFT JOIN strategy_results sr ON s.id = sr.strategy_id
        ORDER BY s.created_at DESC
        LIMIT ?
    """, (limit,))

    results = cursor.fetchall()
    conn.close()
    return results

def record_strategy_result(strategy_id, result):
    """Record win/loss/skip for an auto-strategy"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO strategy_results (strategy_id, result, recorded_at)
            VALUES (?, ?, ?)
        """, (strategy_id, result, datetime.utcnow()))
        # Update strategy status
        cursor.execute("UPDATE auto_strategies SET status = 'voted' WHERE id = ?", (strategy_id,))
        conn.commit()
    finally:
        conn.close()

def get_strategy_performance():
    """Get win/loss/skip stats for auto-strategies"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT result, COUNT(*) FROM strategy_results GROUP BY result")
    rows = cursor.fetchall()
    conn.close()
    stats = {'wins': 0, 'losses': 0, 'skips': 0}
    for result, count in rows:
        if result == 'win': stats['wins'] = count
        elif result == 'loss': stats['losses'] = count
        elif result == 'skip': stats['skips'] = count
    total = stats['wins'] + stats['losses']
    stats['total'] = total
    stats['win_rate'] = round((stats['wins'] / total * 100) if total > 0 else 0, 1)
    return stats

def get_news_fetch_time(news_id):
    """Get when a news item was fetched"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT fetched_at FROM news WHERE id = ?", (news_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None
