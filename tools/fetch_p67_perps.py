"""fetch_p67_perps.py — baja velas diarias y funding de los perpetuos USDT de Binance (incluye cerrados) a .cache_p67/.

Lo usan P67 (carry transversal) y P68 (beta). Read-only: API pública fapi, sin MT5, no toca la DB de AIdan.
El funding se pide con startTime = primera vela (startTime=0 devuelve solo los últimos ~333 días).
Por default baja solo lo necesario para el DESCUBRIMIENTO (velas y funding hasta el 8-ene-2024) para no mirar la reserva.

    python tools/fetch_p67_perps.py            # descubrimiento
    python tools/fetch_p67_perps.py --full     # todo (solo si algo pasó)
"""
import argparse
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p67')
D = 86400_000
T0 = 1567900800000  # 8-sep-2019, primera vela de BTCUSDT
DISC_END = int(dt.datetime(2024, 1, 8, tzinfo=dt.timezone.utc).timestamp() * 1000)
EXCL = {'BTCDOMUSDT', 'DEFIUSDT', 'BLUEBIRDUSDT', 'FOOTBALLUSDT', 'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'USDPUSDT',
        'FDUSDUSDT'}


def _get(u):
    for k in range(6):
        try:
            return json.loads(urllib.request.urlopen(
                urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return None
            if e.code in (418, 429):
                time.sleep(60)
        except Exception:
            pass
        time.sleep(2 + 3 * k)
    raise RuntimeError(u)


def universe():
    ei = json.load(open(os.path.join(ROOT, '.cache_p56', 'exchangeInfo.json')))
    bad = {x['symbol'] for x in ei['symbols'] if x.get('underlyingType', 'COIN') != 'COIN'}
    s3 = json.load(open(os.path.join(ROOT, '.cache_p56', 's3_symbols.json')))
    return sorted(s for s in s3 if s.endswith('USDT') and '_' not in s and s not in EXCL and s not in bad)


def fetch(sym, end):
    sub = 'full' if end is None else 'disc'
    os.makedirs(os.path.join(C, sub), exist_ok=True)
    p = os.path.join(C, sub, urllib.parse.quote(sym, safe='') + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    q = urllib.parse.quote(sym)
    kl, t = [], T0
    while True:
        u = f'https://fapi.binance.com/fapi/v1/klines?symbol={q}&interval=1d&startTime={t}&limit=1500'
        if end:
            u += f'&endTime={end}'
        k = _get(u)
        if not k:
            break
        kl += [(int(x[0]), float(x[1]), float(x[5])) for x in k]
        if len(k) < 1500:
            break
        t = int(k[-1][0]) + D
    fu = []
    if kl:
        t = kl[0][0] - D
        while True:
            u = f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={q}&startTime={t}&limit=1000'
            if end:
                u += f'&endTime={end}'
            r = _get(u)
            time.sleep(0.65)  # límite propio del endpoint: 500 / 5 min
            if not r:
                break
            fu += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
            if len(r) < 1000:
                break
            t = int(r[-1]['fundingTime']) + 1
    d = dict(k=kl, f=fu)
    json.dump(d, open(p, 'w'))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--full', action='store_true')
    a = ap.parse_args()
    end = None if a.full else DISC_END
    u = universe()
    print(f'{len(u)} símbolos', flush=True)
    n = 0
    for i, s in enumerate(u):
        d = fetch(s, end)
        n += bool(d['k'])
        if i % 50 == 0:
            print(i, s, len(d['k']), len(d['f']), flush=True)
    print(f'listo: {n} con velas')


if __name__ == '__main__':
    main()
