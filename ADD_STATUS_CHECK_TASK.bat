@echo off
:: ════════════════════════════════════════════════════════════════════
:: ADD_STATUS_CHECK_TASK.bat
:: Registers check_daily_status.py in Task Scheduler.
::
:: Runs every 4 hours starting at 00:45 (= :45 of each BKK cycle,
:: 15 minutes after Watchdog finishes at :30).
::
:: What it does each run:
::   • Reads daily_status.json
::   • Checks which agents should have completed by now
::   • Sends ✅ all-green OR ⚠️ gap alert to Telegram
::   • Pings localhost:8765 to verify status server is alive
::
:: RUN AS ADMINISTRATOR — required to register tasks
:: ════════════════════════════════════════════════════════════════════

SET SCRIPT_DIR=%~dp0
SET SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

SET TASK_NAME=WhaleStream-StatusCheck
SET PYTHON_CMD="C:\Users\MAX\AppData\Local\Python\bin\python.exe"
SET SCRIPT=%SCRIPT_DIR%\check_daily_status.py

echo ══════════════════════════════════════════════════
echo   WHALE-STREAM Status Check Task Installer
echo ══════════════════════════════════════════════════
echo.
echo Task name : %TASK_NAME%
echo Script    : %SCRIPT%
echo Schedule  : Every 4 hours starting at 00:45
echo             (runs at 00:45, 04:45, 08:45, 12:45, 16:45, 20:45)
echo.

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "%PYTHON_CMD% \"%SCRIPT%\"" ^
  /sc DAILY ^
  /st 00:45 ^
  /ri 240 ^
  /du 9999:59 ^
  /ru "%USERNAME%" ^
  /f

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Task "%TASK_NAME%" registered.
    echo.
    echo To run NOW without waiting:
    echo      schtasks /run /tn "%TASK_NAME%"
    echo.
    echo ══════════════════════════════════════════════════
    echo   3 layers of gap detection now active:
    echo   Layer 1 — Watchdog at :30  (log timestamps)
    echo   Layer 2 — StatusCheck at :45 (daily_status.json)
    echo   Layer 3 — MorningBrief 07:00 (overnight summary)
    echo ══════════════════════════════════════════════════
) ELSE (
    echo.
    echo [ERROR] Failed to register task.
    echo         Run this script as Administrator.
)

pause
