"""
MT5 Executor — Connects to MetaTrader 5 and executes trades for AIdan strategies.
"""
import os
import glob
import time

MAGIC_NUMBER = 20260402  # Identifies AIdan orders in MT5


def _find_mt5_terminal():
    """Auto-detect MT5 terminal64.exe path."""
    # Check known IC Markets path first
    known = r'C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe'
    if os.path.isfile(known):
        return known

    candidates = []
    for base in [
        os.environ.get('PROGRAMFILES', 'C:\\Program Files'),
        os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'),
    ]:
        pattern = os.path.join(base, 'MetaTrader*', 'terminal64.exe')
        candidates.extend(glob.glob(pattern))
    # Prefer IC Markets path
    for c in candidates:
        if 'ICMarkets' in c or 'IC Markets' in c:
            return c
    return candidates[0] if candidates else None


class MT5Executor:
    def __init__(self, logger):
        self.logger = logger
        self.connected = False
        self.kill_switch = False
        self._mt5 = None
        self._terminal_path = None
        self._smc_ref = None  # Set by main loop to enable htf_bias lookup

    def set_smc_ref(self, smc):
        """Inject SMC reference so we can read htf_bias when archiving trades."""
        self._smc_ref = smc

    def connect(self):
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5

            # Try to find terminal path for frozen exe compatibility
            if not self._terminal_path:
                self._terminal_path = _find_mt5_terminal()
                if self._terminal_path:
                    self.logger.info(f"MT5 terminal found: {self._terminal_path}")

            # Initialize with explicit path if available
            init_ok = False
            if self._terminal_path:
                init_ok = mt5.initialize(self._terminal_path)
            if not init_ok:
                init_ok = mt5.initialize()
            if not init_ok:
                err = mt5.last_error()
                self.logger.error(f"MT5 initialize failed: {err}")
                return False

            from src.common.config import Config
            if Config.MT5_ACCOUNT and Config.MT5_PASSWORD:
                if not mt5.login(Config.MT5_ACCOUNT, Config.MT5_PASSWORD, Config.MT5_SERVER):
                    err = mt5.last_error()
                    self.logger.error(f"MT5 login failed: {err}")
                    mt5.shutdown()
                    return False

            info = mt5.account_info()
            if info:
                mode = "Demo" if info.trade_mode == 0 else "Real"
                self.logger.info(f"MT5 connected: {info.login} ({mode}) ${info.balance:.2f} | {Config.MT5_SERVER}")
                self.connected = True
                return True
            else:
                self.logger.error("MT5 account_info() returned None")
                mt5.shutdown()
                return False

        except ImportError:
            self.logger.warning("MetaTrader5 package not installed")
            return False
        except Exception as e:
            self.logger.error(f"MT5 connect error: {e}")
            return False

    def disconnect(self):
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception as e:
                self.logger.debug(f"MT5 shutdown: {e}")
        self.connected = False

    def reconnect(self, account, password, server):
        self.disconnect()
        from src.common.config import Config
        Config.MT5_ACCOUNT = int(account)
        Config.MT5_PASSWORD = password
        Config.MT5_SERVER = server
        return self.connect()

    def is_ready(self):
        return self.connected and not self.kill_switch

    def get_account_info(self):
        if not self.connected or not self._mt5:
            return None
        try:
            info = self._mt5.account_info()
            if info:
                return {
                    'login': info.login,
                    'server': info.server,
                    'name': info.name,
                    'balance': info.balance,
                    'equity': info.equity,
                    'margin': info.margin,
                    'free_margin': info.margin_free,
                    'leverage': info.leverage,
                    'currency': info.currency,
                    'trade_mode': 'Demo' if info.trade_mode == 0 else 'Real',
                }
        except Exception as e:
            self.logger.debug(f"MT5 account_info: {e}")
        return None

    def calculate_lot_size(self, sl_pips):
        from src.common.db import get_mt5_config
        config = get_mt5_config()
        risk_percent = config['risk_percent']
        max_lot = config['max_lot']

        info = self._mt5.account_info()
        if not info:
            return 0.01

        balance = info.balance
        risk_amount = balance * (risk_percent / 100.0)
        pip_value_per_lot = 10.0  # EURUSD standard
        sl_pips = max(sl_pips, 1.0)

        lots = risk_amount / (sl_pips * pip_value_per_lot)
        lots = max(0.01, min(lots, max_lot))
        return round(lots, 2)

    def open_position(self, strategy_id, direction, entry_price, sl, tp, confidence):
        """Open position: tries limit order first (better price), falls back to market."""
        if not self.is_ready() or not self._mt5:
            return None

        from src.common.db import get_mt5_config, get_strategies_with_open_mt5, update_mt5_ticket
        config = get_mt5_config()

        # Guard: max positions
        open_positions = self._mt5.positions_get(group="*")
        aidan_positions = [p for p in (open_positions or []) if p.magic == MAGIC_NUMBER]
        if len(aidan_positions) >= config['max_positions']:
            self.logger.info(f"MT5: max positions reached ({len(aidan_positions)}/{config['max_positions']})")
            return None

        from src.common.config import Config
        symbol = Config.MT5_SYMBOL

        # Get real broker price
        tick = self._mt5.symbol_info_tick(symbol)
        if not tick:
            self.logger.error(f"MT5: no tick data for {symbol}")
            update_mt5_ticket(strategy_id, None, 0, 'error')
            return None

        # Calculate distances and lot size first
        sl_distance = abs(entry_price - sl)
        tp_distance = abs(entry_price - tp)
        sl_pips = sl_distance / 0.0001
        lot = self.calculate_lot_size(sl_pips)

        # Pre-flight: retry up to 3 times if spread > SL distance (news event spikes)
        current_spread = abs(tick.ask - tick.bid)
        if current_spread >= sl_distance:
            self.logger.info(f"MT5: spread spike {current_spread/0.0001:.1f}p >= SL {sl_pips:.1f}p — retrying for #{strategy_id}")
            retried = False
            for _retry in range(3):
                time.sleep(0.5)  # brief wait for spread to normalize
                tick = self._mt5.symbol_info_tick(symbol)
                if not tick:
                    continue
                current_spread = abs(tick.ask - tick.bid)
                if current_spread < sl_distance:
                    retried = True
                    self.logger.info(f"MT5: spread normalized to {current_spread/0.0001:.1f}p after retry — proceeding #{strategy_id}")
                    break
            if not retried:
                self.logger.warning(f"MT5: spread {current_spread/0.0001:.1f}p still >= SL {sl_pips:.1f}p after 3 retries — skipping #{strategy_id}")
                update_mt5_ticket(strategy_id, None, 0, 'error')
                return None

        # Try limit order first for better entry price
        LIMIT_DISCOUNT_PIPS = 1.5  # pips discount from current price
        discount = LIMIT_DISCOUNT_PIPS * 0.0001
        ticket = self._try_limit_order(strategy_id, direction, entry_price, sl_distance, tp_distance, lot, tick, symbol, discount)
        if ticket:
            return ticket

        # Fallback: immediate market order
        self.logger.info(f"MT5: limit order failed for #{strategy_id}, using market order")
        return self._market_order(strategy_id, direction, entry_price, sl_distance, tp_distance, lot, tick, symbol)

    def _try_limit_order(self, strategy_id, direction, entry_price, sl_distance, tp_distance, lot, tick, symbol, discount):
        """Place a limit order at a better price. Returns ticket or None."""
        from src.common.db import update_mt5_ticket
        from datetime import datetime, timezone, timedelta

        # Calculate limit price with discount
        if direction == 'CALL':
            limit_price = round(tick.ask - discount, 5)
            order_type = self._mt5.ORDER_TYPE_BUY_LIMIT
            adjusted_sl = round(limit_price - sl_distance, 5)
            adjusted_tp = round(limit_price + tp_distance, 5)
        else:
            limit_price = round(tick.bid + discount, 5)
            order_type = self._mt5.ORDER_TYPE_SELL_LIMIT
            adjusted_sl = round(limit_price + sl_distance, 5)
            adjusted_tp = round(limit_price - tp_distance, 5)

        # Expiration: 90 seconds from now
        expiration = datetime.now() + timedelta(seconds=90)
        # MT5 expects expiration as a datetime object or unix timestamp
        exp_timestamp = int(expiration.timestamp())

        # Detect filling mode
        sym_info = self._mt5.symbol_info(symbol)
        if sym_info and sym_info.filling_mode == 2:
            filling = self._mt5.ORDER_FILLING_RETURN
        else:
            filling = self._mt5.ORDER_FILLING_RETURN  # RETURN is typical for pending orders

        request = {
            "action": self._mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": limit_price,
            "sl": adjusted_sl,
            "tp": adjusted_tp,
            "magic": MAGIC_NUMBER,
            "comment": f"AIdan #{strategy_id} LMT",
            "type_time": self._mt5.ORDER_TIME_SPECIFIED,
            "expiration": exp_timestamp,
            "type_filling": filling,
        }

        try:
            result = self._mt5.order_send(request)
            if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
                order_ticket = result.order
                # Mark as 'pending' — trailing monitor will detect fill
                update_mt5_ticket(strategy_id, order_ticket, lot, 'pending', fill_price=limit_price)
                # Store adjusted SL/TP
                try:
                    import sqlite3
                    from src.common.db import DB_PATH
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("UPDATE auto_strategies SET stop_loss = ?, take_profit = ? WHERE id = ?",
                                 (adjusted_sl, adjusted_tp, strategy_id))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    self.logger.debug(f"Update SL/TP for limit: {e}")
                discount_pips = discount / 0.0001
                self.logger.info(
                    f"MT5 LIMIT ORDER: #{order_ticket} {direction} {lot} lot @ {limit_price:.5f} "
                    f"({discount_pips:+.1f}p vs market) SL={adjusted_sl:.5f} TP={adjusted_tp:.5f} "
                    f"expires=90s | Strategy #{strategy_id}")
                return order_ticket
            else:
                retcode = result.retcode if result else 'None'
                comment = result.comment if result else 'None'
                self.logger.info(f"MT5 limit order rejected: retcode={retcode} {comment} — falling back to market")
                return None
        except Exception as e:
            self.logger.warning(f"MT5 limit order error: {e} — falling back to market")
            return None

    def _market_order(self, strategy_id, direction, entry_price, sl_distance, tp_distance, lot, tick, symbol):
        """Place immediate market order (fallback)."""
        from src.common.db import update_mt5_ticket

        if direction == 'CALL':
            order_type = self._mt5.ORDER_TYPE_BUY
            price = tick.ask
            adjusted_sl = round(price - sl_distance, 5)
            adjusted_tp = round(price + tp_distance, 5)
        else:
            order_type = self._mt5.ORDER_TYPE_SELL
            price = tick.bid
            adjusted_sl = round(price + sl_distance, 5)
            adjusted_tp = round(price - tp_distance, 5)

        sym_info = self._mt5.symbol_info(symbol)
        if sym_info and sym_info.filling_mode == 1:
            filling = self._mt5.ORDER_FILLING_IOC
        elif sym_info and sym_info.filling_mode == 2:
            filling = self._mt5.ORDER_FILLING_RETURN
        else:
            filling = self._mt5.ORDER_FILLING_IOC

        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": adjusted_sl,
            "tp": adjusted_tp,
            "deviation": 50,  # points (0.1 pip each on 5-digit brokers) = 5 pips tolerance
            "magic": MAGIC_NUMBER,
            "comment": f"AIdan #{strategy_id}",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        # Try order_check first
        check = self._mt5.order_check(request)
        if check and check.retcode != 0:
            for alt_fill in [self._mt5.ORDER_FILLING_FOK, self._mt5.ORDER_FILLING_IOC, self._mt5.ORDER_FILLING_RETURN]:
                if alt_fill == filling:
                    continue
                request["type_filling"] = alt_fill
                check = self._mt5.order_check(request)
                if check and check.retcode == 0:
                    self.logger.info(f"MT5: switched filling mode for #{strategy_id}")
                    break

        result = self._mt5.order_send(request)

        if result is None:
            self.logger.error(f"MT5: order_send returned None for #{strategy_id}")
            update_mt5_ticket(strategy_id, None, 0, 'error')
            return None

        if result.retcode == self._mt5.TRADE_RETCODE_DONE:
            ticket = result.order
            update_mt5_ticket(strategy_id, ticket, lot, 'filled', fill_price=price)
            try:
                conn = __import__('sqlite3').connect(__import__('src.common.db', fromlist=['DB_PATH']).DB_PATH)
                conn.execute("UPDATE auto_strategies SET stop_loss = ?, take_profit = ? WHERE id = ?",
                             (adjusted_sl, adjusted_tp, strategy_id))
                conn.commit()
                conn.close()
            except Exception as e:
                self.logger.warning(f"MT5: could not update DB SL/TP for #{strategy_id}: {e}")
            self.logger.info(f"MT5 MARKET ORDER FILLED: #{ticket} {direction} {lot} lot @ {price:.5f} SL={adjusted_sl:.5f} TP={adjusted_tp:.5f} (signal={entry_price:.5f}) | Strategy #{strategy_id}")
            return ticket
        else:
            self.logger.error(f"MT5 order failed: retcode={result.retcode} comment={result.comment} | Strategy #{strategy_id}")
            update_mt5_ticket(strategy_id, None, 0, 'error')
            return None

    def get_candles(self, timeframe='5min', count=100):
        """Get candle data directly from MT5 (highest quality for chart)."""
        if not self.connected or not self._mt5:
            return None
        try:
            from src.common.config import Config
            symbol = Config.MT5_SYMBOL

            tf_map = {
                '1min': self._mt5.TIMEFRAME_M1,
                '5min': self._mt5.TIMEFRAME_M5,
                '15min': self._mt5.TIMEFRAME_M15,
                '30min': self._mt5.TIMEFRAME_M30,
                '1h': self._mt5.TIMEFRAME_H1,
                '4h': self._mt5.TIMEFRAME_H4,
                '1day': self._mt5.TIMEFRAME_D1,
            }
            tf = tf_map.get(timeframe, self._mt5.TIMEFRAME_M5)

            rates = self._mt5.copy_rates_from_pos(symbol, tf, 0, count)
            if rates is None or len(rates) == 0:
                return None

            candles = []
            for r in rates:
                candles.append({
                    'open': round(float(r['open']), 5),
                    'high': round(float(r['high']), 5),
                    'low': round(float(r['low']), 5),
                    'close': round(float(r['close']), 5),
                    'datetime': str(int(r['time'])),
                })
            return candles
        except Exception as e:
            self.logger.warning(f"MT5 get_candles error: {e}")
            return None

    def check_positions(self):
        if not self.connected or not self._mt5:
            return []
        positions = self._mt5.positions_get(group="*")
        if not positions:
            return []
        result = []
        for p in positions:
            if p.magic == MAGIC_NUMBER:
                result.append({
                    'ticket': p.ticket,
                    'symbol': p.symbol,
                    'type': 'BUY' if p.type == 0 else 'SELL',
                    'volume': p.volume,
                    'price_open': p.price_open,
                    'sl': p.sl,
                    'tp': p.tp,
                    'profit': p.profit,
                    'swap': p.swap,
                    'time': str(p.time),
                    'comment': p.comment,
                })
        return result

    def get_tick(self, symbol=None):
        """Get current bid/ask for a symbol."""
        if not self.connected or not self._mt5:
            return None
        if not symbol:
            from src.common.config import Config
            symbol = Config.MT5_SYMBOL
        tick = self._mt5.symbol_info_tick(symbol)
        if tick:
            return {'bid': tick.bid, 'ask': tick.ask}
        return None

    def modify_position_sl(self, ticket, new_sl):
        """Modify the SL of an open position using TRADE_ACTION_SLTP.
        Returns True on success, False on failure."""
        if not self.connected or not self._mt5:
            return False

        position = self._mt5.positions_get(ticket=ticket)
        if not position or len(position) == 0:
            return False

        p = position[0]
        request = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "position": p.ticket,
            "symbol": p.symbol,
            "sl": round(new_sl, 5),
            "tp": p.tp,  # Keep existing TP
        }

        result = self._mt5.order_send(request)
        if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
            self.logger.info(f"MT5 trailing SL: #{ticket} SL {p.sl:.5f} -> {new_sl:.5f}")
            return True
        else:
            retcode = result.retcode if result else 'None'
            comment = result.comment if result else 'None'
            self.logger.warning(f"MT5 modify SL failed: #{ticket} retcode={retcode} {comment}")
            return False

    def sync_pending_orders(self):
        """Check pending (limit) orders: detect fills or expirations."""
        if not self.connected or not self._mt5:
            return
        try:
            import sqlite3
            from src.common.db import DB_PATH, update_mt5_ticket
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, mt5_ticket, direction, mt5_lot
                FROM auto_strategies
                WHERE mt5_status = 'pending' AND mt5_ticket IS NOT NULL
            """)
            pending = cursor.fetchall()
            conn.close()

            for sid, ticket, direction, lot in pending:
                # Check if order is still pending
                orders = self._mt5.orders_get(ticket=ticket)
                if orders and len(orders) > 0:
                    # Still pending — do nothing
                    continue

                # Order no longer pending — check if it filled (became a position)
                positions = self._mt5.positions_get(ticket=ticket)
                if positions and len(positions) > 0:
                    # Filled! Update status
                    pos = positions[0]
                    fill_price = pos.price_open
                    update_mt5_ticket(sid, ticket, lot, 'filled', fill_price=fill_price)
                    self.logger.info(f"MT5 LIMIT FILLED: #{ticket} {direction} @ {fill_price:.5f} | Strategy #{sid}")
                else:
                    # Not pending, not a position — order expired or was cancelled
                    update_mt5_ticket(sid, ticket, lot, 'expired')
                    self.logger.info(f"MT5 LIMIT EXPIRED: #{ticket} {direction} — not filled within window | Strategy #{sid}")
        except Exception as e:
            self.logger.warning(f"MT5 sync_pending error: {e}")

    def sync_closed_positions(self):
        if not self.connected or not self._mt5:
            return

        # Sync pending limit orders FIRST so freshly filled limits get 'filled' status
        # before the orphan detector runs
        try:
            self.sync_pending_orders()
        except Exception:
            pass

        from src.common.db import get_strategies_with_open_mt5, update_mt5_close
        open_strategies = get_strategies_with_open_mt5()

        # Detect orphaned MT5 positions (AIdan magic but no matching strategy in DB)
        try:
            all_positions = self._mt5.positions_get(group="*") or []
            aidan_positions = [p for p in all_positions if p.magic == MAGIC_NUMBER]
            tracked_tickets = {row[1] for row in open_strategies}  # set of tracked tickets
            # Also include pending limit orders — they may have filled but sync_pending_orders
            # hasn't run yet. Without this, the orphan detector closes freshly filled limits.
            try:
                import sqlite3
                from src.common.db import DB_PATH
                _conn = sqlite3.connect(DB_PATH)
                _cur = _conn.cursor()
                _cur.execute("SELECT mt5_ticket FROM auto_strategies WHERE mt5_status = 'pending' AND mt5_ticket IS NOT NULL")
                for _row in _cur.fetchall():
                    tracked_tickets.add(_row[0])
                _conn.close()
            except Exception:
                pass
            for p in aidan_positions:
                if p.ticket not in tracked_tickets:
                    # Orphaned position — close it
                    close_type = self._mt5.ORDER_TYPE_SELL if p.type == 0 else self._mt5.ORDER_TYPE_BUY
                    tick = self._mt5.symbol_info_tick(p.symbol)
                    if not tick:
                        continue
                    close_price = tick.bid if p.type == 0 else tick.ask
                    request = {
                        "action": self._mt5.TRADE_ACTION_DEAL,
                        "symbol": p.symbol,
                        "volume": p.volume,
                        "type": close_type,
                        "position": p.ticket,
                        "price": close_price,
                        "deviation": 50,  # points (0.1 pip each on 5-digit brokers) = 5 pips tolerance
                        "magic": MAGIC_NUMBER,
                        "comment": "AIdan orphan close",
                        "type_time": self._mt5.ORDER_TIME_GTC,
                        "type_filling": self._mt5.ORDER_FILLING_IOC,
                    }
                    result = self._mt5.order_send(request)
                    if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
                        self.logger.info(f"MT5 orphan closed: #{p.ticket} ({p.comment}) @ {close_price:.5f}")
                    else:
                        self.logger.warning(f"MT5 orphan close failed: #{p.ticket} retcode={result.retcode if result else 'None'}")
        except Exception as e:
            self.logger.error(f"MT5 orphan check error: {e}")

        for row in open_strategies:
            sid, ticket, direction, entry_price, sl, tp, lot, created_at, news_title = row[:9]
            fill_price = row[10] if len(row) > 10 and row[10] else entry_price
            confidence = row[12] if len(row) > 12 and row[12] else 0

            # Check if position still exists in MT5
            position = self._mt5.positions_get(ticket=ticket)
            if position and len(position) > 0:
                continue  # Still open

            # Position closed — get deal history by position ID (most reliable)
            # Sum ALL deals (open + close) for true net P&L including both-side commissions
            pnl = 0.0
            close_price = 0.0

            deals = self._mt5.history_deals_get(position=ticket)
            if deals:
                for deal in deals:
                    pnl += deal.profit + deal.swap + deal.commission
                    if deal.entry == 1:  # close deal → get exit price
                        close_price = deal.price

            if not deals or close_price == 0:
                # Fallback: time-based search
                from datetime import datetime, timezone, timedelta
                time_from = datetime.now(timezone.utc) - timedelta(days=3)
                time_to = datetime.now(timezone.utc) + timedelta(hours=1)
                deals_fb = self._mt5.history_deals_get(time_from, time_to)
                if deals_fb:
                    for deal in deals_fb:
                        if deal.position_id == ticket:
                            pnl += deal.profit + deal.swap + deal.commission
                            if deal.entry == 1:
                                close_price = deal.price

            if close_price == 0:
                # Last resort: estimate from current price
                tick = self._mt5.symbol_info_tick("EURUSD")
                if tick:
                    close_price = tick.bid if direction == 'CALL' else tick.ask

            update_mt5_close(sid, pnl, close_price)
            self.logger.info(f"MT5 position closed: #{ticket} Strategy #{sid} P&L=${pnl:.2f} @ {close_price:.5f}")

            # v3.23.0 — Telegram alert (graceful: skip si no configurado)
            try:
                from src.common.telegram_alerts import send_trade_result, is_configured
                if is_configured():
                    # Get current balance
                    _bal = None
                    try:
                        info = self._mt5.account_info()
                        _bal = info.balance if info else None
                    except Exception:
                        pass
                    # Infer trigger_type
                    _tt_alert = 'structure'
                    if news_title:
                        _nt_a = news_title.upper()
                        if 'CALENDARIO' in _nt_a: _tt_alert = 'calendar'
                        elif 'SMC' in _nt_a: _tt_alert = 'smc'
                        elif 'NOTICIA' in _nt_a or 'NEWS' in _nt_a: _tt_alert = 'news'
                        elif 'M15-STRUCT' in _nt_a or 'M15' in _nt_a: _tt_alert = 'm15_structure'
                        elif 'H1-STRUCT' in _nt_a or 'H1' in _nt_a: _tt_alert = 'h1_structure'
                    send_trade_result(sid, direction, _tt_alert, pnl, confidence or 0, balance=_bal)
            except Exception as _te:
                self.logger.debug(f"Telegram alert skip: {_te}")

            # Immediate evaluation: don't wait for expiry
            try:
                from src.common.db import auto_evaluate_strategy
                pip = 0.0001
                if direction == 'CALL':
                    pips_result = round((close_price - fill_price) / pip, 1)
                else:
                    pips_result = round((fill_price - close_price) / pip, 1)
                result = 'win' if pnl > 0 else 'loss'
                # Infer trigger_type from news_title prefix
                _tt = 'structure'
                if news_title:
                    _nt = news_title.upper()
                    if 'CALENDARIO' in _nt: _tt = 'calendar'
                    elif 'SMC' in _nt: _tt = 'smc'
                    elif 'NOTICIA' in _nt: _tt = 'news'
                # Get current market state for trend context
                _mt5_trend = ''
                _mt5_trend_str = ''
                _mt5_htf = ''
                try:
                    from src.analyzer.technical import TechnicalAnalyzer
                    _t = TechnicalAnalyzer(self.logger)
                    _ms = _t.get_market_state()
                    _mt5_trend = _ms.get('trend', '')
                    _mt5_trend_str = _ms.get('trend_strength', '')
                except Exception:
                    pass
                # Fix: read htf_bias from SMC reference (previously always empty)
                try:
                    if self._smc_ref:
                        _mt5_htf = self._smc_ref.get_status().get('htf_bias', '') or ''
                except Exception:
                    pass
                ctx = {
                    'entry_price': entry_price,
                    'direction': direction,
                    'trigger_type': _tt,
                    'auto_evaluated': True,
                    'market_trend': _mt5_trend,
                    'trend_strength': _mt5_trend_str,
                    'htf_bias': _mt5_htf,
                }
                auto_evaluate_strategy(sid, result, close_price, pips_result, ctx)
                self.logger.info(f"MT5 instant eval: #{sid} {result.upper()} {pips_result:+.1f}p (P&L ${pnl:.2f})")

                # Fix #4: archive to trade_archive with full context (was only going to strategy_results before)
                try:
                    from src.common.db import archive_trade, get_entry_context
                    # Merge live close context with entry context captured when strategy was created
                    entry_ctx = get_entry_context(sid)
                    full_ctx = {**ctx}
                    # Prefer ENTRY-TIME values over close-time snapshot for learning accuracy
                    if entry_ctx:
                        full_ctx['rsi_at_entry'] = entry_ctx.get('rsi', 0)
                        full_ctx['avg_range_pips'] = entry_ctx.get('avg_range_pips', 0)
                        full_ctx['volatility'] = entry_ctx.get('volatility', '')
                        # Keep entry trend+htf; only override if missing
                        if entry_ctx.get('trend'):
                            full_ctx['market_trend'] = entry_ctx['trend']
                        if entry_ctx.get('trend_strength'):
                            full_ctx['trend_strength'] = entry_ctx['trend_strength']
                        if entry_ctx.get('htf_bias'):
                            full_ctx['htf_bias'] = entry_ctx['htf_bias']
                    archive_trade(sid, result, close_price, pips_result, full_ctx)
                except Exception as _ae:
                    self.logger.warning(f"Archive MT5 trade #{sid}: {_ae}")

                # Post-trade analysis with Gemma (background thread)
                try:
                    from threading import Thread
                    from src.analyzer.post_trade_analyzer import analyze_closed_trade
                    from src.common.db import save_post_trade_analysis, save_learning_insight
                    _pt_data = {
                        'result': result, 'pips': pips_result, 'direction': direction,
                        'trigger_type': _tt, 'entry_price': fill_price, 'exit_price': close_price,
                        'stop_loss': sl, 'take_profit': tp,
                        'sl_pips': round(abs(fill_price - sl) / pip, 1) if sl else 0,
                        'tp_pips': round(abs(tp - fill_price) / pip, 1) if tp else 0,
                        'session': '', 'rsi': 0, 'trend': '', 'trend_strength': '',
                        'htf_bias': '', 'volatility': '', 'news_title': news_title or '',
                        'confidence': confidence, 'duration_min': 0, 'mt5_pnl': pnl,
                    }
                    def _run_pt_mt5(s_id, data, res):
                        try:
                            analysis = analyze_closed_trade(data)
                            if analysis:
                                save_post_trade_analysis(s_id, analysis, res)
                                save_learning_insight('post_trade', analysis.get('key_lesson', ''), data=analysis)
                                self.logger.info(f"Post-trade #{s_id}: {analysis.get('key_lesson', '')}")
                        except Exception as _e:
                            self.logger.debug(f"Post-trade MT5 #{s_id} error: {_e}")
                    Thread(target=_run_pt_mt5, args=(sid, _pt_data, result), daemon=True).start()
                except Exception as e:
                    self.logger.debug(f"Post-trade MT5 thread #{sid}: {e}")

            except Exception as e:
                self.logger.error(f"MT5 instant eval error #{sid}: {e}")

    def close_strategy_position(self, strategy_id):
        """Close the MT5 position associated with a strategy after auto-evaluation.
        Returns close_price (float) on success, None on failure."""
        if not self.connected or not self._mt5:
            return None

        from src.common.db import get_strategies_with_open_mt5
        open_strats = get_strategies_with_open_mt5()
        for row in open_strats:
            sid = row[0]
            ticket = row[1]
            direction = row[2]
            if sid != strategy_id:
                continue

            # Check if position still exists
            position = self._mt5.positions_get(ticket=ticket)
            if not position or len(position) == 0:
                # Position already closed by MT5 TP/SL — get actual close price from deal history
                deals = self._mt5.history_deals_get(position=ticket)
                if deals:
                    for deal in deals:
                        if deal.entry == 1:  # entry=1 means close deal
                            self.logger.info(f"MT5 position #{ticket} already closed by TP/SL @ {deal.price:.5f}")
                            return deal.price
                return None

            p = position[0]
            close_type = self._mt5.ORDER_TYPE_SELL if p.type == 0 else self._mt5.ORDER_TYPE_BUY
            tick = self._mt5.symbol_info_tick(p.symbol)
            if not tick:
                return None
            close_price = tick.bid if p.type == 0 else tick.ask

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "position": p.ticket,
                "price": close_price,
                "deviation": 50,  # points (0.1 pip each on 5-digit brokers) = 5 pips tolerance
                "magic": MAGIC_NUMBER,
                "comment": f"AIdan close #{strategy_id}",
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": self._mt5.ORDER_FILLING_IOC,
            }

            result = self._mt5.order_send(request)
            if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"MT5 auto-close: strategy #{strategy_id} ticket #{ticket} closed @ {close_price:.5f}")
                return close_price
            else:
                self.logger.error(f"MT5 auto-close failed: strategy #{strategy_id} retcode={result.retcode if result else 'None'}")
                return None
        return None

    def close_all_positions(self):
        if not self.connected or not self._mt5:
            return 0

        positions = self._mt5.positions_get(group="*")
        if not positions:
            return 0

        closed = 0
        for p in positions:
            if p.magic != MAGIC_NUMBER:
                continue

            close_type = self._mt5.ORDER_TYPE_SELL if p.type == 0 else self._mt5.ORDER_TYPE_BUY
            tick = self._mt5.symbol_info_tick(p.symbol)
            if not tick:
                continue
            close_price = tick.bid if p.type == 0 else tick.ask

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "position": p.ticket,
                "price": close_price,
                "deviation": 50,  # points (0.1 pip each on 5-digit brokers) = 5 pips tolerance
                "magic": MAGIC_NUMBER,
                "comment": "AIdan close",
                "type_time": self._mt5.ORDER_TIME_GTC,
                "type_filling": self._mt5.ORDER_FILLING_IOC,
            }

            result = self._mt5.order_send(request)
            if result and result.retcode == self._mt5.TRADE_RETCODE_DONE:
                closed += 1
                self.logger.info(f"MT5 closed position #{p.ticket}")

        return closed

    def toggle(self, enabled):
        if not enabled and self.connected:
            n = self.close_all_positions()
            self.logger.info(f"MT5 kill switch: closed {n} positions")
        self.kill_switch = not enabled
