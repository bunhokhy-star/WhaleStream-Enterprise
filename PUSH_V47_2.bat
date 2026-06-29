@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.15 — Clean-system pass: 12 fixes across 8 files (stdout reconfigure, REDUCE_SIZE clamp order, veto coin+direction match, cycle guard midnight split, Gate 6 consec display, monitor clock-skew -3000ms, pnl_pct is not None, trade_id row index, Gate 1 div-by-zero, BTC price is not None, health check status==200, version bumps)"
git push
echo.
echo Done — v47.15 pushed to GitHub.
pause
