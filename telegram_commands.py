"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM TELEGRAM COMMAND HANDLER  v47.44              ║
║                                                              ║
║  Runs every hour (cron: 0 * * * *)                           ║
║  Polls Telegram for YES / NO replies to weekly scorecard     ║
║                                                              ║
║  YES → reads pending_recommendation.json → applies action:  ║
║    block_coin  → adds to dynamic_blocklist.json              ║
║    raise_floor → writes floor_override.json                  ║
║  NO  → clears pending_recommendation.json                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BKK        = timezone(timedelta(hours=7))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

PENDING_FILE  = os.path.join(SCRIPT_DIR, "pending_recommendation.json")
DYNBLOCK_FILE = os.path.join(SCRIPT_DIR, "dynamic_blocklist.json")
OFFSET_FILE   = os.path.join(SCRIPT_DIR, ".tg_cmd_offset.json")

try:
    from local_config import TELEGRAM_BOT_TOKEN
except ImportError:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

TELEGRAM_CHAT_ID = ""
try:
    from local_config import TELEGRAM_CHAT_ID_OPS
    TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID_OPS
except ImportError:
    try:
        from local_config import TELEGRAM_CHAT_ID as _tc
        TELEGRAM_CHAT_ID = _tc
    except ImportError:
        TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID_OPS", "") or os.getenv("TELEGRAM_CHAT_ID", "")


def bkk_now():
    return datetime.now(BKK)


def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"[Telegram] {e}")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_updates(offset=None):
    """Poll Telegram for new messages."""
    params = {"timeout": 5, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params=params,
            timeout=15,
        )
        if r.ok:
            return r.json().get("result", [])
    except Exception as e:
        print(f"[getUpdates] {e}")
    return []


def apply_block(rec):
    """Add coin to dynamic_blocklist.json."""
    coin = rec["coin"].upper()
    dirn = rec["direction"].upper()

    dynblock = load_json(DYNBLOCK_FILE, {"LONG": [], "SHORT": []})
    dynblock.setdefault("LONG", [])
    dynblock.setdefault("SHORT", [])

    if dirn == "LONG" and coin not in dynblock["LONG"]:
        dynblock["LONG"].append(coin)
    elif dirn == "SHORT" and coin not in dynblock["SHORT"]:
        dynblock["SHORT"].append(coin)

    dynblock["last_updated"] = bkk_now().isoformat()
    save_json(DYNBLOCK_FILE, dynblock)

    msg = (
        f"✅ <b>AUTO-BLOCK APPLIED</b>\n"
        f"  {coin} {dirn} added to permanent blocklist\n"
        f"  Reason: {rec.get('all_wr')}% all-time WR · {rec.get('week_losses')} losses this week\n"
        f"  Active from next Bot cycle.\n"
        f"🐳 WHALE-STREAM v47.44"
    )
    send_telegram(msg)
    print(f"  ✅ Blocked: {coin} {dirn}")


def apply_raise_floor(rec):
    """Write floor override — bot.py reads this at next run."""
    override = {
        "long_conf_floor": 92,
        "reason":          rec.get("message", "Weekly scorecard recommendation"),
        "applied":         bkk_now().isoformat(),
    }
    save_json(os.path.join(SCRIPT_DIR, "floor_override.json"), override)

    msg = (
        f"✅ <b>FLOOR RAISED</b>\n"
        f"  LONG confidence floor: 88% → 92%\n"
        f"  Reason: {rec.get('message', '')}\n"
        f"  Active from next Bot cycle.\n"
        f"🐳 WHALE-STREAM v47.44"
    )
    send_telegram(msg)
    print("  ✅ Floor raised to 92%")


def main():
    print(f"[{bkk_now().strftime('%H:%M BKK')}] Telegram command handler running...")

    if not TELEGRAM_BOT_TOKEN:
        print("  No Telegram token — skipping")
        return

    # Check if there's a pending recommendation
    pending = load_json(PENDING_FILE, None)
    if not pending or pending.get("status") != "pending":
        print("  No pending recommendation — nothing to act on")
        return

    # Pending recommendation exists — check if it's expired (>48h old)
    created_str = pending.get("created", "")
    if created_str:
        try:
            created = datetime.fromisoformat(created_str)
            if created.tzinfo is None:
                created = created.replace(tzinfo=BKK)
            age_hours = (bkk_now() - created).total_seconds() / 3600
            if age_hours > 48:
                print(f"  Recommendation expired ({age_hours:.0f}h old) — clearing")
                os.remove(PENDING_FILE)
                send_telegram(
                    "⏰ <b>Weekly recommendation expired (48h)</b>\n"
                    f"  {pending.get('coin','')} {pending.get('direction','')} block was NOT applied.\n"
                    "  Next scorecard: Monday 07:00 BKK."
                )
                return
        except Exception:
            pass

    # Load update offset
    offset_data = load_json(OFFSET_FILE, {"offset": None})
    offset      = offset_data.get("offset")

    updates = get_updates(offset)
    if not updates:
        print("  No new Telegram messages")
        return

    # Save new offset
    new_offset = updates[-1]["update_id"] + 1
    save_json(OFFSET_FILE, {"offset": new_offset})

    # Scan for YES or NO from the ops chat
    for update in updates:
        msg     = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text    = msg.get("text", "").strip().upper()

        # Only accept from the configured ops chat
        if chat_id != str(TELEGRAM_CHAT_ID):
            continue

        if text in ("YES", "/YES", "Y"):
            print(f"  ✅ YES received — applying: {pending.get('type')}")
            if pending["type"] == "block_coin":
                apply_block(pending)
            elif pending["type"] == "raise_floor":
                apply_raise_floor(pending)
            # Mark as applied
            pending["status"] = "applied"
            pending["applied"] = bkk_now().isoformat()
            save_json(PENDING_FILE, pending)
            break

        elif text in ("NO", "/NO", "N"):
            print("  ❌ NO received — clearing recommendation")
            pending["status"] = "declined"
            save_json(PENDING_FILE, pending)
            send_telegram(
                f"👍 Understood — <b>{pending.get('coin','')} {pending.get('direction','')} NOT blocked</b>.\n"
                "System will keep watching this coin.\n"
                "Next scorecard: Monday 07:00 BKK."
            )
            break

    print("  Done.")


if __name__ == "__main__":
    main()
