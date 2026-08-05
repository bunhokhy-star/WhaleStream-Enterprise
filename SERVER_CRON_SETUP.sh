#!/bin/bash
# =============================================================================
# WHALE-STREAM v47.68 — Server Crontab Setup
# Server: 152.42.224.87 (Ubuntu DigitalOcean — /opt/whalestream/)
# Run this script ON THE SERVER (ssh root@152.42.224.87 then bash this script)
#
# Schedule (all times UTC):
#   Bot              :00 every 4h  (00:00, 04:00, 08:00, 12:00, 16:00, 20:00)
#   Strategist       :10 every 4h  (00:10, 04:10, ...)
#   Trader           :20 every 4h  (00:20, 04:20, ...)
#   Watchdog         :30 every 4h  (00:30, 04:30, ...)
#   Strat re-check   :10 off-cycle (01:10, 02:10, 03:10 and +4h equivalents)
#   Trader reactive  :15 off-cycle (01:15, 02:15, 03:15 and +4h equivalents)
#   Monitor          every 2 min   (near-real-time fill detector)
#   Tracker          every 30 min  (price check + WIN/LOSS resolution)
#   Briefing         00:00 UTC     (7am Bangkok = 00:00 UTC)
#   Weekly           01:00 UTC Mon (8am Bangkok Monday)
#   Telegram cmds    every hour    (YES/NO reply handler for weekly scorecard)
#   Gap checker      :45 every 4h  (agent health — 5 min after Watchdog)
#
# NOTE: 00:00 UTC = 07:00 BKK (UTC+7)
# =============================================================================

set -euo pipefail

WS=/opt/whalestream
PY=/usr/bin/python3
LOG=$WS/logs

echo "=== WHALE-STREAM Crontab Setup ==="
echo "Working dir: $WS"
echo "Python: $PY"
echo ""

# Ensure logs directory exists
mkdir -p $LOG

# Write the new crontab
crontab - << 'CRON'
# === WHALE-STREAM v47.68 — Server Crontab ===
# All times UTC. BKK = UTC+7.
# Logs rotated weekly — check /opt/whalestream/logs/ for output.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# ── 4-Hour Cycle (main) ───────────────────────────────────────
# Bot: scan Bybit, generate signals, post to Telegram
0 0,4,8,12,16,20 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_bot.py >> /opt/whalestream/logs/bot.log 2>&1

# Strategist: evaluate signals, approve/veto (Claude first pass)
10 0,4,8,12,16,20 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_strategist.py >> /opt/whalestream/logs/strategist.log 2>&1

# Trader: place approved orders on Bybit
20 0,4,8,12,16,20 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_trader.py >> /opt/whalestream/logs/trader.log 2>&1

# Watchdog: health check all agents, alert if anything missed
30 0,4,8,12,16,20 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_watchdog.py >> /opt/whalestream/logs/watchdog.log 2>&1

# Gap checker: verify every expected agent ticked (5 min after Watchdog)
45 0,4,8,12,16,20 * * * cd /opt/whalestream && /usr/bin/python3 check_daily_status.py >> /opt/whalestream/logs/gap_checker.log 2>&1

# ── Intra-Cycle Re-checks (rules-only, no Claude) ─────────────
# Strategist re-check A: 01:10, 05:10, 09:10, 13:10, 17:10, 21:10
10 1,5,9,13,17,21 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_strategist.py --recheck >> /opt/whalestream/logs/strategist_recheck.log 2>&1
# Strategist re-check B: 02:10, 06:10, 10:10, 14:10, 18:10, 22:10
10 2,6,10,14,18,22 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_strategist.py --recheck >> /opt/whalestream/logs/strategist_recheck.log 2>&1
# Strategist re-check C: 03:10, 07:10, 11:10, 15:10, 19:10, 23:10
10 3,7,11,15,19,23 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_strategist.py --recheck >> /opt/whalestream/logs/strategist_recheck.log 2>&1

# Trader reactive A: 01:15, 05:15, 09:15, 13:15, 17:15, 21:15
15 1,5,9,13,17,21 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_trader.py --reactive >> /opt/whalestream/logs/trader_reactive.log 2>&1
# Trader reactive B: 02:15, 06:15, 10:15, 14:15, 18:15, 22:15
15 2,6,10,14,18,22 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_trader.py --reactive >> /opt/whalestream/logs/trader_reactive.log 2>&1
# Trader reactive C: 03:15, 07:15, 11:15, 15:15, 19:15, 23:15
15 3,7,11,15,19,23 * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_trader.py --reactive >> /opt/whalestream/logs/trader_reactive.log 2>&1

# ── High-Frequency ────────────────────────────────────────────
# Monitor: near-real-time fill detector (every 2 min)
*/2 * * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_monitor.py >> /opt/whalestream/logs/monitor.log 2>&1

# Tracker: price check + WIN/LOSS resolution (every 30 min)
*/30 * * * * cd /opt/whalestream && /usr/bin/python3 whale_stream_tracker.py >> /opt/whalestream/logs/tracker.log 2>&1

# Telegram command handler: YES/NO replies to weekly scorecard (every hour)
0 * * * * cd /opt/whalestream && /usr/bin/python3 telegram_commands.py >> /opt/whalestream/logs/tg_commands.log 2>&1

# ── Daily / Weekly ────────────────────────────────────────────
# Morning briefing at 00:00 UTC = 07:00 BKK
0 0 * * * cd /opt/whalestream && /usr/bin/python3 morning_briefing.py >> /opt/whalestream/logs/briefing.log 2>&1

# Weekly scorecard every Monday at 01:00 UTC = 08:00 BKK
0 1 * * 1 cd /opt/whalestream && /usr/bin/python3 whale_stream_weekly.py >> /opt/whalestream/logs/weekly.log 2>&1

# Log rotation: truncate logs over 10MB (keeps last 500 lines)
0 3 * * * for f in /opt/whalestream/logs/*.log; do [ -f "$f" ] && [ $(wc -c < "$f") -gt 10485760 ] && tail -500 "$f" > "$f.tmp" && mv "$f.tmp" "$f"; done

# ── Status Server (Daily Checklist) ───────────────────────────
# Restart status_server.py if it dies (checks every 5 min)
*/5 * * * * pgrep -f "status_server.py" > /dev/null || (cd /opt/whalestream && nohup /usr/bin/python3 status_server.py >> /opt/whalestream/logs/status_server.log 2>&1 &)

# Auto-start on server reboot
@reboot cd /opt/whalestream && nohup /usr/bin/python3 status_server.py >> /opt/whalestream/logs/status_server.log 2>&1 &

CRON

echo ""
echo "=== Crontab installed ==="
crontab -l
echo ""
echo "=== Verifying Python + scripts ==="
$PY --version
ls -la $WS/whale_stream_*.py
echo ""
echo "=== Log directory ==="
ls -la $LOG/ 2>/dev/null || echo "(logs/ created, empty)"
echo ""
echo "=== DONE — system will run autonomously ==="
echo "    No Windows PC required."
echo "    Monitor: ssh root@152.42.224.87 && tail -f /opt/whalestream/logs/bot.log"
