"""
AIdan Daily Report — Generates and uploads trading reports to Google Sheets.
Uses gspread + Service Account credentials.
"""
import os
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

TZ_AR = timezone(timedelta(hours=-3))

def _now_ar():
    return datetime.now(TZ_AR).replace(tzinfo=None)

def _today_str():
    return datetime.now(TZ_AR).strftime('%Y-%m-%d')


def _get_gspread_client():
    """Get authenticated gspread client using service account credentials."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("gspread or google-auth not installed. Run: pip install gspread google-auth")
        return None

    creds_path = os.getenv('GOOGLE_SHEETS_CREDS', 'config/google_creds.json')
    if not os.path.isfile(creds_path):
        logger.warning(f"Google Sheets credentials not found at {creds_path}")
        return None

    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(credentials)


def _get_or_create_spreadsheet(gc):
    """Open existing spreadsheet or create a new one."""
    sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
    sheet_name = os.getenv('GOOGLE_SHEET_NAME', 'AIdan - Trading Report')

    if sheet_id:
        try:
            return gc.open_by_key(sheet_id)
        except Exception as e:
            logger.error(f"Cannot open sheet by ID '{sheet_id}': {e}")
            return None

    # Try by name
    try:
        return gc.open(sheet_name)
    except Exception:
        pass

    # Create new
    try:
        spreadsheet = gc.create(sheet_name)
        logger.info(f"Created new spreadsheet: {sheet_name} (ID: {spreadsheet.id})")
        logger.info(f"Share this sheet with your Google account to see it in Drive!")
        return spreadsheet
    except Exception as e:
        logger.error(f"Cannot create spreadsheet: {e}")
        return None


def _ensure_worksheet(spreadsheet, title, headers):
    """Get or create a worksheet with headers."""
    try:
        ws = spreadsheet.worksheet(title)
    except Exception:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))

    # Check if headers exist
    try:
        first_row = ws.row_values(1)
    except Exception:
        first_row = []

    if not first_row:
        ws.update('A1', [headers])
        # Bold headers
        ws.format('A1:Z1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.15, 'green': 0.15, 'blue': 0.2},
        })

    return ws


def _get_daily_data():
    """Collect all data for today's report from the database."""
    from src.common.db import (
        get_performance_stats, get_strategy_performance,
        get_detailed_trade_history, get_setup_win_rates, get_learned_lessons
    )

    today = _today_str()
    perf_signals = get_performance_stats()
    perf_strategies = get_strategy_performance()
    trades = get_detailed_trade_history(limit=100)
    setup_rates = get_setup_win_rates()
    lessons = get_learned_lessons()

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

    # Total strategies generated today (from auto_strategies table)
    total_strategies = 0
    try:
        import sqlite3
        from src.common.db import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM auto_strategies WHERE date(created_at) = ?", (today,))
        total_strategies = c.fetchone()[0]
        conn.close()
    except Exception:
        pass

    return {
        'date': today,
        'total_strategies': total_strategies,
        'signal_perf': perf_signals,
        'strategy_perf': perf_strategies,
        'trades': today_trades,
        'setup_rates': setup_rates,
        'lessons': lessons,
        'net_pips': round(net_pips, 1),
        'best_setup': best_setup,
        'worst_setup': worst_setup,
    }


def generate_daily_report():
    """
    Generate and upload the daily trading report to Google Sheets.
    Returns dict with status and message.
    """
    gc = _get_gspread_client()
    if not gc:
        return {'status': 'error', 'message': 'Google Sheets not configured. Add config/google_creds.json'}

    spreadsheet = _get_or_create_spreadsheet(gc)
    if not spreadsheet:
        return {'status': 'error', 'message': 'Cannot open/create spreadsheet'}

    data = _get_daily_data()
    today = data['date']

    # ─── Sheet 1: Resumen Diario ───
    summary_headers = [
        'Fecha', 'Estrategias', 'Wins', 'Losses', 'Skips',
        'Win Rate %', 'Pips Netos', 'Mejor Setup', 'Peor Setup', 'Notas IA'
    ]
    ws_summary = _ensure_worksheet(spreadsheet, 'Resumen Diario', summary_headers)

    # Check if today already has a row (avoid duplicates)
    all_dates = ws_summary.col_values(1)
    sp = data['strategy_perf']
    summary_row = [
        today,
        data['total_strategies'],
        sp.get('wins', 0),
        sp.get('losses', 0),
        sp.get('skips', 0),
        sp.get('win_rate', 0),
        data['net_pips'],
        data['best_setup'],
        data['worst_setup'],
        (data['lessons'] or '')[:500],
    ]

    if today in all_dates:
        # Update existing row
        row_idx = all_dates.index(today) + 1
        ws_summary.update(f'A{row_idx}', [summary_row])
        logger.info(f"Updated summary row for {today}")
    else:
        ws_summary.append_row(summary_row, value_input_option='USER_ENTERED')
        logger.info(f"Added summary row for {today}")

    # ─── Sheet 2: Trades Detalle ───
    trade_headers = [
        'Fecha', 'Hora', 'Direccion', 'Entry', 'Exit', 'TP', 'SL',
        'Pips', 'Resultado', 'Confianza %', 'Setup Type', 'Trigger',
        'Tendencia', 'RSI', 'HTF Bias', 'Titulo'
    ]
    ws_trades = _ensure_worksheet(spreadsheet, 'Trades', trade_headers)

    # Get existing trade timestamps to avoid duplicates
    existing_times = set(ws_trades.col_values(2))  # Hora column

    new_trade_rows = []
    for t in data['trades']:
        rec_at = str(t.get('recorded_at', ''))
        hora = rec_at.split(' ')[1] if ' ' in rec_at else rec_at
        if hora in existing_times:
            continue  # already uploaded

        new_trade_rows.append([
            today,
            hora,
            t.get('direction', ''),
            t.get('entry_price', ''),
            t.get('exit_price', ''),
            '',  # TP (not stored in trade history)
            '',  # SL (not stored in trade history)
            t.get('pips', ''),
            t.get('result', ''),
            t.get('confidence', ''),
            t.get('setup_type', ''),
            t.get('trigger_type', ''),
            t.get('market_trend', ''),
            t.get('rsi', ''),
            t.get('htf_bias', ''),
            str(t.get('title', ''))[:100],
        ])

    if new_trade_rows:
        ws_trades.append_rows(new_trade_rows, value_input_option='USER_ENTERED')
        logger.info(f"Added {len(new_trade_rows)} trade rows")

    # ─── Sheet 3: Setup Analysis ───
    setup_headers = [
        'Setup Type', 'Total Trades', 'Wins', 'Losses', 'Win Rate %',
        'Ultima Actualizacion'
    ]
    ws_setup = _ensure_worksheet(spreadsheet, 'Setup Analysis', setup_headers)

    # Clear existing data (except headers) and rewrite
    if data['setup_rates']:
        # Get current row count
        all_vals = ws_setup.get_all_values()
        if len(all_vals) > 1:
            # Clear old data rows
            ws_setup.batch_clear([f'A2:F{len(all_vals) + 1}'])

        setup_rows = []
        for setup_type, stats in sorted(data['setup_rates'].items()):
            setup_rows.append([
                setup_type,
                stats.get('total', 0),
                stats.get('wins', 0),
                stats.get('losses', 0),
                stats.get('win_rate', 0),
                today,
            ])

        if setup_rows:
            ws_setup.update(f'A2:F{len(setup_rows) + 1}', setup_rows,
                          value_input_option='USER_ENTERED')
            logger.info(f"Updated {len(setup_rows)} setup analysis rows")

    # Remove default "Sheet1" if it exists and is empty
    try:
        default_sheet = spreadsheet.worksheet('Sheet1')
        if not default_sheet.get_all_values():
            spreadsheet.del_worksheet(default_sheet)
    except Exception:
        pass

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
    return {
        'status': 'success',
        'message': f'Reporte subido correctamente',
        'sheet_url': sheet_url,
        'trades_added': len(new_trade_rows),
        'date': today,
    }
