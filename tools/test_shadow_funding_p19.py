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


def test_hyperliquid_solo_lectura():
    """Enmienda 1: Hyperliquid se lee solo por /info con tipos de lectura; /exchange (órdenes) no existe."""
    p21_src = open(os.path.join(ROOT, 'tools', 'backtest_p21_hyperliquid.py'), encoding='utf-8').read()
    for src in (SRC, p21_src):
        assert '/exchange' not in src and 'privateKey' not in src and 'eth_account' not in src
    assert re.findall(r"https://[a-z.]+/[a-z]+", p21_src) == ['https://api.hyperliquid.xyz/info']
    assert set(sf.HL_TYPES) == {'fundingHistory', 'candleSnapshot', 'l2Book', 'metaAndAssetCtxs'}
    try:
        sf.hl_info({'type': 'order'})
        assert False, 'hl_info aceptó un tipo fuera de la lista'
    except AssertionError as e:
        assert 'order' in str(e)


def test_costo_de_hyperliquid_no_contamina_binance():
    """book() con el costo de P21 restaura el de P15 aunque falle, y el libro de Binance usa el de P15."""
    before = p15.RT_COST
    t0 = sf.HL_START_MS
    d = {s: dict(spot=[], perp=[], funding=[]) for s in sf.SYMS}
    sf.book(d, t0 + 3 * p15.P8H, t0, sf.HL_COST)
    assert p15.RT_COST == before
    bad = {s: None for s in sf.SYMS}
    try:
        sf.book(bad, t0 + 3 * p15.P8H, t0, sf.HL_COST)
    except Exception:
        pass
    assert p15.RT_COST == before


def test_senal_sin_mirar_el_futuro():
    t = 10 * p15.WINDOW_MS
    f = [(t - p15.WINDOW_MS + k * p15.P8H, 0.0001) for k in range(21)] + [(t, 9.9), (t + p15.P8H, 9.9)]
    assert abs(sf.signal_7d(f, t) - 0.0001) < 1e-12
    assert sf.signal_7d(f[5:], t) is None          # sin 7 días completos no hay señal
