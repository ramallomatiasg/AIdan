"""P57 — vault HLP de Hyperliquid contra la letra del Tesoro a 3 meses.

Criterio declarado antes de medir: docs/p57_vault_hlp_criterio.md (66ed51b).
Read-only: sin MT5, no toca la DB. Serie: .cache_p57/hlp_vaultDetails.json (API pública de HL, bajada el 18-nov);
letra: .cache_p50/dtb3.json (FRED DTB3).

  python tools/backtest_p57_vault_hlp.py              # descubrimiento (may-2023 → dic-2024)
  python tools/backtest_p57_vault_hlp.py --reserved   # 2025 →, solo si pasó
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC = os.path.join(ROOT, '.cache_p57', 'hlp_vaultDetails.json')
TB = os.path.join(ROOT, '.cache_p50', 'dtb3.json')
OUT = os.path.join(ROOT, 'docs', 'p57_vault_hlp_resultado.json')
COST = 0.01
SPLIT = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000
BLOCK, BOOT, SEED = 4, 5000, 20261118


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    port = dict(json.load(open(SRC))['portfolio'])['allTime']
    av = np.array([[t, float(v)] for t, v in port['accountValueHistory']])
    pnl = np.array([[t, float(v)] for t, v in port['pnlHistory']])
    assert np.array_equal(av[:, 0], pnl[:, 0])
    tb = json.load(open(TB))
    tbd = sorted(tb)
    rows = []
    for i in range(len(av) - 1):
        t0, t1 = av[i, 0], av[i + 1, 0]
        if av[i, 1] <= 0:
            continue
        days = (t1 - t0) / 864e5
        if days < 1:                           # el último punto es "ahora" (minutos después): no es un tramo
            continue
        r = (pnl[i + 1, 1] - pnl[i, 1]) / av[i, 1]
        d0 = dt.datetime.utcfromtimestamp(t0 / 1000).strftime('%Y-%m-%d')
        d1 = dt.datetime.utcfromtimestamp(t1 / 1000).strftime('%Y-%m-%d')
        bills = [tb[d] for d in tbd if d0 <= d <= d1] or [tb[max(d for d in tbd if d <= d0)]]
        bill = np.mean(bills) / 100
        rmid = (pnl[i + 1, 1] - pnl[i, 1]) / ((av[i, 1] + av[i + 1, 1]) / 2)   # descriptivo (agregado tras la 1ra corrida)
        rows.append(dict(t0=t0, d0=d0, days=days, r=r, rmid=rmid, bill=bill, prem=r - (bill + COST) * days / 365,
                         av=av[i, 1]))
    sel = [x for x in rows if (x['t0'] >= SPLIT) == a.reserved]
    r = np.array([x['r'] for x in sel]); prem = np.array([x['prem'] for x in sel]); days = np.array([x['days'] for x in sel])
    ann = float(prem.sum() / days.sum() * 365)
    ret_ann = float(r.sum() / days.sum() * 365)
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(prem.size / BLOCK))
    st = rng.integers(0, prem.size - BLOCK + 1, (BOOT, nb))
    idx = (st[:, :, None] + np.arange(BLOCK)).reshape(BOOT, -1)[:, :prem.size]
    bs = np.sort(prem[idx].sum(axis=1) / days[idx].sum(axis=1) * 365)
    lo, hi = float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])
    h = prem.size // 2
    h1 = float(prem[:h].sum() / days[:h].sum() * 365); h2 = float(prem[h:].sum() / days[h:].sum() * 365)
    idxv = np.cumprod(1 + r)
    dd = float(np.max(1 - idxv / np.maximum.accumulate(np.concatenate([[1.0], idxv]))[1:]))
    wi = int(np.argmin(r))
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    print(f"  {tag}: {sel[0]['d0']} → {sel[-1]['d0']}  n={r.size} tramos (~{days.mean():.0f} días)  letra media "
          f"{np.mean([x['bill'] for x in sel]):.2%}")
    print(f'  rendimiento {ret_ann:+.2%}/año  premio neto {ann:+.2%}/año  CI95 [{lo:+.2%}, {hi:+.2%}]  mitades '
          f'{h1:+.2%} / {h2:+.2%}')
    print(f"  caída máx de la cuota {dd:.2%}  peor tramo {r[wi]:+.2%} (desde {sel[wi]['d0']})  tramos negativos "
          f"{(r < 0).sum()}/{r.size}  vault medio ${np.mean([x['av'] for x in sel]) / 1e6:.0f} M")
    rm = np.array([x['rmid'] for x in sel])
    print(f'  descriptivo (no decide, agregado tras la 1ra corrida): con el valor PROMEDIO del tramo como denominador '
          f'(menos inflado por depósitos grandes) rendimiento {rm.sum() / days.sum() * 365:+.2%}/año, premio '
          f'{(rm.sum() / days.sum() - np.mean([x["bill"] for x in sel]) / 365 - COST / 365) * 365:+.2%}/año')
    yrs = {}
    for x in sel:
        yrs.setdefault(x['d0'][:4], [0, 0])
        yrs[x['d0'][:4]][0] += x['r']; yrs[x['d0'][:4]][1] += x['days']
    print('  por año (rendimiento): ' + '  '.join(f'{y} {v[0] / v[1] * 365:+.1%}' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'premio>0': ann > 0, 'caida_max<15%': dd < 0.15}
    else:
        crit = {'1_premio>0': ann > 0, '2_CI_inf>0': lo > 0, '3_dos_mitades>0': h1 > 0 and h2 > 0,
                '4_caida_max<15%': dd < 0.15, '5_peor_tramo>-10%': r.min() > -0.10}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P57 {tag}: {"PASA" if ok else "NO PASA"}')
    res = dict(n=int(r.size), rendimiento_anual=ret_ann, premio_anual=ann, ci=[lo, hi], mitades=[h1, h2],
               caida_max=dd, peor_tramo=[sel[wi]['d0'], float(r[wi])], por_anio={y: v[0] / v[1] * 365 for y, v in yrs.items()},
               criterios={k: bool(v) for k, v in crit.items()}, PASA=ok, criterio='docs/p57_vault_hlp_criterio.md (66ed51b)')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(res, open(path, 'w'), indent=1, default=float)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
