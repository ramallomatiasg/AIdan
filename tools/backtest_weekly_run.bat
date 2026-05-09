@echo off
REM AIdan Backtest Weekly - silent run via pythonw (no console window)
REM Llamado por Task Scheduler domingos 23:00
cd /d F:\AIdan
start "" /b "C:\Program Files\Python311\pythonw.exe" tools\backtest_weekly.py
exit /b 0
