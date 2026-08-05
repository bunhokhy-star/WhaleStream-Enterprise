@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.68 — Remove all auto-blocklist + probation infrastructure: market decides"
git push
echo.
echo Done — v47.67 + v47.68 pushed to GitHub.
pause
