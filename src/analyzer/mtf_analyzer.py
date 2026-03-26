"""
Multi-Timeframe Analyzer for EUR/USD.
Fetches candles at H1, M15, M5 from Yahoo Finance and computes
trend + structure (HH/HL/LH/LL) + swing points per timeframe.
"""
import requests
import time
from datetime import datetime


class MTFAnalyzer:
    """Fetches EUR/USD candles at multiple timeframes and analyzes structure."""

    # Timeframe configs: interval, range for Yahoo, cache TTL, swing neighbor count
    TF_CONFIG = {
        'H1':  {'interval': '1h',  'range': '5d',  'cache_ttl': 120, 'swing_n': 3},
        'M15': {'interval': '15m', 'range': '5d',  'cache_ttl': 60,  'swing_n': 2},
        'M5':  {'interval': '5m',  'range': '1d',  'cache_ttl': 30,  'swing_n': 2},
    }

    def __init__(self, logger):
        self.logger = logger
        self._cache = {}  # {tf: {'candles': [...], 'ts': float}}

    def get_candles(self, timeframe):
        """Get candles for a specific timeframe, with caching."""
        cfg = self.TF_CONFIG.get(timeframe)
        if not cfg:
            return []

        now = time.time()
        cached = self._cache.get(timeframe)
        if cached and (now - cached['ts']) < cfg['cache_ttl']:
            return cached['candles']

        candles = self._fetch_yahoo(cfg['interval'], cfg['range'])
        if candles:
            self._cache[timeframe] = {'candles': candles, 'ts': now}
        return candles or (cached['candles'] if cached else [])

    def get_mtf_state(self):
        """
        Returns multi-timeframe analysis:
        {
            'H1':  {trend, structure, swings, last_swing_high, last_swing_low, price, ...},
            'M15': {...},
            'M5':  {...},
            'summary': str
        }
        """
        result = {}
        for tf in ['H1', 'M15', 'M5']:
            candles = self.get_candles(tf)
            if len(candles) < 10:
                result[tf] = self._empty_tf_state(tf)
                continue
            result[tf] = self._analyze_tf(tf, candles)

        result['summary'] = self._build_summary(result)
        return result

    def _analyze_tf(self, tf, candles):
        """Analyze a single timeframe: trend, swings, structure."""
        cfg = self.TF_CONFIG[tf]
        swing_n = cfg['swing_n']

        closes = [c['close'] for c in candles]
        price = closes[-1]

        # MAs
        ma9 = sum(closes[-9:]) / min(9, len(closes)) if len(closes) >= 9 else price
        ma21 = sum(closes[-21:]) / min(21, len(closes)) if len(closes) >= 21 else price

        # Detect swing points
        swing_highs, swing_lows = self._detect_swings(candles, swing_n)

        # Classify structure: HH/HL/LH/LL
        structure = self._classify_structure(swing_highs, swing_lows)

        # Determine trend from structure
        trend = self._trend_from_structure(structure, price, ma9, ma21)

        # Last swing values
        last_sh = swing_highs[-1]['price'] if swing_highs else None
        last_sl = swing_lows[-1]['price'] if swing_lows else None

        # BOS detection
        bos = self._detect_bos(candles, swing_highs, swing_lows)

        return {
            'timeframe': tf,
            'price': price,
            'trend': trend,
            'ma9': round(ma9, 5),
            'ma21': round(ma21, 5),
            'swing_highs': swing_highs[-5:],  # last 5
            'swing_lows': swing_lows[-5:],
            'last_swing_high': round(last_sh, 5) if last_sh else None,
            'last_swing_low': round(last_sl, 5) if last_sl else None,
            'structure': structure,
            'bos': bos,
        }

    def _detect_swings(self, candles, n):
        """
        Detect swing highs and lows.
        Swing high: candle[i].high > all neighbors within n candles on both sides.
        Swing low: candle[i].low < all neighbors within n candles on both sides.
        """
        swing_highs = []
        swing_lows = []

        for i in range(n, len(candles) - n):
            c = candles[i]
            # Check swing high
            is_sh = True
            for j in range(i - n, i + n + 1):
                if j == i:
                    continue
                if candles[j]['high'] >= c['high']:
                    is_sh = False
                    break
            if is_sh:
                swing_highs.append({
                    'price': c['high'],
                    'index': i,
                    'time': c.get('datetime', '')
                })

            # Check swing low
            is_sl = True
            for j in range(i - n, i + n + 1):
                if j == i:
                    continue
                if candles[j]['low'] <= c['low']:
                    is_sl = False
                    break
            if is_sl:
                swing_lows.append({
                    'price': c['low'],
                    'index': i,
                    'time': c.get('datetime', '')
                })

        return swing_highs, swing_lows

    def _classify_structure(self, swing_highs, swing_lows):
        """
        Compare consecutive swings to classify:
        HH (Higher High), HL (Higher Low), LH (Lower High), LL (Lower Low)
        Returns list of last structure points.
        """
        points = []

        # Classify highs
        for i in range(1, len(swing_highs)):
            prev = swing_highs[i - 1]['price']
            curr = swing_highs[i]['price']
            label = 'HH' if curr > prev else 'LH'
            points.append({
                'type': label,
                'price': curr,
                'index': swing_highs[i]['index'],
                'time': swing_highs[i]['time']
            })

        # Classify lows
        for i in range(1, len(swing_lows)):
            prev = swing_lows[i - 1]['price']
            curr = swing_lows[i]['price']
            label = 'HL' if curr > prev else 'LL'
            points.append({
                'type': label,
                'price': curr,
                'index': swing_lows[i]['index'],
                'time': swing_lows[i]['time']
            })

        # Sort by index
        points.sort(key=lambda p: p['index'])
        return points[-8:]  # last 8 structure points

    def _trend_from_structure(self, structure, price, ma9, ma21):
        """Determine trend from structure points + MAs."""
        if not structure:
            if price > ma9 > ma21:
                return 'bullish'
            elif price < ma9 < ma21:
                return 'bearish'
            return 'neutral'

        # Count recent HH/HL vs LH/LL (last 4 points)
        recent = structure[-4:]
        bullish_count = sum(1 for p in recent if p['type'] in ('HH', 'HL'))
        bearish_count = sum(1 for p in recent if p['type'] in ('LH', 'LL'))

        if bullish_count > bearish_count:
            return 'bullish'
        elif bearish_count > bullish_count:
            return 'bearish'

        # Tie-break with MAs
        if ma9 > ma21:
            return 'bullish'
        elif ma9 < ma21:
            return 'bearish'
        return 'neutral'

    def _detect_bos(self, candles, swing_highs, swing_lows):
        """
        Detect Break of Structure (BOS):
        - Bullish BOS: price closes above last swing high
        - Bearish BOS: price closes below last swing low
        """
        if not candles:
            return None

        last_close = candles[-1]['close']
        prev_close = candles[-2]['close'] if len(candles) >= 2 else last_close

        # Check bullish BOS
        if swing_highs and len(swing_highs) >= 2:
            last_sh = swing_highs[-1]['price']
            if prev_close <= last_sh and last_close > last_sh:
                return {
                    'type': 'bullish',
                    'level': last_sh,
                    'description': f'BOS alcista: precio rompió swing high {last_sh:.5f}'
                }

        # Check bearish BOS
        if swing_lows and len(swing_lows) >= 2:
            last_sl = swing_lows[-1]['price']
            if prev_close >= last_sl and last_close < last_sl:
                return {
                    'type': 'bearish',
                    'level': last_sl,
                    'description': f'BOS bajista: precio rompió swing low {last_sl:.5f}'
                }

        return None

    def _build_summary(self, state):
        """Build human-readable multi-timeframe summary."""
        lines = []
        for tf in ['H1', 'M15', 'M5']:
            s = state.get(tf, {})
            trend = s.get('trend', '?')
            lsh = s.get('last_swing_high')
            lsl = s.get('last_swing_low')

            arrow = {'bullish': 'ALCISTA', 'bearish': 'BAJISTA', 'neutral': 'LATERAL'}.get(trend, '?')

            parts = [f"{tf}: {arrow}"]
            if lsh:
                parts.append(f"SH:{lsh:.5f}")
            if lsl:
                parts.append(f"SL:{lsl:.5f}")

            # Last structure point
            struct = s.get('structure', [])
            if struct:
                last = struct[-1]
                parts.append(f"último:{last['type']} {last['price']:.5f}")

            bos = s.get('bos')
            if bos:
                parts.append(f"[{bos['description']}]")

            lines.append(' | '.join(parts))

        return '\n'.join(lines)

    def _empty_tf_state(self, tf):
        """Return empty state when not enough data."""
        return {
            'timeframe': tf,
            'price': 0,
            'trend': 'unknown',
            'ma9': 0, 'ma21': 0,
            'swing_highs': [], 'swing_lows': [],
            'last_swing_high': None, 'last_swing_low': None,
            'structure': [],
            'bos': None,
        }

    def _fetch_yahoo(self, interval, range_str):
        """Fetch candles from best available source (Twelve Data → Yahoo fallback)."""
        from src.common.price_feed import fetch_candles, get_last_source
        # Map Yahoo-style intervals to generic format
        interval_map = {'1m': '1min', '5m': '5min', '15m': '15min', '30m': '30min', '1h': '1h', '1d': '1day'}
        generic_interval = interval_map.get(interval, interval)
        candles = fetch_candles(interval=generic_interval, count=200, logger=self.logger)
        if candles:
            self.logger.info(f"MTF: {len(candles)} candles via {get_last_source()} ({interval})")
        return candles
