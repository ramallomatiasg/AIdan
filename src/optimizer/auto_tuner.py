"""
Auto-Tuner: autonomous parameter optimization inspired by Karpathy's autoresearch.
Runs periodically, analyzes historical trade results, and adjusts strategy parameters
to maximize win rate. The loop:
  1. Read historical results from DB
  2. Test parameter variations against past trades (backtest)
  3. If a variation beats current config → adopt it
  4. Store optimized params in DB for analyzers to read
"""
import json
import time
import sqlite3
from datetime import datetime, timedelta, timezone

TZ_AR = timezone(timedelta(hours=-3))

# ── Default parameter space (what we optimize) ──
DEFAULT_PARAMS = {
    # Breakout/breakdown
    'breakout_dist_max': 15,        # max pips from level to count as breakout
    'breakdown_dist_max': 15,

    # RSI reversal
    'rsi_oversold': 30,             # RSI threshold for oversold
    'rsi_overbought': 70,           # RSI threshold for overbought
    'rsi_proximity_pips': 12,       # max pips from S/R for RSI reversal

    # Bollinger Band
    'bb_proximity_pips': 8,         # max pips from BB edge
    'bb_sr_proximity_pips': 15,     # max pips from nearest S/R for BB signal

    # Momentum expansion
    'momentum_consol_max_avg': 10,  # max avg range (pips) to count as consolidation
    'momentum_expansion_mult': 1.8, # expansion must be this * avg consolidation
    'momentum_min_body_pips': 2,    # min candle body for momentum signal

    # Trend continuation
    'trend_cont_proximity_pips': 15,  # max pips from S/R for trend continuation

    # Level bounce/rejection
    'level_proximity_pips': 5,      # max pips from level for bounce/rejection

    # Confidence base values (legacy — dynamic_conf() ignores these now,
    # kept only for backward compatibility with tuner DB records)
    'conf_breakout': 0,
    'conf_rsi_reversal': 0,
    'conf_bb_rejection': 0,
    'conf_momentum': 0,
    'conf_ma_crossover': 0,
    'conf_trend_cont': 0,
    'conf_level_bounce': 0,

    # Session filter (hours in UTC)
    'session_london_start': 7,
    'session_london_end': 12,
    'session_ny_start': 12,
    'session_ny_end': 17,
    'block_outside_sessions': False,

    # Setup blocker
    'min_trades_to_block': 5,       # need this many trades to block a setup
    'block_win_rate_threshold': 35,  # block setups below this win rate

    # Auto-eval minimum movement
    'min_pips_for_win': 1.5,        # don't count as win if moved < this

    # SL/TP learning params (updated by LearningEngine)
    'sl_atr_multiplier': 1.2,       # ATR multiplier for SL calculation
    'tp_rr_ratio': 2.0,             # minimum risk:reward ratio
    'sl_min_pips_high_vol': 5.0,    # min SL pips in high volatility
    'sl_min_pips_low_vol': 3.0,     # min SL pips in low volatility
}

# Parameter variations to test (relative to current value)
VARIATIONS = {
    'rsi_oversold': [25, 28, 30, 32, 35],
    'rsi_overbought': [65, 68, 70, 72, 75],
    'rsi_proximity_pips': [8, 10, 12, 15],
    'bb_proximity_pips': [5, 6, 8, 10, 12],
    'bb_sr_proximity_pips': [10, 12, 15, 18],
    'breakout_dist_max': [10, 12, 15, 18],
    'momentum_consol_max_avg': [6, 8, 10, 12],
    'momentum_expansion_mult': [1.5, 1.8, 2.0, 2.5],
    'level_proximity_pips': [3, 4, 5, 7, 8],
    'trend_cont_proximity_pips': [10, 12, 15, 18],
    'conf_breakout': [65, 68, 70, 72, 75],
    'conf_rsi_reversal': [65, 68, 70, 72, 75],
    'conf_bb_rejection': [62, 65, 68, 70, 72],
    'conf_momentum': [65, 68, 70, 72, 75],
    'conf_ma_crossover': [60, 62, 65, 68, 70],
    'conf_trend_cont': [55, 58, 60, 62, 65],
    'conf_level_bounce': [50, 52, 55, 58, 60],
    'min_pips_for_win': [0.5, 1.0, 1.5, 2.0, 3.0],
    'block_win_rate_threshold': [30, 35, 40, 45],
    'sl_atr_multiplier': [1.0, 1.2, 1.5, 1.8, 2.0],
    'tp_rr_ratio': [1.5, 2.0, 2.5, 3.0],
    'sl_min_pips_high_vol': [4.0, 5.0, 6.0, 7.0],
    'sl_min_pips_low_vol': [2.0, 3.0, 4.0, 5.0],
}


class AutoTuner:
    """
    Autonomous parameter optimizer.
    Analyzes trade history and finds optimal parameters via backtest.
    """

    def __init__(self, logger, db_path=None):
        self.logger = logger
        if db_path is None:
            from src.common.db import DB_PATH
            db_path = DB_PATH
        self.db_path = db_path
        self._current_params = dict(DEFAULT_PARAMS)
        self._last_run = 0
        self._run_interval = 30 * 60  # run every 30 minutes
        self._init_db_table()
        self._load_params()

    def _init_db_table(self):
        """Create optimizer_params table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS optimizer_params (
                id INTEGER PRIMARY KEY,
                params TEXT,
                win_rate REAL,
                total_trades INTEGER,
                profit_factor REAL,
                updated_at TIMESTAMP,
                iteration INTEGER DEFAULT 0
            )
        """)
        # Also create blocked_setups table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocked_setups (
                setup_type TEXT PRIMARY KEY,
                win_rate REAL,
                total_trades INTEGER,
                blocked_at TIMESTAMP,
                reason TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _load_params(self):
        """Load latest optimized params from DB, or use defaults."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT params FROM optimizer_params
                ORDER BY updated_at DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                saved = json.loads(row[0])
                # Merge with defaults (in case new params were added)
                merged = dict(DEFAULT_PARAMS)
                merged.update(saved)
                self._current_params = merged
                self.logger.info(f"AutoTuner: loaded optimized params (iteration {self._get_iteration()})")
            else:
                self.logger.info("AutoTuner: using default params (no history yet)")
        except Exception as e:
            self.logger.warning(f"AutoTuner: load params failed: {e}")
        finally:
            conn.close()

    def _get_iteration(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT MAX(iteration) FROM optimizer_params")
            row = cursor.fetchone()
            return (row[0] or 0) if row else 0
        except Exception:
            return 0
        finally:
            conn.close()

    def _save_params(self, params, win_rate, total_trades, profit_factor):
        """Save optimized params to DB."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        iteration = self._get_iteration() + 1
        now = datetime.now(TZ_AR).replace(tzinfo=None)
        cursor.execute("""
            INSERT INTO optimizer_params (params, win_rate, total_trades, profit_factor, updated_at, iteration)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (json.dumps(params), win_rate, total_trades, profit_factor, now, iteration))
        conn.commit()
        conn.close()
        self.logger.info(f"AutoTuner: saved params iteration #{iteration} (WR={win_rate:.1f}%, PF={profit_factor:.2f})")

    def get_params(self):
        """Get current optimized parameters. Called by analyzers."""
        return dict(self._current_params)

    def is_setup_blocked(self, setup_type):
        """Check if a setup type is currently blocked due to poor performance."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT win_rate FROM blocked_setups WHERE setup_type = ?", (setup_type,))
            row = cursor.fetchone()
            return row is not None
        except Exception:
            return False
        finally:
            conn.close()

    def get_blocked_setups(self):
        """Get all currently blocked setup types."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT setup_type, win_rate, total_trades, reason FROM blocked_setups")
            return [{'setup_type': r[0], 'win_rate': r[1], 'total': r[2], 'reason': r[3]}
                    for r in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    def _get_trade_history(self):
        """Get all evaluated trades with full context."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        trades = []
        try:
            # Strategy results (structure/smc signals)
            cursor.execute("""
                SELECT sr.result, sr.direction, sr.confidence, sr.setup_type,
                       sr.trigger_type, sr.market_trend, sr.rsi_at_entry, sr.htf_bias,
                       sr.entry_price, sr.exit_price, sr.pips, sr.recorded_at,
                       s.created_at
                FROM strategy_results sr
                LEFT JOIN auto_strategies s ON sr.strategy_id = s.id
                WHERE sr.result IN ('win', 'loss')
                ORDER BY sr.recorded_at DESC
                LIMIT 200
            """)
            for row in cursor.fetchall():
                trades.append({
                    'result': row[0], 'direction': row[1] or '', 'confidence': row[2] or 0,
                    'setup_type': row[3] or '', 'trigger_type': row[4] or '',
                    'market_trend': row[5] or '', 'rsi': row[6] or 50,
                    'htf_bias': row[7] or '', 'entry_price': row[8] or 0,
                    'exit_price': row[9] or 0, 'pips': row[10] or 0,
                    'recorded_at': row[11] or '', 'created_at': row[12] or ''
                })
        except Exception as e:
            self.logger.warning(f"AutoTuner: trade history query failed: {e}")
        finally:
            conn.close()
        return trades

    def _evaluate_params(self, params, trades):
        """
        Evaluate a parameter set against historical trades.
        Returns (win_rate, profit_factor, total_filtered).
        Simulates which trades would have been taken with these params.
        """
        if not trades:
            return 0, 0, 0

        wins = 0
        losses = 0
        total_profit = 0
        total_loss = 0
        min_pips = params.get('min_pips_for_win', 1.5)

        for t in trades:
            setup = t['setup_type']
            pips = t['pips']

            # Would this trade pass the confidence filter?
            conf_key = self._setup_to_conf_key(setup)
            if conf_key and t['confidence'] < params.get(conf_key, 50):
                continue  # wouldn't have been taken

            # Apply minimum pips filter
            if t['result'] == 'win' and abs(pips) < min_pips:
                # Reclassify as loss (too small to count)
                losses += 1
                total_loss += abs(pips) if pips != 0 else 1
                continue

            if t['result'] == 'win':
                wins += 1
                total_profit += abs(pips) if pips != 0 else 1
            else:
                losses += 1
                total_loss += abs(pips) if pips != 0 else 1

        total = wins + losses
        if total == 0:
            return 0, 0, 0

        win_rate = wins / total * 100
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 99.0
        return win_rate, profit_factor, total

    def _setup_to_conf_key(self, setup_type):
        """Map setup_type to its confidence parameter key."""
        mapping = {
            'breakout_resistance': 'conf_breakout',
            'breakdown_support': 'conf_breakout',
            'rsi_reversal_support': 'conf_rsi_reversal',
            'rsi_reversal_resistance': 'conf_rsi_reversal',
            'bb_rejection_upper': 'conf_bb_rejection',
            'bb_rejection_lower': 'conf_bb_rejection',
            'momentum_expansion': 'conf_momentum',
            'ma_crossover_bull': 'conf_ma_crossover',
            'ma_crossover_bear': 'conf_ma_crossover',
            'trend_continuation_bull': 'conf_trend_cont',
            'trend_continuation_bear': 'conf_trend_cont',
            'level_bounce': 'conf_level_bounce',
            'level_rejection': 'conf_level_bounce',
        }
        return mapping.get(setup_type)

    def _update_blocked_setups(self, trades):
        """Block setup types with consistently poor win rates."""
        from src.common.db import get_setup_win_rates
        rates = get_setup_win_rates()
        params = self._current_params
        min_trades = params.get('min_trades_to_block', 5)
        threshold = params.get('block_win_rate_threshold', 35)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now(TZ_AR).replace(tzinfo=None)

        # Clear old blocks (re-evaluate each time)
        cursor.execute("DELETE FROM blocked_setups")

        blocked = []
        for setup_type, stats in rates.items():
            if stats['total'] >= min_trades and stats['win_rate'] < threshold:
                cursor.execute("""
                    INSERT OR REPLACE INTO blocked_setups
                    (setup_type, win_rate, total_trades, blocked_at, reason)
                    VALUES (?, ?, ?, ?, ?)
                """, (setup_type, stats['win_rate'], stats['total'], now,
                      f"WR {stats['win_rate']:.0f}% < {threshold}% ({stats['total']} trades)"))
                blocked.append(f"{setup_type} ({stats['win_rate']:.0f}%)")

        conn.commit()
        conn.close()

        if blocked:
            self.logger.info(f"AutoTuner: blocked setups: {', '.join(blocked)}")
        return blocked

    def _get_session_stats(self, trades):
        """Analyze win rate by trading session (London, NY, off-hours)."""
        sessions = {'london': {'w': 0, 'l': 0}, 'ny': {'w': 0, 'l': 0}, 'off': {'w': 0, 'l': 0}}
        params = self._current_params

        for t in trades:
            ts = t.get('created_at', '') or t.get('recorded_at', '')
            if not ts:
                continue
            try:
                dt_obj = datetime.strptime(str(ts).split('.')[0], '%Y-%m-%d %H:%M:%S')
                # Convert AR time (UTC-3) to UTC hour
                utc_hour = (dt_obj.hour + 3) % 24
            except Exception:
                continue

            if params['session_london_start'] <= utc_hour < params['session_london_end']:
                session = 'london'
            elif params['session_ny_start'] <= utc_hour < params['session_ny_end']:
                session = 'ny'
            else:
                session = 'off'

            if t['result'] == 'win':
                sessions[session]['w'] += 1
            else:
                sessions[session]['l'] += 1

        result = {}
        for s, stats in sessions.items():
            total = stats['w'] + stats['l']
            result[s] = {
                'wins': stats['w'], 'losses': stats['l'], 'total': total,
                'win_rate': round(stats['w'] / total * 100, 1) if total > 0 else 0
            }
        return result

    def run_optimization(self, force=False):
        """
        Main optimization loop. Call periodically.
        Tests parameter variations and adopts the best one.
        Returns dict with optimization results.
        """
        now = time.time()
        if not force and (now - self._last_run) < self._run_interval:
            return None  # too soon

        self._last_run = now
        self.logger.info("AutoTuner: starting optimization cycle...")

        trades = self._get_trade_history()
        if len(trades) < 3:
            self.logger.info(f"AutoTuner: only {len(trades)} trades, need 3+ to optimize. Skipping.")
            return {'status': 'insufficient_data', 'trades': len(trades)}

        # Evaluate current params as baseline
        base_wr, base_pf, base_total = self._evaluate_params(self._current_params, trades)
        self.logger.info(f"AutoTuner: baseline WR={base_wr:.1f}% PF={base_pf:.2f} ({base_total} trades)")

        best_params = dict(self._current_params)
        best_wr = base_wr
        best_pf = base_pf
        improvements = []

        # Test each parameter variation independently
        for param_name, values in VARIATIONS.items():
            for val in values:
                if val == self._current_params.get(param_name):
                    continue  # skip current value

                test_params = dict(self._current_params)
                test_params[param_name] = val
                wr, pf, total = self._evaluate_params(test_params, trades)

                # Better if: higher win rate with acceptable profit factor
                # or similar win rate with much better profit factor
                if total >= 3 and wr > best_wr + 1.0:  # at least 1% improvement
                    best_wr = wr
                    best_pf = pf
                    best_params[param_name] = val
                    improvements.append(f"{param_name}: {self._current_params.get(param_name)} → {val} (WR +{wr - base_wr:.1f}%)")

        # Update blocked setups
        blocked = self._update_blocked_setups(trades)

        # Session analysis
        session_stats = self._get_session_stats(trades)
        off_wr = session_stats.get('off', {}).get('win_rate', 50)
        off_total = session_stats.get('off', {}).get('total', 0)
        if off_total >= 3 and off_wr < 35:
            best_params['block_outside_sessions'] = True
            improvements.append(f"block_outside_sessions: False → True (off-hours WR={off_wr:.0f}%)")

        # Save if improved
        if improvements:
            self._current_params = best_params
            self._save_params(best_params, best_wr, len(trades), best_pf)
            self.logger.info(f"AutoTuner: {len(improvements)} improvements found!")
            for imp in improvements:
                self.logger.info(f"  → {imp}")
        else:
            self.logger.info("AutoTuner: no improvements found, keeping current params")

        result = {
            'status': 'completed',
            'baseline_wr': round(base_wr, 1),
            'optimized_wr': round(best_wr, 1),
            'improvements': improvements,
            'blocked_setups': blocked,
            'session_stats': session_stats,
            'total_trades': len(trades),
            'iteration': self._get_iteration()
        }
        self.logger.info(f"AutoTuner: cycle complete. {json.dumps(result, default=str)}")
        return result

    def get_status(self):
        """Get current tuner status for dashboard display."""
        trades = self._get_trade_history()
        base_wr, base_pf, base_total = self._evaluate_params(self._current_params, trades)
        return {
            'iteration': self._get_iteration(),
            'current_wr': round(base_wr, 1),
            'profit_factor': round(base_pf, 2),
            'total_trades': len(trades),
            'blocked_setups': self.get_blocked_setups(),
            'params': self._current_params,
            'last_run': self._last_run,
        }
