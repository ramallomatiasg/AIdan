@echo off
chcp 65001 > nul
title AIdan - Compilador a Ejecutables
color 0B

echo.
echo ════════════════════════════════════════════════════════════════
echo    🔨 COMPILANDO AIDAN A EJECUTABLES
echo ════════════════════════════════════════════════════════════════
echo.

cd /d F:\AIdan

echo [1/5] 📦 Instalando PyInstaller...
python -m pip install pyinstaller --quiet --upgrade
timeout /t 2 /nobreak > nul

echo [2/5] ⚙️ Compilando AIdan_Desktop.exe (Todo-en-Uno)...
pyinstaller --onefile ^
    --name "AIdan_Desktop" ^
    --add-data "dashboard_retro.html;." ^
    --add-data "about.html;." ^
    --add-data "config;config" ^
    --add-data "static;static" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import webview ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --collect-all webview ^
    --noconsole ^
    run_desktop.py

echo [3/5] ⚙️ Compilando AIdan_Admin.exe (API)...
pyinstaller --onefile ^
    --name "AIdan_Admin" ^
    --add-data "dashboard_retro.html;." ^
    --add-data "about.html;." ^
    --add-data "static;static" ^
    --add-data "config;config" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan.on ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --noconsole ^
    src\admin\main.py

echo [4/5] 📡 Compilando AIdan_Collector.exe (RSS)...
pyinstaller --onefile ^
    --name "AIdan_Collector" ^
    --add-data "config;config" ^
    --noconsole ^
    src\collector\main.py

echo [5/5] 🔍 Compilando AIdan_Analyzer.exe (Análisis)...
pyinstaller --onefile ^
    --name "AIdan_Analyzer" ^
    --add-data "config;config" ^
    --noconsole ^
    src\analyzer\main.py

echo.
echo ════════════════════════════════════════════════════════════════
echo    ✅ COMPILACIÓN COMPLETA
echo ════════════════════════════════════════════════════════════════
echo.
echo 📁 Ejecutables creados en: dist\
echo    - AIdan_Desktop.exe    ⭐ (TODO-EN-UNO - Recomendado)
echo    - AIdan_Admin.exe
echo    - AIdan_Collector.exe
echo    - AIdan_Analyzer.exe
echo.
echo 📦 PARA DISTRIBUIR:
echo    1. Copia AIdan_Desktop.exe
echo    2. Copia carpeta config\
echo    3. Copia carpeta static\
echo    4. ¡Listo!
echo.

pause
