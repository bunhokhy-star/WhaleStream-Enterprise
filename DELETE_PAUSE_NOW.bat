@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo Deleting paused.flag...
del /f "paused.flag"
if exist "paused.flag" (
    echo FAILED — paused.flag still exists!
) else (
    echo ================================================
    echo  Circuit breaker CLEARED! Trader will resume
    echo  on next scheduled run.
    echo ================================================
)
echo.
pause
