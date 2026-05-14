@echo off
REM run_nightly_analyst.bat — wrapper batch para Windows Task Scheduler.
REM Ejecuta nightly_analyst.py a las 19:00 AR cada dia.
REM
REM Setup (1 vez, como administrator):
REM   schtasks /Create /TN "AIdan_NightlyAnalyst" /TR "F:\AIdan\tools\run_nightly_analyst.bat" /SC DAILY /ST 19:00 /F
REM
REM Verificar:
REM   schtasks /Query /TN "AIdan_NightlyAnalyst"
REM
REM Run manual (test):
REM   schtasks /Run /TN "AIdan_NightlyAnalyst"
REM
REM Remove:
REM   schtasks /Delete /TN "AIdan_NightlyAnalyst" /F

REM No abrir consola (pythonw)
cd /d F:\AIdan
start "" /B pythonw.exe tools\nightly_analyst.py 2>&1
exit /b 0
