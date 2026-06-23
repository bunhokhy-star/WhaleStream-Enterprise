@echo off
echo ============================================================
echo   WHALE-STREAM — SCHEDULE ORPHAN CHECK (DAILY 06:00)
echo ============================================================
echo.
echo  This schedules check_bybit_orphans.py to run daily at 06:00 BKK.
echo  Run this bat file ONCE as administrator to add the task.
echo.

schtasks /create /tn "WhaleStream-OrphanCheck" /tr "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_orphan_check.bat\"" /sc daily /st 06:00 /f

if %errorlevel% == 0 (
    echo.
    echo  ✅ Task "WhaleStream-OrphanCheck" scheduled successfully.
    echo     Runs daily at 06:00 — checks for untracked Bybit positions.
    echo     Telegram alert fires if orphaned positions are found.
) else (
    echo.
    echo  ✗ Failed to create task. Try running as Administrator.
)

echo.
pause
