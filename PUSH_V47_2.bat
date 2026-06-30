@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.23 — AVOID lesson injection into bot prompt; auto-tune score floor (scorer_config.json); score tag in debrief Telegram; weekly health card"
git push
echo.
echo Done — v47.23 pushed to GitHub.
pause
