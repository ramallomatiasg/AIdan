"""
backtest_p36_flujos_etf_btc.py — P36: flujos de los ETF de bitcoin (EE.UU.) -> retorno de BTC al día siguiente.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p36/all.html` (farside, bajado una vez) y `.cache_p15/BTC.json`.
Criterio declarado ANTES de medir: docs/p36_flujos_etf_btc_criterio.md (58dd176 + enmienda 1 2cdc9a3). Leer contra eso.

Uso:
    python tools/backtest_p36_flujos_etf_btc.py            # usa el cache
    python tools/backtest_p36_flujos_etf_btc.py --fetch    # vuelve a bajar la tabla de farside
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_p36', 'all.html')
URL = 'https://farside.co.uk/bitcoin-etf-flow-all-data/'
RT_COST = 0.0014
H8 = 8 * 3600 * 1000
REPS = 2000
MIN_N = 100
SEED = 20261111
OUT = os.path.join(ROOT, 'docs', 'p36_flujos_etf_btc_resultado.json')


def fetch():
    req = urllib.request.Request(URL, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/124.0 Safari/537.36', 'Accept': 'text/html', 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        open(CACHE, 'wb').write(r.read())


def num(s):
    s = s.replace(',', '').strip()
    neg = s.startswith('(')
    v = float(s.strip('()'))
    return -v if neg else v


def flows():
    h = open(CACHE, encoding='utf-8', errors='ignore').read()
    out, skipped = [], dict(feriado=0, incompleto=0)
    seen = set()   # enmienda 1: "-" antes del primer dato de un fondo = fondo no lanzado (vale 0)
    rows = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', h, re.S):
        c = [re.sub('<[^>]+>', '', x).replace('&nbsp;', '').strip()
             for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]
        if c and re.match(r'\d+ \w{3} \d{4}$', c[0]):
            rows.append(c)
    rows.sort(key=lambda c: datetime.strptime(c[0], '%d %b %Y'))
    for c in rows:
        funds = c[1:-1]
        if any(f in ('-', '') and k in seen for k, f in enumerate(funds)):
            skipped['incompleto'] += 1
            continue
        seen |= {k for k, f in enumerate(funds) if f not in ('-', '')}
        funds = ['0' if f in ('-', '') else f for f in funds]
        if all(num(f) == 0 for f in funds):
            skipped['feriado'] += 1
            continue
        out.append((datetime.strptime(c[0], '%d %b %Y').date(), num(c[-1])))
    return out, skipped


def market():
    d = json.load(open(os.path.join(ROOT, '.cache_p15', 'BTC.json')))
    perp = {int(t): p for t, p in d['perp']}
    fund = sorted((int(t), r) for t, r in d['funding'])
    return perp, np.array([t for t, _ in fund]), np.array([r for _, r in fund])


def ts(d, hour):
    return int(datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc).timestamp() * 1000)


def trade_ret(perp, ft, fr, t0, t1):
    """Retorno bruto del perpetuo y suma de funding con t0 < t <= t1 (+300 s de tolerancia)."""
    if t0 not in perp or t1 not in perp:
        return None
    m = (ft > t0 + 300_000) & (ft <= t1 + 300_000)
    return perp[t1] / perp[t0] - 1, float(fr[m].sum()), int(m.sum())


def simulate(F, sig, lo, hi):
    out = []
    for (d, fl, g, fs, half) in F:
        x = sig[d]
        s = 1 if x >= hi else -1 if x <= lo else 0
        if s:
            out.append(dict(d=d, s=s, res=half, gross=s * g, net=s * g - RT_COST - s * fs))
    return out


def main():
    if '--fetch' in sys.argv or not os.path.exists(CACHE):
        fetch()
    fl, skipped = flows()
    perp, ft, fr = market()
    F = []
    nofund = 0
    for d, v in fl:
        e = d + timedelta(1)
        r = trade_ret(perp, ft, fr, ts(e, 8), ts(e, 8) + 3 * H8)
        if r is None:
            continue
        if r[2] != 3:
            nofund += 1
        same = trade_ret(perp, ft, fr, ts(d, 0), ts(d + timedelta(1), 0))
        F.append([d, v, r[0], r[1], None, same[0] if same else np.nan])
    half = len(F) // 2
    for k, row in enumerate(F):
        row[4] = k >= half
    flow = {row[0]: row[1] for row in F}
    desc = np.array([row[1] for row in F[:half]])
    lo, hi = np.percentile(desc, 100 / 3), np.percentile(desc, 200 / 3)
    base = [(r[0], r[1], r[2], r[3], r[4]) for r in F]
    T = simulate(base, flow, lo, hi)
    R = np.array([t['net'] for t in T if t['res']]) * 100
    D = np.array([t['net'] for t in T if not t['res']]) * 100
    lo_ci, hi_ci, _ = bootstrap_ci(R)
    q = R.size // 2
    # placebo: serie de flujos desplazada
    rng = np.random.default_rng(SEED)
    keys = [r[0] for r in F]
    vals = np.array([r[1] for r in F])
    pl = []
    for _ in range(REPS):
        k = int(rng.integers(30, len(F) - 30))
        sh = dict(zip(keys, np.roll(vals, k)))
        tt = [t['net'] for t in simulate(base, sh, lo, hi) if t['res']]
        pl.append(np.mean(tt) * 100)
    pl = np.sort(pl)
    p95 = float(pl[int(0.95 * REPS)])
    lng = np.array([t['net'] for t in T if t['res'] and t['s'] == 1]) * 100
    sht = np.array([t['net'] for t in T if t['res'] and t['s'] == -1]) * 100
    gross = np.array([t['gross'] for t in T if t['res']]) * 100
    yrs = {}
    for t in T:
        yrs.setdefault(t['d'].year, []).append(t['net'] * 100)

    def spear(a, b):
        a, b = np.asarray(a), np.asarray(b)
        m = ~np.isnan(b)
        ra, rb = np.argsort(np.argsort(a[m])), np.argsort(np.argsort(b[m]))
        return float(np.corrcoef(ra, rb)[0, 1])

    ic_next = spear([r[1] for r in F], [r[2] for r in F])
    ic_same = spear([r[1] for r in F], [r[5] for r in F])
    crit = {
        f'1_n_reserva>={MIN_N}': bool(R.size >= MIN_N),
        '2_reserva_media>0_CI_inf>0': bool(R.mean() > 0 and lo_ci is not None and lo_ci > 0),
        '3_descubrimiento>0': bool(D.mean() > 0),
        '4_>placebo_p95': bool(R.mean() > p95),
        '5_dos_mitades_reserva>0': bool(R[:q].mean() > 0 and R[q:].mean() > 0),
    }
    print(f"dias con flujo: {len(fl)} (descartados {skipped}); con precio: {len(F)}; "
          f"desde {F[0][0]} hasta {F[-1][0]}; fundings != 3: {nofund}")
    print(f"umbrales (descubrimiento): p33 {lo:+.1f} M  p67 {hi:+.1f} M")
    print(f"DESCUBRIMIENTO: n={D.size} neto {D.mean():+.3f}%")
    print(f"RESERVA: n={R.size} neto {R.mean():+.3f}%  CI [{lo_ci:+.3f}, {hi_ci:+.3f}]  bruto {gross.mean():+.3f}%  "
          f"ganados {(R > 0).mean():.0%}  mitades {R[:q].mean():+.3f} / {R[q:].mean():+.3f}")
    print(f"   largos {lng.mean():+.3f}% (n={lng.size})  cortos {sht.mean():+.3f}% (n={sht.size})  "
          f"placebo p50 {pl[REPS // 2]:+.3f} p95 {p95:+.3f}")
    print(f"Spearman flujo(D) vs retorno siguiente {ic_next:+.3f} | vs retorno del mismo dia {ic_same:+.3f}")
    print('por año:', {y: round(float(np.mean(v)), 3) for y, v in sorted(yrs.items())})
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p36_flujos_etf_btc_criterio.md (58dd176 + enmienda 1 2cdc9a3)', n_dias=len(F), umbrales=[lo, hi],
                       descubrimiento=dict(n=int(D.size), mean=float(D.mean())),
                       reserva=dict(n=int(R.size), mean=float(R.mean()), ci=[lo_ci, hi_ci], gross=float(gross.mean()),
                                    halves=[float(R[:q].mean()), float(R[q:].mean())], largos=float(lng.mean()),
                                    cortos=float(sht.mean()), placebo_p95=p95),
                       ic_next=ic_next, ic_same=ic_same, por_anio={y: float(np.mean(v)) for y, v in yrs.items()},
                       criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
