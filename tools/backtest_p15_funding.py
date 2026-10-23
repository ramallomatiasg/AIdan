"""
backtest_p15_funding.py — P15: carry de funding en cripto (spot comprado + perpetuo vendido), Binance USDT-M.

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja datos PÚBLICOS de Binance (sin cuenta) a `.cache_p15/`.
Criterio declarado ANTES de medir: docs/p15_funding_criterio.md (748e62f). Leer contra eso.

Uso:
    python tools/backtest_p15_funding.py              # 6 principales (decide)
    python tools/backtest_p15_funding.py --reserved   # 4 reservados: solo si el principal PASÓ
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p15')
MAIN = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
RESERVED = ['ADA', 'LINK', 'LTC', 'AVAX']
START_MS = 1546300800000                                   # 2019-01-01
END_MS = int(dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc).timestamp() * 1000)
P8H = 8 * 3600 * 1000
ENTER = 0.00005                                            # 0,005% por 8 h
EXIT = 0.0
WINDOW_MS = 7 * 24 * 3600 * 1000
RT_COST = 2 * (0.0010 + 0.0005) + 4 * 0.0002               # 0,38% del nocional
CAPITAL = 2.0                                              # capital por unidad de nocional
REBAL = 1.5
PER_YEAR = 1095
BLOCK = 21
BOOT = 5000
SEED = 20261023
OUT = os.path.join(ROOT, 'docs', 'p15_funding_resultado.json')


# ── datos ────────────────────────────────────────────────────────────────────

def _get(url):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                                        timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if k == 4:
                raise
            time.sleep(2 + 3 * k)


def fetch_funding(sym):
    out, start = [], START_MS
    while start < END_MS:
        r = _get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}USDT&startTime={start}&limit=1000')
        if not r:
            break
        out += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r if int(x['fundingTime']) < END_MS]
        nxt = int(r[-1]['fundingTime']) + 1
        if nxt <= start or len(r) < 1000:
            break
        start = nxt
    return out


def fetch_klines(sym, perp):
    base = 'https://fapi.binance.com/fapi/v1/klines' if perp else 'https://api.binance.com/api/v3/klines'
    lim = 1500 if perp else 1000
    out, start = [], START_MS
    while start < END_MS:
        r = _get(f'{base}?symbol={sym}USDT&interval=8h&startTime={start}&limit={lim}')
        if not r:
            break
        out += [(int(x[0]), float(x[1])) for x in r if int(x[0]) < END_MS]
        nxt = int(r[-1][0]) + P8H
        if nxt <= start or len(r) < lim:
            break
        start = nxt
    return out


def load(sym):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'{sym}.json')
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    d = dict(funding=fetch_funding(sym), spot=fetch_klines(sym, False), perp=fetch_klines(sym, True))
    with open(p, 'w') as f:
        json.dump(d, f)
    return d


def hurdle(t0_ms, t1_ms):
    with open(os.path.join(ROOT, 'docs', 'p11_policy_rates.csv')) as f:
        rows = {r['month']: float(r['USD']) for r in csv.DictReader(f)}
    a = dt.datetime.utcfromtimestamp(t0_ms / 1000).strftime('%Y-%m')
    b = dt.datetime.utcfromtimestamp(t1_ms / 1000).strftime('%Y-%m')
    v = [x for m, x in rows.items() if a <= m <= b]
    return float(np.mean(v)) / 100.0


# ── simulación ───────────────────────────────────────────────────────────────

def simulate(d, grid, always_in=False):
    """Devuelve el retorno sobre el capital de la ranura en cada período del grid (len(grid)-1) + desglose."""
    st = dict(d['spot'])
    pp = dict(d['perp'])
    ft = np.array([x[0] for x in d['funding']], dtype=np.int64)
    fr = np.array([x[1] for x in d['funding']], dtype=np.float64)
    pt = np.array(sorted(pp), dtype=np.int64)
    pv = np.array([pp[t] for t in pt])
    cs = np.concatenate([[0.0], np.cumsum(fr)])

    def perp_at(t):
        i = np.searchsorted(pt, t, side='right') - 1
        return pv[max(i, 0)]

    n = len(grid)
    value = np.zeros(n)           # valor acumulado (por unidad de nocional) de lo realizado + abierto
    realized = 0.0
    comp = dict(funding=0.0, base=0.0, cost=0.0, trades=0, rebal=0)
    pos = None                    # dict(s0, f0, ref, t, fund)
    for k, t in enumerate(grid):
        have = t in st and t in pp
        if pos is not None:
            # funding entre la última marca y t (excluye el de la entrada)
            i0 = np.searchsorted(ft, pos['t'], side='right')
            i1 = np.searchsorted(ft, t, side='left')
            fsum = float(sum(fr[j] * perp_at(ft[j]) / pos['f0'] for j in range(i0, i1)))
            pos['fund'] += fsum
            comp['funding'] += fsum
            pos['t'] = t - 1
        if have:
            s, f = st[t], pp[t]
            i_hi = np.searchsorted(ft, t, side='left')
            i_lo = np.searchsorted(ft, t - WINDOW_MS, side='left')
            enough = ft.size and ft[0] <= t - WINDOW_MS
            sig = (cs[i_hi] - cs[i_lo]) / 21.0 if enough else None
            if pos is None and sig is not None and (always_in or sig >= ENTER):
                pos = dict(s0=s, f0=f, ref=s, t=t, fund=0.0)
                realized -= RT_COST / 2
                comp['cost'] += RT_COST / 2
                comp['trades'] += 1
            elif pos is not None and not always_in and sig is not None and sig < EXIT:
                base = s / pos['s0'] - f / pos['f0']
                realized += base + pos['fund'] - RT_COST / 2
                comp['base'] += base
                comp['cost'] += RT_COST / 2
                pos = None
            elif pos is not None and (s / pos['ref'] >= REBAL or s / pos['ref'] <= 1 / REBAL):
                # rebalanceo = cerrar y reabrir al mismo nocional (enmienda 1): realiza base + funding y resetea
                # los precios de entrada; si no, el funding queda ponderado por la suba de la moneda.
                base = s / pos['s0'] - f / pos['f0']
                realized += base + pos['fund'] - RT_COST
                comp['base'] += base
                comp['cost'] += RT_COST
                comp['rebal'] += 1
                pos = dict(s0=s, f0=f, ref=s, t=pos['t'], fund=0.0)
            if pos is not None:
                value[k] = realized + (s / pos['s0'] - f / pos['f0']) + pos['fund']
            else:
                value[k] = realized
        else:
            value[k] = value[k - 1] if k else 0.0
    if pos is not None:                       # cierra lo abierto al final (marca, con costo)
        comp['base'] += value[-1] - realized - pos['fund']
        comp['cost'] += RT_COST / 2
        value[-1] -= RT_COST / 2
    r = np.diff(value) / CAPITAL
    return r, comp, float(value[-1] / CAPITAL)


def block_boot(r, rng):
    nb = int(np.ceil(r.size / BLOCK))
    starts = rng.integers(0, r.size - BLOCK, (BOOT, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)).reshape(BOOT, -1)[:, :r.size]
    return np.sort(r[idx].mean(axis=1))


def run(syms, reserved):
    data = {s: load(s) for s in syms}
    t0 = min(min(t for t, _ in data[s]['perp']) for s in syms)
    grid = np.arange(t0 - t0 % P8H, END_MS, P8H, dtype=np.int64).tolist()
    res, rs, rs_all = {}, [], []
    for s in syms:
        r, comp, tot = simulate(data[s], grid)
        ra, comp_a, tot_a = simulate(data[s], grid, always_in=True)
        rs.append(r)
        rs_all.append(ra)
        res[s] = dict(total_on_capital=tot, comp=comp, always_in_total=tot_a,
                      annual=float(r.mean() * PER_YEAR), first=dt.datetime.utcfromtimestamp(
                          min(t for t, _ in data[s]['perp']) / 1000).strftime('%Y-%m-%d'))
        print(f"  {s:5s} desde {res[s]['first']}  neto {tot:+.2%} del capital ({res[s]['annual']:+.2%}/año)  "
              f"funding {comp['funding']:+.3f} base {comp['base']:+.3f} costo {comp['cost']:.3f} (x nocional)  "
              f"entradas {comp['trades']} rebal {comp['rebal']}  | siempre adentro {tot_a:+.2%}")
    port = np.mean(rs, axis=0)
    port_all = np.mean(rs_all, axis=0)
    eq = np.cumprod(1 + port)
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
    ann = float(port.mean() * PER_YEAR)
    bs = block_boot(port, np.random.default_rng(SEED)) * PER_YEAR
    lo, hi = float(bs[int(0.025 * BOOT)]), float(bs[int(0.975 * BOOT)])
    half = port.size // 2
    h1, h2 = float(port[:half].mean() * PER_YEAR), float(port[half:].mean() * PER_YEAR)
    hr = hurdle(grid[0], grid[-1])
    pos = sum(1 for s in syms if res[s]['total_on_capital'] > 0)
    years = {}
    for k in range(port.size):
        y = dt.datetime.utcfromtimestamp(grid[k] / 1000).year
        years.setdefault(y, []).append(port[k])
    print(f"\n  CARTERA: {ann:+.2%}/año sobre el capital  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {h1:+.2%} / {h2:+.2%}  "
          f"caída máx {dd:.2%}  monedas>0 {pos}/{len(syms)}  tasa libre de riesgo media {hr:.2%}")
    print('  por año: ' + '  '.join(f'{y} {np.mean(v) * PER_YEAR:+.1%}' for y, v in sorted(years.items())))
    print(f"  siempre adentro (desc.): {port_all.mean() * PER_YEAR:+.2%}/año, caída máx "
          f"{float(np.max(1 - np.cumprod(1 + port_all) / np.maximum.accumulate(np.cumprod(1 + port_all)))):.2%}")
    if reserved:
        crit = {'oos_anual>0': ann > 0, 'oos_anual>tasa_libre': ann > hr}
    else:
        crit = {'1_anual>tasa_libre_media': ann > hr,
                '2_CI_inf>0': lo > 0,
                '3_dos_mitades>0': h1 > 0 and h2 > 0,
                '4_caida_max<10%': dd < 0.10,
                '5_>=4/6_monedas>0': pos >= 4}
    ok = all(crit.values())
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    print(f"  >>> {'PASA' if ok else 'NO PASA'}")
    return dict(por_moneda=res, annual=ann, ci=[lo, hi], halves=[h1, h2], max_dd=dd, hurdle=hr, pos=pos,
                por_anio={y: float(np.mean(v) * PER_YEAR) for y, v in years.items()},
                always_in_annual=float(port_all.mean() * PER_YEAR), criterios=crit, PASA=ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El principal NO pasó (o no se corrió): los reservados no se miran.')
        res = run(RESERVED, True)
        path = OUT.replace('.json', '_reservados.json')
    else:
        res = run(MAIN, False)
        path = OUT
    res['criterio'] = 'docs/p15_funding_criterio.md (748e62f)'
    with open(path, 'w') as f:
        json.dump(res, f, indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
