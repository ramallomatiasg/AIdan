"""
Centralized price feed for EUR/USD.
Supports multiple data sources with automatic fallback:
  1. FXCM (free, matches TradingView FXCM chart)
  2. Twelve Data (free API key, good for forex)
  3. Yahoo Finance (no key needed, last resort)
"""
import os
import time
from datetime import datetime, timezone
import requests


# Twelve Data free tier: 800 requests/day, 8/min
_TWELVE_DATA_KEY = None
_SOURCE_PRIORITY = ['twelvedata', 'fxcm', 'yahoo']
_last_source_used = None


def _get_twelve_data_key():
    global _TWELVE_DATA_KEY
    if not _TWELVE_DATA_KEY:
        try:
            from src.common.config import Config
            _TWELVE_DATA_KEY = Config.TWELVE_DATA_API_KEY or ''
        except Exception:
            pass
        if not _TWELVE_DATA_KEY:
            _TWELVE_DATA_KEY = os.getenv('TWELVE_DATA_API_KEY', '')
    return _TWELVE_DATA_KEY


def get_last_source():
    """Return the name of the last data source that succeeded."""
    return _last_source_used or 'unknown'


def fetch_candles(interval='5min', count=100, logger=None):
    """
    Fetch EUR/USD candles from the best available source.

    Args:
        interval: '1min', '5min', '15min', '1h' etc.
        count: number of candles to fetch
        logger: optional logger

    Returns:
        list of dicts with keys: open, high, low, close, datetime
        or None on failure
    """
    global _last_source_used

    # 1. Yahoo Finance first — best precision (7+ decimals), real-time price, no API key
    yh_interval, yh_range = _map_interval_to_yahoo(interval, count)
    candles = _fetch_yahoo(yh_interval, yh_range, logger)
    if candles:
        _last_source_used = 'yahoo'
        if len(candles) > count:
            candles = candles[-count:]
        if logger:
            logger.info(f"PriceFeed: last close={candles[-1]['close']:.5f} from yahoo ({interval})")
        return candles

    # 2. Try Twelve Data as backup
    key = _get_twelve_data_key()
    if key:
        candles = _fetch_twelvedata(interval, count, key, logger)
        if candles:
            _last_source_used = 'twelvedata'
            if logger:
                logger.info(f"PriceFeed: last close={candles[-1]['close']:.5f} from twelvedata ({interval})")
            return candles

    # 3. Try FXCM as last resort
    candles = _fetch_fxcm(interval, count, logger)
    if candles:
        _last_source_used = 'fxcm'
        if logger:
            logger.info(f"PriceFeed: last close={candles[-1]['close']:.5f} from fxcm ({interval})")
        return candles

    return None


# ── FXCM ──────────────────────────────────────────────────────────────────────

def _map_interval_to_fxcm(interval):
    """Map generic interval to FXCM period string."""
    mapping = {
        '1min':  'm1',
        '5min':  'm5',
        '15min': 'm15',
        '30min': 'm30',
        '1h':    'H1',
        '4h':    'H4',
        '1day':  'D1',
    }
    return mapping.get(interval)


def _fetch_fxcm(interval, count, logger=None):
    """
    Fetch from FXCM free candles API.
    This is the same data source that TradingView uses for FXCM:EURUSD.
    No API key required.
    """
    period = _map_interval_to_fxcm(interval)
    if not period:
        if logger:
            logger.warning(f"FXCM: unsupported interval '{interval}'")
        return None

    try:
        url = "https://candles.fxcm.com/candles"
        params = {
            'instrument': 'EUR/USD',
            'period': period,
            'num': min(count, 300),
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            if logger:
                logger.warning(f"FXCM HTTP {resp.status_code}")
            return None

        data = resp.json()

        # FXCM returns: { "instrument": "EUR/USD", "period": "m5",
        #   "candles": [[timestamp, bidOpen, bidClose, bidHigh, bidLow,
        #                 askOpen, askClose, askHigh, askLow, tickQty], ...] }
        raw_candles = data.get('candles', [])
        if not raw_candles:
            if logger:
                logger.warning("FXCM: empty candles response")
            return None

        candles = []
        for c in raw_candles:
            # Use bid prices (index 1-4): bidOpen, bidClose, bidHigh, bidLow
            ts = c[0]  # Unix timestamp in seconds
            bid_open = float(c[1])
            bid_close = float(c[2])
            bid_high = float(c[3])
            bid_low = float(c[4])

            # Convert timestamp to readable datetime
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')

            candles.append({
                'open': bid_open,
                'high': bid_high,
                'low': bid_low,
                'close': bid_close,
                'datetime': dt_str,
            })

        if logger:
            logger.info(f"PriceFeed: {len(candles)} candles from FXCM ({interval})")
        return candles

    except Exception as e:
        if logger:
            logger.warning(f"FXCM fetch failed: {e}")
        return None


# ── Twelve Data ───────────────────────────────────────────────────────────────

def _map_interval_to_yahoo(interval, count):
    """Map generic interval to Yahoo Finance interval+range params."""
    mapping = {
        '1min':  ('1m',  '1d'),
        '5min':  ('5m',  '5d'),
        '15min': ('15m', '5d'),
        '30min': ('30m', '5d'),
        '1h':    ('1h',  '5d'),
        '4h':    ('1h',  '30d'),  # Yahoo doesn't have 4h, use 1h with more range
        '1day':  ('1d',  '6mo'),
    }
    return mapping.get(interval, ('5m', '1d'))


def _fetch_twelvedata(interval, count, api_key, logger=None):
    """Fetch from Twelve Data API (free tier: 800 req/day)."""
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            'symbol': 'EUR/USD',
            'interval': interval,
            'outputsize': min(count, 500),
            'apikey': api_key,
            'dp': 5,  # 5 decimal places
            'timezone': 'UTC',  # Force UTC to avoid timezone misalignment
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            if logger:
                logger.warning(f"Twelve Data HTTP {resp.status_code}")
            return None

        data = resp.json()
        if data.get('status') == 'error':
            if logger:
                logger.warning(f"Twelve Data error: {data.get('message', 'unknown')}")
            return None

        values = data.get('values', [])
        if not values:
            return None

        candles = []
        for v in reversed(values):  # Twelve Data returns newest first
            candles.append({
                'open': float(v['open']),
                'high': float(v['high']),
                'low': float(v['low']),
                'close': float(v['close']),
                'datetime': v['datetime'],
            })

        if logger:
            logger.info(f"PriceFeed: {len(candles)} candles from Twelve Data ({interval})")
        return candles
    except Exception as e:
        if logger:
            logger.warning(f"Twelve Data fetch failed: {e}")
        return None


# ── Yahoo Finance ─────────────────────────────────────────────────────────────

def _fetch_yahoo(interval, range_str, logger=None):
    """Yahoo Finance: free, no API key, high precision (7+ decimals), real-time."""
    # Try both query endpoints (query1 sometimes rate-limits, query2 is backup)
    for host in ['query2.finance.yahoo.com', 'query1.finance.yahoo.com']:
        try:
            url = f"https://{host}/v8/finance/chart/EURUSD=X"
            params = {'interval': interval, 'range': range_str}
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result = data['chart']['result'][0]
            timestamps = result.get('timestamp', [])
            if not timestamps:
                continue
            quote = result['indicators']['quote'][0]

            candles = []
            for i in range(len(timestamps)):
                if quote['close'][i] is not None and quote['open'][i] is not None:
                    candles.append({
                        'open': round(float(quote['open'][i]), 5),
                        'high': round(float(quote['high'][i]), 5),
                        'low': round(float(quote['low'][i]), 5),
                        'close': round(float(quote['close'][i]), 5),
                        'datetime': str(timestamps[i]),
                    })
            if candles:
                if logger:
                    logger.info(f"PriceFeed: {len(candles)} candles from Yahoo Finance ({interval})")
                return candles
        except Exception as e:
            if logger:
                logger.warning(f"Yahoo Finance ({host}) fetch failed: {e}")
            continue
    return None
