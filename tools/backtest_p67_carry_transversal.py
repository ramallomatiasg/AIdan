"""P67 — carry TRANSVERSAL de funding: cada lunes corto el quintil de perpetuos con funding de 7 días más alto y
largo el más bajo, peso igual, funding real y costo por rotación.

Criterio declarado antes de medir: docs/p67_carry_transversal_criterio.md (40c5f4b).
Read-only: sin MT5, no toca la DB. Datos: tools/fetch_p67_perps.py -> .cache_p67/.

  python tools/backtest_p67_carry_transversal.py              # 2020-2023
  python tools/backtest_p67_carry_transversal.py --reserved   # 2024 -> hoy, solo si pasó (requiere --full en el fetch)
"""
import argparse
import datetime as dt
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p67')
OUT = os.path.join(ROOT, 'docs', 'p67_carry_transversal_resultado.json')
COST, PESS = 0.0015, 0.0030
BOOT, SEED, NPLAC = 5000, 20261123, 200
D, W = 86400_000, 7 * 86400_000
MINVOL = 10e6
U = lambda y, m, d: int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


def load(sub):
    out = {}
    for p in glob.glob(os.path.join(C, sub, '*.json')):
        d = json.load(open(p))
        if not d['k']:
            continue
        k = np.array(d['k'], dtype=float)
        f = np.array(d['f'], dtype=float).reshape(-1, 2)
        out[os.path.basename(p)[:-5]] = dict(ts=k[:, 0].astype(np.int64), o=k[:, 1], v=k[:, 2],
                                            ft=f[:, 0].astype(np.int64), fr=f[:, 1])
    return out


def signal(s, m):
    """(funding medio, n cobros) en [m-7d, m)."""
    a, b = np.searchsorted(s['ft'], m - W), np.searchsorted(s['ft'], m)
    return (float(s['fr'][a:b].mean()) if b > a else None), int(b - a)


def eligible(s, m):
    ts = s['ts']
    if ts[0] > m - 30 * D:
        return False
    i = np.searchsorted(ts, m)
    if i >= ts.size or ts[i] != m or s['v'][i] <= 0:
        return False
    a = np.searchsorted(ts, m - W)
    if i - a < 5:
        return False
    if (s['v'][a:i] * s['o'][a:i]).mean() < MINVOL:
        return False
    return signal(s, m)[1] >= 15


def leg(s, a_ms, b_ms):
    """(retorno de precio, funding sumado) de a_ms a b_ms; cierra antes si deja de cotizar."""
    ts, o, v = s['ts'], s['o'], s['v']
    ia = np.searchsorted(ts, a_ms)
    ib = np.searchsorted(ts, b_ms)
    if ib >= ts.size or ts[ib] != b_ms or v[ib] <= 0:
        live = np.flatnonzero((ts > a_ms) & (ts < b_ms) & (v > 0))
        if live.size == 0:
            return 0.0, 0.0
        ib = live[-1]
    i0, i1 = np.searchsorted(s['ft'], ts[ia], side='right'), np.searchsorted(s['ft'], ts[ib], side='right')
    return o[ib] / o[ia] - 1, float(s['fr'][i0:i1].sum())


def pick(sig):
    """sig: {sym: valor}. Devuelve (largos, cortos) por quintil."""
    if len(sig) < 10:
        return None
    q = max(2, len(sig) // 5)
    order = sorted(sig, key=lambda x: (sig[x], x))
    return order[:q], order[-q:]


_MEMO = {}


def leg_m(data, x, m):
    k = (x, m)
    if k not in _MEMO:
        _MEMO[k] = leg(data[x], m, m + W)
    return _MEMO[k]


def week_ret(data, lg, sh, m):
    pl = [leg_m(data, x, m) for x in lg]
    ps = [leg_m(data, x, m) for x in sh]
    L = np.mean([r - f for r, f in pl]); S = np.mean([-r + f for r, f in ps])
    return (L + S) / 2, dict(L_px=np.mean([r for r, _ in pl]), L_f=-np.mean([f for _, f in pl]),
                             S_px=-np.mean([r for r, _ in ps]), S_f=np.mean([f for _, f in ps]))


def turnover(old, new):
    ks = set(old) | set(new)
    return sum(abs(new.get(k, 0) - old.get(k, 0)) for k in ks)


def block_ci(x, rng, b=4):
    nb = int(np.ceil(x.size / b)); st = np.arange(0, x.size - b + 1)
    bs = np.empty(BOOT)
    for r in range(BOOT):
        idx = np.concatenate([np.arange(s, s + b) for s in rng.choice(st, nb)])[:x.size]
        bs[r] = x[idx].mean()
    bs.sort()
    return float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
        data = load('full'); m0 = U(2024, 1, 1)
        m1 = max(int(s['ts'][-1]) for s in data.values()) - W
    else:
        data = load('disc'); m0, m1 = U(2020, 1, 6), U(2023, 12, 25)
    mondays = list(range(m0, m1 + 1, W))
    rng = np.random.default_rng(SEED)
    rows, wold_l, wold_s = [], {}, {}
    elig_by_week, sig_by_week = {}, {}
    for m in mondays:
        el = [x for x, s in data.items() if eligible(s, m)]
        sig = {x: signal(data[x], m)[0] for x in el}
        elig_by_week[m] = el
        sig_by_week[m] = {x: v for x, s in data.items() for v, n in [signal(s, m)] if n >= 15}
        p = pick(sig)
        if p is None:
            continue
        lg, sh = p
        g, parts = week_ret(data, lg, sh, m)
        wl = {x: 1 / len(lg) for x in lg}; ws = {x: 1 / len(sh) for x in sh}
        tv = (turnover(wold_l, wl) + turnover(wold_s, ws)) / 2
        wold_l, wold_s = wl, ws
        btc = leg(data['BTCUSDT'], m, m + W)[0] if 'BTCUSDT' in data else np.nan
        rows.append(dict(m=m, g=g, tv=tv, n=len(el), btc=btc, **parts))
    g = np.array([r['g'] for r in rows]); tv = np.array([r['tv'] for r in rows])
    ex = g - COST * tv; exp_ = g - PESS * tv
    lo, hi = block_ci(ex, rng)
    h = ex.size // 2
    wk = [r['m'] for r in rows]
    plac = np.empty(NPLAC)
    for k in range(NPLAC):
        acc = []
        for m in wk:
            mm = wk[rng.integers(0, len(wk))]
            sig = {x: sig_by_week[mm][x] for x in elig_by_week[m] if x in sig_by_week[mm]}
            p = pick(sig)
            if p:
                acc.append(week_ret(data, p[0], p[1], m)[0])
        plac[k] = np.mean(acc)
    p95 = float(np.percentile(plac, 95))
    eq = np.cumprod(1 + ex); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    f = lambda t: dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime('%Y-%m-%d')
    print(f'== P67 carry transversal {tag}: {ex.size} semanas ({f(wk[0])} -> {f(wk[-1])}), '
          f'elegibles medio {np.mean([r["n"] for r in rows]):.0f}')
    print(f'  neto {ex.mean():+.3%}/semana (≈{ex.mean() * 52:+.1%}/año)  CI95 bloques [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
    print(f'  bruto {g.mean():+.3%}  rotación media {tv.mean():.2f}  placebo media {plac.mean():+.3%} p95 {p95:+.3%}')
    for k in ('L_px', 'L_f', 'S_px', 'S_f'):
        print(f'    {k} {np.mean([r[k] for r in rows]):+.3%}', end='')
    btc = np.array([r['btc'] for r in rows])
    print(f'\n  peor semana {ex.min():+.2%}  caída máx {dd:+.1%}  corr con BTC {np.corrcoef(ex, btc)[0, 1]:+.2f}')
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
    print(f'  >>> P67 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(semanas=int(ex.size), neto=float(ex.mean()), ci=[lo, hi], mitades=[float(ex[:h].mean()),
               float(ex[h:].mean())], pesimista=float(exp_.mean()), bruto=float(g.mean()),
               placebo_media=float(plac.mean()), placebo_p95=p95, caida_max=dd,
               semanal=[[f(r['m']), float(x)] for r, x in zip(rows, ex)],
               criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p67_carry_transversal_criterio.md (40c5f4b)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
