"""
backtest_p31_vol_cost.py — P31: ¿el movimiento esperado al entrar (rango medio de las 16 velas M15 previas) separa
los trades de AIdan que ganan de los que pierden?

Criterio declarado ANTES de medir: docs/p31_vol_costo_criterio.md. Leer contra eso.
READ-ONLY: DB de producción `mode=ro`, sin MT5 (velas del cache M1 de P23 vía las funciones de P27, importadas).

Uso:
    python tools/backtest_p31_vol_cost.py
"""
import datetime as dt
import json
import os
import sqlite3
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools import backtest_p27_llm_judge as p27  # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'p31_vol_costo_resultado.json')
START_AR = '2026-04-20'
SEED = 20261104
BOOT = 5000
PERM = 500


def load_trades():
    c = sqlite3.connect(f'file:{p27.PROD_DB}?mode=ro', uri=True)
    rows = c.execute("SELECT strategy_id, trigger_type, created_at, mt5_pnl FROM trade_archive "
                     "WHERE mt5_pnl IS NOT NULL AND created_at >= ? AND created_at < ? ORDER BY created_at",
                     (START_AR, p27.CUTOFF_AR)).fetchall()
    c.close()
    out = []
    for sid, trig, ca, pnl in rows:
        t = int((dt.datetime.fromisoformat(ca) + dt.timedelta(hours=p27.AR_TO_SERVER_H))
                .replace(tzinfo=dt.timezone.utc).timestamp())
        out.append(dict(sid=sid, track=trig, t=t, pnl=float(pnl)))
    return out


def expected_move(M, t, n=16):
    """Rango medio (pips) de las n velas M15 cerradas antes de t. None si faltan datos."""
    b = p27.bars_before(M, t, 900, n)
    if len(b) < n:
        return None
    return float(np.mean([h - l for _, o, h, l, c in b])) / p27.PIP


def diff_ci(low, rest, rng):
    bs = [rng.choice(low, low.size).mean() - rng.choice(rest, rest.size).mean() for _ in range(BOOT)]
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    M = p27.load_m1()
    trades = []
    for x in load_trades():
        v = expected_move(M, x['t'])
        if v is not None:
            trades.append(dict(x, move=v))
    n = len(trades)
    half = n // 2
    fit, test = trades[:half], trades[half:]
    cut = float(np.percentile([x['move'] for x in fit], 100 / 3))
    rng = np.random.default_rng(SEED)

    def split(rows):
        low = np.array([x['pnl'] for x in rows if x['move'] <= cut])
        rest = np.array([x['pnl'] for x in rows if x['move'] > cut])
        return low, rest

    lo1, re1 = split(fit)
    lo2, re2 = split(test)
    d1 = lo1.mean() - re1.mean()
    d2 = lo2.mean() - re2.mean()
    ci2 = diff_ci(lo2, re2, rng)
    pnl2 = np.array([x['pnl'] for x in test])
    mv2 = np.array([x['move'] for x in test])
    perm = []
    for _ in range(PERM):
        m = rng.permutation(mv2) <= cut
        perm.append(pnl2[m].mean() - pnl2[~m].mean())
    p5 = float(np.percentile(perm, 5))

    print('=' * 92)
    print('P31 — movimiento esperado al entrar (rango medio 16 velas M15) vs resultado real de AIdan')
    print('=' * 92)
    print(f'  trades con velas: {n} · corte del tercio bajo (1ra mitad): {cut:.2f} pips')
    print(f'  1ra mitad: bajo n={lo1.size} {lo1.mean():+.2f}$/trade · resto n={re1.size} {re1.mean():+.2f} · dif {d1:+.2f}')
    print(f'  2da mitad: bajo n={lo2.size} {lo2.mean():+.2f}$/trade · resto n={re2.size} {re2.mean():+.2f} · dif {d2:+.2f}'
          f' CI [{ci2[0]:+.2f}, {ci2[1]:+.2f}] · placebo p5 {p5:+.2f}')
    print(f'  2da mitad total: todo ${pnl2.sum():+.2f} · sin el tercio bajo ${re2.sum():+.2f}')
    print('  [desc] por track (2da mitad):')
    for tr in sorted({x['track'] for x in test}):
        lo = [x['pnl'] for x in test if x['track'] == tr and x['move'] <= cut]
        re_ = [x['pnl'] for x in test if x['track'] == tr and x['move'] > cut]
        print(f"    {tr:14} bajo n={len(lo):3} {np.mean(lo) if lo else float('nan'):+.2f} · "
              f"resto n={len(re_):3} {np.mean(re_) if re_ else float('nan'):+.2f}")
    crit = {
        '1_n_2da>=300': len(test) >= 300,
        '2_bajo<resto_CI_sup<0': ci2[1] < 0,
        '3_misma_direccion_1ra': d1 < 0,
        '4_bajo_pierde': lo2.mean() < 0,
        '5_debajo_placebo_p5': d2 < p5,
    }
    for k, v in crit.items():
        print(f"    [{'OK ' if v else 'NO '}] {k}")
    ok = all(crit.values())
    print(f"  >>> {'PASA' if ok else 'NO PASA'}")
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(dict(criterio='docs/p31_vol_costo_criterio.md', n=n, corte_pips=cut, dif_1ra=d1, dif_2da=d2,
                       ci_2da=ci2, placebo_p5=p5, criterios=crit, PASA=ok), f, indent=1, default=float)


if __name__ == '__main__':
    main()
