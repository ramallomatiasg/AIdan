"""
Centralized price feed for EUR/USD.
Supports multiple data sources with automatic fallback:
  1. Twelve Data (free API key, more accurate for forex)
  2. Yahoo Finance (no key needed, fallback)
"""
import os
import time
import requests


# Twelve Data free tier: 800 requests/day, 8/min
_TWELVE_DATA_KEY = None
_SOURCE_PRIORITY = ['twelvedata', 'yahoo']
_last_source_used = None


def _get_twelve_data_key():
    global _TWELVE_DATA_KEY
    if _TWELVE_DATA_KEY is None:
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

    key = _get_twelve_data_key()

    # Try Twelve Data first if key available
    if key:
        candles = _fetch_twelvedata(interval, count, key, logger)
        if candles:
            _last_source_used = 'twelvedata'
            if logger and candles:
                logger.info(f"PriceFeed: last close={candles[-1]['close']:.5f} from twelvedata ({interval})")
            return candles

    # Fallback to Yahoo Finance
    yh_interval, yh_range = _map_interval_to_yahoo(interval, count)
    candles = _fetch_yahoo(yh_interval, yh_range, logger)
    if candles:
        _last_source_used = 'yahoo'
        # Trim to requested count
        if len(candles) > count:
            candles = candles[-count:]
        if logger and candles:
            logger.info(f"PriceFeed: last close={candles[-1]['close']:.5f} from yahoo ({interval})")
        return candles

    return None


def _map_interval_to_yahoo(interval, count):
    """Map generic interval to Yahoo Finance interval+range params."""
    mapping = {
        '1min':  ('1m',  '1d'),
        '5min':  ('5m',  '1d'),
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


def _fetch_yahoo(interval, range_str, logger=None):
    """Yahoo Finance: free, no API key, reliable but less accurate for forex."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X"
        params = {'interval': interval, 'range': range_str}
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]

        candles = []
        for i in range(len(timestamps)):
            if quote['close'][i] is not None and quote['open'][i] is not None:
                candles.append({
                    'open': float(quote['open'][i]),
                    'high': float(quote['high'][i]),
                    'low': float(quote['low'][i]),
                    'close': float(quote['close'][i]),
                    'datetime': str(timestamps[i]),
                })
        if logger:
            logger.info(f"PriceFeed: {len(candles)} candles from Yahoo Finance ({interval})")
        return candles
    except Exception as e:
        if logger:
            logger.warning(f"Yahoo Finance fetch failed: {e}")
        return None
