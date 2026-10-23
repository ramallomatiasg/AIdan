"""
backtest_p16_vol.py — P16: vender volatilidad (SVXY) solo con la curva del VIX en contango (VIX < VIX3M).

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja datos diarios PÚBLICOS de Yahoo Finance a `.cache_p16/`.
Criterio declarado ANTES de medir: docs/p16_vender_volatilidad_criterio.md (7a3b84e). Leer contra eso.

Señal al cierre del día t (VIX/VIX3M < 1 ⇒ adentro), ejecución a la apertura de t+1, 0,05% por lado, efectivo a 0%.
Antes de medir verifica que el motor, con la señal "siempre adentro", reproduzca SVXY comprar y mantener.

Uso:
    python tools/backtest_p16_vol.py
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

CACHE = os.path.join(ROOT, '.cache_p16')
P1, P2 = 946684800, int(dt.datetime(2026, 10, 24, tzinfo=dt.timezone.utc).timestamp())
COST = 0.0005
BLOCK = 21
BOOT = 5000
SEED = 20261023
OUT = os.path.join(ROOT, 'docs', 'p16_vol_resultado.json')
EVENTS = {'feb-2018': ('2018-02-01', '2018-02-09'), 'mar-2020': ('2020-02-20', '2020-03-20'),
          'ago-2024': ('2024-07-31', '2024-08-09')}


def fetch(sym):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, sym.replace('^', '') + '.json')
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    u = (f'https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}'
         f'?period1={P1}&period2={P2}&interval=1d')
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                j = json.load(r)['chart']['result'][0]
            break
        except Exception:
            if k == 3:
                raise
            time.sleep(3)
    off = j['meta'].get('gmtoffset', 0)
    q = j['indicators']['quote'][0]
    adj = j['indicators'].get('adjclose', [{}])[0].get('adjclose') or q['close']
    rows = {}
    for i, t in enumerate(j['timestamp']):
        o, c, a = q['open'][i], q['close'][i], adj[i]
        if None in (o, c, a) or c <= 0:
            continue
        d = dt.datetime.utcfromtimestamp(t + off).strftime('%Y-%m-%d')
        f = a / c
        rows[d] = (o * f, a)                        # open y close ajustados por splits/dividendos
    with open(p, 'w') as fh:
        json.dump(rows, fh)
    return rows


def engine(dates, px, signal):
    """Retorno diario: overnight si estaba adentro, cambio a la apertura con costo, intradía si queda adentro."""
    r = np.zeros(len(dates))
    held = False
    for i in range(1, len(dates)):
        o, c = px[dates[i]]
        pc = px[dates[i - 1]][1]
        target = signal[i - 1]
        m = 1.0
        if held:
            m *= o / pc
        if target != held:
            m *= 1 - COST
        if target:
            m *= c / o
        r[i] = m - 1
        held = target
    return r


def cagr(r, days):
    return float(np.prod(1 + r) ** (365.25 / days) - 1) if days > 0 else float('nan')


def maxdd(r):
    eq = np.cumprod(1 + r)
    return float(np.max(1 - eq / np.maximum.accumulate(eq)))


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else float('nan')


def span(dates, a, b):
    return (dt.date.fromisoformat(dates[b]) - dt.date.fromisoformat(dates[a])).days


def boot(r):
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(r.size / BLOCK))
    st = rng.integers(0, r.size - BLOCK, (BOOT, nb))
    idx = (st[:, :, None] + np.arange(BLOCK)).reshape(BOOT, -1)[:, :r.size]
    m = np.sort(r[idx].mean(axis=1) * 252)
    return float(m[int(0.025 * BOOT)]), float(m[int(0.975 * BOOT)])


def run_rule(sym, vix, vix3m):
    px = fetch(sym)
    dates = sorted(d for d in px if d in vix and d in vix3m)
    sig = [vix[d][1] / vix3m[d][1] < 1.0 for d in dates]
    return dates, px, sig


def main():
    vix, vix3m, spy, irx = fetch('^VIX'), fetch('^VIX3M'), fetch('SPY'), fetch('^IRX')
    dates, px, sig = run_rule('SVXY', vix, vix3m)
    # control del motor: siempre adentro == comprar y mantener (salvo el costo de la 1ra entrada)
    r_all = engine(dates, px, [True] * len(dates))
    bh = np.array([0.0] + [px[dates[i]][1] / px[dates[i - 1]][1] - 1 for i in range(1, len(dates))])
    exp = np.prod(1 + bh[2:]) * (px[dates[1]][1] / px[dates[1]][0]) * (1 - COST)
    if abs(np.prod(1 + r_all[1:]) / exp - 1) > 1e-9:
        sys.exit('ABORTA: el motor no reproduce comprar y mantener con la señal siempre adentro')
    r = engine(dates, px, sig)
    n = len(dates)
    days = span(dates, 0, n - 1)
    half = n // 2
    c_all = cagr(r[1:], days)
    c1, c2 = cagr(r[1:half], span(dates, 0, half - 1)), cagr(r[half:], span(dates, half - 1, n - 1))
    lo, hi = boot(r[1:])
    spy_r = np.array([0.0] + [spy[dates[i]][1] / spy[dates[i - 1]][1] - 1 if dates[i] in spy and dates[i - 1] in spy
                              else 0.0 for i in range(1, n)])
    months = {}
    for i in range(1, n):
        months.setdefault(dates[i][:7], []).append(r[i])
    worst_m = min((float(np.prod(1 + np.array(v)) - 1), k) for k, v in months.items())
    years = {}
    for i in range(1, n):
        years.setdefault(dates[i][:4], ([], [], []))
        years[dates[i][:4]][0].append(r[i])
        years[dates[i][:4]][1].append(bh[i])
        years[dates[i][:4]][2].append(spy_r[i])
    inn = float(np.mean(sig))
    switches = int(sum(1 for i in range(1, n) if sig[i] != sig[i - 1]))
    rf = np.array([(irx[dates[i]][1] / 100 / 252) if (dates[i] in irx and not sig[i - 1]) else 0.0
                   for i in range(n)])
    print(f'SVXY {dates[0]} -> {dates[-1]}  ({n} días)  adentro {inn:.0%} del tiempo  cambios {switches}')
    print(f'  REGLA (VIX<VIX3M): CAGR {c_all:+.2%}  CI media anual [{lo:+.2%}, {hi:+.2%}]  mitades {c1:+.2%} / '
          f'{c2:+.2%}  caída máx {maxdd(r[1:]):.1%}  Sharpe {sharpe(r[1:]):.2f}  peor mes {worst_m[0]:+.1%} '
          f'({worst_m[1]})')
    print(f'  SVXY siempre adentro: CAGR {cagr(bh[1:], days):+.2%}  caída máx {maxdd(bh[1:]):.1%}  '
          f'Sharpe {sharpe(bh[1:]):.2f}')
    print(f'  SPY comprar y mantener: CAGR {cagr(spy_r[1:], days):+.2%}  caída máx {maxdd(spy_r[1:]):.1%}  '
          f'Sharpe {sharpe(spy_r[1:]):.2f}')
    print(f'  regla con el efectivo a la tasa libre (desc.): CAGR {cagr(r[1:] + rf[1:], days):+.2%}')
    for name, (a, b) in EVENTS.items():
        ix = [i for i in range(1, n) if a <= dates[i] <= b]
        print(f'  {name}: regla {np.prod(1 + r[ix]) - 1:+.1%}  SVXY {np.prod(1 + bh[ix]) - 1:+.1%}  '
              f'SPY {np.prod(1 + spy_r[ix]) - 1:+.1%}')
    print('  por año (regla / SVXY / SPY): ' + '  '.join(
        f'{y} {np.prod(1 + np.array(a)) - 1:+.0%}/{np.prod(1 + np.array(b)) - 1:+.0%}/{np.prod(1 + np.array(s)) - 1:+.0%}'
        for y, (a, b, s) in sorted(years.items())))
    d2, p2, s2 = run_rule('SVIX', vix, vix3m)
    r2 = engine(d2, p2, s2)
    print(f'  SVIX con la misma regla (desc., {d2[0]} ->): CAGR {cagr(r2[1:], span(d2, 0, len(d2) - 1)):+.2%}  '
          f'caída máx {maxdd(r2[1:]):.1%}')
    crit = {'1_CAGR>=10%': c_all >= 0.10,
            '2_CI_inf>0': lo > 0,
            '3_dos_mitades>0': c1 > 0 and c2 > 0,
            '4_caida<=SPY_y_Sharpe>SPY': maxdd(r[1:]) <= maxdd(spy_r[1:]) and sharpe(r[1:]) > sharpe(spy_r[1:]),
            '5_peor_mes>-30%': worst_m[0] > -0.30}
    ok = all(crit.values())
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f"  >>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p16_vender_volatilidad_criterio.md (7a3b84e)', cagr=c_all, ci=[lo, hi],
                       halves=[c1, c2], max_dd=maxdd(r[1:]), sharpe=sharpe(r[1:]), worst_month=worst_m,
                       spy=dict(cagr=cagr(spy_r[1:], days), max_dd=maxdd(spy_r[1:]), sharpe=sharpe(spy_r[1:])),
                       svxy_bh=dict(cagr=cagr(bh[1:], days), max_dd=maxdd(bh[1:])), time_in=inn,
                       criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
