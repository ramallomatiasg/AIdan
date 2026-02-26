@echo off
chcp 65001 > nul
title Financial News Monitor - Sistema Portable
color 0A

echo.
echo ════════════════════════════════════════════════════════════════
echo    💱 FINANCIAL NEWS MONITOR - EUR/USD TRADING SIGNALS
echo    📦 VERSIÓN PORTABLE (No requiere Python)
echo ════════════════════════════════════════════════════════════════
echo.

cd /d %~dp0

REM Verificar que existen los ejecutables
if not exist "dist\AIdan_Admin.exe" (
    echo ❌ ERROR: No se encontraron los ejecutables
    echo.
    echo Por favor, ejecuta primero build_exe.bat para compilar el sistema
    echo.
    pause
    exit /b 1
)

echo [1/4] 🛑 Cerrando procesos previos...
taskkill /F /IM AIdan_Admin.exe 2>nul
taskkill /F /IM AIdan_Collector.exe 2>nul
taskkill /F /IM AIdan_Analyzer.exe 2>nul
timeout /t 2 /nobreak > nul

echo [2/4] 📡 Iniciando Collector (noticias RSS)...
start "Collector - News Feed" /MIN cmd /k "cd /d %~dp0 && echo Collector iniciado... && dist\AIdan_Collector.exe"
timeout /t 3 /nobreak > nul

echo [3/4] 🔍 Iniciando Analyzer (análisis EUR/USD)...
start "Analyzer - EUR/USD Analysis" /MIN cmd /k "cd /d %~dp0 && echo Analyzer iniciado... && dist\AIdan_Analyzer.exe"
timeout /t 3 /nobreak > nul

echo [4/4] 🌐 Iniciando Admin API (dashboard web)...
start "Admin API - Dashboard" /MIN cmd /k "cd /d %~dp0 && echo Admin API iniciado en puerto 8000... && dist\AIdan_Admin.exe"
timeout /t 5 /nobreak > nul

echo.
echo ✅ Sistema iniciado correctamente
echo.
echo 📊 Servicios activos:
echo    • Collector  - Descargando noticias cada 10 minutos
echo    • Analyzer   - Analizando impacto EUR/USD
echo    • Admin API  - Dashboard en http://localhost:8000
echo.
echo 🌐 Abriendo dashboard en tu navegador...
timeout /t 2 /nobreak > nul
start http://localhost:8000

echo.
echo ═══════════════════════════════════════════════════════════════
echo  ✅ SISTEMA OPERATIVO - VERSIÓN PORTABLE
echo ═══════════════════════════════════════════════════════════════
echo.
echo  Dashboard: http://localhost:8000
echo  Auto-refresh: Cada 30 segundos
echo  Trading: Señales para opciones binarias EUR/USD
echo.
echo  Para detener: Cierra esta ventana y las demás ventanas CMD
echo.

pause
