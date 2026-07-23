@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.60 — P5B consecutive-loss auto-block in debrief + telegram_commands manual-block tracking"
git push
echo.
echo Done — v47.60 pushed to GitHub.
pause
