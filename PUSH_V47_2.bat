@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.8 — 21 fixes: Bot CB check missing, Trader TP allocated bug, debrief dedup drops 2nd trade, status_server security patch, check_daily_status localhost fix, Strategist recheck bypasses CB, blended P&L 25/75, Trader pause spam sentinel, scorer threshold 88%, watchdog PAUSED timestamp, debrief Claude timeout+try/except, monitor _mark_done on failure, briefing self-coverage noise, conflict guard ordering, WLD prompt gap, P&L sign filters, CLEAR_PAUSE cb_alerted flag"
git push
echo.
echo Done — v47.7 pushed to GitHub.
pause
