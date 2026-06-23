@echo off
cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" whale_stream_tracker.py >> "C:\Users\MAX\WhaleStream\tracker_log.txt" 2>&1
