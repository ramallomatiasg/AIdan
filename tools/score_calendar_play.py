"""
score_calendar_play.py — Scorer READ-ONLY del shadow "calendar play" (v3.63.0).

Pregunta que responde: si AIdan entrara en la direccion de la SORPRESA del dato
(actual vs forecast) unos segundos despues del release, ¿ganaria neto de spread REAL
+ comision? Y de paso: ¿cuanto se ensancha el spread en ese segundo?

Como puntua cada release (agrupa por release_ts: NFP + desempleo + salarios comparten
la ruta y se cuentan UNA vez, con la sorpresa del evento de mas peso = el primero con
sorpresa no nula):
  - sorpresa = actual - forecast (parseando '%', 'K', 'M').
  - signo esperado para EURUSD: dato USD mejor que lo esperado => USD sube => EURUSD BAJA;
    dato EUR mejor => EURUSD SUBE. Indicadores INVERSOS (desempleo, claims: mas alto = peor)
    invierten el signo. Lista chica y declarada abajo; lo que no esta se asume directo.
  - resultado a +1/+3/+5/+15 min = close_Xm * signo_esperado (pips a favor), NETO de
    spread_max_60s (lo que cobrarian al entrar en el pico de spread) + 1,3p de comision.
  - tambien reporta la excursion ADVERSA maxima en 3 min: si adv >> fav, el setup te pasa
    por arriba antes de darte la razon (lo que refuto fade-chop).

Gate pre-declarado (NO mover): n>=25 releases con sorpresa != 0 · media Y mediana del
neto a +5 min > 0 · CI95 bootstrap de la media que no cruce cero. Si a n>=40 no pasa
=> CALENDAR_PLAY_MODE=off y se cierra la puerta con data propia.

Limites declarados: `actual` puede faltar (FF no lo publico o Forexlive no lo titulo
"vs expected") => esas filas se reportan como "sin sorpresa" y NO puntuan; el match
titulo<->evento es por keywords (cota inferior). Lee solo. No necesita MT5.
"""
import os
import random
import re
import sqlite3
import statistics
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.analyzer.calendar_play import parse_number  # noqa: E402

DB_PATH = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'financial_news.db')
FRICTION_PIPS = 1.3
MIN_N = 25
INVERSE_KEYWORDS = ('unemployment', 'jobless', 'claims', 'inventories')


def expected_sign(currency, event_title, surprise):
    """+1 = EURUSD deberia subir, -1 = bajar, 0 = sin sorpresa."""
    if not surprise:
        return 0
    good = surprise > 0
    if any(k in (event_title or '').lower() for k in INVERSE_KEYWORDS):
        good = not good
    if currency == 'USD':
        return -1 if good else 1
    return 1 if good else -1


def bootstrap_ci(xs, iters=4000, seed=7):
    if len(xs) < 2:
        return (float('nan'), float('nan'))
    rnd = random.Random(seed)
    means = sorted(statistics.fmean(rnd.choices(xs, k=len(xs))) for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def main():
    if not os.path.exists(DB_PATH):
        print('DB no encontrada'); return 2
    c = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    print('=' * 72); print('CALENDAR PLAY — shadow (v3.63.0), read-only'); print('=' * 72)
    try:
        rows = c.execute("""SELECT event_key, event_title, currency, release_ts, forecast, actual, actual_source,
                                   pre_spread, spread_max_60s, max_up_3m, max_down_3m, close_1m, close_3m, close_5m,
                                   close_15m, created_at FROM calendar_play_log ORDER BY release_ts""").fetchall()
    except sqlite3.OperationalError as e:
        # la tabla la crea init_db del exe => no existe hasta el primer arranque de v3.63.0
        print(f'  tabla calendar_play_log no existe todavia ({e}). ¿Corre v3.63.0+? Si si, es un hook muerto.')
        return 1
    if not rows:
        print('  0 filas todavia. Primer release HIGH USD/EUR desde el deploy => primera fila.'); return 0
    by_ts = {}
    for r in rows:
        by_ts.setdefault(r[3], []).append(r)
    scored, no_surprise, spreads, pre_spreads = [], 0, [], []
    print(f'  eventos: {len(rows)} · releases (agrupados por hora): {len(by_ts)}'
          f' · con actual: {sum(1 for r in rows if r[5])}')
    for ts, evs in sorted(by_ts.items()):
        spreads.append(evs[0][8] or 0); pre_spreads.append(evs[0][7] or 0)
        pick = None
        for r in evs:
            f, a = parse_number(r[4]), parse_number(r[5])
            if f is None or a is None:
                continue
            sg = expected_sign(r[2], r[1], a - f)
            if sg:
                pick = (r, sg, a - f); break
        if not pick:
            no_surprise += 1; continue
        r, sg, sur = pick
        fav3 = (r[9] if sg > 0 else r[10]) or 0
        adv3 = (r[10] if sg > 0 else r[9]) or 0
        cost = (r[8] or 0) + FRICTION_PIPS
        net = {k: round((r[i] or 0) * sg - cost, 1) for k, i in (('1m', 11), ('3m', 12), ('5m', 13), ('15m', 14))}
        scored.append(dict(ts=ts, title=r[1], cur=r[2], sur=sur, sign=sg, fav3=fav3, adv3=adv3,
                           spread=r[8], net=net))
    print(f'  releases sin sorpresa legible (no puntuan): {no_surprise}')
    if spreads:
        print(f'  spread: en calma mediana {statistics.median(pre_spreads):.1f}p · '
              f'maximo 1er minuto mediana {statistics.median(spreads):.1f}p, p90 {sorted(spreads)[int(0.9*(len(spreads)-1))]:.1f}p')
    if not scored:
        print('  nada puntuable todavia.'); return 0
    print(f'\n  {"fecha UTC":<17}{"cur":<4}{"evento":<28}{"sorp":>7}{"dir":>4}{"fav3":>6}{"adv3":>6}{"n1m":>7}{"n5m":>7}{"n15m":>7}')
    for s in scored:
        d = datetime.fromtimestamp(s['ts'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
        print(f'  {d:<17}{s["cur"]:<4}{s["title"][:27]:<28}{s["sur"]:>7.2f}{("UP" if s["sign"]>0 else "DN"):>4}'
              f'{s["fav3"]:>6.1f}{s["adv3"]:>6.1f}{s["net"]["1m"]:>7.1f}{s["net"]["5m"]:>7.1f}{s["net"]["15m"]:>7.1f}')
    n = len(scored)
    print(f'\n  n={n} (gate {MIN_N})')
    for k in ('1m', '3m', '5m', '15m'):
        xs = [s['net'][k] for s in scored]
        lo, hi = bootstrap_ci(xs)
        print(f'  neto a +{k:<4} media {statistics.fmean(xs):>6.2f}p  mediana {statistics.median(xs):>6.2f}p'
              f'  CI95 [{lo:.2f}, {hi:.2f}]  ganadores {sum(1 for x in xs if x > 0)}/{n}')
    fav = [s['fav3'] for s in scored]; adv = [s['adv3'] for s in scored]
    print(f'  excursion 3 min: a favor mediana {statistics.median(fav):.1f}p · adversa mediana {statistics.median(adv):.1f}p'
          f'  ({"OJO: adv >= fav, el setup te pasa por arriba" if statistics.median(adv) >= statistics.median(fav) else "fav > adv"})')
    xs5 = [s['net']['5m'] for s in scored]
    lo, hi = bootstrap_ci(xs5)
    passes = n >= MIN_N and statistics.fmean(xs5) > 0 and statistics.median(xs5) > 0 and lo > 0
    if n < MIN_N:
        print(f'\n  >>> n={n} < {MIN_N}: SIN VEREDICTO. Seguir juntando (~10 releases HIGH/mes).')
    elif passes:
        print('\n  >>> PASA el gate a +5 min. Es permiso para diseñar la jugada en shadow con SL/TP, NO para operar.')
    else:
        print(f'\n  >>> NO PASA a +5 min.' + ('  n>=40 => CALENDAR_PLAY_MODE=off.' if n >= 40 else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
