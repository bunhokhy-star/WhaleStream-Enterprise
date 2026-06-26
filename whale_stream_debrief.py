"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM DEBRIEF AGENT v1.0 — POST-TRADE LEARNING     ║
║                                                              ║
║  Called automatically by whale_stream_tracker.py after      ║
║  each WIN or LOSS resolution.                                ║
║                                                              ║
║  Purpose: turn every trade into a lesson.                    ║
║  The Strategist reads these lessons before every decision.   ║
║                                                              ║
║  Output: pattern_memory.json  (read by Strategist)           ║
║                                                              ║
║  Flow:                                                       ║
║    Tracker resolves trade → calls this script with trade     ║
║    data as JSON → Claude Haiku analyses WHY → lesson written ║
║    to pattern_memory.json → Strategist reads it next run     ║
╚══════════════════════════════════════════════════════════════╝

Usage (called by tracker.py):
    python whale_stream_debrief.py '<json_list_of_trades>'

Each trade dict must have:
    coin, direction, confidence, pattern, entry, exit_price,
    outcome (WIN/LOSS), tp_hit, pnl
"""

import os
import io
import sys
import json
import subprocess
import requests
from datetime import datetime, timezone, timedelta

# ── Force UTF-8 ────────────────────────────────────────────────
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── Auto-install ────────────────────────────────────────────────
for mod, pkg in {"anthropic": "anthropic"}.items():
    try:
        __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
try:
    from local_config import ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    import os as _os
    ANTHROPIC_API_KEY  = _os.getenv("ANTHROPIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN = _os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = _os.getenv("TELEGRAM_CHAT_ID", "")

DEBRIEF_MODEL = "claude-haiku-4-5-20251001"   # fast + cheap for short analysis

SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE      = os.path.join(SCRIPT_DIR, "pattern_memory.json")
LOG_FILE         = os.path.join(SCRIPT_DIR, "debrief_log.txt")
MAX_MEMORY_ITEMS = 200   # keep last 200 debriefs in memory file

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def log(msg):
    bkk = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M BKK")
    line = f"[{bkk}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def bkk_now_str():
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M BKK")


def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# PATTERN MEMORY  (read + write)
# ═══════════════════════════════════════════════════════════════

def load_memory():
    """Load existing pattern_memory.json. Returns the full dict."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_updated": "", "debriefs": []}


def already_debriefed(memory, coin, direction, debrief_at_approx):
    """
    Check if this specific trade was already debriefed.
    Uses coin+direction+resolution timestamp proximity (within 5 min).
    """
    for d in memory.get("debriefs", []):
        if d.get("coin") == coin and d.get("direction") == direction:
            stored_ts = d.get("debrief_at", "")
            if stored_ts and debrief_at_approx:
                # Both are "YYYY-MM-DD HH:MM BKK" format
                try:
                    fmt = "%Y-%m-%d %H:%M BKK"
                    t1  = datetime.strptime(stored_ts, fmt)
                    t2  = datetime.strptime(debrief_at_approx[:16] + " BKK", fmt)
                    if abs((t1 - t2).total_seconds()) < 300:   # within 5 minutes
                        return True
                except Exception:
                    pass
    return False


def save_memory(memory):
    """Write updated memory to disk. Trims to MAX_MEMORY_ITEMS."""
    # Keep only most recent debriefs
    if len(memory.get("debriefs", [])) > MAX_MEMORY_ITEMS:
        memory["debriefs"] = memory["debriefs"][-MAX_MEMORY_ITEMS:]
    memory["last_updated"] = bkk_now_str()

    # Rebuild coin_lessons and pattern_lessons from all debriefs
    coin_lessons    = {}
    pattern_lessons = {}
    avoid_patterns  = set()
    prefer_patterns = set()

    for d in memory.get("debriefs", []):
        c   = d.get("coin", "")
        dr  = d.get("direction", "")
        pat = d.get("pattern", "")
        lesson = d.get("lesson", "")
        flag   = d.get("flag", "NEUTRAL")

        if c and dr and lesson:
            coin_lessons.setdefault(c, {}).setdefault(dr, [])
            entry = f"[{flag}] {lesson}"
            if entry not in coin_lessons[c][dr]:
                coin_lessons[c][dr].append(entry)
            # Keep only last 5 lessons per coin+direction
            coin_lessons[c][dr] = coin_lessons[c][dr][-5:]

        if pat and lesson:
            pattern_lessons.setdefault(pat, [])
            if lesson not in pattern_lessons[pat]:
                pattern_lessons[pat].append(lesson)
            pattern_lessons[pat] = pattern_lessons[pat][-3:]

        if flag == "AVOID" and pat:
            avoid_patterns.add(pat)
        elif flag == "REINFORCE" and pat:
            prefer_patterns.add(pat)

    memory["coin_lessons"]    = coin_lessons
    memory["pattern_lessons"] = pattern_lessons
    memory["avoid_patterns"]  = sorted(avoid_patterns)
    memory["prefer_patterns"] = sorted(prefer_patterns)

    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"✗ Failed to save memory: {e}")


# ═══════════════════════════════════════════════════════════════
# DEBRIEF PROMPT
# ═══════════════════════════════════════════════════════════════

DEBRIEF_SYSTEM = """You are the WHALE-STREAM Post-Trade Debrief Agent.

Your job: analyse each completed trade and extract concise, actionable lessons.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GOLDEN RULE — DID WE FOLLOW THE TREND?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The #1 cause of LONG losses: trading LONG in a falling market.
The #1 cause of SHORT losses: trading SHORT in a rising market.
Always check: was this trade WITH the market trend or AGAINST it?
  - SHORT in a downtrend = flowing with water → wins
  - LONG in a downtrend = swimming upstream → drowns
  - LONG in an uptrend = flowing with water → wins
  - SHORT in an uptrend = swimming upstream → drowns
If a trade lost and the direction fought the market trend, the lesson is: DO NOT REPEAT.
If a trade won despite fighting the trend, flag it as lucky — do not reinforce.

For each trade, determine:
1. ENTRY QUALITY — grade A+/A/B/C/D based on outcome AND pattern quality
   A+ = TP2 or better hit, price moved straight in our direction, excellent timing
   A  = TP1+ hit, solid move with minimal drawdown
   B  = Won but only barely (TP1 scraped), OR decent setup that got stopped narrowly
   C  = Lost but setup was reasonable (bad luck or minor timing error)
   D  = Lost AND setup was poor (wrong direction, bad pattern, fought the trend)

2. WHY — root cause of the win or loss (max 20 words, be specific)

3. LESSON — what to do differently or reinforce next time (max 15 words, start with a verb)

4. FLAG — REINFORCE (strong setup to repeat), AVOID (pattern/setup to skip), NEUTRAL

RESPOND IN JSON ONLY. No prose. No explanation outside the JSON:
{
  "entry_quality": "A",
  "why": "Stage 2 expansion confirmed by negative funding; price hit TP2 in 6 hours",
  "lesson": "Reinforce Stage 2 + negative funding combo on TIA and similar alts",
  "flag": "REINFORCE"
}"""


def build_debrief_prompt(trade):
    """Build the user message for Claude Haiku debrief."""
    coin      = trade.get("coin", "?")
    direction = trade.get("direction", "?")
    outcome   = trade.get("outcome", "?")
    tp_hit    = trade.get("tp_hit", "")
    pnl       = trade.get("pnl", 0)
    pattern   = trade.get("pattern", "unknown")
    confidence= float(trade.get("confidence", 0) or 0)   # tracker sends as string; cast to float
    entry     = trade.get("entry", 0)
    exit_price= trade.get("exit_price", 0)

    outcome_detail = f"{outcome}"
    if tp_hit:
        outcome_detail += f" — {tp_hit} hit"
    if pnl:
        outcome_detail += f" — P&L: {pnl:+.1f}%"

    return f"""Trade to debrief:
  Coin:       {coin}
  Direction:  {direction}
  Pattern:    {pattern}
  Confidence: {confidence:.0f}%
  Entry:      {entry:.6g}
  Exit:       {exit_price:.6g}
  Outcome:    {outcome_detail}

Context:
  We use 10× leverage on Bybit demo.
  A+ entries move immediately to TP2+. Poor entries sit near entry or reverse before recovering.
  Our known loser patterns: RS failure, dead cat bounce, meme continuation, "Continuation breakout" standalone.
  Our known winner patterns: Stage 5 distribution collapse (SHORT), Stage 2 expansion (LONG).

Analyse this trade. Return JSON only."""


# ═══════════════════════════════════════════════════════════════
# CLAUDE API CALL
# ═══════════════════════════════════════════════════════════════

def call_debrief_claude(prompt):
    """Call Claude Haiku for a single trade debrief. Returns parsed dict or None."""
    import anthropic
    import re

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=DEBRIEF_MODEL,
        max_tokens=256,
        system=DEBRIEF_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    # Parse JSON
    try:
        return json.loads(raw)
    except Exception:
        pass
    # Try extracting JSON object
    start = raw.find('{')
    if start != -1:
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(raw[start:], start):
            if esc:       esc = False; continue
            if ch == '\\' and in_str: esc = True; continue
            if ch == '"': in_str = not in_str; continue
            if in_str:    continue
            if ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i+1])
                    except Exception:
                        break
    return None


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def run_debrief(trades):
    """
    Process a list of trade dicts and write debriefs to pattern_memory.json.
    trades: list of dicts with keys: coin, direction, confidence, pattern,
            entry, exit_price, outcome, tp_hit, pnl
    """
    if not trades:
        return

    memory = load_memory()
    now    = bkk_now_str()
    debriefs_written = []

    for trade in trades:
        coin      = trade.get("coin", "?")
        direction = trade.get("direction", "?")
        outcome   = trade.get("outcome", "?")

        # Skip if already debriefed (duplicate call guard)
        if already_debriefed(memory, coin, direction, now):
            log(f"   Skip {coin} {direction} — already debriefed")
            continue

        log(f"   Debriefing {coin} {direction} {outcome}...")

        prompt = build_debrief_prompt(trade)
        result = call_debrief_claude(prompt)

        if not result:
            log(f"   ✗ Claude parse failed for {coin} {direction}")
            # Write minimal entry without Claude analysis
            result = {
                "entry_quality": "?" ,
                "why":    f"{outcome} — Claude unavailable",
                "lesson": "Review manually",
                "flag":   "NEUTRAL",
            }

        entry = {
            "coin":          coin,
            "direction":     direction,
            "outcome":       outcome,
            "tp_hit":        trade.get("tp_hit", ""),
            "pnl":           trade.get("pnl", 0),
            "pattern":       trade.get("pattern", ""),
            "confidence":    trade.get("confidence", 0),
            "entry_quality": result.get("entry_quality", "?"),
            "why":           result.get("why", ""),
            "lesson":        result.get("lesson", ""),
            "flag":          result.get("flag", "NEUTRAL"),
            "debrief_at":    now,
        }

        memory["debriefs"].append(entry)
        debriefs_written.append(entry)

        icon = "✅" if outcome == "WIN" else "❌"
        flag_icon = "🔁" if entry["flag"] == "REINFORCE" else ("🚫" if entry["flag"] == "AVOID" else "➡️")
        log(f"   {icon} {coin} {direction} [{entry['entry_quality']}] {flag_icon} {entry['lesson']}")

    if not debriefs_written:
        return

    save_memory(memory)
    log(f"✓ pattern_memory.json updated — {len(memory['debriefs'])} total debriefs")

    # ── Telegram summary (ops channel) ────────────────────────
    lines = [f"🧠 <b>DEBRIEF COMPLETE</b> — {len(debriefs_written)} trade(s) analysed"]
    for d in debriefs_written:
        icon      = "✅" if d["outcome"] == "WIN" else "❌"
        flag_icon = "🔁" if d["flag"] == "REINFORCE" else ("🚫" if d["flag"] == "AVOID" else "➡️")
        pnl_str   = f"{d['pnl']:+.1f}%" if d.get("pnl") else ""
        lines.append(
            f"  {icon} <b>{d['coin']} {d['direction']}</b> [{d['entry_quality']}] {pnl_str}\n"
            f"  Why: {d['why']}\n"
            f"  {flag_icon} Lesson: {d['lesson']}"
        )
    send_telegram("\n".join(lines))


def main():
    """
    Entry point when called by tracker.py via subprocess.
    Argument: JSON string of trade list.
    """
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   🧠  WHALE-STREAM DEBRIEF AGENT v1.0               ║")
    print("║   Post-Trade Learning — every loss teaches us        ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    if len(sys.argv) < 2:
        log("✗ No trade data argument provided. Usage: python whale_stream_debrief.py '<json>'")
        return

    try:
        trades = json.loads(sys.argv[1])
        if not isinstance(trades, list):
            trades = [trades]
    except Exception as e:
        log(f"✗ Failed to parse trade data: {e}")
        return

    log(f"=== Debrief run — {len(trades)} trade(s) to analyse ===")
    run_debrief(trades)
    print()
    print("✅ Debrief complete.")
    print()


if __name__ == "__main__":
    try:
        from mission import print_mission_banner
        print_mission_banner()
    except ImportError:
        pass
    main()
