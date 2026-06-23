@echo off
echo Adding WhaleStream-Briefing to Task Scheduler...
schtasks /Create ^
  /TN "WhaleStream-Briefing" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_briefing.bat\"" ^
  /SC DAILY ^
  /ST 07:00 ^
  /F
if %ERRORLEVEL% NEQ 0 goto :error
echo SUCCESS! Daily 7am briefing scheduled.
goto :end
:error
echo ERROR: Run as administrator.
:end
pause
