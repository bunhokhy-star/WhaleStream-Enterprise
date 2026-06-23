@echo off
:: ============================================================
:: WHALE-STREAM BOT — Update Schedule to Every 4 Hours
:: Right-click this file → "Run as administrator"
:: Changes bot from 6h → 4h for faster Gate 1 acceleration
:: New schedule: 06:00, 10:00, 14:00, 18:00, 22:00, 02:00 BKK
:: ============================================================
echo.
echo ============================================================
echo   WHALE-STREAM BOT — UPGRADE TO 4-HOUR SCHEDULE
echo ============================================================
echo.
echo  This will change the bot from running every 6h to every 4h.
echo  More signals per day = faster Gate 1 progress.
echo.
echo  Current: every 6h = 4 runs/day (~16 resolved trades/day)
echo  New    : every 4h = 6 runs/day (~24 resolved trades/day)
echo.
echo  Note: Trader (WhaleStream-Trader) runs every 2h at :20
echo  and will naturally pick up all new bot runs.
echo.
echo  Press Ctrl+C to cancel, or...
pause

echo.
echo Removing old 6-hour task...
schtasks /Delete /TN "WhaleStream-Bot" /F

if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Could not delete old task. May not exist yet.
)

echo.
echo Creating new 4-hour task...
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
echo   SUCCESS! WhaleStream-Bot updated to 4-hour cycle.
echo.
echo   New schedule (BKK time):
echo     06:00 / 10:00 / 14:00 / 18:00 / 22:00 / 02:00
echo.
echo   Trader picks up signals at :20 past each hour:
echo     06:20 / 10:20 / 14:20 / 18:20 / 22:20 / 02:20
echo.
echo   Gate 1 target: 150 resolved trades
echo   Estimated boost: ~33%% faster than 6-hour schedule
echo =====================================================
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
