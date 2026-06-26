"""
WHALE-STREAM — Bybit API Connection Diagnostic
Run this with: python diagnose_bybit.py
It will show the EXACT error preventing the trader from connecting.
"""
import sys, os, hmac, hashlib, time, json
from urllib.parse import urlencode

import requests

print("=" * 60)
print("  WHALE-STREAM — Bybit API Diagnostic")
print("=" * 60)
print()

# ── Step 1: Load API keys ──────────────────────────────────────
print("Step 1: Loading API keys from local_config.py...")
BYBIT_API_KEY    = ""
BYBIT_API_SECRET = ""
try:
    from local_config import BYBIT_API_KEY, BYBIT_API_SECRET
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        print("  ✗ ERROR: BYBIT_API_KEY or BYBIT_API_SECRET is EMPTY in local_config.py")
        sys.exit(1)
    if "YOUR_BYBIT" in BYBIT_API_KEY:
        print("  ✗ ERROR: BYBIT_API_KEY is still the placeholder value")
        sys.exit(1)
    print(f"  ✓ API Key loaded: {BYBIT_API_KEY[:8]}...{BYBIT_API_KEY[-4:]}  (len={len(BYBIT_API_KEY)})")
    print(f"  ✓ Secret loaded:  {'*' * 8}...{BYBIT_API_SECRET[-4:]}  (len={len(BYBIT_API_SECRET)})")
except ImportError as e:
    print(f"  ✗ IMPORT ERROR: {e}")
    print("  → Make sure local_config.py exists in C:\\Users\\MAX\\WhaleStream")
    sys.exit(1)
print()

# ── Step 2: Test network (public endpoint, no auth) ────────────
print("Step 2: Testing Bybit public API (no auth)...")
BYBIT_PUBLIC_URL = "https://api.bybit.com"
BYBIT_DEMO_URL   = "https://api-demo.bybit.com"
try:
    r = requests.get(f"{BYBIT_PUBLIC_URL}/v5/market/time", timeout=10)
    print(f"  ✓ Public API reachable — HTTP {r.status_code}")
    data = r.json()
    print(f"  ✓ Server time: {data.get('result', {}).get('timeNano', '?')}")
except Exception as e:
    print(f"  ✗ PUBLIC API FAILED: {type(e).__name__}: {e}")
    print("  → Possible network/firewall issue")
print()

# ── Step 3: Test Demo endpoint (public, no auth) ───────────────
print("Step 3: Testing Bybit DEMO endpoint (no auth)...")
try:
    r = requests.get(f"{BYBIT_DEMO_URL}/v5/market/time", timeout=10)
    print(f"  ✓ Demo API reachable — HTTP {r.status_code}")
    try:
        data = r.json()
        print(f"  ✓ Demo server time: {data.get('result', {}).get('timeNano', '?')}")
    except Exception:
        print(f"  ✗ Demo API returned non-JSON: {r.text[:200]}")
except Exception as e:
    print(f"  ✗ DEMO API FAILED: {type(e).__name__}: {e}")
    print("  → The api-demo.bybit.com endpoint may be unreachable")
print()

# ── Step 4: Authenticated request (wallet balance) ─────────────
print("Step 4: Testing authenticated Demo API (wallet balance)...")

def make_auth_headers(api_key, secret, params=None, body=None, method="GET"):
    timestamp   = str(int(time.time() * 1000) - 1000)
    recv_window = "20000"
    if method == "GET":
        query_str = urlencode(params) if params else ""
        sign_str  = f"{timestamp}{api_key}{recv_window}{query_str}"
    else:
        body_str = json.dumps(body) if body else ""
        sign_str = f"{timestamp}{api_key}{recv_window}{body_str}"
    signature = hmac.new(
        secret.encode("utf-8"),
        sign_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return {
        "X-BAPI-API-KEY":      api_key,
        "X-BAPI-SIGN":         signature,
        "X-BAPI-TIMESTAMP":    timestamp,
        "X-BAPI-RECV-WINDOW":  recv_window,
        "X-BAPI-DEMO-TRADING": "1",
        "Content-Type":        "application/json",
    }

params  = {"accountType": "UNIFIED"}
headers = make_auth_headers(BYBIT_API_KEY, BYBIT_API_SECRET, params=params)
url     = f"{BYBIT_DEMO_URL}/v5/account/wallet-balance"

try:
    r = requests.get(url, params=params, headers=headers, timeout=15)
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Raw response (first 500 chars):")
    print(f"  {r.text[:500]}")
    try:
        data = r.json()
        code = data.get("retCode")
        msg  = data.get("retMsg", "")
        if code == 0:
            coins = data["result"]["list"][0].get("coin", [])
            usdt  = next((c for c in coins if c.get("coin") == "USDT"), None)
            if usdt:
                print(f"\n  ✓ AUTH SUCCESS — USDT Balance: ${float(usdt.get('walletBalance', 0)):,.2f}")
            else:
                print(f"\n  ⚠ Auth OK but no USDT found. Coins: {[c.get('coin') for c in coins]}")
        else:
            print(f"\n  ✗ BYBIT ERROR — retCode: {code}  retMsg: '{msg}'")
            if code == 10003:
                print("  → retCode 10003 = Invalid API key or key doesn't have permission")
                print("  → FIX: Re-generate API keys in Bybit Demo → Account → API Management")
            elif code == 33004:
                print("  → retCode 33004 = API key expired")
                print("  → FIX: Re-generate API keys in Bybit Demo → Account → API Management")
            elif code == 10002:
                print("  → retCode 10002 = Your PC clock is out of sync with Bybit's server")
                print("  → FIX: Right-click clock (bottom-right) → Adjust date/time → Sync now")
                print("  → The v46.65 code fix will compensate automatically, but syncing the")
                print("     clock is still recommended to keep the offset small.")
            elif code == 10004:
                print("  → retCode 10004 = Invalid sign (timestamp issue or wrong secret)")
            elif code == 131001:
                print("  → retCode 131001 = UNIFIED account not activated")
            else:
                print(f"  → Unknown error code. See Bybit docs for retCode {code}")
    except Exception as parse_err:
        print(f"\n  ✗ JSON PARSE ERROR: {parse_err}")
        print("  → Bybit returned non-JSON (HTML maintenance page?)")
except Exception as e:
    print(f"\n  ✗ REQUEST FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 60)
print("  Diagnostic complete.")
print("  Screenshot this output and share with your dev team.")
print("=" * 60)
