@echo off
chcp 65001 > nul
title Verificar Sistema AIdan
color 0B

echo.
echo ════════════════════════════════════════════════════════════════
echo    🔍 VERIFICACIÓN DE SISTEMA AIDAN
echo ════════════════════════════════════════════════════════════════
echo.

echo [1/4] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo    ❌ Python NO instalado
    echo    📥 Descargar: https://www.python.org/downloads/
) else (
    for /f "tokens=*" %%i in ('python --version') do echo    ✅ %%i instalado
)
echo.

echo [2/4] Verificando Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo    ❌ Ollama NO está corriendo
    echo    📥 Instalar: https://ollama.com/download/windows
    echo    💡 Después: ollama pull llama3.1:8b
) else (
    echo    ✅ Ollama activo en puerto 11434
    echo    📦 Modelos instalados:
    curl -s http://localhost:11434/api/tags | findstr "name"
)
echo.

echo [3/4] Verificando dependencias Python...
pip show httpx >nul 2>&1
if %errorlevel% neq 0 (
    echo    ❌ Dependencias NO instaladas
    echo    💡 Ejecutar: pip install -r requirements.txt
) else (
    echo    ✅ Dependencias instaladas
)
echo.

echo [4/4] Verificando servicios activos...
tasklist /FI "WINDOWTITLE eq Collector*" 2>nul | find "cmd.exe" >nul
if %errorlevel% equ 0 (
    echo    ✅ Collector corriendo
) else (
    echo    ❌ Collector NO está activo
)

tasklist /FI "WINDOWTITLE eq Analyzer*" 2>nul | find "cmd.exe" >nul
if %errorlevel% equ 0 (
    echo    ✅ Analyzer corriendo
) else (
    echo    ❌ Analyzer NO está activo
)

tasklist /FI "WINDOWTITLE eq Admin*" 2>nul | find "cmd.exe" >nul
if %errorlevel% equ 0 (
    echo    ✅ Admin API corriendo
) else (
    echo    ❌ Admin API NO está activo
)

echo.
echo Verificando API endpoint...
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% neq 0 (
    echo    ❌ API no responde en http://localhost:8000
) else (
    echo    ✅ API respondiendo en http://localhost:8000
)

echo.
echo ════════════════════════════════════════════════════════════════
echo  RESUMEN
echo ════════════════════════════════════════════════════════════════
echo.
echo  Para iniciar el sistema: start_system.bat
echo  Para detener el sistema: stop_system.bat
echo  Dashboard: http://localhost:8000
echo.
echo ════════════════════════════════════════════════════════════════
echo.
pause
