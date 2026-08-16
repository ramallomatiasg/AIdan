"""
score_d1_shadow.py — mide FORWARD las señales del track D1 en shadow (v3.54.0).

READ-ONLY sobre produccion salvo por el UPDATE de las columnas de outcome de
d1_shadow_log (que es la tabla del propio shadow; no toca ninguna tabla del vivo).

═══ QUE MIDE Y QUE NO ════════════════════════════════════════════════════════

Mide la EXCURSION CRUDA del precio despues de cada señal:
    fav   = cuanto llego a moverse A FAVOR   (maximo)
    adv   = cuanto llego a moverse EN CONTRA (maximo)
    close = donde estaba al final del horizonte

NO re-simula SL/TP. Es regla dura del proyecto y viene del caso bounce-entry:
el simulador dijo "22% WR, p=0.000" y los outcomes REALES dieron 43% vs 34% —
habia INVERTIDO el signo, porque penaliza de mas los trades que arrancan
adversos y se recuperan. Aca no hay orden de eventos, ni "que toco primero",
ni stop: solo precio observado.

Se miden fav Y adv (como el scorer de fade-chop, no como el de pullback). A
horizonte de dias un swing puede ir a favor y darse vuelta; medir solo lo
favorable sobreestima el edge. Fue justamente la columna 'adv' la que refuto
fade-chop (fav ~1p vs adv ~9p).

═══ ZONA HORARIA: POR QUE ACA NO HAY LIO ═════════════════════════════════════

Los otros scorers parten de created_at (AR naive) y le suman 3h para llegar a
hora servidor — si alguien se olvida el now_ar() en el INSERT, dan numeros
plausibles y falsos. Este scorer NO usa created_at para nada: usa
d1_candle_ts, que es el epoch de la vela tal como lo devuelve MT5 (hora
servidor), y lo compara contra velas pedidas al MISMO MT5. Misma convencion en
los dos lados, cero conversion.

Uso:
    python tools/score_d1_shadow.py            # scorea y reporta
    python tools/score_d1_shadow.py --dry-run  # reporta sin escribir

Requiere MT5. Correr preferentemente con AIdan CERRADO (regla del 14-jun: no
correr MT5 pesado desde varios procesos mientras el exe opera).
"""
import argparse
import os
import sqlite3
import statistics as st
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

PIP = 0.0001
DB = os.path.join(os.environ.get('APPDATA', ''), 'AIdan', 'state', 'financial_news.db')

# Horizontes en velas D1. El principal (10) es el hold del backtest; los cortos
# dan lectura temprana mientras se acumulan señales (2,7 por mes).
HORIZONS = [3, 5, 10]
PRIMARY_H = 10

# Costos reales medidos en la cuenta (ver CLAUDE.md / propuesta D1):
COMMISSION_PIPS = 0.8      # ~0,7p de comision IC Raw a lote 0.01 + ~0,1p de spread
SWAP_LONG_PIPS = -0.8174   # por noche, comprado  (symbol_info.swap_long / 10)
SWAP_SHORT_PIPS = 0.1445   # por noche, vendido


def fetch_d1_candles(count=400):
    """Velas D1 CERRADAS. copy_rates_from_pos(..., 0, count) devuelve la vela
    ACTUAL en formacion como ultimo elemento — price_feed la descarta
    explicitamente (price_feed.py:142-144) y aca hay que hacer lo mismo.

    Si no se descarta, una fila con 9 velas cerradas + la de hoy a medio hacer
    cuenta como madura a horizonte 10: se le escribe el outcome un dia antes,
    con un high/low incompletos. Y como el UPDATE solo alcanza filas con
    outcome NULL, ese numero queda CLAVADO para siempre.
    """
    import time as _t
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_D1, 0, count)
    tick = mt5.symbol_info_tick("EURUSD")
    # Offset servidor-vs-UTC derivado en vivo (redondeado a 30min, robusto a
    # DST). Hardcodear la zona del broker es el error que dejo 457 filas
    # tz_unreconciled en measure_news_llm_error.
    srv_off = round((tick.time - _t.time()) / 1800.0) * 1800 if tick else 0
    mt5.shutdown()
    if rates is None or len(rates) == 0:
        raise RuntimeError("MT5 no devolvio velas D1")

    ahora_srv = _t.time() + srv_off
    out = [{'t': int(r['time']), 'open': float(r['open']), 'high': float(r['high']),
            'low': float(r['low']), 'close': float(r['close'])} for r in rates]
    # Una vela D1 cierra 86400s despues de su apertura (en hora servidor).
    cerradas = [c for c in out if c['t'] + 86400 <= ahora_srv]
    if len(cerradas) < len(out):
        print(f"  (se descarta{'n' if len(out)-len(cerradas) > 1 else ''} "
              f"{len(out)-len(cerradas)} vela(s) en formacion)")
    return cerradas


def excursion(candles, entry_ts, entry_price, direction, n_bars):
    """Excursion sobre las n_bars velas POSTERIORES a la del setup.

    Devuelve (fav, adv, close) en pips, o None si todavia no hay n_bars velas
    cerradas despues del setup (=> la fila no esta madura y no se scorea).
    """
    fwd = [c for c in candles if c['t'] > entry_ts]
    if len(fwd) < n_bars:
        return None
    w = fwd[:n_bars]
    hi = max(c['high'] for c in w)
    lo = min(c['low'] for c in w)
    close = w[-1]['close']
    if direction == 'CALL':
        return ((hi - entry_price) / PIP, (entry_price - lo) / PIP,
                (close - entry_price) / PIP)
    return ((entry_price - lo) / PIP, (hi - entry_price) / PIP,
            (entry_price - close) / PIP)


def costo(direction, n_bars):
    """Comision + swap. n_bars velas D1 ~ n_bars dias de mercado ~ x7/5 noches."""
    noches = n_bars * (7.0 / 5.0)
    swap = noches * (SWAP_LONG_PIPS if direction == 'CALL' else SWAP_SHORT_PIPS)
    return COMMISSION_PIPS - swap  # swap negativo => costo mayor


def resumen(nombre, filas, h):
    """filas = [(direction, setup_type, fav, adv, close)]"""
    if not filas:
        print(f"  {nombre}: sin datos")
        return
    n = len(filas)
    fav = [f[2] for f in filas]
    adv = [f[3] for f in filas]
    neto = [f[4] - costo(f[0], h) for f in filas]
    ganan = sum(1 for x in neto if x > 0)
    print(f"  {nombre:24s} n={n:3d} | fav {st.mean(fav):6.1f}p  adv {st.mean(adv):6.1f}p "
          f"| close neto {st.mean(neto):+7.1f}p | {ganan}/{n} en verde ({ganan/n*100:.0f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='no escribe outcomes')
    args = ap.parse_args()

    if not os.path.exists(DB):
        print(f"No existe la DB: {DB}")
        return 1

    conn = sqlite3.connect(DB, timeout=15)

    print("=" * 78)
    print("SCORER — Track D1 shadow (v3.54.0)")
    print("=" * 78)

    existe = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='d1_shadow_log'"
    ).fetchone()
    if not existe:
        print("\nLa tabla d1_shadow_log todavia no existe.")
        print("La crea init_db() al arrancar el exe => hace falta rebuild de AIdan.exe")
        print("con v3.54.0 y un arranque. Despues de eso, esta tabla aparece sola.")
        conn.close()
        return 0

    rows = conn.execute("""
        SELECT id, d1_candle_ts, direction, setup_type, entry_price, confidence,
               htf_bias, avg_range, outcome_fav_pips
        FROM d1_shadow_log ORDER BY d1_candle_ts
    """).fetchall()

    if not rows:
        print("\nTodavia no hay ninguna señal D1 logueada.")
        print("Esperado: ~2,7 por mes. La primera puede tardar dias.")
        conn.close()
        return 0

    print(f"\nseñales logueadas: {len(rows)}")
    print(f"  ya scoreadas    : {sum(1 for r in rows if r[8] is not None)}")

    candles = fetch_d1_candles()
    print(f"  velas D1 de MT5 : {len(candles)}")

    por_h = {h: [] for h in HORIZONS}
    escritas = 0
    inmaduras = 0

    for (rid, ts, direction, setup, entry, conf, htf, atr, ya) in rows:
        if not entry or not direction:
            continue
        for h in HORIZONS:
            ex = excursion(candles, ts, entry, direction, h)
            if ex is None:
                if h == PRIMARY_H:
                    inmaduras += 1
                continue
            por_h[h].append((direction, setup, ex[0], ex[1], ex[2], conf, htf, atr))
            # Solo se persiste el horizonte principal, y solo una vez.
            # El UPDATE alcanza filas con outcome NULL, asi que un score
            # prematuro quedaria CLAVADO — por eso el guard de madurez de
            # excursion() es obligatorio, no cosmetico.
            if h == PRIMARY_H and ya is None and not args.dry_run:
                conn.execute("""
                    UPDATE d1_shadow_log
                       SET outcome_fav_pips = ?, outcome_adv_pips = ?,
                           outcome_close_pips = ?, scored_at = ?
                     WHERE id = ? AND outcome_fav_pips IS NULL
                """, (round(ex[0], 1), round(ex[1], 1), round(ex[2], 1),
                      __import__('src.common.db', fromlist=['now_ar']).now_ar(), rid))
                escritas += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"  sin madurar ({PRIMARY_H} velas): {inmaduras}")
    if not args.dry_run:
        print(f"  outcomes escritos: {escritas}")

    for h in HORIZONS:
        filas = por_h[h]
        print(f"\n{'-'*78}\nHORIZONTE {h} velas D1  (costo: comision {COMMISSION_PIPS}p + swap)")
        print('-' * 78)
        if not filas:
            print("  sin señales maduras a este horizonte todavia")
            continue
        base = [(f[0], f[1], f[2], f[3], f[4]) for f in filas]
        resumen("TODAS", base, h)
        print()
        for d in ('CALL', 'PUT'):
            resumen(d, [f for f in base if f[0] == d], h)
        print()
        by = defaultdict(list)
        for f in base:
            by[f[1]].append(f)
        for setup, g in sorted(by.items(), key=lambda x: -len(x[1])):
            resumen(setup, g, h)

    print(f"\n{'-'*78}")
    print("COMO LEERLO")
    print('-' * 78)
    print("- 'close neto' es la comparacion honesta contra el backtest. Es precio")
    print("  observado, NO una simulacion de SL/TP.")
    print("  BASELINE (corregido el 16-ago, ver abajo): +11 a +13p post-swap.")
    print("- Si 'adv' es mucho mayor que 'fav', el setup te pasa por arriba antes de")
    print("  darte la razon: eso fue lo que refuto fade-chop (fav ~1p vs adv ~9p).")
    print("- El gate de la casa: no concluir con n<25 ni con un CI que cruce cero.")
    print("  A ~2,3 señales/mes, n=25 son ~11 meses. Esto se lee despacio, a proposito.")
    print()
    print("- DE DONDE SALE EL BASELINE (re-medido el 16-ago-2026):")
    print("  El titular del 13-ago (242 señales, PF 1,40, +16,3p) NO era comparable")
    print("  contra este shadow: corrio con DEFAULT_PARAMS (breakout_dist_max=15,")
    print("  la DB viva tiene 7) y con un unico conf_adj de sesion — el de la hora")
    print("  en que se ejecuto el script, que resulto ser off-hours.")
    print("  Re-corrido con los params vivos y barriendo las 4 sesiones:")
    print("      señales   186 - 227  (2,1 - 2,5/mes, no 2,7)")
    print("      neto comision  +13,7 a +15,3p/trade")
    print("      neto + swap    +10,8 a +12,7p/trade   PF 1,25 - 1,30")
    print("  Positivo en las 4 sesiones => el edge no dependia de la hora del reloj.")
    print("  Reproducir: tools/backtest_h4_d1.py --tf D1 --variant naive")
    print("              --params live --session sweep")
    return 0


if __name__ == '__main__':
    sys.exit(main())
