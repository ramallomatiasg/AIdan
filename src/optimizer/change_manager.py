"""
change_manager.py — Apply/revert engine para meta-optimization.

Aplica cambios validados al live (de pending_changes status='validated' → 'applied').
Revierte cambios que degradaron PF (status='applied' → 'reverted').

Cada cambio se persiste en `active_meta_filters` (insert con active=1) y el
scanner consulta esa tabla en cada signal para aplicar bloqueos/ajustes.

Guard-rails: hardcoded forbidden params (mt5_config, lot, daily_loss_limit, etc).
Cualquier intento de tocar esas keys = rechazo + alert.
"""
import json
import logging
import sqlite3
from datetime import datetime

from src.common.db import (
    DB_PATH,
    GUARDRAIL_FORBIDDEN_PARAMS,
    SUPPORTED_CHANGE_TYPES,
    deactivate_filter,
    get_active_meta_filters,
    get_baseline_stats,
    get_pending_change,
    insert_active_filter,
    update_pending_change_status,
)

logger = logging.getLogger(__name__)


class ChangeManagerError(Exception):
    """Errores en apply/revert de cambios."""


def _validate_change(change: dict) -> tuple:
    """Validar que un cambio sea aplicable. Returns (ok: bool, error_msg: str|None)."""
    if not change:
        return False, "change not found"
    if change.get('change_type') not in SUPPORTED_CHANGE_TYPES:
        return False, f"unsupported change_type: {change.get('change_type')}"

    # Guard-rail check
    params_str = (change.get('params_json') or '').lower()
    for forbidden in GUARDRAIL_FORBIDDEN_PARAMS:
        if forbidden in params_str:
            return False, f"guardrail violation: {forbidden}"

    return True, None


def apply_change(change_id: int, force: bool = False, baseline_lookback: int = 50) -> dict:
    """Aplica un pending_change al live.

    Args:
        change_id: id del pending_change
        force: si True, skip status validation (solo permite si current_status='validated' or force)
        baseline_lookback: cuantos trades usar para baseline pre-cambio

    Returns: dict con resultado {applied: bool, error: str|None, baseline: dict}
    Raises ChangeManagerError si validation falla.
    """
    change = get_pending_change(change_id)
    if not change:
        raise ChangeManagerError(f"change #{change_id} not found")

    current_status = change.get('status')
    if current_status == 'applied':
        return {'applied': False, 'error': 'already applied', 'baseline': None}
    if not force and current_status != 'validated':
        return {'applied': False,
                'error': f'cannot apply from status={current_status} (need validated or force=True)',
                'baseline': None}

    ok, err = _validate_change(change)
    if not ok:
        update_pending_change_status(change_id, 'rejected', rejected_reason=err)
        raise ChangeManagerError(f"validation failed: {err}")

    change_type = change['change_type']
    try:
        params = json.loads(change.get('params_json', '{}'))
    except Exception as e:
        raise ChangeManagerError(f"invalid params_json: {e}")

    # Capture baseline pre-change
    baseline = get_baseline_stats(lookback_trades=baseline_lookback)

    # Capture previous value for params que requieren rollback restore
    previous_value = None
    if change_type == 'tune_optimizer_param':
        previous_value = _get_optimizer_param_current_value(params.get('param'))

    # Aplicar el cambio segun tipo
    try:
        if change_type == 'tune_optimizer_param':
            _apply_tune_optimizer_param(params)
        # block_* y adjust_* solo insertan en active_meta_filters
        # El scanner consulta get_active_meta_filters() en cada signal
        insert_active_filter(
            change_id=change_id,
            filter_type=change_type,
            params_json=json.dumps(params),
            previous_value_json=json.dumps(previous_value) if previous_value is not None else None,
        )
    except Exception as e:
        raise ChangeManagerError(f"apply failed: {e}")

    # Update pending_changes status
    update_pending_change_status(
        change_id, 'applied',
        applied_baseline_pf=baseline.get('pf', 0),
        applied_baseline_pnl=baseline.get('total_pnl', 0),
    )

    logger.info(f"Applied change #{change_id} ({change_type}): {params} | baseline PF={baseline['pf']}")

    # Telegram alert (best-effort). Escape Markdown chars en change_type/params.
    try:
        from src.common.telegram_alerts import send_alert, is_configured
        if is_configured():
            params_short = json.dumps(params)
            if len(params_short) > 60:
                params_short = params_short[:57] + '...'
            # Escape underscores for Telegram Markdown (igual que telegram_bot.py)
            params_safe = params_short.replace('_', '\\_').replace('*', '\\*')
            change_type_safe = change_type.replace('_', '\\_')
            shadow_pf = change.get('shadow_pf') or 0
            baseline_pf = baseline.get('pf', 0)
            delta = round(shadow_pf - baseline_pf, 2) if shadow_pf else 0
            msg = (f"Cambio aplicado\n"
                   f"{change_type_safe}\n"
                   f"{params_safe}\n"
                   f"Shadow PF {('+' if delta >= 0 else '')}{delta} vs baseline {baseline_pf}")
            send_alert(msg, level='INFO')
    except Exception as e:
        logger.debug(f"Telegram alert apply: {e}")

    return {'applied': True, 'error': None, 'baseline': baseline}


def revert_change(change_id: int, reason: str = 'manual_revert') -> dict:
    """Revierte un cambio aplicado. Marca active_meta_filters.active=0
    y restaura optimizer_params si aplica.

    Args:
        change_id: id del pending_change
        reason: razon del revert (logged en pending_changes.reverted_reason)

    Returns: dict {reverted: bool, error: str|None}
    """
    change = get_pending_change(change_id)
    if not change:
        raise ChangeManagerError(f"change #{change_id} not found")

    if change.get('status') != 'applied':
        return {'reverted': False, 'error': f"not in applied status (current={change.get('status')})"}

    change_type = change['change_type']
    try:
        params = json.loads(change.get('params_json', '{}'))
    except Exception:
        params = {}

    # Get previous value (si lo guardamos al aplicar)
    previous_value = _get_filter_previous_value(change_id)

    try:
        if change_type == 'tune_optimizer_param' and previous_value is not None:
            # Restore optimizer param to previous value
            param_name = params.get('param')
            _set_optimizer_param(param_name, previous_value)

        # Marcar filter inactive (audit trail preservado)
        deactivate_filter(change_id)
    except Exception as e:
        raise ChangeManagerError(f"revert failed: {e}")

    update_pending_change_status(change_id, 'reverted', reverted_reason=reason)
    logger.warning(f"Reverted change #{change_id} ({change_type}): {reason}")

    # Telegram alert. Escape Markdown chars.
    try:
        from src.common.telegram_alerts import send_alert, is_configured
        if is_configured():
            params_short = json.dumps(params)
            if len(params_short) > 60:
                params_short = params_short[:57] + '...'
            params_safe = params_short.replace('_', '\\_').replace('*', '\\*')
            change_type_safe = change_type.replace('_', '\\_')
            reason_safe = reason.replace('_', '\\_').replace('*', '\\*')
            applied_at = (change.get('applied_at') or 'unknown')[:10]
            msg = (f"Cambio revertido\n"
                   f"{change_type_safe} {params_safe}\n"
                   f"Aplicado: {applied_at}\n"
                   f"Razon: {reason_safe}\n"
                   f"Config previa restaurada")
            send_alert(msg, level='WARN')
    except Exception as e:
        logger.debug(f"Telegram alert revert: {e}")

    return {'reverted': True, 'error': None}


def _apply_tune_optimizer_param(params: dict):
    """Modifica un param del AutoTuner via la tabla optimizer_params."""
    param_name = params.get('param')
    new_value = params.get('value')
    if not param_name:
        raise ValueError("tune_optimizer_param requires 'param' key")
    if param_name in GUARDRAIL_FORBIDDEN_PARAMS:
        raise ValueError(f"param {param_name} is guard-railed")

    # Update via AutoTuner
    try:
        from src.optimizer.auto_tuner import AutoTuner
        tuner = AutoTuner(logger, DB_PATH)
        current = dict(tuner.get_params())
        current[param_name] = new_value
        tuner._save_params(current, win_rate=0, total_trades=0, profit_factor=0)
    except Exception as e:
        raise ValueError(f"failed to update optimizer_params: {e}")


def _get_optimizer_param_current_value(param_name: str):
    """Get current value de un param para guardarlo antes de tune (para rollback)."""
    if not param_name:
        return None
    try:
        from src.optimizer.auto_tuner import AutoTuner
        tuner = AutoTuner(logger, DB_PATH)
        return tuner.get_params().get(param_name)
    except Exception:
        return None


def _set_optimizer_param(param_name: str, value):
    """Restore optimizer param to specific value (used in revert)."""
    try:
        from src.optimizer.auto_tuner import AutoTuner
        tuner = AutoTuner(logger, DB_PATH)
        current = dict(tuner.get_params())
        current[param_name] = value
        tuner._save_params(current, win_rate=0, total_trades=0, profit_factor=0)
    except Exception as e:
        logger.warning(f"failed to restore param {param_name}: {e}")


def _get_filter_previous_value(change_id: int):
    """Get previous_value_json de active_meta_filters (para revert)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT previous_value_json FROM active_meta_filters WHERE change_id = ?
    """, (change_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


# ─── Filter evaluation helpers (consumido por el scanner) ───

def is_signal_blocked_by_meta_filters(signal: dict) -> tuple:
    """Evalua un signal contra todos los filtros activos. Returns (blocked, reason).

    El scanner llama esta funcion antes de generar el trade. Si blocked=True,
    el signal se descarta con la razon registrada.

    Args:
        signal: dict con keys direction, confidence, setup_type, trigger_type,
                session, hour_utc, htf_bias

    Returns: (blocked: bool, reason: str)
    """
    try:
        filters = get_active_meta_filters()
    except Exception as e:
        logger.debug(f"meta filters fetch: {e}")
        return False, None

    if not filters:
        return False, None

    # Reutilizamos la logica de _passes_change_filter de shadow_runner
    from src.optimizer.shadow_runner import _passes_change_filter

    for f in filters:
        try:
            passes, skip_reason = _passes_change_filter(signal, f['filter_type'], f.get('params', {}))
            if not passes:
                return True, f"meta_filter_{f.get('change_id')}_{skip_reason}"
        except Exception as e:
            logger.debug(f"filter eval error: {e}")
            continue

    return False, None


def get_confidence_adjustment_for_signal(signal: dict) -> int:
    """Calcula bump/penalty a la confidence basado en filtros activos tipo 'adjust_*'.

    Returns: int delta (positivo = bump, negativo = penalty). Se SUMA al confidence original.
    """
    try:
        filters = get_active_meta_filters()
    except Exception:
        return 0
    if not filters:
        return 0

    delta = 0
    for f in filters:
        ft = f.get('filter_type', '')
        params = f.get('params', {})

        if ft == 'adjust_setup_confidence':
            if signal.get('setup_type') == params.get('setup_type'):
                delta += int(params.get('delta', 0))

    return delta
