"""
backtest_p30_hora_europa.py — P30: ¿la hora del día de DE40 (lo único que pasó P29) vale en otros índices europeos y
en fechas que P29 nunca miró?

Criterio declarado ANTES de medir: docs/p30_hora_indices_europa_criterio.md.
READ-ONLY: sin MT5, sin la DB de AIdan. Lee .cache_p1/M15 e importa las funciones de P29 (tools/info_screen.py).

Uso:
    python tools/backtest_p30_hora_europa.py      # escribe docs/p30_hora_europa_resultado.json
"""
import json
import zlib
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.info_screen import (DISC, P1_DIR, cells_m15, f_bucket_mean, fwd_ret, ic,  # noqa: E402
                               load_p1)

OUT = os.path.join(ROOT, 'docs', 'p30_hora_europa_resultado.json')
H = 16
MAIN = ['STOXX50', 'F40']
DESC = ['STOXX50', 'F40', 'UK100']
PLACEBO = 200
BOOT = 2000
SEED = 20261109
MIN_N = 200


def de40_map():
    D = load_p1('DE40')
    t, c = D['t'], D['c']
    disc_end = int(c.size * DISC)
    hour = (t // 3600) % 24
    r = fwd_ret(c, H)
    f = f_bucket_mean(hour, r, disc_end)
    hmap = {int(k): float(f[hour == k][0]) for k in np.unique(hour) if np.isfinite(f[hour == k][0])}
    vals = f[:disc_end][np.isfinite(f[:disc_end])]
    q20, q80 = np.percentile(vals, [20, 80])
    return hmap, float(q20), float(q80), int(t[0]), int(t[disc_end - 1])


def boot_ci(x, rng):
    bs = np.array([rng.choice(x, x.size).mean() for _ in range(BOOT)])
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def main_test(sym, hmap, q20, q80, t_end):
    r_all = np.load(os.path.join(P1_DIR, f'{sym}.npy'))
    with open(os.path.join(P1_DIR, f'{sym}.meta.json')) as fh:
        m = json.load(fh)
    w = r_all[r_all['time'].astype(np.int64) < t_end]
    t = w['time'].astype(np.int64)
    c = w['close'].astype(float)
    hour = (t // 3600) % 24
    idx = np.arange(0, c.size - H, H)
    f = np.array([hmap.get(int(h), np.nan) for h in hour[idx]])
    ok = np.isfinite(f)
    idx, f = idx[ok], f[ok]
    ret = c[idx + H] / c[idx] - 1.0
    px = float(np.median(c))
    spread = float(np.median(w['spread'])) * m['point'] / px
    nights = ((t[idx + H] // 86400) - (t[idx] // 86400)).astype(float)
    sw_l, sw_s = -m['swap_long'] / px, -m['swap_short'] / px          # costo por noche (positivo = paga)

    rng = np.random.default_rng(SEED ^ zlib.crc32(sym.encode()))
    ic_main = ic(f, ret)
    plac = [ic(np.roll(f, int(rng.integers(f.size // 10, 9 * f.size // 10))), ret) for _ in range(PLACEBO)]
    p95 = float(np.nanpercentile(plac, 95))

    s = np.where(f >= q80, 1.0, np.where(f <= q20, -1.0, 0.0))
    take = s != 0
    st, rt, nt = s[take], ret[take], nights[take]
    swap = np.where(st > 0, sw_l, sw_s) * nt
    net = st * rt - spread - swap
    net_noswap = st * rt - spread
    long_net = rt - spread - sw_l * nt
    excess = net - long_net
    out = dict(sym=sym, desde=str(np.datetime64(int(t[0]), 's')), hasta=str(np.datetime64(int(t[-1]), 's')),
               n=int(take.sum()), n_largos=int((st > 0).sum()), n_cortos=int((st < 0).sum()),
               ic=ic_main, placebo_p95=p95, costo_spread_bps=spread * 1e4,
               bruto_bps=float((st * rt).mean() * 1e4), swap_bps=float(swap.mean() * 1e4),
               neto_bps=float(net.mean() * 1e4), neto_ci=[x * 1e4 for x in boot_ci(net, rng)],
               neto_sin_swap_bps=float(net_noswap.mean() * 1e4),
               siempre_largo_bps=float(long_net.mean() * 1e4),
               exceso_bps=float(excess.mean() * 1e4), exceso_ci=[x * 1e4 for x in boot_ci(excess, rng)])
    half = take.sum() // 2
    out['neto_mitades_bps'] = [float(net[:half].mean() * 1e4), float(net[half:].mean() * 1e4)]
    out['c1'] = out['n'] >= MIN_N
    out['c2'] = bool(np.isfinite(ic_main) and ic_main > 0 and ic_main > p95)
    out['c3'] = out['neto_bps'] > 0
    out['c4'] = out['neto_ci'][0] > 0
    out['c5'] = out['exceso_bps'] > 0
    out['PASA'] = bool(out['c1'] and out['c2'] and out['c3'] and out['c4'] and out['c5'])
    return out


def top_bottom_hours(sym):
    P = load_p1(sym)
    t, c = P['t'], P['c']
    disc_end = int(c.size * DISC)
    hour = (t // 3600) % 24
    f = f_bucket_mean(hour, fwd_ret(c, H), disc_end)
    hm = {int(k): float(f[hour == k][0]) for k in np.unique(hour) if np.isfinite(f[hour == k][0])}
    ordered = sorted(hm, key=hm.get)
    k = max(1, len(ordered) // 5)
    return sorted(ordered[-k:]), sorted(ordered[:k])


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    hmap, q20, q80, t0, tde = de40_map()
    top = sorted(h for h, v in hmap.items() if v >= q80)
    bot = sorted(h for h, v in hmap.items() if v <= q20)
    print('=' * 100)
    print(f'P30 — mapa DE40 (descubrimiento hasta {np.datetime64(tde, "s")}): compra horas {top} · vende horas {bot}')
    print('=' * 100)
    res = [main_test(s, hmap, q20, q80, t0) for s in MAIN]
    for x in res:
        print(f"{x['sym']:8} {x['desde'][:10]}→{x['hasta'][:10]} n={x['n']} (L{x['n_largos']}/C{x['n_cortos']}) "
              f"IC {x['ic']:+.4f} (placebo95 {x['placebo_p95']:+.4f})")
        print(f"         bruto {x['bruto_bps']:+.2f} − spread {x['costo_spread_bps']:.2f} − swap {x['swap_bps']:.2f} "
              f"= neto {x['neto_bps']:+.2f} bps CI [{x['neto_ci'][0]:+.2f}, {x['neto_ci'][1]:+.2f}] · "
              f"sin swap {x['neto_sin_swap_bps']:+.2f} · mitades {x['neto_mitades_bps'][0]:+.2f}/"
              f"{x['neto_mitades_bps'][1]:+.2f}")
        print(f"         siempre largo {x['siempre_largo_bps']:+.2f} · exceso {x['exceso_bps']:+.2f} "
              f"CI [{x['exceso_ci'][0]:+.2f}, {x['exceso_ci'][1]:+.2f}]  "
              f"criterios {[x['c1'], x['c2'], x['c3'], x['c4'], x['c5']]} → {'PASA' if x['PASA'] else 'NO PASA'}")
    veredicto = all(x['PASA'] for x in res)
    print('-' * 100)
    print(f'VEREDICTO PRINCIPAL: {"PASA" if veredicto else "NO PASA"}')

    print('\nSecundario (descriptivo): P29 F1 con 70/30 propio')
    desc = []
    for s in DESC:
        rows = [r for r in cells_m15(load_p1(s)) if r['label'] == 'F1_hora']
        tb = top_bottom_hours(s)
        for r in rows:
            ci = r.get('net_ci', [np.nan, np.nan])
            print(f"  {s:8} h{r['h']:<3} n_res {r['n_res']:>6} IC {r['ic_disc']:+.4f}/{r['ic_res']:+.4f} "
                  f"(pl95 {r.get('placebo_p95', np.nan):.4f}) neto {r.get('net_bps', np.nan):+.2f} "
                  f"[{ci[0]:+.2f}, {ci[1]:+.2f}] {'PASA' if r['PASA'] else 'no'}")
        print(f"  {s:8} horas fuertes (h16) compra {tb[0]} · vende {tb[1]}")
        desc.append(dict(sym=s, celdas=rows, top=tb[0], bottom=tb[1]))
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(dict(criterio='docs/p30_hora_indices_europa_criterio.md', mapa_de40=hmap, top=top, bottom=bot,
                       principal=res, PASA=veredicto, secundario=desc), fh, indent=1, default=float)
    print(f'-> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
