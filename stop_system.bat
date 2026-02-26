@echo off
chcp 65001 > nul
title Cerrar Financial News Monitor
color 0C

echo.
echo ════════════════════════════════════════════════════════════════
echo    🛑 CERRANDO FINANCIAL NEWS MONITOR
echo ════════════════════════════════════════════════════════════════
echo.

echo Deteniendo todos los servicios Python...
taskkill /F /IM python.exe 2>nul

if %errorlevel% equ 0 (
    echo.
    echo ✅ Servicios detenidos correctamente
) else (
    echo.
    echo ⚠️  No había servicios ejecutándose
)

echo.
echo ════════════════════════════════════════════════════════════════
echo.
pause
