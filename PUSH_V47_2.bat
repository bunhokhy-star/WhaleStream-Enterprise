@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.9 — 24 fixes: includes all v47.8 fixes (Bot CB check, TP allocated bug, debrief dedup, status_server security, CB grace, Strategist recheck, blended P&L, pause spam, scorer 88pct, watchdog PAUSED, debrief timeout, monitor mark_done, briefing self-coverage, conflict guard, WLD prompt, P&L sign, cb_alerted flag) + v47.9 (CLEAR_BREACH_NOW YES confirm, briefing log scan 100->500 + 2000->5000)"
git push
echo.
echo Done — v47.9 pushed to GitHub.
pause
