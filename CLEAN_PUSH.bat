@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo ============================================
echo  WHALE-STREAM v46.38 — Clean Push to GitHub
echo  (Squashes history to remove old secrets)
echo ============================================
echo.

REM Set remote
git remote remove origin 2>nul
git remote add origin https://github.com/bunhokhy-star/WhaleStream-Enterprise.git
echo Remote: https://github.com/bunhokhy-star/WhaleStream-Enterprise.git
echo.

REM Create orphan branch (no history) and commit all current files
echo Creating fresh commit with no old history...
git checkout --orphan clean_start
git add .
git commit -m "v46.38 — 2026-06-23 Macro event guard + token unlock calendar"
echo.

REM Rename to main and delete old main
git branch -D main 2>nul
git branch -m main
echo.

REM Force push clean history
echo Pushing to GitHub...
git push --force origin main
echo.

if %ERRORLEVEL% EQU 0 (
    echo ============================================
    echo  SUCCESS! v46.38 is live on GitHub.
    echo  (History squashed — no secrets in repo)
    echo ============================================
) else (
    echo ============================================
    echo  PUSH FAILED (error %ERRORLEVEL%)
    echo ============================================
)
echo.
timeout /t 60
