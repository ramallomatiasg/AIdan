"""P72 — completa el funding de los caches de P56/P59/P63 (pedido antes con startTime=0 ⇒ solo ~333 días).

Criterio: docs/p72_funding_completo_criterio.md (6c65b94). Read-only respecto de AIdan (API pública fapi, sin MT5,
sin DB). Para cada archivo: funding desde la PRIMERA vela hasta el último funding que ya tenía; velas intactas; el
archivo viejo se copia a <cache>/px_funding_viejo/.

    python tools/fix_p72_funding.py
"""
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DIRS = ['.cache_p56', '.cache_p59', '.cache_p63']
T2024 = 1704067200000


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
    raise RuntimeError('sin respuesta: ' + u)


def funding(sym, t0, t1):
    q = urllib.parse.quote(sym)
    fu, t = [], t0
    while t <= t1:
        r = _get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={q}&startTime={t}&endTime={t1}&limit=1000')
        if not r:
            break
        fu += [(int(x['fundingTime']), float(x['fundingRate'])) for x in r]
        if len(r) < 1000:
            break
        t = int(r[-1]['fundingTime']) + 1
        time.sleep(0.05)
    return fu


def main():
    memo = {}
    stats = dict(archivos=0, arreglados=0, sin_funding=0, chequeo_falla=0, pre2024=0)
    for d in DIRS:
        px = os.path.join(ROOT, d, 'px'); bk = os.path.join(ROOT, d, 'px_funding_viejo')
        os.makedirs(bk, exist_ok=True)
        for fn in sorted(os.listdir(px)):
            p = os.path.join(px, fn)
            if not fn.endswith('.json'):
                continue
            stats['archivos'] += 1
            data = json.load(open(p))
            if not data.get('k'):
                continue
            sym = urllib.parse.unquote(fn[:-5])
            k0 = int(data['k'][0][0])
            old = data.get('f') or []
            t1 = int(old[-1][0]) if old else int(data['k'][-1][0]) + 86400_000
            if not os.path.exists(os.path.join(bk, fn)):
                shutil.copy2(p, os.path.join(bk, fn))
            key = (sym, k0, t1)
            if key not in memo:
                memo[key] = funding(sym, k0, t1)
            new = memo[key]
            if not new:
                stats['sin_funding'] += 1
                continue
            if len(new) > len(old):
                stats['arreglados'] += 1
            data['f'] = new
            json.dump(data, open(p, 'w'))
            if k0 < T2024:
                stats['pre2024'] += 1
                if new[0][0] - k0 > 2 * 86400_000:
                    stats['chequeo_falla'] += 1
                    print(f'  chequeo: {d} {sym} primer funding {(new[0][0] - k0) / 86400_000:.0f} días después de la vela')
        print(d, 'listo', dict(stats), flush=True)


if __name__ == '__main__':
    main()
