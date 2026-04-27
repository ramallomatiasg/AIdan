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
            result TEXT CHECK(result IN ('win', 'loss', 'skip', 'break_even')),
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
            result TEXT CHECK(result IN ('win', 'loss', 'skip', 'break_even')),
            recorded_at TIMESTAMP,
            FOREIGN KEY(strategy_id) REFERENCES auto_strategies(id)
        )
    """)

    # Migrations: add columns that may not exist in older DBs
    try:
        cursor.execute("ALTER TABLE strategies ADD COLUMN is_active INTEGER DEFAULT 0")
    except:
        pass  # column already exists

    # Migration: add reported_to_sheets flag to prevent duplicate uploads
    for tbl in ['signal_results', 'strategy_results']:
        try:
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN reported_to_sheets INTEGER DEFAULT 0")
            # Mark all existing trades as already reported (they were uploaded before this fix)
            cursor.execute(f"UPDATE {tbl} SET reported_to_sheets = 1 WHERE result IN ('win', 'loss')")
            print(f"[DB] Migration: marked existing {tbl} as reported_to_sheets")
        except:
            pass

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

    # Migration: MT5 execution columns on auto_strategies
    for col, coltype in [
        ('mt5_ticket', 'INTEGER'), ('mt5_lot', 'REAL'),
        ('mt5_status', 'TEXT'), ('mt5_pnl', 'REAL'),
        ('mt5_close_price', 'REAL'), ('mt5_closed_at', 'TIMESTAMP'),
    ]:
        try:
            cursor.execute(f"ALTER TABLE auto_strategies ADD COLUMN {col} {coltype}")
        except:
            pass

    # MT5 risk config table (singleton)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mt5_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            risk_percent REAL DEFAULT 1.0,
            max_positions INTEGER DEFAULT 3,
            max_lot REAL DEFAULT 0.10
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO mt5_config (id) VALUES (1)")

    # App state persistence (last session, MT5 credentials)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_username TEXT,
            last_password_hash TEXT,
            mt5_account INTEGER,
            mt5_password TEXT,
            mt5_server TEXT DEFAULT 'ICMarketsSC-Demo',
            updated_at TIMESTAMP
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO app_state (id) VALUES (1)")

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

    # ── Learning System Tables ──

    # Permanent trade archive (never deleted, enriched context)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_archive (
            id INTEGER PRIMARY KEY,
            strategy_id INTEGER,
            direction TEXT,
            result TEXT,
            entry_price REAL,
            exit_price REAL,
            pips REAL,
            stop_loss REAL,
            take_profit REAL,
            sl_pips REAL,
            tp_pips REAL,
            sl_hit INTEGER DEFAULT 0,
            tp_hit INTEGER DEFAULT 0,
            confidence REAL,
            impact_score INTEGER,
            setup_type TEXT,
            trigger_type TEXT,
            market_trend TEXT,
            trend_strength TEXT,
            rsi_at_entry REAL,
            htf_bias TEXT,
            volatility TEXT,
            avg_range_pips REAL,
            session TEXT,
            hour_utc INTEGER,
            day_of_week INTEGER,
            profile_name TEXT,
            mt5_pnl REAL,
            news_title TEXT,
            created_at TIMESTAMP,
            archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Post-trade analysis (Gemma 4 insights per closed trade)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_trade_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id INTEGER NOT NULL,
            result TEXT,
            entry_quality TEXT,
            exit_quality TEXT,
            news_accuracy TEXT,
            timing_assessment TEXT,
            key_lesson TEXT,
            confidence_was TEXT,
            suggested_adjustment TEXT,
            raw_response TEXT,
            analyzed_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (strategy_id) REFERENCES auto_strategies(id)
        )
    """)

    # Learning insights (what AIdan discovered)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_insights (
            id INTEGER PRIMARY KEY,
            category TEXT,
            insight TEXT,
            data TEXT,
            action_taken TEXT,
            created_at TIMESTAMP
        )
    """)

    # Learning metrics (periodic snapshots for trend tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_metrics (
            id INTEGER PRIMARY KEY,
            metric_name TEXT,
            value REAL,
            period TEXT,
            recorded_at TIMESTAMP
        )
    """)

    # Shared Learning config table (singleton)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shared_learning_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            supabase_url TEXT DEFAULT '',
            supabase_key TEXT DEFAULT '',
            instance_id TEXT DEFAULT '',
            instance_name TEXT DEFAULT '',
            enabled INTEGER DEFAULT 0,
            last_sync TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO shared_learning_config (id) VALUES (1)")

    # Migration: auto-generate instance_id if empty
    cursor.execute("SELECT instance_id FROM shared_learning_config WHERE id = 1")
    row = cursor.fetchone()
    if row and not row[0]:
        import uuid
        cursor.execute("UPDATE shared_learning_config SET instance_id = ? WHERE id = 1", (str(uuid.uuid4()),))

    # Shared trade cache (trades from other instances, for cross-instance learning)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shared_trade_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            remote_id INTEGER UNIQUE,
            instance_id TEXT,
            direction TEXT, result TEXT, pips REAL,
            sl_pips REAL, tp_pips REAL,
            sl_hit INTEGER DEFAULT 0, tp_hit INTEGER DEFAULT 0,
            confidence REAL, trigger_type TEXT, setup_type TEXT,
            session TEXT, hour_utc INTEGER, day_of_week INTEGER,
            htf_bias TEXT, market_trend TEXT, rsi_at_entry REAL,
            volatility TEXT, news_category TEXT,
            created_at TIMESTAMP,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add synced_to_cloud column to trade_archive
    try:
        cursor.execute("ALTER TABLE trade_archive ADD COLUMN synced_to_cloud INTEGER DEFAULT 0")
    except:
        pass

    # Migration: add entry_context JSON column to trade_archive (preserves full entry snapshot)
    try:
        cursor.execute("ALTER TABLE trade_archive ADD COLUMN entry_context TEXT DEFAULT NULL")
    except:
        pass

    # Migration: add last_fetched_remote_id to shared_learning_config
    try:
        cursor.execute("ALTER TABLE shared_learning_config ADD COLUMN last_fetched_remote_id INTEGER DEFAULT 0")
    except:
        pass

    # Migration: add trailing step tracking to auto_strategies
    try:
        cursor.execute("ALTER TABLE auto_strategies ADD COLUMN mt5_trailing_step INTEGER DEFAULT 0")
    except:
        pass

    # Migration: add mt5_fill_price to store actual broker fill price (may differ from signal entry_price)
    try:
        cursor.execute("ALTER TABLE auto_strategies ADD COLUMN mt5_fill_price REAL")
    except:
        pass

    # Migration: add be_triggered flag — set when trailing SL moves to BE or beyond
    try:
        cursor.execute("ALTER TABLE auto_strategies ADD COLUMN be_triggered INTEGER DEFAULT 0")
    except:
        pass

    # Migration: add paused_from_status for toggle pause/resume
    try:
        cursor.execute("ALTER TABLE auto_strategies ADD COLUMN paused_from_status TEXT DEFAULT NULL")
    except:
        pass

    # Migration: add pre-planning columns
    for col, coltype in [
        ('event_time', 'TEXT DEFAULT NULL'),
        ('planning_reasoning', 'TEXT DEFAULT NULL'),
        ('entry_strategy', 'TEXT DEFAULT NULL'),
        ('risk_level', 'TEXT DEFAULT NULL'),
        ('planned_sl_pips', 'REAL DEFAULT NULL'),
        ('planned_tp_pips', 'REAL DEFAULT NULL'),
        ('mt5_high_water', 'REAL DEFAULT NULL'),
        ('entry_context', 'TEXT DEFAULT NULL'),  # JSON: market_state at entry time (RSI, ATR, trend, htf_bias, volatility)
    ]:
        try:
            cursor.execute(f"ALTER TABLE auto_strategies ADD COLUMN {col} {coltype}")
        except:
            pass

    # Migration: expand strategy_results CHECK constraint to allow 'break_even'
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE name='strategy_results'")
        schema = cursor.fetchone()
        if schema and 'break_even' not in schema[0]:
            cursor.execute("ALTER TABLE strategy_results RENAME TO strategy_results_old")
            cursor.execute("""CREATE TABLE strategy_results (
                id INTEGER PRIMARY KEY, strategy_id INTEGER UNIQUE,
                result TEXT CHECK(result IN ('win', 'loss', 'skip', 'break_even')),
                recorded_at TIMESTAMP, entry_price REAL DEFAULT 0, exit_price REAL DEFAULT 0,
                pips REAL DEFAULT 0, direction TEXT DEFAULT '', confidence REAL DEFAULT 0,
                setup_type TEXT DEFAULT '', trigger_type TEXT DEFAULT '', market_trend TEXT DEFAULT '',
                rsi_at_entry REAL DEFAULT 0, htf_bias TEXT DEFAULT '', reported_to_sheets INTEGER DEFAULT 0,
                FOREIGN KEY(strategy_id) REFERENCES auto_strategies(id))""")
            cursor.execute("INSERT INTO strategy_results SELECT * FROM strategy_results_old")
            cursor.execute("DROP TABLE strategy_results_old")
    except:
        pass

    # Migration: add synced_to_cloud column to learning_insights
    try:
        cursor.execute("ALTER TABLE learning_insights ADD COLUMN synced_to_cloud INTEGER DEFAULT 0")
    except:
        pass

    # Backfill: fix hour_utc and session for trades archived with old code
    cursor.execute("SELECT id, created_at FROM trade_archive WHERE (hour_utc = 0 OR hour_utc IS NULL OR session = '' OR session IS NULL) AND created_at IS NOT NULL")
    _fix_rows = cursor.fetchall()
    if _fix_rows:
        for _fid, _fca in _fix_rows:
            try:
                _fh = int(str(_fca).split(' ')[1].split(':')[0])
                _fh_utc = (_fh + 3) % 24
                if 7 <= _fh_utc < 12: _fs = 'london'
                elif 12 <= _fh_utc < 14: _fs = 'overlap'
                elif 14 <= _fh_utc < 17: _fs = 'ny'
                elif 17 <= _fh_utc < 21: _fs = 'late_ny'
                else: _fs = 'off'
                cursor.execute("UPDATE trade_archive SET hour_utc = ?, session = ? WHERE id = ?", (_fh_utc, _fs, _fid))
            except:
                pass
        print(f"[DB] Backfill: fixed hour_utc/session for {len(_fix_rows)} trades")

    # Backfill: copy existing strategy_results into trade_archive if not already done
    cursor.execute("SELECT COUNT(*) FROM trade_archive")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO trade_archive
                (strategy_id, direction, result, entry_price, exit_price, pips,
                 stop_loss, take_profit, sl_pips, tp_pips,
                 confidence, setup_type, trigger_type, market_trend,
                 rsi_at_entry, htf_bias, news_title, created_at, archived_at)
            SELECT
                sr.strategy_id, sr.direction, sr.result, sr.entry_price, sr.exit_price, sr.pips,
                s.stop_loss, s.take_profit,
                CASE WHEN s.direction='CALL' THEN round((s.entry_price - s.stop_loss)/0.0001, 1)
                     ELSE round((s.stop_loss - s.entry_price)/0.0001, 1) END,
                CASE WHEN s.direction='CALL' THEN round((s.take_profit - s.entry_price)/0.0001, 1)
                     ELSE round((s.entry_price - s.take_profit)/0.0001, 1) END,
                sr.confidence, sr.setup_type, sr.trigger_type, sr.market_trend,
                sr.rsi_at_entry, sr.htf_bias, s.news_title, s.created_at, sr.recorded_at
            FROM strategy_results sr
            JOIN auto_strategies s ON sr.strategy_id = s.id
            WHERE sr.result IN ('win', 'loss', 'break_even')
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
    except Exception as e:
        import logging
        logging.getLogger('db').debug(f"get_active_profile: {e}")
    finally:
        conn.close()
    # Defaults (v3.7.0) — min_confidence raised from 50 to 60 after analysis of 75 trades
    # showed conf=50-59 bucket had ~same WR as conf=60-69 but contributed half the losses.
    # See README v3.7.0 changelog for the data.
    return {
        'min_impact': 50, 'min_confidence': 60, 'direction': 'any',
        'stop_loss_pips': 3.5, 'take_profit_pips': 15, 'expiry_minutes': 15,
        'cooldown_minutes': 2, 'max_trades_per_hour': 3,
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

def add_auto_strategy(alert_id, news_title, direction, entry_price, stop_loss, take_profit, confidence, impact_score, expiry_minutes=15, trigger_type='news', candles_snapshot=None, profile_name=None, entry_context=None):
    """Add auto-generated strategy, enforcing max 6 cap and dedup.
    alert_id can be None for structure-triggered strategies.
    entry_context: dict with RSI/ATR/trend/htf_bias captured at signal creation (atomic with row insert)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Get cooldown + rate limit from active profile
        try:
            profile = get_active_profile()
            cooldown_min = profile.get('cooldown_minutes', 2)
            max_per_hour = profile.get('max_trades_per_hour', 3)
        except Exception:
            cooldown_min = 2
            max_per_hour = 3

        # Rate limit: max_trades_per_hour (configurable via profile)
        hour_cutoff = now_ar() - timedelta(hours=1)
        cursor.execute("SELECT COUNT(*) FROM auto_strategies WHERE created_at > ?", (hour_cutoff,))
        trades_last_hour = cursor.fetchone()[0]
        if trades_last_hour >= max_per_hour:
            import logging
            logging.getLogger('db').info(f"Rate limit: {trades_last_hour}/{max_per_hour} trades in last hour, skipping {direction} {trigger_type}")
            conn.close()
            return None

        import logging
        # Consecutive losses circuit: 3 losses in tight window → pause 30 min (tilt protection)
        # Uses created_at (decision time) not archived_at, and requires the 3 to be in same
        # 2-hour window — prevents false triggers from old carry-over trades archived at cap.
        try:
            # Get last 3 decided trades by creation time (actual trading order)
            cursor.execute("""
                SELECT result, created_at FROM trade_archive
                WHERE mt5_pnl IS NOT NULL AND result IN ('win', 'loss')
                ORDER BY created_at DESC LIMIT 3
            """)
            rows = cursor.fetchall()
            if len(rows) == 3 and all(r[0] == 'loss' for r in rows):
                from datetime import datetime as _dt
                try:
                    # All created_at are in AR time (now_ar()). Compare with now_ar().
                    latest = _dt.strptime(str(rows[0][1]).split('.')[0], '%Y-%m-%d %H:%M:%S')
                    oldest = _dt.strptime(str(rows[2][1]).split('.')[0], '%Y-%m-%d %H:%M:%S')
                    now_local = now_ar()
                    mins_since_latest = (now_local - latest).total_seconds() / 60
                    window_minutes = (latest - oldest).total_seconds() / 60
                    # Only block if:
                    # 1. Last loss was recent (0-30 min ago)
                    # 2. All 3 losses happened within a 2-hour window (real tilt pattern)
                    if 0 <= mins_since_latest < 30 and window_minutes <= 120:
                        logging.getLogger('db').warning(f"Circuit breaker: 3 losses in {window_minutes:.0f}min window, last {mins_since_latest:.0f}min ago — pausing 30min")
                        conn.close()
                        return None
                except Exception as _cbp:
                    logging.getLogger('db').debug(f"Circuit breaker parse: {_cbp}")
        except Exception as _cbe:
            logging.getLogger('db').debug(f"Circuit breaker check: {_cbe}")

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
            # Archive closed strategies before deleting them
            to_delete = count - 5
            cursor.execute("""
                SELECT id, direction, entry_price, stop_loss, take_profit, confidence,
                       impact_score, trigger_type, news_title, profile_name, created_at,
                       mt5_pnl, mt5_close_price, mt5_status, status, mt5_fill_price
                FROM auto_strategies ORDER BY created_at ASC LIMIT ?
            """, (to_delete,))
            for old_row in cursor.fetchall():
                old_id, old_dir, old_entry, old_sl, old_tp, old_conf, old_impact, \
                    old_trigger, old_title, old_profile, old_created, old_mt5_pnl, \
                    old_close, old_mt5_status, old_status, old_fill = old_row
                if old_mt5_status == 'closed' and old_close:
                    pip = 0.0001
                    # Use fill_price (actual MT5 execution) for pip calculations, fallback to entry_price
                    old_ref = old_fill if old_fill else old_entry
                    if old_dir == 'CALL':
                        old_pips = round((old_close - old_ref) / pip, 1) if old_ref else 0
                        old_sl_pips = round((old_ref - old_sl) / pip, 1) if old_sl else 0
                        old_tp_pips = round((old_tp - old_ref) / pip, 1) if old_tp else 0
                    else:
                        old_pips = round((old_ref - old_close) / pip, 1) if old_ref else 0
                        old_sl_pips = round((old_sl - old_ref) / pip, 1) if old_sl else 0
                        old_tp_pips = round((old_ref - old_tp) / pip, 1) if old_tp else 0
                    # Use MT5 P&L as ground truth when available (entry_price != fill_price causes mismatches)
                    old_result = 'win' if (old_mt5_pnl or old_pips) > 0 else 'loss'
                    sl_hit = 1 if old_result == 'loss' else 0
                    tp_hit = 1 if old_result == 'win' else 0
                    # Check not already archived
                    cursor.execute("SELECT 1 FROM trade_archive WHERE strategy_id = ?", (old_id,))
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO trade_archive
                                (strategy_id, direction, result, entry_price, exit_price, pips,
                                 stop_loss, take_profit, sl_pips, tp_pips, sl_hit, tp_hit,
                                 confidence, impact_score, setup_type, trigger_type,
                                 market_trend, trend_strength, rsi_at_entry, htf_bias,
                                 volatility, avg_range_pips, session, hour_utc, day_of_week,
                                 profile_name, mt5_pnl, news_title, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            old_id, old_dir, old_result, old_entry, old_close, old_pips,
                            old_sl, old_tp, old_sl_pips, old_tp_pips, sl_hit, tp_hit,
                            old_conf, old_impact, '', old_trigger,
                            '', '', 0, '', '', 0, '', 0, 0,
                            old_profile, old_mt5_pnl, old_title, old_created
                        ))
                        import logging
                        logging.getLogger('db').info(f"Auto-archived strategy #{old_id} before cap delete: {old_result} {old_pips}p")
            # Delete oldest + their votes
            cursor.execute("""
                DELETE FROM strategy_results WHERE strategy_id IN (
                    SELECT id FROM auto_strategies ORDER BY created_at ASC LIMIT ?
                )
            """, (to_delete,))
            cursor.execute("""
                DELETE FROM auto_strategies WHERE id IN (
                    SELECT id FROM auto_strategies ORDER BY created_at ASC LIMIT ?
                )
            """, (to_delete,))

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

        new_id = cursor.lastrowid
        # Atomic entry_context persist (avoids race with fast MT5 fills)
        if entry_context and 'entry_context' in columns:
            import json as _json
            try:
                cursor.execute("UPDATE auto_strategies SET entry_context = ? WHERE id = ?",
                               (_json.dumps(entry_context), new_id))
            except Exception:
                pass
        conn.commit()
        return new_id
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

    # Expire old ones first (but NOT paused strategies)
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

    has_mt5 = 'mt5_ticket' in columns
    has_fill = 'mt5_fill_price' in columns
    mt5_cols = ', s.mt5_ticket, s.mt5_lot, s.mt5_status, s.mt5_pnl' if has_mt5 else ', NULL, NULL, NULL, NULL'
    mt5_cols += ', s.mt5_fill_price' if has_fill else ', NULL'

    # Pre-planner columns
    has_event_time = 'event_time' in columns
    has_planning = 'planning_reasoning' in columns
    has_entry_strat = 'entry_strategy' in columns
    has_risk = 'risk_level' in columns
    has_plan_pips = 'planned_sl_pips' in columns
    plan_cols = (f", s.event_time" if has_event_time else ", NULL") + \
                (f", s.planning_reasoning" if has_planning else ", NULL") + \
                (f", s.entry_strategy" if has_entry_strat else ", NULL") + \
                (f", s.risk_level" if has_risk else ", NULL") + \
                (f", s.planned_sl_pips, s.planned_tp_pips" if has_plan_pips else ", NULL, NULL")

    cursor.execute(f"""
        SELECT s.id, s.alert_id, s.news_title, s.direction, s.entry_price,
               s.stop_loss, s.take_profit, s.confidence, s.impact_score,
               s.expiry_minutes, s.status, s.created_at, s.expires_at,
               sr.result {tt_col} {snap_col} {prof_col} {mt5_cols} {plan_cols}
        FROM auto_strategies s
        LEFT JOIN strategy_results sr ON s.id = sr.strategy_id
        WHERE date(s.created_at) = date(?) OR s.status IN ('active', 'planned', 'paused')
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
    """Get win/loss/skip stats for auto-strategies from trade_archive (persistent).
    Falls back to strategy_results for break_even/skip which aren't archived."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Primary: trade_archive (persistent, survives 6-cap deletes)
    cursor.execute("""
        SELECT result, COUNT(*) FROM trade_archive
        WHERE strftime('%w', created_at) NOT IN ('0', '6')
        GROUP BY result
    """)
    rows = cursor.fetchall()
    stats = {'wins': 0, 'losses': 0, 'skips': 0, 'break_evens': 0}
    for result, count in rows:
        if result == 'win': stats['wins'] = count
        elif result == 'loss': stats['losses'] = count
    # Break-evens from strategy_results (not archived)
    cursor.execute("""
        SELECT COUNT(*) FROM strategy_results
        WHERE result = 'break_even' AND strftime('%w', recorded_at) NOT IN ('0', '6')
    """)
    stats['break_evens'] = cursor.fetchone()[0]
    conn.close()
    total = stats['wins'] + stats['losses']
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
               s.news_title, s.trigger_type, s.be_triggered
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
    """Get the effective time of a news item in AR time.
    published_at is UTC (from RSS feeds), fetched_at is already AR time (from now_ar()).
    Convert published_at to AR (UTC-3) for consistent comparison."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT published_at, fetched_at FROM news WHERE id = ?
    """, (news_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    pub_utc, fetched_ar = row
    if pub_utc:
        # Convert UTC published_at to AR time (UTC-3)
        try:
            from datetime import datetime, timedelta
            _pub_str = str(pub_utc).split('.')[0].replace('T', ' ')
            pub_dt = datetime.strptime(_pub_str, '%Y-%m-%d %H:%M:%S')
            pub_ar = pub_dt - timedelta(hours=3)
            return pub_ar.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return pub_utc  # fallback: return as-is
    return fetched_ar


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
              AND strftime('%w', sr.recorded_at) NOT IN ('0', '6')
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
              AND strftime('%w', sr.recorded_at) NOT IN ('0', '6')
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


def get_unreported_trades(today_str):
    """Get trades that haven't been reported to Google Sheets yet (today only)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    trades = []

    # Unreported signal results
    try:
        cursor.execute("""
            SELECT sr.id, 'signal' as src, sr.result, sr.direction, sr.confidence, sr.impact_score,
                   sr.setup_type, sr.trigger_type, sr.market_trend, sr.rsi_at_entry,
                   sr.htf_bias, sr.entry_price, sr.exit_price, sr.pips,
                   sr.recorded_at, n.title
            FROM signal_results sr
            LEFT JOIN alerts a ON sr.alert_id = a.id
            LEFT JOIN news n ON a.news_id = n.id
            WHERE sr.result IN ('win', 'loss')
              AND sr.recorded_at LIKE ?
              AND COALESCE(sr.reported_to_sheets, 0) = 0
            ORDER BY sr.recorded_at ASC
        """, (f"{today_str}%",))
        for row in cursor.fetchall():
            trades.append({
                '_id': row[0], '_src': row[1],
                'result': row[2], 'direction': row[3] or '', 'confidence': row[4] or 0,
                'impact_score': row[5] or 0, 'setup_type': row[6] or 'news',
                'trigger_type': row[7] or 'news', 'market_trend': row[8] or '',
                'rsi': row[9] or 0, 'htf_bias': row[10] or '',
                'entry_price': row[11] or 0, 'exit_price': row[12] or 0,
                'pips': row[13] or 0, 'recorded_at': row[14], 'title': row[15] or '',
                'source': 'alert'
            })
    except Exception:
        pass

    # Unreported strategy results
    try:
        cursor.execute("""
            SELECT sr.id, 'strategy' as src, sr.result, sr.direction, sr.confidence,
                   sr.setup_type, sr.trigger_type, sr.market_trend, sr.rsi_at_entry,
                   sr.htf_bias, sr.entry_price, sr.exit_price, sr.pips,
                   sr.recorded_at, s.news_title
            FROM strategy_results sr
            LEFT JOIN auto_strategies s ON sr.strategy_id = s.id
            WHERE sr.result IN ('win', 'loss')
              AND sr.recorded_at LIKE ?
              AND COALESCE(sr.reported_to_sheets, 0) = 0
            ORDER BY sr.recorded_at ASC
        """, (f"{today_str}%",))
        for row in cursor.fetchall():
            trades.append({
                '_id': row[0], '_src': row[1],
                'result': row[2], 'direction': row[3] or '', 'confidence': row[4] or 0,
                'impact_score': 0, 'setup_type': row[5] or '',
                'trigger_type': row[6] or '', 'market_trend': row[7] or '',
                'rsi': row[8] or 0, 'htf_bias': row[9] or '',
                'entry_price': row[10] or 0, 'exit_price': row[11] or 0,
                'pips': row[12] or 0, 'recorded_at': row[13], 'title': row[14] or '',
                'source': 'strategy'
            })
    except Exception:
        pass

    conn.close()
    trades.sort(key=lambda t: t.get('recorded_at', ''))
    return trades


def mark_trades_reported(trades):
    """Mark trades as reported to Google Sheets so they aren't uploaded again."""
    if not trades:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for t in trades:
        src = t.get('_src', '')
        tid = t.get('_id', 0)
        if not tid:
            continue
        table = 'signal_results' if src == 'signal' else 'strategy_results'
        try:
            cursor.execute(f"UPDATE {table} SET reported_to_sheets = 1 WHERE id = ?", (tid,))
        except Exception:
            pass
    conn.commit()
    conn.close()


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
              AND strftime('%w', recorded_at) NOT IN ('0', '6')
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
              AND strftime('%w', recorded_at) NOT IN ('0', '6')
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


# ── MT5 helper functions ──

def update_mt5_ticket(strategy_id, ticket, lot, status, fill_price=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        if fill_price is not None:
            cursor.execute("""
                UPDATE auto_strategies SET mt5_ticket = ?, mt5_lot = ?, mt5_status = ?, mt5_fill_price = ?
                WHERE id = ?
            """, (ticket, lot, status, fill_price, strategy_id))
        else:
            cursor.execute("""
                UPDATE auto_strategies SET mt5_ticket = ?, mt5_lot = ?, mt5_status = ?
                WHERE id = ?
            """, (ticket, lot, status, strategy_id))
        conn.commit()
    finally:
        conn.close()

def update_mt5_close(strategy_id, pnl, close_price, status='closed'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE auto_strategies SET mt5_pnl = ?, mt5_close_price = ?, mt5_status = ?, mt5_closed_at = ?
            WHERE id = ?
        """, (round(pnl, 2), close_price, status, now_ar(), strategy_id))
        conn.commit()
    finally:
        conn.close()

def get_mt5_daily_pnl():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(SUM(mt5_pnl), 0) FROM auto_strategies
        WHERE mt5_status = 'closed' AND date(mt5_closed_at) = date(?)
    """, (now_ar(),))
    result = cursor.fetchone()[0]
    conn.close()
    return result

def get_active_unexecuted_strategies():
    """Get active strategies that were never executed in MT5 (no ticket)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, direction, entry_price, stop_loss, take_profit, confidence
        FROM auto_strategies
        WHERE status = 'active'
          AND expires_at > ?
          AND (mt5_ticket IS NULL AND (mt5_status IS NULL OR mt5_status = 'error'))
    """, (now_ar(),))
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'direction': r[1], 'entry_price': r[2],
             'stop_loss': r[3], 'take_profit': r[4], 'confidence': r[5]} for r in rows]


def get_strategies_with_open_mt5():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, mt5_ticket, direction, entry_price, stop_loss, take_profit,
               mt5_lot, created_at, news_title, mt5_trailing_step, mt5_fill_price,
               mt5_high_water, confidence
        FROM auto_strategies
        WHERE mt5_status = 'filled' AND mt5_ticket IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_mt5_trailing_step(strategy_id, step):
    """Update the trailing SL step for a strategy. Sets be_triggered=1 when step >= 1."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE auto_strategies SET mt5_trailing_step = ? WHERE id = ?", (step, strategy_id))
    if step >= 1:
        conn.execute("UPDATE auto_strategies SET be_triggered = 1 WHERE id = ?", (strategy_id,))
    conn.commit()
    conn.close()


def update_mt5_trailing_data(strategy_id, step, high_water=None):
    """Update trailing step + high water mark. Sets be_triggered=1 when step >= 1."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE auto_strategies SET mt5_trailing_step = ? WHERE id = ?", (step, strategy_id))
    if high_water is not None:
        conn.execute("UPDATE auto_strategies SET mt5_high_water = ? WHERE id = ?", (high_water, strategy_id))
    if step >= 1:
        conn.execute("UPDATE auto_strategies SET be_triggered = 1 WHERE id = ?", (strategy_id,))
    conn.commit()
    conn.close()


def mark_be_triggered(strategy_id):
    """Mark a strategy as having reached breakeven (trailing SL moved to BE)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE auto_strategies SET be_triggered = 1 WHERE id = ?", (strategy_id,))
    conn.commit()
    conn.close()


def add_planned_strategy(news_title, direction, confidence, sl_pips, tp_pips,
                         trigger_type='pre_planned', event_time=None,
                         planning_reasoning=None, entry_strategy=None, risk_level=None):
    """Add a pre-planned strategy (status='planned') for a future event.
    Entry/exit prices are set to 0 — they'll be calculated at activation time.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Dedup: skip if planned strategy with same event already exists (any direction)
        cursor.execute("""
            SELECT id, direction FROM auto_strategies
            WHERE status = 'planned' AND news_title = ?
        """, (news_title,))
        existing = cursor.fetchone()
        if existing:
            import logging
            logging.getLogger('db').info(f"Pre-plan dedup: '{news_title}' already planned as #{existing[0]} {existing[1]}, skipping {direction}")
            conn.close()
            return None  # duplicate event

        now = now_ar()
        # Planned strategies expire 30 min after the event
        try:
            from datetime import datetime as _dt
            evt = _dt.fromisoformat(event_time.replace('Z', '+00:00')) if event_time else now
            expires_at = evt + timedelta(minutes=30)
        except Exception:
            expires_at = now + timedelta(hours=24)

        cursor.execute("""
            INSERT INTO auto_strategies
            (alert_id, news_title, direction, entry_price, stop_loss, take_profit,
             confidence, impact_score, expiry_minutes, status, created_at, expires_at,
             trigger_type, event_time, planning_reasoning, entry_strategy, risk_level,
             planned_sl_pips, planned_tp_pips)
            VALUES (NULL, ?, ?, 0, 0, 0, ?, 0, 30, 'planned', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (news_title, direction, confidence, now, expires_at,
              trigger_type, event_time, planning_reasoning, entry_strategy, risk_level,
              sl_pips, tp_pips))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[DB] add_planned_strategy FAILED: {e}")
        return None
    finally:
        conn.close()


def activate_due_planned_strategies(minutes_before=5):
    """Activate planned strategies whose event is within minutes_before.
    Returns list of strategy IDs that were activated.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        now = datetime.now(timezone.utc)
        window_start = now
        window_end = now + timedelta(minutes=minutes_before)

        cursor.execute("""
            SELECT id, event_time FROM auto_strategies
            WHERE status = 'planned' AND event_time IS NOT NULL
        """)
        activated = []
        for row in cursor.fetchall():
            sid, evt_str = row
            try:
                if 'T' in str(evt_str):
                    evt = datetime.fromisoformat(str(evt_str).replace('Z', '+00:00'))
                else:
                    evt = datetime.strptime(str(evt_str)[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)

                if evt.tzinfo is None:
                    evt = evt.replace(tzinfo=timezone.utc)

                if window_start <= evt <= window_end:
                    cursor.execute("UPDATE auto_strategies SET status = 'active' WHERE id = ?", (sid,))
                    activated.append(sid)
            except Exception:
                continue

        if activated:
            conn.commit()
        return activated
    finally:
        conn.close()


def get_planned_strategies():
    """Get all planned strategies for dashboard display."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM auto_strategies
        WHERE status IN ('planned', 'paused') AND event_time IS NOT NULL
        ORDER BY event_time ASC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def toggle_strategy_pause(strategy_id):
    """Toggle pause/resume for a strategy.
    - If active/planned → paused (saves original status in paused_from_status)
    - If paused → restored to original status
    Returns new status string or None if strategy not found / not pausable.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status, paused_from_status FROM auto_strategies WHERE id = ?", (strategy_id,))
        row = cursor.fetchone()
        if not row:
            return None

        current_status, paused_from = row

        if current_status == 'paused':
            # Resume: restore original status
            new_status = paused_from or 'active'
            cursor.execute("""
                UPDATE auto_strategies SET status = ?, paused_from_status = NULL WHERE id = ?
            """, (new_status, strategy_id))
            conn.commit()
            return new_status
        elif current_status in ('active', 'planned'):
            # Pause: save current status and set to paused
            cursor.execute("""
                UPDATE auto_strategies SET status = 'paused', paused_from_status = ? WHERE id = ?
            """, (current_status, strategy_id))
            conn.commit()
            return 'paused'
        else:
            # Can't pause expired/evaluated strategies
            return None
    finally:
        conn.close()


def get_evaluated_open_mt5():
    """Get strategies that were evaluated/expired but MT5 position still marked as filled."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, status, mt5_ticket
        FROM auto_strategies
        WHERE mt5_status = 'filled' AND mt5_ticket IS NOT NULL
          AND status IN ('auto_win', 'auto_loss', 'expired')
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'result': r[1], 'mt5_ticket': r[2]} for r in rows]

def get_mt5_pnl_for_strategy(strategy_id):
    """Get MT5 P&L and lot for a strategy (if position was closed by MT5 TP/SL or sync)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mt5_pnl, mt5_lot, mt5_close_price
        FROM auto_strategies
        WHERE id = ? AND mt5_pnl IS NOT NULL AND mt5_status = 'closed'
    """, (strategy_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'pnl': row[0], 'lot': row[1] or 0.1, 'close_price': row[2]}
    return None

def get_mt5_config():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT risk_percent, max_positions, max_lot FROM mt5_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'risk_percent': row[0], 'max_positions': row[1], 'max_lot': row[2]}
    return {'risk_percent': 1.0, 'max_positions': 3, 'max_lot': 0.10}

def update_mt5_config(risk_percent=None, max_positions=None, max_lot=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current = get_mt5_config()
    cursor.execute("""
        UPDATE mt5_config SET risk_percent = ?, max_positions = ?, max_lot = ?
        WHERE id = 1
    """, (
        risk_percent if risk_percent is not None else current['risk_percent'],
        max_positions if max_positions is not None else current['max_positions'],
        max_lot if max_lot is not None else current['max_lot'],
    ))
    conn.commit()
    conn.close()


# ── Learning System Functions ──

def archive_trade(strategy_id, result, exit_price, pips, context=None):
    """Archive a completed trade with enriched context for learning."""
    ctx = context or {}
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Check not already archived
        cursor.execute("SELECT 1 FROM trade_archive WHERE strategy_id = ?", (strategy_id,))
        if cursor.fetchone():
            conn.close()
            return  # already archived
        # Get strategy data for enrichment (includes entry_context JSON)
        cursor.execute("""
            SELECT direction, entry_price, stop_loss, take_profit, confidence,
                   impact_score, trigger_type, news_title, profile_name, created_at,
                   mt5_pnl, mt5_fill_price, entry_context
            FROM auto_strategies WHERE id = ?
        """, (strategy_id,))
        row = cursor.fetchone()
        if not row:
            import logging
            logging.getLogger('db').warning(f"archive_trade: strategy #{strategy_id} not found (deleted by cap?)")
            conn.close()
            return
        direction, entry, sl, tp, conf, impact, trigger, title, profile, created, mt5_pnl, fill_price, entry_ctx_json = row

        # Use fill_price (actual MT5 execution price) for SL/TP distance calculation
        # entry_price is the signal price; fill_price is where the order actually filled
        ref_price = fill_price if fill_price else entry
        # Calculate SL/TP distances in pips
        pip = 0.0001
        if direction == 'CALL':
            sl_pips = round((ref_price - sl) / pip, 1) if sl else 0
            tp_pips = round((tp - ref_price) / pip, 1) if tp else 0
        else:
            sl_pips = round((sl - ref_price) / pip, 1) if sl else 0
            tp_pips = round((ref_price - tp) / pip, 1) if tp else 0

        # Determine if SL/TP was hit
        sl_hit = 1 if result == 'loss' and pips < 0 else 0
        tp_hit = 1 if result == 'win' and pips > 0 else 0

        # Determine trading session from creation time
        try:
            from datetime import datetime as dt
            created_dt = dt.strptime(str(created).split('.')[0], '%Y-%m-%d %H:%M:%S')
            # Convert AR time to UTC (+3h)
            hour_utc = (created_dt.hour + 3) % 24
            day_of_week = created_dt.weekday()
            if 7 <= hour_utc < 12:
                session = 'london'
            elif 12 <= hour_utc < 14:
                session = 'overlap'
            elif 14 <= hour_utc < 17:
                session = 'ny'
            elif 17 <= hour_utc < 21:
                session = 'late_ny'
            else:
                session = 'off'
        except:
            hour_utc, day_of_week, session = 0, 0, 'unknown'

        cursor.execute("""
            INSERT INTO trade_archive
                (strategy_id, direction, result, entry_price, exit_price, pips,
                 stop_loss, take_profit, sl_pips, tp_pips, sl_hit, tp_hit,
                 confidence, impact_score, setup_type, trigger_type,
                 market_trend, trend_strength, rsi_at_entry, htf_bias,
                 volatility, avg_range_pips, session, hour_utc, day_of_week,
                 profile_name, mt5_pnl, news_title, created_at, entry_context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            strategy_id, direction, result, ref_price, exit_price, pips,
            sl, tp, sl_pips, tp_pips, sl_hit, tp_hit,
            conf, impact, ctx.get('setup_type', ''), trigger,
            ctx.get('market_trend', ''), ctx.get('trend_strength', ''),
            ctx.get('rsi_at_entry', 0), ctx.get('htf_bias', ''),
            ctx.get('volatility', ''), ctx.get('avg_range_pips', 0),
            session, hour_utc, day_of_week,
            profile, mt5_pnl, title, created, entry_ctx_json
        ))
        conn.commit()
    finally:
        conn.close()


def get_trade_archive(limit=500):
    """Get trades from archive for learning analysis (excludes weekend paper trades)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM trade_archive
        WHERE day_of_week NOT IN (5, 6)
        ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_archive_stats():
    """Get aggregate stats from trade archive."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(AVG(pips), 0) as avg_pips,
            COALESCE(SUM(pips), 0) as total_pips,
            MIN(created_at) as first_trade,
            MAX(created_at) as last_trade
        FROM trade_archive WHERE result IN ('win', 'loss')
          AND day_of_week NOT IN (5, 6)
    """)
    row = cursor.fetchone()
    conn.close()
    total, wins, losses = row[0] or 0, row[1] or 0, row[2] or 0
    return {
        'total': total, 'wins': wins, 'losses': losses,
        'win_rate': round(wins / max(total, 1) * 100, 1),
        'avg_pips': round(row[3], 2), 'total_pips': round(row[4], 2),
        'first_trade': row[5], 'last_trade': row[6]
    }


def save_entry_context(strategy_id, market_state, htf_bias=None):
    """Persist market snapshot captured AT signal creation time (entry).
    Stored as JSON in auto_strategies.entry_context column for later archival.
    """
    import json as _json
    try:
        ctx = {
            'rsi': market_state.get('rsi', 0),
            'rsi_zone': market_state.get('rsi_zone', ''),
            'avg_range_pips': market_state.get('avg_range_pips', 0),
            'volatility': market_state.get('volatility', ''),
            'trend': market_state.get('trend', ''),
            'trend_strength': market_state.get('trend_strength', ''),
            'momentum': market_state.get('momentum', ''),
            'htf_bias': htf_bias or '',
        }
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE auto_strategies SET entry_context = ? WHERE id = ?",
                     (_json.dumps(ctx), strategy_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_entry_context(strategy_id):
    """Read the market snapshot saved at entry time. Returns dict or empty dict."""
    import json as _json
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT entry_context FROM auto_strategies WHERE id = ?",
                           (strategy_id,)).fetchone()
        conn.close()
        if row and row[0]:
            return _json.loads(row[0])
    except Exception:
        pass
    return {}


def save_post_trade_analysis(strategy_id, analysis, result=None):
    """Save post-trade analysis from Gemma 4."""
    import json as _json
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO post_trade_analysis
            (strategy_id, result, entry_quality, exit_quality, news_accuracy,
             timing_assessment, key_lesson, confidence_was, suggested_adjustment, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            strategy_id,
            result or analysis.get('result', ''),
            analysis.get('entry_quality', ''),
            analysis.get('exit_quality', ''),
            analysis.get('news_accuracy', ''),
            analysis.get('timing_assessment', ''),
            analysis.get('key_lesson', ''),
            analysis.get('confidence_was', ''),
            analysis.get('suggested_adjustment', ''),
            _json.dumps(analysis)
        ))
        conn.commit()
    finally:
        conn.close()


def get_post_trade_analyses(limit=20):
    """Get recent post-trade analyses for dashboard."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, a.direction, a.news_title, a.trigger_type, a.confidence as orig_confidence
        FROM post_trade_analysis p
        LEFT JOIN auto_strategies a ON p.strategy_id = a.id
        ORDER BY p.analyzed_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_post_trade_stats():
    """Get aggregate stats from post-trade analyses."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    stats = {}

    # Quality distributions
    for field in ('entry_quality', 'exit_quality', 'timing_assessment', 'news_accuracy', 'confidence_was'):
        cursor.execute(f"SELECT {field}, COUNT(*) FROM post_trade_analysis WHERE {field} != '' GROUP BY {field}")
        stats[field] = {r[0]: r[1] for r in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) FROM post_trade_analysis")
    stats['total'] = cursor.fetchone()[0]

    conn.close()
    return stats


def save_learning_insight(category, insight, data=None, action_taken=None):
    """Save a learning insight."""
    import json
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO learning_insights (category, insight, data, action_taken, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (category, insight, json.dumps(data) if data else None, action_taken, now_ar()))
    conn.commit()
    conn.close()


def get_learning_insights(limit=20):
    """Get recent learning insights."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM learning_insights ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_unsynced_insights(limit=50):
    """Get learning insights not yet synced to cloud."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM learning_insights
        WHERE (synced_to_cloud IS NULL OR synced_to_cloud = 0)
          AND category NOT LIKE 'shared_%'
        ORDER BY id ASC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def mark_insights_synced(ids):
    """Mark insights as synced to cloud."""
    if not ids:
        return
    conn = sqlite3.connect(DB_PATH)
    placeholders = ','.join('?' * len(ids))
    conn.execute(f"UPDATE learning_insights SET synced_to_cloud = 1 WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()


def get_learning_adjustments():
    """Get actionable learning adjustments for strategy generation.
    Returns dict with confidence penalties/bonuses by trigger, session, and blocked patterns."""
    import json
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    adjustments = {
        'session_penalties': {},      # e.g. {'off': -15, 'london': +5}
        'trigger_penalties': {},      # e.g. {'news': -10, 'smc': +5}
        'news_category_penalties': {},# e.g. {'geopolitical': -10, 'inflation': +5}
        'blocked_patterns': [],       # patterns to avoid
        'sl_tp_advice': {},           # e.g. {'news': 'increase_sl', 'structure': 'ok'}
    }
    try:
        # Get most recent insights by category (last 48h)
        cutoff = (datetime.now(TZ_AR) - timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            SELECT category, insight, data FROM learning_insights
            WHERE created_at > ? ORDER BY created_at DESC
        """, (cutoff,))
        for row in cursor.fetchall():
            cat, insight, raw_data = row[0], row[1], row[2]
            data = json.loads(raw_data) if raw_data else {}

            # Shared insights have reduced weight (prefixed with 'shared_')
            is_shared = cat.startswith('shared_')
            weight = 0.5 if is_shared else 1.0
            base_cat = cat.replace('shared_', '') if is_shared else cat
            # Shared insights require more trades for significance
            min_trades = 10 if is_shared else 3

            if base_cat == 'session':
                session = data.get('session', '')
                wr = data.get('win_rate', 50)
                total = data.get('total', 0) or data.get('trades', 0)
                ev = data.get('expected_value', None)
                if total >= min_trades:
                    # Use expected value if available, otherwise fall back to WR
                    if ev is not None:
                        if ev < -1.0:
                            penalty = int(-15 * weight)
                            if session not in adjustments['session_penalties'] or not is_shared:
                                adjustments['session_penalties'][session] = penalty
                        elif ev > 1.0:
                            bonus = int(10 * weight)  # balanced with -15 penalty
                            if session not in adjustments['session_penalties'] or not is_shared:
                                adjustments['session_penalties'][session] = bonus
                    else:
                        if wr < 20:
                            penalty = int(-15 * weight)
                            if session not in adjustments['session_penalties'] or not is_shared:
                                adjustments['session_penalties'][session] = penalty
                        elif wr > 65:
                            bonus = int(10 * weight)  # balanced with -15 penalty
                            if session not in adjustments['session_penalties'] or not is_shared:
                                adjustments['session_penalties'][session] = bonus

            elif base_cat == 'sl_tp':
                trigger = data.get('trigger_type', '')
                rec = data.get('recommendation', '')
                if trigger and rec:
                    if trigger not in adjustments['sl_tp_advice'] or not is_shared:
                        adjustments['sl_tp_advice'][trigger] = rec

            elif base_cat == 'pattern':
                if 'losing' in insight.lower() or 'bloquear' in insight.lower() or 'perdedor' in insight.lower():
                    # Reconstruct pattern key from individual fields
                    _d = data.get('direction', '')
                    _h = data.get('htf_bias', 'unknown')
                    _s = data.get('session', 'unknown')
                    _t = data.get('trigger', 'unknown')
                    if _d:
                        pattern_key = f"{_d}|{_h}|{_s}|{_t}"
                        if pattern_key not in adjustments['blocked_patterns']:
                            adjustments['blocked_patterns'].append(pattern_key)

            elif base_cat == 'trigger_type':
                trigger = data.get('trigger_type', '')
                wr = data.get('win_rate', 50)
                total = data.get('total', 0)
                ev = data.get('expected_value', None)
                if total >= min_trades:
                    if ev is not None:
                        if ev < -1.0:
                            penalty = int(-15 * weight)
                            if trigger not in adjustments['trigger_penalties'] or not is_shared:
                                adjustments['trigger_penalties'][trigger] = penalty
                        elif ev > 1.0:
                            bonus = int(10 * weight)  # balanced with -15 penalty
                            if trigger not in adjustments['trigger_penalties'] or not is_shared:
                                adjustments['trigger_penalties'][trigger] = bonus
                    else:
                        if wr < 20:
                            penalty = int(-15 * weight)
                            if trigger not in adjustments['trigger_penalties'] or not is_shared:
                                adjustments['trigger_penalties'][trigger] = penalty
                        elif wr > 65:
                            bonus = int(10 * weight)  # balanced with -15 penalty
                            if trigger not in adjustments['trigger_penalties'] or not is_shared:
                                adjustments['trigger_penalties'][trigger] = bonus

            elif base_cat == 'news_category':
                ncat = data.get('news_category', '')
                wr = data.get('win_rate', 50)
                total = data.get('total', 0)
                ev = data.get('expected_value', None)
                if ncat and total >= min_trades:
                    if ev is not None:
                        if ev < -1.0:
                            penalty = int(-10 * weight)
                            if ncat not in adjustments['news_category_penalties'] or not is_shared:
                                adjustments['news_category_penalties'][ncat] = penalty
                        elif ev > 1.0:
                            bonus = int(8 * weight)
                            if ncat not in adjustments['news_category_penalties'] or not is_shared:
                                adjustments['news_category_penalties'][ncat] = bonus
                    else:
                        if wr < 20:
                            adjustments['news_category_penalties'][ncat] = int(-10 * weight)
                        elif wr > 65:
                            adjustments['news_category_penalties'][ncat] = int(8 * weight)

            elif base_cat == 'post_trade':
                # Gemma's post-trade analysis: aggregate confidence calibration signals
                # When Gemma consistently says "overestimated" for a trigger type, penalize it
                # When Gemma consistently says "accurate" + good quality, reward it
                _trigger = data.get('trigger_type', '')
                _conf_was = data.get('confidence_was', '')
                _entry_q = data.get('entry_quality', '')
                _exit_q = data.get('exit_quality', '')
                if _trigger:
                    # Small per-trade adjustments; accumulate across trades in last 48h
                    if _conf_was == 'overestimated':
                        cur = adjustments['trigger_penalties'].get(_trigger, 0)
                        adjustments['trigger_penalties'][_trigger] = cur - int(2 * weight)
                    elif _conf_was == 'accurate' and _entry_q == 'good' and _exit_q == 'good':
                        cur = adjustments['trigger_penalties'].get(_trigger, 0)
                        adjustments['trigger_penalties'][_trigger] = cur + int(1 * weight)
                    elif _conf_was == 'underestimated' and _entry_q in ('good', 'fair'):
                        cur = adjustments['trigger_penalties'].get(_trigger, 0)
                        adjustments['trigger_penalties'][_trigger] = cur + int(1 * weight)
    except Exception as _le:
        import logging as _log
        _log.getLogger('db').warning(f"get_learning_adjustments failed: {_le}", exc_info=True)

    # Compute EV-based adjustments directly from trade_archive (most reliable source)
    try:
        cursor2 = conn.cursor()
        # EV by trigger_type from trade_archive
        cursor2.execute("""
            SELECT trigger_type,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN result='win' THEN mt5_pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN result='loss' THEN mt5_pnl ELSE NULL END) as avg_loss
            FROM trade_archive WHERE trigger_type != 'mt5_recovered'
            GROUP BY trigger_type
        """)
        for tt, w, l, avg_w, avg_l in cursor2.fetchall():
            total = w + l
            if total >= 3:
                wr = w / total
                avg_w = avg_w or 0
                avg_l = avg_l or 0
                ev = wr * avg_w + (1 - wr) * avg_l  # EV per trade in $
                if tt not in adjustments['trigger_penalties']:
                    if ev < -1.0:
                        adjustments['trigger_penalties'][tt] = -15
                    elif ev > 1.0:
                        adjustments['trigger_penalties'][tt] = 10  # balanced with -15 penalty

        # EV by news_category from signal_results
        if not adjustments['news_category_penalties']:
            cursor2.execute("""
                SELECT news_category,
                    SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                    AVG(CASE WHEN result='win' THEN pips ELSE NULL END) as avg_win_pips,
                    AVG(CASE WHEN result='loss' THEN pips ELSE NULL END) as avg_loss_pips
                FROM signal_results
                WHERE news_category != '' AND news_category != 'other'
                  AND result IN ('win', 'loss')
                GROUP BY news_category
            """)
            for nc, w, l, avg_wp, avg_lp in cursor2.fetchall():
                total = w + l
                if total >= 3:
                    wr = w / total
                    avg_wp = avg_wp or 0
                    avg_lp = avg_lp or 0
                    ev_pips = wr * avg_wp + (1 - wr) * avg_lp
                    if ev_pips < -2.0:
                        adjustments['news_category_penalties'][nc] = -10
                    elif ev_pips > 2.0:
                        adjustments['news_category_penalties'][nc] = 8
    except Exception:
        pass

    conn.close()
    return adjustments


def save_learning_metric(metric_name, value, period='daily'):
    """Save a periodic metric snapshot."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO learning_metrics (metric_name, value, period, recorded_at)
        VALUES (?, ?, ?, ?)
    """, (metric_name, value, period, now_ar()))
    conn.commit()
    conn.close()


def get_learning_metrics(metric_name=None, period='daily', limit=60):
    """Get metric history for trend analysis."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if metric_name:
        cursor.execute("""
            SELECT * FROM learning_metrics
            WHERE metric_name = ? AND period = ?
            ORDER BY recorded_at DESC LIMIT ?
        """, (metric_name, period, limit))
    else:
        cursor.execute("""
            SELECT * FROM learning_metrics
            WHERE period = ?
            ORDER BY recorded_at DESC LIMIT ?
        """, (period, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ── Shared Learning Functions ──

def get_shared_learning_config():
    """Get shared learning configuration."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT supabase_url, supabase_key, instance_id, instance_name, enabled, last_sync
        FROM shared_learning_config WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'supabase_url': row[0] or '',
            'supabase_key': row[1] or '',
            'instance_id': row[2] or '',
            'instance_name': row[3] or '',
            'enabled': bool(row[4]),
            'last_sync': row[5] or '',
        }
    return {'supabase_url': '', 'supabase_key': '', 'instance_id': '', 'instance_name': '', 'enabled': False, 'last_sync': ''}


def update_shared_learning_config(supabase_url=None, supabase_key=None, instance_name=None, enabled=None):
    """Update shared learning configuration from dashboard."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current = get_shared_learning_config()
    cursor.execute("""
        UPDATE shared_learning_config SET
            supabase_url = ?,
            supabase_key = ?,
            instance_name = ?,
            enabled = ?
        WHERE id = 1
    """, (
        supabase_url if supabase_url is not None else current['supabase_url'],
        supabase_key if supabase_key is not None else current['supabase_key'],
        instance_name if instance_name is not None else current['instance_name'],
        int(enabled) if enabled is not None else int(current['enabled']),
    ))
    conn.commit()
    conn.close()


def update_shared_learning_last_sync(timestamp):
    """Update last sync timestamp."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE shared_learning_config SET last_sync = ? WHERE id = 1", (timestamp,))
    conn.commit()
    conn.close()


def get_unsynced_trades(limit=50):
    """Get trades that haven't been synced to cloud yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM trade_archive
        WHERE synced_to_cloud = 0 AND result IN ('win', 'loss')
        ORDER BY created_at ASC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def mark_trades_synced(trade_ids):
    """Mark trades as synced to cloud."""
    if not trade_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(trade_ids))
    cursor.execute(f"UPDATE trade_archive SET synced_to_cloud = 1 WHERE id IN ({placeholders})", trade_ids)
    conn.commit()
    conn.close()


def get_synced_trade_count():
    """Get count of trades synced to cloud."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM trade_archive WHERE synced_to_cloud = 1")
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ── Shared Trade Cache (cross-instance learning) ──

def save_shared_trades(trades):
    """Bulk insert remote trades into shared_trade_cache. Skips duplicates by remote_id."""
    if not trades:
        return 0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted = 0
    for t in trades:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO shared_trade_cache
                    (remote_id, instance_id, direction, result, pips,
                     sl_pips, tp_pips, sl_hit, tp_hit,
                     confidence, trigger_type, setup_type,
                     session, hour_utc, day_of_week,
                     htf_bias, market_trend, rsi_at_entry,
                     volatility, news_category, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get('id'), t.get('instance_id'),
                t.get('direction'), t.get('result'), t.get('pips'),
                t.get('sl_pips'), t.get('tp_pips'),
                1 if t.get('sl_hit') else 0, 1 if t.get('tp_hit') else 0,
                t.get('confidence'), t.get('trigger_type'), t.get('setup_type'),
                t.get('session'), t.get('hour_utc'), t.get('day_of_week'),
                t.get('htf_bias'), t.get('market_trend'), t.get('rsi_at_entry'),
                t.get('volatility'), t.get('news_category'), t.get('created_at'),
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return inserted


def get_shared_trade_cache(limit=500):
    """Get cached shared trades from other instances, excluding weekends."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM shared_trade_cache
        WHERE result IN ('win', 'loss')
          AND day_of_week NOT IN (5, 6)
        ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_last_fetched_remote_id():
    """Get the last Supabase shared_trades ID we fetched."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT last_fetched_remote_id FROM shared_learning_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return (row[0] or 0) if row else 0


def update_last_fetched_remote_id(remote_id):
    """Update the last fetched Supabase ID cursor."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE shared_learning_config SET last_fetched_remote_id = ? WHERE id = 1", (remote_id,))
    conn.commit()
    conn.close()


# ── App State Persistence ──

def save_last_session(username=None, password_hash=None, mt5_account=None, mt5_password=None, mt5_server=None):
    """Save last login session and/or MT5 credentials for auto-reconnect."""
    conn = sqlite3.connect(DB_PATH)
    fields = []
    values = []
    if username is not None:
        fields.append("last_username = ?")
        values.append(username)
    if password_hash is not None:
        fields.append("last_password_hash = ?")
        values.append(password_hash)
    if mt5_account is not None:
        fields.append("mt5_account = ?")
        values.append(int(mt5_account))
    if mt5_password is not None:
        fields.append("mt5_password = ?")
        values.append(mt5_password)
    if mt5_server is not None:
        fields.append("mt5_server = ?")
        values.append(mt5_server)
    if fields:
        fields.append("updated_at = datetime('now')")
        conn.execute(f"UPDATE app_state SET {', '.join(fields)} WHERE id = 1", values)
        conn.commit()
    conn.close()


def get_last_session():
    """Get saved session data for auto-login and MT5 auto-connect."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM app_state WHERE id = 1").fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def clear_last_session():
    """Clear saved session (on disconnect/logout)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE app_state SET last_username = NULL, last_password_hash = NULL, updated_at = datetime('now') WHERE id = 1")
    conn.commit()
    conn.close()
