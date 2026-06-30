@echo off
REM ══════════════════════════════════════════════════════════════
REM  WHALE-STREAM — Schedule weekly scorecard + command handler
REM  Run this ONCE as Administrator on the server
REM
REM  Weekly scorecard: every Monday 07:00 BKK (= Monday 00:00 UTC)
REM  Command handler:  every hour (checks for YES/NO replies)
REM ══════════════════════════════════════════════════════════════

echo Adding Weekly Scorecard task (Monday 07:00 BKK = 00:00 UTC)...
schtasks /create /tn "WhaleStream-Weekly" ^
  /tr "python C:\Users\MAX\WhaleStream\whale_stream_weekly.py >> C:\Users\MAX\WhaleStream\weekly_log.txt 2>&1" ^
  /sc WEEKLY /d MON /st 00:00 ^
  /ru SYSTEM /f
echo Done.

echo.
echo Adding Telegram Command Handler task (every hour)...
schtasks /create /tn "WhaleStream-Commands" ^
  /tr "python C:\Users\MAX\WhaleStream\telegram_commands.py >> C:\Users\MAX\WhaleStream\commands_log.txt 2>&1" ^
  /sc HOURLY /mo 1 ^
  /ru SYSTEM /f
echo Done.

echo.
echo ══════════════════════════════════════════════════
echo  Tasks created:
echo    WhaleStream-Weekly  — Mon 00:00 UTC (07:00 BKK)
echo    WhaleStream-Commands — every hour
echo ══════════════════════════════════════════════════
pause
