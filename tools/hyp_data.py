"""
hyp_data.py — P22: datos públicos + catálogo CERRADO de features para el loop de hipótesis.

Read-only respecto de AIdan (sin MT5, no toca la DB). Baja series públicas (FRED, CFTC) a `.cache_p22/`.
Criterio: docs/p22_loop_hipotesis_criterio.md. Todas las features por moneda están orientadas a la MONEDA
EXTRANJERA contra el USD (positivo = la lectura ingenua es "sube la moneda"); la hipótesis decide si seguirla o
contrariarla. Las reglas de disponibilidad (sin mirar el futuro) están en `_usable_from` y son las del criterio.
"""
import io
import json
import os
import time

import numpy as np
import pandas as pd
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p22')
MAX_AGE_H = 20

CCYS = ['EUR', 'JPY', 'GBP', 'CHF', 'CAD', 'AUD', 'NZD']
FX = {'EUR': ('DEXUSEU', False), 'JPY': ('DEXJPUS', True), 'GBP': ('DEXUSUK', False), 'CHF': ('DEXSZUS', True),
      'CAD': ('DEXCAUS', True), 'AUD': ('DEXUSAL', False), 'NZD': ('DEXUSNZ', False)}   # True = cotiza USDXXX
COT = {'EUR': '099741', 'JPY': '097741', 'GBP': '096742', 'CHF': '092741', 'CAD': '090741', 'AUD': '232741',
       'NZD': '112741'}
RATES = {'USD': 'IR3TIB01USM156N', 'EUR': 'IR3TIB01EZM156N', 'JPY': 'IR3TIB01JPM156N', 'GBP': 'IR3TIB01GBM156N',
         'CHF': 'IR3TIB01CHM156N', 'CAD': 'IR3TIB01CAM156N', 'AUD': 'IR3TIB01AUM156N', 'NZD': 'IR3TIB01NZM156N'}
GLOBAL = {'DGS2': 'us2y', 'DGS10': 'us10y', 'VIXCLS': 'vix', 'DTWEXBGS': 'usd_broad', 'DCOILWTICO': 'oil'}
PIP = {c: (0.01 if c == 'JPY' else 0.0001) for c in CCYS}
COST_PIPS = {'EUR': 0.8, 'JPY': 0.9, 'GBP': 1.0, 'AUD': 1.0, 'CHF': 1.2, 'CAD': 1.2, 'NZD': 1.3}
START = '1997-01-01'

# Enmienda 2 (28-oct): otros mercados. código: (ticker Yahoo, COT, clase, costo ida y vuelta, moneda de la tasa)
OTHER = {'XAU': ('GC=F', '088691', 'oro', 0.0002, 'USD'),
         'SPX': ('^GSPC', '13874A', 'indices', 0.0002, 'USD'),
         'NDX': ('^NDX', '209742', 'indices', 0.0002, 'USD'),
         'DAX': ('^GDAXI', None, 'indices', 0.0002, 'EUR'),
         'BTC': ('BTC-USD', '133741', 'cripto', 0.0020, None),
         'ETH': ('ETH-USD', '146021', 'cripto', 0.0020, None)}
INSTRUMENTS = CCYS + list(OTHER)
GROUPS = {'ALL': CCYS, 'IDX': ['SPX', 'NDX', 'DAX'], 'CRYPTO': ['BTC', 'ETH']}
CFD_MARKUP = 0.025               # oro/índices: el largo paga tasa + 2,5%, el corto cobra tasa − 2,5%
CRYPTO_FIN = 0.10                # cripto: 10% anual en contra de cualquier lado
SPLITS = {'cripto': ('2015-01-01', '2021-12-31', '2022-01-01')}   # el resto: el corte por defecto del loop


def asset_class(code):
    if code in GROUPS:
        return asset_class(GROUPS[code][0])
    return 'fx' if code in CCYS else OTHER[code][2]

Z = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]
CATALOG = {
    # posicionamiento (CFTC COT, semanal, usable desde el lunes siguiente a la publicación)
    'cot_spec_z52': ('COT: neto de especuladores (no comerciales) en % del interés abierto, z de 52 semanas', Z),
    'cot_spec_chg_z': ('COT: cambio semanal del neto de especuladores, z de 52 semanas', Z),
    'cot_comm_z52': ('COT: neto de comerciales (coberturas) en % del interés abierto, z de 52 semanas', Z),
    # tasas (mensual, usable 2 meses después)
    'rate_diff': ('tasa 3 meses de la moneda menos la de EE.UU., en puntos porcentuales (carry)',
                  [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]),
    'rate_diff_chg3m_z': ('cambio de 3 meses del diferencial de tasas, z de 60 meses', Z),
    # precio de la propia moneda (diario, mediodía NY)
    'mom20_z': ('retorno de 20 días de la moneda contra USD / volatilidad', Z),
    'mom60_z': ('retorno de 60 días de la moneda contra USD / volatilidad', Z),
    'mom250_z': ('retorno de 250 días de la moneda contra USD / volatilidad', Z),
    'dist_ma200_z': ('distancia del precio a su media de 200 días, z de 252 días', Z),
    # otros mercados (iguales para todas las monedas; diarios, usables al día siguiente)
    'us2y_chg20_z': ('cambio de 20 días del bono de EE.UU. a 2 años, z de 252 días', Z),
    'us_curve_z': ('pendiente 10 años menos 2 años de EE.UU., z de 252 días', Z),
    'vix_z': ('nivel del VIX, z de 252 días', Z),
    'vix_chg5_z': ('cambio de 5 días del VIX, z de 252 días', Z),
    'usd_broad_mom20_z': ('retorno de 20 días del dólar amplio (DTWEXBGS, desde 2006) / volatilidad', Z),
    'oil_mom20_z': ('retorno de 20 días del petróleo WTI / volatilidad', Z),
}

SOURCE = {'cot_spec_z52': 'posicionamiento', 'cot_spec_chg_z': 'posicionamiento', 'cot_comm_z52': 'posicionamiento',
          'rate_diff': 'tasas', 'rate_diff_chg3m_z': 'tasas', 'mom20_z': 'precio', 'mom60_z': 'precio',
          'mom250_z': 'precio', 'dist_ma200_z': 'precio', 'us2y_chg20_z': 'bonos_eeuu', 'us_curve_z': 'bonos_eeuu',
          'vix_z': 'volatilidad', 'vix_chg5_z': 'volatilidad', 'usd_broad_mom20_z': 'dolar', 'oil_mom20_z': 'petroleo'}


# ── descarga + cache ─────────────────────────────────────────────────────────

def _get(url):
    # sin User-Agent de navegador: FRED deja colgada la conexión cuando se lo manda (verificado 28-oct)
    for k in range(5):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return r.text
        except Exception:
            if k == 4:
                raise
            time.sleep(2 + 3 * k)


def _cached(name, fetch, refresh):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    fresh = os.path.exists(p) and (time.time() - os.path.getmtime(p)) < MAX_AGE_H * 3600
    if not fresh or refresh:
        try:
            txt = fetch()
            with open(p, 'w', encoding='utf-8') as f:
                f.write(txt)
        except Exception:
            if not os.path.exists(p):
                raise
    with open(p, encoding='utf-8') as f:
        return f.read()


def fred(series, refresh=False):
    txt = _cached(f'fred_{series}.csv',
                  lambda: _get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}'), refresh)
    df = pd.read_csv(io.StringIO(txt), na_values='.')
    s = pd.Series(df.iloc[:, 1].astype(float).values, index=pd.to_datetime(df.iloc[:, 0]), name=series)
    return s.dropna()


def yahoo(ticker, refresh=False):
    """Cierre diario de Yahoo Finance (API pública del gráfico). Fecha = día UTC de la sesión."""
    def fetch():
        r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
                         params={'period1': 0, 'period2': int(time.time()), 'interval': '1d'},
                         headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=60)
        r.raise_for_status()
        return r.text
    safe = ticker.replace('^', 'idx_').replace('=', '_')
    j = json.loads(_cached(f'yahoo_{safe}.json', fetch, refresh))
    res = j['chart']['result'][0]
    close = res['indicators']['quote'][0]['close']
    idx = pd.to_datetime(res['timestamp'], unit='s').normalize()
    s = pd.Series(close, index=idx, dtype=float).dropna()
    s = s[s > 0]
    return s[~s.index.duplicated(keep='last')].sort_index()


def cot(code, refresh=False):
    cols = ('report_date_as_yyyy_mm_dd,open_interest_all,noncomm_positions_long_all,noncomm_positions_short_all,'
            'comm_positions_long_all,comm_positions_short_all')
    url = (f'https://publicreporting.cftc.gov/resource/6dca-aqww.json?$select={cols}'
           f"&$where=cftc_contract_market_code='{code}'&$order=report_date_as_yyyy_mm_dd&$limit=50000")
    txt = _cached(f'cot_{code}.json', lambda: _get(url), refresh)
    df = pd.DataFrame(json.loads(txt))
    df['date'] = pd.to_datetime(df['report_date_as_yyyy_mm_dd'])
    for c in df.columns:
        if c not in ('date', 'report_date_as_yyyy_mm_dd'):
            df[c] = df[c].astype(float)
    df = df.drop_duplicates('date').set_index('date').sort_index()
    oi = df['open_interest_all'].replace(0, np.nan)
    return pd.DataFrame({'spec': (df['noncomm_positions_long_all'] - df['noncomm_positions_short_all']) / oi,
                         'comm': (df['comm_positions_long_all'] - df['comm_positions_short_all']) / oi})


# ── disponibilidad (sin mirar el futuro) ─────────────────────────────────────

def _usable_from(kind, idx):
    """Fecha desde la que un dato con fecha `idx` se puede usar. Reglas fijas del criterio."""
    if kind == 'cot':                      # reporte del martes, publicado el viernes ⇒ desde el lunes
        return idx + pd.Timedelta(days=6)
    if kind == 'monthly':                  # dato del mes m ⇒ desde el 1ro del mes m+2
        return (idx + pd.offsets.MonthBegin(2)).normalize()
    if kind == 'daily_close':              # cierre del día d ⇒ desde d+1
        return idx + pd.Timedelta(days=1)
    return idx                             # precio de mediodía: el mismo día


def _asof(series, kind, calendar, tolerance_days):
    s = series.dropna().copy()
    s.index = _usable_from(kind, s.index)
    s = s[~s.index.duplicated(keep='last')].sort_index()
    left = pd.DataFrame({'date': calendar})
    right = pd.DataFrame({'date': s.index, 'v': s.values})
    out = pd.merge_asof(left, right, on='date', direction='backward',
                        tolerance=pd.Timedelta(days=tolerance_days))
    return pd.Series(out['v'].values, index=calendar)


def _z(s, win, minp):
    m = s.rolling(win, min_periods=minp).mean()
    sd = s.rolling(win, min_periods=minp).std()
    return (s - m) / sd


def _volnorm_mom(px, k):
    lr = np.log(px)
    vol = lr.diff().rolling(252, min_periods=120).std()
    return (lr - lr.shift(k)) / (vol * np.sqrt(k))


# ── panel ────────────────────────────────────────────────────────────────────

def build_panel(refresh=False):
    """dict moneda -> DataFrame diario (calendario = días con dato de EURUSD) con precio, features y swap."""
    eur = fred(FX['EUR'][0], refresh)
    cal = eur[eur.index >= START].index
    glob = {}
    for sid, name in GLOBAL.items():
        s = fred(sid, refresh)
        s = s[s.index >= '1990-01-01']
        if name == 'us2y':
            glob['us2y_chg20_z'] = _z(s - s.shift(20), 252, 120)
        elif name == 'vix':
            glob['vix_z'] = _z(s, 252, 120)
            glob['vix_chg5_z'] = _z(s - s.shift(5), 252, 120)
        elif name in ('usd_broad', 'oil'):
            glob[f'{name}_mom20_z'] = _volnorm_mom(s[s > 0], 20)
        glob[name] = s
    curve = (glob['us10y'] - glob['us2y']).dropna()
    glob['us_curve_z'] = _z(curve, 252, 120)
    gfeat = {k: _asof(glob[k], 'daily_close', cal, 7) for k in
             ('us2y_chg20_z', 'us_curve_z', 'vix_z', 'vix_chg5_z', 'usd_broad_mom20_z', 'oil_mom20_z')}
    usd_rate = fred(RATES['USD'], refresh)
    panel = {}
    for c in CCYS:
        sid, inv = FX[c]
        q = fred(sid, refresh)
        q = q[q > 0]
        quoted = q.reindex(cal, method='ffill', limit=3)
        fxp = 1.0 / quoted if inv else quoted                       # moneda extranjera en USD
        df = pd.DataFrame({'quoted': quoted, 'fx': fxp}, index=cal)
        for k in (20, 60, 250):
            df[f'mom{k}_z'] = _volnorm_mom(fxp, k)
        dist = fxp / fxp.rolling(200, min_periods=150).mean() - 1
        df['dist_ma200_z'] = _z(dist, 252, 120)
        cw = cot(COT[c], refresh)
        cw = cw[cw.index >= '1993-01-01']
        df['cot_spec_z52'] = _asof(_z(cw['spec'], 52, 26), 'cot', cal, 21)
        df['cot_spec_chg_z'] = _asof(_z(cw['spec'].diff(), 52, 26), 'cot', cal, 21)
        df['cot_comm_z52'] = _asof(_z(cw['comm'], 52, 26), 'cot', cal, 21)
        rc = fred(RATES[c], refresh)
        diff = (rc - usd_rate).dropna()
        df['rate_diff'] = _asof(diff, 'monthly', cal, 130)
        df['rate_diff_chg3m_z'] = _asof(_z(diff - diff.shift(3), 60, 24), 'monthly', cal, 130)
        for k, v in gfeat.items():
            df[k] = v.values
        panel[c] = df
    rate_ccy = {'USD': usd_rate, 'EUR': fred(RATES['EUR'], refresh)}
    today = pd.Timestamp.today().normalize()
    for code, (ticker, cot_code, _cls, _cost, rccy) in OTHER.items():
        px = yahoo(ticker, refresh)
        px = px[px.index < today]                       # la vela de hoy puede estar a medio formar
        quoted = px.reindex(cal, method='ffill', limit=4)
        df = pd.DataFrame({'quoted': quoted, 'fx': quoted}, index=cal)
        for k in (20, 60, 250):
            df[f'mom{k}_z'] = _volnorm_mom(quoted, k)
        dist = quoted / quoted.rolling(200, min_periods=150).mean() - 1
        df['dist_ma200_z'] = _z(dist, 252, 120)
        if cot_code:
            cw = cot(cot_code, refresh)
            cw = cw[cw.index >= '1993-01-01']
            df['cot_spec_z52'] = _asof(_z(cw['spec'], 52, 26), 'cot', cal, 21)
            df['cot_spec_chg_z'] = _asof(_z(cw['spec'].diff(), 52, 26), 'cot', cal, 21)
            df['cot_comm_z52'] = _asof(_z(cw['comm'], 52, 26), 'cot', cal, 21)
        else:
            for k in ('cot_spec_z52', 'cot_spec_chg_z', 'cot_comm_z52'):
                df[k] = np.nan
        df['rate_diff'] = np.nan                           # las features de tasas solo existen para monedas
        df['rate_diff_chg3m_z'] = np.nan
        df['fin_rate'] = _asof(rate_ccy[rccy], 'monthly', cal, 130) if rccy else np.nan
        for k, v in gfeat.items():
            df[k] = v.values
        panel[code] = df
    return panel


if __name__ == '__main__':
    import sys
    p = build_panel(refresh='--refresh' in sys.argv)
    for c, df in p.items():
        cov = {k: f"{df[k].notna().mean():.0%}" for k in CATALOG}
        print(c, df.index[0].date(), '->', df.index[-1].date(), len(df), 'días |', cov)
