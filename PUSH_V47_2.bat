@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.3 — Signal Scorer + Trade Logger: pre-Claude quality gate (5-dimension scoring), persistent WIN/LOSS log with stats engine, MASTER_PLAN.md"
git push
echo.
echo Done — v47.3 pushed to GitHub.
pause
