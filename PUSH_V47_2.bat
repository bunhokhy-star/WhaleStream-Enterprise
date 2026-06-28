@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.4 — Full wiring: trade_logger history into scorer WR dimension, debrief auto-sync, go-live test suite (test_golive.py)"
git push
echo.
echo Done — v47.4 pushed to GitHub.
pause
