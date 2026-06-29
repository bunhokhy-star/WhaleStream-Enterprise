@echo off
:: One-click clear — deletes paused.flag + gate4_breach.flag + writes 60min grace period
:: ⚠ REQUIRES MANUAL YES CONFIRMATION — this bypasses Gate 4 capital protection
echo ══════════════════════════════════════════════
echo   WHALE-STREAM — Clear Circuit Breaker
echo ══════════════════════════════════════════════
echo.
echo   ⚠  WARNING: This clears BOTH paused.flag AND gate4_breach.flag.
echo   ⚠  Only use this if you have reviewed the loss streak and the
echo   ⚠  market condition has genuinely changed.
echo.
set /p CONFIRM=Type YES to clear ALL breach flags and resume trading (anything else = cancel):

if /i NOT "%CONFIRM%"=="YES" (
    echo.
    echo   ✗ Cancelled — all flags remain active. No changes made.
    echo.
    pause
    exit /b 0
)

echo.

if exist "C:\Users\MAX\WhaleStream\paused.flag" (
    del /f "C:\Users\MAX\WhaleStream\paused.flag"
    echo   ✅ Deleted paused.flag
) else (
    echo   ✓  paused.flag already gone
)

if exist "C:\Users\MAX\WhaleStream\gate4_breach.flag" (
    del /f "C:\Users\MAX\WhaleStream\gate4_breach.flag"
    echo   ✅ Deleted gate4_breach.flag
) else (
    echo   ✓  gate4_breach.flag already gone
)

:: Write 60-min grace period so Trader won't re-trigger CB on next run
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" -c "import json,datetime; open(r'C:\Users\MAX\WhaleStream\cb_grace.txt','w').write(json.dumps({'cleared_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}))"
echo   ✅ Grace period written ^(60 min^) — CB won't re-fire this cycle

echo.
echo ══════════════════════════════════════════════
echo   Done. System will resume on next cycle.
echo   Watch Telegram for first live signal.
echo ══════════════════════════════════════════════
echo.
pause
