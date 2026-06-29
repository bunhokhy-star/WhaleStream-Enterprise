r"""
sync_status.py -- Sync daily_status.json from DigitalOcean server to Windows machine
Runs every 5 minutes via Task Scheduler.

Does two things:
  1. Writes C:/Users/MAX/WhaleStream/daily_status.json (file:// fallback for Chrome)
  2. Rewrites the var WS_EMBEDDED block in Daily Checklist.html
     so the Cowork panel (sandboxed, no external fetch) always shows live data.
"""

import urllib.request
import json
import os
import re
import sys

# ── Config ────────────────────────────────────────────────────────────────────
SERVER_URL  = "http://152.42.224.87:8765/daily_status.json"
BASE_DIR    = r"C:\Users\MAX\WhaleStream"
LOCAL_JSON  = os.path.join(BASE_DIR, "daily_status.json")
CHECKLIST   = os.path.join(BASE_DIR, "To do list", "Daily Checklist.html")
TIMEOUT_SEC = 10

# ── Fetch from server ─────────────────────────────────────────────────────────
def fetch_status():
    try:
        with urllib.request.urlopen(SERVER_URL, timeout=TIMEOUT_SEC) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw)
    except Exception as e:
        print(f"[sync_status] ERROR fetching {SERVER_URL}: {e}", file=sys.stderr)
        return None

# ── Write local JSON copy ─────────────────────────────────────────────────────
def write_local_json(data):
    try:
        with open(LOCAL_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"[sync_status] Written {LOCAL_JSON}")
    except Exception as e:
        print(f"[sync_status] ERROR writing JSON: {e}", file=sys.stderr)

# ── Update WS_EMBEDDED in Daily Checklist.html ────────────────────────────────
def update_checklist_html(data):
    try:
        with open(CHECKLIST, "r", encoding="utf-8") as f:
            html = f.read()

        new_block = "var WS_EMBEDDED=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"

        # Replace the existing var WS_EMBEDDED={...}; — handles any amount of data
        html_new = re.sub(
            r"var WS_EMBEDDED=\{.*?\};",
            new_block,
            html,
            flags=re.DOTALL,
        )

        if html_new == html:
            print("[sync_status] WS_EMBEDDED unchanged — no rewrite needed")
            return

        with open(CHECKLIST, "w", encoding="utf-8") as f:
            f.write(html_new)
        print(f"[sync_status] Updated WS_EMBEDDED in Daily Checklist.html")

    except Exception as e:
        print(f"[sync_status] ERROR updating HTML: {e}", file=sys.stderr)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    data = fetch_status()
    if data is None:
        print("[sync_status] No data — skipping update.")
        sys.exit(1)

    write_local_json(data)
    update_checklist_html(data)
    print("[sync_status] Done.")
