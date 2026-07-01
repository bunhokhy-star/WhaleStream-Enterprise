@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.48 — fix Strategist checklist ghost: _mark_done before send_telegram (6 paths) + crash safety net; CB threshold 3->5"
git push
echo.
echo Done — v47.48 pushed to GitHub.
pause
