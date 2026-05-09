@echo off
REM AIdan Watchdog - silent run via pythonw (no console window)
REM Llamado por Windows Task Scheduler cada 5 min cuando AIdan esta corriendo
cd /d F:\AIdan
start "" /b "C:\Program Files\Python311\pythonw.exe" tools\aidan_watchdog.py
exit /b 0
