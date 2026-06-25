@echo off
REM ╔══════════════════════════════════════════════════════════════╗
REM ║   ADD_STRATEGIST_TASK.bat                                   ║
REM ║                                                             ║
REM ║  Schedules whale_stream_strategist.py in Windows Task       ║
REM ║  Scheduler to run at :10 past every 4-hour mark (BKK).     ║
REM ║                                                             ║
REM ║  Timing:  00:10  04:10  08:10  12:10  16:10  20:10         ║
REM ║  This gives the Bot 10 min to generate signals (:00)       ║
REM ║  and the Strategist 10 min to review before Trader (:20)   ║
REM ║                                                             ║
REM ║  RUN AS ADMINISTRATOR                                       ║
REM ╚══════════════════════════════════════════════════════════════╝

echo.
echo Adding WHALE-STREAM STRATEGIST to Task Scheduler...
echo Run times: 00:10, 04:10, 08:10, 12:10, 16:10, 20:10 BKK
echo.

REM Detect Python executable
set PYTHON_EXE=
where py >nul 2>&1 && set PYTHON_EXE=py
if "%PYTHON_EXE%"=="" (
    where python >nul 2>&1 && set PYTHON_EXE=python
)
if "%PYTHON_EXE%"=="" (
    set PYTHON_EXE=C:\Users\MAX\AppData\Local\Python\bin\python.exe
)
echo Using Python: %PYTHON_EXE%

REM Script and log paths
set SCRIPT_PATH=C:\Users\MAX\WhaleStream\whale_stream_strategist.py
set LOG_PATH=C:\Users\MAX\WhaleStream\strategist_task_log.txt

REM Delete existing task if present (clean re-register)
schtasks /delete /tn "WhaleStreamStrategist" /f >nul 2>&1

REM Create task — runs every 4 hours starting at 00:10
schtasks /create ^
  /tn "WhaleStreamStrategist" ^
  /tr "\"%PYTHON_EXE%\" \"%SCRIPT_PATH%\" >> \"%LOG_PATH%\" 2>&1" ^
  /sc DAILY ^
  /st 00:10 ^
  /ri 240 ^
  /du 9999:59 ^
  /f ^
  /rl HIGHEST

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS — WhaleStreamStrategist task created!
    echo.
    echo Schedule:
    schtasks /query /tn "WhaleStreamStrategist" /fo LIST
) else (
    echo.
    echo ERROR — Task creation failed. Make sure you ran this as Administrator.
    echo Right-click this .bat file and choose "Run as administrator"
)

echo.
echo Current WHALE-STREAM team schedule:
echo   00:00  04:00  08:00  12:00  16:00  20:00  ^<-- Bot (Scout)
echo   00:10  04:10  08:10  12:10  16:10  20:10  ^<-- Strategist (Council)
echo   00:20  04:20  08:20  12:20  16:20  20:20  ^<-- Trader (Executor)
echo   every 30 min                               ^<-- Tracker (Resolver)
echo   7:00 AM daily                              ^<-- Morning Briefing
echo.
pause
