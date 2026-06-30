@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.18 — MTF learning loop: debrief records mtf_bias outcomes + mtf_stats WR; graveyard MTF table; calc_qty overdeploy fix (#299); orphaned TP auto-cancel (#300)"
git push
echo.
echo Done — v47.18 pushed to GitHub.
pause
