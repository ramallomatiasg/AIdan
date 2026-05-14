@echo off
REM setup_nightly_task.bat — registra el nightly analyst en Windows Task Scheduler.
REM Correr UNA VEZ (como administrator).
REM
REM Que hace:
REM   - Crea task "AIdan_NightlyAnalyst" que corre a las 19:00 AR cada dia
REM   - Llama a F:\AIdan\tools\run_nightly_analyst.bat
REM   - Si la task ya existe, la reemplaza (/F)

echo Creando task "AIdan_NightlyAnalyst" para correr a las 19:00 todos los dias...

schtasks /Create ^
  /TN "AIdan_NightlyAnalyst" ^
  /TR "F:\AIdan\tools\run_nightly_analyst.bat" ^
  /SC DAILY ^
  /ST 19:00 ^
  /RL HIGHEST ^
  /F

if %errorlevel% equ 0 (
    echo.
    echo === Task creada exitosamente ===
    echo Trigger: 19:00 AR diariamente
    echo Action:  F:\AIdan\tools\run_nightly_analyst.bat
    echo.
    echo Para verificar:  schtasks /Query /TN "AIdan_NightlyAnalyst"
    echo Para test ahora: schtasks /Run   /TN "AIdan_NightlyAnalyst"
    echo Para borrar:     schtasks /Delete /TN "AIdan_NightlyAnalyst" /F
) else (
    echo.
    echo === ERROR creando task ===
    echo Asegurate de correr este script como administrator.
)

pause
