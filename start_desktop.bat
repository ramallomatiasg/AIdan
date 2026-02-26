@echo off
chcp 65001 > nul
title AIdan v1.1 - Versión Desktop
color 0A

echo.
echo ════════════════════════════════════════════════════════════════
echo    💱 AIDAN v1.1 - VERSIÓN DESKTOP
echo    Dashboard en ventana independiente
echo ════════════════════════════════════════════════════════════════
echo.

cd /d %~dp0

if exist "dist\AIdan_Desktop.exe" (
    echo 🚀 Iniciando AIdan Desktop...
    echo.
    echo ⏳ Esto puede tardar unos segundos la primera vez...
    echo.
    start "" "dist\AIdan_Desktop.exe"
    
    echo.
    echo ✅ AIdan Desktop iniciado
    echo.
    echo La ventana del dashboard se abrirá automáticamente
    echo.
    echo Para cerrar: Cierra la ventana del dashboard
    echo.
) else (
    echo ❌ ERROR: No se encontró AIdan_Desktop.exe
    echo.
    echo Por favor:
    echo 1. Ejecuta build_exe.bat primero para compilar
    echo 2. O verifica que estés en la carpeta correcta
    echo.
)

pause
