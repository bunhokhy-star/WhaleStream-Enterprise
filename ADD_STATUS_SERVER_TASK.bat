@echo off
:: ════════════════════════════════════════════════════════════════════
:: ADD_STATUS_SERVER_TASK.bat
:: Registers status_server.py in Task Scheduler so it starts
:: automatically at system login (runs silently in background).
::
:: Port  : localhost:8765
:: Serves: daily_status.json → Daily Checklist HTML auto-tick
::
:: NOTE: This script creates run_status_server.bat only if it does not
::    already exist (safe to re-run). Only run this if SETUP_ALL_TASKS.bat
::    has NOT already been run (SETUP_ALL_TASKS.bat registers StatusServer
::    automatically). Running this separately after SETUP_ALL_TASKS.bat is
::    harmless — it will skip the bat creation and re-register the task.
::
:: RUN AS ADMINISTRATOR — required to register tasks
:: ════════════════════════════════════════════════════════════════════

SET SCRIPT_DIR=%~dp0
SET SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

SET TASK_NAME=WhaleStream-StatusServer
SET BAT_FILE=%SCRIPT_DIR%\run_status_server.bat

:: Only create run_status_server.bat if it doesn't already exist.
:: This prevents overwriting a working wrapper on repeated runs.
IF EXIST "%BAT_FILE%" (
    echo [INFO] run_status_server.bat already exists — skipping overwrite.
    echo        Delete it manually if you want to regenerate it.
    goto :register_task
)

:: Create a wrapper bat so pythonw can run it without a console window
echo @echo off > "%BAT_FILE%"
echo start "" /B pythonw "%SCRIPT_DIR%\status_server.py" >> "%BAT_FILE%"

:register_task

echo Creating Task Scheduler entry: %TASK_NAME%

schtasks /create /tn "%TASK_NAME%" /tr "%BAT_FILE%" /sc ONLOGON /delay 0000:30 /ru "%USERNAME%" /f

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Task "%TASK_NAME%" registered.
    echo      Starts 30 seconds after login.
    echo      Port: localhost:8765
    echo.
    echo To run NOW without rebooting:
    echo      schtasks /run /tn "%TASK_NAME%"
) ELSE (
    echo.
    echo [ERROR] Failed to register task. Run this script as Administrator.
)
pause
