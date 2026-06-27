@echo off
echo ══════════════════════════════════════════════════════
echo   WHALE-STREAM — gspread diagnostic + new auth test
echo ══════════════════════════════════════════════════════
echo.

"C:\Users\MAX\AppData\Local\Python\bin\python.exe" -c ^
"import sys, os; ^
print('Python executable:', sys.executable); ^
print('Python version   :', sys.version); ^
print(); ^
print('--- sys.path ---'); ^
[print(' ', p) for p in sys.path]; ^
print(); ^
import gspread; ^
print('gspread version  :', gspread.__version__); ^
print('gspread location :', gspread.__file__); ^
print('has top-level service_account:', hasattr(gspread, 'service_account')); ^
print(); ^
print('--- OLD approach (gspread.auth) ---'); ^
try: ^
    from gspread.auth import service_account; ^
    print('PASS: from gspread.auth import service_account'); ^
except Exception as e: ^
    print('FAIL:', e); ^
print(); ^
print('--- NEW approach (google.oauth2 + gspread.Client) ---'); ^
try: ^
    from google.oauth2.service_account import Credentials; ^
    print('PASS: from google.oauth2.service_account import Credentials'); ^
    print('Has gspread.Client:', hasattr(gspread, \"Client\")); ^
    print('NEW APPROACH SHOULD WORK'); ^
except Exception as e: ^
    print('FAIL:', e); ^
"

echo.
echo Exit code: %ERRORLEVEL%
pause
