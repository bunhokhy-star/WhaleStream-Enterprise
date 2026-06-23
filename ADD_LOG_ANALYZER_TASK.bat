@echo off
echo ============================================================
echo   WHALE-STREAM — SCHEDULE LOG ANALYZER (DAILY 07:00)
echo ============================================================
echo.
echo  This schedules analyze_logs.py to run daily at 07:00 BKK.
echo  Run this bat file ONCE as administrator to add the task.
echo.

schtasks /create /tn "WhaleStream-LogAnalyzer" /tr "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_log_analyzer.bat\"" /sc daily /st 07:00 /f

if %errorlevel% == 0 (
    echo.
    echo  ✅ Task "WhaleStream-LogAnalyzer" scheduled successfully.
    echo     Runs daily at 07:00 — parses all logs for health metrics.
    echo     Output saved to analyze_logs.txt in WhaleStream folder.
) else (
    echo.
    echo  ✗ Failed to create task. Try running as Administrator.
)

echo.
pause
