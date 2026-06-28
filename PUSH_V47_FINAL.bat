@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo Staging all changes...
git add -A
echo.
echo Committing v47.0 final (second-round audit fixes)...
git commit -m "v47.0 final — 23 more fixes: BKK clock systemic fix in 6 agents (_mark_done + cycle guards), TOP-3 LONG prompt token fix, tracker TP4 upgrade, utcnow deprecation, COL_RESOLVED_AT shadow, monitor redundant imports, briefing balance re-read, BAT /ru autonomy bug, SETUP_ALL_TASKS /RL HIGHEST, ADD_RECHECK_TASKS version bump"
echo.
echo Pushing to GitHub...
git push --set-upstream origin main
echo.
echo Done!
pause
