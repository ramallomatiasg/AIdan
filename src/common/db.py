import sqlite3
import os
from datetime import datetime, timedelta, timezone

# Buenos Aires timezone (UTC-3)
TZ_AR = timezone(timedelta(hours=-3))

def now_ar():
    """Current time in Buenos Aires (UTC-3)"""
    return datetime.now(TZ_AR).replace(tzinfo=None)

def today_ar():
    """Today's date string in Buenos Aires"""
    return datetime.now(TZ_AR).strftime('%Y-%m-%d')

def _get_base_dir():
    """Always use %APPDATA%/AIdan/ — single DB for both dev and exe."""
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        base = os.path.join(appdata, 'AIdan')
        os.makedirs(base, exist_ok=True)
        return base
    # Fallback: project root
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sys
_BASE_DIR = _get_base_dir()
DB_PATH = os.path.join(_BASE_DIR, "state", "financial_news.db")

def init_db():
    """Initialize database with required tables"""
    os.makedirs(os.path.join(_BASE_DIR, "state"), exist_ok=True)
    
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
            published_at TIMESTAMP,
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
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )
    """)

    # Auto-generated strategies from high-impact news or market structure
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_strategies (
            id INTEGER PRIMARY KEY,
            alert_id INTEGER,
            news_title TEXT,
            direction TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            confidence REAL,
            impact_score INTEGER,
            expiry_minutes INTEGER DEFAULT 15,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP,
            expires_at TIMESTAMP,
            trigger_type TEXT DEFAULT 'news',
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

    # Migrations: add columns that may not exist in older DBs
    try:
        cursor.execute("ALTER TABLE strategies ADD COLUMN is_active INTEGER DEFAULT 0")
    except:
        pass  # column already exists

    # Migration: add trigger_type to auto_strategies (news vs structure)
    try:
        cursor.execute("ALTER TABLE auto_strategies ADD COLUMN trigger_type TEXT DEFAULT 'news'")
    except:
        pass  # column already exists

    # Migration: add candles_snapshot to auto_strategies (frozen chart data)
    try:
        cursor.execute("ALTER TABLE auto_strategies ADD COLUMN candles_snapshot TEXT")
    except:
        pass  # column already exists

    # Migration: add profile_name to auto_strategies
    try:
        cursor.execute("ALTER TABLE auto_strategies ADD COLUMN profile_name TEXT")
    except:
        pass  # column already exists

    # Migration: enrich signal_results with market context for learning
    for col, default in [
        ('entry_price', '0'), ('exit_price', '0'), ('pips', '0'),
        ('direction', "''"), ('confidence', '0'), ('impact_score', '0'),
        ('setup_type', "''"), ('trigger_type', "''"),
        ('market_trend', "''"), ('rsi_at_entry', '0'), ('htf_bias', "''"),
        ('news_category', "''")
    ]:
        try:
            cursor.execute(f"ALTER TABLE signal_results ADD COLUMN {col} {('REAL' if col in ('entry_price','exit_price','pips','confidence','rsi_at_entry') else 'TEXT')} DEFAULT {default}")
        except:
            pass

    # Migration: enrich strategy_results with market context
    for col, default in [
        ('entry_price', '0'), ('exit_price', '0'), ('pips', '0'),
        ('direction', "''"), ('confidence', '0'),
        ('setup_type', "''"), ('trigger_type', "''"),
        ('market_trend', "''"), ('rsi_at_entry', '0'), ('htf_bias', "''")
    ]:
        try:
            cursor.execute(f"ALTER TABLE strategy_results ADD COLUMN {col} {('REAL' if col in ('entry_price','exit_price','pips','confidence','rsi_at_entry') else 'TEXT')} DEFAULT {default}")
        except:
            pass

    # Migration: add price_at_alert for auto-evaluation of news alerts
    try:
        cursor.execute("ALTER TABLE alerts ADD COLUMN price_at_alert REAL DEFAULT 0")
    except:
        pass

    # Migration: add auto-evaluation columns to alerts
    for col, coltype in [('alert_result', 'TEXT'), ('alert_exit_price', 'REAL DEFAULT 0'), ('alert_pips', 'REAL DEFAULT 0'), ('alert_evaluated_at', 'TIMESTAMP')]:
        try:
            cursor.execute(f"ALTER TABLE alerts ADD COLUMN {col} {coltype}")
        except:
            pass

    # Migration: add published_at to news
    try:
        cursor.execute("ALTER TABLE news ADD COLUMN published_at TIMESTAMP")
    except:
        pass

    # SMC state persistence table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS smc_state (
            timeframe TEXT PRIMARY KEY,
            trend TEXT,
            last_swing_high REAL,
            last_swing_low REAL,
            structure_points TEXT,
            zones TEXT,
            updated_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def add_news(url, title, summary, language, entities, tags, published_at=None):
    """Add news to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO news (url, title, summary, language, entities, tags, published_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (url, title, summary, language, entities, tags, published_at, now_ar()))
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
                   (now_ar(), news_id))
    conn.commit()
    conn.close()

def add_alert(news_id, impact_score, alert_level, explanation, eur_usd_impact, market_implications, analysis_method='keywords', should_operate=False, direction='NEUTRAL', confidence=50, price_at_alert=0):
    """Log an alert with detailed information including AI decision"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alerts (news_id, impact_score, alert_level, explanation, eur_usd_impact, market_implications, analysis_method, should_operate, direction, confidence, alert_sent_at, price_at_alert)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (news_id, impact_score, alert_level, explanation, eur_usd_impact, market_implications, analysis_method, 1 if should_operate else 0, direction, confidence, now_ar(), price_at_alert or 0))
    conn.commit()
    conn.close()

def get_recent_alerts(limit=50):
    """Get ALL alerts from today — no score filter, user sees everything"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.id, a.impact_score, a.alert_level, a.alert_sent_at,
               n.title, n.url, a.explanation, a.eur_usd_impact, a.market_implications,
               a.analysis_method, a.should_operate, a.direction, a.confidence,
               n.published_at, a.alert_result, a.alert_pips, a.price_at_alert
        FROM alerts a
        JOIN news n ON a.news_id = n.id
        WHERE a.alert_sent_at >= datetime(?, '-3 days')
        ORDER BY a.alert_sent_at DESC
        LIMIT ?
    """, (today_ar(), min(limit, 50),))

    results = cursor.fetchall()
    conn.close()
    return results

def has_recent_similar_strategy(direction, entry_price, trigger_type='structure', minutes=30):
    """Check if a similar strategy was already created recently (avoid duplicates).
    Similar = same direction, same trigger type, entry within 3 pips."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = now_ar() - timedelta(minutes=minutes)
    cursor.execute("""
        SELECT id, entry_price FROM auto_strategies
        WHERE direction = ? AND trigger_type = ? AND created_at > ?
        ORDER BY created_at DESC LIMIT 5
    """, (direction, trigger_type, cutoff))
    rows = cursor.fetchall()
    conn.close()
    pip = 0.0001
    for row in rows:
        if abs(row[1] - entry_price) < 3 * pip:  # within 3 pips = duplicate
            return True
    return False


def has_active_opposite_strategy(direction):
    """Check if there's an active strategy in the OPPOSITE direction.
    Prevents contradictory CALL+PUT at the same time."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    opposite = 'PUT' if direction == 'CALL' else 'CALL'
    cursor.execute("""
        SELECT id, direction, confidence FROM auto_strategies
        WHERE direction = ? AND status = 'active' AND expires_at > ?
        LIMIT 1
    """, (opposite, now_ar()))
    row = cursor.fetchone()
    conn.close()
    return row  # returns (id, direction, confidence) or None


def get_alerts_pending_evaluation():
    """Get alerts with a directional prediction (CALL/PUT) older than 30 min that haven't been evaluated yet."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = now_ar() - timedelta(minutes=30)
    cursor.execute("""
        SELECT a.id, a.direction, a.price_at_alert, a.confidence, a.impact_score,
               a.alert_sent_at, n.title
        FROM alerts a
        JOIN news n ON a.news_id = n.id
        WHERE a.direction IN ('CALL', 'PUT')
          AND a.price_at_alert > 0
          AND a.alert_result IS NULL
          AND a.alert_sent_at < ?
          AND a.alert_sent_at >= datetime(?, '-2 days')
        ORDER BY a.alert_sent_at ASC
    """, (cutoff, today_ar()))
    rows = cursor.fetchall()
    conn.close()
    return rows


def auto_evaluate_alert(alert_id, result, exit_price, pips):
    """Record an auto-evaluated alert result directly on the alerts table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE alerts SET alert_result = ?, alert_exit_price = ?, alert_pips = ?, alert_evaluated_at = ?
            WHERE id = ?
        """, (result, exit_price, round(pips, 1), now_ar(), alert_id))
        conn.commit()
    finally:
        conn.close()


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

def record_signal_result(alert_id, result, market_context=None):
    """Record whether a trading signal was correct, with optional market context"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        ctx = market_context or {}
        cursor.execute("""
            INSERT OR REPLACE INTO signal_results
            (alert_id, result, recorded_at, entry_price, exit_price, pips,
             direction, confidence, impact_score, setup_type, trigger_type,
             market_trend, rsi_at_entry, htf_bias, news_category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert_id, result, now_ar(),
              ctx.get('entry_price', 0), ctx.get('exit_price', 0), ctx.get('pips', 0),
              ctx.get('direction', ''), ctx.get('confidence', 0), ctx.get('impact_score', 0),
              ctx.get('setup_type', 'news'), ctx.get('trigger_type', 'news'),
              ctx.get('market_trend', ''), ctx.get('rsi_at_entry', 0), ctx.get('htf_bias', ''),
              ctx.get('news_category', '')))
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

def get_active_profile():
    """Get the active strategy profile config, or defaults"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT config FROM strategies WHERE is_active = 1 LIMIT 1")
        row = cursor.fetchone()
        if row:
            import json
            return json.loads(row[0])
    except:
        pass
    finally:
        conn.close()
    # Defaults (conservative)
    return {
        'min_impact': 50, 'min_confidence': 55, 'direction': 'any',
        'stop_loss_pips': 5, 'take_profit_pips': 15, 'expiry_minutes': 15
    }

def cleanup_old_data(hours=72):
    """Remove data older than specified hours"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff_date = now_ar() - timedelta(hours=hours)

    cursor.execute("DELETE FROM alerts WHERE alert_sent_at < ?", (cutoff_date,))
    cursor.execute("DELETE FROM news WHERE fetched_at < ?", (cutoff_date,))
    cursor.execute("DELETE FROM strategy_results WHERE strategy_id NOT IN (SELECT id FROM auto_strategies)")
    cursor.execute("DELETE FROM auto_strategies WHERE created_at < ?", (cutoff_date,))

    conn.commit()
    conn.close()

# ── Auto-Strategy functions ──

def add_auto_strategy(alert_id, news_title, direction, entry_price, stop_loss, take_profit, confidence, impact_score, expiry_minutes=15, trigger_type='news', candles_snapshot=None, profile_name=None):
    """Add auto-generated strategy, enforcing max 6 cap and dedup.
    alert_id can be None for structure-triggered strategies."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Get cooldown from active profile (default 2 min)
        try:
            profile = get_active_profile()
            cooldown_min = profile.get('cooldown_minutes', 2)
        except Exception:
            cooldown_min = 2

        # Dedup: skip if a strategy with same direction exists within cooldown and ~5 pips
        cutoff = now_ar() - timedelta(minutes=max(cooldown_min * 2, 3))
        cursor.execute("""
            SELECT id, entry_price FROM auto_strategies
            WHERE direction = ? AND created_at > ?
        """, (direction, cutoff))
        for row in cursor.fetchall():
            existing_price = row[1] or 0
            if abs(existing_price - entry_price) < 0.0005:  # within 5 pips
                conn.close()
                return None  # duplicate, skip

        # Global cooldown: skip if ANY strategy was created within cooldown_minutes
        recent_cutoff = now_ar() - timedelta(minutes=cooldown_min)
        cursor.execute("""
            SELECT id FROM auto_strategies WHERE created_at > ? LIMIT 1
        """, (recent_cutoff,))
        if cursor.fetchone():
            conn.close()
            return None  # too soon after last strategy

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

        now = now_ar()
        expires_at = now + timedelta(minutes=expiry_minutes)
        # Check if trigger_type column exists (migration may not have run)
        cursor.execute("PRAGMA table_info(auto_strategies)")
        columns = [row[1] for row in cursor.fetchall()]
        # Serialize candles snapshot as JSON
        snapshot_json = None
        if candles_snapshot:
            import json as _json
            snapshot_json = _json.dumps(candles_snapshot)

        if 'trigger_type' in columns:
            has_snapshot_col = 'candles_snapshot' in columns
            has_profile_col = 'profile_name' in columns
            if has_snapshot_col and has_profile_col:
                cursor.execute("""
                    INSERT INTO auto_strategies
                    (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                     confidence, impact_score, expiry_minutes, status, created_at, expires_at, trigger_type, candles_snapshot, profile_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                """, (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                      confidence, impact_score, expiry_minutes, now, expires_at, trigger_type, snapshot_json, profile_name))
            elif has_snapshot_col:
                cursor.execute("""
                    INSERT INTO auto_strategies
                    (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                     confidence, impact_score, expiry_minutes, status, created_at, expires_at, trigger_type, candles_snapshot)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """, (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                      confidence, impact_score, expiry_minutes, now, expires_at, trigger_type, snapshot_json))
            else:
                cursor.execute("""
                    INSERT INTO auto_strategies
                    (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                     confidence, impact_score, expiry_minutes, status, created_at, expires_at, trigger_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """, (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                      confidence, impact_score, expiry_minutes, now, expires_at, trigger_type))
        else:
            cursor.execute("""
                INSERT INTO auto_strategies
                (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                 confidence, impact_score, expiry_minutes, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """, (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
                  confidence, impact_score, expiry_minutes, now, expires_at))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[DB] add_auto_strategy FAILED: {e}")
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
    """, (now_ar(),))
    conn.commit()

    # Check if trigger_type column exists
    cursor.execute("PRAGMA table_info(auto_strategies)")
    columns = [row[1] for row in cursor.fetchall()]
    has_trigger_type = 'trigger_type' in columns
    has_snapshot = 'candles_snapshot' in columns
    has_profile = 'profile_name' in columns

    snap_col = ', s.candles_snapshot' if has_snapshot else ", NULL as candles_snapshot"
    tt_col = ', s.trigger_type' if has_trigger_type else ", 'news' as trigger_type"
    prof_col = ', s.profile_name' if has_profile else ", NULL as profile_name"

    cursor.execute(f"""
        SELECT s.id, s.alert_id, s.news_title, s.direction, s.entry_price,
               s.stop_loss, s.take_profit, s.confidence, s.impact_score,
               s.expiry_minutes, s.status, s.created_at, s.expires_at,
               sr.result {tt_col} {snap_col} {prof_col}
        FROM auto_strategies s
        LEFT JOIN strategy_results sr ON s.id = sr.strategy_id
        WHERE date(s.created_at) = date(?)
        ORDER BY s.created_at DESC
        LIMIT ?
    """, (today_ar(), limit,))

    results = cursor.fetchall()
    conn.close()
    return results

def record_strategy_result(strategy_id, result, market_context=None):
    """Record win/loss/skip for an auto-strategy with market context"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        ctx = market_context or {}
        cursor.execute("""
            INSERT OR REPLACE INTO strategy_results
            (strategy_id, result, recorded_at, entry_price, exit_price, pips,
             direction, confidence, setup_type, trigger_type,
             market_trend, rsi_at_entry, htf_bias)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (strategy_id, result, now_ar(),
              ctx.get('entry_price', 0), ctx.get('exit_price', 0), ctx.get('pips', 0),
              ctx.get('direction', ''), ctx.get('confidence', 0),
              ctx.get('setup_type', ''), ctx.get('trigger_type', ''),
              ctx.get('market_trend', ''), ctx.get('rsi_at_entry', 0), ctx.get('htf_bias', '')))
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
    stats = {'wins': 0, 'losses': 0, 'skips': 0, 'break_evens': 0}
    for result, count in rows:
        if result == 'win': stats['wins'] = count
        elif result == 'loss': stats['losses'] = count
        elif result == 'skip': stats['skips'] = count
        elif result == 'break_even': stats['break_evens'] = count
    total = stats['wins'] + stats['losses']  # BE excluded from win rate
    stats['total'] = total
    stats['total_resolved'] = total + stats['break_evens']
    stats['win_rate'] = round((stats['wins'] / total * 100) if total > 0 else 0, 1)
    return stats

def get_strategies_pending_evaluation():
    """Get expired strategies that haven't been evaluated yet.
    Returns strategies where:
    - status is 'expired' (past expires_at)
    - no result in strategy_results
    - expiry was at least 1 minute ago (give price time to settle)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = now_ar() - timedelta(minutes=1)
    cursor.execute("""
        SELECT s.id, s.direction, s.entry_price, s.stop_loss, s.take_profit,
               s.confidence, s.expiry_minutes, s.created_at, s.expires_at,
               s.news_title, s.trigger_type
        FROM auto_strategies s
        LEFT JOIN strategy_results sr ON s.id = sr.strategy_id
        WHERE s.expires_at < ?
          AND sr.id IS NULL
          AND date(s.created_at) >= date(?, '-1 day')
        ORDER BY s.expires_at ASC
    """, (cutoff, today_ar()))
    rows = cursor.fetchall()
    conn.close()
    return rows


def auto_evaluate_strategy(strategy_id, result, exit_price, pips, market_context=None):
    """Record an auto-evaluated strategy result."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        ctx = market_context or {}
        ctx['exit_price'] = exit_price
        ctx['pips'] = pips
        ctx['auto_evaluated'] = True
        cursor.execute("""
            INSERT OR REPLACE INTO strategy_results
            (strategy_id, result, recorded_at, entry_price, exit_price, pips,
             direction, confidence, setup_type, trigger_type,
             market_trend, rsi_at_entry, htf_bias)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (strategy_id, result, now_ar(),
              ctx.get('entry_price', 0), exit_price, pips,
              ctx.get('direction', ''), ctx.get('confidence', 0),
              ctx.get('setup_type', ''), ctx.get('trigger_type', ''),
              ctx.get('market_trend', ''), ctx.get('rsi_at_entry', 0), ctx.get('htf_bias', '')))
        status_map = {'win': 'auto_win', 'loss': 'auto_loss', 'break_even': 'auto_break_even'}
        cursor.execute("UPDATE auto_strategies SET status = ? WHERE id = ?",
                       (status_map.get(result, 'auto_loss'), strategy_id))
        conn.commit()
    finally:
        conn.close()


def get_news_fetch_time(news_id):
    """Get the effective time of a news item (published_at if available, else fetched_at)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(published_at, fetched_at) FROM news WHERE id = ?", (news_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ── Learning / Feedback Loop Functions ──

def get_detailed_trade_history(limit=30):
    """Get individual trade history with full context for AI learning.
    Combines both signal_results and strategy_results."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    trades = []

    # Signal results (news alerts)
    try:
        cursor.execute("""
            SELECT sr.result, sr.direction, sr.confidence, sr.impact_score,
                   sr.setup_type, sr.trigger_type, sr.market_trend, sr.rsi_at_entry,
                   sr.htf_bias, sr.entry_price, sr.exit_price, sr.pips,
                   sr.news_category, sr.recorded_at, n.title
            FROM signal_results sr
            LEFT JOIN alerts a ON sr.alert_id = a.id
            LEFT JOIN news n ON a.news_id = n.id
            WHERE sr.result IN ('win', 'loss')
            ORDER BY sr.recorded_at DESC
            LIMIT ?
        """, (limit,))
        for row in cursor.fetchall():
            trades.append({
                'result': row[0], 'direction': row[1] or '', 'confidence': row[2] or 0,
                'impact_score': row[3] or 0, 'setup_type': row[4] or 'news',
                'trigger_type': row[5] or 'news', 'market_trend': row[6] or '',
                'rsi': row[7] or 0, 'htf_bias': row[8] or '',
                'entry_price': row[9] or 0, 'exit_price': row[10] or 0,
                'pips': row[11] or 0, 'news_category': row[12] or '',
                'recorded_at': row[13], 'title': row[14] or '', 'source': 'alert'
            })
    except Exception:
        pass

    # Strategy results
    try:
        cursor.execute("""
            SELECT sr.result, sr.direction, sr.confidence,
                   sr.setup_type, sr.trigger_type, sr.market_trend, sr.rsi_at_entry,
                   sr.htf_bias, sr.entry_price, sr.exit_price, sr.pips,
                   sr.recorded_at, s.news_title
            FROM strategy_results sr
            LEFT JOIN auto_strategies s ON sr.strategy_id = s.id
            WHERE sr.result IN ('win', 'loss')
            ORDER BY sr.recorded_at DESC
            LIMIT ?
        """, (limit,))
        for row in cursor.fetchall():
            trades.append({
                'result': row[0], 'direction': row[1] or '', 'confidence': row[2] or 0,
                'impact_score': 0, 'setup_type': row[3] or '',
                'trigger_type': row[4] or '', 'market_trend': row[5] or '',
                'rsi': row[6] or 0, 'htf_bias': row[7] or '',
                'entry_price': row[8] or 0, 'exit_price': row[9] or 0,
                'pips': row[10] or 0, 'news_category': '',
                'recorded_at': row[11], 'title': row[12] or '', 'source': 'strategy'
            })
    except Exception:
        pass

    conn.close()
    # Sort by date, most recent first
    trades.sort(key=lambda t: t.get('recorded_at', ''), reverse=True)
    return trades[:limit]


def get_setup_win_rates():
    """Get win rate per setup_type for dynamic confidence adjustment.
    Returns dict: {setup_type: {wins, losses, total, win_rate}}"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    stats = {}

    # From strategy_results (has setup_type)
    try:
        cursor.execute("""
            SELECT setup_type, result, COUNT(*) FROM strategy_results
            WHERE result IN ('win', 'loss') AND setup_type != ''
            GROUP BY setup_type, result
        """)
        for setup_type, result, count in cursor.fetchall():
            if setup_type not in stats:
                stats[setup_type] = {'wins': 0, 'losses': 0}
            if result == 'win':
                stats[setup_type]['wins'] = count
            else:
                stats[setup_type]['losses'] = count
    except Exception:
        pass

    # From signal_results too
    try:
        cursor.execute("""
            SELECT setup_type, result, COUNT(*) FROM signal_results
            WHERE result IN ('win', 'loss') AND setup_type != ''
            GROUP BY setup_type, result
        """)
        for setup_type, result, count in cursor.fetchall():
            if setup_type not in stats:
                stats[setup_type] = {'wins': 0, 'losses': 0}
            if result == 'win':
                stats[setup_type]['wins'] += count
            else:
                stats[setup_type]['losses'] += count
    except Exception:
        pass

    conn.close()

    # Calculate win rates
    for setup_type in stats:
        s = stats[setup_type]
        total = s['wins'] + s['losses']
        s['total'] = total
        s['win_rate'] = round(s['wins'] / total * 100, 1) if total > 0 else 50.0
    return stats


def get_learned_lessons():
    """Generate learned lessons text for AI prompts based on trade history.
    Returns a string with patterns detected from past results."""
    trades = get_detailed_trade_history(50)
    if len(trades) < 2:
        return ""

    lines = [f"\nLECCIONES APRENDIDAS ({len(trades)} operaciones analizadas):"]

    # Win rate by direction
    dir_stats = {}
    for t in trades:
        d = t.get('direction', '')
        if not d:
            continue
        if d not in dir_stats:
            dir_stats[d] = {'wins': 0, 'losses': 0}
        if t['result'] == 'win':
            dir_stats[d]['wins'] += 1
        else:
            dir_stats[d]['losses'] += 1
    for d, s in dir_stats.items():
        total = s['wins'] + s['losses']
        if total >= 2:
            wr = round(s['wins'] / total * 100)
            lines.append(f"  - {d}: {wr}% acierto ({s['wins']}W/{s['losses']}L)")

    # Win rate by setup type
    setup_stats = get_setup_win_rates()
    if setup_stats:
        lines.append("  Setups:")
        for setup, s in sorted(setup_stats.items(), key=lambda x: x[1].get('win_rate', 0), reverse=True):
            if s['total'] >= 2:
                label = setup.replace('_', ' ').title()
                emoji = '✅' if s['win_rate'] >= 60 else '⚠️' if s['win_rate'] >= 40 else '❌'
                lines.append(f"    {emoji} {label}: {s['win_rate']}% ({s['wins']}W/{s['losses']}L)")

    # Win rate by HTF alignment
    htf_aligned = {'with': {'w': 0, 'l': 0}, 'against': {'w': 0, 'l': 0}}
    for t in trades:
        htf = t.get('htf_bias', '')
        direction = t.get('direction', '')
        if not htf or not direction:
            continue
        aligned = (htf == 'bullish' and direction == 'CALL') or (htf == 'bearish' and direction == 'PUT')
        key = 'with' if aligned else 'against'
        if t['result'] == 'win':
            htf_aligned[key]['w'] += 1
        else:
            htf_aligned[key]['l'] += 1

    w_total = htf_aligned['with']['w'] + htf_aligned['with']['l']
    a_total = htf_aligned['against']['w'] + htf_aligned['against']['l']
    if w_total >= 2:
        wr = round(htf_aligned['with']['w'] / w_total * 100)
        lines.append(f"  - A FAVOR de HTF: {wr}% acierto ({w_total} trades)")
    if a_total >= 2:
        wr = round(htf_aligned['against']['w'] / a_total * 100)
        lines.append(f"  - CONTRA HTF: {wr}% acierto ({a_total} trades) {'← EVITAR' if wr < 40 else ''}")

    # Win rate by confidence bracket
    conf_brackets = {'alta (>75%)': {'w': 0, 'l': 0}, 'media (50-75%)': {'w': 0, 'l': 0}, 'baja (<50%)': {'w': 0, 'l': 0}}
    for t in trades:
        c = t.get('confidence', 0)
        if c > 75:
            b = 'alta (>75%)'
        elif c > 50:
            b = 'media (50-75%)'
        else:
            b = 'baja (<50%)'
        if t['result'] == 'win':
            conf_brackets[b]['w'] += 1
        else:
            conf_brackets[b]['l'] += 1
    for bracket, s in conf_brackets.items():
        total = s['w'] + s['l']
        if total >= 2:
            wr = round(s['w'] / total * 100)
            lines.append(f"  - Confianza {bracket}: {wr}% acierto ({total} trades)")

    return '\n'.join(lines) if len(lines) > 1 else ""
