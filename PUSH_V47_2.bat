@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.42 — signal quality #2: ENA->LONG blocklist, streak trap warning (>=3 consec losses), H SHORT price floor (<$0.05 suppressed), SHORT slots 3->4 in BTC bear (-3%)"
git push
echo.
echo Done — v47.42 pushed to GitHub.
pause
