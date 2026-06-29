@echo off
:: ADD_SYNC_STATUS_TASK.bat
:: Schedules sync_status.py to run every 5 minutes on Windows.
:: This keeps the Daily Checklist Cowork widget live by syncing
:: daily_status.json from DigitalOcean (152.42.224.87) to this machine.
:: Run as Administrator.

SCHTASKS /CREATE ^
  /TN "WHALE-STREAM\SyncStatus" ^
  /TR "python C:\Users\MAX\WhaleStream\sync_status.py" ^
  /SC MINUTE /MO 5 ^
  /F

echo.
echo Done — SyncStatus task created (every 5 min).
echo Daily Checklist will now auto-refresh in the Cowork panel.
pause
