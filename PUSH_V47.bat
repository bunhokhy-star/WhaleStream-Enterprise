@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo Staging all changes...
git add -A
echo.
echo Committing v47.0...
git commit -m "v47.0 — 9 critical fixes: PARTIAL_CLOSE_RATIO 0.60->0.85 (Quad-TP TP1 detection restored), be_set propagation on TP2/TP3 state updates, rescue_msg content guard, morning_briefing P&L [B] suffix parser, watchdog STRATEGIST_LOG filename corrected, BKK clock fixes in watchdog+strategist _mark_done+cycle_guard, trader API failure log"
echo.
echo Pushing to GitHub...
git push --set-upstream origin main
echo.
echo Done!
pause
