@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.48 — monitor: re-verify TPs every cycle for existing positions; add SYNC_STATUS.bat for checklist fallback"
git push
echo.
echo Done — v47.48 pushed to GitHub.
pause
