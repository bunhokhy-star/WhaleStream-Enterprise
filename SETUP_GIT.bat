@echo off
cd /d "C:\Users\MAX\WhaleStream"

echo ============================================
echo  WHALE-STREAM Git Repository Setup
echo ============================================
echo.

git init
git config user.email "sitha.in0123@gmail.com"
git config user.name "MAX"

echo.
echo Adding all files (secrets + logs excluded by .gitignore)...
git add .

echo.
git commit -m "Initial commit — WHALE-STREAM v46.36

Features:
- whale_stream_bot.py — Signal generator (Claude AI, every 4h)
- whale_stream_tracker.py — WIN/LOSS resolver + dashboard (every 30min)
- whale_stream_trader.py — Bybit Demo auto-trader (every 4h+20min)
- whale_stream_monitor.py — Near-real-time fill detector (every 2min)
- morning_briefing.py — Daily 7am Telegram briefing
- analyze_shorts.py — Gate analysis + SHORT recovery report

Current status: Gate 1 = 105/150 (70pct), WR = 60pct, 15x WIN streak"

echo.
echo ============================================
echo  Done! Git repo initialized at v46.36.
echo  Run 'git log --oneline' to verify.
echo ============================================
echo.
pause
