@echo off
cd /d "C:\Users\MAX\WhaleStream"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
echo ============================================
echo  WHALE-STREAM P&L History Repair
echo ============================================
echo.
echo Step 1: Dry run (preview changes)...
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" repair_pnl_history.py
echo.
echo ============================================
echo  Above is a PREVIEW. No changes made yet.
echo  Close this window to cancel, or...
echo  Press any key to APPLY the fixes.
echo ============================================
pause
echo.
echo Step 2: Applying fixes...
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" repair_pnl_history.py --apply
echo.
pause
