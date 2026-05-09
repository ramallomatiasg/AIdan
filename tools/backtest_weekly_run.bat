@echo off
REM AIdan Backtest Weekly - llamado por Task Scheduler domingos 23:00
REM Corre backtest_parallel para M5/M15/H1 y manda summary via Telegram
cd /d F:\AIdan
"C:\Program Files\Python311\python.exe" tools\backtest_weekly.py >> "%APPDATA%\AIdan\state\backtest_weekly.log" 2>&1
exit /b %ERRORLEVEL%
