@echo off
cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
:: Stderr goes to a SEPARATE file — prevents file-handle conflicts when Python
:: crashes during interpreter shutdown ("lost sys.stderr" / ValueError on closed file).
:: Keeping stderr separate also means Task Scheduler's cmd.exe wrapper exits cleanly
:: even if Python's shutdown hook writes one last error to stderr.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" whale_stream_strategist.py >> "C:\Users\MAX\WhaleStream\strategist_task_log.txt" 2>> "C:\Users\MAX\WhaleStream\strategist_task_err.txt"
exit /b 0
