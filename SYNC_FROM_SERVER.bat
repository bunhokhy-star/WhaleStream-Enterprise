@echo off
echo.
echo ============================================
echo  WHALE-STREAM — Sync runtime files from server
echo  Server: 152.42.224.87
echo  Target: C:\Users\MAX\WhaleStream\
echo  (You may be prompted for password once per file)
echo ============================================
echo.

set SERVER=root@152.42.224.87
set SRC=/opt/whalestream
set DST=C:\Users\MAX\WhaleStream\

echo [1/9] bybit_balance.json ...
scp %SERVER%:%SRC%/bybit_balance.json "%DST%"

echo [2/9] daily_status.json ...
scp %SERVER%:%SRC%/daily_status.json "%DST%"

echo [3/9] trade_log.json ...
scp %SERVER%:%SRC%/trade_log.json "%DST%"

echo [4/9] strategist_decisions.json ...
scp %SERVER%:%SRC%/strategist_decisions.json "%DST%"

echo [5/9] market_context.json ...
scp %SERVER%:%SRC%/market_context.json "%DST%"

echo [6/9] milestone_state.json ...
scp %SERVER%:%SRC%/milestone_state.json "%DST%"

echo [7/9] trader_skips.json ...
scp %SERVER%:%SRC%/trader_skips.json "%DST%"

echo [8/9] pattern_memory.json (may not exist yet) ...
scp %SERVER%:%SRC%/pattern_memory.json "%DST%" 2>nul

echo [9/9] dynamic_blocklist.json (may not exist yet) ...
scp %SERVER%:%SRC%/dynamic_blocklist.json "%DST%" 2>nul

echo.
echo ============================================
echo  Done. Files synced to C:\Users\MAX\WhaleStream\
echo  NOTE: google_credentials.json intentionally excluded.
echo ============================================
echo.
pause
