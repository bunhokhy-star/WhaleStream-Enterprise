@echo off
echo ══════════════════════════════════════════════
echo   WHALE-STREAM — Push to GitHub
echo ══════════════════════════════════════════════
echo.

cd /d "C:\Users\MAX\WhaleStream"

echo [1] Git status...
git status
echo.

echo [2] Staging all changes...
git add -A
echo.

echo [3] Committing...
git commit -m "v46.96 — Full audit + 14 fixes: monitor demo-header conditional (go-live blocker), strategist emoji direction fix (P0 — was silently dropping all signals), monitor f-string crash on zero SL, monitor live avgPrice for SL-to-BE, bot JSON_END rescue + cross-direction conflict guard, trader timestamp skip + balance refresh, debrief max_tokens 450, tracker balance is-not-None guard, briefing drawdown clamp + json= Telegram"
echo.

echo [4] Pushing to remote (setting upstream on first push)...
git push --set-upstream origin main
echo.

echo ══════════════════════════════════════════════
echo   Done. Check output above for errors.
echo ══════════════════════════════════════════════
pause
