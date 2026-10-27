"""Tests de P19 (shadow_funding.py): la frontera (no opera, no toca AIdan) y que la señal sea la de P15."""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import backtest_p15_funding as p15  # noqa: E402
from tools import shadow_funding as sf  # noqa: E402

SRC = open(os.path.join(ROOT, 'tools', 'shadow_funding.py'), encoding='utf-8').read()


def test_no_ordenes_ni_claves():
    for bad in ('/order', 'POST', 'method=', 'X-MBX-APIKEY', 'signature', 'api_key', 'apiKey'):
        assert bad not in SRC, bad


def test_no_toca_aidan():
    assert not re.search(r'import\s+MetaTrader5|mt5\.initialize', SRC)
    assert 'financial_news.db' not in SRC


def test_solo_endpoints_publicos_de_binance():
    urls = set(re.findall(r"https://[a-z.]+", SRC))
    assert urls <= {'https://fapi.binance.com', 'https://api.binance.com'}, urls


def test_reglas_de_p15_sin_cambios():
    assert sf.SYMS == p15.MAIN
    assert (p15.ENTER, p15.EXIT, p15.WINDOW_MS) == (0.00005, 0.0, 7 * 24 * 3600 * 1000)
    assert 'p15.simulate(' in SRC and 'def simulate' not in SRC


def test_senal_sin_mirar_el_futuro():
    t = 10 * p15.WINDOW_MS
    f = [(t - p15.WINDOW_MS + k * p15.P8H, 0.0001) for k in range(21)] + [(t, 9.9), (t + p15.P8H, 9.9)]
    assert abs(sf.signal_7d(f, t) - 0.0001) < 1e-12
    assert sf.signal_7d(f[5:], t) is None          # sin 7 días completos no hay señal
