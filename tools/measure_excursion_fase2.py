# -*- coding: utf-8 -*-
"""
measure_excursion_fase2.py — ¿que hace el precio DESPUES de una senal?

READ-ONLY. Reusa el cache de velas de backtest_fase2.py. No toca produccion.

═══ POR QUE EXISTE ═══════════════════════════════════════════════════════════

Fase 2 midio que el detector es PEOR que el azar (~-0,1 pips/trade) en M5 y M15,
26M de operaciones. La explicacion mecanica propuesta: entra despues de que el
movimiento ya paso (exige cierre confirmado + 0,3-7p de extension) y a ese
horizonte el precio revierte => compra el extremo local.

Esto NO mide si gana. Mide la FORMA: que hace el precio en las velas siguientes.
De eso depende si el "pullback-entry" (el hilo abierto desde el 19-jun) vale la
pena construirse o esta muerto antes de empezar.

═══ QUE MIDE ════════════════════════════════════════════════════════════════

Por cada senal, a horizontes de 1,2,3,6,12,24,48 velas:
  fav   = maxima excursion FAVORABLE (a favor de la direccion de la senal)
  adv   = maxima excursion ADVERSA
  close = movimiento neto al cierre de ese horizonte

Y lo mismo para ENTRADAS ALEATORIAS con el mismo n por simbolo y el mismo ratio
long/short. Sin el control, "adv 5p / fav 4p" no significa nada: toda entrada
tiene las dos. Lo informativo es detector-menos-azar al mismo horizonte.

TODO en pips reales (los JPY se re-escalan solo para el detector, igual que en
backtest_fase2.py; las excursiones se calculan sobre las velas REALES).

═══ CRITERIO DE LECTURA, DECLARADO ANTES DE CORRER ═══════════════════════════

  CONFIRMA retroceso-y-continuacion:
      close(detector) < close(azar) en horizontes cortos
      Y close(detector) > close(azar) en ALGUN horizonte largo (cruce).
      => el cruce dice cuantas velas esperar para el pullback.

  REFUTA el pullback antes de construirlo:
      close(detector) <= close(azar) en TODOS los horizontes.
      => no hay continuacion que capturar.

Nota: esto es DESCRIPTIVO, no un test de pasa/no-pasa. No habilita a operar nada.
Sin costos: se mide movimiento de precio, no P&L (los costos son constantes y no
cambian la FORMA de la curva).

Uso:
    python tools/measure_excursion_fase2.py --tf M5 --profile m5live --workers 14
"""
import argparse
import json
import os
import random
import sys
import time
from copy import deepcopy
from multiprocessing import Pool
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from tools.backtest_h4_d1 import SESSIONS, load_live_params, setup_logger  # noqa: E402
from tools.backtest_fase2 import (  # noqa: E402
    PROFILES_F2, DEDUP_SEC, WARMUP, load_symbol, set_low_priority,
)

# v2 (18-ago, EXPLORATORIO — declarado como tal): el smoke sobre EURUSD mostro que
# el close del detector NO cruza al azar en ningun horizonte (=> pullback REFUTADO
# por el criterio pre-declarado) pero que empeora MONOTONAMENTE: -0,03 a 1 vela y
# -0,23 a 48. Se extienden los horizontes para responder una pregunta NUEVA, que no
# es parte del test declarado: ¿el anti-edge sigue creciendo, y llega a superar los
# ~0,9 pips de costo? A 48 velas vale 0,23; harian falta ~4x mas.
HORIZONS = [1, 2, 3, 6, 12, 24, 48, 96, 192, 384]
CONTROL_REPS = 5         # con n~200k senales por simbolo la media ya es precisa;
                         # aca se mide una FORMA, no se necesita un p-value


def excursion(candles, i, direction, pip, horizons):
    """fav/adv/close a cada horizonte, en pips reales, sin lookahead antes de i."""
    entry = candles[i]['close']
    out = {}
    hh = ll = None
    j = i + 1
    for H in horizons:
        end = min(i + H, len(candles) - 1)
        while j <= end:
            c = candles[j]
            hh = c['high'] if hh is None else max(hh, c['high'])
            ll = c['low'] if ll is None else min(ll, c['low'])
            j += 1
        if hh is None or end <= i:
            continue
        if direction == 'CALL':
            fav, adv = (hh - entry) / pip, (entry - ll) / pip
            clo = (candles[end]['close'] - entry) / pip
        else:
            fav, adv = (entry - ll) / pip, (hh - entry) / pip
            clo = (entry - candles[end]['close']) / pip
        out[H] = (fav, adv, clo)
    return out


def run_symbol(job):
    sym, session, cache_dir, params, profile_key, tf, low_prio = job
    if low_prio:
        set_low_priority()
    t0 = time.perf_counter()
    profile = PROFILES_F2[profile_key]

    import logging
    logging.disable(logging.CRITICAL)
    logger = logging.getLogger('exc')

    candles, spec = load_symbol(sym, cache_dir)
    pip = spec['pip']

    from src.analyzer.technical import TechnicalAnalyzer
    import src.analyzer.technical as tech_mod

    import src.common.db as _dbmod
    _snap = _dbmod.get_setup_win_rates()
    _dbmod.get_setup_win_rates = lambda: _snap

    class _FakeTuner:
        def __init__(self, *a, **k):
            pass

        def get_params(self):
            return dict(params)

    _fixed = dict(SESSIONS[session])
    session_patch = patch.object(TechnicalAnalyzer, 'get_session_info',
                                 staticmethod(lambda: dict(_fixed)))
    analyzer = TechnicalAnalyzer(logger)
    analyzer._cache_ttl = 0
    analyzer._dedup_window_sec = DEDUP_SEC[tf]
    escala = 0.0001 / pip

    # acumuladores: suma y n por horizonte
    det = {H: [0.0, 0.0, 0.0, 0] for H in HORIZONS}
    entries = []          # (idx, direction) para el control
    n_long = 0

    for i in range(WARMUP, len(candles) - 1):
        sl_ = candles[max(0, i - WARMUP + 1):i + 1]
        if escala != 1.0:
            sl_ = [{**c, 'open': c['open'] * escala, 'high': c['high'] * escala,
                    'low': c['low'] * escala, 'close': c['close'] * escala}
                   for c in sl_]
        analyzer._fetch_candles = lambda s=sl_: deepcopy(s)
        analyzer._cache.clear()
        try:
            with patch('src.optimizer.auto_tuner.AutoTuner', _FakeTuner), \
                 patch.object(tech_mod.time, 'time',
                              return_value=candles[i]['time_unix']), \
                 session_patch:
                sigs = analyzer.detect_structure_signals(
                    min_confidence=profile['min_confidence'])
        except Exception:
            continue
        for s in sigs:
            d = s['direction']
            e = excursion(candles, i, d, pip, HORIZONS)
            for H, (fav, adv, clo) in e.items():
                a = det[H]
                a[0] += fav; a[1] += adv; a[2] += clo; a[3] += 1
            entries.append((i, d))
            n_long += (d == 'CALL')

    # ── control: mismo n, mismo ratio long/short, entradas sorteadas ──
    ctl = {H: [0.0, 0.0, 0.0, 0] for H in HORIZONS}
    n = len(entries)
    if n:
        p_long = n_long / n
        rng = random.Random(f'{sym}|{session}|exc')
        lo, hi = WARMUP, len(candles) - 2
        for _ in range(CONTROL_REPS):
            for _ in range(n):
                i = rng.randint(lo, hi)
                d = 'CALL' if rng.random() < p_long else 'PUT'
                e = excursion(candles, i, d, pip, HORIZONS)
                for H, (fav, adv, clo) in e.items():
                    a = ctl[H]
                    a[0] += fav; a[1] += adv; a[2] += clo; a[3] += 1

    return {'symbol': sym, 'n': n, 'det': det, 'ctl': ctl,
            'secs': round(time.perf_counter() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='M5')
    ap.add_argument('--candles', type=int, default=500_000)
    ap.add_argument('--profile', default='m5live')
    ap.add_argument('--session', default='london')
    ap.add_argument('--workers', type=int, default=14)
    ap.add_argument('--low-priority', action='store_true')
    ap.add_argument('--cache-dir', default=os.path.join(ROOT, '.cache_fase2'))
    a = ap.parse_args()

    import logging
    logger = setup_logger()
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%H:%M:%S'))
    logger.addHandler(h)

    cache_dir = os.path.join(a.cache_dir, f'{a.tf}_{a.candles}')
    with open(os.path.join(cache_dir, 'manifest.json')) as f:
        manifest = json.load(f)
    syms = [s for s, v in manifest.items() if 'error' not in v]
    params, _ = load_live_params(logger)

    logger.info(f"EXCURSION — {a.tf} / {a.profile} / sesion {a.session} / "
                f"{len(syms)} pares / horizontes {HORIZONS}")
    jobs = [(s, a.session, cache_dir, params, a.profile, a.tf, a.low_priority)
            for s in syms]

    res = []
    t0 = time.perf_counter()
    with Pool(processes=a.workers) as pool:
        for k, r in enumerate(pool.imap_unordered(run_symbol, jobs), 1):
            res.append(r)
            el = time.perf_counter() - t0
            logger.info(f"[{k}/{len(jobs)}] {r['symbol']} n={r['n']} "
                        f"({r['secs']}s) | ETA {el/k*(len(jobs)-k)/60:.0f} min")

    # ── pooled ──
    def pool_of(key):
        agg = {H: [0.0, 0.0, 0.0, 0] for H in HORIZONS}
        for r in res:
            for H in HORIZONS:
                s = r[key][H]
                a_ = agg[H]
                a_[0] += s[0]; a_[1] += s[1]; a_[2] += s[2]; a_[3] += s[3]
        return {H: (v[0] / v[3], v[1] / v[3], v[2] / v[3], v[3])
                for H, v in agg.items() if v[3]}

    D, C = pool_of('det'), pool_of('ctl')
    ntot = sum(r['n'] for r in res)

    print('\n' + '=' * 92)
    print(f'  EXCURSION DESPUES DE LA SENAL — {a.tf} / {a.profile} / {a.session} / '
          f'{len(syms)} pares / n={ntot:,}')
    print('=' * 92)
    print(f'{"velas":>6} | {"DETECTOR fav":>12} {"adv":>8} {"close":>8} | '
          f'{"AZAR fav":>9} {"adv":>8} {"close":>8} | {"close det-azar":>15}')
    print('-' * 92)
    cruce = None
    for H in HORIZONS:
        if H not in D or H not in C:
            continue
        df, da, dc, _ = D[H]
        cf, ca, cc, _ = C[H]
        diff = dc - cc
        if diff > 0 and cruce is None:
            cruce = H
        print(f'{H:>6} | {df:>12.2f} {da:>8.2f} {dc:>8.3f} | '
              f'{cf:>9.2f} {ca:>8.2f} {cc:>8.3f} | {diff:>+15.3f}')
    print('=' * 92)
    if cruce is None:
        print('  LECTURA (criterio pre-declarado): el cierre del detector NUNCA supera al')
        print('  del azar => NO hay continuacion que capturar. El pullback-entry queda')
        print('  REFUTADO antes de construirlo.')
    else:
        print(f'  LECTURA (criterio pre-declarado): CRUCE en {cruce} velas — el detector')
        print(f'  arranca peor que el azar y lo supera a partir de ahi. Eso confirma')
        print(f'  retroceso-y-continuacion y da el numero: esperar ~{cruce} velas.')
    print('=' * 92)

    out = os.path.join(ROOT, 'docs', f'fase2_excursion_{a.tf}_{a.profile}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'tf': a.tf, 'profile': a.profile, 'session': a.session,
                   'symbols': len(syms), 'n': ntot, 'horizons': HORIZONS,
                   'detector': {str(k): v for k, v in D.items()},
                   'control': {str(k): v for k, v in C.items()},
                   'cruce': cruce}, f, indent=2)
    print(f'json: {out}')


if __name__ == '__main__':
    main()
