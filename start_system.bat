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

echo [1/5] ✅ Verificando Ollama (IA local)...
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo    ⚠️  Ollama NO está corriendo
    echo.
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo  ⚠️  ADVERTENCIA: Sistema iniciará SIN análisis de IA
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo.
    echo  El sistema funcionará pero NO generará señales automáticas.
    echo.
    echo  📥 Para activar análisis con IA:
    echo     1. Descargar: https://ollama.com/download/windows
    echo     2. Instalar y ejecutar Ollama
    echo     3. Abrir PowerShell: ollama pull llama3.1:8b
    echo     4. Reiniciar el sistema con: stop_system.bat y start_system.bat
    echo.
    echo  ¿Continuar sin IA? (S/N)
    choice /C SN /N /M "Presiona S para continuar o N para salir: "
    if errorlevel 2 exit /b 1
    echo.
    echo  Continuando sin Ollama...
) else (
    echo    ✅ Ollama está activo y respondiendo
)
timeout /t 1 /nobreak > nul

echo [2/5] 🛑 Cerrando procesos Python previos...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak > nul

echo [3/5] 🚀 Iniciando Collector (noticias RSS)...
start "Collector - News Feed" /MIN cmd /k "cd /d F:\AIdan && echo Collector iniciado... && python src\collector\main.py"
timeout /t 3 /nobreak > nul

echo [4/5] 🔍 Iniciando Analyzer (análisis con IA)...
start "Analyzer - AI Analysis" /MIN cmd /k "cd /d F:\AIdan && echo Analyzer iniciado con Ollama... && python src\analyzer\main.py"
timeout /t 3 /nobreak > nul

echo [5/5] 🌐 Iniciando Admin API (dashboard web)...
start "Admin API - Dashboard" /MIN cmd /k "cd /d F:\AIdan && echo Admin API iniciado en puerto 8000... && python -m uvicorn src.admin.main:app --host 0.0.0.0 --port 8000"
timeout /t 5 /nobreak > nul

echo.
echo ✅ Sistema iniciado correctamente
echo.
echo 📊 Servicios activos:
echo    • Collector  - Descargando noticias cada 10 minutos
echo    • Analyzer   - Analizando con Ollama (IA local)
echo    • Admin API  - Dashboard en http://localhost:8000
echo.
echo 🤖 Modo de análisis: OLLAMA (IA Local)
echo    • Señales determinadas por IA (no keywords)
echo    • OPERAR / NO OPERAR decidido por Llama 3.1
echo.
echo 🌐 Abriendo dashboard en tu navegador...
timeout /t 2 /nobreak > nul
start http://localhost:8000

echo.
echo ═══════════════════════════════════════════════════════════════
echo  ✅ SISTEMA OPERATIVO CON IA
echo ═══════════════════════════════════════════════════════════════
echo.
echo  Dashboard: http://localhost:8000
echo  Auto-refresh: Cada 30 segundos
echo  Análisis: 🤖 Ollama IA (Llama 3.1)
echo.
echo  ⚡ Las señales CALL/PUT son determinadas por IA
echo  ⚡ Solo se muestran alertas analizadas por Ollama
echo  ⚡ Chat con IA disponible en el sidebar
echo.
echo  Presiona cualquier tecla para cerrar esta ventana
echo  (Los servicios seguirán ejecutándose en segundo plano)
echo ═══════════════════════════════════════════════════════════════
echo.
pause > nul
