"""P75 — cambio semanal del GDPNow (Fed de Atlanta) -> IEF la semana siguiente.

Si el nowcast del trimestre subió del jueves previo a este jueves => corto IEF del cierre del viernes al del viernes
siguiente; si bajó => largo. Criterio declarado antes de medir: docs/p75_gdpnow_bonos_criterio.md (335ac41).
Read-only: sin MT5, no toca la DB. Datos: .cache_p75/gdpnow.xlsx (TrackingDeepArchives 2011-14 + TrackingArchives
2014 ->) y el IEF ajustado de .cache_p64/IEF.json.

  python tools/backtest_p75_gdpnow_bonos.py              # 2011 -> 2019
  python tools/backtest_p75_gdpnow_bonos.py --reserved   # 2020 -> hoy, solo si pasó
"""
import argparse
import bisect
import datetime as dt
import json
import os
import sys

import numpy as np
import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
XLSX = os.path.join(ROOT, '.cache_p75', 'gdpnow.xlsx')
IEF = os.path.join(ROOT, '.cache_p64', 'IEF.json')
OUT = os.path.join(ROOT, 'docs', 'p75_gdpnow_bonos_resultado.json')
COST, PESS = 0.0005, 0.0010
BOOT, SEED, NPLAC = 5000, 20261125, 200
DISC_END = dt.date(2019, 12, 27)


def load_nowcasts():
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    rows = []
    for name in ('TrackingDeepArchives', 'TrackingArchives'):
        it = wb[name].iter_rows(values_only=True)
        hdr = list(next(it))
        ig = hdr.index('GDP Nowcast')
        for r in it:
            if r[0] is None or r[ig] is None:
                continue
            rows.append((r[0].date(), r[1].date(), float(r[ig])))
    rows.sort()
    return rows


def nowcast_fn(rows):
    dates = [r[0] for r in rows]
    by_q = {}
    for d, q, v in rows:
        by_q.setdefault(q, []).append((d, v))

    def last(d):
        i = bisect.bisect_right(dates, d) - 1
        return rows[i] if i >= 0 else None

    def nq(d, q):
        L = by_q.get(q, [])
        i = bisect.bisect_right([x[0] for x in L], d) - 1
        return L[i][1] if i >= 0 else None
    return last, nq


def weeks(px):
    days = sorted(dt.date.fromisoformat(k) for k in px)
    wk = {}
    for d in days:
        wk[d.isocalendar()[:2]] = d       # último día hábil de la semana
    return sorted(wk.values())


def block_ci(x, rng, b=4):
    nb = int(np.ceil(x.size / b)); st = np.arange(0, x.size - b + 1)
    bs = np.array([x[np.concatenate([np.arange(s, s + b) for s in rng.choice(st, nb)])[:x.size]].mean()
                   for _ in range(BOOT)])
    bs.sort()
    return float(bs[int(.025 * BOOT)]), float(bs[int(.975 * BOOT)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reserved', action='store_true')
    a = ap.parse_args()
    if a.reserved:
        prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
        if not prev.get('PASA'):
            sys.exit('El descubrimiento no pasó (o no se corrió): la reserva no se mira.')
    rows = load_nowcasts()
    last, nq = nowcast_fn(rows)
    px = json.load(open(IEF))
    fr = weeks(px)
    first_nc, last_nc = rows[0][0], rows[-1][0]
    sigs = []                                     # (F, F_next, signal, ret)
    for F, Fn in zip(fr[:-1], fr[1:]):
        thu = F - dt.timedelta(days=F.weekday() - 3)
        if F <= thu:
            thu = F - dt.timedelta(days=1)
        thu_prev = thu - dt.timedelta(days=7)
        if thu_prev < first_nc or thu > last_nc + dt.timedelta(days=7):
            continue
        lr = last(thu)
        if lr is None:
            continue
        q = lr[1]
        a_, b_ = nq(thu, q), nq(thu_prev, q)
        if a_ is None or b_ is None:
            sig = 0.0
        else:
            sig = a_ - b_
        r = px[Fn.isoformat()] / px[F.isoformat()] - 1
        sigs.append((F, Fn, sig, r))
    if a.reserved:
        sel = [s for s in sigs if s[0] > DISC_END]
    else:
        sel = [s for s in sigs if s[0] <= DISC_END]
    pos = np.array([-np.sign(s[2]) for s in sel])
    ret = np.array([s[3] for s in sel])
    prevpos = np.concatenate([[0.0], pos[:-1]])
    tv = np.abs(pos - prevpos)
    g_all = pos * ret
    m = pos != 0
    g = g_all[m]; ex = (g_all - COST * tv)[m]; exp_ = (g_all - PESS * tv)[m]
    rng = np.random.default_rng(SEED)
    lo, hi = block_ci(ex, rng)
    h = ex.size // 2
    sv = np.array([s[2] for s in sel]); nz = np.flatnonzero(sv != 0)
    plac = np.empty(NPLAC)
    for k in range(NPLAC):
        pp = -np.sign(sv[rng.choice(nz, nz.size)])
        plac[k] = (pp * ret[nz]).mean()
    p95 = float(np.percentile(plac, 95))
    eq = np.cumprod(1 + ex); dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    tag = 'RESERVA' if a.reserved else 'DESCUBRIMIENTO'
    d0, d1 = sel[0][0], sel[-1][0]
    print(f'== P75 GDPNow -> IEF {tag}: {m.sum()} semanas con posición de {len(sel)} ({d0} -> {d1})')
    print(f'  neto {ex.mean():+.3%}/semana (~{ex.mean() * 52:+.1%}/año)  CI95 bloques [{lo:+.3%}, {hi:+.3%}]  '
          f'mitades {ex[:h].mean():+.3%} / {ex[h:].mean():+.3%}  pesimista {exp_.mean():+.3%}')
    print(f'  bruto {g.mean():+.3%}  placebo media {plac.mean():+.3%} p95 {p95:+.3%}  acierto {(g > 0).mean():.1%}  '
          f'caída máx {dd:+.1%}')
    pm = pos[m]
    print(f'  largos n={int((pm > 0).sum())} bruto {g[pm > 0].mean():+.3%} | cortos n={int((pm < 0).sum())} '
          f'bruto {g[pm < 0].mean():+.3%} | IEF siempre largo {ret.mean():+.3%}/semana')
    live = [(s, x) for s, x in zip(np.array(sel, dtype=object)[m], ex) if s[0] >= dt.date(2014, 7, 1)]
    if live:
        lv = np.array([x for _, x in live])
        print(f'  desc.: solo en vivo (2014-07 ->): n={lv.size} neto {lv.mean():+.3%}')
    yrs = {}
    for s, x in zip(np.array(sel, dtype=object)[m], ex):
        yrs.setdefault(s[0].year, []).append(x)
    print('  por año: ' + '  '.join(f'{y} {np.mean(v):+.2%}' for y, v in sorted(yrs.items())))
    if a.reserved:
        crit = {'2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0, '5_bruto>placebo_p95': g.mean() > p95}
    else:
        crit = {'1_semanas>=150': ex.size >= 150, '2_neto>0_y_CI_inf>0': ex.mean() > 0 and lo > 0,
                '3_dos_mitades>0': ex[:h].mean() > 0 and ex[h:].mean() > 0, '4_pesimista>0': exp_.mean() > 0,
                '5_bruto>placebo_p95': g.mean() > p95}
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = bool(all(crit.values()))
    print(f'  >>> P75 {tag}: {"PASA" if ok else "NO PASA"}')
    path = OUT.replace('.json', '_reserva.json') if a.reserved else OUT
    json.dump(dict(semanas=int(ex.size), neto=float(ex.mean()), ci=[lo, hi], mitades=[float(ex[:h].mean()),
                   float(ex[h:].mean())], pesimista=float(exp_.mean()), bruto=float(g.mean()), placebo_p95=p95,
                   criterios={k: bool(v) for k, v in crit.items()}, PASA=ok,
                   criterio='docs/p75_gdpnow_bonos_criterio.md (335ac41)'), open(path, 'w'), indent=1)
    print(f'-> {os.path.relpath(path, ROOT)}')


if __name__ == '__main__':
    main()
