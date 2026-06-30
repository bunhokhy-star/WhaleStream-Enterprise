@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.41 — signal quality: BTC 24h LONG cap (0 at -5%, 1 at -3%), CHZ->SHORT blocklist, XLM->LONG blocklist, fetch_btc_24h_momentum returns float tuple"
git push
echo.
echo Done — v47.41 pushed to GitHub.
pause
