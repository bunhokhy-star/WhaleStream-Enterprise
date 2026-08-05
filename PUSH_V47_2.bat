@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.67 — Remove static coin blocklists: market decides, not us"
git push
echo.
echo Done — v47.67 pushed to GitHub.
pause
