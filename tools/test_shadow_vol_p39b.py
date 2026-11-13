"""Tests de P39b (shadow_vol_deribit.py): la frontera (no opera, no toca AIdan) y los cálculos puros."""
import math
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import shadow_vol_deribit as sv  # noqa: E402

SRC = open(os.path.join(ROOT, 'tools', 'shadow_vol_deribit.py'), encoding='utf-8').read()
DAY = sv.DAY_MS


def test_no_ordenes_ni_claves():
    for bad in ('private/', '/order', 'POST', 'method=', 'client_secret', 'client_id', 'X-MBX-APIKEY',
                'signature', 'api_key', 'apiKey', "'buy'", "'sell'", 'public/buy', 'public/sell'):
        assert bad not in SRC, bad


def test_solo_endpoints_publicos():
    urls = set(re.findall(r"https://[a-z./0-9]+", SRC))
    assert urls <= set(sv.HOSTS), urls
    assert all(m.startswith('get_') or m == 'ticker' for m in sv.DERIBIT_METHODS)


def test_no_toca_aidan():
    assert not re.search(r'import\s+MetaTrader5|mt5\.initialize', SRC)
    assert 'financial_news.db' not in SRC
    assert sv.default_db().endswith('vol_shadow.db')


def test_regla_de_p39_congelada():
    from tools import backtest_p39_vrp_cripto as p39
    assert (sv.H, sv.PROXY_COST) == (p39.H, p39.COST)


def test_realizada_igual_a_p39():
    t0 = 0
    opens = [(t0 + k * 8 * 3600000, 100 * math.exp(0.01 * (k % 2))) for k in range(0, 3 * 30 + 2)]
    rv = sv.realized_vol(opens, t0, t0 + 30 * DAY, 30)
    n = sum(1 for (a, _), (b, _) in zip(opens, opens[1:]) if t0 < b <= t0 + 30 * DAY)
    assert abs(rv - math.sqrt(n * 0.01 ** 2 * 365 / 30) * 100) < 1e-9


def test_b76_atm():
    dc, dp, vega = sv.b76(70000, 70000, 30 / 365, 50)
    assert 0.5 < dc < 0.55 and abs(dc - dp - 1) < 1e-12
    assert abs(vega - 70000 * 0.3989 * math.sqrt(30 / 365) / 100) < 1


def test_pick_expiry():
    now = 0
    assert sv.pick_expiry([now + 21 * DAY, now + 42 * DAY], now) == now + 21 * DAY
    assert sv.pick_expiry([now + 25 * DAY, now + 35 * DAY], now) == now + 35 * DAY  # empate ⇒ el más largo
    assert sv.pick_expiry([now + 7 * DAY, now + 60 * DAY], now) is None


def test_payoff_y_comisiones():
    assert sv.straddle_payoff(65000, 70000) == 5000 == sv.straddle_payoff(75000, 70000)
    assert abs(sv.deribit_fee(70000, 1000, sv.FEE_IN) - 21.0) < 1e-9
    assert sv.deribit_fee(70000, 100, sv.FEE_IN) == 12.5           # tope 12,5% del precio de la opción


def test_proxy_igual_a_p39():
    assert abs(sv.proxy_vol(60, 50) - ((0.36 - 0.25) / 1.2 * 100 - 2)) < 1e-9
