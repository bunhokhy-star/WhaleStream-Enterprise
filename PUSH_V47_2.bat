@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.65 — Active position management: progressive trailing SL + BTC reversal close + watchdog emergency close"
git push
echo.
echo Done — v47.65 pushed to GitHub.
pause
