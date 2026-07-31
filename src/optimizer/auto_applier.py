"""
auto_applier.py — Daemon que:
1. Promueve pending_changes status='shadow_validating' → 'validated' si shadow PF mejora.
2. Aplica cambios 'validated' al live (status → 'applied').
3. Monitorea cambios 'applied': cada 50 trades post-apply compara PF live vs baseline.
   Si PF cayo > VALIDATION_DROP_PCT → auto-revert.
4. Cooldown 7 dias tras un revert antes de aplicar otro cambio.

Configuracion:
- SHADOW_MIN_TRADES: minimo shadow trades antes de validar (default 30)
- SHADOW_MIN_PF_DELTA: cuanto debe mejorar shadow PF vs baseline para validar (default +0.15)
- VALIDATION_DROP_PCT: cuanto debe bajar live PF post-apply para auto-revert (default 0.10 = 10%)
- MONITOR_INTERVAL_TRADES: cada cuantos trades chequear health post-apply (default 50)
- COOLDOWN_DAYS_AFTER_REVERT: dias de cooldown tras revert (default 7)
"""
import logging
import time
import sqlite3
from datetime import datetime, timedelta
from threading import Thread

from src.common.db import (
    DB_PATH,
    evaluate_shadow_trades_for_change,
    get_baseline_stats,
    get_pending_changes,
    get_pending_change,
    update_pending_change_status,
)
from src.optimizer.change_manager import apply_change, revert_change, ChangeManagerError

logger = logging.getLogger(__name__)

# Thresholds (overridable via env vars)
SHADOW_MIN_TRADES = 30
SHADOW_MIN_PF_DELTA = 0.15
VALIDATION_DROP_PCT = 0.10
MONITOR_INTERVAL_TRADES = 50
COOLDOWN_DAYS_AFTER_REVERT = 7


def promote_shadow_validating_to_validated():
    """Busca pending_changes con status='shadow_validating' y suficientes shadow trades.
    Si shadow PF > baseline PF + SHADOW_MIN_PF_DELTA → status='validated'.
    Si insuficiente sample tras 14 dias → status='rejected' (insufficient_sample).
    Si shadow PF empeora → status='rejected' (no_improvement).
    """
    candidates = get_pending_changes(status='shadow_validating', limit=20)
    promoted = 0
    rejected = 0

    for c in candidates:
        try:
            stats = evaluate_shadow_trades_for_change(c['id'])
            shadow_n = stats['count']
            shadow_pf = stats['pf']

            # Update shadow_pf/wr/count en la row
            update_pending_change_status(
                c['id'], 'shadow_validating',
                shadow_pf=shadow_pf, shadow_wr=stats['wr'],
                shadow_trades_count=shadow_n,
            )

            # Timeout: si tras 14 dias todavia <30 trades, reject
            try:
                started_at = c.get('shadow_started_at') or c.get('proposed_at')
                if started_at:
                    started_dt = datetime.fromisoformat(str(started_at).replace('Z', '+00:00').split('.')[0])
                    from src.common.db import now_ar as _nar  # v3.40.10: AR (matchea shadow_started_at sellado con now_ar), no UTC
                    days_elapsed = (_nar() - started_dt.replace(tzinfo=None)).days
                else:
                    days_elapsed = 0
            except Exception:
                days_elapsed = 0

            if shadow_n < SHADOW_MIN_TRADES:
                if days_elapsed >= 14:
                    update_pending_change_status(
                        c['id'], 'rejected',
                        rejected_reason=f'insufficient_sample_{shadow_n}_after_{days_elapsed}d'
                    )
                    logger.info(f"Rejected change #{c['id']}: only {shadow_n} shadow trades after {days_elapsed}d")
                    rejected += 1
                continue

            # Get baseline para comparar
            baseline = get_baseline_stats(lookback_trades=50)
            baseline_pf = baseline['pf']

            if shadow_pf >= baseline_pf + SHADOW_MIN_PF_DELTA:
                update_pending_change_status(
                    c['id'], 'validated',
                    shadow_pf=shadow_pf, shadow_wr=stats['wr'],
                    shadow_trades_count=shadow_n,
                )
                logger.info(f"Validated change #{c['id']}: shadow PF {shadow_pf} > baseline {baseline_pf} + {SHADOW_MIN_PF_DELTA}")
                promoted += 1
                _send_telegram_validated(c, stats, baseline)
            elif days_elapsed >= 14 or shadow_n >= 100:
                # Si pasamos tiempo o muestra grande sin mejorar, rechazar
                update_pending_change_status(
                    c['id'], 'rejected',
                    rejected_reason=f'no_improvement_pf_{shadow_pf}_vs_baseline_{baseline_pf}'
                )
                logger.info(f"Rejected change #{c['id']}: no improvement after {shadow_n} trades / {days_elapsed}d")
                rejected += 1
        except Exception as e:
            logger.warning(f"promote eval error #{c.get('id')}: {e}")
            continue

    if promoted or rejected:
        logger.info(f"Promotion run: {promoted} validated, {rejected} rejected")


def auto_apply_validated_changes(max_active=1):
    """Aplica pending_changes con status='validated' al live.

    Limite: solo 1 cambio aplicado a la vez (max_active=1). Esto previene
    cascade failure (aplicar varios cambios sin saber cual rompio que).

    Cooldown: si hubo un revert reciente (<COOLDOWN_DAYS_AFTER_REVERT dias),
    no aplica nada. Esperamos para no cascada.
    """
    # Check cooldown post-revert
    if _is_in_revert_cooldown():
        logger.debug("Auto-applier in cooldown post-revert, skip")
        return

    # Check si ya hay un cambio aplicado actualmente
    currently_applied = get_pending_changes(status='applied', limit=10)
    if len(currently_applied) >= max_active:
        return

    # Get cambios listos para aplicar
    validated = get_pending_changes(status='validated', limit=5)
    if not validated:
        return

    # Tomar el mas viejo primero
    validated.sort(key=lambda c: c.get('validated_at') or c.get('proposed_at'))

    for c in validated:
        try:
            result = apply_change(c['id'])
            if result.get('applied'):
                logger.info(f"Auto-applied change #{c['id']}")
                break  # max 1 por iteracion
        except ChangeManagerError as e:
            logger.warning(f"Auto-apply rejected #{c['id']}: {e}")
            try:
                update_pending_change_status(c['id'], 'rejected', rejected_reason=str(e))
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Auto-apply error #{c['id']}: {e}")


def monitor_applied_changes():
    """Monitorea cambios 'applied'. Cada MONITOR_INTERVAL_TRADES trades post-apply,
    compara PF live actual vs baseline pre-cambio. Si PF cayo >VALIDATION_DROP_PCT,
    auto-revert.
    """
    applied = get_pending_changes(status='applied', limit=10)
    if not applied:
        return

    for c in applied:
        try:
            baseline_pf = c.get('applied_baseline_pf') or 0
            if not baseline_pf or baseline_pf <= 0:
                continue

            # Cuantos trades desde apply?
            applied_at = c.get('applied_at')
            if not applied_at:
                continue

            trades_since = _count_trades_since(applied_at)
            if trades_since < MONITOR_INTERVAL_TRADES:
                continue

            # Compute current PF (ultimos N trades)
            current = get_baseline_stats(lookback_trades=MONITOR_INTERVAL_TRADES)
            current_pf = current['pf']

            drop_pct = (baseline_pf - current_pf) / baseline_pf if baseline_pf > 0 else 0

            logger.info(f"Monitor #{c['id']}: baseline_PF={baseline_pf} vs current_PF={current_pf} (drop {drop_pct*100:.1f}%)")

            if drop_pct >= VALIDATION_DROP_PCT:
                reason = f"pf_dropped_{round(drop_pct*100, 1)}pct_after_{trades_since}_trades"
                logger.warning(f"Auto-revert change #{c['id']}: {reason}")
                try:
                    revert_change(c['id'], reason=reason)
                except Exception as e:
                    logger.error(f"Auto-revert failed #{c['id']}: {e}")
        except Exception as e:
            logger.warning(f"Monitor error #{c.get('id')}: {e}")
            continue


def _count_trades_since(timestamp_str):
    """Cuenta trades en auto_strategies + trade_archive desde timestamp."""
    try:
        ts = str(timestamp_str)
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM auto_strategies
            WHERE status IN ('auto_win', 'auto_loss')
            AND mt5_pnl IS NOT NULL
            AND created_at >= ?
        """, (ts,))
        n1 = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM trade_archive
            WHERE result IN ('win', 'loss')
            AND mt5_pnl IS NOT NULL
            AND created_at >= ?
        """, (ts,))
        n2 = cur.fetchone()[0]
        conn.close()
        return n1 + n2
    except Exception:
        return 0


def _is_in_revert_cooldown():
    """Returns True si hubo un revert hace menos de COOLDOWN_DAYS_AFTER_REVERT dias."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        cur = conn.cursor()
        cur.execute("""
            SELECT reverted_at FROM pending_changes
            WHERE status = 'reverted' AND reverted_at IS NOT NULL
            ORDER BY reverted_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        conn.close()
        if not row or not row[0]:
            return False
        reverted_dt = datetime.fromisoformat(str(row[0]).replace('Z', '+00:00').split('.')[0])
        from src.common.db import now_ar as _nar  # v3.40.10: AR (matchea reverted_at sellado con now_ar), no UTC
        days = (_nar() - reverted_dt.replace(tzinfo=None)).days
        return days < COOLDOWN_DAYS_AFTER_REVERT
    except Exception:
        return False


def _send_telegram_validated(change, stats, baseline):
    """Envia alert Telegram cuando un cambio pasa shadow validation."""
    try:
        from src.common.telegram_alerts import send_alert, is_configured
        if not is_configured():
            return
        import json as _json
        change_type = (change.get('change_type') or '').replace('_', '\\_')
        params_short = _json.dumps(_json.loads(change.get('params_json') or '{}'))
        if len(params_short) > 50:
            params_short = params_short[:47] + '...'
        params_safe = params_short.replace('_', '\\_').replace('*', '\\*')
        delta = round(stats['pf'] - baseline['pf'], 2)
        msg = (f"Shadow validado\n"
               f"{change_type}\n"
               f"{params_safe}\n"
               f"Shadow PF +{delta} vs baseline ({stats['count']}t)")
        send_alert(msg, level='INFO')
    except Exception as e:
        logger.debug(f"telegram validated: {e}")


def auto_start_shadow_for_proposed():
    """v3.31.1 — Full autopilot: cambios proposed pasan automaticamente a
    shadow_validating sin intervencion manual.

    Filtros antes de promover:
    - No promover cambios del mismo change_type ya en shadow/validated/applied
      (evita duplicar testing del mismo experimento)
    - Max 3 cambios en shadow_validating simultaneos (evita overload del
      shadow runner)
    """
    from src.common.db import get_pending_changes, update_pending_change_status
    proposed = get_pending_changes(status='proposed', limit=10)
    if not proposed:
        return

    # Limit max 3 en shadow_validating activos
    current_shadow = get_pending_changes(status='shadow_validating', limit=10)
    slots = max(0, 3 - len(current_shadow))
    if slots == 0:
        return

    # Get types ya en pipeline para no duplicar (excluding rejected/reverted)
    active_types = set()
    for s in ['shadow_validating', 'validated', 'applied']:
        for c in get_pending_changes(status=s, limit=20):
            try:
                import json as _json
                key = c['change_type'] + ':' + _json.dumps(_json.loads(c['params_json']), sort_keys=True)
                active_types.add(key)
            except Exception:
                pass

    promoted = 0
    for c in proposed:
        if promoted >= slots:
            break
        try:
            import json as _json
            key = c['change_type'] + ':' + _json.dumps(_json.loads(c['params_json']), sort_keys=True)
            if key in active_types:
                # Dup: marca rejected para no re-procesar
                update_pending_change_status(c['id'], 'rejected',
                                              rejected_reason='duplicate_of_active_change')
                continue
            update_pending_change_status(c['id'], 'shadow_validating')
            logger.info(f"Auto-started shadow for change #{c['id']} ({c['change_type']})")
            promoted += 1
            active_types.add(key)
        except Exception as e:
            logger.warning(f"auto_start_shadow #{c.get('id')}: {e}")


def auto_applier_loop(stop_event, interval_sec=600):
    """Daemon loop: cada `interval_sec` corre los 4 pasos del worker.

    Default 600s (10 min) — balance entre responsiveness y carga DB.
    """
    logger.info(f"Auto-applier daemon started (interval {interval_sec}s)")
    while not stop_event.is_set():
        try:
            auto_start_shadow_for_proposed()  # v3.31.1: proposed -> shadow_validating
            promote_shadow_validating_to_validated()
            auto_apply_validated_changes(max_active=1)
            monitor_applied_changes()
        except Exception as e:
            logger.warning(f"auto_applier_loop error: {e}")
        # Sleep en chunks de 5s para responder a stop_event
        for _ in range(max(1, interval_sec // 5)):
            if stop_event.is_set():
                break
            time.sleep(5)


def start_auto_applier_daemon(stop_event, interval_sec=600):
    """Helper: spawn daemon thread."""
    t = Thread(target=auto_applier_loop, args=(stop_event, interval_sec),
               daemon=True, name='AutoApplier')
    t.start()
    return t
