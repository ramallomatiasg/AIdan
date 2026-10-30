"""
backtest_p20_cash_carry.py — P20: cash-and-carry con futuros trimestrales USDT-M de Binance (BTC, ETH).

READ-ONLY respecto de AIdan: sin MT5, no toca la DB. Baja datos PÚBLICOS de Binance (sin cuenta) a `.cache_p20/`.
Criterio declarado ANTES de medir: docs/p20_cash_and_carry_criterio.md (18706b2). Leer contra eso.

Uso:
    python tools/backtest_p20_cash_carry.py
"""
import csv
import datetime as dt
import json
import os
import time
import urllib.request

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE = os.path.join(ROOT, '.cache_p20')
MAIN = ['BTC', 'ETH']
START = dt.date(2021, 1, 1)
END = dt.date(2026, 10, 29)
RT_COST = 2 * (0.0010 + 0.0005) + 4 * 0.0002               # 0,38% del nocional (igual que P15)
CAPITAL = 2.0
MIN_DAYS = 14
LIQ = 0.80
BLOCK = 7
BOOT = 5000
SEED = 20261030
OUT = os.path.join(ROOT, 'docs', 'p20_cash_carry_resultado.json')
DAY_MS = 86400000


def _get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError(url)


def _ms(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def klines(kind, sym):
    """dict fecha -> open diario. kind: spot | CURRENT_QUARTER | NEXT_QUARTER."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'{sym}_{kind}.json')
    if os.path.exists(path):
        with open(path) as f:
            return {dt.date.fromisoformat(k): v for k, v in json.load(f).items()}
    out, t, end = {}, _ms(START), _ms(END) + DAY_MS
    while t < end:
        if kind == 'spot':
            url = f'https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1d&startTime={t}&limit=1000'
        else:
            url = (f'https://fapi.binance.com/fapi/v1/continuousKlines?pair={sym}USDT&contractType={kind}'
                   f'&interval=1d&startTime={t}&limit=1000')
        rows = _get(url)
        if not rows:
            break
        for r in rows:
            d = dt.datetime.fromtimestamp(r[0] / 1000, dt.timezone.utc).date()
            if d <= END:
                out[d] = float(r[1])
        t = rows[-1][0] + DAY_MS
        time.sleep(0.2)
    with open(path, 'w') as f:
        json.dump({k.isoformat(): v for k, v in out.items()}, f)
    return out


def drop_stale(series):
    """Enmienda 1: la serie continua repite el ultimo precio los dias en que el contrato no cotiza
    (p.ej. NEXT_QUARTER 56774,5 del 27-mar al 15-abr-2021). Un open identico al del dia anterior = sin dato."""
    out, prev = {}, None
    for d in sorted(series):
        v = series[d]
        if prev is None or v != prev:
            out[d] = v
        prev = v
    return out


def last_friday(y, m):
    d = dt.date(y, m + 1, 1) - dt.timedelta(days=1) if m < 12 else dt.date(y, 12, 31)
    return d - dt.timedelta(days=(d.weekday() - 4) % 7)


def expiries():
    return sorted(last_friday(y, m) for y in range(2020, 2028) for m in (3, 6, 9, 12))


EXP = expiries()
STALE = {}


def current_expiry(d):
    """Vencimiento del CURRENT_QUARTER a las 00:00 UTC de d (vence a las 08:00 del último viernes)."""
    return next(e for e in EXP if e >= d)


def next_expiry(d):
    return EXP[EXP.index(current_expiry(d)) + 1]


def load_rf():
    rf = {}
    with open(os.path.join(ROOT, 'docs', 'p11_policy_rates.csv')) as f:
        for r in csv.DictReader(f):
            rf[r['month']] = float(r['USD']) / 100
    last = max(rf)

    def get(d):
        k = f'{d.year}-{d.month:02d}'
        return rf.get(k, rf[last])
    return get


def contract_price(d, exp, cur, nxt):
    """Precio del contrato que vence en exp, a la fecha d (o None)."""
    if current_expiry(d) == exp:
        return cur.get(d)
    if next_expiry(d) == exp:
        return nxt.get(d)
    return None


def simulate(sym, rf):
    spot = klines('spot', sym)
    cur_raw, nxt_raw = klines('CURRENT_QUARTER', sym), klines('NEXT_QUARTER', sym)
    cur, nxt = drop_stale(cur_raw), drop_stale(nxt_raw)
    STALE[sym] = (len(cur_raw) - len(cur), len(nxt_raw) - len(nxt))
    days = sorted(d for d in spot if d >= min(min(cur), min(nxt)))
    pnl = {}                      # fecha -> pnl diario sobre la ranura (en unidades de nocional)
    pos, trades, jumps, basis_seen = None, [], [], []
    prev_mtm = 0.0
    for d in days:
        s = spot[d]
        day_pnl = 0.0
        if pos:
            if d >= pos['exp']:                                   # vence hoy (08:00) => liquida a la base pactada
                final = pos['fe'] / pos['se'] - 1
                day_pnl += final - prev_mtm - RT_COST / 2
                trades.append({'entry': pos['d'].isoformat(), 'exit': d.isoformat(), 'how': 'vencimiento',
                               'net': final - RT_COST})
                pos, prev_mtm = None, 0.0
            else:
                f = contract_price(d, pos['exp'], cur, nxt)
                if f is not None:
                    mtm = (s - f - pos['se'] + pos['fe']) / pos['se']
                    b_prev, b_now = pos.get('blast'), f / s - 1
                    if b_prev is not None and abs(b_now - b_prev) > 0.05:
                        jumps.append((d.isoformat(), round(b_prev, 4), round(b_now, 4)))
                    pos['blast'] = b_now
                    if f / pos['fe'] - 1 >= LIQ:                  # salida forzada por margen
                        day_pnl += mtm - prev_mtm - RT_COST / 2
                        trades.append({'entry': pos['d'].isoformat(), 'exit': d.isoformat(), 'how': 'forzada',
                                       'net': mtm - RT_COST})
                        pos, prev_mtm = None, 0.0
                    else:
                        day_pnl += mtm - prev_mtm
                        prev_mtm = mtm
        if pos is None:
            ce = current_expiry(d)
            if (ce - d).days >= MIN_DAYS:
                exp, f = ce, cur.get(d)
            else:
                exp, f = next_expiry(d), nxt.get(d)
            if f is not None and (exp - d).days > 0:
                dleft = (exp - d).days + 8 / 24
                gross = f / s - 1
                ann = (gross - RT_COST) * 365 / dleft
                basis_seen.append((d, gross * 365 / dleft))
                if ann > rf(d):
                    pos = {'d': d, 'exp': exp, 'se': s, 'fe': f, 'blast': gross}
                    prev_mtm = 0.0
                    day_pnl -= RT_COST / 2
        pnl[d] = day_pnl
    return pnl, trades, jumps, basis_seen


def boot_ci(x, rng):
    n = len(x)
    nb = int(np.ceil(n / BLOCK))
    means = []
    for _ in range(BOOT):
        idx = np.concatenate([np.arange(i, min(i + BLOCK, n)) for i in rng.integers(0, n - BLOCK, nb)])[:n]
        means.append(x[idx].mean())
    return np.percentile(means, [2.5, 97.5])


def main():
    rf = load_rf()
    res = {s: simulate(s, rf) for s in MAIN}
    alld = sorted(set.intersection(*[set(res[s][0]) for s in MAIN]))
    port = np.array([np.mean([res[s][0][d] for s in MAIN]) / CAPITAL for d in alld])
    rng = np.random.default_rng(SEED)
    ann = port.mean() * 365
    lo, hi = boot_ci(port, rng) * 365
    h = len(port) // 2
    halves = (port[:h].mean() * 365, port[h:].mean() * 365)
    cum = np.cumsum(port)
    dd = float(np.max(np.maximum.accumulate(cum) - cum))
    rf_mean = float(np.mean([rf(d) for d in alld]))
    coin = {s: float(sum(res[s][0][d] for d in alld) / CAPITAL / len(alld) * 365) for s in MAIN}
    years = {}
    for d, r in zip(alld, port):
        years.setdefault(d.year, []).append(r)
    by_year = {y: float(np.mean(v) * 365) for y, v in years.items()}
    rf_year = {y: float(np.mean([rf(d) for d in alld if d.year == y])) for y in years}
    inside = {s: float(np.mean([1 if any(t['entry'] <= d.isoformat() < t['exit'] for t in res[s][1]) else 0
                                for d in alld])) for s in MAIN}
    basis = {s: float(np.mean([b for _, b in res[s][3]])) for s in MAIN}
    crit = {
        '1_anual>tasa_libre': ann > rf_mean,
        '2_CI_inf>0': lo > 0,
        '3_mitades>0': min(halves) > 0,
        '4_caida<10%': dd < 0.10,
        '5_monedas>0': all(v > 0 for v in coin.values()),
    }
    print('=' * 76)
    print(f'P20 cash-and-carry trimestral (BTC+ETH USDT-M)  {alld[0]} -> {alld[-1]}  dias={len(alld)}')
    print('=' * 76)
    print(f'  anual sobre capital {ann:+.2%}  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades {halves[0]:+.2%} / {halves[1]:+.2%}')
    print(f'  caida max {dd:.2%}  tasa libre media {rf_mean:.2%}')
    for s in MAIN:
        tr = res[s][1]
        print(f'  {s}: anual {coin[s]:+.2%}  trades {len(tr)} (forzadas {sum(t["how"] == "forzada" for t in tr)})'
              f'  adentro {inside[s]:.0%}  base anualizada media disponible {basis[s]:+.2%}'
              f'  saltos de base >5%: {len(res[s][2])}  dias repetidos descartados cur/next {STALE[s]}')
    print('  por anio (cartera vs tasa libre): ' +
          ' · '.join(f'{y} {by_year[y]:+.1%} (rf {rf_year[y]:.1%})' for y in sorted(by_year)))
    for k, v in crit.items():
        print(f'  [{"OK " if v else "NO "}] {k}')
    verdict = 'PASA' if all(crit.values()) else 'NO PASA'
    print(f'>>> {verdict}')
    for s in MAIN:
        if res[s][2]:
            print(f'  saltos {s}: {res[s][2][:6]}')
    out = {'verdict': verdict, 'annual': ann, 'ci': [lo, hi], 'halves': halves, 'max_dd': dd, 'rf_mean': rf_mean,
           'coins': coin, 'by_year': by_year, 'rf_year': rf_year, 'inside': inside, 'basis_mean': basis,
           'criteria': crit, 'trades': {s: res[s][1] for s in MAIN}, 'jumps': {s: res[s][2] for s in MAIN}}
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1, default=str)


if __name__ == '__main__':
    main()
