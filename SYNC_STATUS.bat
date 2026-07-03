@echo off
REM ═══════════════════════════════════════════════════════════════
REM  WHALE-STREAM STATUS SYNC
REM  Pulls daily_status.json from server → local WhaleStream folder
REM  Run every 5 minutes via Task Scheduler so Daily Checklist
REM  always has fresh data even when the STATUS_URL fetch is blocked
REM  by the Cowork sandbox.
REM ═══════════════════════════════════════════════════════════════

curl -s -m 10 http://152.42.224.87:8765/daily_status.json -o "C:\Users\MAX\WhaleStream\daily_status.json"
if errorlevel 1 (
    echo [%time%] SYNC FAILED — server unreachable
) else (
    echo [%time%] SYNC OK — daily_status.json updated
)
