@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.22 — Scorer feedback loop (debrief saves score; score-tier WR in analyze_shorts); dynamic signal count (BTC 4H regime 2+2 to 4+2); entry hit-rate analysis"
git push
echo.
echo Done — v47.22 pushed to GitHub.
pause
