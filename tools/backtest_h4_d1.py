"""
backtest_h4_d1.py — Paso 0 (READ-ONLY) para la propuesta de swing H4/D1.

Pregunta que responde: si el scanner de structure que ya existe se corre sobre
velas H4 y D1, ¿aparece un edge, y sobrevive a la comisión?

NO toca produccion. NO escribe en la DB. Solo lee velas de MT5.

Dos variantes por timeframe (esto es la mitad del experimento):
  - naive  : las constantes en pips quedan como estan (calibradas para M5).
             En H4 una ventana de 7p sobre una vela de 23p es sub-vela ->
             el scanner dispara fuera de fase. Es el problema "Grupo B".
  - scaled : las constantes en pips se multiplican por ATR_tf/ATR_M5.

SL/TP relativos al ATR del momento (sin lookahead: el ATR se calcula con velas
CERRADAS hasta la de entrada inclusive; se entra al close de esa vela).

Caveats heredados del backtest M15/H1 (siguen valiendo):
  - Solo trigger 'structure' (sin news/smc-live/pre_planned).
  - Sin spread variable, slippage ni latencia.
  - Sin los filtros del loop vivo (SIM A, counter-HTF, sesiones, cooldown,
    warmup) => la frecuencia real seria MENOR que la de aca.
  - htf_bias = None (no derivado de SMC live).
  - Un backtest tipico INFLA 20-30% vs real con friccion.
  - Resultados INDICATIVOS, no decisivos.

═══ v2 (16-ago-2026): DE QUE BASELINE HABLAMOS ══════════════════════════════

La corrida original del 13-ago (242 señales, PF neto 1,40) NO es comparable
1-a-1 contra el shadow del track D1, por dos razones que salieron de la
revision adversarial. Las dos estan resueltas aca con flags:

  (a) PARAMS. El backtest corrio con DEFAULT_PARAMS (via _FakeTuner), donde
      breakout_dist_max = 15. La DB viva tiene 7 => en vivo la ventana es la
      MITAD y la poblacion de señales es mas chica. --params live lee los
      params reales de optimizer_params (READ-ONLY, ultima iteracion).

  (b) SESION. El paso 7 de dynamic_conf suma get_session_info()['conf_adj'],
      que lee datetime.now(timezone.utc) — reloj REAL. El backtest solo
      parcheaba time.time(), asi que las 242 señales recibieron TODAS el mismo
      ajuste: el de la hora en que se corrio el script. Es un corrimiento
      constante de la confianza contra un min_confidence=60, o sea que mueve
      la poblacion entera.

      En vivo el valor depende de a que hora el loop VE la vela nueva
      (rollover del broker si AIdan esta prendido, hora de arranque si no).
      Eso no se puede reconstruir honestamente => no se inventa un 'auto':
      --session sweep corre las cuatro sesiones y reporta el RANGO. Si el
      resultado aguanta las cuatro, el baseline es robusto a esta perilla; si
      solo vive en una, el titular dependia de la hora del reloj.

  Reproducir el titular viejo:  --params default --session frozen
  Baseline para comparar D1  :  --params live    --session sweep

Uso:
    python tools/backtest_h4_d1.py
    python tools/backtest_h4_d1.py --tf D1 --variant scaled
    python tools/backtest_h4_d1.py --tf D1 --variant naive --params live --session sweep
"""
import argparse
import csv
import json
import logging
import os
import statistics as stats
import sys
from contextlib import nullcontext as _nullcontext
from copy import deepcopy
from datetime import datetime
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

PIP = 0.0001

# Costo por trade, en pips-equivalente. IC Markets Raw ~$3.50/lote/lado =>
# ~0.7p a lote 0.01 (pip value $0.10) + spread raw ~0.1p.
COMMISSION_PIPS = 0.8
COMMISSION_PIPS_PESIMISTA = 1.3

# Constantes del scanner que estan expresadas EN PIPS y por lo tanto asumen
# la escala de M5. Son las que se re-escalan en la variante 'scaled'.
PIP_PARAMS = [
    'breakout_dist_max', 'breakdown_dist_max',
    'rsi_proximity_pips', 'bb_proximity_pips', 'bb_sr_proximity_pips',
    'momentum_consol_max_avg', 'momentum_min_body_pips',
    'trend_cont_proximity_pips', 'level_proximity_pips',
    'sl_min_pips_high_vol', 'sl_min_pips_low_vol',
]

TF_SPEC = {
    # label: (mt5 timeframe attr, minutos por vela, velas a traer)
    'H4': ('TIMEFRAME_H4', 240, 2000),
    'D1': ('TIMEFRAME_D1', 1440, 2000),
}

# Perfil propuesto por timeframe. SL/TP relativos al ATR del momento.
PROFILES = {
    'H4': {
        'sl_atr_mult': 1.2,
        'rr': 2.0,
        'hold_candles': 12,      # 12 velas H4 = 48h de vida maxima
        'min_confidence': 60,
    },
    'D1': {
        'sl_atr_mult': 1.2,
        'rr': 2.0,
        'hold_candles': 10,      # 10 velas D1 = 2 semanas
        'min_confidence': 60,
    },
}


# Las 4 sesiones tal cual las define TechnicalAnalyzer.get_session_info().
# Se replican aca a proposito (no se importan): si alguien cambia la tabla de
# sesiones en produccion, este backtest tiene que FALLAR el chequeo de abajo,
# no seguir midiendo con la tabla vieja en silencio.
SESSIONS = {
    'london':  {'session': 'london',    'conf_adj': 8,   'spread_est': 0.6, 'label': 'London'},
    'overlap': {'session': 'overlap',   'conf_adj': 5,   'spread_est': 0.5, 'label': 'London/NY Overlap'},
    'ny':      {'session': 'ny',        'conf_adj': 0,   'spread_est': 0.8, 'label': 'NY'},
    'off':     {'session': 'off_hours', 'conf_adj': -10, 'spread_est': 1.5, 'label': 'Off-hours'},
}


def assert_sessions_match_prod():
    """Verifica que SESSIONS siga siendo la tabla real de produccion.

    get_session_info() lee el reloj, asi que no se puede pedir 'la sesion X':
    se la recorre parcheando la hora UTC y se compara el dict devuelto.
    """
    from datetime import datetime as _dt, timezone as _tz
    from src.analyzer.technical import TechnicalAnalyzer
    import src.analyzer.technical as tech_mod

    horas = {'london': 9, 'overlap': 14, 'ny': 18, 'off': 22}
    vistos = {}
    for name, hour in horas.items():
        fake = _dt(2026, 1, 5, hour, 0, tzinfo=_tz.utc)

        class _FakeDT:
            @staticmethod
            def now(tz=None):
                return fake

        with patch.object(tech_mod, 'datetime', _FakeDT):
            vistos[name] = TechnicalAnalyzer.get_session_info()

    for name, esperado in SESSIONS.items():
        if vistos[name] != esperado:
            raise RuntimeError(
                f"La tabla de sesiones de produccion cambio para '{name}': "
                f"prod={vistos[name]} vs backtest={esperado}. "
                f"Actualizar SESSIONS antes de volver a medir.")


def load_live_params(logger):
    """Params reales de la DB viva (READ-ONLY, ultima iteracion del AutoTuner).

    Se usa el mismo AutoTuner que corre en produccion en vez de leer la tabla
    a mano: si el tuner hace merge con defaults, normaliza tipos o cambia de
    tabla, este backtest se entera solo.
    """
    from src.optimizer.auto_tuner import AutoTuner, DEFAULT_PARAMS
    from src.common.db import DB_PATH
    p = AutoTuner(logger, DB_PATH).get_params()
    if not p:
        raise RuntimeError("optimizer_params vino vacio; no se puede usar --params live")
    diff = {k: (DEFAULT_PARAMS.get(k, '<falta>'), v)
            for k, v in p.items() if DEFAULT_PARAMS.get(k, '<falta>') != v}
    return dict(p), diff


def setup_logger():
    logger = logging.getLogger("backtest_h4_d1")
    logger.setLevel(logging.CRITICAL)
    logger.addHandler(logging.NullHandler())
    return logger


def fetch_mt5_history(tf_attr, count):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    tf = getattr(mt5, tf_attr)
    rates = mt5.copy_rates_from_pos("EURUSD", tf, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No candles for {tf_attr}: {mt5.last_error()}")
    out = []
    for r in rates:
        out.append({
            'open': float(r['open']), 'high': float(r['high']),
            'low': float(r['low']), 'close': float(r['close']),
            'datetime': str(datetime.utcfromtimestamp(int(r['time']))),
            'time_unix': int(r['time']),
        })
    return out


def atr_at(candles, idx, period=14):
    """ATR proxy = media del rango de las <period> velas CERRADAS hasta idx.
    Sin lookahead: la vela idx esta cerrada en el momento de la entrada."""
    lo = max(0, idx - period + 1)
    rngs = [(c['high'] - c['low']) / PIP for c in candles[lo:idx + 1]]
    return stats.mean(rngs) if rngs else 0.0


def simulate(entry_idx, candles, direction, sl_pips, tp_pips, hold_candles):
    """Camina hacia adelante buscando SL/TP; si no, cierra al final del hold.
    Conservador: si una vela toca SL y TP, asume SL primero."""
    entry = candles[entry_idx]['close']
    if direction == 'CALL':
        sl_price, tp_price = entry - sl_pips * PIP, entry + tp_pips * PIP
    else:
        sl_price, tp_price = entry + sl_pips * PIP, entry - tp_pips * PIP

    end = min(entry_idx + 1 + hold_candles, len(candles))
    for j in range(entry_idx + 1, end):
        c = candles[j]
        if direction == 'CALL':
            sl_hit, tp_hit = c['low'] <= sl_price, c['high'] >= tp_price
        else:
            sl_hit, tp_hit = c['high'] >= sl_price, c['low'] <= tp_price
        if sl_hit:
            return {'result': 'sl', 'exit_idx': j, 'pips': -float(sl_pips)}
        if tp_hit:
            return {'result': 'tp', 'exit_idx': j, 'pips': float(tp_pips)}

    last = candles[end - 1]['close']
    pips = (last - entry) / PIP if direction == 'CALL' else (entry - last) / PIP
    return {'result': 'hold_end', 'exit_idx': end - 1, 'pips': round(pips, 1)}


def build_scaled_params(base, factor):
    p = dict(base)
    for k in PIP_PARAMS:
        if k in p:
            p[k] = round(p[k] * factor, 2)
    return p


def run(tf_label, variant, logger, verbose=True, params_source='default',
        session='frozen', candles=None):
    from src.analyzer.technical import TechnicalAnalyzer
    from src.optimizer.auto_tuner import DEFAULT_PARAMS
    import src.analyzer.technical as tech_mod

    tf_attr, tf_minutes, count = TF_SPEC[tf_label]
    prof = PROFILES[tf_label]

    # candles se puede pasar de afuera para que un sweep de 4 sesiones no baje
    # 4 veces las mismas 2000 velas (y no mida sobre snapshots distintos).
    if candles is None:
        candles = fetch_mt5_history(tf_attr, count)
    warmup = 100

    # Factor de escala = cuanto mas grande es la vela de este TF vs M5.
    atr_tf = stats.median([atr_at(candles, i) for i in range(warmup, len(candles))])
    atr_m5 = 2.0  # mediana medida de ATR14 en M5 (ver probe)
    factor = atr_tf / atr_m5

    if params_source == 'live':
        base, param_diff = load_live_params(logger)
    else:
        base, param_diff = dict(DEFAULT_PARAMS), {}
    params = base if variant == 'naive' else build_scaled_params(base, factor)

    if verbose:
        print(f"\n{'='*72}")
        print(f"  {tf_label} / variante={variant} / params={params_source} / sesion={session}")
        print(f"{'='*72}")
        print(f"  velas: {len(candles)}  |  {candles[0]['datetime'][:10]} -> {candles[-1]['datetime'][:10]}")
        if params_source == 'live':
            if param_diff:
                print("  params vivos que DIFIEREN del default:")
                for k, (d, v) in sorted(param_diff.items()):
                    print(f"    {k:26s} default={d} -> live={v}")
            else:
                print("  params vivos == DEFAULT_PARAMS (sin diferencias)")
        if session == 'frozen':
            print("  conf_adj de sesion: RELOJ REAL (constante para toda la corrida)")
        else:
            print(f"  conf_adj de sesion: {SESSIONS[session]['conf_adj']:+d} "
                  f"({SESSIONS[session]['label']}) forzado en las {len(candles)-warmup-1} evaluaciones")
        print(f"  ATR mediano {tf_label}: {atr_tf:.1f}p  (x{factor:.1f} vs M5)")
        print(f"  SL = {prof['sl_atr_mult']}xATR  TP = SL x{prof['rr']}  hold = {prof['hold_candles']} velas")
        if variant == 'scaled':
            print(f"  breakout_dist_max: {base['breakout_dist_max']}p -> {params['breakout_dist_max']}p")

    analyzer = TechnicalAnalyzer(logger)
    analyzer._cache_ttl = 0
    analyzer._dedup_window_sec = tf_minutes * 60 * 2

    signals = []

    class _FakeTuner:
        def __init__(self, *a, **k):
            pass

        def get_params(self):
            return dict(params)

    # Paso 7 de dynamic_conf. 'frozen' = como corria antes (reloj real, o sea
    # un mismo conf_adj para toda la corrida); cualquier otra = forzada.
    if session == 'frozen':
        session_patch = _nullcontext()
    else:
        _fixed = dict(SESSIONS[session])
        session_patch = patch.object(
            TechnicalAnalyzer, 'get_session_info',
            staticmethod(lambda: dict(_fixed)))

    for i in range(warmup, len(candles) - 1):
        sl_ = candles[max(0, i - warmup + 1):i + 1]
        analyzer._fetch_candles = lambda s=sl_: deepcopy(s)
        analyzer._cache.clear()
        try:
            with patch('src.optimizer.auto_tuner.AutoTuner', _FakeTuner), \
                 patch.object(tech_mod.time, 'time', return_value=candles[i]['time_unix']), \
                 session_patch:
                sigs = analyzer.detect_structure_signals(
                    min_confidence=prof['min_confidence'])
        except Exception:
            continue

        for s in sigs:
            a = atr_at(candles, i)
            if a <= 0:
                continue
            sl_pips = round(a * prof['sl_atr_mult'], 1)
            tp_pips = round(sl_pips * prof['rr'], 1)
            out = simulate(i, candles, s['direction'], sl_pips, tp_pips,
                           prof['hold_candles'])
            # Noches en mercado: define el costo de swap, que en D1 no es
            # despreciable (-0.82p/noche comprado, +0.14p/noche vendido).
            hold_days = (candles[out['exit_idx']]['time_unix']
                         - candles[i]['time_unix']) / 86400.0
            signals.append({
                'tf': tf_label, 'variant': variant, 'step': i,
                'datetime': candles[i]['datetime'],
                'direction': s['direction'],
                'confidence': s.get('confidence', 0),
                'setup_type': s.get('setup_type', '?'),
                'atr': round(a, 1), 'sl_pips': sl_pips, 'tp_pips': tp_pips,
                'hold_days': round(hold_days, 1),
                **out,
            })

    res = aggregate(tf_label, variant, signals, candles, tf_minutes, atr_tf, factor)
    res['params_source'] = params_source
    res['session'] = session
    res['param_diff'] = {k: {'default': d, 'live': v} for k, (d, v) in param_diff.items()}
    return res


def _pf(sigs, cost):
    gw = sum(s['pips'] - cost for s in sigs if s['pips'] - cost > 0)
    gl = abs(sum(s['pips'] - cost for s in sigs if s['pips'] - cost < 0))
    return round(gw / gl, 2) if gl > 0 else float('inf')


def aggregate(tf_label, variant, sigs, candles, tf_minutes, atr_tf, factor):
    n = len(sigs)
    span_days = (candles[-1]['time_unix'] - candles[100]['time_unix']) / 86400.0
    res = {
        'tf': tf_label, 'variant': variant, 'signals': n,
        'span_days': round(span_days, 0),
        'atr_median': round(atr_tf, 1), 'scale_factor': round(factor, 1),
    }
    if n == 0:
        res['note'] = 'sin señales'
        return res

    gross = sum(s['pips'] for s in sigs)
    net = sum(s['pips'] - COMMISSION_PIPS for s in sigs)
    net_pes = sum(s['pips'] - COMMISSION_PIPS_PESIMISTA for s in sigs)
    wins = [s for s in sigs if s['pips'] - COMMISSION_PIPS > 0]

    res.update({
        'trades_por_mes': round(n / (span_days / 30.0), 1),
        'wr_neto_pct': round(len(wins) / n * 100, 1),
        'pf_bruto': _pf(sigs, 0.0),
        'pf_neto': _pf(sigs, COMMISSION_PIPS),
        'pf_neto_pesimista': _pf(sigs, COMMISSION_PIPS_PESIMISTA),
        'pips_brutos': round(gross, 1),
        'pips_netos': round(net, 1),
        'pips_netos_pesimista': round(net_pes, 1),
        'avg_pips_neto': round(net / n, 2),
        'sl_hit': sum(1 for s in sigs if s['result'] == 'sl'),
        'tp_hit': sum(1 for s in sigs if s['result'] == 'tp'),
        'hold_end': sum(1 for s in sigs if s['result'] == 'hold_end'),
        'sl_medio_pips': round(stats.mean([s['sl_pips'] for s in sigs]), 1),
        'drag_comision_pct': round(
            COMMISSION_PIPS / stats.mean([abs(s['pips']) for s in sigs]) * 100, 1),
    })

    # Walk-forward: mitad vieja vs mitad nueva. Si el edge solo vive en una
    # mitad, es ruido de periodo y no se puede confiar.
    mid = len(sigs) // 2
    for tag, part in (('primera_mitad', sigs[:mid]), ('segunda_mitad', sigs[mid:])):
        if part:
            res[tag] = {
                'n': len(part),
                'pf_neto': _pf(part, COMMISSION_PIPS),
                'pips_netos': round(sum(s['pips'] - COMMISSION_PIPS for s in part), 1),
                'desde': part[0]['datetime'][:10], 'hasta': part[-1]['datetime'][:10],
            }

    by_setup = {}
    for s in sigs:
        d = by_setup.setdefault(s['setup_type'], {'n': 0, 'pips': 0.0, 'w': 0})
        d['n'] += 1
        d['pips'] += s['pips'] - COMMISSION_PIPS
        if s['pips'] - COMMISSION_PIPS > 0:
            d['w'] += 1
    for k, d in by_setup.items():
        d['pips'] = round(d['pips'], 1)
        d['wr'] = round(d['w'] / d['n'] * 100, 1)
    res['by_setup'] = by_setup
    res['_signals'] = sigs
    return res


def print_res(r):
    if r.get('signals', 0) == 0:
        print(f"  -> SIN SEÑALES en {r['span_days']:.0f} dias")
        return
    print(f"  señales           : {r['signals']}  ({r['trades_por_mes']}/mes) en {r['span_days']:.0f} dias")
    print(f"  SL medio          : {r['sl_medio_pips']}p   |  drag comision: {r['drag_comision_pct']}% del movimiento medio")
    print(f"  salidas           : TP {r['tp_hit']} / SL {r['sl_hit']} / fin-hold {r['hold_end']}")
    print(f"  WR neto           : {r['wr_neto_pct']}%")
    print(f"  PF bruto -> neto  : {r['pf_bruto']} -> {r['pf_neto']}  (pesimista {r['pf_neto_pesimista']})")
    print(f"  pips netos        : {r['pips_netos']:+.1f}  (avg {r['avg_pips_neto']:+.2f}/trade)")
    for tag in ('primera_mitad', 'segunda_mitad'):
        if tag in r:
            h = r[tag]
            print(f"  {tag:14s}: n={h['n']:3d}  PF={h['pf_neto']:<5} pips={h['pips_netos']:+8.1f}  [{h['desde']} -> {h['hasta']}]")
    print("  por setup:")
    for k, d in sorted(r['by_setup'].items(), key=lambda x: -x[1]['n']):
        print(f"    {k:28s} n={d['n']:3d} wr={d['wr']:5.1f}% pips={d['pips']:+8.1f}")


def print_sweep(rows):
    """Tabla comparativa de las 4 sesiones. Lo que importa NO es cual gana:
    es si el signo aguanta las cuatro."""
    print(f"\n  {'-'*66}")
    print("  SWEEP DE SESION (paso 7 de dynamic_conf) — ¿el edge depende de la hora?")
    print(f"  {'sesion':10s} {'conf_adj':>9s} {'n':>5s} {'WR':>7s} {'PF neto':>8s} {'avg p/trade':>12s}")
    for name, r in rows:
        if r.get('signals', 0) == 0:
            print(f"  {name:10s} {SESSIONS[name]['conf_adj']:>+9d} {'0':>5s}   (sin señales)")
            continue
        print(f"  {name:10s} {SESSIONS[name]['conf_adj']:>+9d} {r['signals']:>5d} "
              f"{r['wr_neto_pct']:>6.1f}% {r['pf_neto']:>8} {r['avg_pips_neto']:>+12.2f}")
    validos = [r for _, r in rows if r.get('signals', 0) > 0]
    if len(validos) >= 2:
        avgs = [r['avg_pips_neto'] for r in validos]
        pfs = [r['pf_neto'] for r in validos if r['pf_neto'] != float('inf')]
        todos_pos = all(a > 0 for a in avgs)
        print(f"\n  rango avg/trade : {min(avgs):+.2f} a {max(avgs):+.2f} pips")
        if pfs:
            print(f"  rango PF neto   : {min(pfs)} a {max(pfs)}")
        print(f"  veredicto       : {'ROBUSTO — positivo en las 4 sesiones' if todos_pos else 'FRAGIL — el signo cambia segun la hora'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', choices=['H4', 'D1', 'both'], default='both')
    ap.add_argument('--variant', choices=['naive', 'scaled', 'both'], default='both')
    ap.add_argument('--params', choices=['default', 'live'], default='live',
                    help="'live' = params reales de optimizer_params (default). "
                         "'default' = DEFAULT_PARAMS, reproduce el titular del 13-ago.")
    ap.add_argument('--session', choices=['frozen'] + list(SESSIONS) + ['sweep'],
                    default='sweep',
                    help="conf_adj del paso 7. 'sweep' corre las 4 (default). "
                         "'frozen' = reloj real, como corria antes.")
    args = ap.parse_args()

    logger = setup_logger()
    tfs = ['H4', 'D1'] if args.tf == 'both' else [args.tf]
    variants = ['naive', 'scaled'] if args.variant == 'both' else [args.variant]
    sessions = list(SESSIONS) if args.session == 'sweep' else [args.session]

    print("=" * 72)
    print(f"BACKTEST SWING H4/D1 (READ-ONLY) — {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 72)
    print("Solo 'structure'. Sin los filtros del loop vivo => frecuencia real MENOR.")
    print(f"Comision asumida: {COMMISSION_PIPS}p/trade (pesimista {COMMISSION_PIPS_PESIMISTA}p).")
    print(f"params={args.params}  |  sesion={args.session}")

    # Si la tabla de sesiones de produccion cambio, todo lo de abajo mide otra
    # cosa. Se corta ACA, antes de bajar 2000 velas.
    assert_sessions_match_prod()

    out = {}
    for tf in tfs:
        # Un solo fetch por timeframe: las variantes y las sesiones tienen que
        # medirse sobre EXACTAMENTE las mismas velas para ser comparables.
        try:
            candles = fetch_mt5_history(TF_SPEC[tf][0], TF_SPEC[tf][2])
        except Exception as e:
            print(f"  {tf} FALLO al bajar velas: {e}")
            continue
        for v in variants:
            rows = []
            for s in sessions:
                try:
                    r = run(tf, v, logger, params_source=args.params,
                            session=s, candles=candles)
                    print_res(r)
                    out[f"{tf}_{v}_{args.params}_{s}"] = r
                    rows.append((s, r))
                except Exception as e:
                    print(f"  {tf}/{v}/{s} FALLO: {e}")
                    import traceback
                    traceback.print_exc()
            if args.session == 'sweep' and rows:
                print_sweep(rows)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp = os.path.join(ROOT, f'backtest_h4_d1_{ts}.json')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump({k: {kk: vv for kk, vv in r.items() if kk != '_signals'}
                   for k, r in out.items()}, f, indent=2, ensure_ascii=False, default=str)
    cp = os.path.join(ROOT, f'backtest_h4_d1_{ts}.csv')
    with open(cp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        # params/session van en cada fila: sin eso, las 4 corridas del sweep
        # quedan mezcladas e indistinguibles en el CSV.
        w.writerow(['tf', 'variant', 'params', 'session', 'datetime', 'direction',
                    'confidence', 'setup_type', 'atr', 'sl_pips', 'tp_pips',
                    'result', 'pips', 'hold_days'])
        for r in out.values():
            for s in r.get('_signals', []):
                w.writerow([s['tf'], s['variant'], r['params_source'], r['session'],
                            s['datetime'], s['direction'],
                            s['confidence'], s['setup_type'], s['atr'],
                            s['sl_pips'], s['tp_pips'], s['result'], s['pips'],
                            s['hold_days']])
    print(f"\nJSON: {jp}\nCSV : {cp}")


if __name__ == '__main__':
    main()
