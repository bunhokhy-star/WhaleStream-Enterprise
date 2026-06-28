@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo Staging all changes...
git add -A
echo.
echo Committing v47.1...
git commit -m "v47.1 — 17 fixes: watchdog Tracker/Monitor dynamic health check, morning_briefing bal NameError, tracker Gate4 flat-account bug, Monday Gate1 definition (volume 150), WR decay threshold 5->20, debrief banner+os alias, tracker redundant imports x4, ADD_RECHECK_TASKS version bump"
echo.
echo Pushing to GitHub...
git push --set-upstream origin main
echo.
echo Done!
pause
