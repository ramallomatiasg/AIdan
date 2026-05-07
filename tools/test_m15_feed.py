"""
Test standalone: validar que TechnicalAnalyzerM15 fetchea candles M15 OK.
No toca AIdan corriendo, no escribe a DB.

Uso:
    python tools/test_m15_feed.py
"""
import sys
import os
import logging

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('test_m15')


def test_fetch_candles():
    """Verify that we can fetch M15 candles via the inherited price feed."""
    from src.analyzer.technical_m15 import TechnicalAnalyzerM15, M15_PROFILE

    logger.info(f"M15_PROFILE: {M15_PROFILE}")
    tech = TechnicalAnalyzerM15(logger)

    candles = tech._fetch_candles()
    assert candles, "No candles returned"
    assert len(candles) >= 50, f"Too few candles: {len(candles)}"

    last = candles[-1]
    logger.info(f"Last M15 candle: O={last['open']:.5f} H={last['high']:.5f} L={last['low']:.5f} C={last['close']:.5f}")
    logger.info(f"Total candles: {len(candles)}")

    # Sanity check: M15 candle range should be larger than M5 (typically 1.5-3x)
    last_range_pips = abs(last['high'] - last['low']) * 10000
    logger.info(f"Last candle range: {last_range_pips:.1f} pips (M15 typical: 5-25p)")

    return True


def test_market_state():
    """Verify get_market_state works on M15 data."""
    from src.analyzer.technical_m15 import TechnicalAnalyzerM15

    tech = TechnicalAnalyzerM15(logger)
    state = tech.get_market_state()

    assert state, "No market state returned"
    assert 'price' in state
    assert 'trend' in state
    assert 'rsi' in state
    assert 'avg_range_pips' in state

    logger.info(f"M15 market state:")
    logger.info(f"  price: {state['price']:.5f}")
    logger.info(f"  trend: {state['trend']} ({state.get('trend_strength', 'n/a')})")
    logger.info(f"  rsi: {state['rsi']:.1f} ({state.get('rsi_zone', 'n/a')})")
    logger.info(f"  avg_range_pips: {state['avg_range_pips']:.1f} (vs M5 typical 3-5p)")
    logger.info(f"  volatility: {state.get('volatility', 'n/a')}")
    logger.info(f"  regime: {state.get('regime', 'n/a')}")

    return True


def test_structure_signals():
    """Verify structure detection runs on M15 (signals may be 0 if market quiet)."""
    from src.analyzer.technical_m15 import TechnicalAnalyzerM15, M15_PROFILE

    tech = TechnicalAnalyzerM15(logger)
    signals = tech.detect_structure_signals(min_confidence=M15_PROFILE['min_confidence'])

    logger.info(f"M15 structure signals detected: {len(signals)}")
    for s in signals:
        logger.info(f"  {s.get('direction')} conf={s.get('confidence')} reason={s.get('reason', '')[:80]}")

    return True


if __name__ == '__main__':
    print('=' * 60)
    print('Test M15 feed + analyzer')
    print('=' * 60)

    try:
        print('\n[1/3] Fetching M15 candles...')
        test_fetch_candles()
        print('  OK')

        print('\n[2/3] Computing market state on M15...')
        test_market_state()
        print('  OK')

        print('\n[3/3] Running structure detection on M15...')
        test_structure_signals()
        print('  OK')

        print('\n' + '=' * 60)
        print('ALL TESTS PASSED — M15 feed scaffolding works.')
        print('=' * 60)
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        sys.exit(1)
