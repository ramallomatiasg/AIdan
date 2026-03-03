@echo off
chcp 65001 > nul
title AIdan - Compilador Universal
color 0B

echo.
echo ════════════════════════════════════════════════════════════════
echo    🔨 COMPILANDO AIDAN LAUNCHER (Todo-en-Uno)
echo ════════════════════════════════════════════════════════════════
echo.

cd /d F:\AIdan

echo [1/3] 📦 Instalando PyInstaller...
python -m pip install pyinstaller --quiet --upgrade
timeout /t 2 /nobreak > nul

echo [2/3] ⚙️ Compilando AIdan_Launcher.exe...
pyinstaller --onefile ^
    --name "AIdan_Launcher" ^
    --add-data "dashboard_multi_theme.html;." ^
    --add-data "dashboard_retro.html;." ^
    --add-data "about.html;." ^
    --add-data "config;config" ^
    --add-data "static;static" ^
    --add-data "src;src" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import tkinter ^
    --hidden-import winreg ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --collect-all feedparser ^
    --collect-all requests ^
    --windowed ^
    AIdan_Launcher.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Error en la compilación
    pause
    exit /b 1
)

echo.
echo [3/3] 🧹 Limpiando archivos temporales...
if exist "build" rmdir /s /q "build"
if exist "AIdan_Launcher.spec" del /f "AIdan_Launcher.spec"

echo.
echo ════════════════════════════════════════════════════════════════
echo    ✅ COMPILACIÓN COMPLETA
echo ════════════════════════════════════════════════════════════════
echo.
echo    📦 Ejecutable: dist\AIdan_Launcher.exe
echo    📄 Archivos necesarios para distribuir:
echo       - dist\AIdan_Launcher.exe
echo       - config\sources.yaml
echo       - static\ (carpeta completa)
echo       - LEEME.txt
echo.
echo    ⚠️  El usuario final NO necesita Python instalado
echo    ⚠️  El usuario SÍ necesita instalar Ollama (lo hace automático)
echo.
pause
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
