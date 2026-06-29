@echo off
cd /d C:\Users\MAX\WhaleStream
git add -A
git commit -m "v47.10 — 11 bugs: monitor crash hidden (CRITICAL), trader SHORT floor 95->conditional (HIGH), bot short_wr neutral fallback (HIGH), SL sweep during CB (HIGH), debrief resolved_at dedup key (HIGH), balance warn sentinel (HIGH), partial close TP1 label (MEDIUM), status_server normpath (MEDIUM), gap checker midnight (MEDIUM), tracker Gate3 pnl >=5->>=1.5 (MEDIUM), JULY1 checklist fixes + version bumps"
git push
echo.
echo Done — v47.10 pushed to GitHub.
pause
