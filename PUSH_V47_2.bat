@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.5 — SL guard sweep: auto-restore missing stop-losses every cycle (critical capital protection)"
git push
echo.
echo Done — v47.4 pushed to GitHub.
pause
