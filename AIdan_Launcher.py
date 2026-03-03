"""
AIdan Launcher - Ejecutable maestro que lo hace TODO
- Verifica/instala Ollama automáticamente
- Levanta todos los servicios
- Abre el dashboard
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

# Configuración
OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_API = "http://localhost:11434/api/tags"
OLLAMA_MODEL = "llama3.1:8b"
DASHBOARD_URL = "http://localhost:8000"

class AIdan:
    def __init__(self):
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
                    pass
            winreg.CloseKey(key)
        except:
            pass
        
        # Verificar si el servicio responde
        try:
            response = requests.get(OLLAMA_API, timeout=2)
            return response.status_code == 200
        except:
            pass
        
        return False
    
    def download_ollama(self):
        """Descargar e instalar Ollama"""
        self.log("📥 Descargando Ollama...", "blue")
        
        temp_path = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        
        try:
            # Descargar instalador
            urllib.request.urlretrieve(OLLAMA_URL, temp_path)
            self.log("✓ Descarga completa", "green")
            
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
    
    def start_services(self):
        """Iniciar los servicios de AIdan embebidos"""
        self.log("🚀 Iniciando servicios...", "blue")
        
        # Iniciar todo en threads separados para evitar bloqueos
        from threading import Thread
        import uvicorn
        
        def run_collector():
            """Ejecutar collector en background"""
            try:
                from src.collector.main import main as collector_main
                collector_main()
            except Exception as e:
                self.log(f"Error en Collector: {e}", "red")
        
        def run_analyzer():
            """Ejecutar analyzer en background"""
            try:
                from src.analyzer.main import main as analyzer_main
                analyzer_main()
            except Exception as e:
                self.log(f"Error en Analyzer: {e}", "red")
        
        def run_api():
            """Ejecutar API del dashboard"""
            try:
                from src.admin.main import app
                config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="error")
                server = uvicorn.Server(config)
                server.run()
            except Exception as e:
                self.log(f"Error en API: {e}", "red")
        
        # Iniciar servicios en threads
        self.log("📰 Iniciando Collector (noticias)...", "blue")
        collector_thread = Thread(target=run_collector, daemon=True)
        collector_thread.start()
        time.sleep(2)
        
        self.log("🧠 Iniciando Analyzer (IA)...", "blue")
        analyzer_thread = Thread(target=run_analyzer, daemon=True)
        analyzer_thread.start()
        time.sleep(2)
        
        self.log("🖥️ Iniciando Dashboard API...", "blue")
        api_thread = Thread(target=run_api, daemon=True)
        api_thread.start()
        
        # Esperar a que el servidor esté listo
        self.log("⏳ Esperando que el dashboard esté listo...", "blue")
        for i in range(30):
            try:
                response = requests.get(f"{DASHBOARD_URL}/health", timeout=2)
                if response.status_code == 200:
                    self.log("✓ Dashboard listo", "green")
                    return True
            except:
                time.sleep(1)
        
        messagebox.showerror("Error", "El dashboard no inició correctamente")
        return False
    
    def open_dashboard(self):
        """Abrir el dashboard en el navegador"""
        self.log("🌐 Abriendo dashboard...", "blue")
        webbrowser.open(DASHBOARD_URL)
        time.sleep(2)
        self.log("✅ AIdan está corriendo!", "green")
    
    def cleanup(self):
        """Cerrar al salir - los threads daemon se cierran automáticamente"""
        self.log("🛑 Cerrando AIdan...", "orange")
        # Los threads daemon se cierran automáticamente al cerrar la app
    
    def run_setup_steps(self):
        """Ejecutar todos los pasos de configuración"""
        # Paso 1: Verificar/instalar Ollama
        self.log("🔍 Verificando Ollama...", "blue")
        if not self.check_ollama_installed():
            response = messagebox.askyesno(
                "Ollama requerido",
                "AIdan necesita Ollama (IA local gratis) para funcionar.\n\n"
                "¿Descargar e instalar ahora? (4GB)"
            )
            if response:
                if not self.download_ollama():
                    return False
            else:
                messagebox.showinfo("Info", "AIdan no puede funcionar sin Ollama.")
                return False
        else:
            self.log("✓ Ollama instalado", "green")
        
        # Paso 2: Verificar/instalar modelo
        self.log("🔍 Verificando modelo IA...", "blue")
        if not self.check_ollama_model():
            response = messagebox.askyesno(
                "Modelo de IA requerido",
                f"Se necesita descargar el modelo {OLLAMA_MODEL} (4GB).\n\n"
                "¿Descargar ahora?"
            )
            if response:
                if not self.install_ollama_model():
                    return False
            else:
                messagebox.showwarning("Advertencia", 
                    "Sin el modelo, AIdan funcionará con capacidades limitadas.")
        else:
            self.log("✓ Modelo IA instalado", "green")
        
        # Paso 3: Iniciar servicios
        if not self.start_services():
            return False
        
        # Paso 4: Abrir dashboard
        self.open_dashboard()
        
        return True
    
    def create_gui(self):
        """Crear ventana de estado"""
        self.root = tk.Tk()
        self.root.title("AIdan Launcher")
        self.root.geometry("500x300")
        self.root.resizable(False, False)
        
        # Logo/Título
        title = tk.Label(
            self.root, 
            text="💱 AIdan v1.1",
            font=("Arial", 24, "bold"),
            fg="#2196F3"
        )
        title.pack(pady=20)
        
        # Estado
        self.status_label = tk.Label(
            self.root,
            text="Iniciando...",
            font=("Arial", 12),
            fg="black"
        )
        self.status_label.pack(pady=20)
        
        # Botón cerrar
        def on_close():
            self.cleanup()
            self.root.destroy()
        
        close_btn = tk.Button(
            self.root,
            text="Cerrar AIdan",
            command=on_close,
            font=("Arial", 12),
            bg="#f44336",
            fg="white",
            padx=20,
            pady=10
        )
        close_btn.pack(pady=20)
        
        # Instrucciones
        info = tk.Label(
            self.root,
            text="Mantén esta ventana abierta mientras usas AIdan.\n"
                 "El dashboard se abrirá automáticamente en tu navegador.",
            font=("Arial", 9),
            fg="gray"
        )
        info.pack(pady=10)
        
        self.root.protocol("WM_DELETE_WINDOW", on_close)
        
        # Ejecutar setup en hilo separado
        def run_async():
            success = self.run_setup_steps()
            if not success:
                self.cleanup()
                self.root.destroy()
        
        Thread(target=run_async, daemon=True).start()
        
        self.root.mainloop()

def main():
    """Punto de entrada principal"""
    aidan = AIdan()
    aidan.create_gui()

if __name__ == "__main__":
    main()
