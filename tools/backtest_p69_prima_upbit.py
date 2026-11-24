"""P69 — prima de Upbit por moneda: cada lunes corto el quintil de perpetuos cuya moneda cotiza en Upbit con más prima
(relativa a BTC, media de 7 días) y largo el de menos prima; funding real y costo por rotación como P67.

Criterio declarado antes de medir: docs/p69_prima_upbit_criterio.md (997536c).
Read-only: sin MT5, no toca la DB. Upbit API pública -> .cache_p69/; Binance -> .cache_p67/ (tools/fetch_p67_perps.py).

  python tools/backtest_p69_prima_upbit.py              # 2020-2023
  python tools/backtest_p69_prima_upbit.py --reserved   # 2024 -> hoy, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p67_carry_transversal as P  # noqa: E402

ROOT = P.ROOT
C = os.path.join(ROOT, '.cache_p69')
OUT = os.path.join(ROOT, 'docs', 'p69_prima_upbit_resultado.json')
COST, PESS = 0.0015, 0.0030
D, W = P.D, P.W
DISC_END = '2024-01-08T00:00:00'


def _get(u):
    for k in range(6):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}),
                timeout=30).read())
        except Exception:
            time.sleep(1 + 2 * k)
    raise RuntimeError(u)


def upbit(market, to):
    """dict día UTC (ms) -> (cierre KRW, volumen KRW)."""
    os.makedirs(C, exist_ok=True)
    p = os.path.join(C, f'{market}_{to[:10]}.json')
    if os.path.exists(p):
        return {int(k): tuple(v) for k, v in json.load(open(p)).items()}
    out, t = {}, to
    while True:
        r = _get(f'https://api.upbit.com/v1/candles/days?market={market}&count=200&to={t}Z')
        time.sleep(0.15)
        if not r:
            break
        for c in r:
            day = int(dt.datetime.strptime(c['candle_date_time_utc'], '%Y-%m-%dT%H:%M:%S')
                      .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
            out[day] = (float(c['trade_price']), float(c['candle_acc_trade_price']))
        if len(r) < 200:
            break
        t = r[-1]['candle_date_time_utc']
    json.dump(out, open(p, 'w'))
    return out


def mapping(data):
    mk = json.load(open(os.path.join(C, 'markets.json'))) if os.path.exists(os.path.join(C, 'markets.json')) else None
    if mk is None:
        os.makedirs(C, exist_ok=True)
        mk = _get('https://api.upbit.com/v1/market/all')
        json.dump(mk, open(os.path.join(C, 'markets.json'), 'w'))
    out = {}
    for m in mk:
        if not m['market'].startswith('KRW-'):
            continue
        x = m['market'][4:]
        for pre, sc in (('', 1), ('1000', 1000), ('1000000', 1e6)):
            if pre + x + 'USDT' in data:
                out[m['market']] = (pre + x + 'USDT', sc)
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
        data = P.load('full'); m0 = P.U(2024, 1, 1); to = dt.datetime.utcnow().strftime('%Y-%m-%dT00:00:00')
        m1 = max(int(s['ts'][-1]) for s in data.values()) - W
    else:
        data = P.load('disc'); m0, m1 = P.U(2020, 1, 6), P.U(2023, 12, 25); to = DISC_END
    mp = mapping(data)
    print(f'{len(mp)} mercados KRW mapeados a perpetuos', flush=True)
    up = {mk: upbit(mk, to) for mk in mp}

    def prem(mk, day):
        """prima absoluta (sin FX) del día: cierre Upbit / open Binance del día siguiente (escala del perpetuo)."""
        sym, sc = mp[mk]
        u = up[mk].get(day)
        s = data[sym]
        i = np.searchsorted(s['ts'], day + D)
        if u is None or i >= s['ts'].size or s['ts'][i] != day + D or s['o'][i] <= 0:
            return None
        return u[0] / (s['o'][i] / sc)

    pb = {}
    rel = {}
    for mk in mp:
        rel[mk] = {}
    days = range(m0 - 31 * D, m1 + 1, D)
    for day in days:
        b = prem('KRW-BTC', day) if 'KRW-BTC' in mp else None
        pb[day] = b
        if b is None:
            continue
        for mk in mp:
            if mk == 'KRW-BTC':
                continue
            p = prem(mk, day)
            if p is not None:
                rel[mk][day] = p / b - 1

    def sig_of(mk, m):
        v = [rel[mk][d] for d in range(m - W, m, D) if d in rel[mk]]
        return (float(np.mean(v)) if len(v) >= 5 else None)

    def ok_extra(mk, m):
        v = [abs(rel[mk][d]) for d in range(m - 30 * D, m, D) if d in rel[mk]]
        if len(v) < 5 or np.median(v) > 0.20:
            return False
        kv = [up[mk][d][1] for d in range(m - W, m, D) if d in up[mk]]
        return len(kv) >= 5 and np.mean(kv) >= 1e9

    rng = np.random.default_rng(P.SEED)
    rows, wold_l, wold_s = [], {}, {}
    el_by, sig_by = {}, {}
    for m in range(m0, m1 + 1, W):
        sb = {}
        for mk in mp:
            if mk == 'KRW-BTC':
                continue
            s = sig_of(mk, m)
            if s is not None:
                sb[mp[mk][0]] = s
        sig_by[m] = sb
        el = [mp[mk][0] for mk in mp if mk != 'KRW-BTC' and mp[mk][0] in sb
              and P.eligible(data[mp[mk][0]], m) and ok_extra(mk, m)]
        el_by[m] = el
        p = P.pick({x: sb[x] for x in el})
        if p is None:
            continue
        lg, sh = p  # prima más baja = largos; más alta = cortos
        g, parts = P.week_ret(data, lg, sh, m)
        wl = {x: 1 / len(lg) for x in lg}; ws = {x: 1 / len(sh) for x in sh}
        tv = (P.turnover(wold_l, wl) + P.turnover(wold_s, ws)) / 2
        wold_l, wold_s = wl, ws
        btc = P.leg_m(data, 'BTCUSDT', m)[0]
        rows.append(dict(m=m, g=g, tv=tv, n=len(el), btc=btc, **parts))
    if not rows:
        sys.exit('sin semanas con cartera')
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
            sg = {x: sig_by[mm][x] for x in el_by[m] if x in sig_by[mm]}
            pp = P.pick(sg)
            if pp:
                acc.append(P.week_ret(data, pp[0], pp[1], m)[0])
        plac[k] = np.mean(acc) if acc else np.nan
    p95 = float(np.nanpercentile(plac, 95))
    eq = np.cumprod(1 + ex); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    f = lambda t: dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime('%Y-%m-%d')
    print(f'== P69 prima de Upbit {tag}: {ex.size} semanas ({f(wk[0])} -> {f(wk[-1])}), '
          f'elegibles medio {np.mean([r["n"] for r in rows]):.0f}')
    print(f'  neto {ex.mean():+.3%}/semana (≈{ex.mean() * 52:+.1%}/año)  CI95 bloques [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
    print(f'  bruto {g.mean():+.3%}  rotación media {tv.mean():.2f}  placebo media {np.nanmean(plac):+.3%} '
          f'p95 {p95:+.3%}')
    print('   ' + '  '.join(f'{k} {np.mean([r[k] for r in rows]):+.3%}' for k in ('L_px', 'L_f', 'S_px', 'S_f')))
    btc = np.array([r['btc'] for r in rows])
    print(f'  peor semana {ex.min():+.2%}  caída máx {dd:+.1%}  corr con BTC {np.corrcoef(ex, btc)[0, 1]:+.2f}')
    for nm in ('p67_carry_transversal', 'p68_beta_cripto'):
        pth = os.path.join(ROOT, 'docs', nm + '_resultado.json')
        if os.path.exists(pth) and 'semanal' in json.load(open(pth)):
            s2 = dict(json.load(open(pth))['semanal'])
            pr = [(x, s2[f(r['m'])]) for r, x in zip(rows, ex) if f(r['m']) in s2]
            if len(pr) > 20:
                print(f'  corr semanal con {nm[:3].upper()} {np.corrcoef(*zip(*pr))[0, 1]:+.2f} (n={len(pr)})')
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
    print(f'  >>> P69 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(semanas=int(ex.size), neto=float(ex.mean()), ci=[lo, hi], mitades=[float(ex[:h].mean()),
               float(ex[h:].mean())], pesimista=float(exp_.mean()), bruto=float(g.mean()),
               placebo_media=float(np.nanmean(plac)), placebo_p95=p95, caida_max=dd,
               semanal=[[f(r['m']), float(x)] for r, x in zip(rows, ex)],
               criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
               criterio='docs/p69_prima_upbit_criterio.md (997536c)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
