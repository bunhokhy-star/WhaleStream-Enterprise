@echo off
:: ============================================================
:: WHALE-STREAM BOT — Add to Task Scheduler
:: Right-click this file → "Run as administrator"
:: Runs every 4 hours to generate fresh trading signals
:: Schedule: 06:00, 10:00, 14:00, 18:00, 22:00, 02:00 BKK
:: ============================================================
echo.
echo ============================================================
echo   WHALE-STREAM BOT SCHEDULER
echo ============================================================
echo.
echo Adding WhaleStream-Bot to Task Scheduler...
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
echo =====================================================
echo   SUCCESS! WhaleStream-Bot scheduled.
echo   Generates signals every 4 hours:
echo     06:00 / 10:00 / 14:00 / 18:00 / 22:00 / 02:00 BKK
echo.
echo   WhaleStream-Trader picks up signals at:
echo     06:20 / 08:20 / 10:20 / 12:20 / ...
echo.
echo   Running it NOW for first signal generation...
echo =====================================================
echo.
schtasks /Run /TN "WhaleStream-Bot"
echo.
echo   Bot is running in the background.
echo   Check bot_log.txt in ~3 minutes for results.
echo   Trader will auto-place orders at next :20 past hour.
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
