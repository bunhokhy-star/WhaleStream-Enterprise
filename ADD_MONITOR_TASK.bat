@echo off
:: ============================================================
:: WHALE-STREAM MONITOR — Add to Task Scheduler
:: Right-click this file → "Run as administrator"
:: Runs every 2 MINUTES starting now
::   → Detects TP1 partial closes and full position closes
::   → Moves SL to breakeven immediately when TP1 fires
::   → Sends Telegram alert within 2 min of any fill
:: ============================================================
echo.
echo ============================================================
echo   WHALE-STREAM NEAR-REAL-TIME MONITOR SCHEDULER
echo ============================================================
echo.
echo Adding WhaleStream-Monitor to Task Scheduler...
echo.

schtasks /Create ^
  /TN "WhaleStream-Monitor" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_monitor.bat\"" ^
  /SC MINUTE ^
  /MO 2 ^
  /F

if %ERRORLEVEL% NEQ 0 goto :error

echo.
echo =====================================================
echo   SUCCESS! WhaleStream-Monitor scheduled.
echo   Polls Bybit positions every 2 minutes.
echo.
echo   What it does:
echo     * Detects TP1 partial close (~50% size drop)
echo     * Moves SL to breakeven immediately (SL-to-BE)
echo     * Detects full close + sends Telegram alert
echo     * Logs all events to monitor_log.txt
echo.
echo   Running it NOW for first test...
echo =====================================================
echo.
schtasks /Run /TN "WhaleStream-Monitor"
echo.
echo   Done! Check monitor_log.txt for results.
echo.
goto :end

:error
echo.
echo ERROR: Failed to create task.
echo Make sure you right-clicked and chose "Run as administrator"
echo.

:end
echo.
pause
