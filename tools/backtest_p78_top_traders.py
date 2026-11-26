"""P78 — top traders de Binance contra la masa: cada lunes largo el quintil donde los top traders están más largos que
todas las cuentas (s = ln(top) - ln(cuentas) alto) y corto el más bajo; peso igual, funding real y costo por rotación
(armado de P67/P70).

Criterio declarado antes de medir: docs/p78_top_traders_criterio.md (6a17ab7).
Read-only: sin MT5, no toca la DB. metrics de data.binance.vision (solo los domingos) a .cache_p78/;
precios/funding de .cache_p67/full.

  python tools/backtest_p78_top_traders.py              # may-2022 -> jun-2024
  python tools/backtest_p78_top_traders.py --reserved   # jul-2024 -> hoy, solo si pasó
"""
import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p67_carry_transversal as p67  # noqa: E402

ROOT = p67.ROOT
C = os.path.join(ROOT, '.cache_p78')
OUT = os.path.join(ROOT, 'docs', 'p78_top_traders_resultado.json')
SEED = 20261126
W = p67.W
U = p67.U


def f(t):
    return dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime('%Y-%m-%d')


def _tt_fetch(sym, m):
    """s = ln(top traders) - ln(todas las cuentas) en la última fila >=23:00 del domingo previo al lunes m."""
    d = f(m - 86400 * 1000)
    p = os.path.join(C, sym, d + '.json')
    if os.path.exists(p):
        return json.load(open(p))['s']
    u = f'https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{d}.zip'
    val, done = None, False
    for k in range(5):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                         timeout=60).read()
            z = zipfile.ZipFile(io.BytesIO(raw))
            rows = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode())))
            rows.sort(key=lambda r: r['create_time'])
            for r in reversed(rows):
                if r['create_time'][:10] != d or r['create_time'][11:13] < '23':
                    break
                try:
                    a, b = float(r['sum_toptrader_long_short_ratio']), float(r['count_long_short_ratio'])
                except (ValueError, KeyError, TypeError):
                    continue
                if a > 0 and b > 0:
                    val = float(np.log(a) - np.log(b))
                    break
            done = True
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                done = True
                break
            time.sleep(2 + 3 * k)
        except Exception:
            time.sleep(2 + 3 * k)
    if not done:
        raise RuntimeError('sin respuesta: ' + u)
    os.makedirs(os.path.join(C, sym), exist_ok=True)
    json.dump({'s': val}, open(p, 'w'))
    return val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    data = p67.load('full')
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
        m0 = U(2024, 7, 1); m1 = max(int(s['ts'][-1]) for s in data.values()) - W
    else:
        m0, m1 = U(2022, 5, 30), U(2024, 6, 24)
    mondays = list(range(m0, m1 + 1, W))
    elig0 = {m: [x for x, s in data.items() if p67.eligible(s, m)] for m in mondays}
    need = sorted({(x, m) for m in mondays for x in elig0[m]})
    print(f'metrics: {len(need)} archivos-domingo a leer/bajar', flush=True)
    tt = {}
    with cf.ThreadPoolExecutor(16) as ex_:
        futs = {ex_.submit(_tt_fetch, x, mm): (x, mm) for x, mm in need}
        for i, fu in enumerate(cf.as_completed(futs)):
            tt[futs[fu]] = fu.result()
            if i % 2000 == 0:
                print(f'  {i}/{len(need)}', flush=True)
    rng = np.random.default_rng(SEED)
    rows, wl0, ws0 = [], {}, {}
    sig_by, el_by, sinoi = {}, {}, 0
    for m in mondays:
        el, sig = [], {}
        for x in elig0[m]:
            v = tt.get((x, m))
            if v is None:
                sinoi += 1
                continue
            el.append(x); sig[x] = -v          # pick() pone largo el valor más BAJO ⇒ -s: largo donde los grandes están más largos
        el_by[m], sig_by[m] = el, sig
        p = p67.pick(sig)
        if p is None:
            continue
        lg, sh = p
        g, parts = p67.week_ret(data, lg, sh, m)
        wl = {x: 1 / len(lg) for x in lg}; ws = {x: 1 / len(sh) for x in sh}
        tv = (p67.turnover(wl0, wl) + p67.turnover(ws0, ws)) / 2
        wl0, ws0 = wl, ws
        grev = np.nan
        btc = p67.leg(data['BTCUSDT'], m, m + W)[0]
        rows.append(dict(m=m, g=g, tv=tv, n=len(el), btc=btc, rev=grev, **parts))
    g = np.array([r['g'] for r in rows]); tv = np.array([r['tv'] for r in rows])
    ex = g - p67.COST * tv; exp_ = g - p67.PESS * tv
    lo, hi = p67.block_ci(ex, rng)
    h = ex.size // 2
    wk = [r['m'] for r in rows]
    plac = np.empty(p67.NPLAC)
    for k in range(p67.NPLAC):
        acc = []
        for m in wk:
            mm = wk[rng.integers(0, len(wk))]
            sig = {x: sig_by[mm][x] for x in el_by[m] if x in sig_by[mm]}
            p = p67.pick(sig)
            if p:
                acc.append(p67.week_ret(data, p[0], p[1], m)[0])
        plac[k] = np.mean(acc)
    p95 = float(np.percentile(plac, 95))
    eq = np.cumprod(1 + ex); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f'== P78 top traders vs masa {tag}: {ex.size} semanas ({f(wk[0])} -> {f(wk[-1])}), elegibles medio '
          f'{np.mean([r["n"] for r in rows]):.0f}, monedas-semana sin metrics {sinoi}')
    print(f'  neto {ex.mean():+.3%}/semana (~{ex.mean() * 52:+.1%}/año)  CI95 bloques [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
    print(f'  bruto {g.mean():+.3%}  rotación media {tv.mean():.2f}  placebo media {plac.mean():+.3%} p95 {p95:+.3%}')
    for k in ('L_px', 'L_f', 'S_px', 'S_f'):
        print(f'    {k} {np.mean([r[k] for r in rows]):+.3%}', end='')
    btc = np.array([r['btc'] for r in rows]); rev = np.array([r['rev'] for r in rows])
    ok_r = ~np.isnan(rev)
    print(f'\n  peor semana {ex.min():+.2%}  caída máx {dd:+.1%}  corr con BTC {np.corrcoef(ex, btc)[0, 1]:+.2f}')
    pj = os.path.join(ROOT, 'docs', 'p67_carry_transversal_resultado' + ('_reserva' if a.reserved else '') + '.json')
    if os.path.exists(pj):
        p67w = dict(json.load(open(pj)).get('semanal', []))
        pairs = [(x, p67w[f(r['m'])]) for r, x in zip(rows, ex) if f(r['m']) in p67w]
        if len(pairs) > 20:
            print(f'  corr con P67 (n={len(pairs)}) {np.corrcoef(*zip(*pairs))[0, 1]:+.2f}')
    pj = os.path.join(ROOT, 'docs', 'p70_interes_abierto_resultado.json')
    if os.path.exists(pj) and not a.reserved:
        p70w = dict(json.load(open(pj)).get('semanal', []))
        pairs = [(x, p70w[f(r['m'])]) for r, x in zip(rows, ex) if f(r['m']) in p70w]
        if len(pairs) > 20:
            print(f'  corr con P70 (n={len(pairs)}) {np.corrcoef(*zip(*pairs))[0, 1]:+.2f}')
    yrs = {}
    for r, x in zip(rows, ex):
        yrs.setdefault(f(r['m'])[:4], []).append(x)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%} (n={len(v)})' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '5_bruto>placebo_p95': g.mean() > p95}
    else:
        crit = {'1_semanas>=100': ex.size >= 100, '2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0,
                '3_dos_mitades>0': ex[:h].mean() > 0 and ex[h:].mean() > 0, '4_pesimista>0': exp_.mean() > 0,
                '5_bruto>placebo_p95': g.mean() > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P78 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(semanas=int(ex.size), neto=float(ex.mean()), ci=[lo, hi], mitades=[float(ex[:h].mean()),
               float(ex[h:].mean())], pesimista=float(exp_.mean()), bruto=float(g.mean()),
               placebo_media=float(plac.mean()), placebo_p95=p95, caida_max=dd,
               semanal=[[f(r['m']), float(x)] for r, x in zip(rows, ex)],
               criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p78_top_traders_criterio.md (6a17ab7)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
