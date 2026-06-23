@echo off
cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" check_bybit_orphans.py >> "C:\Users\MAX\WhaleStream\orphan_log.txt" 2>&1
