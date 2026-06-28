@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.2 — full code audit: BKK constants, remove redundant imports, dead code, /ru SYSTEM in all schtasks (+ 2 missed BKK replacements in bot.py main)"
git push
echo.
echo Done — v47.2 pushed to GitHub.
pause
