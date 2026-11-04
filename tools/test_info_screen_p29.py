"""Tests de P29 (info_screen.py): que detecte información cuando la hay, que no la invente, que las features no miren
el futuro y que no toque producción."""
import os
import re
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import info_screen as s  # noqa: E402

SRC = open(os.path.join(ROOT, 'tools', 'info_screen.py'), encoding='utf-8').read()


def _walk(n=60000, seed=1):
    rng = np.random.default_rng(seed)
    return 1.1 * np.exp(np.cumsum(rng.normal(0, 0.0004, n)))


def test_control_positivo_pasa():
    c = _walk()
    h = 4
    r = s.fwd_ret(c, h)
    f = r + np.random.default_rng(2).normal(0, np.nanstd(r) * 2, r.size)   # retorno futuro + mucho ruido
    out = s.evaluate(f, r, 0.00002, int(c.size * 0.7), h, 'ctrl')
    assert out['info_ok'] and out['PASA'], out


def test_dato_al_azar_no_pasa():
    c = _walk(seed=3)
    h = 4
    r = s.fwd_ret(c, h)
    f = np.random.default_rng(4).normal(size=r.size)
    out = s.evaluate(f, r, 0.00002, int(c.size * 0.7), h, 'azar')
    assert not out['PASA'], out


def test_costo_mata_informacion_chica():
    c = _walk(seed=5)
    h = 4
    r = s.fwd_ret(c, h)
    f = r + np.random.default_rng(6).normal(0, np.nanstd(r) * 2, r.size)
    out = s.evaluate(f, r, 0.01, int(c.size * 0.7), h, 'caro')          # costo 100 bps
    assert out['info_ok'] and not out['PASA'], out


def test_features_causales():
    c = _walk(n=500, seed=7)
    hh, ll = c * 1.0005, c * 0.9995
    base = [s.f_momentum(c, 4), s.f_rev2s(c), s.f_vol_range(hh, ll, c), s.f_vol_ret(c)]
    c2 = c.copy()
    c2[301:] *= 1.5                                                        # cambiar el futuro
    hh2, ll2 = c2 * 1.0005, c2 * 0.9995
    new = [s.f_momentum(c2, 4), s.f_rev2s(c2), s.f_vol_range(hh2, ll2, c2), s.f_vol_ret(c2)]
    for a, b in zip(base, new):
        assert np.allclose(a[:301], b[:301], equal_nan=True)


def test_bucket_solo_descubrimiento():
    r = np.r_[np.zeros(700), np.ones(300)]
    keys = np.tile(np.arange(10), 100)
    f = s.f_bucket_mean(keys, r, 700)
    assert np.allclose(f, 0.0)                                             # la reserva (unos) no se filtra


def test_lead_exige_mismo_timestamp():
    t_src = np.arange(0, 100 * 900, 900)
    c_src = np.linspace(1, 2, 100)
    out = s.f_lead(np.array([t_src[10], t_src[10] + 1]), t_src, c_src)
    assert np.isfinite(out[0]) and np.isnan(out[1])


def test_no_toca_produccion():
    assert 'financial_news.db' not in SRC
    assert not re.search(r'import\s+MetaTrader5|mt5\.initialize', SRC)
    assert 'INSERT' not in SRC and 'UPDATE' not in SRC
