@echo off
chcp 65001 > nul
title Financial News Monitor - Iniciador
color 0A

echo.
echo ════════════════════════════════════════════════════════════════
echo    💱 FINANCIAL NEWS MONITOR - EUR/USD ANALYSIS SYSTEM
echo ════════════════════════════════════════════════════════════════
echo.

cd /d F:\AIdan

echo [1/4] 🛑 Cerrando procesos Python previos...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak > nul

echo [2/4] 🚀 Iniciando Collector (noticias RSS)...
start "Collector - News Feed" /MIN cmd /k "cd /d F:\AIdan && echo Collector iniciado... && python src\collector\main.py"
timeout /t 3 /nobreak > nul

echo [3/4] 🔍 Iniciando Analyzer (análisis EUR/USD)...
start "Analyzer - EUR/USD Analysis" /MIN cmd /k "cd /d F:\AIdan && echo Analyzer iniciado... && python src\analyzer\main.py"
timeout /t 3 /nobreak > nul

echo [4/4] 🌐 Iniciando Admin API (dashboard web)...
start "Admin API - Dashboard" /MIN cmd /k "cd /d F:\AIdan && echo Admin API iniciado en puerto 8000... && python -m uvicorn src.admin.main:app --host 0.0.0.0 --port 8000"
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
echo  ✅ SISTEMA OPERATIVO
echo ═══════════════════════════════════════════════════════════════
echo.
echo  Dashboard: http://localhost:8000
echo  Auto-refresh: Cada 30 segundos
echo  Análisis EUR/USD: ✅ Activo con predicciones claras
echo.
echo  Presiona cualquier tecla para cerrar esta ventana
echo  (Los servicios seguirán ejecutándose en segundo plano)
echo ═══════════════════════════════════════════════════════════════
echo.
pause > nul
