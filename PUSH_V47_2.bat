@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.13 — Audit fixes: place_quad_tp_closes allocated bug; redundant balance file reads; watchdog deadline 22→25; _wdog_excepthook _mark_done; Get-CimInstance; morning_briefing cb_grace visibility; version bumps"
git push
echo.
echo Done — v47.13 pushed to GitHub.
pause
