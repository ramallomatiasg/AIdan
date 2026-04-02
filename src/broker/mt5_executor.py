"""
MT5 Executor — Connects to MetaTrader 5 and executes trades for AIdan strategies.
"""
import time

MAGIC_NUMBER = 20260402  # Identifies AIdan orders in MT5


class MT5Executor:
    def __init__(self, logger):
        self.logger = logger
        self.connected = False
        self.kill_switch = False
        self._mt5 = None

    def connect(self):
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5

            if not mt5.initialize():
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

        for row in open_strategies:
            sid, ticket, direction, entry_price, sl, tp, lot, created_at, news_title = row

            # Check if position still exists in MT5
            position = self._mt5.positions_get(ticket=ticket)
            if position and len(position) > 0:
                continue  # Still open

            # Position closed — get deal history
            from datetime import datetime, timezone, timedelta
            time_from = datetime.now(timezone.utc) - timedelta(days=2)
            time_to = datetime.now(timezone.utc) + timedelta(hours=1)

            deals = self._mt5.history_deals_get(time_from, time_to, group="*")
            pnl = 0.0
            close_price = 0.0

            if deals:
                for deal in deals:
                    if deal.position_id == ticket and deal.entry == 1:  # entry=1 means close deal
                        pnl += deal.profit + deal.swap + deal.commission
                        close_price = deal.price

            if close_price == 0:
                # Fallback: estimate from current price
                tick = self._mt5.symbol_info_tick("EURUSD")
                if tick:
                    close_price = tick.bid if direction == 'CALL' else tick.ask

            update_mt5_close(sid, pnl, close_price)
            self.logger.info(f"MT5 position closed: #{ticket} Strategy #{sid} P&L=${pnl:.2f} @ {close_price:.5f}")

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
