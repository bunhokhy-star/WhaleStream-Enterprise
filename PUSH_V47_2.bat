@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.4 — Final pre-go-live audit: 12 bugs fixed (pattern scoring, BKK timestamp, HTML race condition, crash guard, atomic write, Gate 6)"
git push
echo.
echo Done — v47.4 pushed to GitHub.
pause
