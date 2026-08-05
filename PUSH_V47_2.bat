@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.72 — BUG FIX: market intel rate limiting — add sleep between layers so momentum + OI delta return data"
git push
echo.
echo Done — v47.72 pushed to GitHub.
pause
