"""P26 — Valor en FX: REER del BIS contra su promedio de 5 años (criterio docs/p26_valor_ppp_criterio.md).

Read-only respecto de AIdan: sin MT5, no toca la DB. Datos públicos de FRED vía tools/hyp_data.py
(cache .cache_p22/). Uso:  python tools/backtest_p26_valor.py [--selftest]
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hyp_data as h  # noqa: E402

CCYS = ['EUR', 'JPY', 'GBP', 'CHF', 'CAD', 'AUD', 'NZD']
REER = {'EUR': 'RBXMBIS', 'JPY': 'RBJPBIS', 'GBP': 'RBGBBIS', 'CHF': 'RBCHBIS', 'CAD': 'RBCABIS',
        'AUD': 'RBAUBIS', 'NZD': 'RBNZBIS'}
K = 2
WIN = 60
LAG = 2
DISC_END = '2014-12-31'
RES_START = '2015-01-01'
N_CTRL = 2000
RNG = np.random.default_rng(20261107)


def load():
    px = {}
    for c in CCYS:
        s = h.fred(h.FX[c][0])
        s = s.resample('ME').last()
        px[c] = (1.0 / s) if h.FX[c][1] else s            # USD por unidad de moneda
    px = pd.DataFrame(px)
    reer = pd.DataFrame({c: h.fred(REER[c]) for c in CCYS})
    reer.index = reer.index + pd.offsets.MonthEnd(0)
    rates = pd.DataFrame({c: h.fred(h.RATES[c]) for c in CCYS + ['USD']})
    rates.index = rates.index + pd.offsets.MonthEnd(0)
    idx = px.index
    rates = rates.reindex(rates.index.union(idx)).ffill().reindex(idx)
    return px, reer, rates


def value_signal(reer, idx, lag):
    lr = np.log(reer)
    dev = lr - lr.rolling(WIN, min_periods=WIN).mean().shift(1)   # media de los 60 meses PREVIOS
    dev = dev.shift(lag)                                            # REER de t-lag usado en t
    return dev.reindex(idx)


def leg_returns(px, rates, with_carry=True):
    r = np.log(px.shift(-1) / px)                                   # retorno del mes t+1 asignado a t
    if with_carry:
        r = r + (rates[CCYS].sub(rates['USD'], axis=0) / 100.0 / 12.0)
    return r


def cost_frac(px):
    pip = pd.Series({c: h.PIP[c] for c in CCYS})
    cst = pd.Series(h.COST_PIPS)[CCYS]
    # precio en la cotización del mercado (USDXXX para JPY/CHF/CAD) para pasar pips a fracción
    mkt = pd.DataFrame({c: (1.0 / px[c]) if h.FX[c][1] else px[c] for c in CCYS})
    return (cst * pip) / mkt                                        # ida y vuelta, fracción del precio


def weights_from_scores(scores):
    a = scores.values.astype(float)
    full = ~np.isnan(a).any(axis=1)
    w = np.full(a.shape, np.nan)
    if full.any():
        o = np.argsort(a[full], axis=1)
        ww = np.zeros((full.sum(), a.shape[1]))
        rows = np.arange(len(o))[:, None]
        ww[rows, o[:, :K]] = 1.0 / K
        ww[rows, o[:, -K:]] = -1.0 / K
        w[full] = ww
    return pd.DataFrame(w, index=scores.index, columns=CCYS)


def portfolio(w, r, cfrac):
    gross = (w * r).sum(axis=1, min_count=1)
    turn = w.fillna(0).diff().abs()
    turn.iloc[0] = w.fillna(0).iloc[0].abs()
    cost = (turn * cfrac * 0.5).sum(axis=1)                         # medio costo por unidad rotada (entrar o salir)
    net = gross - cost
    ok = w.notna().all(axis=1) & r.notna().all(axis=1)
    return net[ok], gross[ok]


def block_ci(x, b=12, n=4000):
    x = np.asarray(x)
    m = len(x)
    nb = int(np.ceil(m / b))
    means = []
    for _ in range(n):
        st = RNG.integers(0, m - b + 1, nb)
        s = np.concatenate([x[i:i + b] for i in st])[:m]
        means.append(s.mean())
    return np.percentile(means, [2.5, 97.5])


def stats(x):
    x = pd.Series(x)
    eq = x.cumsum()
    dd = (eq - eq.cummax()).min()
    sh = x.mean() / x.std() * np.sqrt(12) if x.std() > 0 else np.nan
    return f'n={len(x)} media/mes={x.mean()*100:+.3f}% anual={x.mean()*1200:+.2f}% Sharpe={sh:.2f} caidaMax={dd*100:.1f}%'


def control(r, cfrac, idx_ok, valid):
    out = []
    for _ in range(N_CTRL):
        sc = pd.DataFrame(RNG.random((len(valid), len(CCYS))), index=valid.index, columns=CCYS)
        sc[valid.isna()] = np.nan
        w = weights_from_scores(sc)
        net, _ = portfolio(w, r, cfrac)
        out.append(net.reindex(idx_ok).mean())
    return np.percentile(out, 95), np.percentile(out, 50)


def selftest():
    # Control positivo: si la señal fuera el retorno futuro, tiene que pasar holgado.
    px, reer, rates = load()
    r = leg_returns(px, rates)
    cf = cost_frac(px)
    w = weights_from_scores(-r)                                     # compra las que más van a subir
    net, _ = portfolio(w, r, cf)
    assert net.mean() > 0.01, net.mean()
    # Causalidad: mutar el REER futuro no cambia la señal pasada.
    s1 = value_signal(reer, px.index, LAG)
    r2 = reer.copy()
    r2.loc['2010-01-01':] *= 3
    s2 = value_signal(r2, px.index, LAG)
    a = s1.loc[:'2009-12-31'].dropna()
    assert np.allclose(a, s2.loc[a.index, a.columns]), 'look-ahead'
    print('selftest OK: control positivo media/mes', f'{net.mean()*100:.2f}%', '· señal causal')


def main():
    if '--selftest' in sys.argv:
        return selftest()
    px, reer, rates = load()
    r = leg_returns(px, rates, True)
    r_px = leg_returns(px, rates, False)
    cf = cost_frac(px)
    sig = value_signal(reer, px.index, LAG)
    w = weights_from_scores(sig)
    net, gross = portfolio(w, r, cf)
    net = net.loc['1999-01-01':]
    disc = net.loc[:DISC_END]
    res = net.loc[RES_START:]
    print('=' * 76)
    print('P26 VALOR (REER BIS vs media 5 años), 2 baratas contra 2 caras, mensual')
    print('=' * 76)
    print('  completa   ', stats(net), f'({net.index[0]:%Y-%m} -> {net.index[-1]:%Y-%m})')
    print('  descubrim. ', stats(disc))
    print('  reserva    ', stats(res))
    lo, hi = block_ci(disc)
    half = len(net) // 2
    h1, h2 = net.iloc[:half].mean(), net.iloc[half:].mean()
    p95, p50 = control(r, cf, net.index, sig)
    crit = [
        ('1_n', len(disc) >= 150 and len(res) >= 100, f'disc {len(disc)} · res {len(res)}'),
        ('2_disc_CI', disc.mean() > 0 and lo > 0, f'media {disc.mean()*100:+.3f}% CI [{lo*100:+.3f}, {hi*100:+.3f}]'),
        ('3_reserva', res.mean() > 0, f'{res.mean()*100:+.3f}%'),
        ('4_control', net.mean() > p95, f'{net.mean()*100:+.3f}% vs p95 {p95*100:+.3f}% (p50 {p50*100:+.3f}%)'),
        ('5_mitades', h1 > 0 and h2 > 0, f'{h1*100:+.3f}% / {h2*100:+.3f}%'),
    ]
    for k, ok, txt in crit:
        print(f'  [{"OK " if ok else "NO "}] {k}: {txt}')
    npass = sum(ok for _, ok, _ in crit)
    print(f'  >>> {"PASA" if npass == 5 else "NO PASA"} ({npass}/5)')
    print('-' * 76, '\nDESCRIPTIVO (no decide)')
    netp, _ = portfolio(w, r_px, cf)
    print('  solo precio ', stats(netp.loc['1999-01-01':]))
    carry_sig = -(rates[CCYS].sub(rates['USD'], axis=0))           # más tasa = "más barata" para ordenar
    wc = weights_from_scores(carry_sig.where(sig.notna()))
    netc, _ = portfolio(wc, r, cf)
    j = net.index.intersection(netc.index)
    print('  carry 2v2   ', stats(netc.loc[j]), f'· corr con valor {np.corrcoef(net[j], netc[j])[0,1]:+.2f}')
    w4 = weights_from_scores(value_signal(reer, px.index, 4))
    net4, _ = portfolio(w4, r, cf)
    print('  rezago t-4  ', stats(net4.loc['1999-01-01':]))
    print('  bruto       ', stats(gross.loc[net.index]))
    yr = net.groupby(net.index.year).sum() * 100
    print('  por año %   ', ' '.join(f'{y % 100:02d}:{v:+.1f}' for y, v in yr.items()))


if __name__ == '__main__':
    main()
