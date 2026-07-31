"""
Slippage tracker + spread guardian.

Persiste cada fill: expected_price (orden) vs actual_price (fill) y spread real.
Permite spread guardian: bloquear entries si spread > MAX.
"""
import sqlite3
import logging

logger = logging.getLogger(__name__)


def _ensure_table():
    try:
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slippage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER,
                expected_price REAL,
                actual_price REAL,
                slippage_pips REAL,
                spread_pips REAL,
                direction TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"slippage_log create: {e}")


def log_fill(strategy_id, expected_price, actual_price, direction, spread_pips=None):
    """Log a fill with slippage data."""
    try:
        _ensure_table()
        from src.common.db import DB_PATH
        # Slippage pips (positive = peor de lo esperado)
        if direction == 'CALL':
            slippage_pips = (actual_price - expected_price) * 10000
        else:
            slippage_pips = (expected_price - actual_price) * 10000
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        conn.execute("""
            INSERT INTO slippage_log
            (strategy_id, expected_price, actual_price, slippage_pips, spread_pips, direction)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (strategy_id, expected_price, actual_price,
              round(slippage_pips, 2), round(spread_pips, 2) if spread_pips else None, direction))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"log_fill: {e}")


def get_current_spread_pips(mt5_module):
    """Returns current EUR/USD spread in pips, or None on error."""
    try:
        tick = mt5_module.symbol_info_tick("EURUSD")
        if tick:
            return round((tick.ask - tick.bid) * 10000, 2)
    except Exception:
        pass
    return None


def is_spread_acceptable(mt5_module, max_pips=2.5):
    """Check if current spread is acceptable for entry. Returns (ok, current_spread)."""
    spread = get_current_spread_pips(mt5_module)
    if spread is None:
        return True, None  # benefit of the doubt
    return spread <= max_pips, spread


def get_slippage_stats(days=7):
    """Aggregate slippage stats for last N days."""
    try:
        _ensure_table()
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*),
                   AVG(slippage_pips),
                   MAX(slippage_pips),
                   AVG(spread_pips)
            FROM slippage_log
            WHERE timestamp >= datetime('now', ?)
        """, (f'-{days} days',))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return {
                'count': row[0],
                'avg_slippage_pips': round(row[1] or 0, 2),
                'max_slippage_pips': round(row[2] or 0, 2),
                'avg_spread_pips': round(row[3] or 0, 2),
            }
    except Exception as e:
        logger.debug(f"slippage stats: {e}")
    return {'count': 0}
