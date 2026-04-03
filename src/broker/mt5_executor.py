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
            except:
                pass
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
        except:
            pass
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

        # Determine order type and price
        if direction == 'CALL':
            order_type = self._mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = self._mt5.ORDER_TYPE_SELL
            price = tick.bid

        # Calculate lot size
        sl_pips = abs(entry_price - sl) / 0.0001
        lot = self.calculate_lot_size(sl_pips)

        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": f"AIdan #{strategy_id}",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }

        result = self._mt5.order_send(request)

        if result is None:
            self.logger.error(f"MT5: order_send returned None for #{strategy_id}")
            update_mt5_ticket(strategy_id, None, 0, 'error')
            return None

        if result.retcode == self._mt5.TRADE_RETCODE_DONE:
            ticket = result.order
            update_mt5_ticket(strategy_id, ticket, lot, 'filled')
            self.logger.info(f"MT5 ORDER FILLED: #{ticket} {direction} {lot} lot @ {price:.5f} SL={sl:.5f} TP={tp:.5f} | Strategy #{strategy_id}")
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

    def sync_closed_positions(self):
        if not self.connected or not self._mt5:
            return

        from src.common.db import get_strategies_with_open_mt5, update_mt5_close
        open_strategies = get_strategies_with_open_mt5()

        # Detect orphaned MT5 positions (AIdan magic but no matching strategy in DB)
        try:
            all_positions = self._mt5.positions_get(group="*") or []
            aidan_positions = [p for p in all_positions if p.magic == MAGIC_NUMBER]
            tracked_tickets = {row[1] for row in open_strategies}  # set of tracked tickets
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
                        "deviation": 20,
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
            sid, ticket, direction, entry_price, sl, tp, lot, created_at, news_title = row

            # Check if position still exists in MT5
            position = self._mt5.positions_get(ticket=ticket)
            if position and len(position) > 0:
                continue  # Still open

            # Position closed — get deal history by position ID (most reliable)
            pnl = 0.0
            close_price = 0.0

            deals = self._mt5.history_deals_get(position=ticket)
            if deals:
                for deal in deals:
                    if deal.entry == 1:  # entry=1 means close deal
                        pnl += deal.profit + deal.swap + deal.commission
                        close_price = deal.price

            if not deals or close_price == 0:
                # Fallback: time-based search
                from datetime import datetime, timezone, timedelta
                time_from = datetime.now(timezone.utc) - timedelta(days=3)
                time_to = datetime.now(timezone.utc) + timedelta(hours=1)
                deals_fb = self._mt5.history_deals_get(time_from, time_to)
                if deals_fb:
                    for deal in deals_fb:
                        if deal.position_id == ticket and deal.entry == 1:
                            pnl += deal.profit + deal.swap + deal.commission
                            close_price = deal.price

            if close_price == 0:
                # Last resort: estimate from current price
                tick = self._mt5.symbol_info_tick("EURUSD")
                if tick:
                    close_price = tick.bid if direction == 'CALL' else tick.ask

            update_mt5_close(sid, pnl, close_price)
            self.logger.info(f"MT5 position closed: #{ticket} Strategy #{sid} P&L=${pnl:.2f} @ {close_price:.5f}")

    def close_strategy_position(self, strategy_id):
        """Close the MT5 position associated with a strategy after auto-evaluation."""
        if not self.connected or not self._mt5:
            return False

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
                return False  # Already closed by SL/TP

            p = position[0]
            close_type = self._mt5.ORDER_TYPE_SELL if p.type == 0 else self._mt5.ORDER_TYPE_BUY
            tick = self._mt5.symbol_info_tick(p.symbol)
            if not tick:
                return False
            close_price = tick.bid if p.type == 0 else tick.ask

            request = {
                "action": self._mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "position": p.ticket,
                "price": close_price,
                "deviation": 20,
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
                return False
        return False

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
                "deviation": 20,
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
