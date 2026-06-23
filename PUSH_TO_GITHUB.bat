@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo ============================================
echo  WHALE-STREAM Push to GitHub
echo ============================================
echo.

REM Stage all changes
git add .

REM Commit with today's date
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
set TODAY=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%
git commit -m "v46.38 — %TODAY% README + local_config.py.example added"

echo.
echo Pushing to GitHub...
git push origin main

echo.
if %ERRORLEVEL% EQU 0 (
    echo ============================================
    echo  Pushed successfully!
    echo ============================================
) else (
    echo ============================================
    echo  Push failed. You may need to:
    echo  1. Set remote: git remote add origin https://github.com/bunhokhy-star/WhaleStream-Enterprise.git
    echo  2. Authenticate via GitHub Desktop or a Personal Access Token
    echo ============================================
)
echo.
pause
