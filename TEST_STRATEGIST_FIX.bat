@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo.
echo ========================================================
echo   Testing Strategist v47.14 fix
echo   Output goes to: strat_test_v4714.txt
echo ========================================================
echo.
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" whale_stream_strategist.py > strat_test_v4714.txt 2>&1
echo.
echo --- First 30 lines of output ---
type strat_test_v4714.txt | more /P /C 30
echo.
echo ========================================================
echo   If you see the banner above, the crash is fixed!
echo   If you see "ValueError" with no banner, still broken.
echo ========================================================
pause
