@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.21 — Signal score gate (score<5 skip); adaptive confidence floors (coin_stats); MTF freshness re-check 0.5x penalty in trader"
git push
echo.
echo Done — v47.21 pushed to GitHub.
pause
