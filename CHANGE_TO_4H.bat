@echo off
:: ============================================================
:: WHALE-STREAM — Change Bot to 4h Schedule
:: Quality over quantity — enough samples collected.
:: Right-click → "Run as administrator"
::
:: Changes: WhaleStream-Bot from 2h → 4h cadence
:: Schedule: 06:00 / 10:00 / 14:00 / 18:00 / 22:00 / 02:00 BKK
:: Strategist already at 4h :10 — stays in sync.
:: ============================================================
echo.
echo ============================================================
echo   WHALE-STREAM — Switching Bot to 4h Cadence
echo ============================================================
echo.
echo   Rationale: Gate 1 cleared (159+ trades). Enough samples.
echo   Now prioritise signal QUALITY over QUANTITY.
echo   4h gives market time to develop clean setups.
echo   Strategist already runs at 4h :10 — stays aligned.
echo.
echo   Updating WhaleStream-Bot schedule: 2h --> 4h...
echo.

schtasks /Create ^
  /TN "WhaleStream-Bot" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_bot.bat\"" ^
  /SC HOURLY ^
  /MO 4 ^
  /ST 06:00 ^
  /F

if %ERRORLEVEL% NEQ 0 goto :error

echo.
echo ============================================================
echo   SUCCESS! Bot now runs every 4 hours.
echo.
echo   Bot schedule:        06:00 / 10:00 / 14:00 / 18:00 / 22:00 / 02:00
echo   Strategist :10:      06:10 / 10:10 / 14:10 / 18:10 / 22:10 / 02:10
echo   Trader :20:          06:20 / 10:20 / 14:20 / 18:20 / 22:20 / 02:20
echo.
echo   Verify in Task Scheduler: WhaleStream-Bot should show
echo   "At 6:00 AM every day - After triggered, repeat every 04:00:00"
echo ============================================================
echo.
goto :end

:error
echo.
echo ERROR: Failed to update task.
echo Make sure you right-clicked and chose "Run as administrator"
echo.

:end
echo.
pause
