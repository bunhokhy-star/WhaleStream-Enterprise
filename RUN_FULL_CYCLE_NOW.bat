@echo off
:: ════════════════════════════════════════════════════════════════════
:: RUN_FULL_CYCLE_NOW.bat
:: Runs a complete Bot → Strategist → Trader cycle immediately.
::
:: What it does:
::   1. Clears the circuit breaker (deletes paused.flag)
::   2. Runs Bot      — scans 200 coins, picks top signals
::   3. Runs Strategist — Claude reviews + approves / vetoes
::   4. Runs Trader   — executes approved signals on Bybit Demo
::
:: Watch your Telegram for live updates from each agent.
:: ════════════════════════════════════════════════════════════════════

SET DIR=%~dp0
SET DIR=%DIR:~0,-1%

cd /d "%DIR%"

echo ══════════════════════════════════════════════════════
echo   WHALE-STREAM — Full Cycle Now
echo ══════════════════════════════════════════════════════
echo.

:: ── Step 0: Clear circuit breaker + write grace period ────
IF EXIST "%DIR%\paused.flag" (
    echo [0] Clearing circuit breaker ^(paused.flag^)...
    del /f "%DIR%\paused.flag"
    echo     Circuit breaker cleared.
) ELSE (
    echo [0] No circuit breaker active.
)
:: Write cb_grace.txt so Trader won't re-create paused.flag this run
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" -c "import json,datetime; f=open(r'%DIR%\cb_grace.txt','w'); f.write(json.dumps({'cleared_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})); f.close()"
echo     Grace period written ^(60min^ — Trader will trade even if loss streak detected^).
echo.

:: ── Step 1: Bot ────────────────────────────────────────
echo [1] Running Bot ^(scanning 200 coins for signals^)...
echo     This takes ~2-3 minutes. Watch Telegram for signal alert.
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" "%DIR%\whale_stream_bot.py"
echo.
echo     [Bot complete]
echo.

:: ── Step 2: Strategist ────────────────────────────────
echo [2] Running Strategist ^(Claude reviewing signals^)...
echo     This takes ~30-60 seconds. Watch Telegram for approval report.
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" "%DIR%\whale_stream_strategist.py"
echo.
echo     [Strategist complete]
echo.

:: ── Step 3: Trader ────────────────────────────────────
echo [3] Running Trader ^(placing approved orders on Bybit Demo^)...
echo     Watch Telegram for order placement alerts.
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" "%DIR%\whale_stream_trader.py"
echo.
echo     [Trader complete]
echo.

echo ══════════════════════════════════════════════════════
echo   Full cycle done. Check Telegram for all alerts.
echo ══════════════════════════════════════════════════════
pause
