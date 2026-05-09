"""
Telegram bot alerts para AIdan.

Setup (1 vez):
1. En Telegram, hablar con @BotFather, crear bot, obtener TOKEN.
2. Hablar con @userinfobot para obtener tu CHAT_ID.
3. En .env de AIdan agregar:
     TELEGRAM_TOKEN=123456:ABCDEF...
     TELEGRAM_CHAT_ID=123456789
4. Restart AIdan. Test con: curl http://localhost:8000/telegram/test

Niveles:
  CRITICAL — drawdown >$50, AIdan caído, balance <$880
  WIN     — trade ganador
  LOSS    — trade perdedor
  INFO    — eventos generales (start, stop, milestones)

Graceful: si TELEGRAM_TOKEN/CHAT_ID no configurados, no envía nada (no crash).
"""
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

# Rate limit interno: max 1 mensaje cada 2s para evitar Telegram throttle
_LAST_SEND = 0
MIN_INTERVAL_SEC = 2

# Cache de Config (lazy import para evitar circulares)
_TOKEN = None
_CHAT_ID = None


def _get_credentials():
    global _TOKEN, _CHAT_ID
    if _TOKEN is None or _CHAT_ID is None:
        try:
            from src.common.config import Config
            _TOKEN = Config.TELEGRAM_TOKEN or ""
            _CHAT_ID = Config.TELEGRAM_CHAT_ID or ""
        except Exception:
            _TOKEN = os.getenv("TELEGRAM_TOKEN", "")
            _CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    return _TOKEN, _CHAT_ID


def is_configured():
    """Returns True si TOKEN+CHAT_ID están seteados."""
    token, chat_id = _get_credentials()
    return bool(token and chat_id)


def send_alert(message, level='INFO', silent=False):
    """Envía mensaje a Telegram. Graceful degradation si no configurado.

    Args:
        message: texto del mensaje (se trunca a 4000 chars max)
        level: 'CRITICAL' | 'WIN' | 'LOSS' | 'INFO'
        silent: si True, no notification sound (Telegram disable_notification)

    Returns:
        True si se envió OK, False si falló o no configurado.
    """
    global _LAST_SEND

    token, chat_id = _get_credentials()
    if not (token and chat_id):
        logger.debug("Telegram not configured (skipping alert)")
        return False

    # Rate limit
    elapsed = time.time() - _LAST_SEND
    if elapsed < MIN_INTERVAL_SEC:
        time.sleep(MIN_INTERVAL_SEC - elapsed)

    # Format message with emoji prefix
    prefix = {
        'CRITICAL': '🚨 *CRITICAL*\n',
        'WIN': '✅ *WIN*\n',
        'LOSS': '❌ *LOSS*\n',
        'INFO': 'ℹ️ ',
        'WARN': '⚠️ *WARN*\n',
        'NEWS': '📰 ',
    }.get(level, '')

    full_msg = (prefix + str(message))[:4000]

    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={
                'chat_id': chat_id,
                'text': full_msg,
                'parse_mode': 'Markdown',
                'disable_notification': silent,
            },
            timeout=10
        )
        _LAST_SEND = time.time()
        if resp.status_code == 200:
            return True
        logger.warning(f"Telegram send failed: HTTP {resp.status_code} - {resp.text[:200]}")
        return False
    except requests.exceptions.Timeout:
        logger.warning("Telegram send timeout")
        return False
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")
        return False


def send_trade_result(strategy_id, direction, trigger_type, pnl, conf, balance=None):
    """Helper para enviar resultado de trade. Auto-formato según win/loss."""
    level = 'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'INFO'
    msg = f"#{strategy_id} {direction} `{trigger_type}` (conf {conf:.0f})\n"
    msg += f"PnL: ${pnl:+.2f}"
    if balance is not None:
        msg += f"  |  Balance: ${balance:.2f}"
    return send_alert(msg, level=level)


def send_drawdown_alert(daily_pnl, balance, baseline=1000):
    """Alert si drawdown serio. Solo dispara con drawdown >=5%."""
    drawdown = baseline - balance
    pct = drawdown / baseline * 100
    if pct >= 5:
        msg = f"Drawdown: ${drawdown:.2f} ({pct:.1f}% del capital)\n"
        msg += f"Daily PnL: ${daily_pnl:+.2f}\n"
        msg += f"Balance: ${balance:.2f}"
        return send_alert(msg, level='CRITICAL')
    return False


def send_milestone(track, trades_count, wr, pf, pnl):
    """Alert milestone Track B/C alcanza criterios Fase 2."""
    msg = f"*Milestone {track}*\n"
    msg += f"Trades: {trades_count}\n"
    msg += f"WR: {wr:.0f}%, PF: {pf:.2f}\n"
    msg += f"PnL: ${pnl:+.2f}\n\n"
    msg += "Posible candidato Fase 2 (cuenta real)."
    return send_alert(msg, level='INFO')


def send_startup(version, mt5_balance=None):
    """v3.24.0 - Aviso al arrancar AIdan."""
    msg = f"AIdan iniciado v{version}"
    if mt5_balance is not None:
        msg += f"\nBalance MT5: ${mt5_balance:.2f}"
    return send_alert(msg, level='INFO', silent=True)


def send_shutdown(version, reason='manual'):
    """v3.24.0 - Aviso al apagar AIdan."""
    return send_alert(f"AIdan v{version} detenido ({reason})", level='WARN', silent=True)


# Throttle state: evitar alerts repetitivos
_DRAWDOWN_LAST_SENT = 0
_MILESTONE_SENT = set()  # set de "{track}_{trade_count_milestone}" para no repetir


def check_and_send_drawdown(balance, daily_pnl, baseline=1000):
    """Throttled drawdown alert: max 1 cada 30min, escala thresholds."""
    global _DRAWDOWN_LAST_SENT
    drawdown = baseline - balance
    pct = drawdown / baseline * 100
    now = time.time()
    if pct >= 5 and (now - _DRAWDOWN_LAST_SENT) > 1800:  # 30min throttle
        if send_drawdown_alert(daily_pnl, balance, baseline):
            _DRAWDOWN_LAST_SENT = now
            return True
    return False


def check_and_send_milestone(track_label, total_trades, wr, pf, pnl):
    """Throttled milestone alert: solo dispara una vez por umbral.
    Umbrales: 15 trades + PF>=1.2 (preliminar) y 30 trades + PF>=1.2 (Fase 2 ready)."""
    if total_trades < 15 or pf < 1.2 or pnl <= 0:
        return False
    # Pick milestone: 15 (preliminar) o 30 (Fase 2 ready)
    if total_trades >= 30:
        milestone_key = f"{track_label}_30trades"
        if milestone_key not in _MILESTONE_SENT:
            _MILESTONE_SENT.add(milestone_key)
            return send_milestone(f"{track_label} (READY FASE 2)", total_trades, wr, pf, pnl)
    elif total_trades >= 15:
        milestone_key = f"{track_label}_15trades"
        if milestone_key not in _MILESTONE_SENT:
            _MILESTONE_SENT.add(milestone_key)
            return send_milestone(f"{track_label} (preliminar)", total_trades, wr, pf, pnl)
    return False


def test_connection():
    """Test connection. Returns dict con resultado."""
    token, chat_id = _get_credentials()
    if not token:
        return {'ok': False, 'error': 'TELEGRAM_TOKEN not configured'}
    if not chat_id:
        return {'ok': False, 'error': 'TELEGRAM_CHAT_ID not configured'}
    try:
        r = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=5)
        if r.status_code != 200:
            return {'ok': False, 'error': f'getMe failed: {r.status_code}'}
        bot_info = r.json().get('result', {})
        # Try sending test message
        sent = send_alert("AIdan Telegram test - configuracion OK", level='INFO', silent=True)
        return {
            'ok': True,
            'bot_username': bot_info.get('username'),
            'bot_name': bot_info.get('first_name'),
            'test_sent': sent,
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)}
