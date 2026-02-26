@echo off
chcp 65001 > nul
title Deteniendo Sistema Portable
color 0C

echo.
echo ════════════════════════════════════════════════════════════════
echo    🛑 DETENIENDO FINANCIAL NEWS MONITOR
echo ════════════════════════════════════════════════════════════════
echo.

echo Cerrando todos los servicios...
taskkill /F /IM AIdan_Admin.exe 2>nul
taskkill /F /IM AIdan_Collector.exe 2>nul
taskkill /F /IM AIdan_Analyzer.exe 2>nul

echo.
echo ✅ Sistema detenido
echo.
pause
