"""
Technical analysis module for EUR/USD.
Fetches live price data and calculates indicators to validate/invalidate fundamental signals.
"""
import requests
import time
from datetime import datetime, timezone, timedelta


class TechnicalAnalyzer:
    """Fetches EUR/USD price data and computes technical indicators."""

    def __init__(self, logger):
        self.logger = logger
        self._cache = {}
        # v3.30.0: TTL extendido 5s -> 10s. El analyzer cycle es 10s, asi reusa
        # market_state entre news/structure/smc en mismo cycle (3-4 llamadas
        # ahorradas por cycle). Para M5 (vela 5min) 10s de cache es seguro.
        self._cache_ttl = 10
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
        if not candles or len(candles) < 21:
            self.logger.warning(f"Not enough candles for indicators: {len(candles) if candles else 0} (need 21+)")
            return self._fallback_state()

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

        # Trend strength (calibrated for M5 timeframe — MAs are always close)
        ma_spread = abs(ma_fast - ma_slow) / current_price * 10000  # in pips
        if ma_spread > 3:
            trend_strength = 'strong'
        elif ma_spread > 1.5:
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

        # Volatility: True ATR-14 (accounts for gaps via previous close)
        atr_period = min(14, len(candles) - 1)
        true_ranges = []
        for i in range(-atr_period, 0):
            h = candles[i]['high']
            l = candles[i]['low']
            prev_c = candles[i - 1]['close']
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            true_ranges.append(tr * 10000)  # convert to pips
        avg_range = sum(true_ranges) / len(true_ranges) if true_ranges else 0
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

        # === v3.10.0 REGIME DETECTION ===
        # Determines if market is currently in TRENDING or RANGING regime.
        # Different regimes need different strategy logic:
        #   TRENDING: aligned trades work, counter-trend = bounce-buying = LOSES
        #   RANGING: counter-trend mean-reversion works, aligned = exhaustion = LOSES
        # Empirical evidence (4 May 2026): EUR/USD was decisively bearish (-36p net).
        # AIdan lost 4/4 CALL trades trying to buy bounces during a clear bearish trend.
        # Regime detector computes 3 signals from last 50 M5 candles (~4 hours):
        #   1. directional_score: |net_move| / avg_atr — how far price has moved net
        #   2. range_atrs: (max_high - min_low) / avg_atr — total swing
        #   3. ma_alignment: ma_fast vs ma_slow distance vs ATR — sustained direction
        regime = 'uncertain'
        regime_score = 0
        try:
            if len(candles) >= 50:
                recent = candles[-50:]
                recent_closes = [c['close'] for c in recent]
                recent_highs = [c['high'] for c in recent]
                recent_lows = [c['low'] for c in recent]

                # Signal 1: Net directional move in ATRs
                net_move_pips = abs(recent_closes[-1] - recent_closes[0]) * 10000
                directional_score = net_move_pips / max(avg_range, 1.0)

                # Signal 2: Range expansion in ATRs
                range_pips = (max(recent_highs) - min(recent_lows)) * 10000
                range_atrs = range_pips / max(avg_range, 1.0)

                # Signal 3: MA alignment strength (how far apart ma_fast and ma_slow)
                ma_gap_pips = abs(ma_fast - ma_slow) * 10000
                ma_alignment_score = ma_gap_pips / max(avg_range, 1.0)

                # Score combination (0-3 trending signals)
                if directional_score > 3.0: regime_score += 1
                if range_atrs > 7.0: regime_score += 1
                if ma_alignment_score > 0.6: regime_score += 1

                if regime_score >= 2:
                    regime = 'trending'
                elif regime_score == 0 and directional_score < 1.5:
                    regime = 'ranging'
                else:
                    regime = 'uncertain'
        except Exception:
            regime = 'uncertain'

        # Summary
        summary = f"EUR/USD {current_price:.5f} | Tendencia {trend} {trend_strength} | RSI {rsi:.0f} ({rsi_zone}) | MA9 {ma_fast:.5f} MA21 {ma_slow:.5f} | Mom: {momentum} | Regime: {regime}"

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
            'regime': regime,
            'regime_score': regime_score,
            'summary': summary,
            'chart_structures': chart_structures,
            'timestamp': datetime.now().isoformat(),
            'source': 'live'
        }

    def detect_structure_signals(self, min_confidence=50, htf_bias=None, daily_context=None):
        """
        Scan market structure for actionable setups (no news needed).
        min_confidence comes from the user's active profile.
        htf_bias: 'bullish', 'bearish', or None/neutral from SMC engine.
        Returns list of signal dicts or empty list.
        Each signal: {direction, confidence, reason, setup_type, key_level}
        """
        market = self.get_market_state()
        if market.get('source') == 'fallback':
            return []

        candles = self._fetch_candles()
        if not candles or len(candles) < 25:
            return []

        # ATR gate: skip if volatility too low (dead market)
        avg_range = market.get('avg_range_pips', 0)
        if avg_range < 1.5:
            self.logger.info(f"Structure: ATR too low ({avg_range:.1f}p < 1.5p), skipping")
            return []

        # Load historical win rates for dynamic confidence adjustment
        setup_win_rates = {}
        try:
            from src.common.db import get_setup_win_rates
            setup_win_rates = get_setup_win_rates()
        except Exception as e:
            self.logger.debug(f"Setup win rates: {e}")

        # v3.24.0 — Cleanup window adaptado por timeframe.
        # Bug observado: H1 #412/#413 mismo breakout 1.17769 con 5min apart.
        # Causa: level oscilaba 0.3p entre cycles + cleanup 30min suficiente para M5
        # pero insuficiente para H1 (candles 60min). Override en TechnicalAnalyzerH1.
        cleanup_window_sec = getattr(self, '_dedup_window_sec', 1800)  # default 30min
        now = time.time()
        if now - self._last_trigger_cleanup > 120:  # cleanup every 2 min
            cutoff = now - cleanup_window_sec
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

        # Recent closed candles — defined early so dynamic_conf() closure can use them
        # (Fix: previously defined AFTER dynamic_conf, causing silent NameError in candle pattern boost)
        prev1 = candles[-2] if len(candles) >= 2 else None
        prev2 = candles[-3] if len(candles) >= 3 else None

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

        # Helper: check if we already triggered this level recently.
        # v3.24.0: round(level, 4) = 1 pip granularity (vs 0.1p antes).
        # Niveles 1.17769 y 1.17770 ahora cuentan como mismo level para dedup.
        def already_triggered(level, direction):
            key = f"{round(level, 4)}_{direction}"
            return key in self._triggered_levels

        def mark_triggered(level, direction):
            key = f"{round(level, 4)}_{direction}"
            self._triggered_levels[key] = time.time()

        def dynamic_conf(_unused_base, setup_type, signal_direction=None):
            """Calculate confidence 100% from market conditions — NO hardcoded bases.
            Every point of confidence is earned from real market factors.
            signal_direction: 'CALL' or 'PUT' — used for trend/HTF alignment scoring."""
            conf = 40  # Conservative starting point — must earn confidence from real factors

            # ── 1. Setup-specific market alignment (0 to +20) ──
            if 'breakout' in setup_type or 'breakdown' in setup_type:
                if trend_strength == 'strong': conf += 18
                elif trend_strength == 'moderate': conf += 12
                elif trend_strength == 'weak': conf += 5
                # Breakouts need momentum
                if momentum in ('up', 'down'): conf += 8
            elif 'reversal' in setup_type:
                # Reversals are stronger at RSI extremes
                if rsi_zone in ('oversold', 'overbought'): conf += 18
                elif rsi < 35 or rsi > 65: conf += 10
                else: conf += 3
            elif 'bb_rejection' in setup_type:
                # BB rejections favor mean reversion
                if rsi_zone in ('oversold', 'overbought'): conf += 15
                elif rsi < 38 or rsi > 62: conf += 10
                else: conf += 5
            elif 'momentum' in setup_type:
                if momentum in ('up', 'down'): conf += 15
                if trend_strength in ('strong', 'moderate'): conf += 8
            elif 'crossover' in setup_type:
                if trend_strength == 'strong': conf += 12
                elif trend_strength == 'moderate': conf += 8
                if momentum in ('up', 'down'): conf += 6
            elif 'trend_cont' in setup_type:
                if trend_strength == 'strong': conf += 15
                elif trend_strength == 'moderate': conf += 10
                if momentum in ('up', 'down'): conf += 5
            elif 'level_bounce' in setup_type or 'level_rejection' in setup_type:
                conf += 5  # Basic proximity — rest comes from other factors
                if trend_strength in ('strong', 'moderate'): conf += 8

            # ── 2. Trend alignment (±10) ──
            if trend_strength == 'strong':
                conf += 10
            elif trend_strength == 'moderate':
                conf += 5
            elif trend_strength == 'weak':
                conf -= 3

            # ── 3. RSI context (±8) ──
            if 'reversal' in setup_type or 'rejection' in setup_type:
                if rsi_zone in ('oversold', 'overbought'):
                    conf += 8  # RSI confirms reversal/rejection
            elif 'breakout' in setup_type or 'momentum' in setup_type:
                if 40 < rsi < 60:
                    conf -= 6  # Neutral RSI weakens breakout signal
                elif rsi_zone in ('overbought',) and 'bull' in setup_type:
                    conf -= 4  # Overbought weakens bullish breakout
                elif rsi_zone in ('oversold',) and 'bear' in setup_type:
                    conf -= 4

            # ── 4. Volatility context (±8) ──
            vol = market.get('volatility', 'normal')
            if vol == 'high':
                if 'breakout' in setup_type or 'momentum' in setup_type:
                    conf += 8  # High vol favors breakouts
                elif 'rejection' in setup_type or 'bounce' in setup_type:
                    conf -= 4  # High vol hurts mean reversion
            elif vol == 'low':
                if 'rejection' in setup_type or 'bounce' in setup_type:
                    conf += 6  # Low vol favors mean reversion
                elif 'breakout' in setup_type:
                    conf -= 8  # Low vol breakouts unreliable

            # ── 4b. ATR gate: penalise very low volatility (< 2.0 pips on 5-min) ──
            _avg_range = market.get('avg_range_pips', 5.0)
            if _avg_range < 2.0:
                conf -= 12  # Near-dead market, signal unreliable

            # ── 5. Candle pattern context (±5) ──
            if prev1 is not None and prev2 is not None and len(candles) >= 3:
                body1 = abs(prev1['close'] - prev1['open']) * 10000
                body2 = abs(prev2['close'] - prev2['open']) * 10000
                if body1 > 3:  # Strong candle body
                    conf += 3
                if body1 > body2 * 1.5:  # Increasing momentum
                    conf += 2

            # ── 6. Historical win rate blend (if enough data, ±15) ──
            stats = setup_win_rates.get(setup_type, {})
            if stats.get('total', 0) >= 3:
                wr = stats['win_rate']
                if wr > 60: conf += 15
                elif wr > 50: conf += 8
                elif wr > 40: conf += 0
                elif wr > 30: conf -= 8
                else: conf -= 15

            # ── 7. Session awareness (±10) ──
            session_info = TechnicalAnalyzer.get_session_info()
            conf += session_info['conf_adj']

            # ── 8. Trend + HTF alignment — NEUTRALIZED in v3.7.0 ──
            # Empirical finding (75 trades, v3.6.3 - v3.7.0):
            #   - HTF aligned trades: 35% WR, -$50.70 PnL  (formula's "ideal" setup)
            #   - HTF counter trades: 54% WR, -$4.00 PnL  (formula penalized these)
            #   - Conf 85+ (formula's high-confidence): 22% WR, -$28.80 PnL
            #   - Conf <55 (formula's low-confidence):  47% WR, +$12.10 PnL  (only positive bucket)
            # Root cause: EUR/USD M5 is mean-reverting, not trending. The formula was
            # rewarding exhaustion entries (price already moved with HTF) and penalizing
            # mean-reversion entries (counter-HTF) which are actually the profitable setups.
            # Decision: neutralize directional alignment scoring entirely — let setup
            # quality (RSI, volatility, structure, daily range positioning in step 9) drive
            # confidence. If a future regime shows trend-following pays, re-enable.
            # See README changelog v3.7.0 for full analysis.
            #
            # NOTE: The variables below are still computed for logging/audit context
            # (consumed by llm_auditor and entry_context persistence), but produce no
            # confidence delta on this step.
            if signal_direction:
                is_with_trend = (
                    (signal_direction == 'CALL' and trend == 'bullish') or
                    (signal_direction == 'PUT' and trend == 'bearish')
                )
                is_against_trend = (
                    (signal_direction == 'CALL' and trend == 'bearish') or
                    (signal_direction == 'PUT' and trend == 'bullish')
                )
                is_with_htf = htf_bias and (
                    (signal_direction == 'CALL' and htf_bias == 'bullish') or
                    (signal_direction == 'PUT' and htf_bias == 'bearish')
                )
                is_against_htf = htf_bias and htf_bias != 'neutral' and (
                    (signal_direction == 'CALL' and htf_bias == 'bearish') or
                    (signal_direction == 'PUT' and htf_bias == 'bullish')
                )
                # No trend/HTF conf delta — see comment above. Variables retained for downstream consumers.
                _ = (is_with_trend, is_against_trend, is_with_htf, is_against_htf)

                # ── Momentum directional (±5) — RESTORED in v3.7.1 ──
                # Removing this in v3.7.0 was an overshoot of the alignment fix.
                # Trend/HTF are REGIME signals (mean-reverting market makes them
                # contraproducente). Momentum is a TIMING signal — short-term inertia.
                # If momentum runs against trade direction, the next 1-2 candles
                # likely push toward SL before any edge plays out.
                # Evidence: trade #351 PUT 2026-04-29 with momentum=up entered
                # against rising candles, SL hit in 30 seconds.
                is_with_momentum = (
                    (signal_direction == 'CALL' and momentum == 'up') or
                    (signal_direction == 'PUT' and momentum == 'down')
                )
                is_against_momentum = (
                    (signal_direction == 'CALL' and momentum == 'down') or
                    (signal_direction == 'PUT' and momentum == 'up')
                )
                if is_with_momentum:
                    conf += 5
                elif is_against_momentum:
                    conf -= 5

            # ── 9. Daily range positioning (±10) — macro context ──
            # If price at top of today's range → CALLs risky (exhaustion), PUTs favored (mean reversion)
            # If at bottom → CALLs favored, PUTs risky
            if signal_direction and daily_context and daily_context.get('today_pos') is not None:
                pos = daily_context['today_pos']  # 0 = at day low, 1 = at day high
                if signal_direction == 'CALL':
                    if pos > 0.85:  # near day high — fading
                        conf -= 10
                    elif pos < 0.25:  # near day low — ideal CALL
                        conf += 8
                else:  # PUT
                    if pos < 0.15:  # near day low — fading
                        conf -= 10
                    elif pos > 0.75:  # near day high — ideal PUT
                        conf += 8
                # Proximity to previous day's close (common pivot)
                prev_close = daily_context.get('prev_close', 0)
                if prev_close > 0 and abs(price - prev_close) < 0.0005:  # within 5p of prev close
                    conf -= 5  # price at reversion zone — uncertain direction

            # ── 10. (v3.39.1) Jitter random ±3 REMOVIDO: hacia NO determinista la
            # decision de ejecutar/no-ejecutar en el borde de min_confidence (mismo
            # estado de mercado -> trade o no-trade al azar). Bug confirmado por auditoria.
            # La confianza ahora es deterministica y reproducible.

            return max(20, min(95, conf))

        # prev1/prev2 already defined at top of function for dynamic_conf closure
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

        # ── Wick filter helper ──
        def wick_ratio(candle):
            """Return wick percentage of total range (0-1). High = likely false breakout."""
            rng = candle['high'] - candle['low']
            if rng <= 0:
                return 0
            body_top = max(candle['open'], candle['close'])
            body_bot = min(candle['open'], candle['close'])
            upper_wick = candle['high'] - body_top
            lower_wick = body_bot - candle['low']
            return max(upper_wick, lower_wick) / rng

        # ── 1. BREAKOUT above resistance (candle-close confirmed) ──
        # v3.13.0: max_dist tightened from 15 to 3 pips — breakouts >3p past level
        # are "stale" (price already moved, exhaustion). Empirical (29 historical):
        #   1-2p past: 5 trades, 80% WR, +$10.40 (fresh)
        #   3-5p past: 8 trades, 38% WR, -$11.20 (late = bad)
        #   5-7p past: 4 trades, 25% WR, -$6.20 (late = bad)
        # Today's losses #328 (+6.2p) and #332 (+5.6p) would have been blocked.
        for res in resistances:
            dist = (price - res) * 10000  # in pips
            # Require CLOSED candle above resistance (not just current price)
            candle_confirmed = prev1['close'] > res
            if 0.3 < dist < tuner_params.get('breakout_dist_max', 7) and crossed_above(res) and candle_confirmed:
                if not already_triggered(res, 'CALL'):
                    conf = dynamic_conf(tuner_params.get('conf_breakout', 70), 'breakout_resistance', 'CALL')
                    if trend == 'bullish':
                        conf += 10
                    if momentum == 'up':
                        conf += 5
                    if rsi_zone == 'overbought':
                        conf -= 10
                    # Wick filter: penalize if breakout candle has long wick (false breakout risk)
                    if wick_ratio(prev1) > 0.6:
                        conf -= 15
                    if conf >= min_confidence:
                        signals.append({
                            'direction': 'CALL',
                            'confidence': min(conf, 90),
                            'reason': f"Breakout sobre resistencia {res:.5f} (precio {price:.5f}, +{dist:.1f}p). Tendencia {trend} {trend_strength}.",
                            'setup_type': 'breakout_resistance',
                            'key_level': res
                        })
                        mark_triggered(res, 'CALL')

        # ── 2. BREAKDOWN below support (candle-close confirmed) ──
        # v3.13.0: max_dist tightened from 15 to 3 pips (same logic as breakouts)
        for sup in supports:
            dist = (sup - price) * 10000  # in pips
            candle_confirmed = prev1['close'] < sup
            if 0.3 < dist < tuner_params.get('breakdown_dist_max', 7) and crossed_below(sup) and candle_confirmed:
                if not already_triggered(sup, 'PUT'):
                    conf = dynamic_conf(tuner_params.get('conf_breakout', 70), 'breakdown_support', 'PUT')
                    if trend == 'bearish':
                        conf += 10
                    if momentum == 'down':
                        conf += 5
                    if rsi_zone == 'oversold':
                        conf -= 10
                    if wick_ratio(prev1) > 0.6:
                        conf -= 15
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
                    conf = dynamic_conf(tuner_params.get('conf_rsi_reversal', 72), 'rsi_reversal_support', 'CALL')
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
                    conf = dynamic_conf(tuner_params.get('conf_rsi_reversal', 72), 'rsi_reversal_resistance', 'PUT')
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
                        conf = dynamic_conf(tuner_params.get('conf_bb_rejection', 68), 'bb_rejection_upper', 'PUT')
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
                        conf = dynamic_conf(tuner_params.get('conf_bb_rejection', 68), 'bb_rejection_lower', 'CALL')
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
                        conf = dynamic_conf(tuner_params.get('conf_momentum', 72), 'momentum_expansion', direction)
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
                    conf = dynamic_conf(tuner_params.get('conf_ma_crossover', 65), 'ma_crossover_bull', 'CALL')
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
                    conf = dynamic_conf(tuner_params.get('conf_ma_crossover', 65), 'ma_crossover_bear', 'PUT')
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
                    conf = dynamic_conf(tuner_params.get('conf_trend_cont', 62), 'trend_continuation_bull', 'CALL')
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
                    conf = dynamic_conf(tuner_params.get('conf_trend_cont', 62), 'trend_continuation_bear', 'PUT')
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

        # ── 8. PRICE AT KEY LEVEL: DISABLED — 24% WR in 17 trades, worst performing setup ──
        # level_bounce and level_rejection removed based on statistical evidence

        # ── Candlestick pattern confirmation ──
        try:
            candle_patterns = self.detect_candle_patterns(candles)
        except Exception:
            candle_patterns = []

        for sig in signals:
            sig['candle_patterns'] = candle_patterns
            for pat in candle_patterns:
                # Boost confidence when pattern direction aligns with signal
                if sig['direction'] == 'CALL' and pat['direction'] == 'bullish':
                    sig['confidence'] = min(sig['confidence'] + pat['confidence_boost'], 95)
                    sig['reason'] += f" Patrón {pat['pattern']} confirma dirección alcista."
                elif sig['direction'] == 'PUT' and pat['direction'] == 'bearish':
                    sig['confidence'] = min(sig['confidence'] + pat['confidence_boost'], 95)
                    sig['reason'] += f" Patrón {pat['pattern']} confirma dirección bajista."
                # Penalize slightly when pattern contradicts signal
                elif pat['direction'] == 'bullish' and sig['direction'] == 'PUT':
                    sig['confidence'] = max(sig['confidence'] - pat['confidence_boost'] // 2, 20)
                    sig['reason'] += f" Precaución: patrón {pat['pattern']} contradice (alcista)."
                elif pat['direction'] == 'bearish' and sig['direction'] == 'CALL':
                    sig['confidence'] = max(sig['confidence'] - pat['confidence_boost'] // 2, 20)
                    sig['reason'] += f" Precaución: patrón {pat['pattern']} contradice (bajista)."

        # ── Counter-trend filter: require higher confidence when fighting trend/HTF ──
        # Two levels of fighting:
        #   Counter-M5-trend: price action on M5 is against signal. Escala por strength.
        #   Counter-HTF: H1 macro bias is against signal. MAS PELIGROSO (H1 >> M5).
        # If BOTH counter: block unless conf >= 85 (extreme confluence required)
        # If only HTF counter (M5 aligned): block unless conf >= 75 (H1 is macro truth)
        # If only M5 counter: current scale (60/70/80 by strength)
        if signals:
            filtered = []
            # Base thresholds for counter-M5-trend by strength
            if trend_strength == 'strong':
                m5_threshold = 80
            elif trend_strength == 'moderate':
                m5_threshold = 70
            else:
                m5_threshold = 60
            for sig in signals:
                is_counter_m5 = trend in ('bullish', 'bearish') and (
                    (sig['direction'] == 'CALL' and trend == 'bearish') or
                    (sig['direction'] == 'PUT' and trend == 'bullish')
                )
                is_counter_htf = htf_bias in ('bullish', 'bearish') and (
                    (sig['direction'] == 'CALL' and htf_bias == 'bearish') or
                    (sig['direction'] == 'PUT' and htf_bias == 'bullish')
                )

                if is_counter_m5 and is_counter_htf:
                    # Fighting BOTH M5 and H1 — suicide territory
                    min_req = 85
                    if sig['confidence'] >= min_req:
                        sig['reason'] += f" [contra M5+HTF, conf {sig['confidence']} >= {min_req} OK]"
                        filtered.append(sig)
                    else:
                        self.logger.info(f"Counter-M5+HTF filter: blocked {sig['direction']} {sig['setup_type']} conf={sig['confidence']} < {min_req} (trend={trend} {trend_strength}, htf={htf_bias})")
                elif is_counter_htf:
                    # M5 aligned but H1 against — common trap (we lost $20 today from this)
                    min_req = 75
                    if sig['confidence'] >= min_req:
                        sig['reason'] += f" [contra-HTF, conf {sig['confidence']} >= {min_req} OK]"
                        filtered.append(sig)
                    else:
                        self.logger.info(f"Counter-HTF filter: blocked {sig['direction']} {sig['setup_type']} conf={sig['confidence']} < {min_req} (htf={htf_bias}, M5 trend={trend})")
                elif is_counter_m5:
                    # Against M5 but HTF aligned or neutral
                    if sig['confidence'] >= m5_threshold:
                        sig['reason'] += f" [contra M5 {trend_strength}, conf {sig['confidence']} >= {m5_threshold} OK]"
                        filtered.append(sig)
                    else:
                        self.logger.info(f"Counter-M5 filter: blocked {sig['direction']} {sig['setup_type']} conf={sig['confidence']} < {m5_threshold} (trend={trend} {trend_strength})")
                else:
                    # Fully aligned or neutral — pass through
                    filtered.append(sig)
            signals = filtered

        # v3.34.0 (Fase C) — Entry Quality Gates basados en hallazgos del modelo ML.
        # v3.38.1 — DESACTIVADOS por default (config-driven). El sweep de significancia
        # (tools/sweep_entry_gates.py, 29 May) mostro que los 30 combos vel x body dan
        # blocked-set = RUIDO (CI cruza baseline 37.4% en TODOS): los gates no separaban
        # ganadores de perdedores en ningun threshold, solo recortaban frecuencia. Default
        # OFF restaura el comportamiento pre-v3.34.0. Reactivar con ENTRY_GATES_ENABLED=true
        # solo si en 300+ trades aparece un threshold que pase significancia.
        try:
            from src.common.config import Config as _GateCfg
            _gates_on = bool(getattr(_GateCfg, 'ENTRY_GATES_ENABLED', False))
            _vel_max = float(getattr(_GateCfg, 'ENTRY_GATE_VEL_MAX', 6.0))
            _body_max = float(getattr(_GateCfg, 'ENTRY_GATE_BODY_ATR_MAX', 1.3))
        except Exception:
            _gates_on, _vel_max, _body_max = False, 6.0, 1.3

        if _gates_on and signals and candles and len(candles) >= 11:
            atr_pips_now = avg_range
            # Last closed candle (vela de "entry")
            entry_candle = candles[-2] if len(candles) >= 2 else None
            # Velocity 5 candles: close actual - close 5 atras
            try:
                vel_5c_raw = (candles[-1]['close'] - candles[-6]['close']) / pip
            except Exception:
                vel_5c_raw = 0

            gates_pre = len(signals)
            gates_filtered = []
            for sig in signals:
                # Aligned velocity: positivo si momentum favorece direction
                if sig['direction'] == 'CALL':
                    vel_aligned = vel_5c_raw
                else:  # PUT
                    vel_aligned = -vel_5c_raw

                # Gate 1: Exhaustion velocity (entered too late after fast move)
                if vel_aligned > _vel_max:
                    self.logger.info(f"Entry gate (exhaustion velocity): blocked {sig['direction']} {sig['setup_type']} vel_5c={vel_aligned:.1f}p > {_vel_max}p")
                    continue

                # Gate 2: Body dominante (vela MUY fuerte = mean reversion riesgo)
                if entry_candle and atr_pips_now > 0:
                    body_pips = abs(entry_candle['close'] - entry_candle['open']) / pip
                    body_atr_ratio = body_pips / atr_pips_now
                    if body_atr_ratio > _body_max:
                        self.logger.info(f"Entry gate (body too dominant): blocked {sig['direction']} {sig['setup_type']} body/atr={body_atr_ratio:.2f} > {_body_max}")
                        continue

                gates_filtered.append(sig)

            blocked = gates_pre - len(gates_filtered)
            if blocked > 0:
                self.logger.info(f"Entry quality gates: blocked {blocked}/{gates_pre} signal(s) (exhaustion/body)")
            signals = gates_filtered

        if signals:
            self.logger.info(f"Structure scanner: {len(signals)} signals detected")
        return signals

    def detect_candle_patterns(self, candles):
        """Detect Japanese candlestick patterns in recent candles.
        Returns list of dicts: [{'pattern': str, 'direction': str, 'reliability': str, 'confidence_boost': int}]
        """
        patterns = []
        if not candles or len(candles) < 3:
            return patterns

        def _body(c):
            return abs(c['close'] - c['open'])

        def _range(c):
            return c['high'] - c['low']

        def _upper_wick(c):
            return c['high'] - max(c['open'], c['close'])

        def _lower_wick(c):
            return min(c['open'], c['close']) - c['low']

        def _is_green(c):
            return c['close'] > c['open']

        def _is_red(c):
            return c['close'] < c['open']

        last = candles[-1]
        prev = candles[-2]
        prev2 = candles[-3]

        body_last = _body(last)
        range_last = _range(last)
        upper_last = _upper_wick(last)
        lower_last = _lower_wick(last)

        # Avoid division by zero
        if range_last <= 0:
            return patterns

        # ── 1. Doji: body < 10% of total range ──
        if body_last < range_last * 0.10:
            patterns.append({
                'pattern': 'Doji',
                'direction': 'neutral',
                'reliability': 'low',
                'confidence_boost': 2
            })

        # ── 2. Hammer: small body + long lower wick (>2x body) ──
        # Typically at bottom of move (last 5 candles trending down)
        if body_last > 0 and lower_last > body_last * 2 and upper_last < body_last:
            # Check if at bottom of move: previous candles trending down
            lookback = candles[-6:-1] if len(candles) >= 6 else candles[:-1]
            trending_down = lookback[0]['close'] > lookback[-1]['close']
            if trending_down:
                patterns.append({
                    'pattern': 'Hammer',
                    'direction': 'bullish',
                    'reliability': 'medium',
                    'confidence_boost': 8
                })

        # ── 3. Shooting Star: small body + long upper wick (>2x body) ──
        # Typically at top of move (last 5 candles trending up)
        if body_last > 0 and upper_last > body_last * 2 and lower_last < body_last:
            lookback = candles[-6:-1] if len(candles) >= 6 else candles[:-1]
            trending_up = lookback[-1]['close'] > lookback[0]['close']
            if trending_up:
                patterns.append({
                    'pattern': 'Shooting Star',
                    'direction': 'bearish',
                    'reliability': 'medium',
                    'confidence_boost': 8
                })

        # ── 4. Bullish Engulfing: red candle followed by larger green candle ──
        if (_is_red(prev) and _is_green(last)
                and last['close'] > prev['open'] and last['open'] < prev['close']):
            patterns.append({
                'pattern': 'Bullish Engulfing',
                'direction': 'bullish',
                'reliability': 'high',
                'confidence_boost': 12
            })

        # ── 5. Bearish Engulfing: green candle followed by larger red candle ──
        if (_is_green(prev) and _is_red(last)
                and last['close'] < prev['open'] and last['open'] > prev['close']):
            patterns.append({
                'pattern': 'Bearish Engulfing',
                'direction': 'bearish',
                'reliability': 'high',
                'confidence_boost': 12
            })

        # ── 6. Marubozu: full body, very small wicks (wicks < 10% of range) ──
        if (upper_last < range_last * 0.10 and lower_last < range_last * 0.10
                and body_last > range_last * 0.80):
            direction = 'bullish' if _is_green(last) else 'bearish'
            patterns.append({
                'pattern': 'Marubozu',
                'direction': direction,
                'reliability': 'high',
                'confidence_boost': 10
            })

        # ── 7. Morning Star: big red, small body, big green (3-candle) ──
        range_prev2 = _range(prev2)
        range_prev = _range(prev)
        body_prev2 = _body(prev2)
        body_prev = _body(prev)

        if (range_prev2 > 0 and range_prev > 0
                and _is_red(prev2) and body_prev2 > range_prev2 * 0.5
                and body_prev < range_prev * 0.30
                and _is_green(last) and body_last > range_last * 0.5
                and last['close'] > (prev2['open'] + prev2['close']) / 2):
            patterns.append({
                'pattern': 'Morning Star',
                'direction': 'bullish',
                'reliability': 'high',
                'confidence_boost': 15
            })

        # ── 8. Evening Star: big green, small body, big red (3-candle) ──
        if (range_prev2 > 0 and range_prev > 0
                and _is_green(prev2) and body_prev2 > range_prev2 * 0.5
                and body_prev < range_prev * 0.30
                and _is_red(last) and body_last > range_last * 0.5
                and last['close'] < (prev2['open'] + prev2['close']) / 2):
            patterns.append({
                'pattern': 'Evening Star',
                'direction': 'bearish',
                'reliability': 'high',
                'confidence_boost': 15
            })

        return patterns

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

    # ── Session & Adaptive SL/TP helpers ──

    @staticmethod
    def get_session_info():
        """Return current trading session info based on UTC hour.
        Session adjustments reflect general forex liquidity patterns (not calibrated to contaminated data).
        Learning engine will adjust per-session bias organically as clean data accumulates.
        """
        utc_hour = datetime.now(timezone.utc).hour
        if 7 <= utc_hour < 12:
            return {'session': 'london', 'conf_adj': 8, 'spread_est': 0.6, 'label': 'London'}
        elif 12 <= utc_hour < 16:
            # London/NY overlap — best liquidity for EURUSD
            return {'session': 'overlap', 'conf_adj': 5, 'spread_est': 0.5, 'label': 'London/NY Overlap'}
        elif 16 <= utc_hour < 20:
            return {'session': 'ny', 'conf_adj': 0, 'spread_est': 0.8, 'label': 'NY'}
        else:
            return {'session': 'off_hours', 'conf_adj': -10, 'spread_est': 1.5, 'label': 'Off-hours'}

    def compute_adaptive_sl_tp(self, direction, price, market_state, profile, trigger_type=None, sl_tp_advice=None):
        """
        Compute SL/TP adapted to current volatility via ATR-14.
        - SL: ATR * 0.8, clamped between profile min and profile * 2.5
        - TP: maintains profile R:R ratio relative to SL
        - Falls back to profile values if ATR unavailable

        v3.15.0: Si sl_tp_advice tiene recomendación para este trigger_type
        (de Gemma post_trade aggregada en últimos 48h con N>=3 y consenso>60%),
        usar como SL/TP base (ajustado a profile bounds).
        """
        pip = 0.0001
        prof_sl = profile.get('stop_loss_pips', 5)
        prof_tp = profile.get('take_profit_pips', 25)
        structures = market_state.get('chart_structures', {})
        supports = structures.get('supports', [])
        resistances = structures.get('resistances', [])

        # v3.15.0 — Apply Gemma SL/TP recommendation if trigger has consensus advice
        learning_sl_override = None
        learning_tp_override = None
        if sl_tp_advice and trigger_type and trigger_type in sl_tp_advice:
            advice = sl_tp_advice[trigger_type]
            if isinstance(advice, dict) and advice.get('action') in ('widen', 'tighten'):
                rec_sl = advice.get('sl_pips', 0)
                rec_tp = advice.get('tp_pips', 0)
                # Validate: only apply if recommendation differs significantly from profile
                if rec_sl > 0 and abs(rec_sl - prof_sl) / prof_sl > 0.15:
                    learning_sl_override = rec_sl
                    self.logger.info(f"Learning SL override for {trigger_type}: {advice['action']} → {rec_sl}p (profile was {prof_sl}p, n={advice.get('sample_size')})")
                if rec_tp > 0 and abs(rec_tp - prof_tp) / prof_tp > 0.15:
                    learning_tp_override = rec_tp

        # ATR-based SL: use 80% of ATR-14, clamped to profile bounds
        # Hard minimum: never below 2.0 pips regardless of ATR or profile
        SL_HARD_MIN = 2.0
        atr = market_state.get('avg_range_pips', 0)

        # If learning override exists, use it as the base (still respect ATR bounds)
        effective_prof_sl = learning_sl_override if learning_sl_override else prof_sl

        if atr > 0:
            atr_sl = round(atr * 0.8, 1)
            sl_min = max(effective_prof_sl, SL_HARD_MIN)
            sl_max = round(effective_prof_sl * 2.5, 1)
            final_sl = max(sl_min, min(sl_max, atr_sl))
        else:
            final_sl = max(effective_prof_sl, SL_HARD_MIN)

        # TP: maintain R:R ratio from profile or use learning override
        # v3.39.1 FIX: rr_ratio se define SIEMPRE (antes solo en el else, y el bloque
        # estructural de abajo lo usaba incondicionalmente -> NameError cuando habia
        # learning_tp_override + ensanche de SL estructural). Bug confirmado por auditoria.
        rr_ratio = prof_tp / prof_sl if prof_sl > 0 else 4.0
        if learning_tp_override:
            final_tp = round(learning_tp_override, 1)
        else:
            final_tp = round(final_sl * rr_ratio, 1)

        # Optionally place SL behind nearest structural level (can WIDEN, not narrow)
        # v3.8.0: ADAPTIVE cap. Both v3.6.x (prof_sl*2.5=8.75p) and v3.7.0 (min cap 5.6p)
        # had problems:
        # - v3.6.x: too loose in low-vol → catastrophic high-conf losses
        # - v3.7.0: too tight in high-vol → SL inside normal candle noise (30 Apr disaster)
        # New formula uses MAX of (ATR*1.0, prof_sl*1.5):
        # - In ATR=3p (calm): max(3, 5.25) = 5.25p — protects from inflation
        # - In ATR=7p (volatile): max(7, 5.25) = 7p — adapts to actual volatility
        # Empirical: data shows SL/ATR sweet spot is 1.0-1.5x (55% WR, +$14 PnL).
        # Current bucket SL/ATR 0.6-1.0 had -$70 PnL — proof that tight cap loses.
        if atr > 0:
            sl_max_struct = round(max(atr * 1.0, prof_sl * 1.5), 1)
        else:
            sl_max_struct = round(prof_sl * 1.5, 1)
        if direction == 'CALL' and supports:
            below_sups = [s for s in supports if s < price]
            if below_sups:
                nearest_sup = max(below_sups)
                structural_sl = (price - nearest_sup) * 10000 + 1.0
                if structural_sl > final_sl and structural_sl <= sl_max_struct:
                    final_sl = round(structural_sl, 1)
                    if not learning_tp_override:  # v3.39.1: preservar el TP del learning
                        final_tp = round(final_sl * rr_ratio, 1)
        elif direction == 'PUT' and resistances:
            above_res = [r for r in resistances if r > price]
            if above_res:
                nearest_res = min(above_res)
                structural_sl = (nearest_res - price) * 10000 + 1.0
                if structural_sl > final_sl and structural_sl <= sl_max_struct:
                    final_sl = round(structural_sl, 1)
                    if not learning_tp_override:  # v3.39.1: preservar el TP del learning
                        final_tp = round(final_sl * rr_ratio, 1)

        # TP priority: next structural level if reachable with min R:R 1:1.5, else ATR cap
        # Structural TP hits natural levels (resistance for CALL, support for PUT) where price naturally pauses
        structural_tp_pips = None
        if direction == 'CALL' and resistances:
            above_res = [r for r in resistances if r > price]
            if above_res:
                nearest_res = min(above_res)
                # Buffer: aim 1 pip BEFORE the resistance to maximize fill probability
                candidate_tp = (nearest_res - price) * 10000 - 1.0
                if candidate_tp >= final_sl * 1.5:  # at least 1:1.5 R:R
                    structural_tp_pips = round(candidate_tp, 1)
        elif direction == 'PUT' and supports:
            below_sups = [s for s in supports if s < price]
            if below_sups:
                nearest_sup = max(below_sups)
                candidate_tp = (price - nearest_sup) * 10000 - 1.0
                if candidate_tp >= final_sl * 1.5:
                    structural_tp_pips = round(candidate_tp, 1)

        # ATR-based TP cap (fallback)
        # Research consensus (2026): M5 scalping profitable R:R = 1:1 to 1:1.5 with 55-65% WR
        # TP cap = ATR*2 is realistic for M5 (vs ATR*3 which was too ambitious)
        if atr > 0:
            atr_floor = max(atr, 2.0)
            tp_cap = round(atr_floor * 2.0, 1)
            min_rr = 1.2  # allow lower R:R if market is tight; research accepts 1:1 for high-WR scalping
            tp_min = round(final_sl * min_rr, 1)
            original_tp = final_tp
            # Priority: use structural TP if available and within reasonable bound (<= 2x cap)
            if structural_tp_pips is not None and structural_tp_pips <= tp_cap * 2:
                final_tp = structural_tp_pips
                method_tp = 'structural'
            else:
                final_tp = min(final_tp, tp_cap)
                final_tp = max(final_tp, tp_min)
                method_tp = 'atr_cap'
            if original_tp != final_tp:
                self.logger.info(f"TP [{method_tp}]: original={original_tp}p -> {final_tp}p (ATR={atr_floor:.1f}p, SL={final_sl}p, R:R=1:{final_tp/max(final_sl,0.1):.1f})")

        method = 'atr_adaptive' if atr > 0 else 'profile'
        if supports or resistances:
            method += '+struct'

        # Calculate actual prices
        if direction == 'CALL':
            sl = round(price - final_sl * pip, 5)
            tp = round(price + final_tp * pip, 5)
        else:
            sl = round(price + final_sl * pip, 5)
            tp = round(price - final_tp * pip, 5)

        return {
            'sl': sl, 'tp': tp,
            'sl_pips': round(final_sl, 1), 'tp_pips': round(final_tp, 1),
            'rr_ratio': round(final_tp / final_sl, 2) if final_sl > 0 else 5.0,
            'method': method
        }
