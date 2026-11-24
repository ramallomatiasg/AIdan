"""P68 — apostar contra la beta en cripto: cada lunes largo el quintil de perpetuos de beta (90 d contra BTC) más baja
y corto el de beta más alta, pesos que dejan la cartera en beta 0 con bruto 1, funding real y costo por rotación.

Criterio declarado antes de medir: docs/p68_beta_cripto_criterio.md (3fae952).
Read-only: sin MT5, no toca la DB. Datos: tools/fetch_p67_perps.py -> .cache_p67/ (los mismos de P67).

  python tools/backtest_p68_beta_cripto.py              # abr-2020 -> 2023
  python tools/backtest_p68_beta_cripto.py --reserved   # 2024 -> hoy, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p67_carry_transversal as P  # noqa: E402  (carga, leg, bootstrap por bloques)

ROOT = P.ROOT
OUT = os.path.join(ROOT, 'docs', 'p68_beta_cripto_resultado.json')
COST, PESS = 0.0015, 0.0030
D, W = P.D, P.W


def daily(s):
    """dict ts -> retorno open->open del día (ts = día de inicio)."""
    o, ts = s['o'], s['ts']
    ok = np.flatnonzero((np.diff(ts) == D) & (o[:-1] > 0))
    return dict(zip(ts[ok].tolist(), (o[ok + 1] / o[ok] - 1).tolist()))


def beta(rc, rb, m):
    days = [t for t in range(m - 90 * D, m - D + 1, D) if t in rc and t in rb]
    if len(days) < 60:
        return None
    x = np.array([rb[t] for t in days]); y = np.array([rc[t] for t in days])
    vx = x.var()
    return float(((x - x.mean()) * (y - y.mean())).mean() / vx) if vx > 0 else None


def eligible(s, m):
    ts = s['ts']
    if ts[0] > m - 90 * D:
        return False
    i = np.searchsorted(ts, m)
    if i >= ts.size or ts[i] != m or s['v'][i] <= 0:
        return False
    a = np.searchsorted(ts, m - W)
    return i - a >= 5 and (s['v'][a:i] * s['o'][a:i]).mean() >= P.MINVOL


def build(data, lg, sh, betas, m):
    bl = max(0.1, float(np.mean([betas[x] for x in lg]))); bs = max(0.1, float(np.mean([betas[x] for x in sh])))
    wl = (1 / bl) / (1 / bl + 1 / bs); ws = 1 - wl
    pl = [P.leg_m(data, x, m) for x in lg]; ps = [P.leg_m(data, x, m) for x in sh]
    L = np.mean([r - f for r, f in pl]); S = np.mean([-r + f for r, f in ps])
    w = {x: wl / len(lg) for x in lg}
    w.update({x: -ws / len(sh) for x in sh})
    parts = dict(L_px=wl * np.mean([r for r, _ in pl]), L_f=-wl * np.mean([f for _, f in pl]),
                 S_px=-ws * np.mean([r for r, _ in ps]), S_f=ws * np.mean([f for _, f in ps]), bl=bl, bs=bs)
    return wl * L + ws * S, w, parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
        data = P.load('full'); m0 = P.U(2024, 1, 1)
        m1 = max(int(s['ts'][-1]) for s in data.values()) - W
    else:
        data = P.load('disc'); m0, m1 = P.U(2020, 4, 6), P.U(2023, 12, 25)
    rets = {x: daily(s) for x, s in data.items()}
    rb = rets['BTCUSDT']
    rng = np.random.default_rng(P.SEED)
    rows, wold = [], {}
    el_by, beta_by = {}, {}
    for m in range(m0, m1 + 1, W):
        bm = {}
        for x in data:
            if x == 'BTCUSDT':
                continue
            b = beta(rets[x], rb, m)
            if b is not None:
                bm[x] = b
        beta_by[m] = bm
        el = [x for x in bm if eligible(data[x], m)]
        el_by[m] = el
        p = P.pick({x: bm[x] for x in el})
        if p is None:
            continue
        lg, sh = p  # pick ordena ascendente: los primeros (beta baja) largos, los últimos (beta alta) cortos
        g, w, parts = build(data, lg, sh, bm, m)
        tv = P.turnover(wold, w); wold = w
        btc = P.leg_m(data, 'BTCUSDT', m)[0]
        rows.append(dict(m=m, g=g, tv=tv, n=len(el), btc=btc, **parts))
    g = np.array([r['g'] for r in rows]); tv = np.array([r['tv'] for r in rows])
    ex = g - COST * tv; exp_ = g - PESS * tv
    lo, hi = P.block_ci(ex, rng)
    h = ex.size // 2
    wk = [r['m'] for r in rows]
    plac = np.empty(P.NPLAC)
    for k in range(P.NPLAC):
        acc = []
        for m in wk:
            mm = wk[rng.integers(0, len(wk))]
            bm = {x: beta_by[mm][x] for x in el_by[m] if x in beta_by[mm]}
            p = P.pick(bm)
            if p:
                acc.append(build(data, p[0], p[1], bm, m)[0])
        plac[k] = np.mean(acc)
    p95 = float(np.percentile(plac, 95))
    eq = np.cumprod(1 + ex); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    btc = np.array([r['btc'] for r in rows])
    bport = np.cov(g, btc)[0, 1] / btc.var(ddof=1)
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    f = lambda t: dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime('%Y-%m-%d')
    print(f'== P68 contra la beta {tag}: {ex.size} semanas ({f(wk[0])} -> {f(wk[-1])}), '
          f'elegibles medio {np.mean([r["n"] for r in rows]):.0f}, beta media pata larga '
          f'{np.mean([r["bl"] for r in rows]):.2f} / corta {np.mean([r["bs"] for r in rows]):.2f}')
    print(f'  neto {ex.mean():+.3%}/semana (≈{ex.mean() * 52:+.1%}/año)  CI95 bloques [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
    print(f'  bruto {g.mean():+.3%}  rotación media {tv.mean():.2f}  placebo media {plac.mean():+.3%} p95 {p95:+.3%}')
    print('   ' + '  '.join(f'{k} {np.mean([r[k] for r in rows]):+.3%}' for k in ('L_px', 'L_f', 'S_px', 'S_f')))
    print(f'  beta realizada contra BTC {bport:+.2f}  peor semana {ex.min():+.2%}  caída máx {dd:+.1%}')
    p67 = os.path.join(ROOT, 'docs', 'p67_carry_transversal_resultado.json')
    if os.path.exists(p67):
        s67 = dict(json.load(open(p67))['semanal'])
        pr = [(x, s67[f(r['m'])]) for r, x in zip(rows, ex) if f(r['m']) in s67]
        if len(pr) > 20:
            print(f'  corr semanal con P67 {np.corrcoef(*zip(*pr))[0, 1]:+.2f} (n={len(pr)})')
    yrs = {}
    for r, x in zip(rows, ex):
        yrs.setdefault(f(r['m'])[:4], []).append(x)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%} (n={len(v)})' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '5_bruto>placebo_p95': g.mean() > p95}
    else:
        crit = {'1_semanas>=150': ex.size >= 150, '2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0,
                '3_dos_mitades>0': ex[:h].mean() > 0 and ex[h:].mean() > 0, '4_pesimista>0': exp_.mean() > 0,
                '5_bruto>placebo_p95': g.mean() > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P68 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(semanas=int(ex.size), neto=float(ex.mean()), ci=[lo, hi], mitades=[float(ex[:h].mean()),
               float(ex[h:].mean())], pesimista=float(exp_.mean()), bruto=float(g.mean()),
               placebo_media=float(plac.mean()), placebo_p95=p95, caida_max=dd, beta_realizada=float(bport),
               semanal=[[f(r['m']), float(x)] for r, x in zip(rows, ex)],
               criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p68_beta_cripto_criterio.md (3fae952)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
