@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.71 — BUG FIX: WR ranking used wrong field name (outcome vs status) — ranking was inactive; fix gap checker cron instructions"
git push
echo.
echo Done — v47.71 pushed to GitHub.
pause
