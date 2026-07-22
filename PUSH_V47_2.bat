@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.51 — tracker: Gate 6 WR-based weekly streak (fixes 0/3 bug caused by P&L tracking gap)"
git push
echo.
echo Done — v47.51 pushed to GitHub.
pause
