"""Baja los datos de P82-P84 a .cache_p82/.cache_p83/.cache_p84 (Yahoo ajustado, FRED, AAII). Solo descarga."""
import datetime as dt, json, os, sys, time, urllib.request
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
P1, P2 = 0, int(time.time())


def yahoo(sym, folder):
    p = os.path.join(ROOT, folder, f'{sym}.json')
    if os.path.exists(p):
        return json.load(open(p))
    u = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={P1}&period2={P2}&interval=1d'
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r:
                j = json.load(r)['chart']['result'][0]
            break
        except Exception:
            if k == 3:
                raise
            time.sleep(3)
    off = j['meta'].get('gmtoffset', 0)
    adj = j['indicators']['adjclose'][0]['adjclose']
    rows = {dt.datetime.utcfromtimestamp(t + off).strftime('%Y-%m-%d'): a for t, a in zip(j['timestamp'], adj) if a}
    json.dump(rows, open(p, 'w'))
    return rows


def fred(sid, folder):
    p = os.path.join(ROOT, folder, f'{sid}.json')
    if os.path.exists(p):
        return json.load(open(p))
    u = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}'
    # sin User-Agent de navegador: FRED deja colgada la conexión cuando se lo manda (ver hyp_data.py)
    with urllib.request.urlopen(u, timeout=60) as r:
        lines = r.read().decode().splitlines()[1:]
    rows = {a: float(b) for a, b in (l.split(',') for l in lines) if b not in ('.', '')}
    json.dump(rows, open(p, 'w'))
    return rows


def show(name, rows):
    ks = sorted(rows)
    print(f'{name}: {len(ks)} filas {ks[0]} -> {ks[-1]}')


if __name__ == '__main__':
    for s in ['SPY', 'EFA', 'EEM', 'TLT', 'IEF', 'GLD', 'DBC', 'VNQ']:
        show('P82 ' + s, yahoo(s, '.cache_p82'))
    show('P83 VUSTX', yahoo('VUSTX', '.cache_p83'))
    show('P83 T10Y3M', fred('T10Y3M', '.cache_p83'))
    show('P84 SPY', yahoo('SPY', '.cache_p84'))
