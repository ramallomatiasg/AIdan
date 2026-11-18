"""p49_unlocks_data.py — P49: calendario de desbloqueos (DefiLlama, público) mapeado a perpetuos USDT de Binance.

READ-ONLY. Sin MT5, no toca la DB. Cache en .cache_p49/. No baja precios (eso lo hace backtest_p49_unlocks.py).
Mapeo símbolo: slug de /protocols → parentProtocols → chains (tokenSymbol); se exige que exista el perpetuo
<SYM>USDT en fapi exchangeInfo (cualquier estado). Eventos: metadata.events con unlockType 'cliff'.
Tamaño = tokens del evento (sumados por día) / desbloqueado total del día previo (documentedData) .
"""
import datetime as dt
import json
import os
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
C = os.path.join(ROOT, '.cache_p49')


def _get(u, path=None):
    if path and os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    for k in range(5):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}),
                                         timeout=90).read()
            d = json.loads(raw)
            if path:
                open(path, 'wb').write(raw)
            return d
        except Exception:
            if k == 4:
                raise
            time.sleep(3 + 3 * k)


def mapping():
    L = _get('https://defillama-datasets.llama.fi/emissionsProtocolsList', os.path.join(C, 'list.json'))
    P = _get('https://api.llama.fi/protocols', os.path.join(C, 'protocols.json'))
    P2 = _get('https://api.llama.fi/lite/protocols2', os.path.join(C, 'p2.json'))
    F = _get('https://fapi.binance.com/fapi/v1/exchangeInfo', os.path.join(C, 'fapi.json'))
    perps = {s['baseAsset']: s['symbol'] for s in F['symbols']
             if s['quoteAsset'] == 'USDT' and s['contractType'] == 'PERPETUAL'}
    sym = {}
    for p in P:
        if p.get('slug') and p.get('symbol') and p['symbol'] != '-':
            sym.setdefault(p['slug'], p['symbol'])
    for p in P2['parentProtocols']:
        if p.get('symbol'):
            sym.setdefault(p['id'].split('#', 1)[1], p['symbol'])
    for c in P2.get('chains', []):
        if isinstance(c, dict) and c.get('tokenSymbol') and c.get('name'):
            sym.setdefault(c['name'].lower().replace(' ', '-'), c['tokenSymbol'])
    out = {}
    for s in L:
        t = (sym.get(s) or '').upper()
        if t in perps and t not in ('BTC', 'ETH', 'USDT', 'USDC'):
            out.setdefault(t, s)            # una sola fuente por símbolo (la primera de la lista)
    return out, perps


def events(t0=dt.datetime(2022, 1, 1), t1=dt.datetime(2026, 10, 15), min_frac=0.01):
    m, perps = mapping()
    ev = []
    for symb, slug in sorted(m.items()):
        try:
            d = _get(f'https://defillama-datasets.llama.fi/emissions/{slug}', os.path.join(C, 'em', f'{slug}.json'))
        except Exception:
            continue
        unl = {}
        for sec in d.get('documentedData', {}).get('data', []):
            for x in sec.get('data', []):
                unl[x['timestamp'] // 86400] = unl.get(x['timestamp'] // 86400, 0.0) + float(x.get('unlocked') or 0)
        days = sorted(unl)
        byday = {}
        for e in d.get('metadata', {}).get('events', []) or []:
            if e.get('unlockType') != 'cliff' or not e.get('timestamp'):
                continue
            n = sum(float(x or 0) for x in (e.get('noOfTokens') or []))
            day = int(e['timestamp']) // 86400
            b = byday.setdefault(day, dict(n=0.0, cats=set()))
            b['n'] += n
            b['cats'].add(e.get('category') or '?')
        for day, b in byday.items():
            when = dt.datetime.utcfromtimestamp(day * 86400)
            if not (t0 <= when <= t1) or b['n'] <= 0:
                continue
            prev = [x for x in days if x < day]
            if not prev or unl[prev[-1]] <= 0:
                continue
            frac = b['n'] / unl[prev[-1]]
            if frac >= min_frac:
                ev.append(dict(sym=symb, perp=perps[symb], slug=slug, day=day, date=when.strftime('%Y-%m-%d'),
                               frac=frac, cats=sorted(b['cats'])))
    return sorted(ev, key=lambda e: e['day'])


if __name__ == '__main__':
    ev = events()
    print('eventos', len(ev), 'monedas', len({e['sym'] for e in ev}))
    for y in range(2022, 2027):
        print(y, sum(e['date'].startswith(str(y)) for e in ev))
    import collections
    print(collections.Counter(c for e in ev for c in e['cats']).most_common())
    print(ev[:5])
