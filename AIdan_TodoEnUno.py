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
OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_API = "http://localhost:11434/api/tags"
OLLAMA_MODEL = "llama3.1:8b"
DASHBOARD_URL = "http://localhost:8000"

# ─────────────────────────────────────────────────────────────────────────────
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
        print(message)
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
        """Clean shutdown — upload daily report before exiting."""
        self._anim_running = False
        # Try to upload daily report on close
        try:
            from src.reports.daily_report import generate_daily_report
            result = generate_daily_report()
            if result.get('status') == 'success':
                print(f"Daily report uploaded: {result.get('message')}")
        except Exception as e:
            print(f"Report upload skipped: {e}")
        self.root.destroy()
    
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
            
            logger = setup_logging("analyzer", Config.LOG_LEVEL)
            logger.info("Initializing analyzer...")
            init_db()
            
            analyzer = NewsAnalyzer(logger)
            tech = TechnicalAnalyzer(logger)

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
            logger.info("Analyzer + SMC + AutoTuner ready")

            # Calendar pre-news: track already-traded events across cycles
            _traded_calendar_events = set()

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
                        if not current_price or not entry_price:
                            continue
                        hit_tp, hit_sl, hit_be = False, False, False
                        # Break Even: 1:1 R:R distance from entry
                        sl_distance = abs(entry_price - sl)
                        be_target = (entry_price + sl_distance) if direction == 'CALL' else (entry_price - sl_distance)
                        be_triggered = False
                        if candles:
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
                                    # Check if 1:1 R:R was reached (BE trigger)
                                    if not be_triggered:
                                        if direction == 'CALL' and c['high'] >= be_target:
                                            be_triggered = True
                                        elif direction == 'PUT' and c['low'] <= be_target:
                                            be_triggered = True
                                    if direction == 'CALL':
                                        if c['high'] >= tp:
                                            hit_tp = True; break
                                        effective_sl = entry_price if be_triggered else sl
                                        if c['low'] <= effective_sl:
                                            if be_triggered:
                                                hit_be = True
                                            else:
                                                hit_sl = True
                                            break
                                    else:
                                        if c['low'] <= tp:
                                            hit_tp = True; break
                                        effective_sl = entry_price if be_triggered else sl
                                        if c['high'] >= effective_sl:
                                            if be_triggered:
                                                hit_be = True
                                            else:
                                                hit_sl = True
                                            break
                        pip = 0.0001
                        try:
                            est_spread = tech.get_session_info()['spread_est']
                        except Exception:
                            est_spread = 1.0
                        if hit_tp:
                            result = 'win'
                            pips_result = abs(tp - entry_price) / pip - est_spread
                        elif hit_be:
                            result = 'break_even'
                            pips_result = 0.0
                        elif hit_sl:
                            result = 'loss'
                            pips_result = -(abs(sl - entry_price) / pip + est_spread)
                        else:
                            pips_result = ((current_price - entry_price) / pip - est_spread) if direction == 'CALL' else ((entry_price - current_price) / pip - est_spread)
                            min_pips = tuner.get_params().get('min_pips_for_win', 1.5)
                            if be_triggered and pips_result < min_pips:
                                result = 'break_even'
                                pips_result = 0.0
                            else:
                                result = 'win' if pips_result >= min_pips else 'loss'
                        exit_px = tp if hit_tp else (entry_price if hit_be else (sl if hit_sl else current_price))
                        _setup_type = ''
                        _title_lower = (news_title or '').lower()
                        for _st in ['breakout', 'breakdown', 'bb_rejection', 'reversal', 'momentum', 'crossover', 'continuation', 'rebote', 'rechazo', 'soporte', 'resistencia']:
                            if _st in _title_lower:
                                _setup_type = _st
                                break
                        ctx = {'entry_price': entry_price, 'direction': direction, 'confidence': conf,
                               'setup_type': _setup_type, 'trigger_type': trigger_type or '',
                               'market_trend': tech.get_market_state().get('trend', ''),
                               'rsi_at_entry': tech.get_market_state().get('rsi', 0)}
                        auto_evaluate_strategy(sid, result, exit_px, round(pips_result, 1), ctx)
                        logger.info(f"Startup eval #{sid}: {result.upper()} | {direction} entry={entry_price:.5f} exit={exit_px:.5f} | {pips_result:+.1f}p")
                    logger.info(f"Startup: evaluated {len(pending)} pending strategies")
            except Exception as e:
                logger.error(f"Startup eval error: {e}", exc_info=True)

            iteration = 0
            while True:
                try:
                    iteration += 1
                    news_items = get_unprocessed_news()
                    
                    alerts_sent = 0
                    strategies_created = 0
                    # Get current price for alert auto-evaluation
                    _alert_price = tech.get_market_state().get('price', 0)
                    # Source conflict resolution: track directions from each source
                    cycle_signals = []  # list of {'source': str, 'direction': str, 'confidence': int}
                    for news_id, url, title, summary, entities, tags in news_items:
                        result = analyzer.analyze(news_id, title, summary, entities, tags)

                        if result:
                            add_alert(news_id, result['impact_score'], result['level'],
                                    result['explanation'], result['eur_usd_impact'],
                                    result['market_implications'],
                                    result.get('analysis_method', 'keywords'),
                                    result.get('should_operate', False),
                                    result.get('direction', 'NEUTRAL'),
                                    result.get('confidence', 50),
                                    price_at_alert=_alert_price)
                            alerts_sent += 1

                        # Auto-strategy: check against active profile (independent of should_alert)
                        if result and result.get('direction', 'NEUTRAL') != 'NEUTRAL':
                            from src.common.db import get_active_profile
                            profile = get_active_profile()
                            prof_min_impact = profile.get('min_impact', 75)
                            prof_min_conf = profile.get('min_confidence', 65)
                            prof_direction = profile.get('direction', 'any')
                            prof_sl = profile.get('stop_loss_pips', 5)
                            prof_tp = profile.get('take_profit_pips', 10)

                            score_ok = result['impact_score'] >= prof_min_impact
                            conf_ok = result.get('confidence', 0) >= prof_min_conf
                            dir_ok = prof_direction == 'any' or result.get('direction') == prof_direction
                            direction = result.get('direction', 'NEUTRAL')

                            if score_ok and conf_ok and dir_ok:
                                try:
                                    from datetime import datetime as dt
                                    fetch_ts = get_news_fetch_time(news_id)
                                    is_fresh = True
                                    if fetch_ts:
                                        fetch_time = dt.strptime(str(fetch_ts).split('.')[0], '%Y-%m-%d %H:%M:%S')
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
                                            # Adaptive SL/TP based on ATR + structure levels
                                            adaptive = tech.compute_adaptive_sl_tp(direction, price, market, profile)
                                            sl = adaptive['sl']
                                            tp = adaptive['tp']

                                            # Adaptive expiry based on TP distance and current volatility
                                            avg_range_pips = market.get('avg_range_pips', 5.0)
                                            avg_range_pips = avg_range_pips if avg_range_pips > 0 else 5.0
                                            expiry_min = max(15, int(adaptive['tp_pips'] / avg_range_pips * 5))
                                            expiry_min = min(expiry_min, 60)  # cap at 60 min

                                            # Spread gate: skip if estimated spread > 25% of SL
                                            session_info = TechnicalAnalyzer.get_session_info()
                                            est_spread = session_info['spread_est']
                                            if est_spread > adaptive['sl_pips'] * 0.25:
                                                logger.info(f"Spread gate: skipping news strategy, spread {est_spread:.1f}p > 25% of SL {adaptive['sl_pips']:.1f}p")
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
                                                conn = sqlite3.connect(DB_PATH)
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
                                                        sid = add_auto_strategy(
                                                            alert_id=row[0], news_title=title,
                                                            direction=direction, entry_price=price,
                                                            stop_loss=sl, take_profit=tp,
                                                            confidence=result.get('confidence', 50),
                                                            impact_score=result['impact_score'],
                                                            expiry_minutes=expiry_min)
                                                        if sid:
                                                            strategies_created += 1
                                                            cycle_signals.append({'source': 'news', 'direction': direction, 'confidence': result.get('confidence', 50)})
                                                            logger.info(f"Auto-strategy #{sid}: {direction} @ {price:.5f} SL={sl:.5f} TP={tp:.5f} [{adaptive.get('method','?')}]")
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

                    # ── Calendar Pre-News Trading: straddle before high-impact events ──
                    try:
                        from datetime import datetime as _cal_dt, timezone as _cal_tz, timedelta as _cal_td
                        from src.analyzer.trading_knowledge import get_entry_rules_summary

                        cal_resp = requests.get('http://localhost:8000/calendar', timeout=5)
                        if cal_resp.status_code == 200:
                            cal_json = cal_resp.json()
                            cal_events = cal_json if isinstance(cal_json, list) else cal_json.get('events', cal_json.get('data', []))
                            utc_now = _cal_dt.now(_cal_tz.utc)
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

                                    # Get market state
                                    ms = tech.get_market_state()
                                    price = ms.get('price', 0)
                                    support = ms.get('support', 0)
                                    resistance = ms.get('resistance', 0)
                                    if price <= 0 or support <= 0 or resistance <= 0:
                                        continue

                                    from src.common.db import get_active_profile
                                    profile = get_active_profile()

                                    # Confidence boost based on impact
                                    base_conf = profile.get('min_confidence', 60)
                                    if evt_impact == 'High':
                                        cal_conf_bonus = 15
                                    else:
                                        cal_conf_bonus = 5

                                    # Capture candles snapshot for chart
                                    cal_candles_snap = None
                                    try:
                                        raw_candles = tech._fetch_candles()
                                        if raw_candles:
                                            cal_candles_snap = [
                                                {'o': round(c['open'], 5), 'h': round(c['high'], 5),
                                                 'l': round(c['low'], 5), 'c': round(c['close'], 5),
                                                 't': c['datetime']}
                                                for c in raw_candles[-30:]
                                            ]
                                    except Exception:
                                        pass

                                    # STRADDLE: generate CALL above resistance and PUT below support
                                    straddle_sides = [
                                        {'direction': 'CALL', 'zone': resistance, 'label': f'CALL zona {resistance:.4f}'},
                                        {'direction': 'PUT',  'zone': support,    'label': f'PUT zona {support:.4f}'},
                                    ]

                                    for side in straddle_sides:
                                        direction = side['direction']
                                        conf = base_conf + cal_conf_bonus

                                        # Adaptive SL/TP
                                        adaptive = tech.compute_adaptive_sl_tp(direction, price, ms, profile)
                                        sl = adaptive['sl']
                                        tp = adaptive['tp']

                                        # Spread gate: skip if estimated spread > 25% of SL
                                        session_info = tech.get_session_info()
                                        est_spread = session_info['spread_est']
                                        if est_spread > adaptive['sl_pips'] * 0.25:
                                            logger.info(f"Spread gate: skipping calendar {direction}, spread {est_spread:.1f}p > 25% of SL {adaptive['sl_pips']:.1f}p")
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

                                        # Dedup: skip if similar calendar strategy exists
                                        if has_recent_similar_strategy(direction, entry_px, 'calendar', 60):
                                            logger.info(f"Dedup: skipping {direction} calendar near {entry_px:.5f}")
                                            continue

                                        # Anti-contradiction: skip if active opposite strategy
                                        opposite = has_active_opposite_strategy(direction)
                                        if opposite:
                                            logger.info(f"Anti-contradiction: skipping {direction} calendar, active #{opposite[0]} {opposite[1]}")
                                            continue

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
                                            expiry_minutes=expiry_min)
                                        if sid:
                                            strategies_created += 1
                                            cycle_signals.append({'source': 'calendar', 'direction': direction, 'confidence': conf})
                                            logger.info(f"Calendar strategy #{sid}: {direction} @ {entry_px:.5f} SL={sl:.5f} TP={tp:.5f} | {evt_name} in {minutes_until:.0f}min")

                                    # Mark this event as traded so we don't create duplicates next cycle
                                    _traded_calendar_events.add(evt_key)

                                except Exception as evt_err:
                                    logger.error(f"Calendar event processing error: {evt_err}")
                                    continue
                        else:
                            logger.debug(f"[{iteration}] Calendar endpoint returned {cal_resp.status_code}")
                    except requests.exceptions.ConnectionError:
                        logger.debug(f"[{iteration}] Calendar endpoint not available")
                    except Exception as e:
                        logger.error(f"Calendar pre-news error: {e}", exc_info=True)

                    # ── Structure scanner: generate strategies from market structure alone ──
                    try:
                        from src.common.db import get_active_profile
                        profile = get_active_profile()
                        prof_name = profile.get('name', 'default')
                        min_conf = profile.get('min_confidence', 60)
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

                        if not skip_session:
                            structure_signals = tech.detect_structure_signals(
                                min_confidence=min_conf)
                            logger.info(f"[{iteration}] Structure signals: {len(structure_signals)}")

                            # AutoTuner: block setup types with poor win rates
                            before_block = len(structure_signals)
                            structure_signals = [s for s in structure_signals
                                                 if not tuner.is_setup_blocked(s.get('setup_type', ''))]
                            tuner_blocked = before_block - len(structure_signals)
                            if tuner_blocked > 0:
                                logger.info(f"[{iteration}] AutoTuner blocked {tuner_blocked} low-WR setup(s)")

                            prof_sl = profile.get('stop_loss_pips', 5)
                            prof_tp = profile.get('take_profit_pips', 10)

                            # HTF bias filter: block counter-trend signals when bias is strong
                            htf_bias = None
                            try:
                                if smc:
                                    smc_status = smc.get_status()
                                    htf_bias = smc_status.get('htf_bias', None)
                            except Exception:
                                htf_bias = None

                            if htf_bias and htf_bias != 'neutral':
                                blocked_dir = 'CALL' if htf_bias == 'bearish' else 'PUT'
                                before_count = len(structure_signals)
                                structure_signals = [s for s in structure_signals if s['direction'] != blocked_dir]
                                blocked = before_count - len(structure_signals)
                                if blocked > 0:
                                    logger.info(f"[{iteration}] HTF bias {htf_bias}: blocked {blocked} {blocked_dir} signal(s)")

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

                            # Capture candles snapshot for frozen chart display
                            candles_snap = None
                            try:
                                raw_candles = tech._fetch_candles()
                                if raw_candles:
                                    candles_snap = [
                                        {'o': round(c['open'], 5), 'h': round(c['high'], 5),
                                         'l': round(c['low'], 5), 'c': round(c['close'], 5),
                                         't': c['datetime']}
                                        for c in raw_candles[-30:]
                                    ]
                            except Exception:
                                pass

                            for sig in structure_signals:
                                direction = sig['direction']
                                conf = sig['confidence']
                                ms = tech.get_market_state()
                                price = ms.get('price', 0)
                                if price <= 0:
                                    break

                                # Adaptive SL/TP based on ATR + structure levels
                                adaptive = tech.compute_adaptive_sl_tp(direction, price, ms, profile)
                                sl = adaptive['sl']
                                tp = adaptive['tp']

                                # Spread gate: skip if estimated spread > 25% of SL
                                session_info = tech.get_session_info()
                                est_spread = session_info['spread_est']
                                if est_spread > adaptive['sl_pips'] * 0.25:
                                    logger.info(f"Spread gate: skipping structure strategy, spread {est_spread:.1f}p > 25% of SL {adaptive['sl_pips']:.1f}p")
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

                                sid = add_auto_strategy(
                                    alert_id=None,
                                    news_title=f"[ESTRUCTURA] {sig['reason'][:80]}",
                                    direction=direction, entry_price=price,
                                    stop_loss=sl, take_profit=tp,
                                    confidence=conf, impact_score=min(struct_score, 100),
                                    trigger_type='structure',
                                    candles_snapshot=candles_snap,
                                    profile_name=prof_name,
                                    expiry_minutes=expiry_min)
                                if sid:
                                    strategies_created += 1
                                    cycle_signals.append({'source': 'structure', 'direction': direction, 'confidence': conf})
                                    logger.info(f"Structure strategy #{sid}: {direction} @ {price:.5f} | {sig['setup_type']} | {sig['reason'][:60]}")
                    except Exception as e:
                        logger.error(f"Structure scanner error: {e}", exc_info=True)

                    # ── SMC Scanner: multi-timeframe + demand/supply zones + confirmation ──
                    try:
                        smc.update()
                        smc_setups = smc.check_confirmations()
                        logger.info(f"[{iteration}] SMC setups: {len(smc_setups)}")
                        for setup in smc_setups:
                            direction = setup['direction']
                            conf = setup['confidence']
                            ms = tech.get_market_state()
                            price = ms.get('price', 0)
                            if price <= 0:
                                break

                            # Adaptive SL/TP
                            adaptive = tech.compute_adaptive_sl_tp(direction, price, ms, profile)
                            sl = adaptive['sl']
                            tp = adaptive['tp']

                            # Spread gate: skip if estimated spread > 25% of SL
                            session_info = tech.get_session_info()
                            est_spread = session_info['spread_est']
                            if est_spread > adaptive['sl_pips'] * 0.25:
                                logger.info(f"Spread gate: skipping SMC strategy, spread {est_spread:.1f}p > 25% of SL {adaptive['sl_pips']:.1f}p")
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
                            except Exception:
                                pass

                            # Source conflict resolution: adjust conf based on agreement/conflict with prior signals
                            for prior in cycle_signals:
                                if prior['direction'] == direction:
                                    conf = min(95, conf + 10)
                                    logger.info(f"Source agreement: SMC {direction} agrees with {prior['source']}, conf +10 → {conf}")
                                else:
                                    if conf <= prior['confidence']:
                                        conf = max(10, conf - 20)
                                        logger.info(f"Source conflict: SMC {direction} vs {prior['source']} {prior['direction']}, conf -20 → {conf}")

                            # Dedup: skip if similar SMC strategy exists
                            if has_recent_similar_strategy(direction, price, 'smc', 30):
                                logger.info(f"Dedup: skipping {direction} SMC near {price:.5f}")
                                continue

                            # Anti-contradiction: skip if active opposite strategy
                            opposite = has_active_opposite_strategy(direction)
                            if opposite:
                                logger.info(f"Anti-contradiction: skipping {direction} SMC, active #{opposite[0]} {opposite[1]}")
                                continue

                            sid = add_auto_strategy(
                                alert_id=None,
                                news_title=f"[SMC] {setup['reason'][:80]}",
                                direction=direction, entry_price=price,
                                stop_loss=sl, take_profit=tp,
                                confidence=conf, impact_score=smc_impact,
                                trigger_type='smc',
                                expiry_minutes=expiry_min)
                            if sid:
                                strategies_created += 1
                                cycle_signals.append({'source': 'smc', 'direction': direction, 'confidence': conf})
                                logger.info(f"SMC strategy #{sid}: {direction} @ {price:.5f} | {setup['reason'][:60]}")
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
                            _conn.execute("""
                                UPDATE auto_strategies SET status = 'expired'
                                WHERE expires_at < ? AND status = 'active'
                            """, (now_ar(),))
                            _conn.commit()
                            _conn.close()
                        except Exception:
                            pass
                        pending = get_strategies_pending_evaluation()
                        if pending:
                            candles = tech._fetch_candles()
                            current_price = tech.get_market_state().get('price', 0)

                            for row in pending:
                                sid, direction, entry_price, sl, tp = row[0], row[1], row[2], row[3], row[4]
                                conf, expiry_min = row[5], row[6]
                                created_at_str, expires_at_str = row[7], row[8]
                                news_title, trigger_type = row[9], row[10]

                                if not current_price or not entry_price:
                                    continue

                                # Check if TP or SL was hit using candle history (with Break Even logic)
                                hit_tp = False
                                hit_sl = False
                                hit_be = False
                                # Break Even: 1:1 R:R distance from entry
                                sl_distance = abs(entry_price - sl)
                                be_target = (entry_price + sl_distance) if direction == 'CALL' else (entry_price - sl_distance)
                                be_triggered = False

                                if candles:
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

                                            # Check if 1:1 R:R was reached (BE trigger)
                                            if not be_triggered:
                                                if direction == 'CALL' and c['high'] >= be_target:
                                                    be_triggered = True
                                                elif direction == 'PUT' and c['low'] <= be_target:
                                                    be_triggered = True

                                            # Check highs/lows against TP/SL (with BE-adjusted SL)
                                            if direction == 'CALL':
                                                if c['high'] >= tp:
                                                    hit_tp = True
                                                    break
                                                effective_sl = entry_price if be_triggered else sl
                                                if c['low'] <= effective_sl:
                                                    if be_triggered:
                                                        hit_be = True
                                                    else:
                                                        hit_sl = True
                                                    break
                                            else:  # PUT
                                                if c['low'] <= tp:
                                                    hit_tp = True
                                                    break
                                                effective_sl = entry_price if be_triggered else sl
                                                if c['high'] >= effective_sl:
                                                    if be_triggered:
                                                        hit_be = True
                                                    else:
                                                        hit_sl = True
                                                    break

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
                                elif hit_be:
                                    result = 'break_even'
                                    pips_result = 0.0
                                elif hit_sl:
                                    result = 'loss'
                                    pips_result = -(abs(sl - entry_price) / pip + est_spread)
                                else:
                                    # Neither TP nor SL hit — evaluate by direction
                                    if direction == 'CALL':
                                        pips_result = (current_price - entry_price) / pip - est_spread
                                    else:
                                        pips_result = (entry_price - current_price) / pip - est_spread
                                    # AutoTuner: require minimum pip movement to count as win
                                    min_pips = tuner.get_params().get('min_pips_for_win', 1.5)
                                    if be_triggered and pips_result < min_pips:
                                        result = 'break_even'
                                        pips_result = 0.0
                                    else:
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
                                auto_evaluate_strategy(sid, result, exit_px, round(pips_result, 1), ctx)
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
                                for arow in pending_alerts:
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
                                    })
                                    logger.info(f"Alert eval #{aid}: {a_result.upper()} | {a_dir} entry={a_entry:.5f} exit={current_price:.5f} | {pips_move:+.1f}p | {a_title[:50]}")
                                logger.info(f"Evaluated {len(pending_alerts)} pending news alerts")
                    except Exception as e:
                        logger.error(f"Alert auto-eval error: {e}", exc_info=True)

                except Exception as e:
                    logger.error(f"Analyzer error: {e}")

                time.sleep(Config.ANALYZER_INTERVAL)
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
    
    def start_services(self):
        """Iniciar los 3 servicios como threads"""
        self.log("🚀 Iniciando servicios integrados...", "blue")
        
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
        self.root.title("AIdan v3.0")
        self.root.geometry(f"{W}x{H}")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        self.root.overrideredirect(True)
        self._anim_running = True
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
            231, 37, text="v3.0", font=("Segoe UI", 11, "bold"),
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

        step_names = ["Ollama Engine", "Modelo IA", "Modelo Vision", "Servicios", "Dashboard"]
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
        self._progress_total = 5
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
            # 1. Ollama
            self._mark_step_active(0)
            self.log("Verificando Ollama...", "blue")
            if not self.check_ollama_installed():
                response = _ask_yesno_safe(
                    "Ollama no instalado",
                    "AIdan necesita Ollama (motor de IA local).\n\n"
                    "Descargar e instalar Ollama ahora?\n"
                    "(Descarga ~400MB, instalacion ~5 minutos)"
                )
                if response:
                    if not self.install_ollama():
                        self.log("Ollama: error de instalacion", "red")
                        self._mark_step_error(0)
                        return
                else:
                    self.log("Ollama es necesario para AIdan", "red")
                    self._mark_step_error(0)
                    return
            self.log("Ollama listo", "green")
            self._advance_progress(step_index=0)

            # 2. Modelo IA
            self._mark_step_active(1)
            self.log(f"Verificando modelo {OLLAMA_MODEL}...", "blue")
            if not self.check_ollama_model():
                response = _ask_yesno_safe(
                    "Modelo no instalado",
                    f"Se necesita descargar el modelo {OLLAMA_MODEL}\n"
                    f"Tamano: ~4GB\n\nDescargar ahora?"
                )
                if response:
                    if not self.install_ollama_model():
                        self.log("Error instalando modelo", "red")
                        self._mark_step_error(1)
                        return
                else:
                    self.log("Sin modelo, analisis limitado", "orange")
            self.log(f"Modelo {OLLAMA_MODEL} listo", "green")
            self._advance_progress(step_index=1)

            # 3. Vision
            self._mark_step_active(2)
            self.log("Verificando modelo de vision (llava)...", "blue")
            if not self.check_vision_model():
                self.log("Descargando llava (analisis de graficos)...", "blue")
                self.install_vision_model()
            self.log("Modelo de vision listo", "green")
            self._advance_progress(step_index=2)

            # 4. Servicios
            self._mark_step_active(3)
            if self.start_services():
                self._advance_progress(step_index=3)
                # 5. Dashboard
                self._mark_step_active(4)
                self.open_dashboard()
                self._advance_progress(step_index=4)
                self._anim_running = False
                self.log("AIdan activo — dashboard abierto", "green")

        Thread(target=init_thread, daemon=True).start()
        # Start strategy watcher (polls /auto-strategies, fires toast on new ones)
        _launch_strategy_watcher(self.root)
        self.root.mainloop()


if __name__ == "__main__":
    aidan = AIdan()
    aidan.run()
