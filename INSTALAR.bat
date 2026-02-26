@echo off
chcp 65001 > nul
title Instalando dependencias de AIdan
color 0B

echo.
echo ════════════════════════════════════════════════════════════════
echo    📦 INSTALANDO DEPENDENCIAS DE AIDAN v1.1
echo ════════════════════════════════════════════════════════════════
echo.
echo Por favor espera, esto puede tardar 2-3 minutos...
echo.

cd /d %~dp0

echo [1/2] 🔍 Verificando Python...
python --version
if errorlevel 1 (
    echo.
    echo ❌ ERROR: Python no está instalado o no está en el PATH
    echo.
    echo Por favor:
    echo 1. Instala Python desde https://www.python.org/downloads/
    echo 2. Marca la casilla "Add Python to PATH" durante la instalación
    echo 3. Reinicia tu computadora
    echo 4. Vuelve a ejecutar este archivo
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] 📥 Instalando librerías Python...
python -m pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ❌ ERROR durante la instalación
    echo.
    echo Intenta ejecutar como Administrador:
    echo 1. Click derecho en INSTALAR.bat
    echo 2. Selecciona "Ejecutar como administrador"
    echo.
    pause
    exit /b 1
)

echo.
echo ════════════════════════════════════════════════════════════════
echo    ✅ INSTALACIÓN COMPLETADA
echo ════════════════════════════════════════════════════════════════
echo.
echo Ya puedes usar AIdan!
echo.
echo Para iniciar el sistema:
echo   → Haz doble click en: start_system.bat
echo.
echo Para detenerlo:
echo   → Haz doble click en: stop_system.bat
echo.
pause
