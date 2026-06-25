@echo off
:: ============================================================
:: WHALE-STREAM — NUCLEAR 4H SCHEDULE FIX
:: Right-click → "Run as administrator"
:: Finds and kills EVERY WhaleStream task variant, then
:: re-creates ONLY the correct 4h tasks.
:: ============================================================
echo.
echo ============================================================
echo   WHALE-STREAM — NUCLEAR 4H SCHEDULE FIX
echo ============================================================
echo.

:: ── Step 1: Show what's currently registered ─────────────
echo [BEFORE] Current WhaleStream tasks:
echo.
schtasks /query /fo LIST | findstr /i "whalestream\|run_bot\|run_trader"
echo.
echo ────────────────────────────────────────────────────────────
echo.

:: ── Step 2: Delete EVERY possible name variant ───────────
echo Deleting all WhaleStream task variants...
schtasks /Delete /TN "WhaleStream-Bot"     /F >nul 2>&1
schtasks /Delete /TN "WhaleStream-Trader"  /F >nul 2>&1
schtasks /Delete /TN "WhaleStreamBot"      /F >nul 2>&1
schtasks /Delete /TN "WhaleStreamTrader"   /F >nul 2>&1
schtasks /Delete /TN "WhaleStream Bot"     /F >nul 2>&1
schtasks /Delete /TN "WhaleStream Trader"  /F >nul 2>&1
schtasks /Delete /TN "Whale-Stream-Bot"    /F >nul 2>&1
schtasks /Delete /TN "Whale-Stream-Trader" /F >nul 2>&1
schtasks /Delete /TN "WS-Bot"             /F >nul 2>&1
schtasks /Delete /TN "WS-Trader"          /F >nul 2>&1
echo   Done — all variants cleared.
echo.

:: ── Step 3: Confirm nothing remains ─────────────────────
echo [CHECK] Remaining tasks after delete:
schtasks /query /fo LIST | findstr /i "whalestream\|run_bot\|run_trader"
echo   (blank above = all clear)
echo.
echo ────────────────────────────────────────────────────────────
echo.

:: ── Step 4: Re-create Bot at EXACTLY 4h ─────────────────
echo [1/2] Creating WhaleStream-Bot at 4h...
schtasks /Create ^
  /TN "WhaleStream-Bot" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_bot.bat\"" ^
  /SC HOURLY ^
  /MO 4 ^
  /ST 06:00 ^
  /F

if %ERRORLEVEL% NEQ 0 goto :error_bot
echo   OK: WhaleStream-Bot → 06:00 / 10:00 / 14:00 / 18:00 / 22:00 / 02:00
echo.

:: ── Step 5: Re-create Trader at EXACTLY 4h ──────────────
echo [2/2] Creating WhaleStream-Trader at 4h...
schtasks /Create ^
  /TN "WhaleStream-Trader" ^
  /TR "cmd.exe /c \"C:\Users\MAX\WhaleStream\run_trader.bat\"" ^
  /SC HOURLY ^
  /MO 4 ^
  /ST 06:20 ^
  /F

if %ERRORLEVEL% NEQ 0 goto :error_trader
echo   OK: WhaleStream-Trader → 06:20 / 10:20 / 14:20 / 18:20 / 22:20 / 02:20
echo.

:: ── Step 6: Verify the new tasks ────────────────────────
echo ────────────────────────────────────────────────────────────
echo [AFTER] Confirmed registered tasks:
echo.
schtasks /query /TN "WhaleStream-Bot"     /fo LIST | findstr /i "task name\|next run\|repeat every\|schedule type"
echo.
schtasks /query /TN "WhaleStream-Trader"  /fo LIST | findstr /i "task name\|next run\|repeat every\|schedule type"
echo.
echo ============================================================
echo   SUCCESS — Both tasks locked to 4h. Done!
echo ============================================================
echo.
goto :end

:error_bot
echo.
echo   ERROR: Failed to create WhaleStream-Bot.
echo   Make sure you right-clicked "Run as administrator"
echo.
goto :end

:error_trader
echo.
echo   ERROR: Failed to create WhaleStream-Trader.
echo   Make sure you right-clicked "Run as administrator"
echo.

:end
echo.
pause
