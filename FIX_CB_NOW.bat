@echo off
:: ════════════════════════════════════════════════════════════════════
:: FIX_CB_NOW.bat  — Emergency circuit-breaker clear
::
:: What this does:
::   1. Deletes paused.flag  (removes the CB lock so Trader runs)
::   2. Writes a fresh cb_grace.txt with current UTC time
::      The Trader reads this and honours an 8-hour (480-min) grace
::      window so the CB cannot re-trigger from the same old LOSS streak.
::   3. Deletes cb_pause_alerted.flag (so Watchdog re-alerts on next CB)
::   4. Deletes balance_warn_alerted.flag (so low-balance alert re-fires)
::
:: Run ONCE — then wait for the next scheduled Trader cycle (every 4h).
:: The 480-min grace window covers 2 full Trader cycles.
:: ════════════════════════════════════════════════════════════════════
cd /d C:\Users\MAX\WhaleStream

echo.
echo  ════════════════════════════════════════════════════════
echo    WHALE-STREAM — Emergency CB Clear + Grace Override
echo  ════════════════════════════════════════════════════════
echo.

:: 1. Delete paused.flag
if exist paused.flag (
    del paused.flag
    echo  [OK] paused.flag deleted ^(CB lock removed^)
) else (
    echo  [OK] paused.flag already absent
)

:: 2. Write fresh cb_grace.txt with current UTC time (8-hour window)
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" -c ^
 "import json,datetime; f=open(r'C:\Users\MAX\WhaleStream\cb_grace.txt','w'); f.write(json.dumps({'cleared_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})); f.close(); print('  [OK] cb_grace.txt written — 480-min grace active')"

:: 3. Delete sentinel flags so alerts re-fire correctly
if exist cb_pause_alerted.flag (
    del cb_pause_alerted.flag
    echo  [OK] cb_pause_alerted.flag deleted
)
if exist balance_warn_alerted.flag (
    del balance_warn_alerted.flag
    echo  [OK] balance_warn_alerted.flag deleted
)

echo.
echo  ════════════════════════════════════════════════════════
echo   DONE — CB cleared.  8-hour grace window is now active.
echo   Trader will place orders on the next scheduled cycle.
echo   Watchdog at :30 will self-heal Strategist if needed.
echo  ════════════════════════════════════════════════════════
echo.
pause
