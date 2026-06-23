@echo off
cd /d "C:\Users\MAX\WhaleStream"
echo ============================================
echo  WHALE-STREAM P&L History Repair — AUTO
echo ============================================
echo.
echo Step 1: Dry run preview...
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" repair_pnl_history.py
echo.
echo ============================================
echo Step 2: Applying fixes now...
echo ============================================
echo.
"C:\Users\MAX\AppData\Local\Python\bin\python.exe" repair_pnl_history.py --apply
echo.
echo ============================================
echo  ALL DONE. Window will close in 30 seconds.
echo ============================================
timeout /t 30
