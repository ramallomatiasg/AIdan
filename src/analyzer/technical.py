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

        # Bollinger Bands (20, 2SD)
        bb_period = min(20, len(closes))
        bb_closes = closes[-bb_period:]
        bb_middle = sum(bb_closes) / len(bb_closes)
        bb_std = (sum((c - bb_middle) ** 2 for c in bb_closes) / len(bb_closes)) ** 0.5
        bb_upper = bb_middle + 2 * bb_std
        bb_lower = bb_middle - 2 * bb_std

        # Support/Resistance from pivot points (last 50 candles)
        pivot_candles = candles[-min(50, len(candles)):]
        supports, resistances = [], []
        for i in range(2, len(pivot_candles) - 2):
            h = pivot_candles[i]['high']
            l = pivot_candles[i]['low']
            if h > pivot_candles[i-1]['high'] and h > pivot_candles[i-2]['high'] and h > pivot_candles[i+1]['high'] and h > pivot_candles[i+2]['high']:
                resistances.append(h)
            if l < pivot_candles[i-1]['low'] and l < pivot_candles[i-2]['low'] and l < pivot_candles[i+1]['low'] and l < pivot_candles[i+2]['low']:
                supports.append(l)

        # Cluster nearby levels (within 5 pips) and keep top 3
        def cluster_levels(levels, threshold=0.0005):
            if not levels:
                return []
            levels.sort()
            clusters = [[levels[0]]]
            for lv in levels[1:]:
                if lv - clusters[-1][-1] < threshold:
                    clusters[-1].append(lv)
                else:
                    clusters.append([lv])
            return sorted([sum(c)/len(c) for c in clusters], key=lambda x: abs(x - current_price))[:3]

        supports = cluster_levels(supports)
        resistances = cluster_levels(resistances)

        # Psychological levels near price
        base = round(current_price, 2)
        psych_levels = [round(base + d, 4) for d in [-0.01, -0.005, 0, 0.005, 0.01]
                        if abs(current_price - (base + d)) < 0.005]

        # Price position summary
        pos_parts = []
        if current_price > bb_upper - 0.0002:
            pos_parts.append("en banda superior Bollinger (sobreextendido)")
        elif current_price < bb_lower + 0.0002:
            pos_parts.append("en banda inferior Bollinger (sobreextendido)")
        if resistances and abs(current_price - resistances[0]) < 0.0005:
            pos_parts.append(f"cerca de resistencia {resistances[0]:.5f}")
        if supports and abs(current_price - supports[0]) < 0.0005:
            pos_parts.append(f"cerca de soporte {supports[0]:.5f}")
        price_position = ", ".join(pos_parts) if pos_parts else "en zona media"

        chart_structures = {
            'supports': [round(s, 5) for s in supports],
            'resistances': [round(r, 5) for r in resistances],
            'psychological_levels': psych_levels,
            'bb_upper': round(bb_upper, 5),
            'bb_lower': round(bb_lower, 5),
            'bb_middle': round(bb_middle, 5),
            'price_position': price_position,
        }

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
            'chart_structures': chart_structures,
            'timestamp': datetime.now().isoformat(),
            'source': 'live'
        }

    def get_candles_text(self, n=15):
        """Return last N candles as text for AI context, with pattern detection."""
        candles = self._fetch_candles()
        if not candles or len(candles) < 3:
            return ""
        recent = candles[-n:]
        lines = [f"\n📉 VELAS EUR/USD 5min (últimas {len(recent)}, más antigua → más reciente):"]
        for i, c in enumerate(recent):
            body = c['close'] - c['open']
            rng = c['high'] - c['low']
            pips = round(body * 10000, 1)
            direction = "▲" if body >= 0 else "▼"
            sign = "+" if pips >= 0 else ""
            lines.append(
                f"  {'[ÚLTIMA]' if i == len(recent)-1 else f'[{i+1:02d}]'} "
                f"O:{c['open']:.5f} H:{c['high']:.5f} L:{c['low']:.5f} C:{c['close']:.5f} "
                f"{direction}{sign}{pips}p"
            )

        # Pattern detection on last 3 candles
        patterns = []
        if len(recent) >= 2:
            last = recent[-1]
            prev = recent[-2]
            body_last = abs(last['close'] - last['open'])
            body_prev = abs(prev['close'] - prev['open'])
            rng_last = last['high'] - last['low']
            rng_prev = prev['high'] - prev['low']

            # Doji
            if rng_last > 0 and body_last / rng_last < 0.25:
                patterns.append("DOJI (indecisión)")

            # Pin bar / hammer / shooting star
            if rng_last > 0:
                upper_wick = last['high'] - max(last['open'], last['close'])
                lower_wick = min(last['open'], last['close']) - last['low']
                if upper_wick > rng_last * 0.6 and last['close'] < last['open']:
                    patterns.append("PIN BAR BAJISTA (mecha superior larga → PUT)")
                elif lower_wick > rng_last * 0.6 and last['close'] > last['open']:
                    patterns.append("PIN BAR ALCISTA / HAMMER (mecha inferior larga → CALL)")
                elif upper_wick > rng_last * 0.6:
                    patterns.append("SHOOTING STAR (mecha superior → PUT)")
                elif lower_wick > rng_last * 0.6:
                    patterns.append("HAMMER (mecha inferior → CALL)")

            # Engulfing
            if len(recent) >= 2:
                if (last['close'] > last['open'] and prev['close'] < prev['open']
                        and last['close'] > prev['open'] and last['open'] < prev['close']):
                    patterns.append("ENGULFING ALCISTA (absorbe vela bajista → CALL)")
                elif (last['close'] < last['open'] and prev['close'] > prev['open']
                        and last['close'] < prev['open'] and last['open'] > prev['close']):
                    patterns.append("ENGULFING BAJISTA (absorbe vela alcista → PUT)")

        if patterns:
            lines.append(f"  🔎 Patrones detectados: {' | '.join(patterns)}")
        else:
            lines.append("  🔎 Sin patrones de reversa claros en la última vela")

        return "\n".join(lines)

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
