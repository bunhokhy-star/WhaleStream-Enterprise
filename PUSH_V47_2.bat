@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.6 — 6 bugs fixed: SL sweep false-fires (Bybit order-level SL detection), TP orphan cancel, SL-to-BE 50%->25% text, bot/strategist 93%->95% SHORT floor, signal_scorer threshold rename, morning_briefing version"
git push
echo.
echo Done — v47.6 pushed to GitHub.
pause
