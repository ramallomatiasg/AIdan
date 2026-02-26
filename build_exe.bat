@echo off
chcp 65001 > nul
title AIdan - Compilador a Ejecutables
color 0B

echo.
echo ════════════════════════════════════════════════════════════════
echo    🔨 COMPILANDO SISTEMA A EJECUTABLES (.EXE)
echo ════════════════════════════════════════════════════════════════
echo.

cd /d F:\AIdan

echo [1/4] 📦 Instalando PyInstaller...
python -m pip install pyinstaller --quiet
timeout /t 2 /nobreak > nul

echo [2/5] ⚙️ Compilando versión DESKTOP (Todo-en-Uno)...
pyinstaller --onefile ^
    --name "AIdan_Desktop" ^
    --add-data "dashboard_retro.html;." ^
    --add-data "about.html;." ^
    --add-data "config;config" ^
    --add-data "static;static" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import webview ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --collect-all webview ^
    --noconsole ^
    --icon=NONE ^
    run_desktop.py

echo [3/5] ⚙️ Compilando Admin API (Dashboard)...
pyinstaller --onefile ^
    --name "AIdan_Admin" ^
    --add-data "dashboard.html;." ^
    --add-data "config;config" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --noconsole ^
    src\admin\main.py

echo [3/5] ⚙️ Compilando Admin API (Dashboard)...
pyinstaller --onefile ^
    --name "AIdan_Admin" ^
    --add-data "dashboard_retro.html;." ^
    --add-data "about.html;." ^
    --add-data "config;config" ^
    --add-data "static;static" ^
    --hi5] 📡 Compilando Collector (RSS Feed)...
pyinstaller --onefile ^
    --name "AIdan_Collector" ^
    --add-data "config;config" ^
    --noconsole ^
    src\collector\main.py

echo [5/5den-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --noconsole ^
    src\admin\main.py

echo [4/5] 📡 Compilando Collector (RSS Feed)...
pyinstaller --onefile ^
    --name "AIdan_Collector" ^
    --add-data "config;config" ^
    --noconsole ^
    src\collector\main.py

echo [4/4] 🔍 Compilando Analyzer (EUR/USD Analysis)...
pyinstaller --onefile ^
    --name "AIdan_Analyzer" ^
    --add-data "config;config" ^
    --noconsole Desktop.exe        ⭐ (TODO-EN-UNO - Recomendado)
echo    - AIdan_Admin.exe
echo    - AIdan_Collector.exe
echo    - AIdan_Analyzer.exe
echo.
echo 📦 Para distribuir, copia:
echo    📌 OPCIÓN FÁCIL (recomendada):
echo       - AIdan_Desktop.exe      (solo este archivo)
echo       - Carpeta config\
echo       - Carpeta static\
echo.
echo    📌 OPCIÓN AVANZADA (3 servicios separados):
echo       - Carpeta dist\ (con los 3 .exe separados)
echo       - Carpeta config\
echo       - Carpeta static\
echo       - AIdan_Analyzer.exe
echo.
echo 📦 Para distribuir, copia:
echo    - Carpeta dist\ (con los .exe)
echo    - Carpeta config\ (con sources.yaml)
echo    - Carpeta state\ (se creará automáticamente)
echo    - Archivo dashboard.html
echo    - Archivo start_system_portable.bat
echo.
echo ⚠️ IMPORTANTE: Cada usuario necesita configurar sus propias API keys
echo.

pause
