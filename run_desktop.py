import webview
import threading
import time
import sys
import os
from multiprocessing import Process

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def start_collector():
    """Iniciar Collector en segundo plano"""
    from src.collector.main import main as collector_main
    collector_main()

def start_analyzer():
    """Iniciar Analyzer en segundo plano"""
    from src.analyzer.main import main as analyzer_main
    analyzer_main()

def start_api():
    """Iniciar FastAPI server"""
    import uvicorn
    from src.admin.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

def check_server_ready(max_attempts=15):
    """Esperar a que el servidor esté listo"""
    import urllib.request
    for i in range(max_attempts):
        try:
            urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1)
            return True
        except:
            time.sleep(1)
    return False

if __name__ == '__main__':
    print("🚀 Iniciando AIdan v1.1...")
    
    # Iniciar servicios en procesos separados
    print("📡 Iniciando Collector...")
    collector_process = Process(target=start_collector, daemon=True)
    collector_process.start()
    
    print("🔍 Iniciando Analyzer...")
    analyzer_process = Process(target=start_analyzer, daemon=True)
    analyzer_process.start()
    
    print("🌐 Iniciando API...")
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    
    # Esperar a que el servidor esté listo
    print("⏳ Esperando a que el servidor inicie...")
    if check_server_ready():
        print("✅ Servidor listo!")
        print("🖥️ Abriendo dashboard...")
        
        # Crear ventana desktop
        webview.create_window(
            '💱 AIdan v1.1 - Trading EUR/USD',
            'http://127.0.0.1:8000',
            width=1400,
            height=900,
            resizable=True,
            fullscreen=False,
            min_size=(800, 600)
        )
        webview.start()
    else:
        print("❌ Error: No se pudo iniciar el servidor")
        input("Presiona Enter para salir...")
