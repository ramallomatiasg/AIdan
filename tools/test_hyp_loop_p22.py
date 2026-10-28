"""Tests de P22 (hyp_data + hyp_loop): frontera, sin mirar el futuro, lista cerrada, anti-repetición y costos."""
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import hyp_data as hd  # noqa: E402
from tools import hyp_loop as hl  # noqa: E402


def _spec(**kw):
    s = dict(pairs='EUR', horizon=5, position='long_fx', symmetric=False,
             conditions=[dict(feature='cot_spec_z52', op='>', threshold=1.0)],
             rationale='los especuladores apalancados pagan cuando se desarman')
    s.update(kw)
    return s


# ── frontera ─────────────────────────────────────────────────────────────────

def test_no_toca_aidan_ni_opera():
    for name in ('hyp_loop.py', 'hyp_data.py'):
        src = open(os.path.join(ROOT, 'tools', name), encoding='utf-8').read()
        assert not re.search(r'import\s+MetaTrader5|mt5\.initialize|order_send', src)
        assert 'financial_news.db' not in src


# ── sin mirar el futuro ──────────────────────────────────────────────────────

def test_disponibilidad():
    t = pd.DatetimeIndex(['2024-01-02'])                                 # martes
    assert hd._usable_from('cot', t)[0] == pd.Timestamp('2024-01-08')    # lunes siguiente
    assert hd._usable_from('monthly', pd.DatetimeIndex(['2024-01-01']))[0] == pd.Timestamp('2024-03-01')
    assert hd._usable_from('daily_close', t)[0] == pd.Timestamp('2024-01-03')


def test_asof_no_usa_el_dato_antes_de_tiempo():
    cal = pd.date_range('2024-01-01', '2024-01-20', freq='D')
    s = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(['2024-01-02', '2024-01-09']))
    out = hd._asof(s, 'cot', cal, 21)
    assert np.isnan(out[pd.Timestamp('2024-01-07')])
    assert out[pd.Timestamp('2024-01-08')] == 1.0
    assert out[pd.Timestamp('2024-01-14')] == 1.0
    assert out[pd.Timestamp('2024-01-15')] == 2.0


# ── lista cerrada y anti-repetición ──────────────────────────────────────────

def test_lista_cerrada():
    ok = lambda s: hl.validate(s, set(), set(), set())[0]  # noqa: E731
    assert ok(_spec())
    assert not ok(_spec(conditions=[dict(feature='inventada', op='>', threshold=1.0)]))
    assert not ok(_spec(conditions=[dict(feature='cot_spec_z52', op='>', threshold=1.3)]))
    assert not ok(_spec(horizon=7))
    assert not ok(_spec(pairs='MXN'))
    assert not ok(_spec(rationale='porque sí'))
    assert not ok(_spec(symmetric=True, conditions=[dict(feature='vix_z', op='<', threshold=1.0)]))


def test_umbral_cambiado_no_es_idea_nueva():
    a = _spec()
    b = _spec(conditions=[dict(feature='cot_spec_z52', op='>', threshold=2.0)], horizon=20, pairs='JPY')
    espejo = _spec(position='short_fx', conditions=[dict(feature='cot_spec_z52', op='<', threshold=-1.0)])
    assert hl.family_of(a) == hl.family_of(b) == hl.family_of(espejo)
    assert hl.variant_of(a) != hl.variant_of(b)


def test_familia_cerrada_duplicado_y_misma_vuelta():
    a = _spec()
    assert hl.validate(a, {hl.family_of(a)}, set(), set())[1].startswith('familia cerrada')
    assert hl.validate(a, set(), {hl.variant_of(a)}, set())[1].startswith('duplicado')
    assert hl.validate(a, set(), set(), {hl.family_of(a)})[1].startswith('misma familia')


def test_familia_se_cierra_tras_3_fallos(tmp_path):
    conn = hl.connect(str(tmp_path / 'h.db'))
    for th in (0.5, 1.0, 1.5):
        s = _spec(conditions=[dict(feature='cot_spec_z52', op='>', threshold=th)])
        conn.execute("INSERT INTO hypotheses (family, variant, spec_json, status, disc_json) VALUES (?,?,?,?,?)",
                     (hl.family_of(s), hl.variant_of(s), __import__('json').dumps(s), 'falló_A', '{"mean_bps": -1}'))
    assert hl.family_of(_spec()) in hl.memory(conn)['closed']


# ── posiciones y costos ──────────────────────────────────────────────────────

def test_simetrica():
    df = pd.DataFrame({'vix_z': [2.0, 0.0, -2.0, np.nan]})
    s = _spec(symmetric=True, position='short_fx', conditions=[dict(feature='vix_z', op='>', threshold=1.0)])
    assert list(hl.raw_positions(df, s)) == [-1, 0, 1, 0]


def test_costo_ida_y_vuelta_se_cobra_una_vez():
    leg = dict(ret=np.zeros(4), cost=np.full(4, 0.001), carry=np.zeros(4), mark=np.zeros(4))
    net = hl.net_series(leg, np.array([1.0, 1.0, 0.0, 0.0]))
    assert abs(net.sum() + 0.001) < 1e-12          # entrar + salir = una ida y vuelta
    flip = hl.net_series(leg, np.array([1.0, -1.0, 0.0, 0.0]))
    assert abs(flip.sum() + 0.002) < 1e-12         # entrar, dar vuelta (1 completa), salir


def test_gate_a_exige_ganarle_al_azar():
    s = dict(n=100, mean_bps=5.0, ci_lo_bps=1.0, half1_bps=4.0, half2_bps=6.0, control_p95_bps=6.0)
    assert not hl.gate_a(s)[0]
    s['control_p95_bps'] = 4.0
    assert hl.gate_a(s)[0]


def test_familia_negativa_se_cierra_a_las_2(tmp_path):
    import json
    conn = hl.connect(str(tmp_path / 'h.db'))
    for th, m in ((0.5, -3.0), (1.0, -1.0)):
        s = _spec(conditions=[dict(feature='vix_z', op='>', threshold=th)])
        conn.execute("INSERT INTO hypotheses (family, variant, spec_json, status, disc_json) VALUES (?,?,?,?,?)",
                     (hl.family_of(s), hl.variant_of(s), json.dumps(s), 'falló_A', json.dumps({'mean_bps': m})))
    assert hl.family_of(_spec(conditions=[dict(feature='vix_z', op='>', threshold=1.5)])) in hl.memory(conn)['closed']


def test_en_etapa_de_combinacion_no_se_repite_una_sola_fuente():
    a = _spec()
    ok, why = hl.validate(a, set(), set(), set(), {hl.family_of(a)}, combo_phase=True)
    assert not ok and 'una sola fuente' in why
    combo = _spec(conditions=[dict(feature='cot_spec_z52', op='>', threshold=1.0),
                              dict(feature='rate_diff', op='>', threshold=0.0)])
    assert hl.validate(combo, set(), set(), set(), {hl.family_of(a)}, combo_phase=True)[0]


def test_reintento_con_los_rechazos(tmp_path):
    """Si la IA propone poco válido, se le devuelven los rechazos una vez (y el manual no reintenta)."""
    calls = []

    def fake(mem, n, fb):
        calls.append(fb)
        return ([dict(pairs='MXN')] if fb is None else []), 'fake'
    panel = hd.build_panel()
    hl.cycle(hl.connect(str(tmp_path / 'h.db')), panel, fake, 4)
    assert len(calls) == 2 and calls[0] is None and 'instrumento inválido' in calls[1]


# ── enmienda 2: oro, índices y cripto ────────────────────────────────────────

def test_misma_idea_en_otro_mercado_es_otra_familia():
    fx = _spec()
    spx = _spec(pairs='SPX')
    idx = _spec(pairs='IDX', conditions=[dict(feature='cot_spec_z52', op='>', threshold=2.0)])
    assert hl.family_of(fx) != hl.family_of(spx)
    assert hl.family_of(spx) == hl.family_of(idx) and hl.family_of(spx).startswith('indices|')
    assert hl.validate(_spec(pairs='BTC'), set(), set(), set())[0]
    assert not hl.validate(_spec(pairs='SOL'), set(), set(), set())[0]


def test_cortes_por_mercado():
    assert hl.seg_bounds('EUR', 'disc', 'disc') == hl.DISC
    assert hl.seg_bounds('SPX', 'hold', '2026-10-01') == (hl.HOLD_START, '2026-10-01')
    assert hl.seg_bounds('BTC', 'disc', 'disc') == ('2015-01-01', '2021-12-31')
    assert hl.seg_bounds('ETH', 'hold', '2026-10-01') == ('2022-01-01', '2026-10-01')


def test_costos_y_financiacion_por_mercado():
    cal = pd.bdate_range('2020-01-01', periods=40)
    df = pd.DataFrame({'fx': 100.0, 'quoted': 100.0, 'rate_diff': np.nan, 'fin_rate': 4.0}, index=cal)
    spx = hl.legs({'SPX': df}, 'SPX', 5, '2020-01-01', '2020-03-01')
    assert np.allclose(spx['cost'], 0.0002)
    assert np.all(spx['carry'] < 0) and np.all(spx['mark'] > 0)          # el largo paga tasa + 2,5%
    btc = hl.legs({'BTC': df}, 'BTC', 5, '2020-01-01', '2020-03-01')
    assert np.allclose(btc['cost'], 0.002) and np.allclose(btc['carry'], 0)
    assert np.allclose(btc['mark'], 0.10 * 7 / 365)                       # 5 días hábiles = 7 corridos


def test_rechaza_datos_que_no_existen_en_ese_mercado():
    v = lambda s: hl.validate(s, set(), set(), set())  # noqa: E731
    assert not v(_spec(pairs='DAX', conditions=[dict(feature='rate_diff', op='>', threshold=0.0)]))[0]
    assert not v(_spec(pairs='DAX'))[0]                                  # COT en DAX
    assert not v(_spec(pairs='ETH'))[0]                                  # COT de ETH desde 2021
    assert v(_spec(pairs='IDX'))[0]                                      # en el grupo, SPX y NDX sí tienen
    assert v(_spec(pairs='SPX'))[0]
