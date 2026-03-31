"""
Professional Trading Knowledge Base
====================================
Curated trading methodology for EUR/USD scalping.
Covers: VWAP, Order Flow, Order Book, Japanese Candlesticks, Break Even,
and general trading strategies.
"""


# =============================================================================
# 1. VWAP (Volume Weighted Average Price) METHODOLOGY
# =============================================================================
VWAP_RULES = {
    "description": (
        "VWAP represents fair market value based on where the highest "
        "transaction concentration occurs. It combines price, volume, value, "
        "and time across multiple timeframes simultaneously."
    ),
    "statistical_foundation": {
        "band_1_std": "68% of data - equilibrium zone",
        "band_2_std": "95% of data - moderate disequilibrium",
        "band_3_std": "99% of data - extreme disequilibrium / trending",
        "note": "Price outside 1st deviation = market disequilibrium or trend"
    },
    "entry_signals": {
        "long": [
            "Price approaches VWAP from below after disequilibrium period",
            "Price bounces off lower deviation band with volume confirmation",
            "Price crosses above VWAP with increasing delta (order flow)",
            "Price below VWAP = undervalued IF demand appears in Order Flow"
        ],
        "short": [
            "Price fails at upper deviation bands with weakness confirmation",
            "Price approaches VWAP from above after disequilibrium period",
            "Price above VWAP = overvalued IF supply dominates in Order Flow",
            "Price rejected at upper deviation band with negative delta"
        ]
    },
    "exit_signals": [
        "Exit when VWAP fails to support price in your trade direction",
        "Exit at opposite deviation band (take profit at band boundary)",
        "Exit when delta diverges from price direction near VWAP"
    ],
    "confluence_requirements": [
        "VWAP alone CANNOT generate trades - always combine with:",
        "  - Order Flow analysis (aggressive sellers/buyers at resistance)",
        "  - MACD divergences",
        "  - Volume strength/weakness assessment",
        "  - Price action confirmation"
    ],
    "timeframe_rules": {
        "daily_vwap": "Allow 5 hours of trading before trusting",
        "weekly_vwap": "Wait 2 days (Mon-Tue completion) before trusting",
        "monthly_vwap": "Require 10 days minimum before trusting",
        "session_filter": "Skip first/last hour of American session (noise)",
        "scalping": "Use daily VWAP with weekly VWAP for reference"
    },
    "mean_reversion_setup": (
        "When price breaks deviation bands (disequilibrium), expect regression "
        "toward VWAP equilibrium zone. The VWAP acts as a comfort zone / magnet."
    ),
    "trend_following": (
        "If price and VWAP converge during uptrends, momentum maintained. "
        "Divergence between price and VWAP signals weakening conviction."
    ),
    "scalping_application": {
        "buy_zone": "Price at or below daily VWAP with bullish order flow",
        "sell_zone": "Price at or above daily VWAP with bearish order flow",
        "target": "Opposite deviation band or next VWAP level",
        "stop_loss": "Below/above the deviation band that triggered entry",
        "risk_reward": "Minimum 1:1.5 for scalping setups"
    }
}


# =============================================================================
# 2. ORDER FLOW & ORDER BOOK METHODOLOGY
# =============================================================================
ORDER_FLOW_RULES = {
    "description": (
        "Order Flow is the union of vertical volume (orders crossed at a specific "
        "moment) and horizontal volume (orders crossed at a specific price level). "
        "It displays contracts executed by buyers (Bid) and sellers (Ask) at "
        "particular price levels and times."
    ),
    "core_concepts": {
        "market_orders": "Execute immediately - these MOVE price",
        "limit_orders": "Execute only at specified price - these ABSORB price movement",
        "bullish_pressure": "Aggressive buying through ASK eliminates offered liquidity",
        "bearish_pressure": "Aggressive selling through BID eliminates demand liquidity",
        "delta": "Difference between aggressive buying and selling volume",
        "positive_delta": "Buyers dominant - bullish bias",
        "negative_delta": "Sellers dominant - bearish bias"
    },
    "footprint_reading": {
        "cluster_structure": (
            "Left side = buy orders executed; Right side = sell orders executed. "
            "Higher numbers indicate stronger pressure at that level. "
            "Large clusters reveal institutional interest concentration."
        ),
        "poc_following": (
            "Follow the movement of the POC (Point of Control / high volume node) "
            "to determine market direction. POC shift direction = market direction."
        ),
        "volume_comparison": (
            "Compare current candle clusters to previous ones. Increasing volume "
            "at support/resistance with directional bias signals breakout direction."
        )
    },
    "entry_patterns": {
        "absorption": {
            "description": (
                "Large sell orders get absorbed by persistent buying. "
                "Indicates buyers willing to chase price higher. "
                "Precedes upward moves. (Reverse for bearish absorption.)"
            ),
            "entry": "Enter in direction of absorbing side after confirmation",
            "stop": "Below the absorption level",
            "target": "Next significant volume level"
        },
        "imbalance": {
            "description": (
                "One side (buyers or sellers) shows significantly stronger "
                "conviction. Directional indicator suggesting momentum continuation."
            ),
            "entry": "Enter in direction of imbalance after price confirms",
            "stop": "Behind the imbalance candle",
            "target": "Next support/resistance zone"
        },
        "delta_divergence": {
            "description": (
                "Price rises but delta weakens = potential reversal signal. "
                "Price falls but delta strengthens = potential reversal signal."
            ),
            "entry": "Enter against price direction when delta diverges strongly",
            "stop": "Above/below the divergence swing point",
            "target": "VWAP or mean reversion level"
        },
        "cluster_exhaustion": {
            "description": (
                "Clusters diminish significantly at directional extremes. "
                "Waning conviction = potential reversal."
            ),
            "entry": "Enter reversal trade when volume clusters thin out at extremes",
            "stop": "Beyond the exhaustion swing",
            "target": "POC or VWAP level"
        }
    },
    "exit_rules": [
        "Exit when delta reverses sharply from established trend direction",
        "Exit when clusters diminish significantly (waning conviction)",
        "Exit at established supply/demand zones without sustained volume",
        "Exit when structural imbalances exhaust"
    ],
    "integration_note": (
        "Order Flow is NOT a standalone system. It enhances existing strategies "
        "by providing granular detail unavailable in traditional candles. "
        "Combine with: Market structure, Volume Profile, VWAP, Price Action."
    )
}


# =============================================================================
# 3. JAPANESE CANDLESTICK PATTERNS
# =============================================================================
CANDLESTICK_PATTERNS = {
    "description": (
        "Japanese candlesticks show OHLC (Open, High, Low, Close) data. "
        "Each candle has a body and wicks. Green/white = bullish close, "
        "Red/black = bearish close. Patterns reflect buyer/seller psychology."
    ),
    "bullish_patterns": {
        "hammer": {
            "structure": "Small body + long lower wick at bottom of downtrend",
            "signal": "Reversal - selling pressure exhausted, buyers stepping in",
            "entry": "Buy when next candle confirms (closes above hammer's body)",
            "stop": "Below the hammer's low",
            "reliability": "High when at key support level with volume"
        },
        "inverted_hammer": {
            "structure": "Small body + long upper wick at bottom of downtrend",
            "signal": "Potential reversal - buying pressure despite resistance",
            "entry": "Confirmation required from next candle closing higher",
            "stop": "Below the inverted hammer's low",
            "reliability": "Medium - needs strong confirmation"
        },
        "bullish_engulfing": {
            "structure": "Red candle fully engulfed by larger green candle",
            "signal": "Strong reversal - buyers overwhelm sellers",
            "entry": "Enter long after second (green) candle closes",
            "stop": "Below the engulfing pattern's low",
            "reliability": "High - one of the strongest reversal signals"
        },
        "piercing_line": {
            "structure": "Red candle + green candle opening below, closing above midpoint",
            "signal": "Bullish reversal - cycle change possibility",
            "entry": "Green candle closes above 50% of red candle's body",
            "stop": "Below the pattern's low",
            "reliability": "Medium-High"
        },
        "morning_star": {
            "structure": "Three candles: large red, small body (gap down), large green",
            "signal": "Strong reversal - selling pressure decreasing",
            "entry": "After third candle (green) closes above first candle's midpoint",
            "stop": "Below the star (middle candle) low",
            "reliability": "High - triple candle confirmation"
        }
    },
    "bearish_patterns": {
        "hanging_man": {
            "structure": "Small body + long lower shadow at top of uptrend",
            "signal": "Reversal warning - sales intensifying",
            "entry": "Exit longs / enter short after next candle confirms down",
            "stop": "Above the hanging man's high",
            "reliability": "Medium - needs confirmation"
        },
        "shooting_star": {
            "structure": "Small body + long upper wick at top of uptrend",
            "signal": "Bearish reversal - buyers rejected at highs",
            "entry": "Enter short after next candle confirms bearish close",
            "stop": "Above the shooting star's high",
            "reliability": "High when at resistance level"
        },
        "bearish_engulfing": {
            "structure": "Green candle fully engulfed by larger red candle",
            "signal": "Strong reversal - sellers overwhelm buyers",
            "entry": "Enter short after the engulfing red candle closes",
            "stop": "Above the engulfing pattern's high",
            "reliability": "High - strong reversal signal"
        },
        "evening_star": {
            "structure": "Three candles: large green, small body, large red",
            "signal": "Strong bearish reversal - buying exhaustion",
            "entry": "After third candle (red) closes below first candle's midpoint",
            "stop": "Above the star (middle candle) high",
            "reliability": "High - triple candle confirmation"
        },
        "three_black_crows": {
            "structure": "Three consecutive large red candles with short wicks",
            "signal": "Strong downtrend - each opens near prior close, closes lower",
            "entry": "Enter short or exit all longs immediately",
            "stop": "Above the first crow's high",
            "reliability": "Very High - strong continuation/reversal"
        }
    },
    "indecision_patterns": {
        "doji": {
            "structure": "Open and close nearly identical - very small body",
            "signal": "Indecision - no clear price intention",
            "entry": "Wait for NEXT candle to determine direction",
            "note": "Doji at key levels = potential reversal",
            "reliability": "Low alone - needs context and confirmation"
        },
        "marubozu": {
            "structure": "Full body with no wicks - pure directional candle",
            "signal": "Strong conviction in direction (bullish or bearish)",
            "entry": "Continuation entry in marubozu direction",
            "reliability": "High - shows complete dominance by one side"
        }
    },
    "scalping_best_patterns": [
        "Bullish/Bearish Engulfing at key levels (VWAP, S/R)",
        "Hammer/Shooting Star at deviation bands",
        "Doji at VWAP followed by directional candle",
        "Marubozu as momentum confirmation after entry signal"
    ],
    "critical_warning": (
        "Trading ONLY with candlestick patterns brings disadvantages. "
        "Patterns don't show complete market conditions. "
        "ALWAYS combine with: VWAP, Order Flow, Volume, Support/Resistance."
    )
}


# =============================================================================
# 4. BREAK EVEN METHODOLOGY
# =============================================================================
BREAK_EVEN_RULES = {
    "description": (
        "Break Even is the point where a trade neither gains nor loses. "
        "Moving stop loss to break even protects capital and converts "
        "a risk trade into a zero-loss position."
    ),
    "true_break_even_calculation": (
        "Break Even is NOT just the entry price. Must include: "
        "spread/commission, swap fees, and slippage. "
        "Example: Entry at 1.0800 with 1.2 pip spread -> true BE = 1.08012"
    ),
    "methodology": {
        "step_1": "Enter trade with initial stop loss at predetermined level",
        "step_2": "Wait for price to move in your favor (minimum 1:1 R:R distance)",
        "step_3": "Close 50% of position at first target",
        "step_4": "Move stop loss from original level to break even (entry + costs)",
        "step_5": "Let remaining 50% run with zero downside risk"
    },
    "when_to_move_to_break_even": [
        "Price has moved at least 1x your initial risk in your favor",
        "Price has reached a significant support/resistance level",
        "You have already taken partial profit (50% position closed)",
        "A new structure has formed that protects your entry level",
        "Time-based: if trade hasn't moved after expected duration"
    ],
    "when_NOT_to_move_to_break_even": [
        "Price has barely moved past entry - gets stopped out on noise",
        "During high volatility news events (wicks will hunt BE levels)",
        "When price is in a strong trend - let it breathe",
        "If your strategy requires wider stops for profitability"
    ],
    "scalping_break_even": {
        "rule": "Move to BE after price reaches 1:1 risk/reward",
        "partial_close": "Close 50-70% at first target, trail remainder",
        "aggressive": "Some scalpers move to BE at 0.5:1 in fast markets",
        "conservative": "Wait for 1.5:1 before moving to BE in slow markets"
    },
    "position_management_example": {
        "entry": "Buy EUR/USD at 1.0800",
        "stop_loss": "1.0785 (15 pips risk)",
        "target_1": "1.0815 (15 pips = 1:1 R:R)",
        "action_at_target_1": "Close 50%, move stop to 1.08012 (BE + spread)",
        "target_2": "1.0830 (30 pips = 2:1 R:R for remaining 50%)",
        "result_if_stopped": "Net profit from first 50%, zero loss on remainder"
    }
}


# =============================================================================
# 5. COMPREHENSIVE SCALPING STRATEGY (EUR/USD)
# =============================================================================
SCALPING_STRATEGY = {
    "description": (
        "Combined professional methodology integrating VWAP, "
        "Order Flow, Japanese Candlesticks, and Break Even management "
        "for EUR/USD intraday scalping."
    ),
    "timeframes": {
        "analysis": "15-minute chart for trend/structure identification",
        "entry": "1-minute or 5-minute chart for precise entries",
        "vwap_reference": "Daily VWAP with weekly VWAP overlay"
    },
    "session_filter": {
        "best_sessions": "London (08:00-12:00 UTC) and NY overlap (13:00-17:00 UTC)",
        "avoid": "First/last hour of American session (opening/closing noise)",
        "avoid_also": "Asian session for EUR/USD (low volatility, wide spreads)"
    },
    "entry_checklist": {
        "step_1_trend": (
            "Identify trend on 15min: price vs VWAP position, "
            "MA fast vs MA slow, higher highs/lows or lower highs/lows"
        ),
        "step_2_level": (
            "Wait for price to reach a key level: VWAP, deviation band, "
            "support/resistance, or previous session high/low"
        ),
        "step_3_order_flow": (
            "Confirm with Order Flow: absorption pattern at level, "
            "delta supporting your direction, cluster volume confirmation"
        ),
        "step_4_candle_pattern": (
            "Wait for candlestick confirmation: engulfing, hammer, "
            "shooting star, or marubozu at the key level"
        ),
        "step_5_execute": (
            "Enter trade with stop loss below/above the pattern. "
            "Risk no more than 1-2% of account per trade."
        )
    },
    "exit_strategy": {
        "target_1": "First deviation band or next VWAP level (close 50%)",
        "target_2": "Second deviation band or session extreme (remaining 50%)",
        "break_even": "Move stop to BE after reaching 1:1 R:R",
        "trailing_stop": "Trail stop behind each new swing after 1.5:1 R:R",
        "max_loss": "Cut trade at initial stop loss - no averaging down"
    },
    "risk_management": {
        "max_risk_per_trade": "1-2% of total account",
        "max_daily_loss": "3-5% of total account then STOP trading",
        "max_open_positions": "1-2 simultaneous trades",
        "risk_reward_minimum": "1:1.5 minimum, prefer 1:2 or better",
        "position_sizing": "Calculate lots based on stop distance and max risk %",
        "leverage_warning": (
            "Leverage amplifies both gains and losses. "
            "Use minimum leverage necessary for position size."
        )
    },
    "long_setup_example": {
        "condition": "Price below daily VWAP, approaching -1 deviation band",
        "order_flow": "Absorption pattern: large sells being absorbed by buyers",
        "candle": "Bullish engulfing or hammer forming at -1 deviation",
        "entry": "Above the confirmation candle's high",
        "stop": "Below the pattern low (typically 8-15 pips for EUR/USD)",
        "tp1": "Daily VWAP level (close 50%)",
        "tp2": "+1 deviation band (close remaining 50%)",
        "be_trigger": "Move stop to BE when price reaches VWAP"
    },
    "short_setup_example": {
        "condition": "Price above daily VWAP, approaching +1 deviation band",
        "order_flow": "Absorption pattern: large buys being absorbed by sellers",
        "candle": "Bearish engulfing or shooting star at +1 deviation",
        "entry": "Below the confirmation candle's low",
        "stop": "Above the pattern high (typically 8-15 pips for EUR/USD)",
        "tp1": "Daily VWAP level (close 50%)",
        "tp2": "-1 deviation band (close remaining 50%)",
        "be_trigger": "Move stop to BE when price reaches VWAP"
    }
}


# =============================================================================
# 6. TRADING STRATEGIES OVERVIEW (2026 Best Practices)
# =============================================================================
TRADING_STRATEGIES_2026 = {
    "scalping": {
        "timeframe": "1-5 minute charts",
        "indicators": ["VWAP", "Order Flow", "RSI", "MACD"],
        "session": "London and NY overlap for EUR/USD",
        "trades_per_day": "5-15 trades",
        "hold_time": "1-30 minutes",
        "risk_per_trade": "0.5-1% of account",
        "key_principle": "Quick entries, quick exits, tight stops"
    },
    "day_trading": {
        "timeframe": "5-15 minute charts with 1H context",
        "indicators": ["RSI", "MACD", "Stochastic", "VWAP"],
        "session": "Full London or NY session",
        "trades_per_day": "2-5 trades",
        "hold_time": "30 minutes to several hours",
        "risk_per_trade": "1-2% of account",
        "key_principle": "All positions closed by session end"
    },
    "swing_trading": {
        "timeframe": "4H and Daily charts",
        "indicators": ["Moving Averages", "RSI", "Support/Resistance"],
        "hold_time": "2-10 days",
        "risk_per_trade": "1-3% of account",
        "key_principle": "Capture medium-term swings within larger trends"
    },
    "price_action": {
        "timeframe": "Any - framework dependent",
        "method": "Examine patterns, trends, candle formations",
        "focus": "Market psychology through pure price movement",
        "no_indicators": "Based exclusively on price - no lagging indicators",
        "key_principle": "Understanding supply/demand through price behavior"
    },
    "trend_trading": {
        "entry": "Higher highs + higher lows = uptrend entry",
        "exit": "Lower highs + lower lows = downtrend / exit",
        "indicators": ["Moving Averages", "Trendlines", "ADX"],
        "key_principle": "Trade with the trend, not against it"
    },
    "range_trading": {
        "entry": "Buy at support, sell at resistance in sideways markets",
        "indicators": ["RSI", "Stochastic for overbought/oversold"],
        "limitation": "Profits limited by range boundaries",
        "key_principle": "Mean reversion within defined boundaries"
    },
    "algorithmic_trading": {
        "execution": "Predefined rules for entry, exit, stop-loss",
        "advantage": "No emotional interference, millisecond execution",
        "models": "Mathematical models + statistical formulas",
        "key_principle": "Systematic, rule-based, repeatable"
    },
    "ai_integration_2026": (
        "In 2026, technology is the main differentiator. Retail traders "
        "now access real-time data feeds, AI-assisted analysis, and "
        "automated execution systems. Algorithms following trend rules "
        "(MA crosses, volatility filters, position management) operate "
        "without emotional interference."
    ),
    "general_2026_wisdom": (
        "2026 does not reward quantity of trades but QUALITY, PATIENCE, "
        "and MACRO reading. Success requires selection, discipline, and context."
    )
}


# =============================================================================
# 7. HELPER FUNCTION - Get all methodology as a single dict
# =============================================================================
def get_full_methodology():
    """Return the complete trading methodology knowledge base."""
    return {
        "vwap": VWAP_RULES,
        "order_flow": ORDER_FLOW_RULES,
        "candlestick_patterns": CANDLESTICK_PATTERNS,
        "break_even": BREAK_EVEN_RULES,
        "scalping_strategy": SCALPING_STRATEGY,
        "strategies_2026": TRADING_STRATEGIES_2026
    }


def get_entry_rules_summary():
    """Return a condensed summary of all entry rules for the scalping bot."""
    return {
        "long_conditions": [
            "Price at or below daily VWAP (undervalued zone)",
            "Price near -1 or -2 standard deviation band",
            "Order Flow shows absorption: sellers being absorbed by buyers",
            "Delta turning positive after bearish pressure",
            "Bullish candlestick confirmation: engulfing, hammer, morning star",
            "RSI below 30 (oversold) recovering upward",
            "Session: London or NY overlap (not Asian session)"
        ],
        "short_conditions": [
            "Price at or above daily VWAP (overvalued zone)",
            "Price near +1 or +2 standard deviation band",
            "Order Flow shows absorption: buyers being absorbed by sellers",
            "Delta turning negative after bullish pressure",
            "Bearish candlestick confirmation: engulfing, shooting star, evening star",
            "RSI above 70 (overbought) declining",
            "Session: London or NY overlap (not Asian session)"
        ],
        "mandatory_filters": [
            "Minimum 2 of the above conditions must align (confluence)",
            "Never trade against the 15-minute trend direction",
            "Risk no more than 1-2% per trade",
            "Stop loss must be placed at a structural level (not arbitrary pips)",
            "Minimum 1:1.5 risk/reward ratio required"
        ]
    }


def get_exit_rules_summary():
    """Return a condensed summary of all exit rules for the scalping bot."""
    return {
        "take_profit": [
            "TP1: Next VWAP level or first deviation band (close 50%)",
            "TP2: Second deviation band or session extreme (close remaining)",
            "Alternative: Exit at next significant Order Flow resistance/support"
        ],
        "stop_loss": [
            "Initial: Below/above the entry pattern's structural level",
            "Break Even: Move to BE after 1:1 risk/reward reached",
            "Trailing: Trail behind each new swing after 1.5:1 R:R reached"
        ],
        "forced_exit": [
            "Max daily loss reached (3-5% of account) -> stop all trading",
            "Delta reverses sharply against position",
            "Order Flow clusters diminish (conviction fading)",
            "End of preferred trading session approaching",
            "High-impact news event imminent (within 15 minutes)"
        ]
    }
