"""
╔══════════════════════════════════════════════════════════════════╗
║  WHALE-STREAM STATUS SERVER                                      ║
║  Serves daily_status.json to the Daily Checklist HTML            ║
║  Port  : 127.0.0.1:8765  (local only — not exposed to internet) ║
║  Run   : python status_server.py                                 ║
║  Task Scheduler: At system startup, run minimized / hidden       ║
╚══════════════════════════════════════════════════════════════════╝

Each agent writes its own key to daily_status.json when it finishes.
This server delivers that file to the Daily Checklist HTML with CORS
headers so the browser can fetch it from localhost.

Keys written by agents:
  sigbot_HH, strategist_HH, trader_HH, watchdog_HH  (HH = 00/04/08/12/16/20)
  tracker, monitor, briefing  (always-running — no cycle suffix)
"""

# ══════════════════════════════════════════════════════════════════
# WHALE-STREAM CONSTITUTION — 7 PRINCIPLES (applies to every agent)
# ══════════════════════════════════════════════════════════════════
# P1  Clear isolated roles — each agent owns one job, never another's
# P2  Continuous 4h schedule — Bot:00 Strategist:10 Trader:20 Watchdog:30
#     Tracker every 30m | Monitor every 2m | Briefing 07:00 daily
# P3  Report after every cycle — state what worked and what didn't
# P4  24/7 proactive Telegram — never wait for the human to ask
# P5  Multi-agent consensus — Debrief cross-checks Strategist vs actual outcome
# P6  High-risk discipline — no vague signals; plan every entry precisely
# P7  Mission — every trade generates capital to help those in need
# ══════════════════════════════════════════════════════════════════

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


# ── Config ────────────────────────────────────────────────────────
PORT     = 8765
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class WhaleStreamStatusHandler(SimpleHTTPRequestHandler):
    """Serve files from WhaleStream folder with CORS + no-cache headers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Allow the Daily Checklist HTML (file://) to fetch from localhost
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        # Only serve the two status files — block everything else for security
        # (prevents local_config.py and other files from being exposed over HTTP)
        import posixpath
        allowed = {"daily_status.json", "daily_status.js"}
        req_path = posixpath.basename(posixpath.normpath(self.path.split("?")[0]))
        if req_path not in allowed:
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"403 Forbidden\n")
            return
        # Serve normally via the parent class
        super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Silent — suppress per-request console spam
        pass


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), WhaleStreamStatusHandler)  # explicit IPv4 — avoids IPv6 mismatch on Windows
    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  WHALE-STREAM Status Server running              ║")
    print(f"║  http://127.0.0.1:{PORT}/daily_status.json         ║")
    print(f"║  Serving: {BASE_DIR[:38]:<38} ║")
    print(f"╚══════════════════════════════════════════════════╝")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Status Server] Stopped.")
        sys.exit(0)
