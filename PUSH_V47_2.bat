@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.12 — CB grace period 60min→480min (prevents re-trigger for 8h); FIX_CB_NOW.bat; Strategist self-healing; run_strategist.bat stderr fix"
git push
echo.
echo Done — v47.12 pushed to GitHub.
pause
