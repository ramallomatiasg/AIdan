"""
shadow_runner.py — Shadow mode worker para meta-optimization.

Por cada pending_change en estado 'shadow_validating', evalua signals reales
contra los filtros del cambio. Si el signal pasaria con esa config alterada,
lo simula y registra como shadow_trade. Esto permite validar empiricamente
si un cambio mejora performance ANTES de aplicarlo al live.

Workflow:
1. Hook: cuando se crea auto_strategy real -> `evaluate_signal_for_shadow_changes(signal)`
   Crea shadow_strategies (decision=taken/skipped) por cada pending_change.
2. Daemon thread: periodicamente busca shadow_strategies (decision=taken,
   sin shadow_trade) y simula outcome con candles posteriores.

Soporta change_types: block_setup_type, block_conf_bucket, block_hour_utc,
block_session, block_pattern, adjust_min_confidence_per_track,
adjust_setup_confidence (afecta la entrada del signal, no el outcome).
"""
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from threading import Thread

from src.common.db import (
    DB_PATH,
    get_pending_changes,
    insert_shadow_strategy,
    insert_shadow_trade,
)
from src.optimizer.sim_engine import (
    simulate_signal_outcome,
    simulate_pnl_dollars,
    fetch_candles_for_simulation,
)

logger = logging.getLogger(__name__)

TZ_AR = timezone(timedelta(hours=-3))


def _passes_change_filter(signal: dict, change_type: str, params: dict) -> tuple:
    """Returns (passes: bool, skip_reason: str|None).
    El filtro RECHAZA el signal cuando es del tipo a bloquear (es decir, si change_type='block_X'
    y signal tiene X, el filtro lo bloquea -> passes=False, skip_reason='block_X').

    Para tipos 'adjust_*' el signal siempre pasa (modifican confidence, no bloquean).
    """
    try:
        if change_type == 'block_setup_type':
            blocked = params.get('setup_type')
            if signal.get('setup_type') == blocked:
                return False, f'blocked_setup_{blocked}'

        elif change_type == 'block_conf_bucket':
            lo = params.get('bucket_lo', 0)
            hi = params.get('bucket_hi', 100)
            conf = signal.get('confidence', 0)
            if conf is not None and lo <= conf <= hi:
                return False, f'blocked_conf_{lo}-{hi}'

        elif change_type == 'block_hour_utc':
            hours = params.get('hours', [])
            hour = signal.get('hour_utc')
            if hour is not None and hour in hours:
                return False, f'blocked_hour_{hour}'

        elif change_type == 'block_session':
            sessions = params.get('sessions', [])
            sess = signal.get('session')
            if sess in sessions:
                return False, f'blocked_session_{sess}'

        elif change_type == 'block_pattern':
            pattern = params.get('pattern', '')  # "DIR|HTF|SESSION|TRIGGER"
            parts = pattern.split('|')
            if len(parts) == 4:
                d, h, s, t = parts
                if (signal.get('direction') == d and
                        signal.get('htf_bias') == h and
                        signal.get('session') == s and
                        signal.get('trigger_type') == t):
                    return False, f'blocked_pattern_{pattern}'

        elif change_type == 'adjust_min_confidence_per_track':
            track = params.get('track', '').upper()  # M5, M15, H1
            new_min = params.get('value', 0)
            sig_track = _infer_track_from_signal(signal)
            if sig_track == track and (signal.get('confidence', 0) or 0) < new_min:
                return False, f'below_new_min_conf_{new_min}_for_{track}'

        # adjust_setup_confidence + tune_optimizer_param: no bloquean, modifican
        # confidence/params pero el signal pasa. No producen shadow_strategies.

        return True, None
    except Exception as e:
        logger.warning(f"shadow filter eval error ({change_type}): {e}")
        return True, None  # En duda, pasa


def _infer_track_from_signal(signal: dict) -> str:
    """Infiere track (M5/M15/H1) desde trigger_type del signal."""
    tt = (signal.get('trigger_type') or '').lower()
    if tt.startswith('m15_'):
        return 'M15'
    if tt.startswith('h1_'):
        return 'H1'
    return 'M5'  # default (structure, news, smc, pre_planned, calendar)


def evaluate_signal_for_shadow_changes(signal: dict, base_strategy_id: int = None):
    """Hook: cuando un signal real se crea (auto_strategy INSERT), evaluar contra todos
    los pending_changes con status='shadow_validating' y crear shadow_strategy por cada uno.

    Args:
        signal: dict con keys: direction, entry_price, stop_loss, take_profit, sl_pips, tp_pips,
                confidence, trigger_type, setup_type, session, hour_utc, day_of_week, htf_bias,
                avg_range_pips
        base_strategy_id: id del auto_strategy correspondiente (opcional)
    """
    try:
        validating = get_pending_changes(status='shadow_validating', limit=50)
        if not validating:
            return  # Nada en shadow validation -> noop

        for change in validating:
            try:
                params = json.loads(change.get('params_json', '{}'))
            except Exception:
                continue

            passes, skip_reason = _passes_change_filter(signal, change['change_type'], params)
            decision = 'taken' if passes else 'skipped'

            insert_shadow_strategy(
                pending_change_id=change['id'],
                base_strategy_id=base_strategy_id,
                config_overrides_json=change.get('params_json'),
                direction=signal.get('direction', ''),
                entry_price=signal.get('entry_price', 0),
                stop_loss=signal.get('stop_loss', 0),
                take_profit=signal.get('take_profit', 0),
                sl_pips=signal.get('sl_pips', 0),
                tp_pips=signal.get('tp_pips', 0),
                confidence=signal.get('confidence', 0),
                trigger_type=signal.get('trigger_type', ''),
                setup_type=signal.get('setup_type', ''),
                session=signal.get('session', ''),
                hour_utc=signal.get('hour_utc'),
                day_of_week=signal.get('day_of_week'),
                htf_bias=signal.get('htf_bias', ''),
                avg_range_pips=signal.get('avg_range_pips', 0),
                shadow_decision=decision,
                skip_reason=skip_reason,
            )
    except Exception as e:
        logger.warning(f"evaluate_signal_for_shadow_changes error: {e}")


def _infer_tf_minutes(trigger_type: str) -> int:
    """Map trigger_type -> minutos por vela del scanner."""
    tt = (trigger_type or '').lower()
    if tt.startswith('h1_'):
        return 60
    if tt.startswith('m15_'):
        return 15
    return 5  # M5 default


def _infer_interval_str(trigger_type: str) -> str:
    """Map trigger_type -> string interval para price_feed."""
    tt = (trigger_type or '').lower()
    if tt.startswith('h1_'):
        return '1h'
    if tt.startswith('m15_'):
        return '15min'
    return '5min'


def _infer_expiry_minutes(trigger_type: str) -> int:
    """Default expiry por track."""
    tt = (trigger_type or '').lower()
    if tt.startswith('h1_'):
        return 180  # H1_PROFILE.expiry_minutes
    if tt.startswith('m15_'):
        return 45   # M15_PROFILE.expiry_minutes
    return 15      # M5 default


def simulate_pending_shadow_trades(max_per_run: int = 20):
    """Busca shadow_strategies con decision='taken' y SIN shadow_trade asociado
    cuyo tiempo de expiry ya paso, y simula outcomes.

    Returns count de trades simulados.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Buscar shadow_strategies pendientes de simular
    cur.execute("""
        SELECT ss.* FROM shadow_strategies ss
        LEFT JOIN shadow_trades st ON st.shadow_strategy_id = ss.id
        WHERE ss.shadow_decision = 'taken' AND st.id IS NULL
        ORDER BY ss.created_at ASC LIMIT ?
    """, (max_per_run,))
    pending = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not pending:
        return 0

    simulated = 0
    for ss in pending:
        try:
            tt = ss.get('trigger_type', '')
            interval = _infer_interval_str(tt)
            tf_min = _infer_tf_minutes(tt)
            expiry_min = _infer_expiry_minutes(tt)

            # Verificar que paso suficiente tiempo desde el signal
            try:
                created_dt = datetime.fromisoformat(str(ss['created_at']).replace('Z', '+00:00'))
            except Exception:
                # Fallback: parse manual
                try:
                    created_dt = datetime.strptime(str(ss['created_at'])[:19], '%Y-%m-%d %H:%M:%S')
                except Exception:
                    continue

            now = datetime.utcnow() if created_dt.tzinfo is None else datetime.now(created_dt.tzinfo)
            elapsed_min = (now - created_dt).total_seconds() / 60
            if elapsed_min < expiry_min + tf_min:
                # Aun no paso el tiempo de expiry, esperar
                continue

            # Fetch suficientes candles posteriores al signal
            # Necesitamos: warmup (50 candles) + expiry_min/tf_min + buffer
            candles_needed = 50 + int(expiry_min / tf_min) + 5
            candles = fetch_candles_for_simulation(interval, count=candles_needed)

            if not candles or len(candles) < 25:
                logger.debug(f"shadow_simulate: insufficient candles ({len(candles) if candles else 0}) for ss#{ss['id']}")
                continue

            # Encontrar la vela del entry: buscar por timestamp/precio cercano
            entry_idx = _find_entry_idx_in_candles(candles, ss)
            if entry_idx is None:
                # No pudimos localizar la vela exacta -> usar fallback: vela mas cercana al timestamp
                entry_idx = _find_entry_idx_by_time(candles, created_dt)
            if entry_idx is None or entry_idx >= len(candles) - 2:
                logger.debug(f"shadow_simulate: cannot locate entry candle for ss#{ss['id']}")
                continue

            # Simular outcome
            result = simulate_signal_outcome(
                entry_idx=entry_idx,
                candles=candles,
                direction=ss.get('direction', ''),
                sl_pips=ss.get('sl_pips') or 0,
                tp_pips=ss.get('tp_pips') or 0,
                expiry_minutes=expiry_min,
                tf_minutes=tf_min,
            )

            # Estimar lot — usar lot del base_strategy si disponible
            lot = _get_base_strategy_lot(ss.get('base_strategy_id')) or 0.06
            pnl_usd = simulate_pnl_dollars(result.get('pips', 0), lot=lot)

            insert_shadow_trade(
                shadow_strategy_id=ss['id'],
                simulated_exit_price=result.get('exit_price', 0),
                simulated_pnl=pnl_usd,
                simulated_pips=result.get('pips', 0),
                sl_hit=1 if result.get('result') == 'sl' else 0,
                tp_hit=1 if result.get('result') == 'tp' else 0,
                expiry_hit=1 if result.get('result') == 'expiry' else 0,
                exit_reason=result.get('exit_reason', 'unknown'),
            )
            simulated += 1
        except Exception as e:
            logger.warning(f"shadow simulate error ss#{ss.get('id')}: {e}")
            continue

    if simulated:
        logger.info(f"Shadow runner: simulated {simulated} shadow trades")
    return simulated


def _find_entry_idx_in_candles(candles, shadow_strategy):
    """Buscar la vela donde el close coincide con entry_price del signal."""
    try:
        entry_price = float(shadow_strategy.get('entry_price') or 0)
        if not entry_price:
            return None
        # Tolerancia: 0.5 pip = 0.00005
        tol = 0.00005
        # Buscar de mas reciente hacia atras (signal cercano en tiempo)
        for i in range(len(candles) - 1, -1, -1):
            if abs(candles[i]['close'] - entry_price) <= tol:
                return i
        return None
    except Exception:
        return None


def _find_entry_idx_by_time(candles, target_dt):
    """Fallback: encontrar vela con datetime mas cercano al target_dt."""
    try:
        target_ts = target_dt.timestamp() if hasattr(target_dt, 'timestamp') else 0
        if not target_ts:
            return None
        best_idx = None
        best_diff = float('inf')
        for i, c in enumerate(candles):
            cdt_str = c.get('datetime', '')
            if not cdt_str:
                continue
            try:
                # Format: "2026-05-14 19:00:00+00:00" o "2026-05-14 19:00:00"
                cdt = datetime.fromisoformat(cdt_str.replace('Z', '+00:00'))
                cts = cdt.timestamp()
                diff = abs(cts - target_ts)
                if diff < best_diff:
                    best_diff = diff
                    best_idx = i
            except Exception:
                continue
        # Aceptar solo si <30 min de diferencia
        if best_diff < 1800:
            return best_idx
        return None
    except Exception:
        return None


def _get_base_strategy_lot(base_strategy_id):
    """Get mt5_lot from auto_strategies for shadow PnL calculation."""
    if not base_strategy_id:
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT mt5_lot FROM auto_strategies WHERE id = ?", (base_strategy_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def shadow_simulator_loop(stop_event, interval_sec=120):
    """Daemon loop: cada `interval_sec` simula shadow_trades pendientes.

    Args:
        stop_event: threading.Event para shutdown gracefully
        interval_sec: cada cuantos segundos correr la simulacion (default 2 min)
    """
    logger.info(f"Shadow simulator daemon started (interval {interval_sec}s)")
    while not stop_event.is_set():
        try:
            simulate_pending_shadow_trades(max_per_run=20)
        except Exception as e:
            logger.warning(f"shadow_simulator_loop error: {e}")
        # Sleep en chunks de 5s para responder a stop_event
        for _ in range(interval_sec // 5):
            if stop_event.is_set():
                break
            time.sleep(5)


def start_shadow_simulator_daemon(stop_event, interval_sec=120):
    """Helper: spawn daemon thread."""
    t = Thread(target=shadow_simulator_loop, args=(stop_event, interval_sec),
               daemon=True, name='ShadowSimulator')
    t.start()
    return t
