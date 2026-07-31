@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.62 — DEXE blocklist + pnl_pct computed from prices"
git push
echo.
echo Done — v47.62 pushed to GitHub.
pause
