"""
fase6_audit_export.py — arma los datos de la AUDITORÍA VISUAL del Setup 1 de Leo (Fase 6).

READ-ONLY (cache `.cache_fase2/M5_500000`). Pregunta que responde: ¿la máquina elige los mismos trades
que Leo? Para eso Leo revisa 20 trades que eligió la máquina (10 ganadores y 10 perdedores de los
últimos 12 meses, sin ver el resultado) y, antes, hace una prueba a ciegas en una ventana de EURUSD.

Salidas:
  - `--out` (JSON para la página): velas M15 y M5 HASTA la entrada (nada del futuro), zona, entrada,
    stop, objetivo, nivel del CHoCH. NO incluye el resultado del trade.
  - `.cache_fase2/fase6_audit_key.json` (privado, fuera de git): resultado de cada tarjeta y los trades
    de la máquina dentro de la ventana ciega, para puntuar las respuestas de Leo.

Selección fija (semilla 20260929): primero pares mayores, 10 ganadores + 10 perdedores; se excluye la
ventana ciega.
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

import tools.backtest_fase6_leo_smc as f6  # noqa: E402
from tools.backtest_fase4_planes import us_dst  # noqa: E402

MAJORS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY']
CUT_FROM = datetime(2025, 8, 18)                       # últimos 12 meses del cache
BLIND_PAIR = 'EURUSD'
BLIND_FROM, BLIND_TO = datetime(2026, 7, 27), datetime(2026, 8, 8)   # hora Argentina, [desde, hasta)
KEY = os.path.join(ROOT, '.cache_fase2', 'fase6_audit_key.json')
M15_MAX, M5_MAX = 170, 110


def server_to_ar(ts):
    """epoch del server (hora del server tratada como UTC) -> datetime naive en hora Argentina."""
    dt = datetime.fromtimestamp(int(ts), timezone.utc).replace(tzinfo=None)
    utc = dt - timedelta(hours=3 if us_dst(dt) else 2)
    return utc - timedelta(hours=3)


def ar_epoch(ts):
    return int((server_to_ar(ts) - datetime(1970, 1, 1)).total_seconds())


def bars(o, h, l, c, t, a, b, dec):
    return {'t': [ar_epoch(x) for x in t[a:b + 1]],
            'o': [round(float(x), dec) for x in o[a:b + 1]], 'h': [round(float(x), dec) for x in h[a:b + 1]],
            'l': [round(float(x), dec) for x in l[a:b + 1]], 'c': [round(float(x), dec) for x in c[a:b + 1]]}


def card_for(sym, d):
    r, spec = f6.load(sym)
    pip = spec['pip']; dec = 3 if pip == 0.01 else 5
    t = r['time'].astype(np.int64)
    o, h, l, c = (r[k].astype(np.float64) for k in ('open', 'high', 'low', 'close'))
    B15 = f6.resample(t, o, h, l, c, 900)
    j = d['j15']
    # barra del extremo: la M15 cuyo máximo (venta) / mínimo (compra) es el borde de la zona
    ext_j = j
    for k in range(j, max(-1, j - 2000), -1):
        if (d['D'] == -1 and abs(B15['h'][k] - d['zh']) < 1e-9) or (d['D'] == 1 and abs(B15['l'][k] - d['zl']) < 1e-9):
            ext_j = k; break
    a15 = max(0, min(ext_j - 20, j - 120), j - 220)   # >=120 velas de contexto, el extremo visible si entra
    t15 = B15['end'] - 900
    m15 = bars(B15['o'], B15['h'], B15['l'], B15['c'], t15, a15, j, dec)
    a5 = max(d['i'] - M5_MAX, d['touch_i'] - 30, 0)
    m5 = bars(o, h, l, c, t, a5, d['i'], dec)
    when = server_to_ar(t[d['i']] + 300)                 # la entrada es al CIERRE de la vela M5
    return {
        'pair': sym, 'dir': 'venta' if d['D'] == -1 else 'compra', 'when': when.strftime('%Y-%m-%d %H:%M'),
        'dec': dec, 'pip': pip,
        'zone': [round(d['zl'], dec), round(d['zh'], dec)], 'entry': round(d['E'], dec),
        'stop': round(d['S'], dec), 'target': round(d['T'], dec), 'choch': round(d['choch'], dec),
        'sl_pips': round(d['sl_p'], 1), 'tp_pips': round(d['tp_p'], 1),
        'ext_t': ar_epoch(t15[ext_j]), 'touch_t': ar_epoch(t[d['touch_i']]),
        'm15': m15, 'm5': m5,
    }, {'pair': sym, 'when': when.strftime('%Y-%m-%d %H:%M'), 'dir': d['D'], 'net_pips': round(d['net'], 2),
        'gross_pips': round(d['gross'], 2), 'sl_pips': round(d['sl_p'], 1), 'tp_pips': round(d['tp_p'], 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    pool_w, pool_l, blind = [], [], []
    for sym in MAJORS:
        _, res, _, _ = f6.run_pair((sym, False, True))
        r, _ = f6.load(sym)
        t = r['time']
        for d in res['_detail']:
            w = server_to_ar(t[d['i']] + 300)
            if sym == BLIND_PAIR and BLIND_FROM <= w < BLIND_TO:
                blind.append({'when': w.strftime('%Y-%m-%d %H:%M'), 'dir': d['D'], 'entry': d['E'],
                              'net_pips': round(d['net'], 2)})
                continue
            if w < CUT_FROM:
                continue
            (pool_w if d['net'] > 0 else pool_l).append((sym, d))
    rng = random.Random(20260929)

    def pick(pool, k):
        # reparte entre pares: primero uno por par (orden de MAJORS), después al azar
        by = {}
        for s, d in pool:
            by.setdefault(s, []).append((s, d))
        out = []
        for s in MAJORS:
            if s in by and len(out) < k:
                out.append(by[s].pop(rng.randrange(len(by[s]))))
        rest = [x for v in by.values() for x in v]
        rng.shuffle(rest)
        return out + rest[:k - len(out)]

    chosen = pick(pool_w, 10) + pick(pool_l, 10)
    rng.shuffle(chosen)
    cards, key = [], []
    for n, (sym, d) in enumerate(chosen, 1):
        cd, ky = card_for(sym, d)
        cd['id'] = n; ky['id'] = n
        cards.append(cd); key.append(ky)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump({'blind': {'pair': BLIND_PAIR, 'from': BLIND_FROM.strftime('%Y-%m-%d'),
                             'to': (BLIND_TO - timedelta(days=1)).strftime('%Y-%m-%d')}, 'cards': cards},
                  f, separators=(',', ':'))
    with open(KEY, 'w', encoding='utf-8') as f:
        json.dump({'cards': key, 'blind_machine_trades': blind}, f, indent=2)
    print(f'{len(cards)} tarjetas ({sum(1 for k in key if k["net_pips"] > 0)} ganadoras) · '
          f'máquina en la ventana ciega: {len(blind)} trades · clave: {KEY}')
    for k in key:
        print(f"  #{k['id']:2} {k['pair']} {k['when']} {'V' if k['dir'] == -1 else 'C'} SL {k['sl_pips']} TP {k['tp_pips']}")


if __name__ == '__main__':
    main()
