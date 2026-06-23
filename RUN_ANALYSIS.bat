@echo off
cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo Running SHORT win rate analysis...
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" -X utf8 analyze_shorts.py
echo.
echo Done! Results in analysis_shorts.txt
echo.
pause
