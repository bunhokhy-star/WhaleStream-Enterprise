@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.43 — signal quality #3: LONG proven whitelist (prompt+code filter >=60%WR>=3T needs 95% conf if unproven), SHORT proven list prompt injection (100%WR>=2T)"
git push
echo.
echo Done — v47.43 pushed to GitHub.
pause
