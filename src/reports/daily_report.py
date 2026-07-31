"""
AIdan Daily Report — Generates and uploads trading reports to Google Sheets.
Uses Google Apps Script webhook (no credentials needed).
"""
import os
import json
import logging
import requests
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

TZ_AR = timezone(timedelta(hours=-3))

def _now_ar():
    return datetime.now(TZ_AR).replace(tzinfo=None)

def _today_str():
    return datetime.now(TZ_AR).strftime('%Y-%m-%d')


def _get_webhook_url():
    """Get the Google Apps Script webhook URL from config."""
    url = os.getenv('GOOGLE_SHEETS_WEBHOOK', '')
    if not url:
        from src.common.config import Config
        url = getattr(Config, 'GOOGLE_SHEETS_WEBHOOK', '')
    return url


def _get_daily_data():
    """Collect all data for today's report from the database."""
    from src.common.db import (
        get_performance_stats, get_strategy_performance,
        get_detailed_trade_history, get_setup_win_rates, get_learned_lessons
    )

    today = _today_str()
    perf_strategies = get_strategy_performance()
    trades = get_detailed_trade_history(limit=100)
    setup_rates = get_setup_win_rates()

    # Filter trades for today only
    today_trades = []
    for t in trades:
        rec = str(t.get('recorded_at', ''))
        if today in rec:
            today_trades.append(t)

    # Calculate net pips
    net_pips = sum(t.get('pips', 0) or 0 for t in today_trades if t.get('result') in ('win', 'loss'))

    # Find best and worst setup
    best_setup = ''
    worst_setup = ''
    if setup_rates:
        sorted_setups = sorted(setup_rates.items(), key=lambda x: x[1].get('win_rate', 0), reverse=True)
        if sorted_setups:
            best_setup = f"{sorted_setups[0][0]} ({sorted_setups[0][1].get('win_rate', 0):.0f}%)"
        if len(sorted_setups) > 1:
            worst_setup = f"{sorted_setups[-1][0]} ({sorted_setups[-1][1].get('win_rate', 0):.0f}%)"

    # Total strategies generated today
    total_strategies = 0
    try:
        import sqlite3
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM auto_strategies WHERE date(created_at) = ?", (today,))
        total_strategies = c.fetchone()[0]
        conn.close()
    except Exception:
        pass

    return {
        'date': today,
        'total_strategies': total_strategies,
        'strategy_perf': perf_strategies,
        'trades': today_trades,
        'setup_rates': setup_rates,
        'net_pips': round(net_pips, 1),
        'best_setup': best_setup,
        'worst_setup': worst_setup,
    }


def _generate_comment(trade):
    """Generate a simple, human-readable comment for a trade."""
    result = trade.get('result', '')
    direction = trade.get('direction', '')
    pips = trade.get('pips', 0) or 0
    setup = trade.get('setup_type', '')
    title = str(trade.get('title', ''))

    dir_es = 'compra' if direction == 'CALL' else 'venta'

    # Determine what triggered the trade
    if 'soporte' in title.lower():
        trigger = 'rebote en soporte'
    elif 'resistencia' in title.lower():
        trigger = 'breakout de resistencia'
    elif 'bollinger' in title.lower():
        trigger = 'rebote en Bollinger'
    elif 'rsi' in title.lower():
        trigger = 'senal de RSI'
    elif 'cruce' in title.lower() or 'ma' in title.lower():
        trigger = 'cruce de medias'
    elif 'smc' in setup.lower() or 'zona' in title.lower():
        trigger = 'confirmacion SMC'
    elif 'calendario' in title.lower() or 'pre-' in title.lower():
        trigger = 'evento del calendario'
    else:
        trigger = 'senal de estructura'

    if result == 'win':
        return f"Se abrio {dir_es} por {trigger}. Acerto, gano {abs(pips):.1f} pips."
    elif result == 'loss':
        return f"Se abrio {dir_es} por {trigger}. No funciono, perdio {abs(pips):.1f} pips."
    elif result == 'break_even':
        return f"Se abrio {dir_es} por {trigger}. Llego a break even, sin ganancia ni perdida."
    elif result == 'skip':
        return f"Se detecto {dir_es} por {trigger}. No se opero."
    else:
        return f"Se abrio {dir_es} por {trigger}. Pendiente de resultado."


def generate_daily_report():
    """
    Generate and upload the daily trading report to Google Sheets via webhook.
    Returns dict with status and message.
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return {'status': 'error', 'message': 'Google Sheets webhook no configurado. Agregá GOOGLE_SHEETS_WEBHOOK en config.'}

    data = _get_daily_data()
    sp = data['strategy_perf']

    # 1. Upload summary
    try:
        summary_payload = {
            'action': 'summary',
            'date': data['date'],
            'total_strategies': data['total_strategies'],
            'wins': sp.get('wins', 0),
            'losses': sp.get('losses', 0),
            'break_evens': sp.get('break_evens', 0),
            'win_rate': sp.get('win_rate', 0),
            'net_pips': data['net_pips'],
            'best_setup': data['best_setup'],
            'worst_setup': data['worst_setup'],
        }
        r = requests.post(webhook_url, json=summary_payload, timeout=15)
        logger.info(f"Summary uploaded: {r.status_code}")
    except Exception as e:
        logger.error(f"Error uploading summary: {e}")
        return {'status': 'error', 'message': f'Error subiendo resumen: {e}'}

    # 2. Upload trades (only unreported ones to avoid duplicates)
    trades_added = 0
    from src.common.db import get_unreported_trades, mark_trades_reported
    unreported = get_unreported_trades(data['date'])
    if unreported:
        try:
            trade_rows = []
            for t in unreported:
                rec_at = str(t.get('recorded_at', ''))
                hora = rec_at.split(' ')[1] if ' ' in rec_at else rec_at
                comment = _generate_comment(t)
                trade_rows.append({
                    'date': data['date'],
                    'time': hora,
                    'direction': t.get('direction', ''),
                    'entry': t.get('entry_price', ''),
                    'tp': '',
                    'sl': '',
                    'pips': t.get('pips', ''),
                    'result': t.get('result', ''),
                    'confidence': t.get('confidence', ''),
                    'setup_type': t.get('setup_type', ''),
                    'trigger_type': t.get('trigger_type', ''),
                    'title': str(t.get('title', ''))[:100],
                    'comment': comment,
                })
            trades_payload = {
                'action': 'trades',
                'trades': trade_rows,
            }
            r = requests.post(webhook_url, json=trades_payload, timeout=15)
            if r.status_code == 200:
                mark_trades_reported(unreported)
                trades_added = len(trade_rows)
                logger.info(f"Trades uploaded: {trades_added} new rows, status {r.status_code}")
            else:
                logger.error(f"Trades upload failed: status {r.status_code}")
        except Exception as e:
            logger.error(f"Error uploading trades: {e}")
    else:
        logger.info("No new unreported trades to upload.")

    # 3. Upload setup analysis
    if data['setup_rates']:
        try:
            setup_rows = []
            for setup_type, stats in sorted(data['setup_rates'].items()):
                setup_rows.append({
                    'type': setup_type,
                    'total': stats.get('total', 0),
                    'wins': stats.get('wins', 0),
                    'losses': stats.get('losses', 0),
                    'win_rate': stats.get('win_rate', 0),
                })
            setups_payload = {
                'action': 'setups',
                'date': data['date'],
                'setups': setup_rows,
            }
            r = requests.post(webhook_url, json=setups_payload, timeout=15)
            logger.info(f"Setup analysis uploaded: {len(setup_rows)} rows, status {r.status_code}")
        except Exception as e:
            logger.error(f"Error uploading setup analysis: {e}")

    return {
        'status': 'success',
        'message': 'Reporte subido correctamente a Google Sheets',
        'trades_added': trades_added,
        'date': data['date'],
    }
