@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.16 — monitor.py: auto-place 4x25% TP reduce-only orders when new position detected (fixes 'current position is zero' TP failures after limit entry fills)"
git push
echo.
echo Done — v47.16 pushed to GitHub.
pause
