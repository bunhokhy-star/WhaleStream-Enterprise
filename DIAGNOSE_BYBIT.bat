@echo off
echo ══════════════════════════════════════════════
echo   WHALE-STREAM — Bybit API Diagnostic
echo ══════════════════════════════════════════════
echo.

cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

"C:\Users\MAX\AppData\Local\Python\bin\python.exe" diagnose_bybit.py

echo.
pause
