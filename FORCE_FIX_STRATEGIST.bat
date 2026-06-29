@echo off
:: ═══════════════════════════════════════════════════════════════════
:: FORCE_FIX_STRATEGIST.bat
::
:: PURPOSE: The WhaleStreamStrategist Task Scheduler task is STUCK.
:: Python crashed during shutdown on June 28 20:10 — cmd.exe is still
:: hanging. Task Scheduler sees the task as "Running" and won't start
:: new instances. This bat kills the stuck process and re-runs.
::
:: RUN AS ADMINISTRATOR (right-click → Run as administrator)
:: ═══════════════════════════════════════════════════════════════════
echo.
echo ═══════════════════════════════════════════════════════════════════
echo   WHALE-STREAM — Force Fix Strategist
echo   Kills stuck task instance and restores 4h schedule
echo ═══════════════════════════════════════════════════════════════════
echo.

:: [1/5] Force-end the stuck Task Scheduler instance
echo [1/5] Force-stopping stuck WhaleStreamStrategist task...
schtasks /End /TN "WhaleStreamStrategist" >nul 2>&1
echo    Done.
echo.

:: [2/5] Kill stuck Python processes running whale_stream_strategist.py
echo [2/5] Killing stuck Python processes (whale_stream_strategist.py)...
powershell -NoProfile -NonInteractive -Command ^
  "Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*whale_stream_strategist*' } | ForEach-Object { Write-Host '   Killed PID:' $_.ProcessId; $_.Terminate() }"
echo    Done.
echo.

:: [3/5] Kill stuck cmd.exe processes wrapping run_strategist.bat
echo [3/5] Killing stuck cmd.exe wrappers (run_strategist.bat)...
powershell -NoProfile -NonInteractive -Command ^
  "Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*run_strategist*' } | ForEach-Object { Write-Host '   Killed PID:' $_.ProcessId; $_.Terminate() }"
echo    Done.
echo.

:: [4/5] Wait for cleanup then run the Strategist once right now
echo [4/5] Running Strategist NOW (one-shot to catch up)...
timeout /t 2 /nobreak >nul
cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" whale_stream_strategist.py
echo    Done.
echo.

:: [5/5] Confirm Task Scheduler will auto-resume at next :10 slot
echo [5/5] Verifying task is still registered and enabled...
schtasks /Query /TN "WhaleStreamStrategist" /fo LIST | findstr /i "Task Name\|Status\|Next Run"
echo.
echo ═══════════════════════════════════════════════════════════════════
echo   DONE. Strategist ran immediately.
echo   Task Scheduler will continue at the next :10 slot (00:10 / 04:10
echo   / 08:10 / 12:10 / 16:10 / 20:10 BKK) automatically.
echo   Check Telegram for the Strategist result.
echo ═══════════════════════════════════════════════════════════════════
echo.
pause
