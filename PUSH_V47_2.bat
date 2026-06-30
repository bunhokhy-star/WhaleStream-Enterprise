@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.17 — MTF chart analysis: real 4H+1H OHLCV candles injected into Claude signals; VETO rule 6 for 4H_SIDEWAYS bias; mtf_bias field in every signal JSON"
git push
echo.
echo Done — v47.17 pushed to GitHub.
pause
