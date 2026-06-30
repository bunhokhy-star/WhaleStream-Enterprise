@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.27 — Fix ts in debrief records; score accuracy actions; per-coin 4H regime filter"
git push
echo.
echo Done — v47.27 pushed to GitHub.
pause
