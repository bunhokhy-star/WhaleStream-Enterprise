@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.60 — Fix Daily Checklist: status_server.py added to server crontab + bot.py label fixes"
git push
echo.
echo Done — v47.60 pushed to GitHub.
pause
