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
        self._triggered_levels = {}  # {level_key: timestamp} — avoid duplicate signals
        self._last_trigger_cleanup = 0

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
        """Fetch 5-min candles from best available source."""
        from src.common.price_feed import fetch_candles, get_last_source
        candles = fetch_candles(interval='5min', count=100, logger=self.logger)
        if candles:
            self.logger.info(f"Technical: {len(candles)} candles via {get_last_source()}")
        return candles

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

    def detect_structure_signals(self, min_confidence=50):
        """
        Scan market structure for actionable setups (no news needed).
        min_confidence comes from the user's active profile.
        Returns list of signal dicts or empty list.
        Each signal: {direction, confidence, reason, setup_type, key_level}
        """
        market = self.get_market_state()
        if market.get('source') == 'fallback':
            return []

        candles = self._fetch_candles()
        if not candles or len(candles) < 25:
            return []

        # Load historical win rates for dynamic confidence adjustment
        setup_win_rates = {}
        try:
            from src.common.db import get_setup_win_rates
            setup_win_rates = get_setup_win_rates()
        except Exception:
            pass

        # Cleanup old triggered levels (every 30 min)
        now = time.time()
        if now - self._last_trigger_cleanup > 300:  # cleanup every 5 min
            cutoff = now - 900  # forget levels older than 15 min
            self._triggered_levels = {k: v for k, v in self._triggered_levels.items() if v > cutoff}
            self._last_trigger_cleanup = now

        price = market['price']
        trend = market['trend']
        trend_strength = market['trend_strength']
        rsi = market['rsi']
        rsi_zone = market['rsi_zone']
        momentum = market['momentum']
        ma_fast = market.get('ma_fast', 0)
        ma_slow = market.get('ma_slow', 0)
        structures = market.get('chart_structures', {})
        supports = structures.get('supports', [])
        resistances = structures.get('resistances', [])
        bb_upper = structures.get('bb_upper', 0)
        bb_lower = structures.get('bb_lower', 0)

        signals = []
        pip = 0.0001

        # Load auto-tuner optimized params (fallback to defaults)
        tuner_params = {}
        try:
            from src.optimizer.auto_tuner import AutoTuner, DEFAULT_PARAMS
            from src.common.db import DB_PATH
            _tuner = AutoTuner(self.logger, DB_PATH)
            tuner_params = _tuner.get_params()
        except Exception:
            from src.optimizer.auto_tuner import DEFAULT_PARAMS
            tuner_params = dict(DEFAULT_PARAMS)

        # Helper: check if we already triggered this level recently
        def already_triggered(level, direction):
            key = f"{round(level, 5)}_{direction}"
            return key in self._triggered_levels

        def mark_triggered(level, direction):
            key = f"{round(level, 5)}_{direction}"
            self._triggered_levels[key] = time.time()

        def dynamic_conf(base_conf, setup_type):
            """Adjust base confidence using historical win rate for this setup type."""
            stats = setup_win_rates.get(setup_type, {})
            if stats.get('total', 0) >= 5:
                # Blend: 60% base + 40% historical
                historical = 50 + int(stats['win_rate'] / 100 * 40)  # maps 0-100% WR to 50-90
                return int(base_conf * 0.6 + historical * 0.4)
            return base_conf

        # Recent closed candles (not current incomplete one)
        prev1 = candles[-2]
        prev2 = candles[-3]
        recent_candles = candles[-6:-1]  # last 5 closed candles for wider detection

        # Helper: check if level was crossed in recent candles
        def crossed_above(level, lookback=None):
            """Check if any consecutive pair in recent candles crossed above level."""
            cb = lookback or recent_candles
            for i in range(1, len(cb)):
                if cb[i-1]['close'] <= level and cb[i]['close'] >= level and cb[i]['close'] != cb[i-1]['close']:
                    return True
            # Also: first candle below, price now above
            if cb and cb[0]['close'] < level and price > level:
                return True
            return False

        def crossed_below(level, lookback=None):
            cb = lookback or recent_candles
            for i in range(1, len(cb)):
                if cb[i-1]['close'] >= level and cb[i]['close'] <= level and cb[i]['close'] != cb[i-1]['close']:
                    return True
            if cb and cb[0]['close'] > level and price < level:
                return True
            return False

        # ── 1. BREAKOUT above resistance ──
        for res in resistances:
            dist = (price - res) * 10000  # in pips
            if 0.3 < dist < tuner_params.get('breakout_dist_max', 15) and crossed_above(res):
                if not already_triggered(res, 'CALL'):
                    conf = dynamic_conf(tuner_params.get('conf_breakout', 70), 'breakout_resistance')
                    if trend == 'bullish':
                        conf += 10
                    if momentum == 'up':
                        conf += 5
                    if rsi_zone == 'overbought':
                        conf -= 10
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'CALL',
                            'confidence': min(conf, 90),
                            'reason': f"Breakout sobre resistencia {res:.5f} (precio {price:.5f}, +{dist:.1f}p). Tendencia {trend} {trend_strength}.",
                            'setup_type': 'breakout_resistance',
                            'key_level': res
                        })
                        mark_triggered(res, 'CALL')

        # ── 2. BREAKDOWN below support ──
        for sup in supports:
            dist = (sup - price) * 10000  # in pips
            if 0.3 < dist < tuner_params.get('breakdown_dist_max', 15) and crossed_below(sup):
                if not already_triggered(sup, 'PUT'):
                    conf = dynamic_conf(tuner_params.get('conf_breakout', 70), 'breakdown_support')
                    if trend == 'bearish':
                        conf += 10
                    if momentum == 'down':
                        conf += 5
                    if rsi_zone == 'oversold':
                        conf -= 10
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'PUT',
                            'confidence': min(conf, 90),
                            'reason': f"Ruptura bajo soporte {sup:.5f} (precio {price:.5f}, -{dist:.1f}p). Tendencia {trend} {trend_strength}.",
                            'setup_type': 'breakdown_support',
                            'key_level': sup
                        })
                        mark_triggered(sup, 'PUT')

        # ── 3. RSI extreme + key level = REVERSAL ──
        rsi_prox = tuner_params.get('rsi_proximity_pips', 12)
        if rsi_zone == 'oversold' and supports:
            nearest_sup = min(supports, key=lambda s: abs(price - s))
            if abs(price - nearest_sup) * 10000 < rsi_prox:
                if not already_triggered(nearest_sup, 'RSI_CALL'):
                    conf = dynamic_conf(tuner_params.get('conf_rsi_reversal', 72), 'rsi_reversal_support')
                    if trend == 'bullish':
                        conf += 8
                    if prev1['close'] > prev1['open']:  # green candle bonus
                        conf += 5
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'CALL',
                            'confidence': min(conf, 88),
                            'reason': f"RSI sobrevendido ({rsi:.0f}) en soporte {nearest_sup:.5f}. Posible rebote alcista.",
                            'setup_type': 'rsi_reversal_support',
                            'key_level': nearest_sup
                        })
                        mark_triggered(nearest_sup, 'RSI_CALL')

        if rsi_zone == 'overbought' and resistances:
            nearest_res = min(resistances, key=lambda r: abs(price - r))
            if abs(price - nearest_res) * 10000 < rsi_prox:
                if not already_triggered(nearest_res, 'RSI_PUT'):
                    conf = dynamic_conf(tuner_params.get('conf_rsi_reversal', 72), 'rsi_reversal_resistance')
                    if trend == 'bearish':
                        conf += 8
                    if prev1['close'] < prev1['open']:  # red candle bonus
                        conf += 5
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'PUT',
                            'confidence': min(conf, 88),
                            'reason': f"RSI sobrecomprado ({rsi:.0f}) en resistencia {nearest_res:.5f}. Posible rechazo bajista.",
                            'setup_type': 'rsi_reversal_resistance',
                            'key_level': nearest_res
                        })
                        mark_triggered(nearest_res, 'RSI_PUT')

        # ── 4. Bollinger Band rejection at S/R ──
        has_recent_red = any(c['close'] <= c['open'] for c in recent_candles[-3:])
        has_recent_green = any(c['close'] >= c['open'] for c in recent_candles[-3:])
        bb_prox = tuner_params.get('bb_proximity_pips', 8)
        bb_sr_prox = tuner_params.get('bb_sr_proximity_pips', 15)

        if bb_upper > 0 and abs(price - bb_upper) * 10000 < bb_prox:
            if has_recent_red and resistances:
                nearest_res = min(resistances, key=lambda r: abs(price - r))
                if abs(price - nearest_res) * 10000 < bb_sr_prox:
                    if not already_triggered(bb_upper, 'BB_PUT'):
                        conf = dynamic_conf(tuner_params.get('conf_bb_rejection', 68), 'bb_rejection_upper')
                        if conf >= min_confidence:
                            signals.append({
                                'direction': 'PUT',
                                'confidence': conf,
                                'reason': f"Rechazo en Bollinger superior ({bb_upper:.5f}) + resistencia {nearest_res:.5f}. Vela bajista.",
                                'setup_type': 'bb_rejection_upper',
                                'key_level': bb_upper
                            })
                            mark_triggered(bb_upper, 'BB_PUT')

        if bb_lower > 0 and abs(price - bb_lower) * 10000 < bb_prox:
            if has_recent_green and supports:
                nearest_sup = min(supports, key=lambda s: abs(price - s))
                if abs(price - nearest_sup) * 10000 < bb_sr_prox:
                    if not already_triggered(bb_lower, 'BB_CALL'):
                        conf = dynamic_conf(tuner_params.get('conf_bb_rejection', 68), 'bb_rejection_lower')
                        if conf >= min_confidence:
                            signals.append({
                                'direction': 'CALL',
                                'confidence': conf,
                                'reason': f"Rebote en Bollinger inferior ({bb_lower:.5f}) + soporte {nearest_sup:.5f}. Vela alcista.",
                                'setup_type': 'bb_rejection_lower',
                                'key_level': bb_lower
                            })
                            mark_triggered(bb_lower, 'BB_CALL')

        # ── 5. Strong momentum after consolidation ──
        if len(candles) >= 8:
            consol_candles = candles[-8:-2]
            consol_ranges = [(c['high'] - c['low']) * 10000 for c in consol_candles]
            avg_consol = sum(consol_ranges) / len(consol_ranges)
            last_range = (prev1['high'] - prev1['low']) * 10000

            consol_max = tuner_params.get('momentum_consol_max_avg', 10)
            exp_mult = tuner_params.get('momentum_expansion_mult', 1.8)
            min_body = tuner_params.get('momentum_min_body_pips', 2)
            if avg_consol < consol_max and last_range > avg_consol * exp_mult:
                body = prev1['close'] - prev1['open']
                if abs(body) * 10000 > min_body:
                    direction = 'CALL' if body > 0 else 'PUT'
                    key = round(prev1['close'], 5)
                    if not already_triggered(key, f'MOMENTUM_{direction}'):
                        conf = dynamic_conf(tuner_params.get('conf_momentum', 72), 'momentum_expansion')
                        if conf >= min_confidence:
                            signals.append({
                                'direction': direction,
                                'confidence': conf,
                                'reason': f"Expansión de volatilidad ({last_range:.1f}p) tras consolidación ({avg_consol:.1f}p). Momentum {direction}.",
                                'setup_type': 'momentum_expansion',
                                'key_level': prev1['close']
                            })
                            mark_triggered(key, f'MOMENTUM_{direction}')

        # ── 6. MA9/MA21 crossover ──
        if ma_fast > 0 and ma_slow > 0 and len(candles) >= 22:
            # Compute MA9 and MA21 for previous candle to detect crossover
            prev_closes = [c['close'] for c in candles[:-1]]
            prev_ma_fast = sum(prev_closes[-9:]) / 9
            prev_ma_slow = sum(prev_closes[-21:]) / 21

            # Golden cross: MA9 crosses above MA21
            if prev_ma_fast <= prev_ma_slow and ma_fast > ma_slow:
                if not already_triggered(ma_fast, 'MA_CALL'):
                    conf = dynamic_conf(tuner_params.get('conf_ma_crossover', 65), 'ma_crossover_bull')
                    if momentum == 'up':
                        conf += 5
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'CALL',
                            'confidence': min(conf, 85),
                            'reason': f"Cruce alcista MA9 ({ma_fast:.5f}) sobre MA21 ({ma_slow:.5f}). Momentum {momentum}.",
                            'setup_type': 'ma_crossover_bull',
                            'key_level': price
                        })
                        mark_triggered(ma_fast, 'MA_CALL')

            # Death cross: MA9 crosses below MA21
            elif prev_ma_fast >= prev_ma_slow and ma_fast < ma_slow:
                if not already_triggered(ma_fast, 'MA_PUT'):
                    conf = dynamic_conf(tuner_params.get('conf_ma_crossover', 65), 'ma_crossover_bear')
                    if momentum == 'down':
                        conf += 5
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'PUT',
                            'confidence': min(conf, 85),
                            'reason': f"Cruce bajista MA9 ({ma_fast:.5f}) bajo MA21 ({ma_slow:.5f}). Momentum {momentum}.",
                            'setup_type': 'ma_crossover_bear',
                            'key_level': price
                        })
                        mark_triggered(ma_fast, 'MA_PUT')

        # ── 7. TREND CONTINUATION: price near S/R with aligned trend + MA ──
        tc_prox = tuner_params.get('trend_cont_proximity_pips', 15)
        if trend == 'bullish' and ma_fast > ma_slow and supports:
            nearest_sup = min(supports, key=lambda s: abs(price - s))
            dist_to_sup = (price - nearest_sup) * 10000
            if 0 < dist_to_sup < tc_prox and has_recent_green:
                if not already_triggered(nearest_sup, 'TREND_CALL'):
                    conf = dynamic_conf(tuner_params.get('conf_trend_cont', 62), 'trend_continuation_bull')
                    if momentum == 'up':
                        conf += 5
                    if trend_strength == 'strong':
                        conf += 5
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'CALL',
                            'confidence': min(conf, 85),
                            'reason': f"Continuación alcista: precio {price:.5f} rebotando en soporte {nearest_sup:.5f} (+{dist_to_sup:.1f}p). MA9>MA21, tendencia {trend}.",
                            'setup_type': 'trend_continuation_bull',
                            'key_level': nearest_sup
                        })
                        mark_triggered(nearest_sup, 'TREND_CALL')

        if trend == 'bearish' and ma_fast < ma_slow and resistances:
            nearest_res = min(resistances, key=lambda r: abs(price - r))
            dist_to_res = (nearest_res - price) * 10000
            if 0 < dist_to_res < tc_prox and has_recent_red:
                if not already_triggered(nearest_res, 'TREND_PUT'):
                    conf = dynamic_conf(tuner_params.get('conf_trend_cont', 62), 'trend_continuation_bear')
                    if momentum == 'down':
                        conf += 5
                    if trend_strength == 'strong':
                        conf += 5
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'PUT',
                            'confidence': min(conf, 85),
                            'reason': f"Continuación bajista: precio {price:.5f} rechazando en resistencia {nearest_res:.5f} (-{dist_to_res:.1f}p). MA9<MA21, tendencia {trend}.",
                            'setup_type': 'trend_continuation_bear',
                            'key_level': nearest_res
                        })
                        mark_triggered(nearest_res, 'TREND_PUT')

        # ── 8. PRICE AT KEY LEVEL: simple proximity to S/R when market is active ──
        lv_prox = tuner_params.get('level_proximity_pips', 5)
        avg_range = sum((c['high'] - c['low']) * 10000 for c in recent_candles) / len(recent_candles)
        if avg_range > 0.5:
            for sup in supports:
                dist = abs(price - sup) * 10000
                if dist < lv_prox:
                    if not already_triggered(sup, 'LEVEL_CALL'):
                        conf = dynamic_conf(tuner_params.get('conf_level_bounce', 55), 'level_bounce')
                        if trend == 'bullish':
                            conf += 8
                        if has_recent_green:
                            conf += 5
                        if conf >= min_confidence:
                            signals.append({
                                'direction': 'CALL',
                                'confidence': min(conf, 80),
                                'reason': f"Precio en soporte clave {sup:.5f} (dist {dist:.1f}p). Posible rebote.",
                                'setup_type': 'level_bounce',
                                'key_level': sup
                            })
                            mark_triggered(sup, 'LEVEL_CALL')
                        break  # only closest

            for res in resistances:
                dist = abs(price - res) * 10000
                if dist < lv_prox:
                    if not already_triggered(res, 'LEVEL_PUT'):
                        conf = dynamic_conf(tuner_params.get('conf_level_bounce', 55), 'level_rejection')
                        if trend == 'bearish':
                            conf += 8
                        if has_recent_red:
                            conf += 5
                        if conf >= min_confidence:
                            signals.append({
                                'direction': 'PUT',
                                'confidence': min(conf, 80),
                                'reason': f"Precio en resistencia clave {res:.5f} (dist {dist:.1f}p). Posible rechazo.",
                                'setup_type': 'level_rejection',
                                'key_level': res
                            })
                            mark_triggered(res, 'LEVEL_PUT')
                        break

        if signals:
            self.logger.info(f"Structure scanner: {len(signals)} signals detected")
        return signals

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
