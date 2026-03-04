@echo off
chcp 65001 > nul
title AIdan - Crear Paquete Portable
color 0A

echo.
echo ════════════════════════════════════════════════════════════════
echo    📦 CREANDO PAQUETE PORTABLE DE AIDAN
echo ════════════════════════════════════════════════════════════════
echo.

cd /d F:\AIdan

:: Crear carpeta portable
if exist "AIdan_Portable" rmdir /s /q "AIdan_Portable"
mkdir "AIdan_Portable"

echo [1/4] 📋 Copiando ejecutable...
copy /Y "dist\AIdan.exe" "AIdan_Portable\"

echo [2/4] ⚙️ Copiando configuración y recursos...
xcopy /E /I /Y "config" "AIdan_Portable\config"
xcopy /E /I /Y "static" "AIdan_Portable\static"

echo [3/4] 📄 Copiando documentación...
copy /Y "README.md" "AIdan_Portable\"
copy /Y "LICENSE" "AIdan_Portable\"

echo [4/4] 📦 Comprimiendo en .zip...
powershell -Command "Compress-Archive -Path 'AIdan_Portable\*' -DestinationPath 'AIdan_Portable.zip' -Force"

echo.
echo ════════════════════════════════════════════════════════════════
echo    ✅ PAQUETE CREADO EXITOSAMENTE
echo.
echo    📦 Carpeta: AIdan_Portable\
echo    📦 ZIP: AIdan_Portable.zip
echo.
echo    🎉 ¡Listo para compartir!
echo.
echo    Contenido:
dir /B "AIdan_Portable"
echo.
pause
