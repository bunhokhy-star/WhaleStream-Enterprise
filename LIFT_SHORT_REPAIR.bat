@echo off
echo ============================================================
echo   WHALE-STREAM — LIFT SHORT REPAIR MODE
echo ============================================================
echo.

set FLAG_FILE=C:\Users\MAX\WhaleStream\short_repair.flag

if not exist "%FLAG_FILE%" (
    echo  ✓ SHORT REPAIR MODE is not active — SHORTs already running normally.
    echo.
    pause
    exit /b 0
)

echo  Current repair mode reason:
echo.
type "%FLAG_FILE%"
echo.
echo ------------------------------------------------------------
echo  SHORT WR must be >= 50%% over 20+ real trades before lifting.
echo  Run analyze_shorts.py first to verify SHORT WR has recovered.
echo ------------------------------------------------------------
echo.
set /p CONFIRM=Type YES to lift SHORT repair mode (or anything else to cancel):

if /i "%CONFIRM%"=="YES" (
    del "%FLAG_FILE%"
    echo.
    echo  ✅ SHORT repair mode lifted. Trader will place SHORT orders on next run.
    echo     Run analyze_shorts.py weekly to monitor SHORT WR recovery.
) else (
    echo.
    echo  ✗ Cancelled — SHORT repair mode remains active.
)

echo.
pause
