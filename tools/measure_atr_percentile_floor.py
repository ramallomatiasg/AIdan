"""
measure_atr_percentile_floor.py - FASE 1 del piso de ATR por PERCENTIL (read-only).

Pregunta: el piso de ATR de m15 esta FIJO en pips (`M15_ATR_FLOOR=8.0`, v3.55.0) y por
eso no se autoajusta. En el regimen de agosto-2026 el ATR de M15 pico en 5,6p en su MEJOR
hora => el piso quedo por ENCIMA de toda la distribucion y m15 no esta filtrado, esta
APAGADO (0 trades desde el 20-ago). El research del 19-ago propone rankear el ATR contra
las ultimas ~100 barras y exigir percentil >= ~20, que mantiene elegible una fraccion
CONSTANTE de las barras por construccion.

Este script NO cambia nada: mide si esa promesa se cumple, y si el percentil separa
ganar/perder tan bien como el corte en pips. Escribe CERO filas (conexion `mode=ro`).

======================================================================================
CRITERIOS PRE-DECLARADOS (escritos ANTES de correrlo - no ajustar despues de ver los
numeros; esa es la regla que ya freno ML, los gates y el bounce-skip en este proyecto)
======================================================================================

  C1 - FRECUENCIA CONSTANTE (la premisa de la idea).
       La fraccion de ventanas elegibles del percentil tiene que ser ESTABLE entre un mes
       muerto y uno normal. Umbral: |frac(mes muerto) - frac(mes normal)| <= 10 puntos
       para el percentil. El piso fijo va a fallar esto por construccion (es el defecto
       que se esta midiendo); lo que hay que verificar es que el percentil NO falle.
       Si el percentil tambien colapsa => la idea no cumple su premisa => no se implementa.

  C2 - SEPARACION (la condicion que manda).
       Sobre los m15 REALES del archive, el corte por percentil tiene que separar WR al
       menos tan bien como el corte en 8p, que dio 27,8% (n=90) abajo vs 51,6% (n=31)
       arriba => delta 23,8pp. Umbral: delta de WR >= 15pp Y el CI95 de Wilson del bucket
       alto no cruza el WR del bucket bajo. Si el percentil PROTEGE la frecuencia pero NO
       separa => no se implementa. Un filtro que no separa recorta para nada; ese es el
       principio rector del proyecto.

  C3 - QUE NO SEA LO MISMO.
       Las ventanas donde las dos reglas DIFIEREN tienen que ser >= 20% del total. Si el
       percentil habilita casi exactamente lo mismo que el 8p, no justifica un rebuild.

  ANTI-OVERFIT: se barre una GRILLA (percentil 10/15/20/25/30 x lookback 50/100/200) y se
  reporta ENTERA. Elegir la mejor celda seria overfit. **La decision se toma con la celda
  PRE-DECLARADA del research: percentil 20, lookback 100.** Las otras celdas sirven solo
  para ver si el resultado es una MESETA (robusto) o una AGUJA (ruido). Una aguja se lee
  como "no pasa", no como "hay que usar esa celda".

======================================================================================
METODOLOGIA
======================================================================================
  * El ATR se calcula EXACTAMENTE como en produccion (`TechnicalAnalyzer.get_market_state`,
    technical.py:218-227): media simple del True Range de las ultimas 14 velas, en pips,
    redondeada a 1 decimal. Si esto difiere, la comparacion no mide el gate real.
  * El percentil es el rank del ATR actual DENTRO de la distribucion de los ATR de las
    ultimas `lookback` barras (rolling, causal: nunca mira hacia adelante).
  * Los trades reales se clasifican por el percentil de SU vela; el ATR reconstruido se
    valida contra `trade_archive.avg_range_pips`, que fue clasificado EN EL MOMENTO. Si la
    reconstruccion no coincide, el mapeo de timestamps esta roto y el script ABORTA
    (fail-loud - la leccion de measure_news_latency, que reportaba 398 min por sumar UTC
    con hora AR).
  * NO se re-simula SL/TP en ningun lado (doctrina del proyecto). Para C2 se usan los
    outcomes REALES (`mt5_pnl`, broker-truth).

LIMITES DECLARADOS
  * La clasificacion por percentil de los trades historicos es RETROSPECTIVA (reconstruida
    de velas), no medida en el momento. El proyecto ya se quemo con eso (caso bounce-entry).
    El control de sanidad contra `avg_range_pips` acota el riesgo de timestamp pero NO
    convierte esto en una medicion limpia => C2 es indicativo, no veredicto final.
  * VELA EN FORMACION: produccion calcula el ATR incluyendo la vela ABIERTA (pide 100 velas
    M15 y promedia el TR de las ultimas 14, la ultima a medio hacer). La reconstruccion de
    aca ve esa misma vela YA CERRADA, con su high/low completos => el ATR reconstruido
    tiende a salir un poco MAS ALTO que el que vio produccion al decidir. No hay forma de
    reconstruir la vela parcial desde velas M15. Es la razon principal por la que el
    control de sanidad existe y por la que su tolerancia es 1,5p y no 0: si el desvio
    tipico se va por encima de eso, la reconstruccion dejo de representar lo que el gate
    vio y C2 no se reporta. Afecta a C2; C1 y C3 son sobre velas cerradas y no lo tienen.
  * `--offline` NO es la medicion. El percentil rolling necesita velas; sin MT5 solo se
    puede armar una distribucion con los ATR guardados (rejected_signals = todos < piso,
    archive = todos >= piso del momento) => doblemente censurada. Sirve como smoke test del
    plumbing y para cuantificar la censura. No decidir con eso.

USO
  python tools/measure_atr_percentile_floor.py --offline        # sin MT5, corre hoy
  python tools/measure_atr_percentile_floor.py --months 4       # la medicion (requiere MT5)

  ATENCION: el modo MT5 pide el terminal, que lo tiene tomado AIdan.exe en vivo.
  Correr con AIdan CERRADO (sabado, mercado cerrado).
"""
import argparse
import math
import os
import sqlite3
import statistics
import sys
import time as _time
from collections import defaultdict
from datetime import datetime, timedelta

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')

# --- celda pre-declarada por el research del 19-ago (docs/research_mercado_2026-08-19.md, seccion 5) ---
DECLARED_PCT = 20
DECLARED_LOOKBACK = 100
DECLARED_CEILING = 90          # el techo del research; se reporta aparte, no gatea C1/C2/C3

# --- grilla anti-overfit ---
GRID_PCT = [10, 15, 20, 25, 30]
GRID_LOOKBACK = [50, 100, 200]

# --- umbrales de los criterios (pre-declarados, no tocar tras ver los numeros) ---
C1_MAX_SPREAD_PP = 10.0        # puntos de diferencia entre mes muerto y mes normal
C2_MIN_WR_DELTA_PP = 15.0      # delta de WR minimo para que el corte "separe"
C3_MIN_DISAGREE_FRAC = 0.20    # fraccion minima de ventanas en las que las reglas difieren

FIXED_FLOOR = 8.0              # el piso vivo (Config.M15_ATR_FLOOR)
ATR_PERIOD = 14                # igual que produccion
BASELINE_LOW_WR = 27.8         # referencia v3.55.0: ATR <=8p, n=90
BASELINE_HIGH_WR = 51.6        # referencia v3.55.0: ATR >8p, n=31


def wilson(wins, n, z=1.96):
    """CI95 de Wilson. Mismo metodo que `significance.py` usa en el resto del proyecto -
    no se estrena estadistica nueva para leer este experimento."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(100 * (c - m) / d, 1), round(100 * (c + m) / d, 1))


def _parse_ar(ts):
    """created_at del proyecto: hora AR (UTC-3), con o sin microsegundos."""
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(str(ts).split('+')[0].strip(), fmt)
        except ValueError:
            continue
    return None


def atr_at(candles, i):
    """ATR de produccion en la vela i. Replica technical.py:218-227 (TR medio de 14 velas,
    en pips, round 1). `i` es indice absoluto; necesita i >= 1."""
    period = min(ATR_PERIOD, i)
    if period < 1:
        return None
    trs = []
    for k in range(i - period + 1, i + 1):
        h, l = candles[k]['high'], candles[k]['low']
        prev_c = candles[k - 1]['close']
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)) * 10000)
    return round(sum(trs) / len(trs), 1)


def pct_rank(value, window):
    """Percentil (0-100) de `value` dentro de `window`. Definicion de rank medio: los
    empates cuentan medio - con ATR redondeado a 1 decimal los empates son frecuentes y
    'strictly less' sesgaria el percentil hacia abajo en mercados muertos, que es
    justamente el regimen que se esta midiendo."""
    if not window:
        return None
    below = sum(1 for w in window if w < value)
    equal = sum(1 for w in window if w == value)
    return 100.0 * (below + 0.5 * equal) / len(window)


# ======================================================================================
# MT5: velas
# ======================================================================================
def fetch_m15(months):
    """Velas M15 de MT5 hacia atras. Devuelve (candles, offset_s) con candles en
    [{'ts': datetime UTC, 'open','high','low','close'}] ordenadas."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()}")
        print("Si AIdan.exe esta corriendo, cerralo: tiene el terminal tomado.")
        return None, None
    tick = mt5.symbol_info_tick("EURUSD")
    if not tick or not getattr(tick, 'time', 0):
        print("Sin tick - no se puede derivar el offset del server. Abortando.")
        mt5.shutdown()
        return None, None
    offset_s = round((tick.time - _time.time()) / 1800.0) * 1800  # server - UTC

    srv_now = datetime.utcnow() + timedelta(seconds=offset_s)
    srv_from = srv_now - timedelta(days=int(months * 31))
    rates = None
    for _attempt in range(3):  # MT5 baja la historia async: reintentar antes de concluir
        rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M15, srv_from, srv_now)
        if rates is not None and len(rates) > 1000:
            break
        _time.sleep(2.0)
    mt5.shutdown()
    if rates is None or len(rates) == 0:
        print("MT5 no devolvio velas M15. Abortando.")
        return None, None
    candles = [{'ts': datetime.utcfromtimestamp(int(r['time']) - offset_s),
                'open': float(r['open']), 'high': float(r['high']),
                'low': float(r['low']), 'close': float(r['close'])} for r in rates]
    candles.sort(key=lambda c: c['ts'])
    print(f"MT5: {len(candles)} velas M15 desde {candles[0]['ts']} hasta {candles[-1]['ts']} UTC "
          f"(offset server-UTC {offset_s}s)")
    return candles, offset_s


def min_window(lookback):
    """Ventana minima para emitir percentil. Cuanto mas grande el lookback, mas tarde
    arranca la serie => distintas celdas de la grilla arrancan en barras distintas. Ver
    `common_start()`."""
    return max(20, lookback // 4)


def common_start(lookbacks):
    """Primer indice de vela en el que TODAS las celdas de la grilla ya tienen percentil.
    Sin esto, la fila lookback=200 se promediaria sobre menos barras que la de 50 y la
    lectura 'meseta o aguja' compararia periodos distintos - un artefacto que se leeria
    como si el resultado dependiera del lookback."""
    return max(min_window(lb) for lb in lookbacks) + 1


def build_series(candles, lookback):
    """Serie causal [(idx, ts, atr, pct)] con el percentil rolling del ATR."""
    atrs, out = [], []
    need = min_window(lookback)
    for i in range(len(candles)):
        a = atr_at(candles, i)
        atrs.append(a)
        if a is None:
            continue
        window = [x for x in atrs[max(0, i - lookback):i] if x is not None]
        pct = pct_rank(a, window) if len(window) >= need else None
        out.append((i, candles[i]['ts'], a, pct))
    return out


# ======================================================================================
# C1 + C3 - frecuencia y solapamiento
# ======================================================================================
def report_frequency(candles):
    print()
    print("=" * 82)
    print("C1 - FRACCION DE VENTANAS ELEGIBLES POR MES  (piso fijo vs percentil)")
    print("=" * 82)
    assert DECLARED_LOOKBACK in GRID_LOOKBACK, \
        "la celda pre-declarada tiene que estar en la grilla o C1/C3 quedan sin denominador"
    start = common_start(GRID_LOOKBACK)
    print(f"Cada vela M15 = una ventana. Todas las celdas se cuentan desde la vela #{start} "
          f"(donde ya hay percentil para lookback {max(GRID_LOOKBACK)}), asi la grilla compara "
          f"el MISMO periodo.")

    by_month_fixed = defaultdict(lambda: [0, 0])
    grids = {}
    for lb in GRID_LOOKBACK:
        series = build_series(candles, lb)
        for pmin in GRID_PCT:
            grids[(pmin, lb)] = defaultdict(lambda: [0, 0])
        for _i, ts, atr, pct in series:
            if pct is None or _i < start:
                continue
            m = ts.strftime('%Y-%m')
            if lb == DECLARED_LOOKBACK:
                by_month_fixed[m][1] += 1
                if atr >= FIXED_FLOOR:
                    by_month_fixed[m][0] += 1
            for pmin in GRID_PCT:
                g = grids[(pmin, lb)][m]
                g[1] += 1
                if pct >= pmin:
                    g[0] += 1

    months = sorted(by_month_fixed)
    print()
    hdr = f"{'mes':<9}{'velas':>7}  {'fijo 8p':>8}"
    for pmin in GRID_PCT:
        hdr += f"  {'p' + str(pmin):>6}"
    print(hdr + f"   (lookback {DECLARED_LOOKBACK})")
    for m in months:
        ok, tot = by_month_fixed[m]
        line = f"{m:<9}{tot:>7}  {100.0 * ok / tot:>7.1f}%"
        for pmin in GRID_PCT:
            g = grids[(pmin, DECLARED_LOOKBACK)][m]
            line += f"  {(100.0 * g[0] / g[1] if g[1] else 0):>5.1f}%"
        print(line)

    def spread(fracs):
        return (max(fracs) - min(fracs)) if len(fracs) >= 2 else 0.0

    fx = [100.0 * by_month_fixed[m][0] / by_month_fixed[m][1] for m in months]
    pc = [100.0 * grids[(DECLARED_PCT, DECLARED_LOOKBACK)][m][0]
          / max(1, grids[(DECLARED_PCT, DECLARED_LOOKBACK)][m][1]) for m in months]
    print()
    print(f"  dispersion mes-a-mes  piso fijo 8p : {spread(fx):>5.1f} pp")
    print(f"  dispersion mes-a-mes  percentil {DECLARED_PCT:<3}: {spread(pc):>5.1f} pp"
          f"   (umbral C1 <= {C1_MAX_SPREAD_PP} pp)")
    c1 = spread(pc) <= C1_MAX_SPREAD_PP
    print(f"  [{'OK ' if c1 else 'NO '}] C1 - el percentil mantiene la frecuencia estable")

    # Lo que un lector puede pasar por alto: el percentil no es "el mismo filtro pero
    # autoajustado". Un piso p20 deja elegible ~80% de las barras POR DEFINICION, y el
    # piso fijo de 8p en un mes NORMAL deja bastante menos => el percentil puede ser un
    # filtro claramente MAS PERMISIVO, no solo mas estable. Eso multiplica la frecuencia
    # de m15 en vez de restaurarla, y es exactamente por que C2 (¿separa?) es el que
    # decide y no C1.
    avg_fx = sum(fx) / len(fx) if fx else 0.0
    avg_pc = sum(pc) / len(pc) if pc else 0.0
    print(f"  elegible promedio: piso fijo {avg_fx:.1f}%  vs  percentil {DECLARED_PCT} "
          f"{avg_pc:.1f}%   (x{avg_pc / avg_fx:.1f} mas permisivo)" if avg_fx > 0 else
          f"  elegible promedio: piso fijo 0%  vs  percentil {DECLARED_PCT} {avg_pc:.1f}%")
    if avg_fx > 0 and avg_pc > 1.5 * avg_fx:
        print("  (!) OJO: el percentil habilita mucho MAS que el piso fijo. No es un cambio")
        print("      neutro de frecuencia: multiplica los trades de m15. Leer C2 antes de")
        print("      entusiasmarse con C1 - mas frecuencia sin separacion es mas sangria.")
    if len(months) < 2:
        print("  (!) 1 solo mes de historia: C1 NO es evaluable. Subir --months.")
        c1 = None

    print()
    print("  grilla completa (fraccion elegible promedio sobre todos los meses):")
    line = f"  {'lookback':<10}"
    for pmin in GRID_PCT:
        line += f"{'p' + str(pmin):>8}"
    print(line)
    for lb in GRID_LOOKBACK:
        line = f"  {lb:<10}"
        for pmin in GRID_PCT:
            g = grids[(pmin, lb)]
            tot = sum(v[1] for v in g.values())
            ok = sum(v[0] for v in g.values())
            line += f"{(100.0 * ok / tot if tot else 0):>7.1f}%"
        print(line)

    # C3 - desacuerdo entre reglas (celda pre-declarada)
    series = build_series(candles, DECLARED_LOOKBACK)
    both = fixed_only = pct_only = neither = 0
    for _i, _ts, atr, pct in series:
        if pct is None or _i < start:
            continue
        f_ok, p_ok = atr >= FIXED_FLOOR, pct >= DECLARED_PCT
        if f_ok and p_ok:
            both += 1
        elif f_ok:
            fixed_only += 1
        elif p_ok:
            pct_only += 1
        else:
            neither += 1
    tot = both + fixed_only + pct_only + neither
    dis = (fixed_only + pct_only) / tot if tot else 0
    print()
    print("=" * 82)
    print(f"C3 - SOLAPAMIENTO  (piso fijo {FIXED_FLOOR}p vs percentil {DECLARED_PCT}"
          f"/lookback {DECLARED_LOOKBACK})")
    print("=" * 82)
    print(f"  las dos habilitan      {both:>7}  ({100.0 * both / tot:.1f}%)")
    print(f"  solo el piso fijo      {fixed_only:>7}  ({100.0 * fixed_only / tot:.1f}%)")
    print(f"  solo el percentil      {pct_only:>7}  ({100.0 * pct_only / tot:.1f}%)  <- lo que RECUPERA")
    print(f"  las dos bloquean       {neither:>7}  ({100.0 * neither / tot:.1f}%)")
    print(f"  desacuerdo total       {100.0 * dis:.1f}%   (umbral C3 >= {100 * C3_MIN_DISAGREE_FRAC:.0f}%)")
    c3 = dis >= C3_MIN_DISAGREE_FRAC
    print(f"  [{'OK ' if c3 else 'NO '}] C3 - las reglas no son la misma cosa")

    ceil_blocked = sum(1 for _i, _t, _a, p in series if p is not None and p > DECLARED_CEILING)
    print()
    print(f"  (informativo) techo percentil >{DECLARED_CEILING}: {ceil_blocked} ventanas "
          f"({100.0 * ceil_blocked / tot:.1f}%) - es el 'ATR ceiling' del backlog, sin medir.")
    return c1, c3, series


# ======================================================================================
# C2 - separacion sobre los trades REALES
# ======================================================================================
def report_separation(series):
    print()
    print("=" * 82)
    print("C2 - SEPARACION SOBRE LOS m15 REALES  (broker-truth, sin re-simular SL/TP)")
    print("=" * 82)
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    rows = conn.execute("""
        SELECT created_at, avg_range_pips, mt5_pnl
        FROM trade_archive
        WHERE trigger_type = 'm15_structure' AND mt5_pnl IS NOT NULL
        ORDER BY created_at""").fetchall()
    conn.close()
    if not rows:
        print("  0 trades de m15 en el archive. Nada que medir.")
        return None

    by_ts = {ts: (atr, pct) for _i, ts, atr, pct in series}
    ordered = sorted(by_ts)

    def bar_for(utc_dt):
        """La vela M15 que CONTIENE utc_dt (la que estaba abierta al crearse la senal)."""
        lo, hi = 0, len(ordered) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if ordered[mid] <= utc_dt:
                best = ordered[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        if best is None or (utc_dt - best) > timedelta(minutes=30):
            return None
        return best

    matched, atr_gap = [], []
    for created_at, stored_atr, pnl in rows:
        ar = _parse_ar(created_at)
        if ar is None:
            continue
        utc = ar + timedelta(hours=3)          # AR = UTC-3
        b = bar_for(utc)
        if b is None:
            continue
        atr, pct = by_ts[b]
        if pct is None:
            continue
        matched.append({'pct': pct, 'atr': atr, 'stored_atr': stored_atr,
                        'pnl': float(pnl), 'win': 1 if float(pnl) > 0 else 0})
        # OJO: `avg_range_pips` NO se poblaba antes del 10-jun-2026 => 71 de los 194 m15
        # tienen 0, que no es un ATR real. Esas filas SI sirven para C2 (se clasifican por
        # el percentil reconstruido de su vela), pero NO pueden entrar al control de
        # sanidad: compararlas daria |delta| ~5p y el script abortaria diciendo que el
        # mapeo de timestamps esta roto cuando lo roto es la columna.
        if stored_atr and float(stored_atr) > 0:
            atr_gap.append(abs(atr - float(stored_atr)))

    print(f"  trades m15 con P&L real: {len(rows)}  |  cruzados con vela+percentil: {len(matched)}")
    if not matched:
        print("  (!) 0 cruces. La historia M15 no cubre el periodo de los trades. Subir --months.")
        return None
    print(f"  con ATR guardado usable (>0) para el control de sanidad: {len(atr_gap)}"
          f"  |  con avg_range_pips=0 (columna sin poblar, pre 10-jun): "
          f"{len(matched) - len(atr_gap)}")

    # CONTROL DE SANIDAD (fail-loud): el ATR reconstruido tiene que parecerse al que
    # produccion guardo EN EL MOMENTO. Si no, el mapeo de timestamps esta roto y todo
    # C2 es basura (la leccion de measure_news_latency).
    if len(atr_gap) < 20:
        print("  (!) menos de 20 filas con ATR guardado usable: el control de sanidad NO")
        print("      puede correr => C2 queda SIN validar el mapeo de timestamps. Leerlo")
        print("      como indicativo debil, no como medicion.")
    if atr_gap:
        med_gap = statistics.median(atr_gap)
        print(f"  control de sanidad ATR reconstruido vs guardado: mediana |delta| = {med_gap:.2f}p")
        if med_gap > 1.5:
            print()
            print("  ABORTADO - el ATR reconstruido NO coincide con el que se guardo al entrar.")
            print("  Eso significa que el mapeo de timestamps (AR->UTC->server) esta mal, o que")
            print("  las velas no son las mismas que vio produccion. C2 no se reporta: un numero")
            print("  plausible sobre un mapeo roto es peor que ningun numero.")
            return False
        print("  -> mapeo de timestamps OK, sigo.")

    def bucket_stats(sel):
        n = len(sel)
        w = sum(s['win'] for s in sel)
        pnl = sum(s['pnl'] for s in sel)
        wr = 100.0 * w / n if n else 0.0
        return n, w, wr, pnl, wilson(w, n)

    print()
    print(f"  -- referencia v3.55.0 (corte en pips): <=8p WR {BASELINE_LOW_WR}% (n=90) | "
          f">8p WR {BASELINE_HIGH_WR}% (n=31) => delta {BASELINE_HIGH_WR - BASELINE_LOW_WR:.1f}pp")
    print()
    print("  -- corte por PERCENTIL sobre los mismos trades --")
    print(f"  {'regla':<26}{'n':>5}{'WR':>8}{'CI95':>16}{'PnL':>10}{'$/trade':>10}")
    results = {}
    for pmin in GRID_PCT:
        below = [s for s in matched if s['pct'] < pmin]
        above = [s for s in matched if s['pct'] >= pmin]
        nb, _wb, wrb, pb, _cb = bucket_stats(below)
        na, _wa, wra, pa, ca = bucket_stats(above)
        results[pmin] = (nb, wrb, na, wra, ca, pb, pa)
        tag = ' <- pre-declarada' if pmin == DECLARED_PCT else ''
        print(f"  {'p<' + str(pmin) + ' (bloqueado)':<26}{nb:>5}{wrb:>7.1f}%"
              f"{'':>16}{pb:>9.2f}{(pb / nb if nb else 0):>10.2f}")
        print(f"  {'p>=' + str(pmin) + ' (opera)':<26}{na:>5}{wra:>7.1f}%"
              f"{'[' + str(ca[0]) + '-' + str(ca[1]) + ']':>16}{pa:>9.2f}"
              f"{(pa / na if na else 0):>10.2f}{tag}")

    nb, wrb, na, wra, ca, _pb, _pa = results[DECLARED_PCT]
    delta = wra - wrb
    ci_clears = ca[0] > wrb
    print()
    print(f"  celda pre-declarada p{DECLARED_PCT}: delta WR {delta:>5.1f}pp "
          f"(umbral C2 >= {C2_MIN_WR_DELTA_PP}pp)")
    print(f"  CI95 inferior del bucket que opera {ca[0]:.1f}% vs WR del bloqueado {wrb:.1f}%"
          f"  -> {'NO cruza' if ci_clears else 'CRUZA'}")
    if min(nb, na) < 25:
        print(f"  (!) n chico en un bucket (min {min(nb, na)}) - por el gate del proyecto (n>=25)")
        print("      esto NO alcanza para decidir, incluso si los umbrales dan bien.")
    c2 = (delta >= C2_MIN_WR_DELTA_PP) and ci_clears and min(nb, na) >= 25
    print(f"  [{'OK ' if c2 else 'NO '}] C2 - el percentil separa ganar de perder")
    return c2


# ======================================================================================
# modo offline (smoke test + censura). NO es la medicion.
# ======================================================================================
def report_offline():
    print("=" * 82)
    print("MODO OFFLINE - smoke test y censura de la muestra. NO es la medicion de C1/C2/C3.")
    print("=" * 82)
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    blocked = [r[0] for r in conn.execute(
        "SELECT atr_pips FROM rejected_signals WHERE reason='atr_floor' AND atr_pips IS NOT NULL")]
    # `avg_range_pips > 0`: la columna no se poblaba antes del 10-jun-2026 y quedaron 71
    # filas en 0. Meterlas en el bucket "<=8p" seria inventar 71 ventanas de chop que
    # nunca se midieron -> el corte en pips saldria falseado hacia el lado que ya se
    # queria demostrar. Se cuentan aparte.
    traded = [(r[0], float(r[1]), float(r[2])) for r in conn.execute(
        """SELECT created_at, avg_range_pips, mt5_pnl FROM trade_archive
           WHERE trigger_type='m15_structure' AND mt5_pnl IS NOT NULL
             AND avg_range_pips IS NOT NULL AND avg_range_pips > 0""")]
    unpopulated = conn.execute(
        """SELECT count(*) FROM trade_archive
           WHERE trigger_type='m15_structure' AND mt5_pnl IS NOT NULL
             AND (avg_range_pips IS NULL OR avg_range_pips = 0)""").fetchone()[0]
    conn.close()

    print()
    print(f"  ventanas BLOQUEADAS por el piso (rejected_signals, ATR medido en el momento): {len(blocked)}")
    if blocked:
        qs = statistics.quantiles(blocked, n=10) if len(blocked) >= 10 else []
        print(f"    ATR  min {min(blocked):.1f}p  mediana {statistics.median(blocked):.1f}p  "
              f"max {max(blocked):.1f}p")
        if qs:
            print(f"    deciles: {' '.join(f'{q:.1f}' for q in qs)}")
        over = sum(1 for b in blocked if b >= FIXED_FLOOR)
        print(f"    >= {FIXED_FLOOR}p: {over}  (deberia ser 0 - son las ventanas que el piso rechazo)")
        if over:
            print("    (!) hay filas >= piso entre las rechazadas: el piso cambio de valor")
            print("        durante el periodo (era 5.0 antes del 16-ago) o el log esta mezclando.")
    print()
    print(f"  trades m15 con ATR guardado al entrar (usable, >0): {len(traded)}")
    print(f"  descartados por avg_range_pips 0/NULL (columna sin poblar, pre 10-jun): "
          f"{unpopulated}")
    if traded:
        atrs = [t[1] for t in traded]
        print(f"    ATR  min {min(atrs):.1f}p  mediana {statistics.median(atrs):.1f}p  "
              f"max {max(atrs):.1f}p")
        lo = [t for t in traded if t[1] <= FIXED_FLOOR]
        hi = [t for t in traded if t[1] > FIXED_FLOOR]
        for name, sel in (('ATR <= 8p', lo), ('ATR  > 8p', hi)):
            n = len(sel)
            w = sum(1 for t in sel if t[2] > 0)
            pnl = sum(t[2] for t in sel)
            wr = 100.0 * w / n if n else 0
            ci = wilson(w, n)
            print(f"    {name}: n={n:<4} WR {wr:>5.1f}%  CI95 [{ci[0]}-{ci[1]}]  "
                  f"PnL {pnl:>8.2f}  ${(pnl / n if n else 0):.2f}/trade")
        print("    ^ reproduce el hallazgo de v3.55.0 con la data de hoy. Si NO se parece a")
        print("      27,8% / 51,6%, el hallazgo no aguanto el forward y eso se decide en la")
        print("      lectura del piso fijo, no aca.")
    print()
    print("  CENSURA: las dos muestras estan cortadas por el propio piso -")
    print("  rejected_signals son todas < piso y el archive todas >= piso del momento.")
    print("  Con eso NO se puede construir el percentil rolling (necesita TODAS las velas,")
    print("  operadas o no). Por eso la medicion real requiere MT5.")
    print()
    print("  Siguiente paso: cerrar AIdan.exe y correr")
    print("    python tools/measure_atr_percentile_floor.py --months 4")


def main():
    ap = argparse.ArgumentParser(
        description="Fase 1 del piso de ATR por percentil (read-only, no escribe nada).")
    ap.add_argument('--months', type=float, default=4.0,
                    help='meses de velas M15 a bajar de MT5 (default 4)')
    ap.add_argument('--offline', action='store_true',
                    help='sin MT5: smoke test + censura. NO es la medicion.')
    args = ap.parse_args()

    print(f"DB: {DB}  (read-only, este script no escribe NADA)")
    if args.offline:
        report_offline()
        return 0

    print("ATENCION: se va a inicializar MT5. Si AIdan.exe esta corriendo, cerralo primero.")
    candles, _off = fetch_m15(args.months)
    if not candles:
        return 1
    if len(candles) < DECLARED_LOOKBACK + ATR_PERIOD + 50:
        print(f"Historia insuficiente ({len(candles)} velas) para lookback {DECLARED_LOOKBACK}.")
        return 1

    c1, c3, series = report_frequency(candles)
    c2 = report_separation(series)

    print()
    print("=" * 82)
    print("VEREDICTO (criterios pre-declarados, celda p20/lookback100)")
    print("=" * 82)
    for name, val, txt in (('C1', c1, 'el percentil mantiene la frecuencia estable'),
                           ('C2', c2, 'separa ganar de perder (>=15pp y CI que no cruza)'),
                           ('C3', c3, 'no habilita lo mismo que el piso fijo')):
        mark = 'OK ' if val is True else ('NO ' if val is False else '?? ')
        print(f"  [{mark}] {name} - {txt}")
    if c2 is False:
        print()
        print("  C2 manda: si el percentil NO separa, no se implementa aunque proteja la")
        print("  frecuencia. Un filtro que no separa recorta para nada (principio rector).")
    elif c1 and c2 and c3:
        print()
        print("  Las 3 pasan => recien ahi tiene sentido la Fase 2 (gate por percentil con")
        print("  perilla M15_ATR_MODE, default fixed, + rebuild). Y con la celda")
        print(f"  PRE-DECLARADA p{DECLARED_PCT}/lookback{DECLARED_LOOKBACK}, no con la mejor de la grilla.")
    else:
        print()
        print("  No pasan las 3 => no se toca el vivo. La grilla de arriba dice si el")
        print("  resultado es una meseta (volver a mirar con mas historia) o una aguja (ruido).")
    return 0


if __name__ == '__main__':
    sys.exit(main())
