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

echo [1/5] 📋 Copiando ejecutable...
copy /Y "dist\AIdan_Launcher.exe" "AIdan_Portable\"

echo [2/5] ⚙️ Copiando configuración...
xcopy /E /I /Y "config" "AIdan_Portable\config"

echo [3/5] 🎨 Copiando recursos estáticos...
xcopy /E /I /Y "static" "AIdan_Portable\static"

echo [4/5] 📄 Copiando documentación...
copy /Y "LEEME.txt" "AIdan_Portable\"
copy /Y "README.md" "AIdan_Portable\"
copy /Y "LICENSE" "AIdan_Portable\"

echo [5/5] 📦 Comprimiendo en .zip...
powershell -Command "Compress-Archive -Path 'AIdan_Portable\*' -DestinationPath 'AIdan_Portable.zip' -Force"

echo.
echo ════════════════════════════════════════════════════════════════
echo    ✅ PAQUETE CREADO EXITOSAMENTE
echo ════════════════════════════════════════════════════════════════
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
