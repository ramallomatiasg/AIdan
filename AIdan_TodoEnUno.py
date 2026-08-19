"""
AIdan Todo-En-Uno - Versión portable con todos los servicios integrados
NO requiere ejecutables separados - Todo corre en un solo proceso
"""
import sys
import os
import subprocess
import time
import requests
import webbrowser
import tkinter as tk
from tkinter import messagebox
from threading import Thread
import winreg
import urllib.request
import tempfile

# v3.16.0 — force UTF-8 on Windows console to prevent UnicodeEncodeError on emojis (🚀 📰 etc).
# When AIdan launches without a console attached (Task Scheduler / start ""),
# stdout falls back to cp1252 which can't encode emoji and crashes start_services.
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Ensure working directory and data paths are correct
if getattr(sys, 'frozen', False):
    _EXE_DIR = os.path.dirname(sys.executable)
    # Use %APPDATA%/AIdan/ for persistent data (survives RAR temp folders)
    _APP_DIR = os.path.join(os.environ.get('APPDATA', _EXE_DIR), 'AIdan')
    os.makedirs(_APP_DIR, exist_ok=True)
    # Copy config/ and templates/ to AppData if they don't exist there yet
    # (they ship alongside the exe in the RAR)
    import shutil
    for folder in ('config', 'templates'):
        src = os.path.join(_EXE_DIR, folder)
        dst = os.path.join(_APP_DIR, folder)
        if os.path.isdir(src) and not os.path.isdir(dst):
            shutil.copytree(src, dst)
    os.chdir(_APP_DIR)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
    os.chdir(_APP_DIR)

# Add src to path ANTES de cualquier import local
sys.path.insert(0, _APP_DIR)

# Configuración
DASHBOARD_URL = "http://localhost:8000"

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# NEWS CATEGORY CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

_NEWS_CATEGORIES = {
    'fed_rate': ['fed ', 'federal reserve', 'fomc', 'interest rate', 'rate decision', 'rate hike', 'rate cut', 'powell', 'tasa de interés'],
    'employment': ['nonfarm', 'non-farm', 'payroll', 'unemployment', 'jobless', 'jobs report', 'employment', 'hiring', 'empleo', 'desempleo'],
    'inflation': ['cpi', 'ppi', 'pce', 'inflation', 'consumer price', 'producer price', 'core price', 'inflación'],
    'gdp_growth': ['gdp', 'gross domestic', 'economic growth', 'pib', 'crecimiento'],
    'central_bank': ['ecb', 'boe', 'boj', 'central bank', 'lagarde', 'banco central', 'monetary policy'],
    'geopolitical': ['war', 'tariff', 'sanction', 'trade war', 'ceasefire', 'conflict', 'guerra', 'arancel'],
    'oil_energy': ['oil', 'crude', 'opec', 'energy', 'petróleo', 'gas natural'],
    'market_sentiment': ['rally', 'crash', 'sell-off', 'selloff', 'risk-on', 'risk-off', 'volatility', 'vix', 'futures'],
}

def _classify_news_category(title: str) -> str:
    """Classify a news title into a category for learning."""
    if not title:
        return 'other'
    t = title.lower()
    for cat, keywords in _NEWS_CATEGORIES.items():
        if any(kw in t for kw in keywords):
            return cat
    return 'other'

# STRATEGY TOAST NOTIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def _show_strategy_toast(strategy: dict, candles: list):
    """
    Show a Windows-style toast popup in the bottom-right corner.
    Contains a mini candlestick chart + ENTRY / TP / SL.
    Must be called from the main tkinter thread via root.after().
    """
    import math

    direction  = strategy.get('direction', 'CALL')
    entry      = strategy.get('entry_price', 0)
    sl         = strategy.get('stop_loss', 0)
    tp         = strategy.get('take_profit', 0)
    conf       = strategy.get('confidence', 0)
    title_raw  = strategy.get('news_title', '')
    trigger    = strategy.get('trigger_type', 'news')

    is_call  = direction == 'CALL'
    clr_dir  = '#22c55e' if is_call else '#ef4444'   # green / red
    clr_bg   = '#0a0e14'
    clr_card = '#111822'
    clr_bdr  = clr_dir
    clr_text = '#e2e8f0'
    clr_dim  = '#64748b'
    clr_gold = '#f59e0b'

    W, H = 400, 340

    toast = tk.Toplevel()
    toast.overrideredirect(True)
    toast.attributes('-topmost', True)
    toast.configure(bg=clr_bg)
    toast.resizable(False, False)

    # Position: bottom-right with 16px margin
    sw = toast.winfo_screenwidth()
    sh = toast.winfo_screenheight()
    x_end = sw - W - 16
    y_end = sh - H - 52      # above taskbar
    y_start = sh + 10        # off-screen below

    toast.geometry(f'{W}x{H}+{x_end}+{y_start}')

    # Outer border in direction color
    border = tk.Frame(toast, bg=clr_bdr, padx=2, pady=2)
    border.pack(fill='both', expand=True)
    inner = tk.Frame(border, bg=clr_bg)
    inner.pack(fill='both', expand=True)

    # ── Header bar ──
    hdr = tk.Frame(inner, bg=clr_card, height=38)
    hdr.pack(fill='x')
    hdr.pack_propagate(False)

    arrow = '▲ CALL' if is_call else '▼ PUT'
    tk.Label(hdr, text=f'  {arrow}', font=('Segoe UI', 13, 'bold'),
             fg=clr_dir, bg=clr_card).pack(side='left', padx=6, pady=6)

    conf_lbl = f'{conf:.0f}% conf'
    tk.Label(hdr, text=conf_lbl, font=('Segoe UI', 9),
             fg=clr_gold, bg=clr_card).pack(side='left', padx=4)

    badge_colors = {'news': ('#f97316', '#1a0a00'), 'structure': ('#818cf8', '#0a0a1a'), 'smc': ('#e040fb', '#140014'), 'calendar': ('#facc15', '#1a1600')}
    bc, bk = badge_colors.get(trigger, ('#64748b', '#111'))
    tk.Label(hdr, text=f' {trigger.upper()} ', font=('Segoe UI', 8, 'bold'),
             fg=bc, bg=bk).pack(side='left', padx=4)

    # Close button
    close_lbl = tk.Label(hdr, text='  ✕  ', font=('Segoe UI', 11),
                         fg=clr_dim, bg=clr_card, cursor='hand2')
    close_lbl.pack(side='right')
    close_lbl.bind('<Button-1>', lambda e: toast.destroy())
    close_lbl.bind('<Enter>', lambda e: close_lbl.config(fg='#ef4444', bg='#1a0008'))
    close_lbl.bind('<Leave>', lambda e: close_lbl.config(fg=clr_dim, bg=clr_card))

    # ── Candlestick chart ──
    CHART_H = 160
    cv = tk.Canvas(inner, bg='#0d1117', height=CHART_H,
                   highlightthickness=0)
    cv.pack(fill='x')

    def draw_chart(event=None):
        cw = cv.winfo_width() or (W - 4)
        ch = CHART_H
        cv.delete('all')

        # Background grid lines
        for i in range(1, 5):
            y = int(ch * i / 5)
            cv.create_line(0, y, cw, y, fill='#1e293b', width=1)

        data = candles[-40:] if candles and len(candles) >= 5 else []
        if not data:
            cv.create_text(cw//2, ch//2, text='Sin datos de velas',
                           fill=clr_dim, font=('Segoe UI', 9))
            return

        highs  = [c['high']  for c in data]
        lows   = [c['low']   for c in data]
        prices = [entry, sl, tp] + highs + lows
        p_min  = min(prices) - 0.0002
        p_max  = max(prices) + 0.0002
        rng    = p_max - p_min or 0.001

        def py(price):
            return ch - int((price - p_min) / rng * ch)

        n     = len(data)
        pad   = 6
        avail = cw - 2 * pad
        step  = max(4, avail // max(n, 1))
        cw_c  = max(2, step - 2)

        for i, c in enumerate(data):
            x = pad + i * step + step // 2
            o, cl, h, l = c['open'], c['close'], c['high'], c['low']
            color = '#22c55e' if cl >= o else '#ef4444'
            # Wick
            cv.create_line(x, py(h), x, py(l), fill=color, width=1)
            # Body
            y1, y2 = sorted([py(o), py(cl)])
            cv.create_rectangle(x - cw_c//2, y1, x + cw_c//2, max(y2, y1+1),
                                fill=color, outline='')

        # ENTRY line (white dashed)
        ye = py(entry)
        for xi in range(0, cw, 8):
            cv.create_line(xi, ye, xi+5, ye, fill='#ffffff', width=1)
        cv.create_text(cw - 2, ye - 7, text=f'E {entry:.5f}',
                       fill='#ffffff', font=('Segoe UI', 7, 'bold'), anchor='e')

        # TP line (green)
        yt = py(tp)
        for xi in range(0, cw, 8):
            cv.create_line(xi, yt, xi+5, yt, fill='#22c55e', width=1)
        cv.create_text(cw - 2, yt - 7, text=f'TP {tp:.5f}',
                       fill='#22c55e', font=('Segoe UI', 7, 'bold'), anchor='e')

        # SL line (red)
        ys = py(sl)
        for xi in range(0, cw, 8):
            cv.create_line(xi, ys, xi+5, ys, fill='#ef4444', width=1)
        cv.create_text(cw - 2, ys - 7, text=f'SL {sl:.5f}',
                       fill='#ef4444', font=('Segoe UI', 7, 'bold'), anchor='e')

    cv.bind('<Configure>', draw_chart)
    cv.after(50, draw_chart)

    # ── ENTRY / TP / SL labels ──
    lbl_frame = tk.Frame(inner, bg=clr_bg)
    lbl_frame.pack(fill='x', padx=10, pady=(8, 4))

    def make_stat(parent, label, value, color):
        f = tk.Frame(parent, bg=clr_card, padx=10, pady=6)
        f.pack(side='left', expand=True, fill='x', padx=4)
        tk.Label(f, text=label, font=('Segoe UI', 8),
                 fg=clr_dim, bg=clr_card).pack(anchor='w')
        tk.Label(f, text=value, font=('Segoe UI', 12, 'bold'),
                 fg=color, bg=clr_card).pack(anchor='w')

    make_stat(lbl_frame, 'ENTRY', f'{entry:.5f}', clr_text)
    make_stat(lbl_frame, 'TP', f'{tp:.5f}', '#22c55e')
    make_stat(lbl_frame, 'SL', f'{sl:.5f}', '#ef4444')

    # ── Reason (truncated) ──
    reason_txt = title_raw.replace('[ESTRUCTURA] ', '').replace('[SMC] ', '')[:72]
    tk.Label(inner, text=reason_txt, font=('Segoe UI', 8),
             fg=clr_dim, bg=clr_bg, wraplength=W - 24, justify='left'
             ).pack(anchor='w', padx=12, pady=(2, 8))

    # ── Auto-dismiss progress bar ──
    AUTO_DISMISS = 20  # seconds
    pb_frame = tk.Frame(inner, bg='#1e293b', height=3)
    pb_frame.pack(fill='x', side='bottom')
    pb_fill = tk.Frame(pb_frame, bg=clr_dir, height=3)
    pb_fill.place(x=0, y=0, relwidth=1, height=3)

    start_ts = time.time()
    def tick_dismiss():
        elapsed = time.time() - start_ts
        frac = max(0.0, 1.0 - elapsed / AUTO_DISMISS)
        try:
            pb_fill.place(x=0, y=0, relwidth=frac, height=3)
            if elapsed >= AUTO_DISMISS:
                _slide_out(toast, x_end, y_end, W, H)
            else:
                toast.after(100, tick_dismiss)
        except tk.TclError:
            pass

    # ── Slide-in animation ──
    def _slide_in(step=0):
        steps = 18
        if step > steps:
            tick_dismiss()
            return
        t_val = step / steps
        ease = 1 - (1 - t_val) ** 3   # cubic ease-out
        y_pos = int(y_start + (y_end - y_start) * ease)
        try:
            toast.geometry(f'{W}x{H}+{x_end}+{y_pos}')
            toast.after(14, lambda: _slide_in(step + 1))
        except tk.TclError:
            pass

    def _slide_out(win, xe, ye, w, h):
        steps = 14
        y_tgt = ye + h + 20

        def step_out(i=0):
            if i >= steps:
                try: win.destroy()
                except: pass
                return
            t_val = i / steps
            ease = t_val ** 2
            y_pos = int(ye + (y_tgt - ye) * ease)
            try:
                win.geometry(f'{w}x{h}+{xe}+{y_pos}')
                win.after(14, lambda: step_out(i + 1))
            except tk.TclError:
                pass
        step_out()

    _slide_in()


def _launch_strategy_watcher(root: tk.Tk):
    """
    Background thread that polls for new strategies and schedules
    a toast notification via root.after() (thread-safe).
    """
    seen_ids: set = set()
    initialized = False

    def _poll():
        nonlocal seen_ids, initialized
        try:
            resp = requests.get('http://localhost:8000/auto-strategies', timeout=3)
            if resp.status_code != 200:
                return
            data = resp.json().get('data', [])
            current_ids = {s['id'] for s in data}

            if not initialized:
                # First run: populate seen without toasting
                seen_ids = current_ids
                initialized = True
                return

            for s in data:
                if s['id'] not in seen_ids:
                    seen_ids.add(s['id'])
                    # Fetch candles for the chart
                    candles = []
                    try:
                        cr = requests.get('http://localhost:8000/market-state', timeout=3)
                        if cr.status_code == 200:
                            mdata = cr.json().get('data', {})
                            candles = mdata.get('candles', [])
                    except Exception:
                        pass
                    # Schedule toast on main thread
                    strategy_copy = dict(s)
                    candles_copy  = list(candles)
                    try:
                        root.after(0, lambda sc=strategy_copy, cc=candles_copy:
                                   _show_strategy_toast(sc, cc))
                    except Exception:
                        pass
        except Exception:
            pass

    def _loop():
        while True:
            try:
                _poll()
            except Exception:
                pass
            time.sleep(15)  # check every 15s

    t = Thread(target=_loop, daemon=True)
    t.start()


class AIdan:
    def __init__(self):
        self.threads = []
        self.root = None
        self.status_label = None
        from threading import Lock, Event
        self._mt5_lock = Lock()
        self._shutdown_event = Event()  # signals all service loops to exit cleanly
        
    # ── Color palette ──
    BG = '#0a0e14'
    BG_CARD = '#111822'
    BG_CARD_ALT = '#151d2b'
    ACCENT = '#00d4ff'
    ACCENT_DIM = '#0088aa'
    ACCENT_GLOW = '#003d4d'
    GREEN = '#00e676'
    RED = '#ff3d5a'
    ORANGE = '#ffab40'
    TEXT = '#e8edf4'
    TEXT_DIM = '#5c6a7e'
    BORDER = '#1e2a3a'

    def log(self, message, color="white"):
        """Mostrar mensaje en la GUI (thread-safe)."""
        fg_map = {
            'black': self.TEXT, 'green': self.GREEN, 'red': self.RED,
            'blue': self.ACCENT, 'orange': self.ORANGE, 'white': self.TEXT
        }
        fg = fg_map.get(color, self.TEXT)
        # v3.16.0 — encode-safe print: never crash on emoji even if stdout is cp1252
        try:
            print(message)
        except (UnicodeEncodeError, OSError):
            try:
                _enc = (getattr(sys.stdout, 'encoding', None) or 'ascii')
                print(message.encode(_enc, 'replace').decode(_enc, 'replace'))
            except Exception:
                pass
        if self.status_label and self.root:
            def _update_gui():
                try:
                    self._current_status_text = message
                    self.status_label.config(text=message, fg=fg)
                    if hasattr(self, '_log_text'):
                        tag = color if color in ('green', 'red', 'blue', 'orange', 'white') else 'white'
                        self._log_text.config(state='normal')
                        self._log_text.insert('end', message + '\n', tag)
                        self._log_text.see('end')
                        self._log_text.config(state='disabled')
                except tk.TclError:
                    pass
            try:
                self.root.after(0, _update_gui)
            except Exception:
                pass

    def _advance_progress(self, step_index=None):
        """Advance the progress bar and update step checklist (thread-safe)."""
        if hasattr(self, '_progress_steps'):
            self._progress_steps += 1
            frac = min(self._progress_steps / self._progress_total, 1.0)
            if hasattr(self, '_progress_target'):
                self._progress_target = frac
        if step_index is not None and hasattr(self, '_step_icons'):
            if 0 <= step_index < len(self._step_icons):
                icon = self._step_icons[step_index]
                green = self.GREEN
                try:
                    self.root.after(0, lambda: icon.config(text="✓", fg=green))
                except Exception:
                    pass

    def _mark_step_active(self, idx):
        """Mark a step as currently in progress (thread-safe)."""
        if hasattr(self, '_step_icons') and 0 <= idx < len(self._step_icons):
            icon = self._step_icons[idx]
            accent = self.ACCENT
            try:
                self.root.after(0, lambda: icon.config(text="⟳", fg=accent))
            except Exception:
                pass

    def _mark_step_error(self, idx):
        """Mark a step as failed (thread-safe)."""
        if hasattr(self, '_step_icons') and 0 <= idx < len(self._step_icons):
            icon = self._step_icons[idx]
            red = self.RED
            try:
                self.root.after(0, lambda: icon.config(text="✗", fg=red))
            except Exception:
                pass

    def _on_close(self):
        """v3.30.2 — Fast shutdown. Antes tardaba >5s por:
          - generate_daily_report() (network call sync)
          - sleep(0.5)
          - threads no daemon haciendo cleanup
        Ahora: signal threads, kick report en background, destroy UI inmediato,
        force-exit tras 1.5s. Total <2s vs ~5s antes.
        """
        self._anim_running = False
        # 1) Signal all service loops to exit ASAP
        try:
            self._shutdown_event.set()
        except Exception:
            pass

        # 2) Stop Telegram bot (solo flag, daemon thread morira con proceso)
        try:
            if getattr(self, '_telegram_bot', None):
                self._telegram_bot.stop()
        except Exception:
            pass

        # 3) Daily report en background — NO bloqueamos la UI
        def _bg_report():
            try:
                from src.reports.daily_report import generate_daily_report
                generate_daily_report()
            except Exception:
                pass
        try:
            from threading import Thread as _T
            _T(target=_bg_report, daemon=True, name="ShutdownReport").start()
        except Exception:
            pass

        # 4) MT5 disconnect (rapido, no bloquea UI)
        def _bg_mt5_close():
            try:
                import MetaTrader5 as _m5
                _m5.shutdown()
            except Exception:
                pass
        try:
            from threading import Thread as _T2
            _T2(target=_bg_mt5_close, daemon=True, name="ShutdownMT5").start()
        except Exception:
            pass

        # 5) Destroy UI inmediato
        try:
            self.root.destroy()
        except Exception:
            pass

        # 6) Force-exit 1.5s despues si quedan threads colgados (daemon=True deberia
        # bastar pero si hay alguno bloqueado en I/O largo, garantizamos exit limpio)
        def _force_exit():
            try:
                import time as _t
                _t.sleep(1.5)
                import os as _os
                _os._exit(0)
            except Exception:
                pass
        try:
            from threading import Thread as _T3
            _T3(target=_force_exit, daemon=True, name="ForceExit").start()
        except Exception:
            pass
    
    def _ollama_is_running(self):
        """Check if Ollama API is responding."""
        try:
            response = requests.get(OLLAMA_API, timeout=3)
            return response.status_code == 200
        except Exception:
            return False

    def _find_ollama_exe(self):
        """Find the Ollama executable path on this system."""
        # Common install locations
        candidates = [
            os.path.join(os.getenv('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama.exe'),
            os.path.join(os.getenv('LOCALAPPDATA', ''), 'Ollama', 'ollama.exe'),
            os.path.join(os.getenv('PROGRAMFILES', ''), 'Ollama', 'ollama.exe'),
            os.path.join(os.getenv('USERPROFILE', ''), 'AppData', 'Local', 'Programs', 'Ollama', 'ollama.exe'),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                return path

        # Try to find via PATH
        import shutil
        found = shutil.which('ollama')
        if found:
            return found

        # Search in registry for install location
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    if "ollama" in name.lower():
                        try:
                            install_loc = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                            exe = os.path.join(install_loc, 'ollama.exe')
                            if os.path.isfile(exe):
                                winreg.CloseKey(subkey)
                                winreg.CloseKey(key)
                                return exe
                        except Exception:
                            pass
                    winreg.CloseKey(subkey)
                except Exception:
                    continue
            winreg.CloseKey(key)
        except Exception:
            pass

        return None

    def _is_ollama_installed(self):
        """Check if Ollama is installed (regardless of whether it's running)."""
        # Check registry
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    if "ollama" in name.lower():
                        winreg.CloseKey(subkey)
                        winreg.CloseKey(key)
                        return True
                    winreg.CloseKey(subkey)
                except Exception:
                    continue
            winreg.CloseKey(key)
        except Exception:
            pass

        # Check if exe exists in common paths
        return self._find_ollama_exe() is not None

    def _start_ollama(self):
        """Start Ollama if installed but not running. Returns True if API responds."""
        if self._ollama_is_running():
            return True

        self.log("Iniciando Ollama...", "blue")

        # Try 'ollama serve' first (works if in PATH)
        exe = self._find_ollama_exe() or 'ollama'
        try:
            # Launch ollama serve in background (detached)
            subprocess.Popen(
                [exe, 'serve'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
        except Exception:
            # Try launching the app shortcut (Ollama app with tray icon)
            try:
                ollama_app = os.path.join(os.getenv('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'Ollama.exe')
                if os.path.isfile(ollama_app):
                    subprocess.Popen(
                        [ollama_app],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
            except Exception:
                pass

        # Wait for API to come up
        for i in range(20):
            time.sleep(1.5)
            if self._ollama_is_running():
                return True
            if i % 4 == 3:
                self.log(f"Esperando que Ollama responda... ({i+1}s)", "blue")

        return self._ollama_is_running()

    def check_ollama_installed(self):
        """Check if Ollama is installed and ensure it's running."""
        if self._ollama_is_running():
            return True
        if self._is_ollama_installed():
            return self._start_ollama()
        return False
    
    def install_ollama(self):
        """Descargar e instalar Ollama"""
        try:
            self.log("📥 Descargando Ollama...", "blue")
            
            # Descargar instalador
            temp_path = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            urllib.request.urlretrieve(OLLAMA_URL, temp_path)
            
            # Ejecutar instalador
            self.log("🔧 Instalando Ollama (sigue las instrucciones)...", "blue")
            subprocess.run([temp_path], check=True)
            
            # Esperar a que se complete la instalación
            self.log("⏳ Esperando que Ollama inicie...", "blue")
            time.sleep(10)
            
            # Verificar que funciona
            for i in range(30):
                try:
                    response = requests.get(OLLAMA_API, timeout=2)
                    if response.status_code == 200:
                        self.log("✓ Ollama instalado correctamente", "green")
                        return True
                except:
                    time.sleep(2)
            
            messagebox.showwarning("Advertencia", 
                "Ollama se instaló pero no responde.\n"
                "Reinicia tu PC y vuelve a ejecutar AIdan.")
            return False
            
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo instalar Ollama:\n{str(e)}")
            return False
    
    def check_ollama_model(self):
        """Verificar si el modelo está instalado"""
        try:
            response = requests.get(OLLAMA_API, timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                for model in models:
                    if OLLAMA_MODEL in model.get("name", ""):
                        return True
        except:
            pass
        return False
    
    def install_ollama_model(self):
        """Instalar el modelo de IA"""
        self.log(f"📦 Descargando modelo {OLLAMA_MODEL} (4GB, puede tardar)...", "blue")
        
        try:
            # Ejecutar ollama pull en background
            process = subprocess.Popen(
                ["ollama", "pull", OLLAMA_MODEL],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Esperar a que termine
            process.wait()
            
            if process.returncode == 0:
                self.log(f"✓ Modelo {OLLAMA_MODEL} instalado", "green")
                return True
            else:
                messagebox.showerror("Error", f"No se pudo descargar el modelo:\n{process.stderr.read()}")
                return False
                
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo instalar el modelo:\n{str(e)}")
            return False
    
    def check_vision_model(self):
        """Verificar si hay un modelo de visión (llava) instalado"""
        try:
            response = requests.get(OLLAMA_API, timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                for model in models:
                    name = model.get("name", "").lower()
                    if any(v in name for v in ['llava', 'llama3.2-vision', 'minicpm-v', 'bakllava']):
                        return True
        except:
            pass
        return False

    def install_vision_model(self):
        """Instalar llava para análisis de gráficos"""
        self.log("📦 Descargando modelo de visión (llava) para análisis de gráficos...", "blue")
        try:
            process = subprocess.Popen(
                ["ollama", "pull", "llava"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            process.wait()
            if process.returncode == 0:
                self.log("✓ Modelo de visión (llava) instalado", "green")
                return True
        except Exception as e:
            self.log(f"⚠️ No se pudo instalar llava: {e}. Análisis de imágenes no disponible.", "orange")
        return False

    def run_collector_service(self):
        """Servicio Collector integrado"""
        try:
            from src.common.config import Config
            from src.common.logging_setup import setup_logging
            from src.common.db import init_db, add_news
            from src.collector.feed_fetcher import FeedFetcher
            
            logger = setup_logging("collector", Config.LOG_LEVEL)
            logger.info("Initializing collector...")
            init_db()
            
            fetcher = FeedFetcher(logger)
            default_sources = [
                {"name": "Financial Times", "url": "https://feeds.ft.com/markets"},
                {"name": "Reuters", "url": "https://feeds.reuters.com/reuters/businessNews"},
                {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss"},
            ]
            
            sources = Config.get_sources() or default_sources
            logger.info(f"Collector ready with {len(sources)} sources")
            
            iteration = 0
            while True:
                try:
                    iteration += 1
                    news_items = fetcher.fetch_feeds(sources)
                    fetcher.save_to_file(news_items)
                    
                    added = 0
                    for item in news_items:
                        if add_news(item['url'], item['title'], item['summary'],
                                   item['language'], str(item['entities']), str(item['tags']),
                                   published_at=item.get('published_at')):
                            added += 1
                    
                    logger.info(f"[{iteration}] Added {added}/{len(news_items)} news")
                except Exception as e:
                    logger.error(f"Collector error: {e}")
                
                time.sleep(Config.COLLECTOR_INTERVAL)
        except Exception as e:
            print(f"FATAL Collector: {e}")
    
    def run_analyzer_service(self):
        """Servicio Analyzer integrado"""
        try:
            from src.common.config import Config
            from src.common.logging_setup import setup_logging
            from src.common.db import (init_db, get_unprocessed_news, mark_news_processed,
                                       add_alert, add_auto_strategy, get_news_fetch_time,
                                       get_strategies_pending_evaluation, auto_evaluate_strategy,
                                       get_alerts_pending_evaluation, auto_evaluate_alert,
                                       record_signal_result, has_recent_similar_strategy,
                                       has_active_opposite_strategy)
            from src.analyzer.news_analyzer import NewsAnalyzer
            from src.analyzer.technical import TechnicalAnalyzer
            from src.analyzer.technical_m15 import TechnicalAnalyzerM15, M15_PROFILE
            from src.analyzer.technical_h1 import TechnicalAnalyzerH1, H1_PROFILE
            from src.analyzer.technical_d1 import TechnicalAnalyzerD1, D1_PROFILE
            from src.analyzer.llm_auditor import audit_signal, build_signal_context

            logger = setup_logging("analyzer", Config.LOG_LEVEL)
            logger.info("Initializing analyzer...")
            init_db()

            analyzer = NewsAnalyzer(logger)
            tech = TechnicalAnalyzer(logger)
            # v3.19.0 — Track B M15 experimental (paralelo, sin tocar M5)
            tech_m15 = TechnicalAnalyzerM15(logger)
            _last_m15_scan = 0  # timestamp last scan M15
            M15_SCAN_INTERVAL = 60  # segundos entre scans M15 (M15 candles cambian cada 15min)
            # v3.31.7 — Warmup gate M15: 30 min para que cierren 2 velas M15 frescas
            # mientras AIdan observa en real-time (igual logica que M5 warmup 10min).
            # Bug observado: M15 disparaba trades a los 20s post-restart sobre data stale.
            M15_WARMUP_SECONDS = 1800  # 30 min (2 velas M15)
            _last_m15_warmup_log = 0
            # v3.55.0 — throttle del log del piso de ATR: con el piso en 8 el skip es la
            # mayoria de los ciclos (74% de los trades vivian debajo), y a 60s por ciclo
            # eso son ~1.400 lineas por dia. Se loguea 1 vez por hora.
            _last_m15_floor_log = 0
            # v3.20.0 — Track C H1 experimental (paralelo a M5+M15)
            tech_h1 = TechnicalAnalyzerH1(logger)
            _last_h1_scan = 0  # timestamp last scan H1
            H1_SCAN_INTERVAL = 300  # 5 min — H1 candles cambian cada 60min
            # v3.31.7 — Warmup gate H1: 60 min para que cierre al menos 1 vela H1 fresca.
            H1_WARMUP_SECONDS = 3600  # 60 min (1 vela H1)
            _last_h1_warmup_log = 0
            # v3.54.0 — Track D: swing DIARIO (D1) en SHADOW. Loguea, NO opera.
            # NO lleva warmup gate (a diferencia de M15/H1) y es a proposito: el warmup
            # existe para no operar sobre velas stale recien arrancado, pero este track
            # no opera, y ademas solo actua cuando aparece una vela D1 NUEVA — la vela
            # ya viene cerrada del broker, no depende de haberla observado en vivo.
            tech_d1 = TechnicalAnalyzerD1(logger)
            _last_d1_scan = 0        # timestamp del ultimo chequeo
            _last_d1_candle_ts = 0   # ts (hora servidor) de la ultima vela D1 ya procesada
            _d1_mode = getattr(Config, 'D1_TRACK_MODE', 'shadow') or 'shadow'
            D1_SCAN_INTERVAL = getattr(Config, 'D1_SCAN_INTERVAL_SEC', 900)
            logger.info(f"Track D1 (swing diario): modo={_d1_mode} scan cada {D1_SCAN_INTERVAL}s")

            # SMC Engine initialization
            from src.analyzer.mtf_analyzer import MTFAnalyzer
            from src.analyzer.smc import SMCEngine
            mtf = MTFAnalyzer(logger)
            smc = SMCEngine(logger, mtf)

            # Auto-Tuner initialization
            from src.optimizer.auto_tuner import AutoTuner
            tuner = AutoTuner(logger)
            # Run initial optimization on startup
            tuner.run_optimization(force=True)

            # Learning Engine initialization
            from src.optimizer.learning_engine import LearningEngine
            learner = LearningEngine(logger, tuner)
            try:
                from src.admin.main import set_learning_engine
                set_learning_engine(learner)
            except Exception as e:
                logger.debug(f"Learning engine API export: {e}")
            logger.info("Analyzer + SMC + AutoTuner + LearningEngine ready")

            # Calendar pre-news: track already-traded events across cycles
            _traded_calendar_events = set()
            # v3.40.16 — throttle de la auditoria del path calendar (1 log por etapa+evento)
            _cal_dbg_seen = set()
            def _cal_dbg(stage, detail='', key=None):
                try:
                    _k = key or stage
                    if _k in _cal_dbg_seen:
                        return
                    _cal_dbg_seen.add(_k)
                    from src.common.db import log_calendar_debug
                    log_calendar_debug(stage, detail)
                except Exception:
                    pass

            # MT5 Executor initialization
            mt5_exec = None
            self._mt5_exec = None  # expose for API endpoints (protected by _mt5_lock)
            if Config.MT5_ENABLED:
                try:
                    from src.broker.mt5_executor import MT5Executor
                    mt5_exec = MT5Executor(logger)
                    mt5_exec.set_smc_ref(smc)  # Inject SMC so executor can read htf_bias at archive time
                    if mt5_exec.connect():
                        logger.info("MT5 execution enabled")
                        with self._mt5_lock:
                            self._mt5_exec = mt5_exec
                        # Expose to API endpoints
                        try:
                            from src.admin.main import set_mt5_executor
                            set_mt5_executor(mt5_exec)
                        except Exception as e:
                            logger.debug(f"MT5 API export: {e}")
                        # v3.24.0 — Telegram startup alert
                        try:
                            from src.common.telegram_alerts import send_startup, is_configured
                            if is_configured():
                                _bal = None
                                try:
                                    _info = mt5_exec._mt5.account_info() if mt5_exec._mt5 else None
                                    if _info:
                                        _bal = _info.balance
                                except Exception:
                                    pass
                                send_startup(Config.VERSION, _bal)
                        except Exception as _se:
                            logger.debug(f"Telegram startup: {_se}")
                        # v3.28.0 — Telegram bot bidireccional (commands)
                        try:
                            from src.common.telegram_bot import TelegramBot
                            self._telegram_bot = TelegramBot(mt5_executor_provider=lambda: mt5_exec)
                            if self._telegram_bot.start():
                                logger.info("Telegram bidirectional bot started (use /help in chat)")
                        except Exception as _tbe:
                            logger.debug(f"Telegram bot start: {_tbe}")

                        # v3.28.0 — Pre-warmup Ollama models (background thread, no bloquea)
                        def _warmup_models():
                            try:
                                import requests as _r
                                models_to_warm = list(set(Config.LLM_MODELS.values()))
                                # Pre-warm en orden de prioridad (mas usados primero)
                                priority = ['signal_audit', 'news_prefilter', 'news_analysis_ollama', 'post_trade', 'pre_planner']
                                ordered = []
                                seen = set()
                                for task in priority:
                                    m = Config.LLM_MODELS.get(task)
                                    if m and m not in seen:
                                        ordered.append(m)
                                        seen.add(m)
                                for m in models_to_warm:
                                    if m not in seen and m != 'deepseek-r1:14b':  # skip 14b (no live use)
                                        ordered.append(m)
                                        seen.add(m)
                                for m in ordered:
                                    try:
                                        logger.info(f"Pre-warming Ollama model: {m}")
                                        _r.post(f"{Config.OLLAMA_URL}/api/generate",
                                                json={'model': m, 'prompt': 'ok', 'stream': False,
                                                      'keep_alive': '5m',
                                                      'options': {'num_predict': 1, 'num_ctx': 512}},
                                                timeout=60)
                                    except Exception as _e:
                                        logger.debug(f"Pre-warm {m}: {_e}")
                            except Exception as _e:
                                logger.debug(f"Pre-warmup error: {_e}")
                        Thread(target=_warmup_models, daemon=True, name="OllamaWarmup").start()
                    else:
                        logger.warning("MT5 connection failed - paper mode only")
                        mt5_exec = None
                except ImportError:
                    logger.warning("MetaTrader5 not installed - paper mode only")
                except Exception as e:
                    logger.error(f"MT5 init error: {e}")

            def _try_mt5_execute(sid, direction, entry_price, sl, tp, confidence, track='m5', trigger_type=None):
                """v3.28.0: track param para consensus boost + spread guardian.
                track: 'm5'|'m15'|'h1'.
                v3.31.4: trigger_type='pre_planned' -> lot cap 0.05 (news event safety)."""
                if mt5_exec and mt5_exec.is_ready():
                    # Block new trades 10min before market close (Friday 20:50+ UTC)
                    try:
                        from datetime import datetime, timezone, timedelta
                        utc_now = datetime.now(timezone.utc)
                        if utc_now.weekday() == 4 and utc_now.hour == 20 and utc_now.minute >= 50:
                            logger.info(f"MT5 blocked: market closing soon, skipping #{sid}")
                            return None
                    except Exception as e:
                        logger.debug(f"MT5 market-close check: {e}")

                    # v3.32.1 — User awake window: no abrir trades cerca del horario en que
                    # el user duerme. Para H1 (expiry 180min) cerrar 22:00 AR garantiza
                    # cierre antes de 01:00 AR. Para M15 (45min) cerrar 23:00 AR garantiza
                    # cierre antes de 23:45. M5 (15min) sin restriccion practica.
                    # Override via env vars TRADING_END_HOUR_AR / H1_LAST_OPEN_AR.
                    try:
                        import os as _os
                        # Default: user opera entre 06:00 y 22:00 AR (UTC -3)
                        # Pero queremos NO ABRIR trades nuevos cerca del cierre del usuario
                        end_hour_ar = int(_os.getenv('TRADING_END_HOUR_AR', '22'))  # default 22:00 AR
                        h1_last_open_ar = int(_os.getenv('H1_LAST_OPEN_AR', '19'))  # H1 mas estricto
                        m15_last_open_ar = int(_os.getenv('M15_LAST_OPEN_AR', '22'))  # M15 hasta 22
                        # AR es UTC-3 (sin DST). hora_ar = utc_hour - 3 (con mod 24)
                        ar_hour = (utc_now.hour - 3) % 24
                        # Track-aware cutoff
                        cutoff = {'h1': h1_last_open_ar, 'm15': m15_last_open_ar, 'm5': end_hour_ar}.get(track, end_hour_ar)
                        # Ventana operativa: 06:00 AR hasta cutoff_ar
                        if ar_hour < 6 or ar_hour >= cutoff:
                            logger.info(f"User-window block: skip #{sid} {track} at {ar_hour:02d}h AR (cutoff {cutoff}h)")
                            return None
                    except Exception as e:
                        logger.debug(f"User-window check: {e}")
                    # v3.40.15 — COOLDOWN POST-PERDIDA (decision del checkpoint 12 Jun).
                    # Unico hallazgo que paso el gate adversarial: re-entradas <=5min tras
                    # una perdida = 24% WR vs 37% (n=76, p=0.009, broker-truth, sostenido
                    # 4/5 quincenas; #611 y #633->#634-class = el patron). Senal generada
                    # dentro del cooldown -> SKIP definitivo (status skipped_cooldown), no
                    # delay: la senal nace de la vela de panico, esperar no la arregla.
                    try:
                        _cd_min = float(getattr(Config, 'COOLDOWN_AFTER_LOSS_MIN', 5) or 0)
                    except Exception:
                        _cd_min = 5.0
                    if _cd_min > 0:
                        try:
                            import sqlite3 as _sq_cd
                            from datetime import datetime as _cd_dt
                            from src.common.db import now_ar as _cd_now
                            _cn = _sq_cd.connect(DB_PATH)
                            _r = _cn.execute("SELECT MAX(mt5_closed_at) FROM auto_strategies WHERE mt5_pnl < 0 AND mt5_closed_at IS NOT NULL").fetchone()
                            _cn.close()
                            if _r and _r[0]:
                                _lc = _cd_dt.strptime(str(_r[0]).split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
                                _cd_elapsed = (_cd_now() - _lc).total_seconds() / 60.0
                                if 0 <= _cd_elapsed < _cd_min:
                                    logger.info(f"COOLDOWN post-perdida: skip #{sid} {trigger_type or ''} — ultima perdida hace {_cd_elapsed:.1f}min (<{_cd_min:.0f}min)")
                                    try:
                                        _cn = _sq_cd.connect(DB_PATH)
                                        _cn.execute("UPDATE auto_strategies SET status='skipped_cooldown' WHERE id=? AND status='active'", (sid,))
                                        _cn.commit(); _cn.close()
                                    except Exception:
                                        pass
                                    return None
                        except Exception as _cde:
                            logger.debug(f"cooldown check #{sid}: {_cde}")

                    # v3.39.0 — Skip bounce-entry: ¿la vela de entrada va EN CONTRA?
                    # PUT entrando sobre vela verde / CALL sobre vela roja = bounce.
                    # Validado p=0.000 (bounce 22% WR vs 45%). MODE off/shadow/active.
                    _bounce_mode = (getattr(Config, 'SKIP_BOUNCE_ENTRY', 'shadow') or 'shadow').lower()
                    if _bounce_mode != 'off':
                        try:
                            _bc = tech._fetch_candles()
                            if _bc and len(_bc) >= 1:
                                _ec = _bc[-1]
                                _o = _ec.get('open'); _cl = _ec.get('close')
                                if _o is not None and _cl is not None and _o != _cl:
                                    _is_bounce = (_cl > _o) if direction == 'PUT' else (_cl < _o)
                                    _will_skip = bool(_is_bounce and _bounce_mode == 'active')
                                    try:
                                        from src.common.db import log_bounce_decision
                                        log_bounce_decision(sid, direction, trigger_type, _o, _cl,
                                                            _is_bounce, _bounce_mode, _will_skip)
                                    except Exception:
                                        pass
                                    if _is_bounce and _bounce_mode == 'active':
                                        logger.info(f"Skip bounce-entry [ACTIVE]: #{sid} {direction} entra sobre vela contra-direccion (O={_o:.5f} C={_cl:.5f}) -> SKIP")
                                        try:
                                            import sqlite3 as _sq
                                            _cn = _sq.connect(DB_PATH)
                                            _cn.execute("UPDATE auto_strategies SET status='skipped_bounce' WHERE id=?", (sid,))
                                            _cn.commit(); _cn.close()
                                        except Exception:
                                            pass
                                        return None
                                    elif _is_bounce:
                                        logger.info(f"Skip bounce-entry [SHADOW]: #{sid} {direction} habria saltado (vela contra-direccion O={_o:.5f} C={_cl:.5f})")
                        except Exception as _be:
                            logger.debug(f"bounce-entry check #{sid}: {_be}")

                    # v3.40.14 — Conciencia de eventos (SHADOW por default): etiqueta CADA
                    # ejecucion (normal y retry — ambas pasan por aca) con su proximidad al
                    # evento HIGH/MEDIUM mas cercano del calendario (revivido v3.40.4) y
                    # marca que habria bloqueado el escudo: senal CIEGA (structure/m15/h1/smc,
                    # que no saben de eventos) o VIEJA (>10min, caso #625: el retry ejecuto
                    # una senal de 27min en el primer minuto del spike) dentro de la ventana.
                    # news/pre_planned/calendar dentro de la ventana NO se marcan (son las
                    # jugadas de evento por diseno). En shadow solo loguea, NUNCA bloquea.
                    _ew_mode = (getattr(Config, 'EVENT_WINDOW_MODE', 'shadow') or 'shadow').lower()
                    if _ew_mode != 'off':
                        try:
                            from src.common.event_window import get_event_proximity
                            _prox = get_event_proximity()
                            if _prox:
                                _stale_mins = None
                                _ew_trig = trigger_type
                                try:
                                    import sqlite3 as _sq_ew
                                    from datetime import datetime as _ew_dt
                                    from src.common.db import now_ar as _ew_now
                                    _cn = _sq_ew.connect(DB_PATH)
                                    # v3.40.15 FIX: leer tambien trigger_type de la fila — la mayoria
                                    # de los call sites no lo pasan como param -> None -> el shadow
                                    # trataba TODO como 'structure' (ciego) y marco mal a un news (#635).
                                    _r = _cn.execute("SELECT created_at, trigger_type FROM auto_strategies WHERE id=?", (sid,)).fetchone()
                                    _cn.close()
                                    if _r and _r[0]:
                                        _c0 = _ew_dt.strptime(str(_r[0]).split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
                                        _stale_mins = round((_ew_now() - _c0).total_seconds() / 60.0, 1)
                                    if _r and _r[1]:
                                        _ew_trig = _r[1]
                                except Exception:
                                    _stale_mins = None
                                _blind = (_ew_trig or 'structure') in ('structure', 'm15_structure', 'h1_structure', 'smc')
                                _would_block = bool(_prox.get('in_window') and (_blind or (_stale_mins or 0) > 10))
                                try:
                                    from src.common.db import log_event_window
                                    log_event_window(sid, _ew_trig, direction, _stale_mins, _prox, _would_block, _ew_mode)
                                except Exception:
                                    pass
                                if _would_block:
                                    _ev_name = _prox.get('next_event') if (_prox.get('mins_to_next') or 9e9) <= (_prox.get('mins_since_prev') or 9e9) else _prox.get('prev_event')
                                    if _ew_mode == 'active':
                                        logger.info(f"Event-window [ACTIVE]: skip #{sid} {_ew_trig or 'structure'} dentro de ventana de '{_ev_name}' (stale={_stale_mins}min)")
                                        return None
                                    logger.info(f"Event-window [SHADOW]: #{sid} {_ew_trig or 'structure'} habria sido bloqueado — ventana de '{_ev_name}' (stale={_stale_mins}min)")
                        except Exception as _ewe:
                            logger.debug(f"event-window check #{sid}: {_ewe}")

                    # v3.28.0 Spread guardian
                    try:
                        from src.common.slippage_tracker import is_spread_acceptable
                        ok, current_spread = is_spread_acceptable(mt5_exec._mt5, max_pips=Config.MAX_SPREAD_PIPS)
                        if not ok:
                            logger.warning(f"Spread guardian: blocking #{sid} {direction}, spread {current_spread}p > {Config.MAX_SPREAD_PIPS}p")
                            return None
                    except Exception as _se:
                        logger.debug(f"Spread guardian check: {_se}")
                    # v3.28.0 Consensus tracker + boost
                    lot_mult = 1.0
                    try:
                        from src.common.consensus_tracker import record_signal, check_consensus
                        record_signal(track, direction)
                        # Check si hay 1+ otro track con misma direction reciente
                        consensus_count = check_consensus(direction, window_sec=Config.CONSENSUS_WINDOW_SEC, exclude_track=track)
                        if consensus_count >= 1:
                            lot_mult = Config.CONSENSUS_BOOST_MULTIPLIER
                            logger.info(f"Consensus boost: #{sid} {track} {direction} - {consensus_count} other track(s) agree -> lot x{lot_mult}")
                            try:
                                from src.common.telegram_alerts import send_alert, is_configured
                                if is_configured():
                                    send_alert(f"Consensus boost activado #{sid} {direction} (track {track}, +{consensus_count} convergence) -> lote x{lot_mult}", level='INFO', silent=True)
                            except Exception:
                                pass
                    except Exception as _ce:
                        logger.debug(f"Consensus check: {_ce}")
                    try:
                        ticket = mt5_exec.open_position(sid, direction, entry_price, sl, tp, confidence, lot_multiplier=lot_mult, trigger_type=trigger_type)
                        if ticket:
                            logger.info(f"MT5 executed: ticket #{ticket} for strategy #{sid} (track={track}, lot_mult={lot_mult})")
                            # v3.40.23 — aviso Telegram de APERTURA (con la confianza)
                            try:
                                from src.common.telegram_alerts import send_trade_open, is_configured
                                if is_configured():
                                    send_trade_open(sid, direction, trigger_type or track or 'structure',
                                                    entry_price, confidence, sl, tp)
                            except Exception as _toe:
                                logger.debug(f"Telegram open alert skip: {_toe}")
                        return ticket
                    except Exception as e:
                        logger.error(f"MT5 execution error for #{sid}: {e}")
                return None

            def _apply_learning_adjustments(conf, trigger_type, session=None, direction=None, htf_bias=None, news_title=None):
                """Apply learning engine confidence adjustments including blocked patterns and news categories."""
                adj = 0
                if not _learn_adj:
                    return conf
                # Trigger-based penalty/bonus
                tp = _learn_adj.get('trigger_penalties', {}).get(trigger_type, 0)
                adj += tp
                # Session-based penalty/bonus
                if session:
                    sp = _learn_adj.get('session_penalties', {}).get(session, 0)
                    adj += sp
                # News category penalty/bonus (for news/calendar triggers)
                ncp = 0
                if news_title and trigger_type in ('news', 'calendar', 'pre_planned'):
                    ncat = _classify_news_category(news_title)
                    ncp = _learn_adj.get('news_category_penalties', {}).get(ncat, 0)
                    adj += ncp
                # Blocked pattern penalty: if this exact combo was identified as a loser
                blocked = _learn_adj.get('blocked_patterns', [])
                if blocked and direction and session:
                    _htf = htf_bias or 'unknown'
                    pattern_key = f"{direction}|{_htf}|{session}|{trigger_type}"
                    if pattern_key in blocked:
                        adj -= 25
                        logger.info(f"Learning BLOCKED PATTERN: {pattern_key} → conf -{25}")
                new_conf = max(5, min(95, conf + adj))
                if adj != 0:
                    logger.info(f"Learning adj: {trigger_type} conf {conf}→{new_conf} (trigger={tp}, session={_learn_adj.get('session_penalties', {}).get(session, 0) if session else 0}, news_cat={ncp}, pattern={'blocked' if adj <= -25 else 'ok'})")
                return new_conf

            def _fetch_candles_snapshot(count=30):
                """Get candles for snapshot: MT5 first, Yahoo fallback."""
                try:
                    if mt5_exec and mt5_exec.is_ready():
                        raw = mt5_exec.get_candles(timeframe='5min', count=count)
                        if raw and len(raw) > 5:
                            return [{'o': round(c['open'], 5), 'h': round(c['high'], 5),
                                     'l': round(c['low'], 5), 'c': round(c['close'], 5),
                                     't': c['datetime']} for c in raw[-count:]]
                except Exception as e:
                    logger.debug(f"Candle snapshot MT5: {e}")
                try:
                    raw = tech._fetch_candles()
                    if raw:
                        return [{'o': round(c['open'], 5), 'h': round(c['high'], 5),
                                 'l': round(c['low'], 5), 'c': round(c['close'], 5),
                                 't': c['datetime']} for c in raw[-count:]]
                except Exception as e:
                    logger.debug(f"Candle snapshot Yahoo: {e}")
                return None

            # ── Startup: expire and evaluate pending strategies from previous session ──
            try:
                import sqlite3 as _sq3
                from src.common.db import DB_PATH, now_ar
                _conn = _sq3.connect(DB_PATH)
                expired_count = _conn.execute("""
                    UPDATE auto_strategies SET status = 'expired'
                    WHERE expires_at < ? AND status = 'active'
                """, (now_ar(),)).rowcount
                _conn.commit()
                _conn.close()
                if expired_count:
                    logger.info(f"Startup: marked {expired_count} strategies as expired")

                pending = get_strategies_pending_evaluation()
                if pending:
                    candles = tech._fetch_candles()
                    current_price = tech.get_market_state().get('price', 0)
                    for row in pending:
                        sid, direction, entry_price, sl, tp = row[0], row[1], row[2], row[3], row[4]
                        conf, expiry_min = row[5], row[6]
                        created_at_str, expires_at_str = row[7], row[8]
                        news_title, trigger_type = row[9], row[10]
                        be_triggered = bool(row[11]) if len(row) > 11 and row[11] else False
                        if not current_price or not entry_price:
                            continue
                        # v3.39.1 FIX: no evaluar con outcome SINTETICO (current_price) una
                        # posicion que sigue ABIERTA en MT5 -> reintroducia el win-amputation
                        # v3.9.0 / P&L fantasma en trade_archive en cada restart. Si la posicion
                        # sigue viva en MT5, la salteamos y deja que el main loop la cierre/evalue
                        # con el P&L real. (Bug confirmado por auditoria.)
                        # STARTUP-EVAL GUARD v3.53.2 — ahora FAIL-CLOSED, alineado con su
                        # gemelo in-loop (ver AIdan_TodoEnUno.py:3042, patron `_tk='unknown'`).
                        #
                        # Antes fallaba ABIERTO por DOS lados y en los dos casos la ejecucion
                        # caia a la evaluacion por precio, que es justo el bug v3.39.1:
                        #   (1) estaba condicionado a mt5_exec.is_ready() — que es
                        #       `connected and not kill_switch` — asi que con MT5 todavia
                        #       levantando (arranque por Task Scheduler 4 AM) o con el kill
                        #       switch puesto, el guard NI CORRIA;
                        #   (2) su `except` logueaba a debug y seguia de largo.
                        #
                        # El fix saca MT5 de la ecuacion: alcanza el TICKET en la DB. Si hay
                        # ticket, la estrategia llego al broker => la evalua el main loop con
                        # el P&L REAL de los deals (sync_closed_positions), que siempre es
                        # mejor que un outcome sintetico por precio. Si NO hay ticket, nunca
                        # se ejecuto => se evalua la SENAL normalmente y el guard de v3.51.1
                        # la mantiene afuera de trade_archive.
                        #
                        # El valor inicial 'unknown' es truthy A PROPOSITO: si la lectura de
                        # la DB falla, se saltea. En la duda NO adivinamos.
                        _tk_su = 'unknown'
                        try:
                            _c2 = _sq3.connect(DB_PATH, timeout=15.0)
                            _r2 = _c2.execute("SELECT mt5_ticket FROM auto_strategies WHERE id=?", (sid,)).fetchone()
                            _c2.close()
                            _tk_su = _r2[0] if _r2 else None
                        except Exception as _se:
                            logger.warning(f"Startup eval: no se pudo leer el ticket de #{sid} "
                                           f"({_se}) -> skip por precaucion (no evaluamos por precio)")
                        if _tk_su:
                            logger.info(f"Startup eval: #{sid} tiene ticket #{_tk_su} -> skip "
                                        f"(la evalua el main loop con el P&L real del broker)")
                            continue
                        hit_tp, hit_sl, hit_be = False, False, False
                        # SL/TP fijos — trailing desactivado.
                        # Solo trackea HWM para learning.
                        tp_distance = abs(tp - entry_price)
                        trailing_step = 0
                        effective_sl = sl
                        _high_water = 0
                        if candles and tp_distance > 0.00005:
                            from datetime import datetime as dt
                            try:
                                entry_ts = dt.strptime(str(created_at_str).split('.')[0], '%Y-%m-%d %H:%M:%S')
                            except Exception:
                                entry_ts = None
                            if entry_ts:
                                for c in candles:
                                    c_ts = c.get('datetime', c.get('timestamp', 0))
                                    try:
                                        if isinstance(c_ts, (int, float)):
                                            from datetime import timezone as tz_mod, timedelta as td_mod
                                            c_time = dt.fromtimestamp(c_ts, tz=tz_mod(td_mod(hours=-3))).replace(tzinfo=None)
                                        else:
                                            c_time = dt.strptime(str(c_ts).split('.')[0], '%Y-%m-%d %H:%M:%S')
                                    except Exception:
                                        continue
                                    if c_time < entry_ts:
                                        continue
                                    if direction == 'CALL':
                                        progress = c['high'] - entry_price
                                    else:
                                        progress = entry_price - c['low']
                                    _high_water = max(_high_water, progress)
                                    # Check TP/SL hits
                                    if direction == 'CALL':
                                        if c['high'] >= tp:
                                            hit_tp = True
                                            break
                                        if c['low'] <= effective_sl:
                                            if trailing_step > 0:
                                                hit_be = True
                                            else:
                                                hit_sl = True
                                            break
                                    else:  # PUT
                                        if c['low'] <= tp:
                                            hit_tp = True
                                            break
                                        if c['high'] >= effective_sl:
                                            if trailing_step > 0:
                                                hit_be = True
                                            else:
                                                hit_sl = True
                                            break
                        # Persist be_triggered flag to DB if detected during candle analysis
                        if be_triggered:
                            try:
                                from src.common.db import mark_be_triggered
                                mark_be_triggered(sid)
                            except Exception as e:
                                logger.debug(f"mark_be_triggered: {e}")
                        pip = 0.0001
                        try:
                            est_spread = tech.get_session_info()['spread_est']
                        except Exception:
                            est_spread = 1.0  # safe default
                        if hit_tp:
                            result = 'win'
                            pips_result = abs(tp - entry_price) / pip - est_spread
                        elif hit_be or be_triggered:
                            # BE flag: trailing SL reached BE — evaluate as break_even
                            # Calculate actual pips lost to spread for display
                            if direction == 'CALL':
                                spread_loss = (current_price - entry_price) / pip
                            else:
                                spread_loss = (entry_price - current_price) / pip
                            result = 'break_even'
                            pips_result = round(spread_loss, 1)  # show real spread impact
                            logger.info(f"Strategy #{sid} BE flag: spread cost {pips_result:+.1f}p -> evaluated as BREAK_EVEN")
                        elif hit_sl:
                            result = 'loss'
                            pips_result = -(abs(sl - entry_price) / pip + est_spread)
                        else:
                            pips_result = ((current_price - entry_price) / pip - est_spread) if direction == 'CALL' else ((entry_price - current_price) / pip - est_spread)
                            min_pips = tuner.get_params().get('min_pips_for_win', 1.5)
                            result = 'win' if pips_result >= min_pips else 'loss'
                        exit_px = tp if hit_tp else (entry_price if hit_be else (sl if hit_sl else current_price))
                        # v3.49.1 — el setup_type REAL vive en el snapshot de entrada
                        # (v3.48.0 lo empezo a guardar). Antes esta rama lo ADIVINABA
                        # raspando palabras del titulo con una lista mezclada es/en
                        # ('soporte', 'resistencia', 'rebote', 'breakout' pelado) y como el
                        # caller le gana al entry_context en la cadena de fallback de
                        # archive_trade, esa adivinanza PISABA al valor bueno -> el archivo
                        # quedaba con DOS vocabularios y los buckets del aprendizaje
                        # (paso 6 de dynamic_conf, block_setup_type) se fragmentaban.
                        # Ahora: snapshot primero, raspado solo si no hay nada.
                        _setup_type = ''
                        try:
                            from src.common.db import get_entry_context as _gec
                            _setup_type = (_gec(sid) or {}).get('setup_type', '') or ''
                        except Exception:
                            _setup_type = ''
                        if not _setup_type:
                            _title_lower = (news_title or '').lower()
                            for _st in ['breakout', 'breakdown', 'bb_rejection', 'reversal',
                                        'momentum', 'crossover', 'continuation']:
                                if _st in _title_lower:
                                    _setup_type = _st
                                    break
                        ctx = {'entry_price': entry_price, 'direction': direction, 'confidence': conf,
                               'setup_type': _setup_type, 'trigger_type': trigger_type or '',
                               'market_trend': tech.get_market_state().get('trend', ''),
                               'rsi_at_entry': tech.get_market_state().get('rsi', 0)}
                        auto_evaluate_strategy(sid, result, exit_px, round(pips_result, 1), ctx)
                        try:
                            from src.common.db import archive_trade, get_entry_context
                            ms = tech.get_market_state()
                            # Prefer entry-time snapshot over exit-time (for accurate learning)
                            entry_ctx = get_entry_context(sid)
                            if entry_ctx:
                                # v3.49.1 — el setup_type del snapshot manda sobre cualquier
                                # inferencia hecha al cerrar (vocabulario canonico unico).
                                if entry_ctx.get('setup_type'):
                                    ctx['setup_type'] = entry_ctx['setup_type']
                                ctx['rsi_at_entry'] = entry_ctx.get('rsi', 0)
                                ctx['avg_range_pips'] = entry_ctx.get('avg_range_pips', 0)
                                ctx['volatility'] = entry_ctx.get('volatility', '')
                                ctx['market_trend'] = entry_ctx.get('trend') or ms.get('trend', '')
                                ctx['trend_strength'] = entry_ctx.get('trend_strength') or ms.get('trend_strength', '')
                                ctx['htf_bias'] = entry_ctx.get('htf_bias', '')
                            else:
                                # Fallback: use exit-time snapshot
                                ctx['volatility'] = ms.get('volatility', '')
                                ctx['trend_strength'] = ms.get('trend_strength', '')
                                ctx['avg_range_pips'] = ms.get('avg_range_pips', 0)
                                try:
                                    if smc:
                                        ctx['htf_bias'] = smc.get_status().get('htf_bias', '') or ''
                                except Exception:
                                    ctx['htf_bias'] = ''
                            archive_trade(sid, result, exit_px, round(pips_result, 1), ctx)
                        except Exception as e:
                            logger.warning(f"Archive trade #{sid}: {e}")
                        # Post-trade analysis in background thread
                        try:
                            from src.analyzer.post_trade_analyzer import analyze_closed_trade
                            from src.common.db import save_post_trade_analysis, save_learning_insight
                            _pt_data = {
                                'strategy_id': sid,  # v3.53.7: para leer el recorrido (MFE)
                                'result': result, 'pips': round(pips_result, 1), 'direction': direction,
                                'trigger_type': trigger_type or '', 'entry_price': entry_price, 'exit_price': exit_px,
                                'stop_loss': sl, 'take_profit': tp, 'sl_pips': abs(sl - entry_price) / pip,
                                'tp_pips': abs(tp - entry_price) / pip, 'session': ctx.get('session', ''),
                                'rsi': ctx.get('rsi_at_entry', 50), 'trend': ctx.get('market_trend', ''),
                                'trend_strength': ctx.get('trend_strength', ''), 'htf_bias': ctx.get('htf_bias', ''),
                                'volatility': ctx.get('volatility', ''), 'news_title': news_title or '',
                                'confidence': conf, 'duration_min': expiry_min or 15, 'mt5_pnl': 0,
                            }
                            def _run_pt(s_id, data, res):
                                try:
                                    # v3.53.6 — no fabricar lecciones sobre trades que no existieron.
                                    # Una señal frenada por el cooldown / "market closing" / spread
                                    # gate no tiene fill, ni SL real, ni duracion, pero el analyzer
                                    # igual escribia un insight sobre los pips TEORICOS del TP/SL
                                    # nominal ("#886: Ajustar el SL a 2.5 pips" sobre una señal que
                                    # nunca opero), y eso va a learning_insights ->
                                    # get_learning_adjustments -> compute_adaptive_sl_tp.
                                    # `is None` = no se pudo determinar -> se corre igual
                                    # (fail-open: comportamiento previo; una lectura de DB fallada
                                    # no debe apagar el post-trade en silencio).
                                    from src.common.db import strategy_was_executed as _was_exec
                                    if _was_exec(s_id) is False:
                                        logger.info(f"Post-trade #{s_id}: SKIP — la señal nunca se ejecuto (sin ticket ni P&L)")
                                        return
                                    analysis = analyze_closed_trade(data)
                                    if analysis:
                                        save_post_trade_analysis(s_id, analysis, res)
                                        save_learning_insight('post_trade', analysis.get('key_lesson', ''), data=analysis)
                                        logger.info(f"Post-trade #{s_id}: {analysis.get('key_lesson', '')}")
                                except Exception as _e:
                                    logger.debug(f"Post-trade analysis #{s_id} error: {_e}")
                            Thread(target=_run_pt, args=(sid, _pt_data, result), daemon=True).start()
                        except Exception as e:
                            logger.debug(f"Post-trade thread #{sid}: {e}")
                        logger.info(f"Startup eval #{sid}: {result.upper()} | {direction} entry={entry_price:.5f} exit={exit_px:.5f} | {pips_result:+.1f}p")
                    logger.info(f"Startup: evaluated {len(pending)} pending strategies")
            except Exception as e:
                logger.error(f"Startup eval error: {e}", exc_info=True)

            iteration = 0
            _weekend_logged = False
            _planned_today = False
            _planned_date = None
            # v3.9.1 WARMUP GATE: skip strategy generation for the first N seconds after startup.
            # When AIdan starts mid-session, the indicators are populated from historical candles
            # but the bot has no memory of recent cycles. It can detect "BULLISH STRONG + bounce
            # off support" 5-15 minutes AFTER the actual bounce already occurred — a stale signal.
            # Empirical: trade #371 (2026-05-04) created 30s after startup, lost -$3.80 in 90s.
            # 10-min warmup ensures at least 2 fresh M5 candles close while AIdan watches in real-time
            # before generating strategies. News/structure/SMC affected; pre_planned exempt.
            _analyzer_warmup_start = time.time()
            WARMUP_SECONDS = 600  # 10 minutes
            logger.info(f"Analyzer warmup active: no strategies generated for first {WARMUP_SECONDS}s ({WARMUP_SECONDS//60}min)")
            while not self._shutdown_event.is_set():
                _cycle_start = time.time()
                try:
                    iteration += 1

                    # ── Weekend filter: forex market closed Sat & Sun ──
                    from datetime import datetime as _wdt, timezone as _wtz
                    _w_utc = _wdt.now(_wtz.utc)
                    # Market closed: Friday after 21:00 UTC until Sunday 22:00 UTC
                    _is_weekend = (_w_utc.weekday() == 5) or (_w_utc.weekday() == 6 and _w_utc.hour < 22) or (_w_utc.weekday() == 4 and _w_utc.hour >= 21)
                    if _is_weekend:
                        if not _weekend_logged:
                            logger.info("Forex market closed (weekend) — pausing until Sunday 22:00 UTC")
                            _weekend_logged = True
                        time.sleep(300)  # check every 5 min
                        continue
                    _weekend_logged = False

                    # ── Pre-plan strategies for tomorrow (20:00-23:00 UTC) ──
                    try:
                        _hour_utc = _w_utc.hour
                        _today_str = _w_utc.strftime('%Y-%m-%d')
                        if 20 <= _hour_utc <= 23 and (_planned_date != _today_str):
                            from src.analyzer.pre_planner import plan_next_day_strategies
                            ms = tech.get_market_state()
                            _plan_ctx = {
                                'trend': ms.get('trend', 'unknown'),
                                'rsi': ms.get('rsi', 50),
                                'volatility': ms.get('volatility', 'normal'),
                            }
                            logger.info(f"Pre-planner: running for {_today_str} (hour UTC={_hour_utc})")
                            planned_ids = plan_next_day_strategies(_plan_ctx)
                            _planned_date = _today_str
                            if planned_ids:
                                logger.info(f"Pre-planner: created {len(planned_ids)} strategies for tomorrow")
                            else:
                                logger.info(f"Pre-planner: no strategies generated (Gemma may have skipped events)")
                    except Exception as _pe:
                        logger.warning(f"Pre-planner error: {_pe}", exc_info=True)

                    # ── Activate planned strategies close to event time ──
                    # v3.31.4 — Bug fix: pre-plans usaban SL/TP del profile M5 (5p/15p)
                    # que es absurdo para news events. Ahora usa planned_sl_pips/planned_tp_pips
                    # del LLM. Fallback: SL 20p / TP 40p (wider para acomodar volatility
                    # de news release). Tambien skip si confidence < 60 (bug: conf 50 entraba).
                    try:
                        from src.common.db import activate_due_planned_strategies
                        activated = activate_due_planned_strategies(minutes_before=5)
                        if activated:
                            logger.info(f"Activated {len(activated)} planned strategies: {activated}")
                            # Update prices for newly activated planned strategies
                            for _act_id in activated:
                                try:
                                    import sqlite3 as _sq3
                                    from datetime import timedelta  # v3.40.1 FIX: timedelta no estaba en scope -> NameError en el UPDATE de l.1408 (re-pricing/expiry de pre-plan fallaba en silencio dentro del try). Detectado por pyflakes.
                                    _act_price = tech.get_market_state().get('price', 0)
                                    if _act_price > 0:
                                        _pip = 0.0001
                                        _conn = _sq3.connect(DB_PATH)
                                        _cur = _conn.cursor()
                                        # v3.31.4: leer SL/TP planificados por el LLM + confidence
                                        _cur.execute("""SELECT direction, confidence, planned_sl_pips, planned_tp_pips
                                                        FROM auto_strategies WHERE id = ?""", (_act_id,))
                                        _row = _cur.fetchone()
                                        if _row:
                                            _dir, _conf, _planned_sl, _planned_tp = _row
                                            # v3.31.4 — Min conf 60 para pre-plans (era 50 sin check)
                                            if _conf is not None and _conf < 60:
                                                logger.warning(f"Pre-plan #{_act_id}: conf {_conf} < 60, marcando skipped")
                                                _cur.execute("UPDATE auto_strategies SET status='auto_skipped' WHERE id=?", (_act_id,))
                                                _conn.commit()
                                                _conn.close()
                                                continue
                                            # v3.31.4: usar planned_sl/tp del LLM con piso minimo
                                            # para evitar SL pegado (lot escala a max_lot 0.10).
                                            # News events necesitan volatility buffer: SL >=15p / TP >=30p
                                            _sl_p = max(float(_planned_sl or 20), 15.0)
                                            _tp_p = max(float(_planned_tp or 40), 25.0)
                                            if _dir == 'CALL':
                                                _sl = _act_price - _sl_p * _pip
                                                _tp = _act_price + _tp_p * _pip
                                            else:
                                                _sl = _act_price + _sl_p * _pip
                                                _tp = _act_price - _tp_p * _pip
                                            _cur.execute("""
                                                UPDATE auto_strategies SET entry_price = ?, stop_loss = ?, take_profit = ?,
                                                    expires_at = ? WHERE id = ?
                                            """, (_act_price, _sl, _tp, now_ar() + timedelta(minutes=30), _act_id))
                                            _conn.commit()
                                            logger.info(f"Pre-plan #{_act_id} activated: {_dir} entry={_act_price:.5f} SL={_sl_p:.1f}p TP={_tp_p:.1f}p conf={_conf}")
                                        _conn.close()
                                except Exception as e:
                                    logger.debug(f"Planned activation DB: {e}")
                    except Exception as _ae:
                        logger.warning(f"Planned activation error: {_ae}", exc_info=True)

                    news_items = get_unprocessed_news()

                    alerts_sent = 0
                    strategies_created = 0
                    # Get current price for alert auto-evaluation
                    _alert_price = tech.get_market_state().get('price', 0)
                    # Load learning adjustments (confidence penalties from learning engine)
                    _learn_adj = {}
                    try:
                        from src.common.db import get_learning_adjustments
                        _learn_adj = get_learning_adjustments()
                    except Exception as e:
                        logger.debug(f"Learning adjustments: {e}")
                    # Source conflict resolution: track directions from each source
                    cycle_signals = []  # list of {'source': str, 'direction': str, 'confidence': int}

                    # v3.30.1 — Paralelizar analyzer.analyze() para batches de news.
                    # Antes: 5 news x 2-3s LLM = 10-15s seriales
                    # Ahora: ThreadPoolExecutor max 5 workers en paralelo = ~3s
                    # analyzer.analyze() es thread-safe (no escribe a DB internamente,
                    # solo llama LLM y retorna dict).
                    _precomputed = None
                    if len(news_items) >= 2:
                        try:
                            from concurrent.futures import ThreadPoolExecutor
                            workers = min(5, len(news_items))
                            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='news-llm') as _ex:
                                _precomputed = list(_ex.map(
                                    lambda item: analyzer.analyze(item[0], item[2], item[3], item[4], item[5]),
                                    news_items
                                ))
                            logger.info(f"News batch analyzed in parallel: {len(news_items)} items / {workers} workers")
                        except Exception as _pe:
                            logger.warning(f"News parallel analyze failed: {_pe}, fallback to serial")
                            _precomputed = None

                    for _news_idx, (news_id, url, title, summary, entities, tags) in enumerate(news_items):
                        # v3.40.10: guard del analyze serial (LLM/red). Un throw aca abortaba el
                        # ciclo entero (incl. SMC/M15/H1, que corren despues). El path paralelo ya
                        # cae a None solo; este faltaba. Aislar -> el ciclo sigue aunque 1 news falle.
                        try:
                            if _precomputed is not None and _news_idx < len(_precomputed):
                                result = _precomputed[_news_idx]
                            else:
                                result = analyzer.analyze(news_id, title, summary, entities, tags)
                        except Exception as _ane:
                            logger.error(f"News analyze error (item {_news_idx}): {_ane}")
                            result = None

                        if result:
                            # Freshness check: stale news (>30min) get price=0 so they don't show as "Evaluando"
                            _use_price = _alert_price
                            try:
                                from datetime import datetime as _fdt
                                _fts = get_news_fetch_time(news_id)
                                if _fts:
                                    _ft = _fdt.strptime(str(_fts).split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
                                    from datetime import timezone, timedelta as _ftd
                                    _ar_tz = timezone(_ftd(hours=-3))
                                    _age = (_fdt.now(_ar_tz).replace(tzinfo=None) - _ft).total_seconds() / 60
                                    if _age > 30:
                                        _use_price = 0
                                        logger.info(f"Stale news #{news_id} ({_age:.0f}min old): alert without price (no eval)")
                            except Exception as e:
                                logger.debug(f"Stale news check: {e}")
                            add_alert(news_id, result['impact_score'], result['level'],
                                    result['explanation'], result['eur_usd_impact'],
                                    result['market_implications'],
                                    result.get('analysis_method', 'keywords'),
                                    result.get('should_operate', False),
                                    result.get('direction', 'NEUTRAL'),
                                    result.get('confidence', 50),
                                    price_at_alert=_use_price)
                            alerts_sent += 1

                        # Auto-strategy: check against active profile (independent of should_alert)
                        if result and result.get('direction', 'NEUTRAL') != 'NEUTRAL':
                            from src.common.db import get_active_profile
                            profile = get_active_profile()
                            prof_min_impact = profile.get('min_impact', 75)
                            prof_min_conf = profile.get('min_confidence', 50)  # centralized default matching profile schema
                            prof_direction = profile.get('direction', 'any')
                            prof_sl = profile.get('stop_loss_pips', 5)
                            prof_tp = profile.get('take_profit_pips', 10)

                            score_ok = result['impact_score'] >= prof_min_impact
                            direction = result.get('direction', 'NEUTRAL')

                            # v3.14.0: news bypass solo aplica si dirección NO es counter-HTF.
                            # Empirical (9 historical bypass trades):
                            #   News aligned with HTF: 7/7 wins (PUTs in HTF bearish)
                            #   News counter-HTF: 0/2 wins (CALLs in HTF bearish)
                            # Razón: news low-conf direction is uncertain. Counter-HTF + uncertain
                            # direction + fighting macro trend = stacked against us. Better to skip.
                            _bypass_htf = None
                            try:
                                if smc:
                                    _bypass_htf = smc.get_status().get('htf_bias')
                            except Exception:
                                pass
                            _is_counter_htf_bypass = _bypass_htf and _bypass_htf != 'neutral' and (
                                (direction == 'CALL' and _bypass_htf == 'bearish') or
                                (direction == 'PUT' and _bypass_htf == 'bullish')
                            )

                            # v3.12.1 BUGFIX + v3.14.0: bypass solo si impact alto Y NO counter-HTF
                            _bypass_eligible = result.get('impact_score', 0) >= 55 and not _is_counter_htf_bypass
                            _initial_min_conf = 30 if _bypass_eligible else prof_min_conf
                            conf_ok = result.get('confidence', 0) >= _initial_min_conf
                            dir_ok = prof_direction == 'any' or result.get('direction') == prof_direction
                            if _is_counter_htf_bypass and result.get('confidence', 0) < prof_min_conf and result.get('impact_score', 0) >= 55:
                                logger.info(f"v3.14.0 bypass blocked: news {direction} counter-HTF (htf={_bypass_htf}), conf {result.get('confidence',0):.0f} would have bypassed but counter-HTF kills it")

                            # v3.16.0 — Counter-HTF news gate (path regular).
                            # Bug observado en #387 (5 May 2026): news CALL counter-HTF (htf bearish)
                            # con conf 60.5 (apenas pasó threshold 60) cerró por expiry-loss.
                            # El precio recuperó a +TP 85min después del cierre. El 15-min expiry
                            # no le dió chance al setup.
                            # v3.35.1 — Threshold relajado de 65 → 60 (= base min_conf).
                            # Razon: hoy 26 May, 4 news directional, 0 strategies. 3 CALLs counter-HTF
                            # con conf 58.5-62.5 todas bloqueadas. v3.34.0 (entry quality gates) +
                            # v3.35.0 (ML predictor) ya filtran exhaustion entries y low-P(win) trades,
                            # asi que duplicar con threshold 65 acumula filtros sin razon empirica.
                            if score_ok and conf_ok and dir_ok and _is_counter_htf_bypass and result.get('confidence', 0) < 60:
                                logger.info(f"v3.35.1 counter-HTF news gate: {direction} conf {result.get('confidence',0):.1f} < 60 (HTF {_bypass_htf}), skip")
                                conf_ok = False  # block

                            if score_ok and conf_ok and dir_ok:
                                try:
                                    from datetime import datetime as dt
                                    fetch_ts = get_news_fetch_time(news_id)
                                    is_fresh = True
                                    if fetch_ts:
                                        fetch_time = dt.strptime(str(fetch_ts).split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
                                        from datetime import timezone, timedelta as td
                                        ar_tz = timezone(td(hours=-3))
                                        age_min = (dt.now(ar_tz).replace(tzinfo=None) - fetch_time).total_seconds() / 60
                                        is_fresh = age_min <= 30
                                        if not is_fresh:
                                            logger.info(f"Skip auto-strategy: news {age_min:.0f}min old (max 30)")

                                    if is_fresh:
                                        market = tech.get_market_state()
                                        price = market.get('price', 0)
                                        if price > 0:
                                            # v3.8.0 ATR ceiling: skip news strategy in extreme volatility
                                            # SL becomes too tight relative to candle noise, hits SL on rebotes.
                                            _news_atr = market.get('avg_range_pips', 0)
                                            if _news_atr > 6.0:
                                                logger.info(f"ATR ceiling: skipping news {direction}, ATR {_news_atr:.1f}p > 6.0p")
                                                price = 0
                                        if price > 0:
                                            # AutoTuner block: skip if news setup type has poor win rate
                                            if tuner.is_setup_blocked('news'):
                                                logger.info(f"AutoTuner: blocking news {direction}, setup type blocked")
                                                price = 0  # skip creation

                                            # Market hours check: skip outside active sessions
                                            if price > 0:
                                                _news_tp = tuner.get_params()
                                                if _news_tp.get('block_outside_sessions', False):
                                                    from datetime import datetime as _ndt, timezone as _ntz
                                                    _n_utc_h = _ndt.now(_ntz.utc).hour
                                                    _n_london = _news_tp.get('session_london_start', 7) <= _n_utc_h < _news_tp.get('session_london_end', 16)
                                                    _n_ny = _news_tp.get('session_ny_start', 13) <= _n_utc_h < _news_tp.get('session_ny_end', 21)
                                                    if not _n_london and not _n_ny:
                                                        logger.info(f"Session filter: skipping news {direction}, outside active sessions (UTC {_n_utc_h}h)")
                                                        price = 0

                                            # HTF bias filter: penalize (not block) news signals against H1 trend
                                            # High-impact news can reverse trends, so we reduce confidence instead of blocking
                                            _htf_penalty = 0
                                            if price > 0:
                                                try:
                                                    _news_htf = None
                                                    if smc:
                                                        _news_smc_st = smc.get_status()
                                                        _news_htf = _news_smc_st.get('htf_bias', None)
                                                    if _news_htf and _news_htf != 'neutral':
                                                        if (direction == 'CALL' and _news_htf == 'bearish') or (direction == 'PUT' and _news_htf == 'bullish'):
                                                            _htf_penalty = 10  # will reduce confidence later instead of blocking
                                                            logger.info(f"HTF filter: penalizing news {direction} -10 conf (H1 bias is {_news_htf})")
                                                except Exception as e:
                                                    logger.debug(f"HTF filter: {e}")

                                            # v3.37.4 — Counter-HTF gate reforzado con ML conf.
                                            # El gate v3.35.1 (~line 1478) usa LLM conf que puede ser sobre-optimista.
                                            # Caso real #542 (28 May): LLM conf 72.5 paso el gate, ML predictor lo
                                            # bajaba a 57.5, trade counter-HTF perdio. Si chequeabamos ML conf < 60
                                            # ahi -> bloqueado, ahorrabamos -$2.40. Solo aplica cuando es counter-HTF
                                            # (_htf_penalty>0) Y hay ML predictor disponible (USE_ML_CONFIDENCE=true).
                                            if price > 0 and _htf_penalty > 0:
                                                try:
                                                    from src.optimizer.confidence_predictor import predict_confidence
                                                    from datetime import datetime as _ndt3, timezone as _ntz3
                                                    _now_pre = _ndt3.now(_ntz3.utc)
                                                    _sess_pre = ''
                                                    try:
                                                        _sess_pre = tech.get_session_info().get('session', '')
                                                    except Exception:
                                                        pass
                                                    _ml_signal_pre = {
                                                        'trigger_type': 'news',
                                                        'direction': direction,
                                                        'session': _sess_pre,
                                                        'htf_bias': _news_htf or '',
                                                        'market_trend': market.get('trend', ''),
                                                        'trend_strength': market.get('trend_strength', ''),
                                                        'volatility': market.get('volatility', ''),
                                                        'rsi_at_entry': market.get('rsi', 50),
                                                        'avg_range_pips': market.get('avg_range_pips', 3),
                                                        'hour_utc': _now_pre.hour,
                                                        'day_of_week': _now_pre.weekday(),
                                                    }
                                                    _ml_conf_pre = predict_confidence(_ml_signal_pre)
                                                    if _ml_conf_pre is not None and _ml_conf_pre < 60:
                                                        logger.info(f"v3.37.4 counter-HTF ML gate: blocking news {direction} (LLM conf {result.get('confidence',0):.0f}, ML conf {_ml_conf_pre} < 60, HTF {_news_htf})")
                                                        price = 0
                                                except Exception as _mle:
                                                    logger.debug(f"counter-HTF ML pre-check error: {_mle}")

                                            # Dedup: skip if similar news strategy exists recently
                                            if price > 0 and has_recent_similar_strategy(direction, price, 'news', 30):
                                                logger.info(f"Dedup: skipping {direction} news near {price:.5f}, similar exists within 30min")
                                                price = 0

                                        if price > 0:
                                            # v3.51.0 PERILLA 1 — piso de expiry para news.
                                            # El profile activo no trae 'expiry_minutes', asi que el tp_cap
                                            # caia siempre en cap_mult 2.25 (el default 15) y el expiry se
                                            # calculaba DE ese TP chico -> se retroalimentaban hacia abajo.
                                            # Copia local del profile: NO muta el dict que usa el resto de
                                            # la rama (min_impact/min_confidence/direction siguen intactos).
                                            _news_floor = max(0, int(getattr(Config, 'NEWS_MIN_EXPIRY_MIN', 45)))
                                            _news_profile = profile
                                            if _news_floor > 15:
                                                _news_profile = dict(profile)
                                                _news_profile['expiry_minutes'] = _news_floor

                                            # Adaptive SL/TP based on ATR + structure levels
                                            adaptive = tech.compute_adaptive_sl_tp(direction, price, market, _news_profile, trigger_type='news', sl_tp_advice=_learn_adj.get('sl_tp_advice') if _learn_adj else None)
                                            sl = adaptive['sl']
                                            tp = adaptive['tp']

                                            # Adaptive expiry based on TP distance and current volatility
                                            avg_range_pips = market.get('avg_range_pips', 5.0)
                                            avg_range_pips = avg_range_pips if avg_range_pips > 0 else 5.0
                                            expiry_min = max(15, int(adaptive['tp_pips'] / avg_range_pips * 5))
                                            # el piso pisa al calculo de arriba; el cap sigue siendo el techo
                                            expiry_min = max(expiry_min, _news_floor)
                                            expiry_min = min(expiry_min, max(60, _news_floor))  # cap at 60 min

                                            # Spread gate: skip if estimated spread > 50% of SL
                                            session_info = TechnicalAnalyzer.get_session_info()
                                            est_spread = session_info['spread_est']
                                            if est_spread > adaptive['sl_pips'] * 0.50:
                                                logger.info(f"Spread gate: skipping news strategy, spread {est_spread:.1f}p > 50% of SL {adaptive['sl_pips']:.1f}p")
                                            else:
                                                # Adjust entry price for spread
                                                half_spread = est_spread / 2
                                                if direction == 'CALL':
                                                    price = price + half_spread * 0.0001
                                                else:
                                                    price = price - half_spread * 0.0001

                                                # Get alert_id from DB (last inserted)
                                                import sqlite3
                                                from src.common.db import DB_PATH
                                                conn = sqlite3.connect(DB_PATH, timeout=15.0)
                                                c = conn.cursor()
                                                c.execute("SELECT id FROM alerts WHERE news_id=? ORDER BY id DESC LIMIT 1", (news_id,))
                                                row = c.fetchone()
                                                conn.close()
                                                if row:
                                                    # Anti-contradiction: skip if active opposite strategy
                                                    opposite = has_active_opposite_strategy(direction)
                                                    if opposite:
                                                        logger.info(f"Anti-contradiction: skipping {direction} news, active #{opposite[0]} {opposite[1]}")
                                                    elif row:
                                                        news_snap = _fetch_candles_snapshot(30)
                                                        _news_session_info = tech.get_session_info()
                                                        _news_session = _news_session_info.get('session', '')
                                                        _news_conf = _apply_learning_adjustments(result.get('confidence', 50), 'news', _news_session, direction=direction, news_title=title)
                                                        if _htf_penalty > 0:
                                                            _news_conf = max(10, _news_conf - _htf_penalty)
                                                        _news_base_conf = prof_min_conf  # min confidence from active profile

                                                        # v3.9.1 Warmup gate: skip first 10 min after analyzer startup
                                                        _warmup_elapsed = time.time() - _analyzer_warmup_start
                                                        # v3.11.0 ATR floor + hour gate + conf ceiling
                                                        from datetime import datetime as _ndt2, timezone as _ntz2
                                                        _news_atr_now = market.get('avg_range_pips', 0)
                                                        _news_utc_h = _ndt2.now(_ntz2.utc).hour
                                                        if _warmup_elapsed < WARMUP_SECONDS:
                                                            logger.info(f"Warmup gate: skipping news {direction}, analyzer running {_warmup_elapsed:.0f}s < {WARMUP_SECONDS}s warmup")
                                                        elif _news_atr_now < 2.0:
                                                            logger.info(f"ATR floor: skipping news {direction}, ATR {_news_atr_now:.1f}p < 2.0p (deadzone)")
                                                        # v3.17.0 — REMOVED hour gate (UTC 12/14/20).
                                                        # Original data (26 trades) era cross-version (v3.7-v3.11)
                                                        # con multiples cambios de filtros simultaneos -> data contaminada.
                                                        # No representa comportamiento de v3.16.x. Re-evaluar con data fresca.
                                                        elif _news_conf >= 80:
                                                            logger.info(f"Conf ceiling: blocking news {direction}, conf {_news_conf} >= 80 (anti-predictive)")
                                                        # v3.12.0 Effective min_conf for news: lower threshold to 30 when impact_score >= 55
                                                        # Empirical: 5 of 8 conf<50 trades won (62% WR, +$12.10), and 4 of those 5
                                                        # were news with impact_score 55-91. High-impact news moves price even when
                                                        # Groq's directional confidence is low — uncertainty about direction != lack of move.
                                                        # Min confidence gate: skip if below EFFECTIVE threshold
                                                        elif _news_conf < (30 if result.get('impact_score', 0) >= 55 else prof_min_conf):
                                                            _eff_min = 30 if result.get('impact_score', 0) >= 55 else prof_min_conf
                                                            logger.info(f"Min confidence gate: skipping news {direction}, conf {_news_conf} < effective min {_eff_min} (impact={result.get('impact_score')})")
                                                        # v3.57.0 — TOGGLE del track news (`ENABLE_NEWS_TRACK`, env, sin rebuild).
                                                        # Corta la EJECUCION direccional, no la medicion: el alert ya quedo
                                                        # guardado arriba, asi que la habilidad direccional del LLM se sigue
                                                        # midiendo con `tools/measure_news_llm_error.py` estando apagado.
                                                        # DEFAULT = 'true' (news sigue operando) a proposito: el user decidio
                                                        # el 7-ago "news NO se apaga, se arregla", y hay un veredicto
                                                        # pre-declarado para ~28 ago (v3.51.0). Esto entrega la PERILLA, no
                                                        # la decision de girarla.
                                                        elif os.getenv('ENABLE_NEWS_TRACK', 'true').strip().lower() in ('0', 'false', 'no', 'off'):
                                                            logger.info(f"News track OFF (ENABLE_NEWS_TRACK): no se crea trade para {direction} conf={_news_conf} — el alert SI queda medido")
                                                        else:
                                                            # FAST PATH: create strategy + MT5 order FIRST, audit async
                                                            # Build entry context for atomic persist (avoids race with fast MT5 fills)
                                                            _news_htf_real = ''
                                                            try:
                                                                if smc:
                                                                    _news_htf_real = smc.get_status().get('htf_bias', '') or ''
                                                            except Exception:
                                                                pass
                                                            _news_entry_ctx = {
                                                                'rsi': market.get('rsi', 0),
                                                                'rsi_zone': market.get('rsi_zone', ''),
                                                                'avg_range_pips': market.get('avg_range_pips', 0),
                                                                'volatility': market.get('volatility', ''),
                                                                'trend': market.get('trend', ''),
                                                                'trend_strength': market.get('trend_strength', ''),
                                                                'momentum': market.get('momentum', ''),
                                                                'htf_bias': _news_htf_real,
                                                                # v3.48.0 — setup_type en el snapshot de entrada. Sin esto el
                                                                # archive lo guardaba vacio (546/546 NULL) y moria el blend
                                                                # historico de dynamic_conf + block_setup_type + adjust_setup_confidence.
                                                                'setup_type': f"news_{result.get('level') or 'unknown'}",
                                                            }
                                                            # v3.57.0 — LATENCIA de la noticia, clasificada EN EL MOMENTO.
                                                            # Research 19-ago: sobre 993 eventos USD de alto impacto
                                                            # (2022-2025) la deriva post-release esta contenida en las velas
                                                            # +1..+5 (el spike); desde la +6 los T dan 0,14-0,69. Y ~80% del
                                                            # movimiento se completa en los primeros 3 MINUTOS.
                                                            # Medido sobre los 871 alerts direccionales de AIdan: mediana de
                                                            # deteccion 8,9 min y solo el 7,7% dentro de los 3 min => AIdan
                                                            # entra, tipicamente, cuando el movimiento informativo ya paso.
                                                            # Retrospectivamente el bucket <=3min rinde 60,5% vs 51,3% de
                                                            # baseline, PERO n=43 con CI95 [45,6-73,6] que CRUZA el baseline
                                                            # => NO pasa el gate, y encima corre sobre `alert_result` (no
                                                            # broker-truth). Por eso aca no se filtra ni se ajusta NADA: se
                                                            # guarda el numero para poder medirlo limpio contra `mt5_pnl`.
                                                            try:
                                                                _pub_ar = get_news_fetch_time(news_id)
                                                                if _pub_ar:
                                                                    from datetime import datetime as _ldt
                                                                    from src.common.db import now_ar as _lnow
                                                                    _p = _ldt.strptime(str(_pub_ar).split('.')[0].replace('T', ' '),
                                                                                       '%Y-%m-%d %H:%M:%S')
                                                                    _news_entry_ctx['news_latency_min'] = round(
                                                                        (_lnow().replace(tzinfo=None) - _p).total_seconds() / 60.0, 1)
                                                            except Exception as _lex:
                                                                logger.warning(f"news_latency_min no calculada para news #{news_id}: {_lex}")
                                                            sid = add_auto_strategy(
                                                                alert_id=row[0], news_title=title,
                                                                direction=direction, entry_price=price,
                                                                stop_loss=sl, take_profit=tp,
                                                                confidence=_news_conf,
                                                                impact_score=result['impact_score'],
                                                                candles_snapshot=news_snap,
                                                                expiry_minutes=expiry_min,
                                                                entry_context=_news_entry_ctx)
                                                            if sid:
                                                                strategies_created += 1
                                                                # v3.35.0 — ML confidence predictor para news (AUC 0.75 en test).
                                                                # Solo activa si USE_ML_CONFIDENCE=true. Fallback a _news_conf si modelo no aplicable.
                                                                _exec_conf = _news_conf
                                                                try:
                                                                    from src.optimizer.confidence_predictor import predict_confidence
                                                                    from datetime import datetime as _dt, timezone as _tz
                                                                    _now = _dt.now(_tz.utc)
                                                                    _ml_signal = {
                                                                        'trigger_type': 'news',
                                                                        'direction': direction,
                                                                        'session': _news_session_info.get('session', '') if _news_session_info else '',
                                                                        'htf_bias': _news_htf_real,
                                                                        'market_trend': market.get('trend', ''),
                                                                        'trend_strength': market.get('trend_strength', ''),
                                                                        'volatility': market.get('volatility', ''),
                                                                        'rsi_at_entry': market.get('rsi', 50),
                                                                        'avg_range_pips': market.get('avg_range_pips', 3),
                                                                        'hour_utc': _now.hour,
                                                                        'day_of_week': _now.weekday(),
                                                                        # enriched features (use medians from training)
                                                                    }
                                                                    _ml_conf = predict_confidence(_ml_signal)
                                                                    if _ml_conf is not None:
                                                                        logger.info(f"ML predictor override (news): heuristic conf {_news_conf} -> ML conf {_ml_conf}")
                                                                        _exec_conf = _ml_conf
                                                                except Exception as _ml_e:
                                                                    logger.debug(f"ML predictor error (news): {_ml_e}")
                                                                cycle_signals.append({'source': 'news', 'direction': direction, 'confidence': _exec_conf})
                                                                logger.info(f"Auto-strategy #{sid}: {direction} @ {price:.5f} SL={sl:.5f} TP={tp:.5f} [{adaptive.get('method','?')}] conf={_exec_conf} (audit pending)")
                                                                _try_mt5_execute(sid, direction, price, sl, tp, _exec_conf)

                                                                # Gemma 4 audit in background — veto closes position if needed
                                                                def _async_news_audit(_sid=sid, _dir=direction, _price=price, _conf=_news_conf, _base=_news_base_conf,
                                                                                      _ms=ms, _adaptive=adaptive, _sess_info=_news_session_info):
                                                                    try:
                                                                        _actx = build_signal_context(_dir, _price, _ms, _adaptive, _sess_info, _conf, setup_type='news', source='news')
                                                                        _aud = audit_signal(_actx)
                                                                        if _aud:
                                                                            if _aud['agree']:
                                                                                _new_conf = min(95, _conf + min(_aud['confidence_adjustment'], 10))
                                                                                logger.info(f"Gemma audit NEWS #{_sid}: AGREE | adj={_aud['confidence_adjustment']:+d} -> conf={_new_conf} | {_aud['reasoning']}")
                                                                                # Update confidence in DB
                                                                                import sqlite3 as _sq
                                                                                _cn = _sq.connect(DB_PATH)
                                                                                _cn.execute("UPDATE auto_strategies SET confidence = ? WHERE id = ? AND status = 'active' AND (mt5_status IS NULL OR mt5_status NOT IN ('closed', 'error'))", (_new_conf, _sid))
                                                                                _cn.commit(); _cn.close()
                                                                            else:
                                                                                _new_conf = max(10, _conf + _aud['confidence_adjustment'])
                                                                                logger.info(f"Gemma audit NEWS #{_sid}: DISAGREE | adj={_aud['confidence_adjustment']:+d} -> conf={_new_conf} | {_aud['reasoning']}")
                                                                                # Don't close MT5 position — SL/TP handle risk.
                                                                                # Just record reduced confidence for learning.
                                                                                import sqlite3 as _sq
                                                                                _cn = _sq.connect(DB_PATH)
                                                                                _cn.execute("UPDATE auto_strategies SET confidence = ? WHERE id = ? AND status = 'active' AND (mt5_status IS NULL OR mt5_status NOT IN ('closed', 'error'))", (_new_conf, _sid))
                                                                                _cn.commit(); _cn.close()
                                                                                if _new_conf < _base:
                                                                                    logger.info(f"Gemma low-conf NEWS #{_sid}: conf {_new_conf} < {_base} — keeping open, SL/TP protect")
                                                                        else:
                                                                            logger.info(f"Gemma audit NEWS #{_sid}: no response — strategy stands")
                                                                    except Exception as _e:
                                                                        logger.warning(f"Gemma async audit error for #{_sid}: {_e}")
                                                                Thread(target=_async_news_audit, daemon=True).start()
                                except Exception as e:
                                    logger.error(f"Auto-strategy error: {e}")

                        mark_news_processed(news_id)

                    if alerts_sent > 0 or strategies_created > 0:
                        logger.info(f"[{iteration}] Alerts: {alerts_sent} | Strategies: {strategies_created}")

                    # ── Run auto-tuner optimization every 30min ──
                    try:
                        logger.info(f"[{iteration}] AutoTuner: checking if optimization cycle is due...")
                        tuner_result = tuner.run_optimization()
                        if tuner_result:
                            logger.info(f"[{iteration}] AutoTuner: {tuner_result.get('status')} | improvements={len(tuner_result.get('improvements', []))} | trades_analyzed={tuner_result.get('trades', 'N/A')}")
                        else:
                            logger.info(f"[{iteration}] AutoTuner: skipped (interval not reached yet)")
                    except Exception as e:
                        logger.error(f"AutoTuner error: {e}", exc_info=True)

                    # ── Learning Engine tick ──
                    try:
                        learner.tick()
                        # Reload learning adjustments after tick so strategies use fresh insights
                        try:
                            _learn_adj = get_learning_adjustments()
                        except Exception as e:
                            logger.debug(f"Refresh learning adj: {e}")
                    except Exception as e:
                        logger.error(f"LearningEngine error: {e}", exc_info=True)

                    # ── Calendar Pre-News Trading: straddle before high-impact events ──
                    try:
                        from datetime import datetime as _cal_dt, timezone as _cal_tz, timedelta as _cal_td
                        from src.analyzer.trading_knowledge import get_entry_rules_summary

                        cal_resp = requests.get('http://localhost:8000/calendar', timeout=5)
                        if cal_resp.status_code == 200:
                            cal_json = cal_resp.json()
                            cal_events = cal_json if isinstance(cal_json, list) else cal_json.get('events', cal_json.get('data', []))
                            utc_now = _cal_dt.now(_cal_tz.utc)
                            # v3.40.16: si el cache del /calendar sirve un intento vacio justo en la
                            # ventana de un evento, antes era invisible — 1 log por hora como maximo
                            if not cal_events:
                                _cal_dbg('feed_empty', '/calendar respondio 200 con 0 eventos', key=f"fe_{utc_now.strftime('%d%H')}")
                            entry_rules = get_entry_rules_summary()

                            for evt in cal_events:
                                try:
                                    evt_impact = evt.get('impact', '').strip()
                                    if evt_impact not in ('High', 'Medium'):
                                        continue

                                    # Parse event datetime
                                    evt_date_str = evt.get('date', '')
                                    if not evt_date_str:
                                        continue
                                    # Handle ISO format with timezone offset
                                    try:
                                        evt_dt = _cal_dt.fromisoformat(evt_date_str)
                                    except (ValueError, TypeError):
                                        continue
                                    # Convert to UTC for comparison
                                    if evt_dt.tzinfo is not None:
                                        evt_utc = evt_dt.astimezone(_cal_tz.utc)
                                    else:
                                        evt_utc = evt_dt.replace(tzinfo=_cal_tz.utc)

                                    # Only events in the next 30 minutes
                                    minutes_until = (evt_utc - utc_now).total_seconds() / 60
                                    if minutes_until < 0 or minutes_until > 30:
                                        continue

                                    # Dedup: build a unique key for this event
                                    evt_key = f"{evt.get('event', '')}_{evt_date_str}"
                                    if evt_key in _traded_calendar_events:
                                        continue

                                    evt_name = evt.get('event', 'Unknown Event')
                                    evt_currency = evt.get('currency', '')
                                    logger.info(f"[{iteration}] Calendar: {evt_name} ({evt_impact}) in {minutes_until:.0f}min - preparing straddle")
                                    _cal_dbg('detected', f"{evt_name} ({evt_impact}) in {minutes_until:.0f}min", key=f"det_{evt_key}")

                                    # Get market state
                                    ms = tech.get_market_state()
                                    price = ms.get('price', 0)
                                    support = ms.get('support', 0)
                                    resistance = ms.get('resistance', 0)
                                    if price <= 0 or support <= 0 or resistance <= 0:
                                        # v3.40.16: salida que era SILENCIOSA (sospechosa del 0-filas del 12 Jun)
                                        _cal_dbg('sr_zero', f"{evt_name}: price={price} S={support} R={resistance}", key=f"sr0_{evt_key}")
                                        continue

                                    from src.common.db import get_active_profile
                                    profile = get_active_profile()

                                    # Confidence boost based on impact
                                    base_conf = profile.get('min_confidence', 50)  # centralized default matching profile schema
                                    if evt_impact == 'High':
                                        cal_conf_bonus = 15
                                    else:
                                        cal_conf_bonus = 5

                                    # Capture candles snapshot for chart (MT5 priority)
                                    cal_candles_snap = _fetch_candles_snapshot(30)

                                    # STRADDLE: generate CALL above resistance and PUT below support
                                    straddle_sides = [
                                        {'direction': 'CALL', 'zone': resistance, 'label': f'CALL zona {resistance:.4f}'},
                                        {'direction': 'PUT',  'zone': support,    'label': f'PUT zona {support:.4f}'},
                                    ]

                                    # AutoTuner block: skip if calendar setup type has poor win rate
                                    if tuner.is_setup_blocked('calendar'):
                                        logger.info(f"AutoTuner: blocking calendar straddle for {evt_name}, setup type blocked")
                                        _cal_dbg('autotuner_block', evt_name, key=f"at_{evt_key}")
                                        _traded_calendar_events.add(evt_key)
                                        continue

                                    # Market hours / session awareness for calendar
                                    _cal_tp = tuner.get_params()
                                    _cal_session_penalty = 0
                                    if _cal_tp.get('block_outside_sessions', False):
                                        _cal_utc_h = utc_now.hour
                                        _cal_in_london = _cal_tp.get('session_london_start', 7) <= _cal_utc_h < _cal_tp.get('session_london_end', 16)
                                        _cal_in_ny = _cal_tp.get('session_ny_start', 13) <= _cal_utc_h < _cal_tp.get('session_ny_end', 21)
                                        if not _cal_in_london and not _cal_in_ny:
                                            _cal_session_penalty = 10
                                            logger.info(f"Session awareness: calendar outside active sessions (UTC {_cal_utc_h}h), conf -10")

                                    # HTF bias: reduce confidence if going against H1 trend (don't block entirely)
                                    _cal_htf = None
                                    try:
                                        if smc:
                                            _cal_smc_st = smc.get_status()
                                            _cal_htf = _cal_smc_st.get('htf_bias', None)
                                    except Exception:
                                        _cal_htf = None

                                    for side in straddle_sides:
                                        direction = side['direction']
                                        conf = base_conf + cal_conf_bonus - _cal_session_penalty

                                        # HTF bias penalty: reduce confidence by 15 if against trend
                                        if _cal_htf and _cal_htf != 'neutral':
                                            if (direction == 'CALL' and _cal_htf == 'bearish') or (direction == 'PUT' and _cal_htf == 'bullish'):
                                                conf = max(10, conf - 15)
                                                logger.info(f"HTF penalty: calendar {direction} against {_cal_htf} bias, conf -15 → {conf}")

                                        # Adaptive SL/TP
                                        _trigger_for_sltp = 'calendar'
                                        adaptive = tech.compute_adaptive_sl_tp(direction, price, ms, profile, trigger_type=_trigger_for_sltp, sl_tp_advice=_learn_adj.get('sl_tp_advice') if _learn_adj else None)
                                        sl = adaptive['sl']
                                        tp = adaptive['tp']

                                        # Spread gate: skip if estimated spread > 50% of SL
                                        session_info = tech.get_session_info()
                                        est_spread = session_info['spread_est']
                                        if est_spread > adaptive['sl_pips'] * 0.50:
                                            logger.info(f"Spread gate: skipping calendar {direction}, spread {est_spread:.1f}p > 50% of SL {adaptive['sl_pips']:.1f}p")
                                            _cal_dbg('spread_gate', f"{evt_name} {direction} spread={est_spread:.1f}p SL={adaptive['sl_pips']:.1f}p", key=f"sp_{evt_key}_{direction}")
                                            continue

                                        # Adjust entry price for spread
                                        entry_px = price
                                        half_spread = est_spread / 2
                                        if direction == 'CALL':
                                            entry_px = price + half_spread * 0.0001
                                        else:
                                            entry_px = price - half_spread * 0.0001

                                        # Adaptive expiry: use 30 min or ATR-based, whichever is larger
                                        avg_range = ms.get('avg_range_pips', 5.0)
                                        candles_needed = adaptive['tp_pips'] / max(avg_range, 1.0)
                                        expiry_min = max(20, min(60, int(candles_needed * 5)))

                                        # Impact score: high impact events get higher base score
                                        cal_impact_score = 70 if evt_impact == 'High' else 50
                                        # Add momentum/trend bonuses
                                        mom = ms.get('momentum', '')
                                        if (direction == 'CALL' and mom == 'up') or (direction == 'PUT' and mom == 'down'):
                                            cal_impact_score += 8

                                        # Source conflict resolution with prior cycle signals
                                        for prior in cycle_signals:
                                            if prior['direction'] == direction:
                                                conf = min(95, conf + 10)
                                                logger.info(f"Source agreement: calendar {direction} agrees with {prior['source']}, conf +10 -> {conf}")
                                            else:
                                                if conf <= prior['confidence']:
                                                    conf = max(10, conf - 20)
                                                    logger.info(f"Source conflict: calendar {direction} vs {prior['source']} {prior['direction']}, conf -20 -> {conf}")

                                        news_title_cal = f"[CALENDARIO] Pre-{evt_name} ({evt_impact} Impact) - {side['label']}"
                                        prof_name = profile.get('name', 'default')

                                        # v3.40.4 — CALENDAR_MODE gate. Default 'shadow': loguea el
                                        # straddle (ambas patas) SIN operar. En shadow no se crea la
                                        # estrategia CALL, asi que la anti-contradiccion no bloquea la
                                        # PUT -> vemos el straddle completo (que en vivo esta roto).
                                        try:
                                            from src.common.config import Config as _CalCfg
                                            _cal_mode = getattr(_CalCfg, 'CALENDAR_MODE', 'shadow')
                                        except Exception:
                                            _cal_mode = 'shadow'
                                        if _cal_mode != 'active':
                                            if _cal_mode == 'shadow':
                                                try:
                                                    from src.common.db import log_calendar_shadow
                                                    log_calendar_shadow(evt_name, evt_impact, direction, entry_px, sl, tp, conf, int(minutes_until))
                                                    logger.info(f"[CALENDAR shadow] {direction} {evt_name} ({evt_impact}) @ {entry_px:.5f} conf={conf} SL={sl:.5f} TP={tp:.5f} — NO operado")
                                                except Exception as _cse:
                                                    logger.debug(f"calendar shadow log: {_cse}")
                                            continue

                                        # Dedup: skip if similar calendar strategy exists
                                        if has_recent_similar_strategy(direction, entry_px, 'calendar', 60):
                                            logger.info(f"Dedup: skipping {direction} calendar near {entry_px:.5f}")
                                            continue

                                        # Anti-contradiction: skip if active opposite strategy
                                        opposite = has_active_opposite_strategy(direction)
                                        if opposite:
                                            logger.info(f"Anti-contradiction: skipping {direction} calendar, active #{opposite[0]} {opposite[1]}")
                                            continue

                                        _cal_session_info = tech.get_session_info()
                                        _cal_session = _cal_session_info.get('session', '')
                                        conf = _apply_learning_adjustments(conf, 'calendar', _cal_session, direction=direction, htf_bias=_cal_htf, news_title=evt_name)

                                        # Min confidence gate: skip if below profile threshold after all adjustments
                                        if conf < base_conf:
                                            logger.info(f"Min confidence gate: skipping calendar {direction}, conf {conf} < profile min {base_conf}")
                                            _cal_dbg('minconf_gate', f"{evt_name} {direction} conf={conf}<{base_conf}", key=f"mc_{evt_key}_{direction}")
                                            continue

                                        # FAST PATH: create strategy + MT5 order FIRST, Gemma audits async
                                        _cal_entry_ctx = {
                                            'rsi': ms.get('rsi', 0),
                                            'rsi_zone': ms.get('rsi_zone', ''),
                                            'avg_range_pips': ms.get('avg_range_pips', 0),
                                            'volatility': ms.get('volatility', ''),
                                            'trend': ms.get('trend', ''),
                                            'trend_strength': ms.get('trend_strength', ''),
                                            'momentum': ms.get('momentum', ''),
                                            'htf_bias': _cal_htf or '',
                                            'setup_type': 'calendar',  # v3.48.0
                                        }
                                        sid = add_auto_strategy(
                                            alert_id=None,
                                            news_title=news_title_cal,
                                            direction=direction,
                                            entry_price=entry_px,
                                            stop_loss=sl,
                                            take_profit=tp,
                                            confidence=conf,
                                            impact_score=min(cal_impact_score, 100),
                                            trigger_type='calendar',
                                            candles_snapshot=cal_candles_snap,
                                            profile_name=prof_name,
                                            expiry_minutes=expiry_min,
                                            entry_context=_cal_entry_ctx)
                                        if sid:
                                            strategies_created += 1
                                            cycle_signals.append({'source': 'calendar', 'direction': direction, 'confidence': conf})
                                            logger.info(f"Calendar strategy #{sid}: {direction} @ {entry_px:.5f} SL={sl:.5f} TP={tp:.5f} | {evt_name} in {minutes_until:.0f}min (audit pending)")
                                            _try_mt5_execute(sid, direction, entry_px, sl, tp, conf)

                                            # Gemma 4 audit in background — veto closes position
                                            def _async_cal_audit(_sid=sid, _dir=direction, _px=entry_px, _conf=conf, _base=base_conf,
                                                                 _ms=ms, _adaptive=adaptive, _sess=_cal_session_info, _htf=_cal_htf):
                                                try:
                                                    _actx = build_signal_context(_dir, _px, _ms, _adaptive, _sess, _conf, setup_type='calendar', source='calendar', htf_bias=_htf)
                                                    _aud = audit_signal(_actx)
                                                    if _aud:
                                                        if _aud['agree']:
                                                            _nc = min(95, _conf + min(_aud['confidence_adjustment'], 10))
                                                            logger.info(f"Gemma audit CALENDAR #{_sid}: AGREE | adj={_aud['confidence_adjustment']:+d} -> conf={_nc} | {_aud['reasoning']}")
                                                            import sqlite3 as _sq
                                                            _cn = _sq.connect(DB_PATH); _cn.execute("UPDATE auto_strategies SET confidence = ? WHERE id = ? AND status = 'active' AND (mt5_status IS NULL OR mt5_status NOT IN ('closed', 'error'))", (_nc, _sid)); _cn.commit(); _cn.close()
                                                        else:
                                                            _nc = max(10, _conf + _aud['confidence_adjustment'])
                                                            logger.info(f"Gemma audit CALENDAR #{_sid}: DISAGREE | adj={_aud['confidence_adjustment']:+d} -> conf={_nc} | {_aud['reasoning']}")
                                                            # Don't close MT5 position — SL/TP handle risk.
                                                            import sqlite3 as _sq
                                                            _cn = _sq.connect(DB_PATH); _cn.execute("UPDATE auto_strategies SET confidence = ? WHERE id = ? AND status = 'active' AND (mt5_status IS NULL OR mt5_status NOT IN ('closed', 'error'))", (_nc, _sid)); _cn.commit(); _cn.close()
                                                            if _nc < _base:
                                                                logger.info(f"Gemma low-conf CALENDAR #{_sid}: conf {_nc} < {_base} — keeping open, SL/TP protect")
                                                    else:
                                                        logger.info(f"Gemma audit CALENDAR #{_sid}: no response — strategy stands")
                                                except Exception as _e:
                                                    logger.warning(f"Gemma async audit error for #{_sid}: {_e}")
                                            Thread(target=_async_cal_audit, daemon=True).start()

                                    # Mark this event as traded so we don't create duplicates next cycle
                                    _traded_calendar_events.add(evt_key)

                                except Exception as evt_err:
                                    logger.error(f"Calendar event processing error: {evt_err}")
                                    _cal_dbg('exception', f"{evt_err}", key=f"exc_{iteration}")
                                    continue
                        else:
                            logger.debug(f"[{iteration}] Calendar endpoint returned {cal_resp.status_code}")
                    except requests.exceptions.ConnectionError:
                        logger.debug(f"[{iteration}] Calendar endpoint not available")
                    except Exception as e:
                        logger.error(f"Calendar pre-news error: {e}", exc_info=True)

                    # v3.33.0 (Fase B) — Macro context disponible SIEMPRE para todos los tracks.
                    # Antes htf_bias y daily_ctx se computaban DENTRO del bloque M5 (if not skip_session
                    # and not skip_atr), lo que hacia que M15 y H1 los recibieran como None cuando M5
                    # estaba skipped. Hallazgo del Explore agent: el scanner M5 ya los pasa OK,
                    # pero M15/H1 leen del scope que puede no estar inicializado.
                    # Fix: calcular ambos ANTES del bloque y mantener en scope para todos los tracks.
                    htf_bias = None
                    daily_ctx = None
                    smc_status = None  # v3.40.3: init para evitar NameError 1er ciclo si SMC falla
                    try:
                        if smc:
                            smc.update()
                            smc_status = smc.get_status()
                            htf_bias = smc_status.get('htf_bias', None)
                    except Exception as _sue:
                        logger.debug(f"Macro context smc/htf_bias: {_sue}")
                    try:
                        daily_ctx = mtf.get_daily_context()
                    except Exception as _dce:
                        logger.debug(f"Macro context daily_ctx: {_dce}")

                    # ── Structure scanner: generate strategies from market structure alone ──
                    try:
                        from src.common.db import get_active_profile
                        profile = get_active_profile()
                        prof_name = profile.get('name', 'default')
                        min_conf = profile.get('min_confidence', 50)  # centralized default matching profile schema
                        logger.info(f"[{iteration}] Structure scan: profile='{prof_name}' min_conf={min_conf}")

                        # Session filter: skip if outside active sessions and tuner says to block
                        tuner_params = tuner.get_params()
                        skip_session = False
                        if tuner_params.get('block_outside_sessions', False):
                            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                            utc_hour = _dt.now(_tz.utc).hour
                            in_london = tuner_params['session_london_start'] <= utc_hour < tuner_params['session_london_end']
                            in_ny = tuner_params['session_ny_start'] <= utc_hour < tuner_params['session_ny_end']
                            if not in_london and not in_ny:
                                skip_session = True
                                logger.info(f"[{iteration}] AutoTuner: outside active sessions (UTC {utc_hour}h), skipping structure scan")

                        # v3.8.0 ATR ceiling: skip structure scan when volatility too high
                        # Empirical: 13 trades with ATR>6p had 0% net WR (-$29 collective).
                        # Extreme example: 30 Apr — 3 trades with ATR 6.9-7.8p all SL-hit
                        # despite correct directional analysis (SL inside normal candle noise).
                        skip_atr = False
                        try:
                            _ms_for_atr = tech.get_market_state()
                            _atr_now = _ms_for_atr.get('avg_range_pips', 0)
                            if _atr_now > 6.0:
                                skip_atr = True
                                logger.info(f"[{iteration}] ATR ceiling: ATR {_atr_now:.1f}p > 6.0p, skipping structure scan (volatility too high for tight SLs)")
                        except Exception as _atr_e:
                            logger.debug(f"ATR ceiling check: {_atr_e}")

                        if not skip_session and not skip_atr:
                            # v3.33.0: htf_bias y daily_ctx ya se calcularon ARRIBA (fuera del
                            # bloque condicional) para que M15/H1 los reciban siempre.
                            structure_signals = tech.detect_structure_signals(
                                min_confidence=min_conf, htf_bias=htf_bias, daily_context=daily_ctx)
                            _dc_info = f" day_pos={daily_ctx['today_pos']:.0%}" if daily_ctx and daily_ctx.get('today_pos') is not None else ''
                            logger.info(f"[{iteration}] Structure signals: {len(structure_signals)} (htf_bias={htf_bias}{_dc_info})")

                            # AutoTuner: block setup types with poor win rates
                            before_block = len(structure_signals)
                            structure_signals = [s for s in structure_signals
                                                 if not tuner.is_setup_blocked(s.get('setup_type', ''))]
                            tuner_blocked = before_block - len(structure_signals)
                            if tuner_blocked > 0:
                                logger.info(f"[{iteration}] AutoTuner blocked {tuner_blocked} low-WR setup(s)")

                            prof_sl = profile.get('stop_loss_pips', 5)
                            prof_tp = profile.get('take_profit_pips', 10)

                            # Consensus: pick SINGLE direction with strongest total confidence
                            call_sigs = [s for s in structure_signals if s['direction'] == 'CALL']
                            put_sigs = [s for s in structure_signals if s['direction'] == 'PUT']
                            call_score = sum(s['confidence'] for s in call_sigs)
                            put_score = sum(s['confidence'] for s in put_sigs)

                            if call_score > 0 and put_score > 0:
                                ratio = max(call_score, put_score) / min(call_score, put_score)
                                if ratio < 1.30:
                                    logger.info(f"[{iteration}] Structure: conflicting signals (CALL={call_score:.0f} vs PUT={put_score:.0f}, ratio={ratio:.2f} < 1.30), skipping")
                                    structure_signals = []
                                elif call_score > put_score:
                                    structure_signals = [max(call_sigs, key=lambda s: s['confidence'])]
                                else:
                                    structure_signals = [max(put_sigs, key=lambda s: s['confidence'])]
                            elif call_sigs:
                                structure_signals = [max(call_sigs, key=lambda s: s['confidence'])]
                            elif put_sigs:
                                structure_signals = [max(put_sigs, key=lambda s: s['confidence'])]

                            # Capture candles snapshot for frozen chart display (MT5 priority)
                            candles_snap = _fetch_candles_snapshot(30)

                            for sig in structure_signals:
                                direction = sig['direction']
                                conf = sig['confidence']
                                ms = tech.get_market_state()
                                price = ms.get('price', 0)
                                if price <= 0:
                                    break

                                # Use MT5 live tick as entry price (most accurate, zero lag)
                                if mt5_exec and mt5_exec.is_ready() and mt5_exec._mt5:
                                    try:
                                        _tick = mt5_exec._mt5.symbol_info_tick("EURUSD")
                                        if _tick:
                                            _mt5_price = _tick.ask if direction == 'CALL' else _tick.bid
                                            if _mt5_price > 0:
                                                logger.info(f"Structure entry: MT5 tick {_mt5_price:.5f} vs market_state {price:.5f} (delta {abs(_mt5_price-price)/0.0001:.1f}p)")
                                                price = _mt5_price
                                    except Exception:
                                        pass  # fallback to market_state price

                                # Note: key_level override removed — it was locking in worse entries.
                                # The MT5 tick price fetched above is the real market price.
                                # key_level still influences confidence via detect_structure_signals.

                                # Adaptive SL/TP based on ATR + structure levels
                                _trigger_for_sltp = 'structure'
                                adaptive = tech.compute_adaptive_sl_tp(direction, price, ms, profile, trigger_type=_trigger_for_sltp, sl_tp_advice=_learn_adj.get('sl_tp_advice') if _learn_adj else None)
                                sl = adaptive['sl']
                                tp = adaptive['tp']

                                # Spread gate: skip if estimated spread > 50% of SL
                                session_info = tech.get_session_info()
                                est_spread = session_info['spread_est']
                                if est_spread > adaptive['sl_pips'] * 0.50:
                                    logger.info(f"Spread gate: skipping structure strategy, spread {est_spread:.1f}p > 50% of SL {adaptive['sl_pips']:.1f}p")
                                    continue
                                # Adjust entry price for spread
                                half_spread = est_spread / 2
                                if direction == 'CALL':
                                    price = price + half_spread * 0.0001
                                else:
                                    price = price - half_spread * 0.0001
                                # Spread awareness: penalize confidence if spread is moderate
                                spread_ratio = est_spread / max(adaptive['sl_pips'], 1)
                                if spread_ratio > 0.15:
                                    spread_penalty = int((spread_ratio - 0.10) * 30)  # ~1-5 points
                                    conf = max(20, conf - spread_penalty)
                                    logger.info(f"Spread penalty: {est_spread:.1f}p = {spread_ratio:.0%} of SL, conf -{spread_penalty} → {conf}")

                                # Impact score: history-based when available, else dynamic
                                struct_score = 40
                                try:
                                    from src.common.db import get_setup_win_rates
                                    wr_data = get_setup_win_rates().get(sig.get('setup_type', ''), {})
                                    if wr_data.get('total', 0) >= 3:
                                        struct_score = int(30 + wr_data['win_rate'] * 0.7)
                                    else:
                                        struct_score += int(conf * 0.3)
                                except Exception:
                                    struct_score += int(conf * 0.3)
                                # HTF alignment bonus
                                if htf_bias and ((direction == 'CALL' and htf_bias == 'bullish') or
                                                  (direction == 'PUT' and htf_bias == 'bearish')):
                                    struct_score += 15
                                # Trend strength bonus
                                ts = ms.get('trend_strength', 'weak')
                                if ts == 'strong': struct_score += 10
                                elif ts == 'moderate': struct_score += 5
                                # Momentum alignment
                                mom = ms.get('momentum', '')
                                if (direction == 'CALL' and mom == 'up') or (direction == 'PUT' and mom == 'down'):
                                    struct_score += 8

                                # Adaptive expiry: time needed for TP based on current ATR
                                avg_range = ms.get('avg_range_pips', 5.0)
                                candles_needed = adaptive['tp_pips'] / max(avg_range, 1.0)
                                expiry_min = max(15, min(60, int(candles_needed * 5)))

                                # Source conflict resolution: adjust conf based on agreement/conflict with prior signals
                                for prior in cycle_signals:
                                    if prior['direction'] == direction:
                                        conf = min(95, conf + 10)
                                        logger.info(f"Source agreement: structure {direction} agrees with {prior['source']}, conf +10 → {conf}")
                                    else:
                                        if conf <= prior['confidence']:
                                            conf = max(10, conf - 20)
                                            logger.info(f"Source conflict: structure {direction} vs {prior['source']} {prior['direction']}, conf -20 → {conf}")

                                # Dedup: skip if a similar strategy was created recently
                                if has_recent_similar_strategy(direction, price, 'structure', 30):
                                    logger.info(f"Dedup: skipping {direction} structure near {price:.5f}, similar exists within 30min")
                                    continue

                                # Anti-contradiction: skip if there's an active strategy in the opposite direction
                                opposite = has_active_opposite_strategy(direction)
                                if opposite:
                                    logger.info(f"Anti-contradiction: skipping {direction} structure, active #{opposite[0]} {opposite[1]} (conf={opposite[2]})")
                                    continue

                                _struct_session_info = tech.get_session_info()
                                _struct_session = _struct_session_info.get('session', '')
                                conf = _apply_learning_adjustments(conf, 'structure', _struct_session, direction=direction, htf_bias=htf_bias)

                                # v3.9.0 FULLY-ALIGNED FILTER (SIM A):
                                # Block structure trades where direction + HTF + M5 trend ALL align.
                                # Empirical evidence (50 historical aligned trades):
                                #   28% WR, -$82.30 PnL, avg pips -1.6
                                # vs counter-trend structure (HTF or M5 mismatch with direction):
                                #   57% WR, +$5.60 PnL
                                # The "perfect alignment" setup is exhaustion entry on EUR/USD M5
                                # (mean-reverting timeframe). News trades are exempt from this filter
                                # because news catalysts can drive aligned moves successfully.
                                _ms_trend = ms.get('trend', 'unknown')
                                _regime = ms.get('regime', 'uncertain')
                                _is_fully_aligned = (
                                    (direction == 'CALL' and htf_bias == 'bullish' and _ms_trend == 'bullish') or
                                    (direction == 'PUT' and htf_bias == 'bearish' and _ms_trend == 'bearish')
                                )
                                _is_counter_htf = (
                                    (direction == 'CALL' and htf_bias == 'bearish') or
                                    (direction == 'PUT' and htf_bias == 'bullish')
                                )
                                _setup_type_str = sig.get('setup_type', '')
                                _is_reversal_setup = any(t in _setup_type_str for t in ('reversal', 'rejection', 'bounce', 'rebote', 'rechazo'))

                                # === v3.10.0 REGIME-AWARE FILTERS (CORRECTED via empirical data) ===
                                # Counter-intuitive finding from 53-trade trending sample:
                                #   aligned in trending:    23 trades | 17% WR | -$58.90  ← WORST
                                #   M5-only counter-HTF:    14 trades | 50% WR | -$8.30   ← actually best!
                                #   HTF-only counter-M5:    13 trades | 46% WR | -$11.11
                                #   counter-both (HTF+M5):   3 trades |  0% WR | -$16.90
                                # Conclusion: EUR/USD M5 is mean-reverting EVEN INSIDE trends. Aligned
                                # trades are exhaustion entries regardless of regime. Counter-trend trades
                                # are bouncing off short-term overextension (the mean reversion).
                                # New logic: ALWAYS block fully-aligned + ALWAYS block counter-both.
                                # M5-only and HTF-only pass.
                                _is_counter_both = (
                                    (direction == 'CALL' and htf_bias == 'bearish' and _ms_trend == 'bearish') or
                                    (direction == 'PUT' and htf_bias == 'bullish' and _ms_trend == 'bullish')
                                )
                                if _is_fully_aligned:
                                    logger.info(f"SIM A: skipping structure {direction} fully-aligned (htf={htf_bias} m5={_ms_trend} regime={_regime}). 17-29% WR historically.")
                                    continue
                                if _is_counter_both:
                                    logger.info(f"Counter-both filter: skipping structure {direction} (htf={htf_bias} m5={_ms_trend} both against direction). 0% WR historically.")
                                    continue
                                # M5-only or HTF-only setups pass — those are the empirically-profitable bucket

                                # v3.9.1 Warmup gate: skip first 10 min after analyzer startup
                                _warmup_elapsed = time.time() - _analyzer_warmup_start
                                if _warmup_elapsed < WARMUP_SECONDS:
                                    logger.info(f"Warmup gate: skipping structure {direction}, analyzer running {_warmup_elapsed:.0f}s < {WARMUP_SECONDS}s warmup")
                                    continue

                                # === v3.11.0 DATA-DRIVEN FILTERS ===
                                # ATR floor: skip when volatility too low (deadzone — comm eats wins).
                                # Empirical: 15 trades with ATR<2.5 had 13% WR, -$22.81.
                                # v3.35.3 — Floor bajado 2.5 → 2.0p. Semana 26 May: mercado quieto
                                # (ATR 1.8-2.3p casi todo el dia) dejaba a AIdan sin operar. ML predictor
                                # (v3.35.0) actua como red de seguridad contra trades de baja calidad.
                                _atr_now = ms.get('avg_range_pips', 0)
                                if _atr_now < 2.0:
                                    logger.info(f"ATR floor: skipping structure {direction}, ATR {_atr_now:.1f}p < 2.0p (deadzone)")
                                    continue
                                # v3.17.0 — REMOVED hour gate (UTC 12/14/20).
                                # Data original era cross-version (v3.7-v3.11) con cambios
                                # simultaneos. Contaminada, no representa v3.16.x.
                                # Conf ceiling: block conf >= 80 (anti-predictive zone).
                                # Empirical: bucket 80-89 (-$20) and 90+ (-$21) are net losers.
                                if conf >= 80:
                                    logger.info(f"Conf ceiling: blocking structure {direction}, conf {conf} >= 80 (anti-predictive zone, historically losers)")
                                    continue

                                # Min confidence gate: skip if below profile threshold after all adjustments
                                if conf < min_conf:
                                    logger.info(f"Min confidence gate: skipping structure {direction}, conf {conf} < profile min {min_conf}")
                                    continue

                                # FAST PATH: create strategy + MT5 order FIRST, audit async
                                _struct_entry_ctx = {
                                    'rsi': ms.get('rsi', 0),
                                    'rsi_zone': ms.get('rsi_zone', ''),
                                    'avg_range_pips': ms.get('avg_range_pips', 0),
                                    'volatility': ms.get('volatility', ''),
                                    'trend': ms.get('trend', ''),
                                    'trend_strength': ms.get('trend_strength', ''),
                                    'momentum': ms.get('momentum', ''),
                                    'htf_bias': htf_bias or '',
                                    'setup_type': sig.get('setup_type', ''),  # v3.48.0
                                }
                                sid = add_auto_strategy(
                                    alert_id=None,
                                    news_title=f"[ESTRUCTURA] {sig['reason'][:80]}",
                                    direction=direction, entry_price=price,
                                    stop_loss=sl, take_profit=tp,
                                    confidence=conf, impact_score=min(struct_score, 100),
                                    trigger_type='structure',
                                    candles_snapshot=candles_snap,
                                    profile_name=prof_name,
                                    expiry_minutes=expiry_min,
                                    entry_context=_struct_entry_ctx)
                                if sid:
                                    strategies_created += 1
                                    cycle_signals.append({'source': 'structure', 'direction': direction, 'confidence': conf})
                                    # v3.40.20 — tag calidad de nivel (plan B) EN EL MOMENTO; join por sid a trade_archive
                                    try:
                                        from src.common.db import log_level_quality
                                        log_level_quality(sid, sig.get('setup_type', 'structure'), direction,
                                                          sig.get('key_level'), sig.get('level_touches', 0), conf)
                                    except Exception:
                                        pass
                                    logger.info(f"Structure strategy #{sid}: {direction} @ {price:.5f} | {sig['setup_type']} | {sig['reason'][:60]} (audit pending)")
                                    _try_mt5_execute(sid, direction, price, sl, tp, conf)

                                    # Gemma 4 audit in background — adjust confidence post-hoc
                                    def _async_struct_audit(_sid=sid, _dir=direction, _price=price, _conf=conf, _base=min_conf,
                                                            _ms=ms, _adaptive=adaptive, _sess_info=_struct_session_info,
                                                            _setup=sig.get('setup_type', 'structure'), _htf=htf_bias,
                                                            _key=sig.get('key_level', 'none')):
                                        try:
                                            _actx = build_signal_context(_dir, _price, _ms, _adaptive, _sess_info, _conf,
                                                                         setup_type=_setup, source='structure', htf_bias=_htf, key_level=_key)
                                            _aud = audit_signal(_actx)
                                            if _aud:
                                                if _aud['agree']:
                                                    _new_conf = min(95, _conf + min(_aud['confidence_adjustment'], 10))
                                                    logger.info(f"Gemma audit STRUCTURE #{_sid}: AGREE | adj={_aud['confidence_adjustment']:+d} -> conf={_new_conf} | {_aud['reasoning']}")
                                                else:
                                                    _new_conf = max(10, _conf + _aud['confidence_adjustment'])
                                                    logger.info(f"Gemma audit STRUCTURE #{_sid}: DISAGREE | adj={_aud['confidence_adjustment']:+d} -> conf={_new_conf} | {_aud['reasoning']}")
                                                import sqlite3 as _sq
                                                _cn = _sq.connect(DB_PATH)
                                                _cn.execute("UPDATE auto_strategies SET confidence = ? WHERE id = ? AND status = 'active' AND (mt5_status IS NULL OR mt5_status NOT IN ('closed', 'error'))", (_new_conf, _sid))
                                                _cn.commit(); _cn.close()
                                            else:
                                                logger.info(f"Gemma audit STRUCTURE #{_sid}: no response — strategy stands")
                                        except Exception as _e:
                                            logger.warning(f"Gemma async audit error for #{_sid}: {_e}")
                                    Thread(target=_async_struct_audit, daemon=True).start()
                    except Exception as e:
                        logger.error(f"Structure scanner error: {e}", exc_info=True)

                    # ── SMC Scanner: multi-timeframe + demand/supply zones + confirmation ──
                    # Note: smc.update() already called above before structure scanner.
                    # Skip re-update here to avoid double MT5 fetch in same cycle.
                    try:
                        smc_setups = smc.check_confirmations()
                        logger.info(f"[{iteration}] SMC setups: {len(smc_setups)}")
                        # AutoTuner: block SMC setup types with poor win rates
                        _smc_before = len(smc_setups)
                        smc_setups = [s for s in smc_setups
                                      if not tuner.is_setup_blocked(s.get('setup_type', 'smc'))]
                        _smc_blocked = _smc_before - len(smc_setups)
                        if _smc_blocked > 0:
                            logger.info(f"[{iteration}] AutoTuner blocked {_smc_blocked} SMC setup(s)")

                        # Market hours check for SMC: skip all if outside active sessions
                        _smc_tp = tuner.get_params()
                        _smc_skip_session = False
                        if _smc_tp.get('block_outside_sessions', False):
                            from datetime import datetime as _sdt, timezone as _stz
                            _s_utc_h = _sdt.now(_stz.utc).hour
                            _s_london = _smc_tp.get('session_london_start', 7) <= _s_utc_h < _smc_tp.get('session_london_end', 16)
                            _s_ny = _smc_tp.get('session_ny_start', 13) <= _s_utc_h < _smc_tp.get('session_ny_end', 21)
                            if not _s_london and not _s_ny:
                                _smc_skip_session = True
                                logger.info(f"[{iteration}] Session filter: skipping SMC scan, outside active sessions (UTC {_s_utc_h}h)")

                        for setup in smc_setups:
                            if _smc_skip_session:
                                break
                            direction = setup['direction']
                            conf = setup['confidence']
                            # v3.40.17: reversal-en-zona (bias HTF flipeado) — hasta ahora estaba
                            # MUERTO por un bug de clave (el gate leia 'htf_bias' inexistente -> caia
                            # al bias original -> el filtro HTF lo bloqueaba siempre). Arreglado el
                            # alias, ahora pasaria a operar. Lo dejamos APAGADO explicitamente (vivo
                            # idéntico) hasta medirlo: es contra-tendencia, sin evidencia aun.
                            if setup.get('reversal'):
                                logger.info(f"SMC reversal {direction} detectado (bias debil, zona opuesta) — DESACTIVADO pendiente de medicion")
                                continue
                            ms = tech.get_market_state()
                            price = ms.get('price', 0)
                            if price <= 0:
                                break

                            # Confidence minimum check: skip if below profile minimum
                            # v3.50.4 — BUG: esto leia `prof_min_conf`, que se asigna en la
                            # rama de NOTICIAS (~l.1620, dentro de `if result and
                            # direction != NEUTRAL`). En los ciclos sin noticia analizada la
                            # variable no existe => UnboundLocalError justo aca => el
                            # scanner de SMC moria EN EL MOMENTO en que encontraba un setup
                            # (visto en vivo el 5-ago: los 2 setups del dia se perdieron
                            # asi). Es la misma clase de bug que mato a M15 en v3.33.0:
                            # variable de otro scope + excepcion atrapada = subsistema
                            # muerto en silencio. Ahora se resuelve local y autosuficiente.
                            _smc_min_conf = 60
                            try:
                                from src.common.db import get_active_profile as _gap
                                _smc_min_conf = (_gap() or {}).get('min_confidence', 60)
                            except Exception as _mce:
                                logger.debug(f"SMC min_conf fallback 60: {_mce}")
                            if conf < _smc_min_conf:
                                logger.info(f"Min confidence: skipping SMC {direction}, conf {conf} < profile min {_smc_min_conf}")
                                continue

                            # Adaptive SL/TP
                            _trigger_for_sltp = 'smc'
                            adaptive = tech.compute_adaptive_sl_tp(direction, price, ms, profile, trigger_type=_trigger_for_sltp, sl_tp_advice=_learn_adj.get('sl_tp_advice') if _learn_adj else None)
                            sl = adaptive['sl']
                            tp = adaptive['tp']

                            # Spread gate: skip if estimated spread > 50% of SL
                            session_info = tech.get_session_info()
                            est_spread = session_info['spread_est']
                            if est_spread > adaptive['sl_pips'] * 0.50:
                                logger.info(f"Spread gate: skipping SMC strategy, spread {est_spread:.1f}p > 50% of SL {adaptive['sl_pips']:.1f}p")
                                continue
                            # Adjust entry price for spread
                            half_spread = est_spread / 2
                            if direction == 'CALL':
                                price = price + half_spread * 0.0001
                            else:
                                price = price - half_spread * 0.0001

                            # Adaptive expiry
                            avg_range = ms.get('avg_range_pips', 5.0)
                            candles_needed = adaptive['tp_pips'] / max(avg_range, 1.0)
                            expiry_min = max(15, min(60, int(candles_needed * 5)))

                            # Impact score: history-based when available, else confidence
                            smc_impact = int(conf)
                            try:
                                from src.common.db import get_setup_win_rates
                                smc_wr = get_setup_win_rates().get(setup.get('setup_type', 'smc'), {})
                                if smc_wr.get('total', 0) >= 3:
                                    smc_impact = int(30 + smc_wr['win_rate'] * 0.7)
                            except Exception as e:
                                logger.debug(f"SMC win rate lookup: {e}")

                            # Source conflict resolution: adjust conf based on agreement/conflict with prior signals
                            for prior in cycle_signals:
                                if prior['direction'] == direction:
                                    conf = min(95, conf + 10)
                                    logger.info(f"Source agreement: SMC {direction} agrees with {prior['source']}, conf +10 → {conf}")
                                else:
                                    if conf <= prior['confidence']:
                                        conf = max(10, conf - 20)
                                        logger.info(f"Source conflict: SMC {direction} vs {prior['source']} {prior['direction']}, conf -20 → {conf}")

                            # HTF bias filter: block SMC signals against H1 trend
                            try:
                                smc_htf = setup.get('htf_bias') or (smc_status.get('htf_bias') if smc_status else None)
                                if smc_htf and smc_htf != 'neutral':
                                    if (direction == 'CALL' and smc_htf == 'bearish') or (direction == 'PUT' and smc_htf == 'bullish'):
                                        logger.info(f"HTF filter: blocking SMC {direction} — H1 bias is {smc_htf}")
                                        continue
                            except Exception as e:
                                logger.debug(f"SMC HTF filter: {e}")

                            # Dedup: skip if similar SMC strategy exists
                            if has_recent_similar_strategy(direction, price, 'smc', 30):
                                logger.info(f"Dedup: skipping {direction} SMC near {price:.5f}")
                                continue

                            # Anti-contradiction: skip if active opposite strategy
                            opposite = has_active_opposite_strategy(direction)
                            if opposite:
                                logger.info(f"Anti-contradiction: skipping {direction} SMC, active #{opposite[0]} {opposite[1]}")
                                continue

                            # === v3.10.0 SMC ALIGNMENT FILTER (corrected via empirical data) ===
                            # Same logic as structure: block fully-aligned and counter-both.
                            # M5-only and HTF-only setups pass.
                            _smc_regime = ms.get('regime', 'uncertain')
                            _smc_htf_for_filter = setup.get('htf_bias') or (smc_status.get('htf_bias') if 'smc_status' in dir() and smc_status else None) or 'neutral'
                            _smc_m5_trend = ms.get('trend', 'unknown')
                            _smc_aligned = (
                                (direction == 'CALL' and _smc_htf_for_filter == 'bullish' and _smc_m5_trend == 'bullish') or
                                (direction == 'PUT' and _smc_htf_for_filter == 'bearish' and _smc_m5_trend == 'bearish')
                            )
                            _smc_counter_both = (
                                (direction == 'CALL' and _smc_htf_for_filter == 'bearish' and _smc_m5_trend == 'bearish') or
                                (direction == 'PUT' and _smc_htf_for_filter == 'bullish' and _smc_m5_trend == 'bullish')
                            )
                            if _smc_aligned:
                                logger.info(f"SIM A SMC: skipping {direction} fully-aligned (htf={_smc_htf_for_filter} m5={_smc_m5_trend}).")
                                continue
                            if _smc_counter_both:
                                logger.info(f"Counter-both SMC: skipping {direction} (htf={_smc_htf_for_filter} m5={_smc_m5_trend}).")
                                continue

                            # v3.9.1 Warmup gate: skip first 10 min after analyzer startup
                            _warmup_elapsed = time.time() - _analyzer_warmup_start
                            if _warmup_elapsed < WARMUP_SECONDS:
                                logger.info(f"Warmup gate: skipping SMC {direction}, analyzer running {_warmup_elapsed:.0f}s < {WARMUP_SECONDS}s warmup")
                                continue

                            # === v3.11.0 DATA-DRIVEN FILTERS (SMC) ===
                            # v3.35.3 — Floor bajado 2.5 → 2.0p (ver nota en structure flow).
                            _smc_atr = ms.get('avg_range_pips', 0)
                            if _smc_atr < 2.0:
                                logger.info(f"ATR floor: skipping SMC {direction}, ATR {_smc_atr:.1f}p < 2.0p (deadzone)")
                                continue
                            # v3.17.0 — REMOVED hour gate (UTC 12/14/20). Data contaminada cross-version.
                            # Conf ceiling check happens later, after audit may inflate conf

                            smc_snap = _fetch_candles_snapshot(30)
                            _smc_session_info = tech.get_session_info()
                            _smc_session = _smc_session_info.get('session', '')
                            _smc_htf_val = setup.get('htf_bias') or (smc_status.get('htf_bias') if 'smc_status' in dir() and smc_status else None)
                            conf = _apply_learning_adjustments(conf, 'smc', _smc_session, direction=direction, htf_bias=_smc_htf_val)

                            # Gemma 4 audit
                            _audit_ctx = build_signal_context(
                                direction, price, ms, adaptive, _smc_session_info,
                                conf, setup_type=setup.get('setup_type', 'smc'),
                                source='smc', htf_bias=_smc_htf_val,
                                key_level=setup.get('key_level', 'none'))
                            _audit = audit_signal(_audit_ctx)
                            if _audit:
                                if _audit['agree']:
                                    conf = min(95, conf + min(_audit['confidence_adjustment'], 10))
                                    logger.info(f"Gemma audit SMC: AGREE | adj={_audit['confidence_adjustment']:+d} -> conf={conf} | {_audit['reasoning']}")
                                else:
                                    conf = max(10, conf + _audit['confidence_adjustment'])
                                    logger.info(f"Gemma audit SMC: DISAGREE | adj={_audit['confidence_adjustment']:+d} -> conf={conf} | {_audit['reasoning']}")
                                    if conf < min_conf:
                                        logger.info(f"Gemma vetoed SMC signal: conf {conf} < {min_conf}")
                                        continue

                            # v3.11.0 Conf ceiling for SMC (post-audit)
                            if conf >= 80:
                                logger.info(f"Conf ceiling: blocking SMC {direction}, conf {conf} >= 80 (anti-predictive)")
                                continue

                            _smc_htf_for_ctx = setup.get('htf_bias') or (smc_status.get('htf_bias') if 'smc_status' in dir() and smc_status else None) or ''
                            _smc_entry_ctx = {
                                'rsi': ms.get('rsi', 0),
                                'rsi_zone': ms.get('rsi_zone', ''),
                                'avg_range_pips': ms.get('avg_range_pips', 0),
                                'volatility': ms.get('volatility', ''),
                                'trend': ms.get('trend', ''),
                                'trend_strength': ms.get('trend_strength', ''),
                                'momentum': ms.get('momentum', ''),
                                'htf_bias': _smc_htf_for_ctx,
                                # v3.48.0 — smc no emite setup_type; el tipo de zona (demand/supply)
                                # ES la hipotesis del setup, asi que sirve de grano.
                                'setup_type': f"smc_{(setup.get('zone') or {}).get('type') or 'zone'}",
                            }
                            sid = add_auto_strategy(
                                alert_id=None,
                                news_title=f"[SMC] {setup['reason'][:80]}",
                                direction=direction, entry_price=price,
                                stop_loss=sl, take_profit=tp,
                                confidence=conf, impact_score=smc_impact,
                                trigger_type='smc',
                                candles_snapshot=smc_snap,
                                expiry_minutes=expiry_min,
                                entry_context=_smc_entry_ctx)
                            if sid:
                                strategies_created += 1
                                cycle_signals.append({'source': 'smc', 'direction': direction, 'confidence': conf})
                                logger.info(f"SMC strategy #{sid}: {direction} @ {price:.5f} | {setup['reason'][:60]}")
                                _try_mt5_execute(sid, direction, price, sl, tp, conf)
                    except Exception as e:
                        logger.error(f"SMC scanner error: {e}", exc_info=True)

                    if strategies_created > 0:
                        logger.info(f"[{iteration}] Total strategies created this cycle: {strategies_created}")

                    # ── Mark expired strategies + auto-evaluate ──
                    try:
                        # Expire active strategies past their expiry time
                        try:
                            import sqlite3 as _sq3
                            _conn = _sq3.connect(DB_PATH)
                            # First: find strategies about to expire that still have pending MT5 orders — cancel them
                            try:
                                _cur_exp = _conn.execute("""
                                    SELECT id, mt5_ticket FROM auto_strategies
                                    WHERE expires_at < ? AND status = 'active'
                                      AND mt5_ticket IS NOT NULL AND mt5_status = 'pending'
                                """, (now_ar(),))
                                _expiring_pending = _cur_exp.fetchall()
                            except Exception:
                                _expiring_pending = []
                            # Cancel each pending order on MT5 before marking expired
                            if _expiring_pending and mt5_exec and mt5_exec.is_ready():
                                for _exp_sid, _exp_ticket in _expiring_pending:
                                    try:
                                        _mt5 = mt5_exec._mt5
                                        _req = {
                                            "action": _mt5.TRADE_ACTION_REMOVE,
                                            "order": int(_exp_ticket),
                                        }
                                        _r = _mt5.order_send(_req)
                                        if _r and _r.retcode == _mt5.TRADE_RETCODE_DONE:
                                            logger.info(f"Cancelled expired pending limit order #{_exp_ticket} (strategy #{_exp_sid})")
                                        else:
                                            logger.warning(f"Cancel expired pending #{_exp_ticket} retcode={getattr(_r, 'retcode', 'n/a')}")
                                    except Exception as _ce:
                                        logger.debug(f"Cancel expired pending #{_exp_ticket}: {_ce}")
                            _conn.execute("""
                                UPDATE auto_strategies SET status = 'expired'
                                WHERE expires_at < ? AND status = 'active'
                            """, (now_ar(),))
                            _conn.commit()
                            _conn.close()
                        except Exception as e:
                            logger.debug(f"Expire old strategies: {e}")
                        pending = get_strategies_pending_evaluation()
                        if pending:
                            candles = tech._fetch_candles()
                            current_price = tech.get_market_state().get('price', 0)

                            for row in pending:
                                sid, direction, entry_price, sl, tp = row[0], row[1], row[2], row[3], row[4]
                                conf, expiry_min = row[5], row[6]
                                created_at_str, expires_at_str = row[7], row[8]
                                news_title, trigger_type = row[9], row[10]
                                be_triggered = bool(row[11]) if len(row) > 11 and row[11] else False

                                if not current_price or not entry_price:
                                    continue

                                # Check if TP or SL was hit using candle history (3-step trailing SL)
                                hit_tp = False
                                hit_sl = False
                                hit_be = False
                                # SL/TP fijos — trailing desactivado. Solo trackea HWM.
                                tp_distance = abs(tp - entry_price)
                                trailing_step = 0
                                effective_sl = sl
                                _high_water = 0

                                if candles and tp_distance > 0.00005:
                                    from datetime import datetime as dt
                                    try:
                                        entry_ts = dt.strptime(str(created_at_str).split('.')[0], '%Y-%m-%d %H:%M:%S')
                                    except Exception:
                                        entry_ts = None

                                    if entry_ts:
                                        for c in candles:
                                            c_ts = c.get('datetime', c.get('timestamp', 0))
                                            try:
                                                if isinstance(c_ts, (int, float)):
                                                    from datetime import timezone as tz_mod, timedelta as td_mod
                                                    c_time = dt.fromtimestamp(c_ts, tz=tz_mod(td_mod(hours=-3))).replace(tzinfo=None)
                                                else:
                                                    c_time = dt.strptime(str(c_ts).split('.')[0], '%Y-%m-%d %H:%M:%S')
                                            except Exception:
                                                continue

                                            if c_time < entry_ts:
                                                continue

                                            if direction == 'CALL':
                                                progress = c['high'] - entry_price
                                            else:
                                                progress = entry_price - c['low']
                                            _high_water = max(_high_water, progress)

                                            # Check TP/SL hits
                                            if direction == 'CALL':
                                                if c['high'] >= tp:
                                                    hit_tp = True
                                                    break
                                                if c['low'] <= effective_sl:
                                                    if trailing_step > 0:
                                                        hit_be = True
                                                    else:
                                                        hit_sl = True
                                                    break
                                            else:  # PUT
                                                if c['low'] <= tp:
                                                    hit_tp = True
                                                    break
                                                if c['high'] >= effective_sl:
                                                    if trailing_step > 0:
                                                        hit_be = True
                                                    else:
                                                        hit_sl = True
                                                    break

                                # Persist be_triggered flag to DB if detected during candle analysis
                                if be_triggered:
                                    try:
                                        from src.common.db import mark_be_triggered
                                        mark_be_triggered(sid)
                                    except Exception as e:
                                        logger.debug(f"mark_be_triggered eval: {e}")

                                # Determine result (accounting for estimated spread)
                                pip = 0.0001
                                try:
                                    from src.analyzer.technical import TechnicalAnalyzer
                                    est_spread = TechnicalAnalyzer.get_session_info()['spread_est']
                                except Exception:
                                    est_spread = 1.0

                                if hit_tp:
                                    result = 'win'
                                    pips_result = abs(tp - entry_price) / pip - est_spread
                                elif hit_be or be_triggered:
                                    # BE flag: trailing SL reached BE — evaluate as break_even
                                    if direction == 'CALL':
                                        spread_loss = (current_price - entry_price) / pip
                                    else:
                                        spread_loss = (entry_price - current_price) / pip
                                    result = 'break_even'
                                    pips_result = round(spread_loss, 1)
                                    logger.info(f"Strategy #{sid} BE flag: spread cost {pips_result:+.1f}p -> evaluated as BREAK_EVEN")
                                elif hit_sl:
                                    result = 'loss'
                                    pips_result = -(abs(sl - entry_price) / pip + est_spread)
                                else:
                                    # Neither TP nor SL hit — evaluate by direction
                                    if direction == 'CALL':
                                        pips_result = (current_price - entry_price) / pip - est_spread
                                    else:
                                        pips_result = (entry_price - current_price) / pip - est_spread
                                    min_pips = tuner.get_params().get('min_pips_for_win', 1.5)
                                    result = 'win' if pips_result >= min_pips else 'loss'

                                exit_px = tp if hit_tp else (entry_price if hit_be else (sl if hit_sl else current_price))

                                # Extract setup_type from news_title for learning
                                _setup_type = ''
                                _title_lower = (news_title or '').lower()
                                for _st in ['breakout', 'breakdown', 'bb_rejection', 'reversal', 'momentum', 'crossover', 'continuation', 'rebote', 'rechazo', 'soporte', 'resistencia']:
                                    if _st in _title_lower:
                                        _setup_type = _st
                                        break
                                ctx = {
                                    'entry_price': entry_price,
                                    'direction': direction,
                                    'confidence': conf,
                                    'setup_type': _setup_type,
                                    'trigger_type': trigger_type or '',
                                    'market_trend': tech.get_market_state().get('trend', ''),
                                    'rsi_at_entry': tech.get_market_state().get('rsi', 0),
                                }
                                # v3.9.0 EXPIRY FIX (CRITICAL):
                                # Old behavior: force-close ALL filled positions on expiry, even if not at TP/SL.
                                # This was the WIN AMPUTATION BUG — wins captured only 43% of TP nominal because
                                # the 15-minute expiry timer killed trades before they could reach TP.
                                # New behavior: only force-close if SL/TP was actually hit (per candle analysis).
                                # If neither hit, let MT5 keep the position open with its fixed SL/TP.
                                # The strategy is marked 'expired' for tracking but the position stays alive.
                                # SL is still protecting against runaway losses; TP can finally trigger.
                                mt5_closed_price = None
                                should_force_close = hit_tp or hit_sl or hit_be
                                # v3.36.0 — En modo Position Manager 'active', NO force-close por
                                # mechas re-analizadas (es el bug del 538). El gestor + MT5 SL/TP +
                                # MAX_HOLD gobiernan el cierre; dejamos que MT5 cierre naturalmente.
                                try:
                                    from src.common.config import Config as _PMC
                                    if (getattr(_PMC, 'POSITION_MANAGER_MODE', 'log') or 'log').lower() == 'active':
                                        should_force_close = False
                                except Exception:
                                    pass
                                if should_force_close and mt5_exec and mt5_exec.is_ready():
                                    try:
                                        mt5_closed_price = mt5_exec.close_strategy_position(sid)
                                    except Exception as e:
                                        logger.error(f"MT5 close on eval error: {e}")
                                elif mt5_exec and mt5_exec.is_ready():
                                    # Check if MT5 already closed the position naturally (TP/SL hit by ticks)
                                    try:
                                        from src.common.db import get_mt5_pnl_for_strategy
                                        _mt5_check = get_mt5_pnl_for_strategy(sid)
                                        if _mt5_check and _mt5_check['pnl'] is not None:
                                            # MT5 already closed — use that data, don't force anything
                                            logger.info(f"Strategy #{sid} expired — MT5 already closed naturally @ ${_mt5_check['pnl']:.2f}")
                                        else:
                                            # v3.51.1 — "sin P&L" NO implica "posicion abierta". Una
                                            # estrategia que nunca llego al broker (cooldown, market
                                            # closing, spread gate, sin fill) tampoco tiene P&L, y este
                                            # branch la dejaba en limbo: `continue` para siempre, con el
                                            # log mintiendo cada 10s (#865 lo repitio ~4.300 veces en 12h)
                                            # hasta que el eval de arranque la archivaba como fantasma.
                                            # El ticket distingue los dos casos sin ambiguedad.
                                            # imports LOCALES a proposito: `_sq3`/`DB_PATH` se asignan
                                            # en otras ramas de esta misma funcion, y depender de eso
                                            # es la clase de bug que mato a SMC en v3.50.4.
                                            # Si la lectura falla NO adivinamos: se asume que hay
                                            # posicion y se conserva el comportamiento previo
                                            # (continue). Nunca evaluar por precio algo que
                                            # podria estar abierto — es el bug v3.39.1.
                                            _tk = 'unknown'
                                            try:
                                                import sqlite3 as _sq3b
                                                from src.common.db import DB_PATH as _DBP
                                                _c3 = _sq3b.connect(_DBP, timeout=15.0)
                                                _r3 = _c3.execute("SELECT mt5_ticket FROM auto_strategies WHERE id=?", (sid,)).fetchone()
                                                _c3.close()
                                                _tk = _r3[0] if _r3 else None
                                            except Exception as _tke:
                                                logger.debug(f"ticket check #{sid}: {_tke}")
                                            if _tk:
                                                # Position still open — let it run with MT5's SL/TP
                                                logger.info(f"Strategy #{sid} expired but MT5 position still OPEN (ticket #{_tk}) — letting SL/TP do their job (no force-close)")
                                                # Skip evaluation this cycle; will be re-evaluated when MT5 closes naturally
                                                continue
                                            # Nunca se ejecuto: no hay posicion que esperar. Se evalua la
                                            # SEÑAL normalmente (strategy_results) y archive_trade la
                                            # excluye de trade_archive por el guard de v3.51.1.
                                            logger.info(f"Strategy #{sid} expired y NUNCA se ejecuto (sin ticket) — se evalua la señal, no entra a trade_archive")
                                    except Exception as e:
                                        logger.debug(f"MT5 status check on expiry: {e}")

                                # Check if MT5 already has real P&L (closed by TP/SL via sync)
                                try:
                                    from src.common.db import get_mt5_pnl_for_strategy
                                    mt5_data = get_mt5_pnl_for_strategy(sid)
                                    if mt5_data and mt5_data['pnl'] is not None:
                                        # Use MT5 ground truth: real P&L -> pips
                                        lot = mt5_data['lot'] or 0.1
                                        pips_result = round(mt5_data['pnl'] / (lot * 10), 1)
                                        # BE flag overrides: if SL was at BE, it's break_even regardless of spread loss
                                        if be_triggered and mt5_data['pnl'] <= 0:
                                            result = 'break_even'
                                            logger.info(f"Strategy #{sid} BE flag + MT5 P&L ${mt5_data['pnl']:.2f} ({pips_result:+.1f}p spread cost) -> BREAK_EVEN")
                                        else:
                                            result = 'win' if mt5_data['pnl'] > 0 else 'loss'
                                        exit_px = mt5_data['close_price'] or exit_px
                                        logger.info(f"Strategy #{sid} using MT5 P&L: ${mt5_data['pnl']:.2f} = {pips_result:+.1f}p -> {result}")
                                        mt5_closed_price = None  # skip next block
                                except Exception as e:
                                    logger.debug(f"MT5 P&L lookup #{sid}: {e}")

                                # Fallback: if MT5 just closed, use close price (no spread deduction)
                                if mt5_closed_price and isinstance(mt5_closed_price, (int, float)) and mt5_closed_price > 0:
                                    exit_px = mt5_closed_price
                                    if direction == 'CALL':
                                        pips_result = (exit_px - entry_price) / pip
                                    else:
                                        pips_result = (entry_price - exit_px) / pip
                                    # BE flag overrides: if SL was at BE, it's break_even
                                    if be_triggered and pips_result <= 0:
                                        result = 'break_even'
                                        logger.info(f"Strategy #{sid} BE flag + close price: {pips_result:+.1f}p spread cost -> BREAK_EVEN")
                                    else:
                                        result = 'win' if pips_result > 0 else 'loss'

                                auto_evaluate_strategy(sid, result, exit_px, round(pips_result, 1), ctx)
                                try:
                                    from src.common.db import archive_trade, get_entry_context
                                    ms = tech.get_market_state()
                                    entry_ctx = get_entry_context(sid)
                                    if entry_ctx:
                                        ctx['rsi_at_entry'] = entry_ctx.get('rsi', 0)
                                        ctx['avg_range_pips'] = entry_ctx.get('avg_range_pips', 0)
                                        ctx['volatility'] = entry_ctx.get('volatility', '')
                                        ctx['market_trend'] = entry_ctx.get('trend') or ms.get('trend', '')
                                        ctx['trend_strength'] = entry_ctx.get('trend_strength') or ms.get('trend_strength', '')
                                        ctx['htf_bias'] = entry_ctx.get('htf_bias', '')
                                    else:
                                        ctx['volatility'] = ms.get('volatility', '')
                                        ctx['trend_strength'] = ms.get('trend_strength', '')
                                        ctx['avg_range_pips'] = ms.get('avg_range_pips', 0)
                                        try:
                                            if smc:
                                                ctx['htf_bias'] = smc.get_status().get('htf_bias', '') or ''
                                        except Exception:
                                            ctx['htf_bias'] = ''
                                    archive_trade(sid, result, exit_px, round(pips_result, 1), ctx)
                                except Exception as e:
                                    logger.warning(f"Archive trade eval #{sid}: {e}")
                                # Post-trade analysis in background thread
                                try:
                                    from src.analyzer.post_trade_analyzer import analyze_closed_trade
                                    from src.common.db import save_post_trade_analysis, save_learning_insight
                                    _mt5_pnl_val = 0
                                    try:
                                        _mt5d = get_mt5_pnl_for_strategy(sid)
                                        if _mt5d and _mt5d.get('pnl') is not None:
                                            _mt5_pnl_val = _mt5d['pnl']
                                    except Exception as e:
                                        logger.debug(f"MT5 P&L for post-trade: {e}")
                                    _pt_data = {
                                        'strategy_id': sid,  # v3.53.7: para leer el recorrido (MFE)
                                        'result': result, 'pips': round(pips_result, 1), 'direction': direction,
                                        'trigger_type': trigger_type or '', 'entry_price': entry_price, 'exit_price': exit_px,
                                        'stop_loss': sl, 'take_profit': tp, 'sl_pips': abs(sl - entry_price) / pip,
                                        'tp_pips': abs(tp - entry_price) / pip, 'session': ctx.get('session', ''),
                                        'rsi': ctx.get('rsi_at_entry', 50), 'trend': ctx.get('market_trend', ''),
                                        'trend_strength': ctx.get('trend_strength', ''), 'htf_bias': ctx.get('htf_bias', ''),
                                        'volatility': ctx.get('volatility', ''), 'news_title': news_title or '',
                                        'confidence': conf, 'duration_min': expiry_min or 15, 'mt5_pnl': _mt5_pnl_val,
                                    }
                                    def _run_pt_eval(s_id, data, res):
                                        try:
                                            # v3.53.6 — ver el comentario del gemelo en el eval de
                                            # arranque: no se analizan señales que nunca llegaron al
                                            # broker (sus pips son teoricos). Este es el path que
                                            # genero la leccion fantasma de #886. fail-open ante duda.
                                            from src.common.db import strategy_was_executed as _was_exec
                                            if _was_exec(s_id) is False:
                                                logger.info(f"Post-trade #{s_id}: SKIP — la señal nunca se ejecuto (sin ticket ni P&L)")
                                                return
                                            analysis = analyze_closed_trade(data)
                                            if analysis:
                                                save_post_trade_analysis(s_id, analysis, res)
                                                save_learning_insight('post_trade', analysis.get('key_lesson', ''), data=analysis)
                                                logger.info(f"Post-trade #{s_id}: {analysis.get('key_lesson', '')}")
                                        except Exception as _e:
                                            logger.debug(f"Post-trade analysis #{s_id} error: {_e}")
                                    Thread(target=_run_pt_eval, args=(sid, _pt_data, result), daemon=True).start()
                                except Exception as e:
                                    logger.debug(f"Post-trade thread eval: {e}")

                                method = 'TP hit' if hit_tp else ('BE hit' if hit_be else ('SL hit' if hit_sl else f'price eval {current_price:.5f}'))
                                logger.info(f"Auto-eval #{sid}: {result.upper()} | {direction} entry={entry_price:.5f} exit={exit_px:.5f} | {pips_result:+.1f}p | {method}")

                    except Exception as e:
                        logger.error(f"Auto-eval error: {e}", exc_info=True)

                    # ===== AUTO-EVALUATE NEWS ALERTS =====
                    try:
                        pending_alerts = get_alerts_pending_evaluation()
                        if pending_alerts:
                            current_price = tech.get_market_state().get('price', 0)
                            if current_price:
                                pip = 0.0001
                                min_pips_move = 2.0  # minimum pips to count as win/loss
                                _eval_ok = 0
                                for arow in pending_alerts:
                                  # v3.50.1 — try POR ALERTA: antes el try envolvia el for
                                  # entero, asi que una sola fila mala (p.ej. el
                                  # IntegrityError de 'break_even') abortaba la evaluacion
                                  # de todas las alertas siguientes del lote.
                                  try:
                                    aid, a_dir, a_entry, a_conf, a_impact, a_sent, a_title = arow
                                    if not a_entry or a_entry <= 0:
                                        continue
                                    if a_dir == 'CALL':
                                        pips_move = (current_price - a_entry) / pip
                                    else:  # PUT
                                        pips_move = (a_entry - current_price) / pip

                                    if pips_move >= min_pips_move:
                                        a_result = 'win'
                                    elif pips_move <= -min_pips_move:
                                        a_result = 'loss'
                                    else:
                                        a_result = 'break_even'

                                    auto_evaluate_alert(aid, a_result, current_price, pips_move)

                                    # Also record in signal_results for learning/performance stats
                                    record_signal_result(aid, a_result, {
                                        'entry_price': a_entry,
                                        'exit_price': current_price,
                                        'pips': round(pips_move, 1),
                                        'direction': a_dir,
                                        'confidence': a_conf,
                                        'impact_score': a_impact,
                                        'setup_type': 'news',
                                        'trigger_type': 'news',
                                        'market_trend': tech.get_market_state().get('trend', ''),
                                        'rsi_at_entry': tech.get_market_state().get('rsi', 0),
                                        'news_category': _classify_news_category(a_title),
                                    })
                                    logger.info(f"Alert eval #{aid}: {a_result.upper()} | {a_dir} entry={a_entry:.5f} exit={current_price:.5f} | {pips_move:+.1f}p | {a_title[:50]}")
                                    _eval_ok += 1
                                  except Exception as _ae:
                                    logger.warning(f"Alert eval fallo en una alerta (sigue el lote): {_ae}")
                                logger.info(f"Evaluated {_eval_ok}/{len(pending_alerts)} pending news alerts")
                    except Exception as e:
                        logger.error(f"Alert auto-eval error: {e}", exc_info=True)

                    # ── MT5: pick up executor connected via dashboard ──
                    if mt5_exec is None:
                        try:
                            from src.admin.main import _get_mt5
                            api_mt5 = _get_mt5()
                            if api_mt5 and api_mt5.connected:
                                mt5_exec = api_mt5
                                with self._mt5_lock:
                                    self._mt5_exec = mt5_exec
                                logger.info("MT5 adopted from dashboard connection")
                        except Exception as e:
                            logger.debug(f"MT5 dashboard adopt: {e}")

                    # ── MT5: reconnect if disconnected ──
                    if mt5_exec and not mt5_exec.connected:
                        try:
                            logger.info("MT5 disconnected — attempting reconnect...")
                            if mt5_exec.connect():
                                logger.info("MT5 reconnected successfully")
                                try:
                                    from src.admin.main import set_mt5_executor
                                    set_mt5_executor(mt5_exec)
                                except Exception as e:
                                    logger.debug(f"MT5 reconnect API export: {e}")
                            else:
                                logger.debug("MT5 reconnect failed, will retry next cycle")
                        except Exception as e:
                            logger.error(f"MT5 reconnect error: {e}")
                    elif Config.MT5_ENABLED and mt5_exec is None:
                        try:
                            from src.broker.mt5_executor import MT5Executor
                            mt5_exec = MT5Executor(logger)
                            mt5_exec.set_smc_ref(smc)  # Inject SMC for htf_bias lookup
                            if mt5_exec.connect():
                                logger.info("MT5 late-connect succeeded")
                                with self._mt5_lock:
                                    self._mt5_exec = mt5_exec
                                try:
                                    from src.admin.main import set_mt5_executor
                                    set_mt5_executor(mt5_exec)
                                except Exception as e:
                                    logger.debug(f"MT5 late-connect API export: {e}")
                            else:
                                mt5_exec = None
                        except Exception as e:
                            logger.error(f"MT5 late-connect error: {e}")
                            mt5_exec = None

                    # ── MT5: retry execution for active strategies without tickets ──
                    if mt5_exec and mt5_exec.is_ready():
                        try:
                            from src.common.db import get_active_unexecuted_strategies
                            unexecuted = get_active_unexecuted_strategies()
                            for strat in unexecuted:
                                sid = strat['id']
                                # v3.31.4: pasar trigger_type para aplicar lot cap pre-plan
                                _trig = strat.get('trigger_type') if isinstance(strat, dict) else None
                                ticket = _try_mt5_execute(
                                    sid, strat['direction'], strat['entry_price'],
                                    strat['stop_loss'], strat['take_profit'], strat['confidence'],
                                    trigger_type=_trig
                                )
                                if ticket:
                                    logger.info(f"MT5 retry SUCCESS: ticket #{ticket} for strategy #{sid}")
                                else:
                                    logger.debug(f"MT5 retry: no fill for strategy #{sid}")
                        except Exception as e:
                            logger.error(f"MT5 retry execution error: {e}")

                    # ── MT5 trailing SL: handled by dedicated 1s thread (run_trailing_monitor) ──

                    # ── MT5: close positions for evaluated strategies ──
                    if mt5_exec and mt5_exec.is_ready():
                        try:
                            from src.common.db import get_evaluated_open_mt5
                            # v3.40.11 FIX (forense 10 Jun): con PM active, NO cerrar por 'expired'.
                            # Este late-close pisaba los HOLD/EXTEND del Position Manager a segundos
                            # del expiry (#609/#613/#614; y corto al ganador #603 a +5.8p de 17p TP)
                            # -> la pata "extender mas alla del expiry" del experimento PM estaba
                            # estructuralmente muerta. Ahora con PM active gobiernan PM (R2/R4
                            # MAX_HOLD 90/120/240min) + SL/TP duro. auto_win/auto_loss se siguen
                            # cerrando (ya evaluados). En mode log/off el comportamiento no cambia.
                            try:
                                from src.common.config import Config as _LCCfg
                                _pm_owns_expiry = (getattr(_LCCfg, 'POSITION_MANAGER_MODE', 'log') or 'log').lower() == 'active'
                            except Exception:
                                _pm_owns_expiry = False
                            for row in get_evaluated_open_mt5():
                                if _pm_owns_expiry and row['result'] == 'expired':
                                    continue  # el PM decide la salida; MAX_HOLD es el techo
                                try:
                                    mt5_exec.close_strategy_position(row['id'])
                                    logger.info(f"MT5 late-close: strategy #{row['id']} (evaluated as {row['result']})")
                                except Exception as e:
                                    logger.error(f"MT5 late-close error #{row['id']}: {e}")
                        except Exception as e:
                            logger.debug(f"MT5 evaluated-close check: {e}")

                    # ── MT5: pre-market-close — close all positions 10min before Friday close ──
                    if mt5_exec and mt5_exec.is_ready():
                        try:
                            from datetime import datetime, timezone, timedelta
                            utc_now = datetime.now(timezone.utc)
                            # Forex closes Friday ~21:00 UTC (18:00 AR), close positions at 20:50 UTC (17:50 AR)
                            if utc_now.weekday() == 4 and utc_now.hour == 20 and utc_now.minute >= 50:
                                positions = mt5_exec.check_positions()
                                if positions:
                                    logger.warning(f"Market closing soon — closing {len(positions)} open position(s)")
                                    closed = mt5_exec.close_all_positions()
                                    logger.info(f"Pre-close: {closed} position(s) closed before weekend")
                        except Exception as e:
                            logger.error(f"MT5 pre-close error: {e}")

                    # ── MT5: sync closed positions ──
                    if mt5_exec and mt5_exec.is_ready():
                        try:
                            mt5_exec.sync_closed_positions()
                        except Exception as e:
                            logger.error(f"MT5 sync error: {e}")

                    # v3.24.0 — Telegram drawdown + milestone alerts (cada N cycles, throttled)
                    if iteration % 30 == 0:  # cada ~5min (interval 10s × 30)
                        try:
                            from src.common.telegram_alerts import check_and_send_drawdown, check_and_send_milestone, is_configured, send_alert
                            if is_configured() and mt5_exec and mt5_exec.is_ready():
                                # Drawdown check
                                try:
                                    info = mt5_exec._mt5.account_info() if mt5_exec._mt5 else None
                                    if info:
                                        check_and_send_drawdown(info.balance, info.profit if hasattr(info, 'profit') else 0.0)
                                except Exception:
                                    pass
                                # Milestone check Track B/C
                                try:
                                    from src.common.db import get_strategy_performance_by_track
                                    stats = get_strategy_performance_by_track()
                                    tb = stats.get('track_b_m15', {})
                                    tc = stats.get('track_c_h1', {})
                                    if tb.get('total', 0) > 0:
                                        check_and_send_milestone('Track B M15', tb['total'], tb['win_rate'], tb['profit_factor'], tb['sum_pnl'])
                                    if tc.get('total', 0) > 0:
                                        check_and_send_milestone('Track C H1', tc['total'], tc['win_rate'], tc['profit_factor'], tc['sum_pnl'])
                                except Exception:
                                    pass
                        except Exception as _ta:
                            logger.debug(f"Telegram periodic check: {_ta}")

                    # v3.28.0 — Daily loss limit auto-pause
                    # Cada cycle: si daily_pnl <= -LIMIT y kill switch OFF -> activar kill switch
                    # Reset al día siguiente: si cambió la fecha, asegurar kill switch OFF (si no fue activado manual)
                    if mt5_exec and mt5_exec.is_ready() and Config.DAILY_LOSS_LIMIT_USD > 0:
                        try:
                            info = mt5_exec._mt5.account_info() if mt5_exec._mt5 else None
                            if info:
                                daily_pnl = info.profit if hasattr(info, 'profit') else 0.0
                                # Detect day change to reset auto-pause flag
                                from datetime import datetime as _dlt
                                today_str = _dlt.now().strftime('%Y-%m-%d')
                                if not hasattr(self, '_dll_today_paused') or self._dll_today_paused != today_str:
                                    # New day: clear paused state (kill switch can be reset by analyzer)
                                    if hasattr(self, '_dll_auto_paused') and self._dll_auto_paused and not getattr(self, '_dll_user_paused', False):
                                        # We auto-paused yesterday, restore
                                        mt5_exec.kill_switch = False
                                        logger.info(f"Daily loss limit: new day, auto-pause cleared")
                                        try:
                                            from src.common.telegram_alerts import send_alert
                                            send_alert("Nuevo dia: auto-pause del daily loss limit liberado. Trading REANUDADO.", level='INFO')
                                        except Exception:
                                            pass
                                    self._dll_today_paused = today_str
                                    self._dll_auto_paused = False
                                # Check trigger
                                if daily_pnl <= -Config.DAILY_LOSS_LIMIT_USD and not mt5_exec.kill_switch:
                                    mt5_exec.kill_switch = True
                                    self._dll_auto_paused = True
                                    logger.warning(f"Daily loss limit TRIGGERED: ${daily_pnl:+.2f} <= -${Config.DAILY_LOSS_LIMIT_USD} -> kill switch ON")
                                    try:
                                        from src.common.telegram_alerts import send_alert
                                        send_alert(
                                            f"*Daily loss limit alcanzado*\n"
                                            f"PnL hoy: ${daily_pnl:+.2f}\n"
                                            f"Limit: -${Config.DAILY_LOSS_LIMIT_USD}\n"
                                            f"Trading auto-pausado hasta manana.",
                                            level='CRITICAL'
                                        )
                                    except Exception:
                                        pass
                        except Exception as _dle:
                            logger.debug(f"Daily loss limit check: {_dle}")

                    # v3.19.0 — Track B: M15 structure scan paralelo (cada 60s)
                    # Track separado del M5: trigger_type='m15_structure', profile M15.
                    # Filtros mínimos (counter-both + conf ceiling). Sin late breakout
                    # (M15 está en otra escala). Sin hour gate (ya removido v3.17).
                    # v3.31.7 — Warmup gate: skip primeros 30min post-restart para que
                    # cierren 2 velas M15 frescas mientras observamos en real-time.
                    _m15_warmup_elapsed = time.time() - _analyzer_warmup_start
                    _m15_in_warmup = _m15_warmup_elapsed < M15_WARMUP_SECONDS
                    if _m15_in_warmup:
                        # Log cada 5min para no spamear pero confirmar que el gate trabaja
                        if time.time() - _last_m15_warmup_log > 300:
                            logger.info(f"M15 warmup gate: scan skipped, {_m15_warmup_elapsed:.0f}s < {M15_WARMUP_SECONDS}s ({(M15_WARMUP_SECONDS - _m15_warmup_elapsed)/60:.1f}min restantes)")
                            _last_m15_warmup_log = time.time()
                    try:
                        if not _m15_in_warmup and (time.time() - _last_m15_scan) >= M15_SCAN_INTERVAL:
                            _last_m15_scan = time.time()
                            _m15_state = tech_m15.get_market_state()
                            _m15_atr = _m15_state.get('avg_range_pips', 0)
                            # ATR floor M15 (v3.55.0: perilla, antes 5.0 fijo). El default
                            # sigue siendo 5p (vs M5 2.5p — el ATR de M15 es ~3x). Subirlo a 8
                            # saca el chop, que es donde m15 pierde de forma consistente
                            # (<=8p: n=90 WR 27.8% -$75.59 | >8p: n=31 WR 51.6% +$18.80).
                            # Ver el comentario largo en Config.M15_ATR_FLOOR.
                            # Se lee en CADA ciclo a proposito: asi cambiar el .env y reiniciar
                            # alcanza, sin rebuild del exe.
                            _m15_atr_floor = getattr(Config, 'M15_ATR_FLOOR', 5.0)
                            if _m15_atr < _m15_atr_floor and (time.time() - _last_m15_floor_log) > 3600:
                                _last_m15_floor_log = time.time()
                                logger.info(
                                    f"M15: ATR {_m15_atr:.1f}p < piso {_m15_atr_floor:.1f}p "
                                    f"-> sin scan (chop). Perilla: M15_ATR_FLOOR")
                            if _m15_atr >= _m15_atr_floor:
                                # v3.33.0 (Fase B): htf_bias y daily_ctx GARANTIZADOS por scope
                                # superior (se setean siempre, antes del structure scanner).
                                # Antes usabamos 'in dir()' check que retornaba None cuando M5
                                # scanner estaba skipped por session/ATR -> M15 sin contexto macro.
                                _m15_signals = tech_m15.detect_structure_signals(
                                    min_confidence=M15_PROFILE['min_confidence'],
                                    htf_bias=htf_bias,
                                    daily_context=daily_ctx
                                )
                                if _m15_signals:
                                    # Pick highest confidence signal
                                    _top = max(_m15_signals, key=lambda s: s['confidence'])
                                    _m15_dir = _top['direction']
                                    _m15_conf = _top['confidence']

                                    # Counter-both filter: if HTF + M5 both AGAINST direction → block
                                    _m5_state_now = tech.get_market_state()
                                    _m5_trend_now = _m5_state_now.get('trend', 'neutral')
                                    _m15_counter_both = (
                                        htf_bias and htf_bias != 'neutral' and _m5_trend_now != 'neutral' and (
                                            (_m15_dir == 'CALL' and htf_bias == 'bearish' and _m5_trend_now == 'bearish') or
                                            (_m15_dir == 'PUT' and htf_bias == 'bullish' and _m5_trend_now == 'bullish')
                                        )
                                    )
                                    # v3.19.1 — REMOVED conf ceiling. Era data M5 contaminada aplicada
                                    # a M15 sin evidencia. M15 puede ganar con conf alta (movimientos
                                    # claros sostenidos != exhaustion entry M5). Re-evaluar con data
                                    # fresca M15 si efectivamente conf>=80 pierde tambien aqui.
                                    # Anti-spam: skip if active opposite OR active m15_structure already
                                    _m15_skip_dup = False
                                    try:
                                        if has_active_opposite_strategy(_m15_dir):
                                            _m15_skip_dup = True
                                    except Exception:
                                        pass

                                    if _m15_counter_both:
                                        logger.info(f"M15: counter-both blocked {_m15_dir} (htf={htf_bias} m5={_m5_trend_now})")
                                    elif _m15_skip_dup:
                                        logger.info(f"M15: skipping {_m15_dir}, active opposite exists")
                                    else:
                                        _m15_price = _m15_state.get('price', 0)
                                        # Use MT5 tick if available
                                        if mt5_exec and mt5_exec.is_ready() and mt5_exec._mt5:
                                            try:
                                                _tk = mt5_exec._mt5.symbol_info_tick("EURUSD")
                                                if _tk:
                                                    _m15_price = _tk.ask if _m15_dir == 'CALL' else _tk.bid
                                            except Exception:
                                                pass
                                        if _m15_price > 0:
                                            _m15_adapt = tech_m15.compute_adaptive_sl_tp(
                                                _m15_dir, _m15_price, _m15_state, M15_PROFILE,
                                                trigger_type='m15_structure',
                                                sl_tp_advice=_learn_adj.get('sl_tp_advice') if _learn_adj else None
                                            )
                                            _m15_sl = _m15_adapt['sl']
                                            _m15_tp = _m15_adapt['tp']
                                            # entry_context atomic — v3.40.11 FIX: dict crudo, NO json.dumps.
                                            # add_auto_strategy ya dumpea (db.py); el doble-encode hacia que
                                            # get_entry_context devolviera str -> .get() AttributeError tragado
                                            # -> archive directo NUNCA corria para m15 (features vacias).
                                            _m15_ctx = {
                                                'rsi': _m15_state.get('rsi'),
                                                'rsi_zone': _m15_state.get('rsi_zone'),
                                                'avg_range_pips': _m15_atr,
                                                'volatility': _m15_state.get('volatility'),
                                                'trend': _m15_state.get('trend'),
                                                'trend_strength': _m15_state.get('trend_strength'),
                                                'momentum': _m15_state.get('momentum'),
                                                'htf_bias': htf_bias,
                                                'timeframe': 'M15',
                                                'setup_type': _top.get('setup_type', ''),  # v3.48.0
                                            }
                                            _m15_title = f"[M15-STRUCT] {_top.get('reason', '')[:200]}"
                                            _m15_sid = add_auto_strategy(
                                                alert_id=None,
                                                news_title=_m15_title,
                                                direction=_m15_dir,
                                                entry_price=_m15_price,
                                                stop_loss=_m15_sl,
                                                take_profit=_m15_tp,
                                                confidence=_m15_conf,
                                                impact_score=_top.get('impact_score', 70),
                                                expiry_minutes=M15_PROFILE['expiry_minutes'],
                                                trigger_type='m15_structure',
                                                profile_name=M15_PROFILE['name'],
                                                candles_snapshot=None,
                                                entry_context=_m15_ctx,
                                            )
                                            if _m15_sid:
                                                # v3.40.21 — tag calidad de nivel (Grupo B en shadow) para M15
                                                try:
                                                    from src.common.db import log_level_quality
                                                    log_level_quality(_m15_sid, _top.get('setup_type', 'm15_structure'),
                                                                      _m15_dir, _top.get('key_level'),
                                                                      _top.get('level_touches', 0), _m15_conf)
                                                except Exception:
                                                    pass
                                                # v3.35.0 — ML confidence predictor para m15_structure (AUC 0.625 en test)
                                                _m15_exec_conf = _m15_conf
                                                try:
                                                    from src.optimizer.confidence_predictor import predict_confidence
                                                    from datetime import datetime as _dt, timezone as _tz
                                                    _now = _dt.now(_tz.utc)
                                                    _ml_sig_m15 = {
                                                        'trigger_type': 'm15_structure',
                                                        'direction': _m15_dir,
                                                        'session': _m15_state.get('session', '') if isinstance(_m15_state, dict) else '',
                                                        'htf_bias': htf_bias or '',
                                                        'market_trend': _m15_state.get('trend', '') if isinstance(_m15_state, dict) else '',
                                                        'trend_strength': _m15_state.get('trend_strength', '') if isinstance(_m15_state, dict) else '',
                                                        'volatility': _m15_state.get('volatility', '') if isinstance(_m15_state, dict) else '',
                                                        'rsi_at_entry': _m15_state.get('rsi', 50) if isinstance(_m15_state, dict) else 50,
                                                        'avg_range_pips': _m15_atr,
                                                        'hour_utc': _now.hour,
                                                        'day_of_week': _now.weekday(),
                                                    }
                                                    _ml_m15 = predict_confidence(_ml_sig_m15)
                                                    if _ml_m15 is not None:
                                                        logger.info(f"ML predictor override (m15): heuristic {_m15_conf} -> ML {_ml_m15}")
                                                        _m15_exec_conf = _ml_m15
                                                except Exception as _e:
                                                    logger.debug(f"ML predictor error (m15): {_e}")
                                                logger.info(f"M15 strategy #{_m15_sid}: {_m15_dir} conf={_m15_exec_conf} SL={_m15_adapt['sl_pips']:.1f}p TP={_m15_adapt['tp_pips']:.1f}p price={_m15_price:.5f} expiry={M15_PROFILE['expiry_minutes']}min")
                                                _try_mt5_execute(_m15_sid, _m15_dir, _m15_price, _m15_sl, _m15_tp, _m15_exec_conf, track='m15')
                                            else:
                                                logger.info(f"M15: add_auto_strategy returned None for {_m15_dir} (cooldown/cap?)")
                            else:
                                logger.debug(f"M15 skip: ATR {_m15_atr:.1f}p < 5.0p floor")
                    except Exception as _m15_e:
                        logger.error(f"M15 scan error: {_m15_e}")

                    # v3.20.0 — Track C: H1 structure scan paralelo (cada 5 min)
                    # Track separado de M5+M15: trigger_type='h1_structure', profile H1.
                    # H1 candles cambian cada hora, no tiene sentido escanear más seguido.
                    # v3.31.7 — Warmup gate: skip primeros 60min post-restart para que
                    # cierre al menos 1 vela H1 fresca observada en real-time.
                    _h1_warmup_elapsed = time.time() - _analyzer_warmup_start
                    _h1_in_warmup = _h1_warmup_elapsed < H1_WARMUP_SECONDS
                    if _h1_in_warmup:
                        if time.time() - _last_h1_warmup_log > 300:
                            logger.info(f"H1 warmup gate: scan skipped, {_h1_warmup_elapsed:.0f}s < {H1_WARMUP_SECONDS}s ({(H1_WARMUP_SECONDS - _h1_warmup_elapsed)/60:.1f}min restantes)")
                            _last_h1_warmup_log = time.time()
                    try:
                        if not _h1_in_warmup and (time.time() - _last_h1_scan) >= H1_SCAN_INTERVAL:
                            _last_h1_scan = time.time()
                            _h1_state = tech_h1.get_market_state()
                            _h1_atr = _h1_state.get('avg_range_pips', 0)
                            # ATR floor H1: 10p (vs M15 5p, M5 2.5p — escala ~2x cada step)
                            if _h1_atr >= 10.0:
                                # v3.33.0 (Fase B): scope superior garantiza htf_bias/daily_ctx
                                _h1_signals = tech_h1.detect_structure_signals(
                                    min_confidence=H1_PROFILE['min_confidence'],
                                    htf_bias=htf_bias,
                                    daily_context=daily_ctx
                                )
                                if _h1_signals:
                                    _h1_top = max(_h1_signals, key=lambda s: s['confidence'])
                                    _h1_dir = _h1_top['direction']
                                    _h1_conf = _h1_top['confidence']

                                    # Counter-both filter (HTF + M5 ambos contra direction → block)
                                    _m5_state_h1 = tech.get_market_state()
                                    _m5_trend_h1 = _m5_state_h1.get('trend', 'neutral')
                                    _h1_counter_both = (
                                        htf_bias and htf_bias != 'neutral' and _m5_trend_h1 != 'neutral' and (
                                            (_h1_dir == 'CALL' and htf_bias == 'bearish' and _m5_trend_h1 == 'bearish') or
                                            (_h1_dir == 'PUT' and htf_bias == 'bullish' and _m5_trend_h1 == 'bullish')
                                        )
                                    )
                                    # Anti-spam: skip si hay opposite activa
                                    _h1_skip_dup = False
                                    try:
                                        if has_active_opposite_strategy(_h1_dir):
                                            _h1_skip_dup = True
                                    except Exception:
                                        pass

                                    if _h1_counter_both:
                                        logger.info(f"H1: counter-both blocked {_h1_dir} (htf={htf_bias} m5={_m5_trend_h1})")
                                    elif _h1_skip_dup:
                                        logger.info(f"H1: skipping {_h1_dir}, active opposite exists")
                                    else:
                                        _h1_price = _h1_state.get('price', 0)
                                        if mt5_exec and mt5_exec.is_ready() and mt5_exec._mt5:
                                            try:
                                                _tk = mt5_exec._mt5.symbol_info_tick("EURUSD")
                                                if _tk:
                                                    _h1_price = _tk.ask if _h1_dir == 'CALL' else _tk.bid
                                            except Exception:
                                                pass
                                        if _h1_price > 0:
                                            _h1_adapt = tech_h1.compute_adaptive_sl_tp(
                                                _h1_dir, _h1_price, _h1_state, H1_PROFILE,
                                                trigger_type='h1_structure',
                                                sl_tp_advice=_learn_adj.get('sl_tp_advice') if _learn_adj else None
                                            )
                                            _h1_sl = _h1_adapt['sl']
                                            _h1_tp = _h1_adapt['tp']
                                            # v3.40.11 FIX: dict crudo, NO json.dumps (mismo doble-encode que m15)
                                            _h1_ctx = {
                                                'rsi': _h1_state.get('rsi'),
                                                'rsi_zone': _h1_state.get('rsi_zone'),
                                                'avg_range_pips': _h1_atr,
                                                'volatility': _h1_state.get('volatility'),
                                                'trend': _h1_state.get('trend'),
                                                'trend_strength': _h1_state.get('trend_strength'),
                                                'momentum': _h1_state.get('momentum'),
                                                'htf_bias': htf_bias,
                                                'timeframe': 'H1',
                                                'setup_type': _h1_top.get('setup_type', ''),  # v3.48.0
                                            }
                                            _h1_title = f"[H1-STRUCT] {_h1_top.get('reason', '')[:200]}"
                                            _h1_sid = add_auto_strategy(
                                                alert_id=None,
                                                news_title=_h1_title,
                                                direction=_h1_dir,
                                                entry_price=_h1_price,
                                                stop_loss=_h1_sl,
                                                take_profit=_h1_tp,
                                                confidence=_h1_conf,
                                                impact_score=_h1_top.get('impact_score', 70),
                                                expiry_minutes=H1_PROFILE['expiry_minutes'],
                                                trigger_type='h1_structure',
                                                profile_name=H1_PROFILE['name'],
                                                candles_snapshot=None,
                                                entry_context=_h1_ctx,
                                            )
                                            if _h1_sid:
                                                # v3.40.21 — tag calidad de nivel (Grupo B en shadow) para H1
                                                try:
                                                    from src.common.db import log_level_quality
                                                    log_level_quality(_h1_sid, _h1_top.get('setup_type', 'h1_structure'),
                                                                      _h1_dir, _h1_top.get('key_level'),
                                                                      _h1_top.get('level_touches', 0), _h1_conf)
                                                except Exception:
                                                    pass
                                                logger.info(f"H1 strategy #{_h1_sid}: {_h1_dir} conf={_h1_conf} SL={_h1_adapt['sl_pips']:.1f}p TP={_h1_adapt['tp_pips']:.1f}p price={_h1_price:.5f} expiry={H1_PROFILE['expiry_minutes']}min")
                                                _try_mt5_execute(_h1_sid, _h1_dir, _h1_price, _h1_sl, _h1_tp, _h1_conf, track='h1')
                                            else:
                                                logger.info(f"H1: add_auto_strategy returned None for {_h1_dir}")
                            else:
                                logger.debug(f"H1 skip: ATR {_h1_atr:.1f}p < 10.0p floor")
                    except Exception as _h1_e:
                        logger.error(f"H1 scan error: {_h1_e}")

                    # ── v3.54.0 — Track D: swing DIARIO (D1) en SHADOW ──────────────
                    # LOGUEA Y NO OPERA. Corta ANTES de add_auto_strategy, o sea que no
                    # toca auto_strategies (ni su buffer rotativo de 6, ni el rate-limit
                    # horario, ni el cooldown de profile) y nunca llama a _try_mt5_execute.
                    # Los otros 3 tracks quedan 100% intactos.
                    #
                    # El analyzer D1 tiene su PROPIO _triggered_levels (es otra instancia),
                    # asi que su dedup no puede suprimir señales del scanner vivo — a
                    # diferencia de los shadows de pullback/fade-chop, que comparten el
                    # dict del M5 y dependen de un prefijo de key para no pisarlo.
                    #
                    # DELIBERADO: se reproduce la poblacion del backtest, no la del vivo.
                    #   - se loguean TODAS las señales de la vela (el backtest itero sobre
                    #     todas), no solo la de mayor confianza como hacen M15/H1;
                    #   - NO se pasa htf_bias/daily_context (el backtest no los paso, y
                    #     pasarlos cambia dynamic_conf y por lo tanto quien supera el piso
                    #     de confianza). Igual se GUARDAN en la fila como contexto, para
                    #     poder cortar por ellos despues sin haber cambiado la medicion;
                    #   - NO se aplican counter-both ni anti-spam (el backtest tampoco).
                    #   - NO se aplica floor de ATR: el backtest no tenia, y el unico gate
                    #     interno (avg_range < 1.5p) nunca muerde en D1 (ATR ~70p).
                    try:
                        if _d1_mode != 'off' and (time.time() - _last_d1_scan) >= D1_SCAN_INTERVAL:
                            _last_d1_scan = time.time()
                            # Imports LOCALES con alias propio: en este monolito
                            # `datetime` NO existe a nivel de modulo y Config/db se
                            # importan dentro de cada funcion. Un nombre suelto acá
                            # seria NameError -> track muerto (v3.50.4 / v3.33.0).
                            from datetime import datetime as _d1_dt
                            from src.common.db import (log_d1_shadow as _d1_log,
                                                       d1_shadow_already_logged as _d1_seen)
                            _d1_candles = tech_d1._fetch_candles()
                            if not _d1_candles or len(_d1_candles) < 30:
                                # None = MT5 no fue la fuente (fail-closed del analyzer D1).
                                # "no escanear" NO es "no hay señal": se loguea distinto.
                                logger.debug("D1: sin velas del broker este ciclo, skip")
                            else:
                                # ts de la vela D1 CERRADA mas reciente. price_feed ya
                                # descarta la vela en formacion (price_feed.py:142-144),
                                # asi que candles[-1] siempre esta cerrada.
                                # El epoch es HORA SERVIDOR (el broker esta en UTC+3): se
                                # guarda tal cual, porque el scorer compara contra velas
                                # pedidas al mismo MT5 => misma convencion, sin conversion.
                                _d1_ts = int(_d1_dt.fromisoformat(
                                    _d1_candles[-1]['datetime']).timestamp())
                                if _d1_ts == _last_d1_candle_ts:
                                    pass  # misma vela que el scan anterior, nada nuevo
                                elif _d1_seen(_d1_ts):
                                    # ya procesada en una corrida anterior del exe.
                                    # OJO: _d1_seen tambien devuelve True ante error
                                    # de LECTURA (fail-closed para no duplicar), asi
                                    # que esto se loguea — si no, una DB trabada
                                    # descartaria la vela del dia sin dejar rastro.
                                    logger.info(
                                        f"D1 shadow: vela {_d1_candles[-1]['datetime'][:10]} "
                                        f"ya registrada (o DB ilegible), skip")
                                    _last_d1_candle_ts = _d1_ts
                                else:
                                    _d1_state = tech_d1.get_market_state()
                                    _d1_atr = _d1_state.get('avg_range_pips', 0)
                                    _d1_price = _d1_state.get('price', 0)
                                    if _d1_state.get('source') == 'fallback' or _d1_price <= 0:
                                        # get_market_state cae a _fallback_state() si su
                                        # propio fetch falla. Loguear con precio 0 QUEMA
                                        # la vela para siempre (la idempotencia la daria
                                        # por vista) => mejor no marcarla y reintentar.
                                        logger.warning(
                                            "D1 shadow: market state en fallback "
                                            "(price=0) -> no se loguea, se reintenta")
                                    else:
                                        _d1_signals = tech_d1.detect_structure_signals(
                                            min_confidence=D1_PROFILE['min_confidence'])
                                        logger.info(
                                            f"D1 shadow: vela nueva {_d1_candles[-1]['datetime'][:10]} "
                                            f"ATR={_d1_atr:.1f}p -> {len(_d1_signals or [])} señal(es)")
                                        # La vela se marca DESPUES del trabajo: si algo
                                        # falla arriba, el proximo ciclo la reintenta en
                                        # vez de darla por procesada.
                                        _last_d1_candle_ts = _d1_ts
                                        if _d1_signals:
                                            _d1_m5_trend = tech.get_market_state().get('trend', 'neutral')
                                            _d1_snap = _d1_candles[-5:]
                                            for _d1_sig in _d1_signals:
                                                # SL/TP con la formula EXACTA del titular del
                                                # backtest: 1,2xATR y R:R 2 (PF 1,40 / +16,3p).
                                                # En el barrido 1,5xATR rindio MAS (+16,4 vs
                                                # +12,8) pero no es lo que se midio => se deja
                                                # 1,2 para que la fila sea comparable.
                                                # Es METADATA: en shadow no se opera.
                                                _d1_sl = round(max(_d1_atr, 1.0) * 1.2, 1)
                                                _d1_tp = round(_d1_sl * 2.0, 1)
                                                _d1_log(
                                                    _d1_ts,
                                                    _d1_sig.get('direction'),
                                                    _d1_sig.get('setup_type', 'd1_structure'),
                                                    _d1_state.get('price', 0),
                                                    _d1_sig.get('key_level'),
                                                    _d1_sig.get('level_touches', 0),
                                                    _d1_atr,
                                                    _d1_state.get('rsi', 0),
                                                    htf_bias,
                                                    _d1_m5_trend,
                                                    _d1_sig.get('confidence', 0),
                                                    _d1_sl, _d1_tp, _d1_snap)
                                                logger.info(
                                                    f"D1 shadow LOG: {_d1_sig.get('direction')} "
                                                    f"{_d1_sig.get('setup_type')} conf={_d1_sig.get('confidence')} "
                                                    f"SL={_d1_sl}p TP={_d1_tp}p (NO opera)")
                    except Exception as _d1_e:
                        logger.error(f"D1 shadow scan error: {_d1_e}")

                except Exception as e:
                    logger.error(f"Analyzer error: {e}")

                # Cycle overlap guard: sleep remaining time, but at least 1s
                _elapsed = time.time() - _cycle_start
                _remaining = max(1, Config.ANALYZER_INTERVAL - _elapsed)
                if _elapsed > Config.ANALYZER_INTERVAL:
                    logger.warning(f"[{iteration}] Cycle overran: {_elapsed:.1f}s > {Config.ANALYZER_INTERVAL}s interval")
                time.sleep(_remaining)
        except Exception as e:
            print(f"FATAL Analyzer: {e}")
    
    def run_api_service(self):
        """Servicio API integrado"""
        try:
            import uvicorn
            import logging as _logging
            print("API: importing src.admin.main...")
            from src.admin.main import app
            print("API: import successful, starting uvicorn...")

            # Disable uvicorn's own logging config (crashes in frozen exe)
            MINIMAL_LOG_CONFIG = {
                "version": 1,
                "disable_existing_loggers": False,
                "handlers": {
                    "default": {
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stderr",
                    },
                },
                "loggers": {
                    "uvicorn": {"handlers": ["default"], "level": "WARNING"},
                    "uvicorn.error": {"handlers": ["default"], "level": "WARNING"},
                    "uvicorn.access": {"handlers": ["default"], "level": "WARNING"},
                },
            }

            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=8000,
                log_config=MINIMAL_LOG_CONFIG,
                access_log=False,
                loop="asyncio"
            )
            server = uvicorn.Server(config)
            server.run()
        except Exception as e:
            print(f"FATAL API: {e}")
            import traceback
            traceback.print_exc()
            self.log(f"Error API: {e}", "red")
    
    def run_trailing_monitor(self):
        """Dedicated thread: scan MT5 positions every 1s for trailing SL.
        Hybrid stepped + dynamic trail algorithm."""
        import time as _time
        import logging
        _logger = logging.getLogger("analyzer")
        _logger.info("Trailing monitor started (1s interval)")

        # v3.32.0 — Re-enable trailing en modo CONSERVADOR (BE-first then trail).
        # User insight (19 may, 250 trades data): avg_win $2.91 vs avg_loss $3.36.
        # AIdan gana poco y pierde mucho. Math break-even WR=53.6%, actual 38%.
        # El analisis viejo (TRAILING_ENABLED=False, 69 trades) sugeria empeoraba R:R,
        # pero ahora con 250 trades y datos mas claros, vale la pena re-activar
        # en modo BE_FIRST: mover SL a BE+0.5p cuando trade va +50% del TP a favor.
        # Luego, si llega a +80% del TP, trail con stop 3p detras del HWM.
        #
        # Objetivo: reducir avg_loss (BE-out cuando se puede) sin sacrificar avg_win.
        # Math esperado: si 30% de los SL se convierten en BE-out (-$0.35 comm vs -$3.36 SL),
        # avg_loss baja de $3.36 a ~$2.45 → WR break-even baja de 53.6% a 47.4%.
        TRAILING_ENABLED = True
        BE_TRIGGER = 0.50       # Cuando price va +50% del TP -> mover SL a BE
        # v3.40.19 BUGFIX: 0.5p NO cubria la comision real (~0.7p round-turn IC Markets Raw
        # + spread de salida ~0.1p = ~0.8p) -> el "break-even" cerraba NETO negativo (-0.20
        # observado en #658). Subido a 1.0p para que el BE cierre neto >=0, como dice el nombre.
        BE_OFFSET_PIPS = 1.0    # SL queda 1.0p a favor: cubre comision ~0.8p + margen -> neto >=0
        TRAIL_START = 0.80      # Cuando price va +80% del TP -> empezar trail
        TRAIL_PIPS = 3.0        # Trail SL queda 3p detras del HWM
        TRAIL_DIST = TRAIL_PIPS * 0.0001
        BE_OFFSET = BE_OFFSET_PIPS * 0.0001
        MIN_SL_MOVE = 0.00003

        # v3.52.0 — Cap del umbral de BE en pips absolutos, por track. Ver Config para el
        # detalle medido. Resumen: en h1 el TP es ~54p => el BE arma a +27p y el HWM maximo
        # historico es 26.3p => nunca armo. El cap lo baja a +5p, que si se alcanza (32% de
        # los h1). Se resuelve aca una sola vez; el loop solo hace un min().
        # NOTA: Config NO existe a nivel de modulo en este archivo (se importa local en cada
        # sitio, con alias). Importarlo aca adentro y con alias propio es deliberado: es la
        # clase de bug que mato a SMC en v3.50.4 (nombre resuelto desde otro scope).
        try:
            from src.common.config import Config as _TrailCfg
            _be_cap_pips = float(getattr(_TrailCfg, 'BE_TRIGGER_MAX_PIPS', 0) or 0)
            _be_cap_tracks = {
                t.strip() for t in str(getattr(_TrailCfg, 'BE_TRIGGER_MAX_TRACKS', '') or '').split(',')
                if t.strip()
            }
        except Exception as e:
            _be_cap_pips, _be_cap_tracks = 0.0, set()
            _logger.warning(f"BE cap: no se pudo leer la config, queda apagado ({e})")
        _be_cap_dist = _be_cap_pips * 0.0001 if _be_cap_pips > 0 else None
        if _be_cap_dist and _be_cap_tracks:
            _logger.info(f"BE cap activo: {_be_cap_pips}p para {sorted(_be_cap_tracks)}")

        while True:
            try:
                with self._mt5_lock:
                    mt5 = self._mt5_exec
                if not mt5 or not mt5.is_ready():
                    _time.sleep(2)
                    continue

                # Sync pending limit orders (detect fills/expirations)
                try:
                    mt5.sync_pending_orders()
                except Exception as e:
                    _logger.debug(f"Sync pending orders: {e}")

                from src.common.db import (get_strategies_with_open_mt5, update_mt5_trailing_data,
                                           update_mt5_high_water)
                open_mt5 = get_strategies_with_open_mt5()
                if not open_mt5:
                    _time.sleep(1)
                    continue

                tick = mt5.get_tick()
                if not tick:
                    _time.sleep(1)
                    continue

                for row in open_mt5:
                    sid, ticket, direction = row[0], row[1], row[2]
                    entry_price, sl, tp = row[3], row[4], row[5]
                    current_step = row[9] if len(row) > 9 else 0
                    fill_price = row[10] if len(row) > 10 and row[10] else entry_price
                    stored_hwm = row[11] if len(row) > 11 else None

                    tp_distance = abs(tp - fill_price)
                    if tp_distance < 0.00005:
                        continue

                    current_price = tick['bid'] if direction == 'CALL' else tick['ask']

                    # Progress from fill price
                    progress = (current_price - fill_price) if direction == 'CALL' else (fill_price - current_price)

                    # Update high-water mark (best price reached)
                    high_water = max(stored_hwm or 0, progress)

                    # v3.32.0 — Two-stage trailing:
                    # Stage 1 (BE): cuando price reaches BE_TRIGGER del TP, mover SL a BE+offset.
                    # Stage 2 (Trail): cuando price reaches TRAIL_START del TP, trail HWM - TRAIL_DIST.
                    be_threshold = tp_distance * BE_TRIGGER
                    trail_threshold = tp_distance * TRAIL_START

                    # v3.52.0 — el % del TP no sirve cuando el TP es inalcanzable (h1). El min()
                    # es MONOTONICO: solo puede adelantar el BE, nunca atrasarlo. El trailing
                    # (80% del TP) NO se capea: es una etapa distinta, sin evidencia medida.
                    if _be_cap_dist and _be_cap_tracks:
                        _trk = row[13] if len(row) > 13 else None
                        if _trk in _be_cap_tracks:
                            be_threshold = min(be_threshold, _be_cap_dist)
                    be_active = high_water >= be_threshold
                    trail_active = high_water >= trail_threshold

                    new_sl = None
                    new_step = current_step or 0

                    if TRAILING_ENABLED and be_active:
                        if direction == 'CALL':
                            if trail_active:
                                # Stage 2: trail HWM - TRAIL_DIST
                                trail_sl = fill_price + high_water - TRAIL_DIST
                                candidate = max(trail_sl, fill_price + BE_OFFSET)
                                new_step = 2
                            else:
                                # Stage 1: SL a BE + offset (lock pequeno profit)
                                candidate = fill_price + BE_OFFSET
                                new_step = 1
                            if candidate > sl + MIN_SL_MOVE:
                                new_sl = round(candidate, 5)
                        else:  # PUT
                            if trail_active:
                                trail_sl = fill_price - high_water + TRAIL_DIST
                                candidate = min(trail_sl, fill_price - BE_OFFSET)
                                new_step = 2
                            else:
                                candidate = fill_price - BE_OFFSET
                                new_step = 1
                            if candidate < sl - MIN_SL_MOVE:
                                new_sl = round(candidate, 5)

                    # Execute SL modification (only if trailing enabled)
                    if new_sl is not None:
                        success = mt5.modify_position_sl(ticket, new_sl)
                        if success:
                            locked_pips = (new_sl - fill_price) / 0.0001 if direction == 'CALL' else (fill_price - new_sl) / 0.0001
                            update_mt5_trailing_data(sid, new_step, high_water)
                            stage_label = "TRAIL" if new_step == 2 else "BE"
                            _logger.info(
                                f"Trailing[{stage_label}]: #{ticket} strat#{sid} SL->{new_sl:.5f} "
                                f"(lock={locked_pips:+.1f}p hwm={high_water/0.0001:+.1f}p "
                                f"progress={progress/0.0001:+.1f}p)")
                        elif high_water != (stored_hwm or 0) and high_water > 0:
                            # v3.52.1 BUGFIX — AMNESIA DEL HWM. La escritura de arriba vive
                            # bajo `if success`, y el respaldo de abajo es el `elif` de
                            # `new_sl`, NO de `success` => cuando el trailing DECIDE mover el
                            # SL y el broker rechaza el modify, ese ciclo perdia el pico. Y el
                            # pico no se recupera: al ciclo siguiente high_water se recalcula
                            # como max(stored_hwm_viejo, progress_actual), asi que si el precio
                            # ya retrocedio, el maximo real se pierde para siempre.
                            # Medido: 101 filas con el pico retrocediendo en 21 trades (15 m15).
                            # h1 tenia 0 casos SOLO porque su BE nunca armaba (arm a 27p, HWM
                            # max historico 26.3p) => v3.52.0, al bajar el arm a 5p, lo expone
                            # por primera vez. Lo lee el profit-lock del PM (R1).
                            # Helper HWM-only a proposito: el SL no se movio, marcar el step
                            # avanzado o be_triggered=1 seria mentir sobre el estado del stop.
                            update_mt5_high_water(sid, high_water)
                    elif high_water != (stored_hwm or 0) and high_water > 0:
                        # Always track HWM for learning even with trailing disabled
                        update_mt5_trailing_data(sid, new_step, high_water)

            except Exception as e:
                _logger.error(f"Trailing monitor error: {e}")

            _time.sleep(1)

    def run_position_manager(self):
        """v3.36.0 — Live Position Manager (Fase 1: reglas, sin LLM).
        Cada POSITION_MANAGER_INTERVAL s evalua cada posicion abierta y decide
        HOLD / CLOSE_PROFIT / CLOSE_PROTECT / CLOSE_MAXHOLD.
          - modo 'log': solo registra la decision (shadow); el force-close viejo sigue.
          - modo 'active': ejecuta cierres; el force-close por mechas queda desactivado.
        El SL/TP de MT5 y el trailing thread (1s) corren en paralelo sin interferir."""
        import time as _time
        import logging
        from datetime import datetime as _dt, timedelta as _td_pm
        _logger = logging.getLogger("analyzer")

        from src.common.config import Config
        mode = (getattr(Config, 'POSITION_MANAGER_MODE', 'log') or 'log').lower()
        interval = int(getattr(Config, 'POSITION_MANAGER_INTERVAL', 15))
        if mode == 'off':
            _logger.info("Position manager: OFF")
            return

        # v3.40.3: setup (imports + construccion) envuelto en try → si un refactor futuro
        # rompe un simbolo, el thread NO muere en silencio (clase del bug que mato M15 2 semanas).
        try:
            from src.broker.position_manager import (
                PositionManager, PositionContext, ManagerDecision,
                max_hold_for_trigger, CLOSE_ACTIONS, CLOSE_LLM, HOLD)
            from src.common.db import (get_open_mt5_for_manager,
                                       log_position_manager_decision, now_ar)

            pm = PositionManager(
                profit_lock_arm=float(getattr(Config, 'PM_PROFIT_LOCK_ARM', 0.60)),
                profit_lock_keep=float(getattr(Config, 'PM_PROFIT_LOCK_KEEP', 0.60)),
            )
            _llm_enabled = bool(getattr(Config, 'POSITION_MANAGER_LLM', False))
            _llm_cooldown_s = float(getattr(Config, 'PM_LLM_COOLDOWN_MIN', 5)) * 60.0
            _llm_last = {}  # sid -> monotonic_ts de la ultima consulta LLM
            _logger.info(f"Position manager started (mode={mode}, interval={interval}s, llm={_llm_enabled})")
            _PIP = 0.0001
            _last_log = {}  # sid -> (action, monotonic_ts) para throttle de HOLD
        except Exception as _pm_setup_err:
            _logger.error(f"FATAL Position manager setup fallo — thread no arranca: {_pm_setup_err}", exc_info=True)
            return

        while True:
            try:
                with self._mt5_lock:
                    mt5 = self._mt5_exec
                if not mt5 or not mt5.is_ready():
                    _time.sleep(max(interval, 5))
                    continue

                open_rows = get_open_mt5_for_manager()
                if not open_rows:
                    _time.sleep(interval)
                    continue

                tick = mt5.get_tick()
                if not tick:
                    _time.sleep(interval)
                    continue

                # Velas M5 recientes para momentum + ATR (una vez por ciclo)
                candles = mt5.get_candles('5min', count=6) or []
                mom_raw = 0.0
                atr_pips = 0.0
                if len(candles) >= 4:
                    mom_raw = (candles[-1]['close'] - candles[-4]['close']) / _PIP
                if candles:
                    _ranges = [(c['high'] - c['low']) / _PIP for c in candles]
                    atr_pips = sum(_ranges) / len(_ranges)

                for row in open_rows:
                    sid, ticket, direction = row[0], row[1], row[2]
                    entry_price, sl, tp = row[3], row[4], row[5]
                    fill_price = row[6] or entry_price
                    stored_hwm = row[7] or 0.0
                    created_at = row[8]
                    expiry_min = row[9] or 15
                    trigger_type = row[10] or ''

                    if not fill_price or not tp:
                        continue

                    current_price = tick['bid'] if direction == 'CALL' else tick['ask']
                    progress = (current_price - fill_price) if direction == 'CALL' else (fill_price - current_price)
                    hwm = max(stored_hwm, progress)
                    tp_distance = abs(tp - fill_price)
                    sl_distance = abs(sl - fill_price)

                    try:
                        _ct = _dt.strptime(str(created_at).split('.')[0], '%Y-%m-%d %H:%M:%S')
                        # v3.40.12 FIX (caso #615): para pre-plans, created_at es cuando se
                        # PLANEO (dia anterior), no cuando se lleno la orden -> el PM creia
                        # "985min en trade" 20s despues del fill y lo mato por MAX_HOLD antes
                        # del evento. Edad real = expires_at - expiry_minutes (expires_at se
                        # re-escribe a activacion+expiry al activarse; para trades normales
                        # da exactamente created_at). Solo se usa si es POSTERIOR a created_at;
                        # cualquier parse raro -> fallback a created_at.
                        _trade_start = _ct
                        try:
                            _exp_raw = row[12] if len(row) > 12 else None
                            if _exp_raw:
                                _exp = _dt.strptime(str(_exp_raw).replace('T', ' ').split('.')[0], '%Y-%m-%d %H:%M:%S')
                                _derived = _exp - _td_pm(minutes=expiry_min)
                                if _derived > _ct:
                                    _trade_start = _derived
                        except Exception:
                            pass
                        time_in_trade_min = (now_ar().replace(tzinfo=None) - _trade_start).total_seconds() / 60.0
                    except Exception:
                        time_in_trade_min = 0.0

                    mom_aligned = mom_raw if direction == 'CALL' else -mom_raw

                    # v3.51.0 PERILLA 2 — el soft-expiry de news queda ANCLADO donde estaba.
                    # La perilla 1 le da al TRADE mas tiempo (y un TP mas lejos) para que el
                    # ganador llegue; esto evita que de paso el PERDEDOR gane 30min extra para
                    # caminar hasta el stop. CLOSE_PROTECT dispara en time_in_trade >=
                    # base_expiry_min, asi que sin este ancla el cambio se da vuelta (EV -0.86p).
                    # OJO: se toca SOLO lo que ve el PM. `expiry_min` no se modifica porque
                    # arriba deriva _trade_start (fix #615) y abajo nada mas lo usa.
                    _pm_base_expiry = float(expiry_min)
                    _news_pm_anchor = int(getattr(Config, 'NEWS_PM_BASE_EXPIRY_MIN', 15))
                    if (trigger_type or '').lower() == 'news' and _news_pm_anchor > 0:
                        _pm_base_expiry = float(min(expiry_min, _news_pm_anchor))

                    ctx = PositionContext(
                        strategy_id=sid, direction=direction,
                        fill_price=fill_price, current_price=current_price,
                        tp_distance=tp_distance, sl_distance=sl_distance,
                        progress=progress, hwm=hwm,
                        time_in_trade_min=time_in_trade_min,
                        base_expiry_min=_pm_base_expiry,
                        max_hold_min=max_hold_for_trigger(trigger_type, Config),
                        momentum_aligned_pips=mom_aligned,
                        atr_pips=atr_pips, trigger_type=trigger_type,
                    )
                    decision = pm.evaluate(ctx)

                    # ── Fase 2: consulta LLM en zona ambigua (soft-expiry HOLD) ──
                    decision_source = 'rules'
                    if decision.llm_eligible and _llm_enabled:
                        _lp = _llm_last.get(sid)
                        if _lp is None or (_time.monotonic() - _lp) >= _llm_cooldown_s:
                            try:
                                from src.analyzer.exit_advisor import get_exit_advice
                                _rc = ' '.join(
                                    f"{c['open']:.5f}/{c['high']:.5f}/{c['low']:.5f}/{c['close']:.5f}"
                                    for c in candles[-5:]
                                ) if candles else 'n/a'
                                _trend = 'flat'
                                if len(candles) >= 2:
                                    _d = candles[-1]['close'] - candles[0]['close']
                                    _trend = 'up' if _d > 0 else ('down' if _d < 0 else 'flat')
                                advice = get_exit_advice({
                                    'direction': direction, 'fill_price': fill_price,
                                    'current_price': current_price,
                                    'progress_pips': decision.progress_pips,
                                    'hwm_pips': decision.hwm_pips, 'tp_pct': decision.tp_pct,
                                    'tp_pips': tp_distance / _PIP, 'sl_pips': sl_distance / _PIP,
                                    'time_in_trade_min': time_in_trade_min,
                                    'base_expiry_min': float(expiry_min),
                                    'momentum_aligned_pips': mom_aligned, 'atr_pips': atr_pips,
                                    'trend': _trend, 'htf_bias': 'n/a', 'recent_candles': _rc,
                                })
                                _llm_last[sid] = _time.monotonic()
                                if advice:
                                    decision_source = f"llm_{advice.get('source', '?')}"
                                    if advice['action'] == 'CLOSE':
                                        decision = ManagerDecision(
                                            CLOSE_LLM,
                                            f"LLM close (conf {advice['confidence']}): {advice['reasoning']}",
                                            decision.progress_pips, decision.hwm_pips,
                                            decision.tp_pct, False)
                                    elif advice['action'] == 'TIGHTEN':
                                        decision = ManagerDecision(
                                            HOLD,
                                            f"LLM tighten (conf {advice['confidence']}): {advice['reasoning']}",
                                            decision.progress_pips, decision.hwm_pips,
                                            decision.tp_pct, False)
                                    # HOLD -> mantener decision de reglas
                            except Exception as _le:
                                _logger.debug(f"exit_advisor consult error #{sid}: {_le}")

                    is_close = decision.action in CLOSE_ACTIONS

                    executed = 0
                    if is_close and mode == 'active':
                        try:
                            # v3.40.19: pedir el flag did_send -> executed=1 SOLO si el PM
                            # realmente mando la orden. Si la posicion ya estaba cerrada por
                            # TP/SL, did_send=False -> no atribuir el cierre al PM (no ensuciar
                            # la lectura del experimento: "cerre yo" vs "ya estaba cerrado").
                            closed_px, did_send = mt5.close_strategy_position(sid, return_sent_flag=True)
                            if did_send and closed_px:
                                executed = 1
                                _logger.info(f"PositionManager CLOSE [{decision.action}] #{sid} "
                                             f"ticket#{ticket} @ {closed_px} — {decision.reason}")
                            elif closed_px:
                                _logger.info(f"PositionManager [{decision.action}] #{sid} — ya estaba "
                                             f"cerrada por TP/SL @ {closed_px} (no la cerro el PM)")
                            else:
                                # v3.53.0 — el else que faltaba. Sin esto, cuando
                                # close_strategy_position devolvia (None, False) la decision
                                # se persistia con executed=0 y en el log NO quedaba rastro:
                                # el PM decidia cerrar, no se cerraba nada, y nadie se enteraba.
                                # Medido: 25 de 174 CLOSE en modo active (14%) cayeron aca.
                                _logger.warning(
                                    f"PositionManager [{decision.action}] #{sid} ticket#{ticket} — "
                                    f"NO se pudo cerrar (sin precio ni orden enviada). "
                                    f"Razon de la decision: {decision.reason}")
                        except Exception as ce:
                            _logger.error(f"PositionManager close error #{sid}: {ce}")
                    elif is_close:
                        _logger.info(f"PositionManager [LOG] would {decision.action} #{sid} — {decision.reason}")

                    # Throttle de logging: CLOSE siempre; HOLD solo si cambio o cada 5 min.
                    _now_m = _time.monotonic()
                    _prev = _last_log.get(sid)
                    _should_log = (
                        is_close
                        or _prev is None
                        or _prev[0] != decision.action
                        or (_now_m - _prev[1]) >= 300
                    )
                    if _should_log:
                        log_position_manager_decision(
                            sid, ticket, mode, decision.action, decision.reason,
                            decision.progress_pips, decision.hwm_pips, decision.tp_pct,
                            round(time_in_trade_min, 1),
                            decision_source=decision_source, executed=executed)
                        _last_log[sid] = (decision.action, _now_m)

                # Limpiar sids cerrados de los caches
                _open_sids = {r[0] for r in open_rows}
                for _sid in list(_last_log.keys()):
                    if _sid not in _open_sids:
                        _last_log.pop(_sid, None)
                for _sid in list(_llm_last.keys()):
                    if _sid not in _open_sids:
                        _llm_last.pop(_sid, None)

            except Exception as e:
                _logger.error(f"Position manager error: {e}")

            _time.sleep(interval)

    def start_services(self):
        """Iniciar los 4 servicios como threads"""
        self.log("🚀 Iniciando servicios integrados...", "blue")

        # v3.48.0 — Backup de la DB al arrancar (idempotente por dia, rota a 7 dias).
        # La DB es el 100% del track record (trades + insights + shadows) y no tenia
        # ninguna copia. Corre en thread para no demorar el arranque; si falla, se
        # loguea y AIdan sigue normal (nunca bloquea el trading).
        #
        # El logging a archivo se inicializa ACA, antes de lanzar el thread: el primer
        # setup_logging() del proceso ocurre reciEn dentro del thread del collector,
        # asi que sin esto el root no tiene handlers todavia y el resultado del backup
        # se perdia (el INFO se descartaba y el WARNING salia por stderr a una consola
        # oculta) => el user creeria tener backups sin tenerlos.
        # OJO: `Config` NO existe a nivel de modulo en este archivo (todos los demas
        # sitios lo importan localmente). Usar Config.LOG_LEVEL aca tiraba NameError
        # y un `except: pass` se lo comia => install_file_logging nunca corria y el
        # resultado del backup se perdia igual. El except loguea a stderr en vez de
        # tragar, para no repetir la misma clase de bug.
        try:
            from src.common.config import Config as _LogCfg
            from src.common.logging_setup import install_file_logging
            install_file_logging(getattr(_LogCfg, 'LOG_LEVEL', 'INFO'))
        except Exception as _lge:
            import traceback as _tb
            print(f"[start_services] install_file_logging fallo: {_lge}")
            _tb.print_exc()

        def _startup_backup():
            try:
                import logging as _bl
                from src.common.db_backup import run_backup
                run_backup(logger=_bl.getLogger('analyzer'))
            except Exception as _be:
                import logging as _bl
                _bl.getLogger('analyzer').warning(f"Backup de DB no realizado: {_be}")
        Thread(target=_startup_backup, daemon=True).start()

        # Collector thread
        self.log("📰 Iniciando Collector...", "blue")
        collector_thread = Thread(target=self.run_collector_service, daemon=True)
        collector_thread.start()
        self.threads.append(collector_thread)
        time.sleep(2)
        
        # Analyzer thread
        self.log("🧠 Iniciando Analyzer...", "blue")
        analyzer_thread = Thread(target=self.run_analyzer_service, daemon=True)
        analyzer_thread.start()
        self.threads.append(analyzer_thread)
        time.sleep(2)
        
        # API thread
        self.log("🖥️ Iniciando Dashboard API...", "blue")
        api_thread = Thread(target=self.run_api_service, daemon=True)
        api_thread.start()
        self.threads.append(api_thread)
        time.sleep(3)

        # Trailing monitor thread (1s interval)
        trailing_thread = Thread(target=self.run_trailing_monitor, daemon=True)
        trailing_thread.start()
        self.threads.append(trailing_thread)

        # v3.36.0 — Position Manager thread (Fase 1: reglas). Default modo 'log'.
        try:
            from src.common.config import Config as _PMCfg
            if (getattr(_PMCfg, 'POSITION_MANAGER_MODE', 'log') or 'log').lower() != 'off':
                pm_thread = Thread(target=self.run_position_manager, daemon=True)
                pm_thread.start()
                self.threads.append(pm_thread)
        except Exception as _pme:
            import logging as _l
            _l.getLogger('analyzer').warning(f"Position manager no iniciado: {_pme}")

        # v3.31.0 — Meta-optimization daemons
        # Shadow simulator: cada 2 min evalua shadow_strategies pending de simulacion
        # Auto-applier: cada 10 min promueve/aplica/monitorea pending_changes
        # v3.31.3 — Fix: usar logging.getLogger local en lugar de `logger` no definido en este scope
        try:
            import logging as _logging
            _meta_log = _logging.getLogger('analyzer')
            from src.optimizer.shadow_runner import start_shadow_simulator_daemon
            from src.optimizer.auto_applier import start_auto_applier_daemon
            shadow_t = start_shadow_simulator_daemon(self._shutdown_event, interval_sec=120)
            self.threads.append(shadow_t)
            applier_t = start_auto_applier_daemon(self._shutdown_event, interval_sec=600)
            self.threads.append(applier_t)
            _meta_log.info("Meta-optimization daemons started (shadow_simulator 2min, auto_applier 10min)")
        except Exception as e:
            import logging as _logging
            _logging.getLogger('analyzer').warning(f"Meta-optimization daemons failed to start: {e}")

        return True
    
    def open_dashboard(self):
        """Abrir dashboard en navegador"""
        self.log("🌐 Verificando dashboard...", "blue")
        time.sleep(3)
        
        # Verificar que API responde
        for i in range(15):
            try:
                response = requests.get(f"{DASHBOARD_URL}/health", timeout=3)
                if response.status_code == 200:
                    self.log("✅ Dashboard activo - Abriendo...", "green")
                    time.sleep(1)
                    webbrowser.open(DASHBOARD_URL)
                    return True
            except Exception as e:
                self.log(f"⏳ Esperando API... ({i+1}/15)", "blue")
                time.sleep(2)
        
        self.log("⚠️ Dashboard no responde en http://localhost:8000", "orange")
        self.log("Intentá abrir manualmente en tu navegador", "orange")
        return False
    
    def _animate_dots(self):
        """Animate loading dots on the status label."""
        if not self._anim_running:
            return
        if not hasattr(self, '_dot_count'):
            self._dot_count = 0
        self._dot_count = (self._dot_count + 1) % 4
        dots = '.' * self._dot_count
        if hasattr(self, '_current_status_text'):
            self.status_label.config(text=self._current_status_text + dots)
        if self._anim_running:
            self.root.after(500, self._animate_dots)

    def _animate_progress(self):
        """Smooth animated progress bar with shimmer effect."""
        if not self._anim_running and not hasattr(self, '_progress_target'):
            return
        target = getattr(self, '_progress_target', 0)
        current = getattr(self, '_progress_current', 0)
        # Ease towards target
        if current < target:
            current = min(current + 0.008, target)
            self._progress_current = current
        # Draw on canvas
        if hasattr(self, '_progress_canvas'):
            c = self._progress_canvas
            w = c.winfo_width() or 480
            h = c.winfo_height() or 6
            c.delete('all')
            # Background track
            c.create_rectangle(0, 0, w, h, fill=self.BORDER, outline='')
            # Filled portion
            fill_w = int(w * current)
            if fill_w > 0:
                c.create_rectangle(0, 0, fill_w, h, fill=self.ACCENT, outline='')
                # Shimmer highlight
                import math
                shimmer_x = int((math.sin(time.time() * 3) + 1) / 2 * fill_w)
                shimmer_w = min(60, fill_w)
                for i in range(shimmer_w):
                    alpha_frac = 1 - abs(i - shimmer_w // 2) / (shimmer_w // 2)
                    r = int(0x00 + (0xff - 0x00) * alpha_frac * 0.3)
                    g = int(0xd4 + (0xff - 0xd4) * alpha_frac * 0.3)
                    b = int(0xff)
                    color = f'#{r:02x}{g:02x}{b:02x}'
                    x = shimmer_x - shimmer_w // 2 + i
                    if 0 <= x < fill_w:
                        c.create_rectangle(x, 0, x + 1, h, fill=color, outline='')
        self.root.after(30, self._animate_progress)

    def _animate_glow(self):
        """Pulse the glow ring behind the title."""
        if not self._anim_running:
            return
        if hasattr(self, '_glow_canvas') and hasattr(self, '_glow_oval'):
            import math
            phase = (math.sin(time.time() * 2) + 1) / 2  # 0..1
            # Interpolate between dim and bright
            r = int(0x00 + 0x00 * phase)
            g = int(0x50 + int(0x64 * phase))
            b = int(0x80 + int(0x7f * phase))
            color = f'#{r:02x}{g:02x}{b:02x}'
            self._glow_canvas.itemconfig(self._glow_oval, fill=color, outline=color)
        self.root.after(50, self._animate_glow)

    def run(self):
        """Flujo principal con UI moderna."""
        import math

        W, H = 620, 520

        # ── Window (borderless but stays in taskbar) ──
        self.root = tk.Tk()
        self.root.title("AIdan v3.4")
        self.root.geometry(f"{W}x{H}")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        self.root.overrideredirect(True)
        self._anim_running = True
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # v3.35.0 — Icon Tkinter window + taskbar (PyInstaller exe + dev)
        try:
            import sys as _sys
            from pathlib import Path as _Path
            if getattr(_sys, 'frozen', False):
                _icon_base = _Path(getattr(_sys, '_MEIPASS', '.'))
            else:
                _icon_base = _Path(__file__).resolve().parent
            _icon_ico = _icon_base / 'static' / 'aidan_icon.ico'
            if _icon_ico.exists():
                self.root.iconbitmap(default=str(_icon_ico))
        except Exception as _ie:
            pass  # silent fallback to default Tk icon

        # Center on screen
        self.root.update_idletasks()
        sx = (self.root.winfo_screenwidth() - W) // 2
        sy = (self.root.winfo_screenheight() - H) // 2
        self.root.geometry(f"{W}x{H}+{sx}+{sy}")

        # Make borderless window appear in taskbar (Windows)
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

        # ── Drag support ──
        self._drag_data = {'x': 0, 'y': 0}
        def start_drag(e):
            self._drag_data['x'] = e.x
            self._drag_data['y'] = e.y
        def do_drag(e):
            dx = e.x - self._drag_data['x']
            dy = e.y - self._drag_data['y']
            x = self.root.winfo_x() + dx
            y = self.root.winfo_y() + dy
            self.root.geometry(f"+{x}+{y}")

        # ── Outer border glow ──
        border_frame = tk.Frame(self.root, bg=self.ACCENT_DIM, padx=1, pady=1)
        border_frame.pack(fill='both', expand=True)
        inner_frame = tk.Frame(border_frame, bg=self.BG)
        inner_frame.pack(fill='both', expand=True)

        # ── Custom title bar ──
        titlebar = tk.Frame(inner_frame, bg='#060a10', height=36)
        titlebar.pack(fill='x')
        titlebar.pack_propagate(False)
        titlebar.bind('<Button-1>', start_drag)
        titlebar.bind('<B1-Motion>', do_drag)

        tb_left = tk.Label(titlebar, text="  AIdan", font=("Segoe UI", 9),
                          fg=self.TEXT_DIM, bg='#060a10')
        tb_left.pack(side='left', padx=4)
        tb_left.bind('<Button-1>', start_drag)
        tb_left.bind('<B1-Motion>', do_drag)

        close_btn = tk.Label(titlebar, text=" \u2715 ", font=("Segoe UI", 12),
                            fg=self.TEXT_DIM, bg='#060a10', cursor='hand2')
        close_btn.pack(side='right', padx=8)
        close_btn.bind('<Button-1>', lambda e: self._on_close())
        close_btn.bind('<Enter>', lambda e: close_btn.config(fg=self.RED, bg='#1a0008'))
        close_btn.bind('<Leave>', lambda e: close_btn.config(fg=self.TEXT_DIM, bg='#060a10'))

        # ── Accent line under titlebar ──
        tk.Frame(inner_frame, bg=self.ACCENT, height=2).pack(fill='x')

        # ── Main content area ──
        content = tk.Frame(inner_frame, bg=self.BG)
        content.pack(fill='both', expand=True, padx=32, pady=0)

        # ── Glow canvas + Title ──
        header_canvas = tk.Canvas(content, bg=self.BG, height=90, highlightthickness=0)
        header_canvas.pack(fill='x', pady=(18, 0))
        self._glow_canvas = header_canvas

        # Glow ellipse (drawn behind text)
        self._glow_oval = header_canvas.create_oval(
            30, 10, 220, 80, fill=self.ACCENT_GLOW, outline=self.ACCENT_GLOW
        )

        # Title text on canvas
        header_canvas.create_text(
            125, 42, text="AIdan", font=("Segoe UI", 38, "bold"),
            fill=self.TEXT, anchor='center'
        )
        # Version badge
        header_canvas.create_rectangle(200, 25, 262, 50, fill=self.ACCENT_DIM, outline=self.ACCENT)
        header_canvas.create_text(
            231, 37, text="v3.4", font=("Segoe UI", 11, "bold"),
            fill='#ffffff', anchor='center'
        )

        # ── Subtitle ──
        tk.Label(content, text="Scalping Intelligence Engine  ·  EUR/USD",
                font=("Segoe UI", 10), fg=self.TEXT_DIM, bg=self.BG
        ).pack(anchor='w', padx=4, pady=(2, 12))

        # ── Gradient separator ──
        sep_canvas = tk.Canvas(content, bg=self.BG, height=2, highlightthickness=0)
        sep_canvas.pack(fill='x')
        sep_canvas.update_idletasks()
        sep_w = sep_canvas.winfo_width() or 540
        for i in range(sep_w):
            frac = i / max(sep_w, 1)
            if frac < 0.5:
                intensity = frac * 2
            else:
                intensity = (1 - frac) * 2
            r = int(0x00 * intensity)
            g = int(0xd4 * intensity)
            b = int(0xff * intensity)
            sep_canvas.create_rectangle(i, 0, i + 1, 2, fill=f'#{r:02x}{g:02x}{b:02x}', outline='')

        # ── Steps checklist ──
        steps_frame = tk.Frame(content, bg=self.BG_CARD, highlightbackground=self.BORDER,
                              highlightthickness=1)
        steps_frame.pack(fill='x', pady=(14, 0), ipady=8)

        step_names = ["Groq API", "Servicios", "Dashboard"]
        self._step_icons = []
        for i, name in enumerate(step_names):
            row = tk.Frame(steps_frame, bg=self.BG_CARD)
            row.pack(fill='x', padx=16, pady=2)
            icon = tk.Label(row, text="○", font=("Consolas", 11),
                           fg=self.TEXT_DIM, bg=self.BG_CARD, width=2)
            icon.pack(side='left')
            self._step_icons.append(icon)
            tk.Label(row, text=name, font=("Segoe UI", 10),
                    fg=self.TEXT, bg=self.BG_CARD).pack(side='left', padx=(6, 0))

        # ── Animated progress bar ──
        self._progress_canvas = tk.Canvas(content, bg=self.BORDER, height=6,
                                         highlightthickness=0)
        self._progress_canvas.pack(fill='x', pady=(12, 0))
        self._progress_steps = 0
        self._progress_total = 3
        self._progress_target = 0.02
        self._progress_current = 0.0

        # ── Status line ──
        self.status_label = tk.Label(content, text="Iniciando...",
                                     font=("Segoe UI", 10), fg=self.ACCENT,
                                     bg=self.BG, anchor='w')
        self.status_label.pack(fill='x', pady=(10, 0))
        self._current_status_text = "Iniciando"

        # ── Log console ──
        log_frame = tk.Frame(content, bg=self.BG_CARD, highlightbackground=self.BORDER,
                            highlightthickness=1)
        log_frame.pack(fill='both', expand=True, pady=(8, 0))

        self._log_text = tk.Text(log_frame, bg=self.BG_CARD, fg=self.TEXT_DIM,
                                font=("Consolas", 8), height=3, width=50,
                                borderwidth=0, highlightthickness=0,
                                state='disabled', wrap='word')
        self._log_text.pack(fill='both', expand=True, padx=8, pady=4)
        self._log_text.tag_configure('green', foreground=self.GREEN)
        self._log_text.tag_configure('red', foreground=self.RED)
        self._log_text.tag_configure('blue', foreground=self.ACCENT)
        self._log_text.tag_configure('orange', foreground=self.ORANGE)
        self._log_text.tag_configure('white', foreground=self.TEXT)

        # ── Footer ──
        footer = tk.Frame(content, bg=self.BG)
        footer.pack(fill='x', pady=(6, 10))
        tk.Label(footer, text="Mantene esta ventana abierta mientras uses AIdan",
                font=("Segoe UI", 8), fg=self.TEXT_DIM, bg=self.BG).pack(side='left')

        # ── Start animations ──
        self._animate_dots()
        self._animate_progress()
        self._animate_glow()

        # ── Thread-safe messagebox helper ──
        import threading
        _msgbox_result = {}
        _msgbox_event = threading.Event()

        def _ask_yesno_safe(title, message):
            """Show messagebox from main thread, wait for result."""
            _msgbox_event.clear()
            def _show():
                _msgbox_result['value'] = messagebox.askyesno(title, message)
                _msgbox_event.set()
            self.root.after(0, _show)
            _msgbox_event.wait(timeout=120)
            return _msgbox_result.get('value', False)

        # ── Init thread ──
        def init_thread():
            # 1. Groq API
            self._mark_step_active(0)
            self.log("Verificando Groq API...", "blue")
            try:
                from src.common.config import Config
                if Config.GROQ_API_KEY:
                    self.log("Groq API configurada", "green")
                else:
                    self.log("GROQ_API_KEY no configurada", "orange")
            except Exception as e:
                self.log(f"Config: {e}", "orange")
            self._advance_progress(step_index=0)

            # 2. Servicios
            self._mark_step_active(1)
            if self.start_services():
                self._advance_progress(step_index=1)
                # 3. Dashboard
                self._mark_step_active(2)
                self.open_dashboard()
                self._advance_progress(step_index=2)
                self._anim_running = False
                self.log("AIdan activo — dashboard abierto", "green")

        Thread(target=init_thread, daemon=True).start()
        # Start strategy watcher (polls /auto-strategies, fires toast on new ones)
        _launch_strategy_watcher(self.root)
        self.root.mainloop()


if __name__ == "__main__":
    aidan = AIdan()
    aidan.run()
