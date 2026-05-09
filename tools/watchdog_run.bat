@echo off
REM AIdan Watchdog runner - llamado por Windows Task Scheduler cada 5 min
REM Verifica si AIdan.exe corre y manda alert Telegram si esta caido
cd /d F:\AIdan
"C:\Program Files\Python311\python.exe" tools\aidan_watchdog.py >> "%APPDATA%\AIdan\state\watchdog.log" 2>&1
exit /b %ERRORLEVEL%
