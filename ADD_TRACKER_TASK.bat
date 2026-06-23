@echo off
:: ============================================================
:: WHALE-STREAM TRACKER — Add to Task Scheduler
:: Right-click this file → "Run as administrator"
:: Runs every 30 minutes to check TP/SL and update Google Sheets
:: ============================================================
echo.
echo Adding WhaleStream-Tracker to Task Scheduler...
echo.

schtasks /Create ^
  /TN "WhaleStream-Tracker" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_tracker.bat\"" ^
  /SC MINUTE ^
  /MO 30 ^
  /ST 00:10 ^
  /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo =====================================================
    echo   SUCCESS! WhaleStream-Tracker scheduled.
    echo   Runs every 30 minutes starting at :10 past hour
    echo   (Catches TP/SL hits quickly)
    echo.
    echo   Running it NOW for first test...
    echo =====================================================
    echo.
    schtasks /Run /TN "WhaleStream-Tracker"
    echo.
    echo Done! Check tracker_log.txt for results.
) else (
    echo.
    echo ERROR: Failed to create task.
    echo Make sure you right-clicked and chose "Run as administrator"
)

echo.
pause
