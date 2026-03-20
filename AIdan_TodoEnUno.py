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

# Add src to path ANTES de cualquier import local
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configuración
OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_API = "http://localhost:11434/api/tags"
OLLAMA_MODEL = "llama3.1:8b"
DASHBOARD_URL = "http://localhost:8000"

class AIdan:
    def __init__(self):
        self.threads = []
        self.root = None
        self.status_label = None
        
    def log(self, message, color="black"):
        """Mostrar mensaje en la GUI"""
        if self.status_label:
            self.status_label.config(text=message, fg=color)
            self.root.update()
        print(message)
    
    def check_ollama_installed(self):
        """Verificar si Ollama está instalado"""
        try:
            # Verificar en registro de Windows
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
            for i in range(0, winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    if "ollama" in name.lower():
                        winreg.CloseKey(subkey)
                        winreg.CloseKey(key)
                        return True
                    winreg.CloseKey(subkey)
                except:
                    continue
            winreg.CloseKey(key)
        except:
            pass
        
        # Verificar si el servicio responde
        try:
            response = requests.get(OLLAMA_API, timeout=3)
            return response.status_code == 200
        except:
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
                                   item['language'], str(item['entities']), str(item['tags'])):
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
                                       add_alert, add_auto_strategy, get_news_fetch_time)
            from src.analyzer.news_analyzer import NewsAnalyzer
            from src.analyzer.technical import TechnicalAnalyzer
            
            logger = setup_logging("analyzer", Config.LOG_LEVEL)
            logger.info("Initializing analyzer...")
            init_db()
            
            analyzer = NewsAnalyzer(logger)
            tech = TechnicalAnalyzer(logger)
            logger.info("Analyzer ready")
            
            iteration = 0
            while True:
                try:
                    iteration += 1
                    news_items = get_unprocessed_news()
                    
                    alerts_sent = 0
                    strategies_created = 0
                    for news_id, url, title, summary, entities, tags in news_items:
                        result = analyzer.analyze(news_id, title, summary, entities, tags)

                        if result and result['should_alert']:
                            add_alert(news_id, result['impact_score'], result['level'],
                                    result['explanation'], result['eur_usd_impact'],
                                    result['market_implications'],
                                    result.get('analysis_method', 'keywords'),
                                    result.get('should_operate', False),
                                    result.get('direction', 'NEUTRAL'),
                                    result.get('confidence', 50))
                            alerts_sent += 1

                            # Auto-strategy: use active profile params + fresh news (<10 min)
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

                            if score_ok and conf_ok and dir_ok and direction != 'NEUTRAL':
                                try:
                                    from datetime import datetime as dt
                                    fetch_ts = get_news_fetch_time(news_id)
                                    is_fresh = True
                                    if fetch_ts:
                                        fetch_time = dt.strptime(str(fetch_ts).split('.')[0], '%Y-%m-%d %H:%M:%S')
                                        from datetime import timezone, timedelta as td
                                        ar_tz = timezone(td(hours=-3))
                                        age_min = (dt.now(ar_tz).replace(tzinfo=None) - fetch_time).total_seconds() / 60
                                        is_fresh = age_min <= 10
                                        if not is_fresh:
                                            logger.info(f"Skip auto-strategy: news {age_min:.0f}min old (max 10)")

                                    if is_fresh:
                                        market = tech.get_market_state()
                                        price = market.get('price', 0)
                                        if price > 0:
                                            pip = 0.0001
                                            if direction == 'CALL':
                                                sl = round(price - prof_sl * pip, 5)
                                                tp = round(price + prof_tp * pip, 5)
                                            else:  # PUT
                                                sl = round(price + prof_sl * pip, 5)
                                                tp = round(price - prof_tp * pip, 5)

                                            # Get alert_id from DB (last inserted)
                                            import sqlite3
                                            from src.common.db import DB_PATH
                                            conn = sqlite3.connect(DB_PATH)
                                            c = conn.cursor()
                                            c.execute("SELECT id FROM alerts WHERE news_id=? ORDER BY id DESC LIMIT 1", (news_id,))
                                            row = c.fetchone()
                                            conn.close()
                                            if row:
                                                sid = add_auto_strategy(
                                                    alert_id=row[0], news_title=title,
                                                    direction=direction, entry_price=price,
                                                    stop_loss=sl, take_profit=tp,
                                                    confidence=result.get('confidence', 50),
                                                    impact_score=result['impact_score'])
                                                if sid:
                                                    strategies_created += 1
                                                    logger.info(f"Auto-strategy #{sid}: {direction} @ {price:.5f} SL={sl:.5f} TP={tp:.5f}")
                                except Exception as e:
                                    logger.error(f"Auto-strategy error: {e}")

                        mark_news_processed(news_id)

                    if alerts_sent > 0 or strategies_created > 0:
                        logger.info(f"[{iteration}] Alerts: {alerts_sent} | Strategies: {strategies_created}")

                    # ── Structure scanner: generate strategies from market structure alone ──
                    try:
                        from src.common.db import get_active_profile
                        profile = get_active_profile()
                        structure_signals = tech.detect_structure_signals(
                            min_confidence=profile.get('min_confidence', 60))
                        prof_sl = profile.get('stop_loss_pips', 5)
                        prof_tp = profile.get('take_profit_pips', 10)

                        for sig in structure_signals:
                            direction = sig['direction']
                            conf = sig['confidence']
                            price = tech.get_market_state().get('price', 0)
                            if price <= 0:
                                break
                            pip = 0.0001
                            if direction == 'CALL':
                                sl = round(price - prof_sl * pip, 5)
                                tp = round(price + prof_tp * pip, 5)
                            else:
                                sl = round(price + prof_sl * pip, 5)
                                tp = round(price - prof_tp * pip, 5)

                            sid = add_auto_strategy(
                                alert_id=None,
                                news_title=f"[ESTRUCTURA] {sig['reason'][:80]}",
                                direction=direction, entry_price=price,
                                stop_loss=sl, take_profit=tp,
                                confidence=conf, impact_score=int(conf),
                                trigger_type='structure')
                            if sid:
                                strategies_created += 1
                                logger.info(f"Structure strategy #{sid}: {direction} @ {price:.5f} | {sig['setup_type']} | {sig['reason'][:60]}")
                    except Exception as e:
                        logger.error(f"Structure scanner error: {e}")

                except Exception as e:
                    logger.error(f"Analyzer error: {e}")

                time.sleep(Config.ANALYZER_INTERVAL)
        except Exception as e:
            print(f"FATAL Analyzer: {e}")
    
    def run_api_service(self):
        """Servicio API integrado"""
        try:
            import uvicorn
            from src.admin.main import app
            
            # Configuración para ejecutable
            config = uvicorn.Config(
                app, 
                host="127.0.0.1", 
                port=8000,
                log_level="error",
                access_log=False,
                loop="asyncio"
            )
            server = uvicorn.Server(config)
            server.run()
        except Exception as e:
            print(f"FATAL API: {e}")
            import traceback
            traceback.print_exc()
    
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
    
    def run(self):
        """Flujo principal"""
        # Crear GUI
        self.root = tk.Tk()
        self.root.title("AIdan Launcher")
        self.root.geometry("500x300")
        self.root.resizable(False, False)
        
        # Título
        title_label = tk.Label(self.root, text="🚀 AIdan v1.2", 
                              font=("Arial", 24, "bold"), fg="#2196F3")
        title_label.pack(pady=20)
        
        # Estado
        self.status_label = tk.Label(self.root, text="Iniciando...", 
                                     font=("Arial", 11), wraplength=450)
        self.status_label.pack(pady=20)
        
        # Botón cerrar
        close_button = tk.Button(self.root, text="Cerrar AIdan", 
                                command=self.root.destroy, bg="#f44336", fg="white",
                                font=("Arial", 12, "bold"), width=15, height=2)
        close_button.pack(pady=20)
        
        # Info
        info_label = tk.Label(self.root, 
                            text="Mantén esta ventana abierta mientras usas AIdan.\n"
                                 "El dashboard se abrirá automáticamente en tu navegador.",
                            font=("Arial", 9), fg="gray")
        info_label.pack(pady=10)
        
        # Iniciar verificación en thread
        def init_thread():
            # 1. Verificar Ollama
            self.log("🔍 Verificando Ollama...", "blue")
            if not self.check_ollama_installed():
                response = messagebox.askyesno(
                    "Ollama no instalado",
                    "AIdan necesita Ollama (motor de IA local).\n\n"
                    "¿Descargar e instalar Ollama ahora?\n"
                    "(Descarga ~400MB, instalación ~5 minutos)"
                )
                if response:
                    if not self.install_ollama():
                        self.log("❌ No se pudo instalar Ollama", "red")
                        return
                else:
                    self.log("❌ Ollama es necesario para AIdan", "red")
                    return
            else:
                self.log("✓ Ollama instalado", "green")
            
            # 2. Verificar modelo
            self.log(f"🔍 Verificando modelo {OLLAMA_MODEL}...", "blue")
            if not self.check_ollama_model():
                response = messagebox.askyesno(
                    "Modelo no instalado",
                    f"Se necesita descargar el modelo {OLLAMA_MODEL}\n"
                    f"Tamaño: ~4GB\n\n"
                    "¿Descargar ahora?"
                )
                if response:
                    if not self.install_ollama_model():
                        self.log("❌ No se pudo instalar el modelo", "red")
                        return
                else:
                    self.log("⚠️ Sin modelo, análisis limitado", "orange")
            else:
                self.log(f"✓ Modelo {OLLAMA_MODEL} listo", "green")
            
            # 3. Verificar modelo de visión (llava) para análisis de gráficos
            self.log("🔍 Verificando modelo de visión (llava)...", "blue")
            if not self.check_vision_model():
                self.log("📦 Descargando llava (análisis de gráficos)...", "blue")
                self.install_vision_model()
            else:
                self.log("✓ Modelo de visión listo", "green")

            # 4. Iniciar servicios
            if self.start_services():
                # 5. Abrir dashboard
                self.open_dashboard()
        
        # Ejecutar init en background
        Thread(target=init_thread, daemon=True).start()
        
        # Mantener ventana abierta
        self.root.mainloop()

if __name__ == "__main__":
    aidan = AIdan()
    aidan.run()
