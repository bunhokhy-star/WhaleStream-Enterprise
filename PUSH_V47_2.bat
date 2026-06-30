@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.31 — score gate status in briefing; blocklist aging 7d; dim correlation tracking"
git push
echo.
echo Done — v47.31 pushed to GitHub.
pause
