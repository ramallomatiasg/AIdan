"""
AIdan watchdog: detecta si AIdan se cae y avisa via Telegram.

Uso:
    python tools/aidan_watchdog.py        # corre 1 check
    python tools/aidan_watchdog.py --loop # corre cada 60s indefinidamente

Recomendado: setupear como Task Scheduler de Windows que corre cada 5 min.

Lógica:
1. Check si AIdan.exe está corriendo (psutil)
2. Check si API responde en http://localhost:8000/version
3. Si AMBOS fallan -> alert Telegram CRITICAL "AIdan caído"
4. Throttle: max 1 alert cada 30min (evitar spam)

Si Telegram no está configurado en .env, log local y skip.
"""
import argparse
import logging
import os
import sys
import time

# Add project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

# v3.28.1: log a archivo (compat con pythonw que no tiene stdout)
LOG_FILE = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', 'watchdog.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Compat: usar print() con redirección a logger
def print(*args, **kwargs):
    logging.info(' '.join(str(a) for a in args))

ALERT_THROTTLE_FILE = os.path.join(os.environ.get('APPDATA', '/tmp'), 'AIdan', 'state', '.watchdog_last_alert')
ALERT_THROTTLE_SEC = 1800  # 30 min entre alerts repetidos


def is_user_gaming():
    """Detect si user esta en juego/render/app pesada.

    Estrategia: medir USO REAL de recursos (no listas de procesos).

    1. GPU memory used > 7000MB:
       AIdan idle (Ollama qwen2.5:7b cargado) usa ~5GB.
       Si total > 7GB, hay algo MAS demandando VRAM (juego/render/AAA app).

    2. GPU util > 30% sostenido:
       Juego con frames activos. AIdan idle = 0% util.

    3. CPU promedio > 60% (sostenido 3 samples):
       Render/compilación/encoding/juego CPU-heavy.

    Si CUALQUIERA es True -> skip silencioso.

    NO usamos nvidia-smi compute-apps porque lista TODOS los procesos con
    GPU access (dwm, chrome, explorer) — falsea constantemente.

    Lista hardcoded de juegos como fallback solo para juegos light que no
    detectan via metricas (ej: titulos viejos sin GPU usage alto).
    """
    import subprocess

    # 1+2. GPU usage o memoria
    try:
        from src.common.gpu_monitor import get_gpu_state
        state = get_gpu_state(force_refresh=True)
        if state.get('available'):
            if state.get('gpu_mem_used_mb', 0) > 7000:
                return True
            if state.get('gpu_util', 0) > 30:
                return True
    except Exception:
        pass

    # 3. CPU promedio (3 samples de 1s, descarta primer sample)
    try:
        samples = []
        for i in range(3):
            out = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 '(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average'],
                capture_output=True, text=True, timeout=4
            )
            if out.returncode == 0:
                try:
                    samples.append(float(out.stdout.strip()))
                except (ValueError, TypeError):
                    pass
        if samples:
            avg = sum(samples) / len(samples)
            if avg > 60:
                return True
    except Exception:
        pass

    # 4. Lista hardcoded fallback (juegos light que escapan a metricas)
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV'], capture_output=True, text=True, timeout=5, encoding='cp850', errors='replace')
        if out.returncode == 0:
            text = (out.stdout or '').lower()
            light_games = [
                'cs2.exe', 'csgo.exe', 'valorant', 'leagueclient',
                'fortnite', 'overwatch', 'cyberpunk', 'apex.exe',
                'dota2.exe', 'pubg.exe', 'minecraft', 'wow.exe',
                'gta5.exe', 'rdr2.exe', 'eldenring',
                'obs64.exe', 'photoshop.exe', 'premiere.exe',
            ]
            for p in light_games:
                if p in text:
                    return True
    except Exception:
        pass

    return False


def aidan_is_running():
    """Check si AIdan.exe está corriendo."""
    try:
        import psutil
        for p in psutil.process_iter(['name']):
            if p.info['name'] and p.info['name'].lower() == 'aidan.exe':
                return True
        return False
    except ImportError:
        # Fallback: tasklist en Windows
        import subprocess
        try:
            out = subprocess.check_output('tasklist /FI "IMAGENAME eq AIdan.exe"', shell=True, text=True)
            return 'AIdan.exe' in out
        except Exception:
            return False


def aidan_api_responds():
    """Check si API en :8000 responde."""
    try:
        import requests
        r = requests.get('http://localhost:8000/version', timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def alert_throttled():
    """Returns True si último alert fue dentro de la ventana throttle."""
    if not os.path.exists(ALERT_THROTTLE_FILE):
        return False
    try:
        with open(ALERT_THROTTLE_FILE) as f:
            last = float(f.read().strip())
        return (time.time() - last) < ALERT_THROTTLE_SEC
    except Exception:
        return False


def mark_alert_sent():
    """Persistir timestamp de último alert."""
    try:
        os.makedirs(os.path.dirname(ALERT_THROTTLE_FILE), exist_ok=True)
        with open(ALERT_THROTTLE_FILE, 'w') as f:
            f.write(str(time.time()))
    except Exception:
        pass


def check_once():
    """Check + alert if needed. v3.28.1: gaming-aware silent skip."""
    # v3.28.1 — skip silencioso si user esta en juego/render
    if is_user_gaming():
        print(f"[watchdog] gaming detected, silent skip")
        return True

    running = aidan_is_running()
    api_ok = aidan_api_responds()

    status = f"running={running} api={api_ok}"

    if not running and not api_ok:
        # AIdan caído
        if not alert_throttled():
            try:
                from src.common.telegram_alerts import send_alert, is_configured
                if is_configured():
                    msg = (
                        "AIdan no está corriendo.\n"
                        f"  - Process AIdan.exe: {'corriendo' if running else 'NO encontrado'}\n"
                        f"  - API localhost:8000: {'responde' if api_ok else 'sin respuesta'}\n"
                        "Posible causa: crash, cierre manual, o reinicio Windows.\n"
                        "Acción: revisar manualmente y relanzar si querés que vuelva a operar."
                    )
                    sent = send_alert(msg, level='CRITICAL')
                    if sent:
                        mark_alert_sent()
                        print(f"[watchdog] CRITICAL alert sent ({status})")
                        return False
                    print(f"[watchdog] AIdan down ({status}), Telegram send failed")
                else:
                    print(f"[watchdog] AIdan down ({status}), Telegram NOT configured")
            except Exception as e:
                print(f"[watchdog] error sending alert: {e}")
        else:
            print(f"[watchdog] AIdan down ({status}), alert throttled")
        return False

    print(f"[watchdog] OK {status}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--loop', action='store_true', help='loop forever, check cada 60s')
    p.add_argument('--interval', type=int, default=60, help='segundos entre checks (loop mode)')
    args = p.parse_args()

    if args.loop:
        print(f"[watchdog] starting loop, check cada {args.interval}s")
        while True:
            check_once()
            time.sleep(args.interval)
    else:
        ok = check_once()
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
