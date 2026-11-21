"""P63 — comisiones de protocolos DeFi → retorno semanal de su token (largo más crecimiento, corto menos).

Criterio declarado antes de medir: docs/p63_fees_defi_criterio.md (60478bc).
Read-only: sin MT5, no toca la DB. Fuentes públicas (Binance, DefiLlama) a .cache_p63/.
Reusa del tool de P59 (importado, no copiado): descarga de precios/funding, cartera, bootstrap.

  python tools/backtest_p63_fees_defi.py --map     # solo arma el mapeo moneda → protocolo
  python tools/backtest_p63_fees_defi.py           # descubrimiento 2020-2023
  python tools/backtest_p63_fees_defi.py --reserved
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import backtest_p59_wikipedia_atencion as p59  # noqa: E402

ROOT = p59.ROOT
C = os.path.join(ROOT, '.cache_p63')
FE = os.path.join(C, 'fees')
p59.PX = os.path.join(C, 'px')
OUT = os.path.join(ROOT, 'docs', 'p63_fees_defi_resultado.json')
MIN_F, DAY = 50_000, 86400
MOZ = {'User-Agent': 'Mozilla/5.0'}


def build_map():
    os.makedirs(C, exist_ok=True)
    ei = p59._get('https://fapi.binance.com/fapi/v1/exchangeInfo', MOZ)
    syms = {x['symbol'] for x in ei['symbols'] if x['contractType'] == 'PERPETUAL' and x['quoteAsset'] == 'USDT'
            and x.get('underlyingType', 'COIN') == 'COIN'}
    s3 = json.load(open(os.path.join(ROOT, '.cache_p56', 's3_symbols.json')))
    syms |= {s for s in s3 if s.endswith('USDT')}
    prot = p59._get('https://api.llama.fi/protocols', MOZ)
    groups = {}
    for q in prot:
        sy = (q.get('symbol') or '').upper()
        if not sy or sy == '-':
            continue
        g = (q.get('parentProtocol') or '').replace('parent#', '') or q['slug']
        groups.setdefault(sy, set()).add(g)
    mp, amb = {}, {}
    for s in sorted(syms):
        b = p59.base_of(s)
        gs = groups.get(b)
        if not gs:
            continue
        if len(gs) == 1:
            mp[s] = next(iter(gs))
        else:
            amb[s] = sorted(gs)
    # dos símbolos (p. ej. XUSDT y 1000XUSDT) al mismo grupo: se queda el que tenga más historia más abajo; acá se
    # excluyen los dos, como P59 hace con artículos compartidos
    inv = {}
    for s, g in mp.items():
        inv.setdefault(g, []).append(s)
    dup = {g: v for g, v in inv.items() if len(v) > 1}
    mp = {s: g for s, g in mp.items() if g not in dup}
    json.dump(dict(map=mp, ambiguos=amb, compartidos=dup, n_simbolos=len(syms)),
              open(os.path.join(C, 'mapping.json'), 'w'), indent=1)
    print(f'mapeo: {len(mp)} monedas con un solo protocolo ({len(amb)} ambiguas, {len(dup)} grupos compartidos) '
          f'de {len(syms)} símbolos')


def fees(g):
    os.makedirs(FE, exist_ok=True)
    p = os.path.join(FE, g + '.json')
    if os.path.exists(p):
        return json.load(open(p))
    r = p59._get(f'https://api.llama.fi/summary/fees/{g}?dataType=dailyFees', MOZ)
    out = {str(int(t)): float(v) for t, v in ((r or {}).get('totalDataChart') or [])}
    json.dump(out, open(p, 'w')); time.sleep(0.3)
    return out


def panel(mp, weeks):
    sig, ret = {}, {}
    for s, g in mp.items():
        f = fees(g)
        if not f:
            continue
        fd = {dt.datetime.fromtimestamp(int(t), dt.timezone.utc).date(): v for t, v in f.items()}
        px = p59.prices(s)
        if not px['k']:
            continue
        ts = np.array([x[0] for x in px['k']]); o = np.array([x[1] for x in px['k']]); vol = np.array([x[2] for x in px['k']])
        ft = np.array([x[0] for x in px['f']], dtype=np.int64); fr = np.array([x[1] for x in px['f']])
        first = ts[0]
        sg, rt = {}, {}
        for w in weeks:
            f4 = sum(fd.get(w - dt.timedelta(days=i), 0.0) for i in range(1, 29))
            f4p = sum(fd.get(w - dt.timedelta(days=i), 0.0) for i in range(29, 57))
            a, b = p59.ms(w), p59.ms(w + dt.timedelta(days=7))
            if f4p < MIN_F or f4 <= 0 or a - first < p59.MIN_AGE * p59.DAY:
                continue
            ia = np.searchsorted(ts, a)
            if ia >= ts.size or ts[ia] != a or vol[ia] <= 0:
                continue
            ib = np.searchsorted(ts, b)
            if ib >= ts.size or ts[ib] != b or vol[ib] <= 0:
                live = np.flatnonzero((ts > a) & (ts < b) & (vol > 0))
                if live.size == 0:
                    continue
                ib = live[-1]
            fu = fr[np.searchsorted(ft, ts[ia], side='right'):np.searchsorted(ft, ts[ib], side='right')].sum()
            # p59.run pone LARGO las de señal más BAJA ⇒ se pasa la señal con el signo invertido (largo = más crecimiento)
            sg[w] = -float(np.log(f4 / f4p)); rt[w] = float(o[ib] / o[ia] - 1 - fu)
        if sg:
            sig[s], ret[s] = sg, rt
    return sig, ret


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', action='store_true')
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    mpf = os.path.join(C, 'mapping.json')
    if a.map or not os.path.exists(mpf):
        build_map()
        if a.map:
            return
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    mp = json.load(open(mpf))['map']
    lo_d, hi_d = (p59.SPLIT, p59.DEND) if a.reserved else (p59.D0, p59.SPLIT - dt.timedelta(days=7))
    weeks = [lo_d + dt.timedelta(days=7 * i) for i in range((hi_d - lo_d).days // 7 + 1)]
    sig, ret = panel(mp, weeks)
    net, gross, wk, info = p59.run(sig, ret, weeks, p59.COST)
    if net.size == 0:
        sys.exit('0 semanas con cartera (nunca hubo >=10 monedas elegibles).')
    netp, _, _, _ = p59.run(sig, ret, weeks, p59.PESS)
    rng = np.random.default_rng(20261121)
    lo, hi = p59.block_ci(net, rng)
    h = net.size // 2
    plac, wi = [], {w: i for i, w in enumerate(weeks)}
    for _ in range(p59.NPLAC):
        ps = {}
        for s, sg in sig.items():
            sh = int(rng.integers(26, max(27, len(weeks) - 26)))
            vals = [sg.get(w) for w in weeks]
            ps[s] = {w: vals[(wi[w] + sh) % len(weeks)] for w in sg if vals[(wi[w] + sh) % len(weeks)] is not None}
        _, g, _, _ = p59.run(ps, ret, weeks, 0)
        plac.append(g.mean() if g.size else np.nan)
    plac = np.array(plac); p95 = float(np.nanpercentile(plac, 95))
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    rl = np.array([x[0] for x in info]); rs = np.array([x[1] for x in info]); nn = np.array([x[2] for x in info])
    print(f'== P63 {tag}: {len(mp)} monedas mapeadas, {len(sig)} con comisiones y precio; {net.size} semanas con cartera '
          f'(elegibles media {nn.mean():.0f}, desde {wk[0]})')
    print(f'  neto {net.mean():+.3%}/semana (≈{net.mean() * 52:+.1%}/año)  CI95 bloques [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {net[:h].mean():+.3%} / {net[h:].mean():+.3%}  pesimista {netp.mean():+.3%}')
    print(f'  bruto {gross.mean():+.3%}  placebo media {np.nanmean(plac):+.3%} p95 {p95:+.3%}  '
          f'pata larga {rl.mean():+.3%}  pata corta {rs.mean():+.3%}')
    yrs = {}
    for w, x in zip(wk, net):
        yrs.setdefault(w.year, []).append(x)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%} (n={len(v)})' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': net.mean() > 0 and lo > 0, '5_le_gana_al_placebo': gross.mean() > p95}
    else:
        crit = {'1_semanas>=100': net.size >= 100, '2_neto>0_y_CI_inf>0': net.mean() > 0 and lo > 0,
                '3_dos_mitades>0': net[:h].mean() > 0 and net[h:].mean() > 0, '4_pesimista>0': netp.mean() > 0,
                '5_le_gana_al_placebo': gross.mean() > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P63 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(semanas=int(net.size), monedas=len(sig), neto_semanal=float(net.mean()), ci=[lo, hi],
               mitades=[float(net[:h].mean()), float(net[h:].mean())], pesimista=float(netp.mean()),
               bruto=float(gross.mean()), placebo_p95=p95, pata_larga=float(rl.mean()), pata_corta=float(rs.mean()),
               criterios={k: bool(v) for k, v in crit.items()}, PASA=ok, criterio='docs/p63_fees_defi_criterio.md (60478bc)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
