"""
backtest_p37_emision_stablecoins.py — P37: emisión semanal de USDT+USDC -> retorno de BTC la semana siguiente.

READ-ONLY. Sin MT5, no toca la DB. Lee `.cache_p37/stable_{1,2}.json` (DefiLlama) y `.cache_p15/BTC.json`.
Criterio declarado ANTES de medir: docs/p37_emision_stablecoins_criterio.md (25998ff). Leer contra eso.

Uso:
    python tools/backtest_p37_emision_stablecoins.py            # usa el cache
    python tools/backtest_p37_emision_stablecoins.py --fetch    # vuelve a bajar DefiLlama
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_fase2 import bootstrap_ci  # noqa: E402
from tools.backtest_p36_flujos_etf_btc import market, trade_ret, ts  # noqa: E402

CACHE = os.path.join(ROOT, '.cache_p37')
RT_COST = 0.0014
WEEK = 7 * 24 * 3600 * 1000
START = date(2020, 1, 6)
RES_FROM = date(2023, 1, 1)
REPS = 2000
MIN_N = 40
SEED = 20261111
OUT = os.path.join(ROOT, 'docs', 'p37_emision_stablecoins_resultado.json')


def fetch():
    os.makedirs(CACHE, exist_ok=True)
    for i in (1, 2):
        u = f'https://stablecoins.llama.fi/stablecoincharts/all?stablecoin={i}'
        with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60) as r:
            open(os.path.join(CACHE, f'stable_{i}.json'), 'wb').write(r.read())


def supply():
    S = {}
    for i in (1, 2):
        for x in json.load(open(os.path.join(CACHE, f'stable_{i}.json'))):
            d = datetime.fromtimestamp(int(x['date']), timezone.utc).date()
            S[d] = S.get(d, 0.0) + float(x['totalCirculating']['peggedUSD'])
    return S


def main():
    if '--fetch' in sys.argv or not os.path.exists(os.path.join(CACHE, 'stable_1.json')):
        fetch()
    S = supply()
    perp, ft, fr = market()
    W = []
    d = START
    while True:
        t0 = ts(d, 0)
        r = trade_ret(perp, ft, fr, t0, t0 + WEEK)
        if r is None:
            if t0 + WEEK > max(perp):
                break
            d += timedelta(7)
            continue
        a, b = S.get(d - timedelta(1)), S.get(d - timedelta(8))
        prev = trade_ret(perp, ft, fr, t0 - WEEK, t0)
        if a and b and prev:
            W.append(dict(d=d, sig=np.log(a / b), mom=prev[0], g=r[0], fs=r[1], nf=r[2], res=d >= RES_FROM))
        d += timedelta(7)
    desc = [w for w in W if not w['res']]
    res = [w for w in W if w['res']]
    thr = np.percentile([w['sig'] for w in desc], 200 / 3)
    thr_lo = np.percentile([w['sig'] for w in desc], 100 / 3)
    mthr = np.percentile([w['mom'] for w in desc], 200 / 3)

    def lnet(w):
        return (w['g'] - RT_COST - w['fs']) * 100

    def snet(w):
        return (-w['g'] - RT_COST + w['fs']) * 100

    L = np.array([lnet(w) for w in res if w['sig'] >= thr])
    LD = np.array([lnet(w) for w in desc if w['sig'] >= thr])
    SH = np.array([snet(w) for w in res if w['sig'] <= thr_lo])
    M = np.array([lnet(w) for w in res if w['mom'] >= mthr])
    allres = np.array([lnet(w) for w in res])
    lo, hi, _ = bootstrap_ci(L)
    rng = np.random.default_rng(SEED)
    ctrl = np.sort([rng.choice(allres, L.size, replace=False).mean() for _ in range(REPS)])
    p95 = float(ctrl[int(0.95 * REPS)])

    def spear(a, b):
        ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])

    ic_next = spear([w['sig'] for w in W], [w['g'] for w in W])
    ic_prev = spear([w['sig'] for w in W], [w['mom'] for w in W])
    yrs = {}
    for w in res + desc:
        if w['sig'] >= thr:
            yrs.setdefault(w['d'].year, []).append(lnet(w))
    crit = {
        f'1_n_largos_reserva>={MIN_N}': bool(L.size >= MIN_N),
        '2_reserva_media>0_CI_inf>0': bool(L.mean() > 0 and lo is not None and lo > 0),
        '3_descubrimiento>0': bool(LD.mean() > 0),
        '4_>control_deriva_p95': bool(L.mean() > p95),
        '5_>regla_momentum': bool(L.mean() > M.mean()),
    }
    print(f"semanas: {len(W)} (desc {len(desc)}, reserva {len(res)}) {W[0]['d']} -> {W[-1]['d']}; "
          f"fundings!=21: {sum(w['nf'] != 21 for w in W)}")
    print(f"umbral (tercio alto desc): {thr:+.4%} de emision semanal")
    print(f"DESCUBRIMIENTO largos: n={LD.size} neto {LD.mean():+.3f}%")
    print(f"RESERVA largos: n={L.size} neto {L.mean():+.3f}%  CI [{lo:+.3f}, {hi:+.3f}]  ganados {(L > 0).mean():.0%}")
    print(f"   control deriva (semanas al azar) p50 {ctrl[REPS // 2]:+.3f} p95 {p95:+.3f} | todas las semanas "
          f"{allres.mean():+.3f} | momentum n={M.size} {M.mean():+.3f} | corto tercio bajo n={SH.size} {SH.mean():+.3f}")
    print(f"Spearman emision vs BTC semana siguiente {ic_next:+.3f} | vs BTC semana previa {ic_prev:+.3f}")
    print('largos por año:', {y: round(float(np.mean(v)), 2) for y, v in sorted(yrs.items())})
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f">>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w') as f:
        json.dump(dict(criterio='docs/p37_emision_stablecoins_criterio.md (25998ff)', semanas=len(W), umbral=thr,
                       descubrimiento=dict(n=int(LD.size), mean=float(LD.mean())),
                       reserva=dict(n=int(L.size), mean=float(L.mean()), ci=[lo, hi], control_p95=p95,
                                    todas=float(allres.mean()), momentum=float(M.mean()), corto=float(SH.mean())),
                       ic_next=ic_next, ic_prev=ic_prev, por_anio={y: float(np.mean(v)) for y, v in yrs.items()},
                       criterios=crit, PASA=ok), f, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
