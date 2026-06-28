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
git commit -m "v46.76 — FIX: cycle guard added to Strategist + Trader; CHANGE_TO_2H.bat deleted"
echo.

echo [4] Pushing to remote (setting upstream on first push)...
git push --set-upstream origin main
echo.

echo ══════════════════════════════════════════════
echo   Done. Check output above for errors.
echo ══════════════════════════════════════════════
pause
