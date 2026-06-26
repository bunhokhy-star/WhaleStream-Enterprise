@echo off
echo ══════════════════════════════════════════════════
echo   WHALE-STREAM — Register Watchdog Task
echo ══════════════════════════════════════════════════
echo.
echo Removing old task (if any)...
schtasks /delete /tn "WhaleStreamWatchdog" /f >nul 2>&1

echo Creating WhaleStreamWatchdog task...
schtasks /create ^
  /tn "WhaleStreamWatchdog" ^
  /tr "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_watchdog.bat\"" ^
  /sc DAILY ^
  /st 00:30 ^
  /ri 240 ^
  /du 9999:59 ^
  /f ^
  /rl HIGHEST

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to create task. Make sure you run this as Administrator.
    pause
    exit /b 1
)

echo.
echo SUCCESS — WhaleStreamWatchdog scheduled every 4h starting 00:30 BKK.
echo Runs at: 00:30, 04:30, 08:30, 12:30, 16:30, 20:30
echo Alerts via Telegram if Bot / Strategist / Trader missed their slot.
echo.
pause
