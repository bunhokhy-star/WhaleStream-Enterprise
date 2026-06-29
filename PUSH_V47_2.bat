@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.14 — CRITICAL: fix Strategist crash (signal_scorer.py tuple[int,str] Python<3.9 TypeError killed Strategist at module level; add from __future__ import annotations); widen except ImportError→Exception for signal_scorer+trade_logger; replace TextIOWrapper double-wrap with reconfigure() to eliminate shutdown ValueError"
git push
echo.
echo Done — v47.14 pushed to GitHub.
pause
