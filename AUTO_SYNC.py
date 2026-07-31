#!/usr/bin/env python3
"""
AUTO_SYNC.py — WHALE-STREAM Live Server Sync
Pulls runtime JSON files from server every 5 minutes.
Double-click AUTO_SYNC.bat to start. Ctrl+C or close window to stop.
"""

import subprocess
import time
import os
from datetime import datetime, timedelta

SERVER   = "root@152.42.224.87"
SRC      = "/opt/whalestream"
DST      = os.path.dirname(os.path.abspath(__file__))
INTERVAL = 300  # seconds — 5 minutes

# (filename, optional)
# optional=True → silently skip if file doesn't exist on server yet
FILES = [
    ("bybit_balance.json",        False),
    ("daily_status.json",         False),
    ("trade_log.json",            False),
    ("strategist_decisions.json", False),
    ("market_context.json",       False),
    ("milestone_state.json",      False),
    ("trader_skips.json",         False),
    ("debrief_log.txt",           False),
    ("pattern_memory.json",       True),   # created when P5 fires
    ("dynamic_blocklist.json",    True),   # created when P5B fires
]

def ts():
    return datetime.now().strftime("%H:%M:%S")

def sync_all():
    ok, skipped, failed = [], [], []
    for fname, optional in FILES:
        result = subprocess.run(
            ["scp", "-q", "-o", "ConnectTimeout=10",
             f"{SERVER}:{SRC}/{fname}",
             os.path.join(DST, fname)],
            capture_output=True
        )
        if result.returncode == 0:
            ok.append(fname)
        elif optional:
            skipped.append(fname)
        else:
            failed.append(fname)
    return ok, skipped, failed

def main():
    print("=" * 56)
    print("  WHALE-STREAM  --  AUTO SYNC")
    print(f"  Server   : {SERVER}")
    print(f"  Folder   : {DST}")
    print(f"  Interval : every 5 minutes")
    print("  Ctrl+C or close this window to stop")
    print("=" * 56)
    print()

    run = 0
    while True:
        run += 1
        print(f"[{ts()}] Sync #{run} ...", end="  ", flush=True)
        ok, skipped, failed = sync_all()

        parts = [f"OK: {len(ok)} files"]
        if skipped:
            parts.append(f"not yet on server: {', '.join(skipped)}")
        if failed:
            parts.append(f"FAILED: {', '.join(failed)}")
        print(" | ".join(parts))

        next_at = datetime.now() + timedelta(seconds=INTERVAL)
        print(f"         Next sync at {next_at.strftime('%H:%M:%S')}")
        print()
        time.sleep(INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped.")
