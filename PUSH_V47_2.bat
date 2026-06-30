@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.24 — Score-based position sizing (9-10=1.0x, 7-8=0.85x, 5-6=0.70x); time-of-day WR by 4h BKK slot; holding period analysis; resolved_at field fix"
git push
echo.
echo Done — v47.24 pushed to GitHub.
pause
