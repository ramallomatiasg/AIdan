"""
Technical analysis module for EUR/USD.
Fetches live price data and calculates indicators to validate/invalidate fundamental signals.
"""
import requests
import time
from datetime import datetime


class TechnicalAnalyzer:
    """Fetches EUR/USD price data and computes technical indicators."""

    def __init__(self, logger):
        self.logger = logger
        self._cache = {}
        self._cache_ttl = 30  # seconds

    def get_market_state(self):
        """
        Returns current market state dict:
        {
            'price': float,
            'trend': 'bullish' | 'bearish' | 'neutral',
            'trend_strength': 'strong' | 'moderate' | 'weak',
            'rsi': float,
            'rsi_zone': 'oversold' | 'overbought' | 'neutral',
            'ma_fast': float,       # ~9 period
            'ma_slow': float,       # ~21 period
            'price_vs_ma': 'above' | 'below',
            'momentum': 'up' | 'down' | 'flat',
            'volatility': 'high' | 'normal' | 'low',
            'summary': str,         # human-readable 1-liner
            'timestamp': str,
            'source': str
        }
        """
        cache_key = 'market_state'
        now = time.time()
        if cache_key in self._cache and (now - self._cache[cache_key]['_ts']) < self._cache_ttl:
            return self._cache[cache_key]

        candles = self._fetch_candles()
        if not candles or len(candles) < 25:
            self.logger.warning("Technical: not enough candle data")
            return self._fallback_state()

        state = self._compute_indicators(candles)
        state['_ts'] = now
        self._cache[cache_key] = state
        return state

    def validate_signal(self, fundamental_direction, fundamental_confidence, market_state=None):
        """
        Cross-reference a fundamental signal with technical context.
        Returns adjusted direction, confidence, and reasoning.
        """
        if market_state is None:
            market_state = self.get_market_state()

        if market_state.get('source') == 'fallback':
            return {
                'adjusted_direction': fundamental_direction,
                'adjusted_confidence': fundamental_confidence,
                'technical_agrees': None,
                'reason': 'Sin datos técnicos disponibles'
            }

        trend = market_state['trend']
        trend_strength = market_state['trend_strength']
        rsi_zone = market_state['rsi_zone']
        momentum = market_state['momentum']

        # Map directions
        fund_bull = fundamental_direction in ('CALL',)
        fund_bear = fundamental_direction in ('PUT',)
        tech_bull = trend == 'bullish'
        tech_bear = trend == 'bearish'

        adj_dir = fundamental_direction
        adj_conf = fundamental_confidence
        agrees = None
        reasons = []

        if fundamental_direction == 'NEUTRAL':
            # Neutral fundamental — no adjustment needed
            return {
                'adjusted_direction': 'NEUTRAL',
                'adjusted_confidence': fundamental_confidence * 0.8,
                'technical_agrees': None,
                'reason': f"Fundamental neutral. Técnico: {trend} {trend_strength}."
            }

        # Check agreement
        if fund_bull and tech_bull:
            agrees = True
            adj_conf = min(fundamental_confidence * 1.15, 95)
            reasons.append(f"Técnico confirma: tendencia alcista {trend_strength}")
            if rsi_zone == 'overbought':
                adj_conf *= 0.85
                reasons.append("RSI sobrecomprado, posible pullback")
        elif fund_bear and tech_bear:
            agrees = True
            adj_conf = min(fundamental_confidence * 1.15, 95)
            reasons.append(f"Técnico confirma: tendencia bajista {trend_strength}")
            if rsi_zone == 'oversold':
                adj_conf *= 0.85
                reasons.append("RSI sobrevendido, posible rebote")
        elif fund_bull and tech_bear:
            agrees = False
            if trend_strength == 'strong':
                adj_dir = 'NEUTRAL'
                adj_conf = fundamental_confidence * 0.4
                reasons.append(f"CONFLICTO: Fundamental CALL vs tendencia bajista fuerte. Señal invalidada.")
            else:
                adj_conf = fundamental_confidence * 0.6
                reasons.append(f"Fundamental CALL pero técnico bajista {trend_strength}. Confianza reducida.")
        elif fund_bear and tech_bull:
            agrees = False
            if trend_strength == 'strong':
                adj_dir = 'NEUTRAL'
                adj_conf = fundamental_confidence * 0.4
                reasons.append(f"CONFLICTO: Fundamental PUT vs tendencia alcista fuerte. Señal invalidada.")
            else:
                adj_conf = fundamental_confidence * 0.6
                reasons.append(f"Fundamental PUT pero técnico alcista {trend_strength}. Confianza reducida.")

        # RSI extreme adjustments
        if rsi_zone == 'oversold' and fund_bear:
            adj_conf *= 0.7
            reasons.append("RSI sobrevendido — riesgo de rebote")
        elif rsi_zone == 'overbought' and fund_bull:
            adj_conf *= 0.7
            reasons.append("RSI sobrecomprado — riesgo de corrección")

        return {
            'adjusted_direction': adj_dir,
            'adjusted_confidence': round(adj_conf, 2),
            'technical_agrees': agrees,
            'reason': ' | '.join(reasons)
        }

    def _fetch_candles(self):
        """Fetch 5-min candles. Yahoo Finance (free, no API key)."""
        candles = self._fetch_from_yahoo()
        if candles:
            return candles
        return None

    def _fetch_from_yahoo(self):
        """Yahoo Finance: free, no API key, reliable."""
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X"
            params = {'interval': '5m', 'range': '1d'}
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            quote = result['indicators']['quote'][0]
            opens = quote['open']
            highs = quote['high']
            lows = quote['low']
            closes = quote['close']

            candles = []
            for i in range(len(timestamps)):
                if closes[i] is not None and opens[i] is not None:
                    candles.append({
                        'open': float(opens[i]),
                        'high': float(highs[i]),
                        'low': float(lows[i]),
                        'close': float(closes[i]),
                        'datetime': str(timestamps[i])
                    })
            self.logger.info(f"Technical: {len(candles)} candles from Yahoo Finance")
            return candles
        except Exception as e:
            self.logger.warning(f"Yahoo Finance fetch failed: {e}")
            return None

    def _compute_indicators(self, candles):
        """Compute RSI, MAs, trend, momentum from candle data."""
        closes = [c['close'] for c in candles]
        current_price = closes[-1]

        # Moving averages
        ma_fast = sum(closes[-9:]) / 9
        ma_slow = sum(closes[-21:]) / 21

        # RSI (14 period)
        rsi = self._calc_rsi(closes, 14)

        # Trend detection via HH/HL or LH/LL
        recent_highs = [c['high'] for c in candles[-10:]]
        recent_lows = [c['low'] for c in candles[-10:]]

        higher_highs = all(recent_highs[i] >= recent_highs[i-1] for i in range(max(1, len(recent_highs)-4), len(recent_highs)))
        lower_lows = all(recent_lows[i] <= recent_lows[i-1] for i in range(max(1, len(recent_lows)-4), len(recent_lows)))
        lower_highs = all(recent_highs[i] <= recent_highs[i-1] for i in range(max(1, len(recent_highs)-4), len(recent_highs)))
        higher_lows = all(recent_lows[i] >= recent_lows[i-1] for i in range(max(1, len(recent_lows)-4), len(recent_lows)))

        # Determine trend
        if current_price > ma_fast > ma_slow and (higher_highs or higher_lows):
            trend = 'bullish'
        elif current_price < ma_fast < ma_slow and (lower_lows or lower_highs):
            trend = 'bearish'
        elif current_price > ma_slow:
            trend = 'bullish'
        elif current_price < ma_slow:
            trend = 'bearish'
        else:
            trend = 'neutral'

        # Trend strength
        ma_spread = abs(ma_fast - ma_slow) / current_price * 10000  # in pips
        if ma_spread > 8:
            trend_strength = 'strong'
        elif ma_spread > 3:
            trend_strength = 'moderate'
        else:
            trend_strength = 'weak'

        # Momentum: last 3 candles
        last3 = closes[-3:]
        if last3[-1] > last3[0]:
            momentum = 'up'
        elif last3[-1] < last3[0]:
            momentum = 'down'
        else:
            momentum = 'flat'

        # RSI zone
        if rsi <= 30:
            rsi_zone = 'oversold'
        elif rsi >= 70:
            rsi_zone = 'overbought'
        else:
            rsi_zone = 'neutral'

        # Volatility (ATR-like: average range of last 10 candles in pips)
        ranges = [(c['high'] - c['low']) * 10000 for c in candles[-10:]]
        avg_range = sum(ranges) / len(ranges) if ranges else 0
        if avg_range > 10:
            volatility = 'high'
        elif avg_range > 4:
            volatility = 'normal'
        else:
            volatility = 'low'

        # Summary
        summary = f"EUR/USD {current_price:.5f} | Tendencia {trend} {trend_strength} | RSI {rsi:.0f} ({rsi_zone}) | MA9 {ma_fast:.5f} MA21 {ma_slow:.5f} | Mom: {momentum}"

        return {
            'price': current_price,
            'trend': trend,
            'trend_strength': trend_strength,
            'rsi': round(rsi, 1),
            'rsi_zone': rsi_zone,
            'ma_fast': round(ma_fast, 5),
            'ma_slow': round(ma_slow, 5),
            'price_vs_ma': 'above' if current_price > ma_fast else 'below',
            'momentum': momentum,
            'volatility': volatility,
            'avg_range_pips': round(avg_range, 1),
            'summary': summary,
            'timestamp': datetime.utcnow().isoformat(),
            'source': 'live'
        }

    def _calc_rsi(self, closes, period=14):
        """Calculate RSI."""
        if len(closes) < period + 1:
            return 50.0  # default
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _fallback_state(self):
        """Return fallback state when no data available."""
        return {
            'price': 0,
            'trend': 'unknown',
            'trend_strength': 'unknown',
            'rsi': 50,
            'rsi_zone': 'neutral',
            'ma_fast': 0,
            'ma_slow': 0,
            'price_vs_ma': 'unknown',
            'momentum': 'unknown',
            'volatility': 'unknown',
            'summary': 'Sin datos técnicos disponibles',
            'timestamp': datetime.utcnow().isoformat(),
            'source': 'fallback'
        }
