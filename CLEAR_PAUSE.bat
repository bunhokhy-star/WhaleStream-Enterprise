@echo off
echo ============================================================
echo   WHALE-STREAM — CLEAR CIRCUIT BREAKER PAUSE
echo ============================================================
echo.

set FLAG_FILE=C:\Users\MAX\WhaleStream\paused.flag

if not exist "%FLAG_FILE%" (
    echo  ✓ No pause flag found — trader is already running normally.
    echo.
    pause
    exit /b 0
)

echo  ⚠  Current pause reason:
echo.
type "%FLAG_FILE%"
echo.
echo ------------------------------------------------------------
echo  Are you sure you want to clear the pause and resume trading?
echo  Only do this after reviewing the losing streak and confirming
echo  the market condition has changed.
echo ------------------------------------------------------------
echo.
set /p CONFIRM=Type YES to clear the pause (or anything else to cancel):

if /i "%CONFIRM%"=="YES" (
    del "%FLAG_FILE%"
    if exist "C:\Users\MAX\WhaleStream\cb_pause_alerted.flag" del "C:\Users\MAX\WhaleStream\cb_pause_alerted.flag"
    "C:\Users\MAX\AppData\Local\Python\bin\python.exe" -c "import json,datetime; f=open(r'C:\Users\MAX\WhaleStream\cb_grace.txt','w'); f.write(json.dumps({'cleared_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})); f.close()"
    echo.
    echo  ✅ Pause cleared. Grace period written ^(60min^).
    echo     cb_pause_alerted.flag also deleted ^(Trader will resend alert on next CB^).
    echo     Trader will place orders on next run without re-triggering CB.
    echo     Next run: check Task Scheduler or wait for the 4-hour cycle.
) else (
    echo.
    echo  ✗ Cancelled — pause remains active.
)

echo.
pause
