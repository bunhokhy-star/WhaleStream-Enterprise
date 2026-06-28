@echo off
:: ════════════════════════════════════════════════════════════════════
:: ADD_RECHECK_TASKS.bat
:: Registers 6 Task Scheduler entries for the v47.0 continuous
:: decision loop:
::
::   Strategist re-checks  (rules-only, no Claude)
::     01:10, 05:10, 09:10, 13:10, 17:10, 21:10  →  task _A (every 4h from 01:10)
::     02:10, 06:10, 10:10, 14:10, 18:10, 22:10  →  task _B (every 4h from 02:10)
::     03:10, 07:10, 11:10, 15:10, 19:10, 23:10  →  task _C (every 4h from 03:10)
::
::   Trader reactive runs  (place new approvals / cancel vetoed)
::     01:15, 05:15, 09:15, 13:15, 17:15, 21:15  →  task _A (every 4h from 01:15)
::     02:15, 06:15, 10:15, 14:15, 18:15, 22:15  →  task _B (every 4h from 02:15)
::     03:15, 07:15, 11:15, 15:15, 19:15, 23:15  →  task _C (every 4h from 03:15)
::
:: RUN AS ADMINISTRATOR — required to register tasks
:: ════════════════════════════════════════════════════════════════════

SET SCRIPT_DIR=%~dp0
SET SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
SET PYTHON=%SCRIPT_DIR%\run_strategist_recheck.bat
SET TRADER=%SCRIPT_DIR%\run_trader_reactive.bat

echo ══════════════════════════════════════════════════════
echo   WHALE-STREAM v47.0 — Continuous Decision Loop
echo   Task Scheduler Installer
echo ══════════════════════════════════════════════════════
echo.

:: ── Strategist Re-check A  (01:10 every 4h) ─────────────────
schtasks /create ^
  /tn "WhaleStream-Strategist-Recheck-A" ^
  /tr "\"%PYTHON%\"" ^
  /sc HOURLY /mo 4 /st 01:10 ^
  /rl HIGHEST ^
  /f
echo [A] Strategist re-check A registered (01:10 +4h)

:: ── Strategist Re-check B  (02:10 every 4h) ─────────────────
schtasks /create ^
  /tn "WhaleStream-Strategist-Recheck-B" ^
  /tr "\"%PYTHON%\"" ^
  /sc HOURLY /mo 4 /st 02:10 ^
  /rl HIGHEST ^
  /f
echo [B] Strategist re-check B registered (02:10 +4h)

:: ── Strategist Re-check C  (03:10 every 4h) ─────────────────
schtasks /create ^
  /tn "WhaleStream-Strategist-Recheck-C" ^
  /tr "\"%PYTHON%\"" ^
  /sc HOURLY /mo 4 /st 03:10 ^
  /rl HIGHEST ^
  /f
echo [C] Strategist re-check C registered (03:10 +4h)

echo.

:: ── Trader Reactive A  (01:15 every 4h) ──────────────────────
schtasks /create ^
  /tn "WhaleStream-Trader-Reactive-A" ^
  /tr "\"%TRADER%\"" ^
  /sc HOURLY /mo 4 /st 01:15 ^
  /rl HIGHEST ^
  /f
echo [D] Trader reactive A registered (01:15 +4h)

:: ── Trader Reactive B  (02:15 every 4h) ──────────────────────
schtasks /create ^
  /tn "WhaleStream-Trader-Reactive-B" ^
  /tr "\"%TRADER%\"" ^
  /sc HOURLY /mo 4 /st 02:15 ^
  /rl HIGHEST ^
  /f
echo [E] Trader reactive B registered (02:15 +4h)

:: ── Trader Reactive C  (03:15 every 4h) ──────────────────────
schtasks /create ^
  /tn "WhaleStream-Trader-Reactive-C" ^
  /tr "\"%TRADER%\"" ^
  /sc HOURLY /mo 4 /st 03:15 ^
  /rl HIGHEST ^
  /f
echo [F] Trader reactive C registered (03:15 +4h)

echo.
echo ══════════════════════════════════════════════════════
echo   6 tasks registered. Full 4h cycle schedule:
echo.
echo   :00  SigBot      (existing)
echo   :10  Strategist  (existing — Claude first pass)
echo   :20  Trader      (existing — first order run)
echo   :30  Watchdog    (existing)
echo.
echo   1:10  Strategist re-check A  (rules-only)
echo   1:15  Trader reactive A
echo   2:10  Strategist re-check B  (rules-only)
echo   2:15  Trader reactive B
echo   3:10  Strategist re-check C  (rules-only)
echo   3:15  Trader reactive C
echo ══════════════════════════════════════════════════════

pause
