@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.49 — trader: always full size ($200); REDUCE→VETO, remove MTF+score size penalties"
git push
echo.
echo Done — v47.49 pushed to GitHub.
pause
