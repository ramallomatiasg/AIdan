@echo off
:: Start AIdan Trading Bot
:: Scheduled via Windows Task Scheduler at 4:00 AM (Argentina)

:: Wait 30 seconds for network to connect after wake
timeout /t 30 /nobreak >nul

:: Start AIdan
start "" "F:\AIdan\dist\AIdan.exe"
