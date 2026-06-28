@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.5 final — 9 bugs fixed: HTML race (trader+briefing), WLD blocklist, debrief pnl fix, allocated counter, Bybit alert, version sync"
git push
echo.
echo Done — v47.5 final pushed to GitHub.
pause
