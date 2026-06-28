@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.5 final — 12 bugs fixed: HTML race (trader+briefing+tracker), WLD blocklist, debrief pnl fix, allocated counter, Bybit alert, strategist/scorer version sync, bot confidence floor"
git push
echo.
echo Done — v47.5 final pushed to GitHub.
pause
