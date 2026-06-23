@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo ============================================
echo  WHALE-STREAM v46.38 — Force Push to GitHub
echo ============================================
echo.

REM Set / update remote origin
git remote remove origin 2>nul
git remote add origin https://github.com/bunhokhy-star/WhaleStream-Enterprise.git
echo Remote set to: https://github.com/bunhokhy-star/WhaleStream-Enterprise.git
echo.

REM Stage everything and commit
git add .
git commit -m "v46.38 — 2026-06-23 Macro event guard + token unlock calendar" 2>nul
echo.

REM Force-push (overwrites the old enterprise codebase in the remote)
echo Pushing to GitHub...
git push --force origin main
echo.

if %ERRORLEVEL% EQU 0 (
    echo ============================================
    echo  SUCCESS! v46.38 is live on GitHub.
    echo ============================================
) else (
    echo ============================================
    echo  PUSH FAILED (error %ERRORLEVEL%)
    echo  If prompted for credentials:
    echo    Username: your GitHub username
    echo    Password: your Personal Access Token
    echo    (NOT your GitHub password - a PAT from
    echo     github.com/settings/tokens)
    echo ============================================
)
echo.
timeout /t 60
