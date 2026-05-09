"""
Backtest semanal automático: corre backtest_parallel.py y envía resumen via Telegram.

Uso:
    python tools/backtest_weekly.py

Recomendado: setupear como Task Scheduler de Windows que corre
cada domingo a las 23:00 AR (~02:00 UTC lunes, antes de la apertura).

Flow:
1. Run backtest_parallel internamente
2. Get top 5 combos por track (M5, M15, H1)
3. Format summary como mensaje Telegram
4. Send

Si Telegram no configurado: log local, no crash.
"""
import logging
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

# v3.28.1: log a archivo (compat con pythonw que no tiene stdout)
LOG_FILE = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'backtest_weekly.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
def print(*args, **kwargs):
    logging.info(' '.join(str(a) for a in args))


def run_backtest_for_track(track):
    """Run backtest_parallel for a track, return top 3 combos."""
    cmd = [sys.executable, os.path.join(ROOT, 'tools', 'backtest_parallel.py'),
           '--workers', '8', '--top', '3', '--min-trades', '10', '--track', track]
    try:
        out = subprocess.check_output(cmd, text=True, timeout=300)
        return out
    except subprocess.TimeoutExpired:
        return f"Timeout backtest {track}"
    except Exception as e:
        return f"Error backtest {track}: {e}"


def extract_top_combo_summary(output):
    """Parse output del script para extraer la línea TOP 1."""
    for line in output.split('\n'):
        if line.strip().startswith('1 '):
            # Es la línea del top 1: "1   2.74   1.06  48%  $+3.50   27  filters..."
            return line.strip()
    return "Sin combos válidos"


def main():
    print("[backtest_weekly] running for M5, M15, H1...")

    summaries = {}
    for track in ['m5', 'm15', 'h1']:
        out = run_backtest_for_track(track)
        summaries[track] = out

    # Build Telegram message
    msg_lines = ["*Backtest semanal AIdan*", ""]
    for track in ['m5', 'm15', 'h1']:
        out = summaries[track]
        # Extract baseline + top combo
        lines = out.split('\n')
        baseline = ''
        top_combo = ''
        for i, line in enumerate(lines):
            if 'Baseline' in line and i + 1 < len(lines):
                baseline = lines[i+1].strip()
            if line.strip().startswith('1 ') and 'PF' not in line:
                top_combo = line.strip()
                break

        msg_lines.append(f"*Track {track.upper()}*:")
        if baseline:
            msg_lines.append(f"  baseline: {baseline[:80]}")
        if top_combo:
            msg_lines.append(f"  top combo: {top_combo[:120]}")
        msg_lines.append("")

    full_msg = '\n'.join(msg_lines)
    print(full_msg)
    print()

    # Send via Telegram
    try:
        from src.common.telegram_alerts import send_alert, is_configured
        if is_configured():
            sent = send_alert(full_msg, level='INFO', silent=True)
            print(f"Telegram sent: {sent}")
        else:
            print("Telegram NOT configured")
    except Exception as e:
        print(f"Telegram error: {e}")

    # Persistir output completo para revisión
    log_dir = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'backtest_weekly')
    os.makedirs(log_dir, exist_ok=True)
    from datetime import datetime
    log_file = os.path.join(log_dir, f"backtest_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(full_msg + "\n\n")
        for track, out in summaries.items():
            f.write(f"=== {track} ===\n{out}\n\n")
    print(f"Log saved: {log_file}")


if __name__ == '__main__':
    main()
