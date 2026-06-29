@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.7 — 12 fixes: Daily Checklist offline (UTC/BKK date mismatch), Strategist circuit breaker skip, Trader confidence floor + TP KeyError + min_q inflation + reactive scan, bot SHORT floor thresholds, debrief JS write, watchdog regex fallback, gap-check briefing guard, DELETE_PAUSE disabled, status_server IPv4 bind"
git push
echo.
echo Done — v47.7 pushed to GitHub.
pause
