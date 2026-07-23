@echo off
echo.
echo ============================================================
echo  WHALE-STREAM v47.60 — Install Server Crontab
echo  Server: 152.42.224.87 (DigitalOcean Ubuntu VPS)
echo  This moves ALL scheduling OFF your PC onto the server.
echo  After this, the system runs 24/7 even when PC is off.
echo ============================================================
echo.
echo Step 1: Upload the setup script to the server...
scp C:\Users\MAX\WhaleStream\SERVER_CRON_SETUP.sh root@152.42.224.87:/opt/whalestream/
echo.
echo Step 2: Make it executable and run it...
ssh root@152.42.224.87 "chmod +x /opt/whalestream/SERVER_CRON_SETUP.sh && bash /opt/whalestream/SERVER_CRON_SETUP.sh"
echo.
echo ============================================================
echo  DONE — Crontab is live on the server.
echo.
echo  Schedule (UTC times):
echo    Bot         :00 every 4h
echo    Strategist  :10 every 4h
echo    Trader      :20 every 4h
echo    Watchdog    :30 every 4h
echo    Monitor     every 2 min
echo    Tracker     every 30 min
echo    Briefing    00:00 UTC = 07:00 BKK
echo.
echo  To verify: ssh root@152.42.224.87
echo             then: crontab -l
echo.
echo  IMPORTANT: Disable Windows Task Scheduler tasks after
echo  confirming server cron is running correctly!
echo  (Keep them as backup for first 2 days.)
echo ============================================================
echo.
pause
