@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.11 — Strategist self-healing: watchdog kills zombie processes + relaunches automatically; run_strategist.bat stderr separated to prevent shutdown crash deadlock"
git push
echo.
echo Done — v47.11 pushed to GitHub.
pause
