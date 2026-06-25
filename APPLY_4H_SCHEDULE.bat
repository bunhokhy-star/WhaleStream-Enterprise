@echo off
:: ============================================================
:: WHALE-STREAM — Enforce Exact 4-Hour Schedule
:: Right-click this file → "Run as administrator"
:: Re-registers both tasks at precisely 4h intervals:
::   Bot:    06:00 / 10:00 / 14:00 / 18:00 / 22:00 / 02:00
::   Trader: 06:20 / 10:20 / 14:20 / 18:20 / 22:20 / 02:20
:: ============================================================
echo.
echo ============================================================
echo   WHALE-STREAM — ENFORCING EXACT 4-HOUR SCHEDULE
echo ============================================================
echo.

:: ── Step 1: Re-register Bot task at 4h ──────────────────────
echo [1/2] Re-registering WhaleStream-Bot at 4h...
schtasks /Delete /TN "WhaleStream-Bot" /F >nul 2>&1
schtasks /Create ^
  /TN "WhaleStream-Bot" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_bot.bat\"" ^
  /SC HOURLY ^
  /MO 4 ^
  /ST 06:00 ^
  /F

if %ERRORLEVEL% NEQ 0 goto :error_bot
echo   ✓ WhaleStream-Bot → every 4h from 06:00

:: ── Step 2: Re-register Trader task at 4h ───────────────────
echo.
echo [2/2] Re-registering WhaleStream-Trader at 4h...
schtasks /Delete /TN "WhaleStream-Trader" /F >nul 2>&1
schtasks /Create ^
  /TN "WhaleStream-Trader" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_trader.bat\"" ^
  /SC HOURLY ^
  /MO 4 ^
  /ST 06:20 ^
  /F

if %ERRORLEVEL% NEQ 0 goto :error_trader
echo   ✓ WhaleStream-Trader → every 4h from 06:20

:: ── Done ────────────────────────────────────────────────────
echo.
echo ============================================================
echo   SUCCESS! Both tasks locked to exactly 4 hours.
echo.
echo   Bot runs at:    06:00 / 10:00 / 14:00 / 18:00 / 22:00
echo   Trader runs at: 06:20 / 10:20 / 14:20 / 18:20 / 22:20
echo ============================================================
echo.
goto :end

:error_bot
echo.
echo   ERROR: Failed to re-register WhaleStream-Bot.
echo   Make sure you right-clicked → "Run as administrator"
echo.
goto :end

:error_trader
echo.
echo   ERROR: Failed to re-register WhaleStream-Trader.
echo   Make sure you right-clicked → "Run as administrator"
echo.

:end
echo.
pause
