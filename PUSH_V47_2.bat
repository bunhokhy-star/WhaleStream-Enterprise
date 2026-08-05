@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.69 — SERVER_CRON_SETUP.sh: fix morning_briefing filename + add recheck/reactive/gap-checker/tg-commands; v47.68 remove auto-blocklist + probation"
git push
echo.
echo Done — v47.67 + v47.68 + v47.69 pushed to GitHub.
pause
