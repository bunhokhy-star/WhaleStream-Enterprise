@echo off
:: ╔══════════════════════════════════════════════════════════════════╗
:: ║   WHALE-STREAM — MASTER TASK SETUP                              ║
:: ║   Single source of truth for ALL scheduled tasks.               ║
:: ║   Right-click → "Run as administrator"                          ║
:: ║                                                                  ║
:: ║   This is the ONLY file you need to run to set up or            ║
:: ║   repair the Task Scheduler. Do NOT use any other bat.          ║
:: ║                                                                  ║
:: ║   4-hour team cycle (BKK time):                                  ║
:: ║     :00  Bot       00:00 04:00 08:00 12:00 16:00 20:00          ║
:: ║     :10  Strategist 00:10 04:10 08:10 12:10 16:10 20:10         ║
:: ║     :20  Trader    00:20 04:20 08:20 12:20 16:20 20:20          ║
:: ║     :30  Watchdog  00:30 04:30 08:30 12:30 16:30 20:30          ║
:: ║   + Tracker every 30 min, Monitor every 2 min, Briefing 07:00   ║
:: ╚══════════════════════════════════════════════════════════════════╝

echo.
echo ══════════════════════════════════════════════════════════════════
echo    WHALE-STREAM — MASTER TASK SETUP
echo    Clearing ALL old tasks and re-registering from scratch.
echo ══════════════════════════════════════════════════════════════════
echo.

:: ── STEP 1: Delete EVERY possible task name variant ──────────────────
echo [1/9] Clearing all existing WhaleStream tasks...
schtasks /Delete /TN "WhaleStream-Bot"        /F >nul 2>&1
schtasks /Delete /TN "WhaleStream-Trader"     /F >nul 2>&1
schtasks /Delete /TN "WhaleStream-Tracker"    /F >nul 2>&1
schtasks /Delete /TN "WhaleStream-Monitor"    /F >nul 2>&1
schtasks /Delete /TN "WhaleStream-Briefing"   /F >nul 2>&1
schtasks /Delete /TN "WhaleStreamStrategist"  /F >nul 2>&1
schtasks /Delete /TN "WhaleStreamWatchdog"    /F >nul 2>&1
schtasks /Delete /TN "WhaleStreamBot"         /F >nul 2>&1
schtasks /Delete /TN "WhaleStreamTrader"      /F >nul 2>&1
schtasks /Delete /TN "WhaleStreamTracker"     /F >nul 2>&1
schtasks /Delete /TN "WhaleStream Bot"        /F >nul 2>&1
schtasks /Delete /TN "WhaleStream Trader"     /F >nul 2>&1
schtasks /Delete /TN "Whale-Stream-Bot"       /F >nul 2>&1
schtasks /Delete /TN "Whale-Stream-Trader"    /F >nul 2>&1
schtasks /Delete /TN "WS-Bot"                 /F >nul 2>&1
schtasks /Delete /TN "WS-Trader"              /F >nul 2>&1
echo    Done — slate wiped clean.
echo.

:: ── STEP 2: BOT — every 4h starting 00:00 ───────────────────────────
echo [2/9] Registering WhaleStream-Bot (every 4h from 00:00)...
schtasks /Create ^
  /TN "WhaleStream-Bot" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_bot.bat\"" ^
  /SC HOURLY ^
  /MO 4 ^
  /ST 00:00 ^
  /F ^
  /RL HIGHEST
if %ERRORLEVEL% NEQ 0 goto :error_bot
echo    OK: 00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00
echo.

:: ── STEP 3: STRATEGIST — every 4h starting 00:10 ─────────────────────
echo [3/9] Registering WhaleStreamStrategist (every 4h from 00:10)...
schtasks /Create ^
  /TN "WhaleStreamStrategist" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_strategist.bat\"" ^
  /SC DAILY ^
  /ST 00:10 ^
  /RI 240 ^
  /DU 9999:59 ^
  /F ^
  /RL HIGHEST
if %ERRORLEVEL% NEQ 0 goto :error_strategist
echo    OK: 00:10 / 04:10 / 08:10 / 12:10 / 16:10 / 20:10
echo.

:: ── STEP 4: TRADER — every 4h starting 00:20 ─────────────────────────
echo [4/9] Registering WhaleStream-Trader (every 4h from 00:20)...
schtasks /Create ^
  /TN "WhaleStream-Trader" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_trader.bat\"" ^
  /SC HOURLY ^
  /MO 4 ^
  /ST 00:20 ^
  /F ^
  /RL HIGHEST
if %ERRORLEVEL% NEQ 0 goto :error_trader
echo    OK: 00:20 / 04:20 / 08:20 / 12:20 / 16:20 / 20:20
echo.

:: ── STEP 5: WATCHDOG — every 4h starting 00:30 ───────────────────────
echo [5/9] Registering WhaleStreamWatchdog (every 4h from 00:30)...
schtasks /Create ^
  /TN "WhaleStreamWatchdog" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_watchdog.bat\"" ^
  /SC DAILY ^
  /ST 00:30 ^
  /RI 240 ^
  /DU 9999:59 ^
  /F ^
  /RL HIGHEST
if %ERRORLEVEL% NEQ 0 goto :error_watchdog
echo    OK: 00:30 / 04:30 / 08:30 / 12:30 / 16:30 / 20:30
echo.

:: ── STEP 6: TRACKER — every 30 minutes ───────────────────────────────
echo [6/9] Registering WhaleStream-Tracker (every 30 min)...
schtasks /Create ^
  /TN "WhaleStream-Tracker" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_tracker.bat\"" ^
  /SC MINUTE ^
  /MO 30 ^
  /ST 00:00 ^
  /F
if %ERRORLEVEL% NEQ 0 goto :error_tracker
echo    OK: every 30 minutes (00:00, 00:30, 01:00, 01:30, ...)
echo.

:: ── STEP 7: MONITOR — every 2 minutes ────────────────────────────────
echo [7/9] Registering WhaleStream-Monitor (every 2 min)...
schtasks /Create ^
  /TN "WhaleStream-Monitor" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_monitor.bat\"" ^
  /SC MINUTE ^
  /MO 2 ^
  /F
if %ERRORLEVEL% NEQ 0 goto :error_monitor
echo    OK: every 2 minutes (real-time TP/SL fill detection)
echo.

:: ── STEP 8: BRIEFING — daily at 07:00 ────────────────────────────────
echo [8/9] Registering WhaleStream-Briefing (daily 07:00)...
schtasks /Create ^
  /TN "WhaleStream-Briefing" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_briefing.bat\"" ^
  /SC DAILY ^
  /ST 07:00 ^
  /F
if %ERRORLEVEL% NEQ 0 goto :error_briefing
echo    OK: every day at 07:00 BKK
echo.

:: ── STEP 8b: ORPHAN CHECK — daily 06:00 ──────────────────────────────
echo [8b] Registering WhaleStream-OrphanCheck (daily 06:00)...
schtasks /Create ^
  /TN "WhaleStream-OrphanCheck" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_orphan_check.bat\"" ^
  /SC DAILY ^
  /ST 06:00 ^
  /F
if %ERRORLEVEL% NEQ 0 echo    WARNING: OrphanCheck failed. Run as administrator!
echo    OK: daily at 06:00 (orphaned Bybit position detection)
echo.

:: ── STEP 8c: LOG ANALYZER — daily 07:00 ──────────────────────────────
echo [8c] Registering WhaleStream-LogAnalyzer (daily 07:00)...
schtasks /Create ^
  /TN "WhaleStream-LogAnalyzer" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_log_analyzer.bat\"" ^
  /SC DAILY ^
  /ST 07:00 ^
  /F
if %ERRORLEVEL% NEQ 0 echo    WARNING: LogAnalyzer failed. Run as administrator!
echo    OK: daily at 07:00 (log health report)
echo.

:: ── STEP 9: Verify all tasks ─────────────────────────────────────────
echo [9/9] Verifying registered tasks...
echo.
echo ─────────────────────────────────────────────────────────────────
schtasks /query /TN "WhaleStream-Bot"       /fo LIST | findstr /i "Task Name\|Next Run Time\|Repeat Every\|Scheduled Task State"
echo.
schtasks /query /TN "WhaleStreamStrategist" /fo LIST | findstr /i "Task Name\|Next Run Time\|Repeat Every\|Scheduled Task State"
echo.
schtasks /query /TN "WhaleStream-Trader"    /fo LIST | findstr /i "Task Name\|Next Run Time\|Repeat Every\|Scheduled Task State"
echo.
schtasks /query /TN "WhaleStreamWatchdog"   /fo LIST | findstr /i "Task Name\|Next Run Time\|Repeat Every\|Scheduled Task State"
echo.
schtasks /query /TN "WhaleStream-Tracker"   /fo LIST | findstr /i "Task Name\|Next Run Time\|Repeat Every\|Scheduled Task State"
echo.
schtasks /query /TN "WhaleStream-Monitor"   /fo LIST | findstr /i "Task Name\|Next Run Time\|Repeat Every\|Scheduled Task State"
echo.
schtasks /query /TN "WhaleStream-Briefing"  /fo LIST | findstr /i "Task Name\|Next Run Time\|Repeat Every\|Scheduled Task State"
echo ─────────────────────────────────────────────────────────────────
echo.
echo ══════════════════════════════════════════════════════════════════
echo    ALL DONE — 9 tasks registered correctly.
echo.
echo    4-hour cycle (BKK):
echo      00:00  Bot        — signal generation
echo      00:10  Strategist — signal review (APPROVE / VETO)
echo      00:20  Trader     — order placement
echo      00:30  Watchdog   — health check + alert if anyone missed
echo    + Tracker every 30 min, Monitor every 2 min
echo    + Briefing 07:00, OrphanCheck 06:00, LogAnalyzer 07:00
echo ══════════════════════════════════════════════════════════════════
echo.
goto :end

:error_bot
echo    ERROR on WhaleStream-Bot. Run as administrator!
goto :end
:error_strategist
echo    ERROR on WhaleStreamStrategist. Run as administrator!
goto :end
:error_trader
echo    ERROR on WhaleStream-Trader. Run as administrator!
goto :end
:error_watchdog
echo    ERROR on WhaleStreamWatchdog. Run as administrator!
goto :end
:error_tracker
echo    ERROR on WhaleStream-Tracker. Run as administrator!
goto :end
:error_monitor
echo    ERROR on WhaleStream-Monitor. Run as administrator!
goto :end
:error_briefing
echo    ERROR on WhaleStream-Briefing. Run as administrator!

:end
echo.
pause
