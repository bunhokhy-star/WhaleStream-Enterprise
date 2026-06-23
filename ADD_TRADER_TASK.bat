@echo off
:: ============================================================
:: WHALE-STREAM TRADER — Add to Task Scheduler
:: Right-click this file → "Run as administrator"
:: Runs every 2 hours starting at 06:20 BKK
::   → Picks up fresh signals 20 min after the bot runs
::   → Extra runs at 08:20, 10:20 catch signals still in range
:: ============================================================
echo.
echo ============================================================
echo   WHALE-STREAM TRADER SCHEDULER
echo ============================================================
echo.
echo Adding WhaleStream-Trader to Task Scheduler...
echo.

schtasks /Create ^
  /TN "WhaleStream-Trader" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_trader.bat\"" ^
  /SC HOURLY ^
  /MO 2 ^
  /ST 06:20 ^
  /F

if %ERRORLEVEL% NEQ 0 goto :error

echo.
echo =====================================================
echo   SUCCESS! WhaleStream-Trader scheduled.
echo   Places orders every 2 hours starting 06:20:
echo     06:20 / 08:20 / 10:20 / 12:20 / 14:20 / ...
echo.
echo   Signals stay valid for 4 hours after bot runs.
echo   Multiple trader attempts = more chances to fill.
echo.
echo   Running it NOW for first test...
echo =====================================================
echo.
schtasks /Run /TN "WhaleStream-Trader"
echo.
echo   Done! Check trader_log.txt for results.
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
