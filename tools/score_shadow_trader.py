"""
score_shadow_trader.py — Scorer READ-mostly del SHADOW TRADER LLM (v3.60.0).

Completa el outcome de cada decision en PAPEL de `shadow_trader_log` (la unica
tabla que escribe — es SU tabla) y evalua el gate pre-declarado:

  kind='open' (CALL/PUT): drift direccional NETO de friccion (1,3p) al horizonte
    (45 min), sobre velas M5 de MT5, SIN re-simular SL/TP (doctrina del proyecto).
    GATE: n>=25 con outcome; media Y mediana > 0. Con n>=40 sin pasar =>
    SHADOW_TRADER_MODE=off, no buscarle la vuelta.
    (NONE tambien se puntua — drift absoluto — como contexto, no como gate.)

  kind='manage' (CLOSE): "ahorro" = pips_at_decision - pips finales del trade
    (broker-truth: ticket -> auto_strategies.mt5_ticket -> trade_archive por
    strategy_id — trade_archive NO tiene columna de ticket). Positivo = cerrar ahi
    hubiera salvado pips; negativo = hubiera cortado recorrido a favor.
    GATE: n>=15 CLOSE resueltos; ahorro neto total > 0.
    (HOLD se reporta como contexto: pips finales - pips al decidir.)

Ojo al leer (el sesgo conocido): que los HOLD terminen bien NO es evidencia de
skill — arrastra el sesgo de que la mayoria de los trades siguen su curso. Lo
que el LLM tiene que demostrar es que sus CLOSE salvan plata y sus OPEN ganan
neto. Mismo principio que la retrospectiva (aligned no cuenta, contrarian si).

Requiere MT5 para los 'open'. `--dry-run` no escribe outcomes.
"""
import argparse
import os
import sqlite3
import statistics
import sys
import time as _time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mt5_server_offset import mt5_offset_s, StaleTickError  # noqa: E402

DB = os.path.join(os.environ['APPDATA'], 'AIdan', 'state', 'financial_news.db')
PIP = 0.0001
FRICTION_PIPS = 1.3   # comision round-trip declarada del proyecto
MIN_N_OPEN = 25
GIVE_UP_N_OPEN = 40
MIN_N_CLOSE = 15


def _parse_ar(ts):
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(str(ts).split('+')[0].strip(), fmt)
        except ValueError:
            continue
    return None


def score_open_pending(dry_run=False, server_offset_hours=None):
    """Outcome forward de los 'open' (mismo mecanismo que score_rejected_signals)."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"MT5 init failed: {mt5.last_error()} — los 'open' quedan pendientes.")
        return 0
    try:
        offset_s = mt5_offset_s(mt5, override_hours=server_offset_hours)
    except StaleTickError as e:
        print(f"[offset] {e}\n  -> los 'open' quedan pendientes (no se escribe nada).")
        mt5.shutdown()
        return 0

    conn = sqlite3.connect(DB, timeout=15.0)
    rows = conn.execute("""
        SELECT id, decision, price, horizon_min, created_at
        FROM shadow_trader_log
        WHERE kind='open' AND scored_at IS NULL""").fetchall()

    scored = 0
    for rid, decision, price, horizon, created_at in rows:
        ar_dt = _parse_ar(created_at)
        if ar_dt is None or not price:
            continue
        horizon = horizon or 45
        utc_start = ar_dt + timedelta(hours=3)   # AR = UTC-3
        if datetime.utcnow() < utc_start + timedelta(minutes=horizon + 5):
            continue  # horizonte no vencido
        srv_start = utc_start + timedelta(seconds=offset_s)
        srv_end = srv_start + timedelta(minutes=horizon)
        rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, srv_start, srv_end)
        if rates is None or len(rates) == 0:
            continue  # finde/feriado: queda pendiente
        close = float(rates[-1]['close'])
        net = (close - price) / PIP
        if decision == 'CALL':
            outcome = round(net - FRICTION_PIPS, 1)
            detail = 'net_dir-friction'
        elif decision == 'PUT':
            outcome = round(-net - FRICTION_PIPS, 1)
            detail = 'net_dir-friction'
        else:  # NONE: drift absoluto como contexto (¿que se dejo pasar?)
            outcome = round(abs(net), 1)
            detail = 'abs_drift(none)'
        if not dry_run:
            conn.execute("""UPDATE shadow_trader_log
                SET outcome_pips=?, outcome_detail=?, scored_at=datetime('now')
                WHERE id=?""", (outcome, detail, rid))
        scored += 1
    if not dry_run:
        conn.commit()
    conn.close()
    mt5.shutdown()
    return scored


def score_manage_pending(dry_run=False):
    """Outcome de los 'manage': broker-truth del trade cerrado (trade_archive)."""
    conn = sqlite3.connect(DB, timeout=15.0)
    rows = conn.execute("""
        SELECT s.id, s.decision, s.pips_at_decision, t.pips
        FROM shadow_trader_log s
        JOIN auto_strategies a ON a.mt5_ticket = s.ticket
        JOIN trade_archive t ON t.strategy_id = a.id
        WHERE s.kind='manage' AND s.scored_at IS NULL
          AND s.ticket IS NOT NULL AND t.pips IS NOT NULL""").fetchall()
    scored = 0
    for rid, decision, pips_dec, final_pips in rows:
        if pips_dec is None:
            continue
        if decision == 'CLOSE':
            # positivo = cerrar ahi hubiera SALVADO pips
            outcome = round(float(pips_dec) - float(final_pips), 1)
            detail = 'saved(close@dec - final)'
        else:  # HOLD: lo que el resto del trade aporto (contexto, no gate)
            outcome = round(float(final_pips) - float(pips_dec), 1)
            detail = 'held(final - @dec)'
        if not dry_run:
            conn.execute("""UPDATE shadow_trader_log
                SET outcome_pips=?, outcome_detail=?, scored_at=datetime('now')
                WHERE id=?""", (outcome, detail, rid))
        scored += 1
    if not dry_run:
        conn.commit()
    conn.close()
    return scored


def report():
    conn = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    total = conn.execute("SELECT COUNT(*) FROM shadow_trader_log").fetchone()[0]
    print('\nSHADOW TRADER LLM — %d decisiones registradas' % total)
    if total == 0:
        print('  Nada todavia. Si AIdan corre hace >1h con mercado abierto y sigue')
        print('  en 0, el loop puede estar muerto: buscar "shadow trader" en aidan.log.')
        conn.close()
        return

    per_kind = conn.execute("""
        SELECT kind, decision, COUNT(*),
               SUM(CASE WHEN scored_at IS NOT NULL THEN 1 ELSE 0 END)
        FROM shadow_trader_log GROUP BY kind, decision""").fetchall()
    for kind, decision, n, n_sc in per_kind:
        print('  %-7s %-5s n=%-4d con outcome=%d' % (kind, decision, n, n_sc))

    # ── GATE 1: open direccionales ──────────────────────────────────────────
    vals = [r[0] for r in conn.execute("""
        SELECT outcome_pips FROM shadow_trader_log
        WHERE kind='open' AND decision IN ('CALL','PUT')
          AND scored_at IS NOT NULL AND outcome_pips IS NOT NULL""")]
    print('\n[GATE open] CALL/PUT con outcome: n=%d' % len(vals))
    if vals:
        mean = sum(vals) / len(vals)
        med = statistics.median(vals)
        pos = sum(1 for v in vals if v > 0)
        print('  pips netos (friccion %.1fp descontada): media=%+.2f mediana=%+.2f  >0: %d/%d'
              % (FRICTION_PIPS, mean, med, pos, len(vals)))
        if len(vals) < MIN_N_OPEN:
            print('  -> n<%d: SIN VEREDICTO (no concluir).' % MIN_N_OPEN)
        elif mean > 0 and med > 0:
            print('  -> PASA el gate (media y mediana > 0). Discutir el paso siguiente')
            print('     con el user — que sigue siendo UNA perilla chica, no el volante.')
        elif len(vals) >= GIVE_UP_N_OPEN:
            print('  -> NO PASA con n>=%d => SHADOW_TRADER_MODE=off. El LLM no' % GIVE_UP_N_OPEN)
            print('     demostro edge direccional, consistente con lo ya medido (news).')
        else:
            print('  -> NO PASA todavia (n=%d); a n>=%d se decide.' % (len(vals), GIVE_UP_N_OPEN))

    # contexto: que dejo pasar cuando dijo NONE
    nones = [r[0] for r in conn.execute("""
        SELECT outcome_pips FROM shadow_trader_log
        WHERE kind='open' AND decision='NONE' AND scored_at IS NOT NULL
          AND outcome_pips IS NOT NULL""")]
    if nones:
        print('  [contexto NONE] n=%d, drift absoluto mediano=%.1fp (>%.1fp = dejaba recorrido)'
              % (len(nones), statistics.median(nones), FRICTION_PIPS))

    # ── GATE 2: manage CLOSE ────────────────────────────────────────────────
    closes = [r[0] for r in conn.execute("""
        SELECT outcome_pips FROM shadow_trader_log
        WHERE kind='manage' AND decision='CLOSE'
          AND scored_at IS NOT NULL AND outcome_pips IS NOT NULL""")]
    print('\n[GATE manage] CLOSE resueltos: n=%d' % len(closes))
    if closes:
        tot = sum(closes)
        med = statistics.median(closes)
        print('  ahorro (pips al decidir - finales): total=%+.1f mediana=%+.1f' % (tot, med))
        if len(closes) < MIN_N_CLOSE:
            print('  -> n<%d: SIN VEREDICTO.' % MIN_N_CLOSE)
        elif tot > 0:
            print('  -> PASA: sus CLOSE hubieran salvado pips netos.')
        else:
            print('  -> NO PASA: sus CLOSE cortaban recorrido a favor.')

    holds = [r[0] for r in conn.execute("""
        SELECT outcome_pips FROM shadow_trader_log
        WHERE kind='manage' AND decision='HOLD'
          AND scored_at IS NOT NULL AND outcome_pips IS NOT NULL""")]
    if holds:
        print('  [contexto HOLD] n=%d, aporte posterior mediano=%+.1fp '
              '(NO es evidencia de skill: sesgo de continuidad)' %
              (len(holds), statistics.median(holds)))

    conn.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--server-offset-hours', type=float, default=None,
                    help='offset server-UTC a mano (mercado cerrado sin cache). ICMarkets: 3 verano / 2 invierno')
    args = ap.parse_args()
    n1 = score_manage_pending(dry_run=args.dry_run)
    try:
        n2 = score_open_pending(dry_run=args.dry_run, server_offset_hours=args.server_offset_hours)
    except ImportError:
        print('MetaTrader5 no disponible — los open quedan pendientes.')
        n2 = 0
    print('Outcomes calculados en esta corrida: %d manage + %d open%s'
          % (n1, n2, ' (dry-run, no escrito)' if args.dry_run else ''))
    report()
