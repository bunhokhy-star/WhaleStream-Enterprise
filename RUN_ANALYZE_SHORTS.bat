@echo off
cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo Running analyze_shorts.py...
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" analyze_shorts.py > analyze_shorts_output.txt 2>&1
echo.
echo Done! Output saved to analyze_shorts_output.txt
pause
