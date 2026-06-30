@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.40 — bug fixes: Python 3.8 dict-merge compat, Sunday digest dedup, fromisoformat tz suffix, blended P&L 25/75->50/50, P&L velocity year key, MTF floor clamp, already_active.add, SL warn false-positive, R:R None guard"
git push
echo.
echo Done — v47.40 pushed to GitHub.
pause
