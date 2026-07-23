@echo off
echo === Pulling v47.60 on server 152.42.224.87 ===
ssh root@152.42.224.87 "cd /opt/whalestream && git pull && echo '=== Pull complete ===' && python3 -c 'import sys; print(sys.version)' && ls -la whale_stream_debrief.py telegram_commands.py"
echo.
echo Done — server is up to date.
pause
