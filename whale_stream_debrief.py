"""
╔══════════════════════════════════════════════════════════════╗
║   WHALE-STREAM DEBRIEF AGENT v47.26 — POST-TRADE LEARNING    ║
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
import io
import re
import sys
import json
import subprocess
import requests
import anthropic
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
    ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

DEBRIEF_MODEL = "claude-haiku-4-5-20251001"   # fast + cheap for short analysis

SCRIPT_DIR          = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE         = os.path.join(SCRIPT_DIR, "pattern_memory.json")
STRATEGIST_FILE     = os.path.join(SCRIPT_DIR, "strategist_decisions.json")
LOG_FILE            = os.path.join(SCRIPT_DIR, "debrief_log.txt")
MAX_MEMORY_ITEMS    = 200   # keep last 200 debriefs in memory file

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

BKK = timezone(timedelta(hours=7))


def _mark_done(agent_name="debrief", details=None):
    """Mark this agent done for the current cycle in daily_status.json."""
    _path  = os.path.join(SCRIPT_DIR, "daily_status.json")
    _now   = datetime.now(BKK)
    _today = _now.date().isoformat()
    _h     = _now.hour
    _cycle = str((_h // 4) * 4).zfill(2)
    _key   = f"{agent_name}_{_cycle}"
    try:
        with open(_path, encoding="utf-8") as _f:
            _data = json.load(_f)
        if _data.get("date") != _today:
            _data = {"date": _today}
    except Exception:
        _data = {"date": _today}
    _data[_key] = True
    if details:
        _data[f"{_key}_details"] = details
    try:
        with open(_path, "w", encoding="utf-8") as _f:
            json.dump(_data, _f, indent=2)
    except Exception as _de:
        print(f"   ⚠ _mark_done write failed: {_de}")
    try:
        _jspath = _path.replace("daily_status.json", "daily_status.js")
        with open(_jspath, "w", encoding="utf-8") as _f:
            _f.write("window.WHALE_STATUS=" + json.dumps(_data) + ";")
    except Exception as _je:
        print(f"   ⚠ _mark_done JS write failed: {_je}")


def log(msg):
    bkk = datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK")
    line = f"[{bkk}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def bkk_now_str():
    return datetime.now(BKK).strftime("%Y-%m-%d %H:%M BKK")


def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log(f"   ⚠ Telegram debrief send failed: {e}")


# ═══════════════════════════════════════════════════════════════
# PATTERN MEMORY  (read + write)
# ═══════════════════════════════════════════════════════════════

def load_memory():
    """Load existing pattern_memory.json. Returns the full dict."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"✗ pattern_memory.json corrupt or unreadable: {e} — starting fresh")
    return {"last_updated": "", "debriefs": []}


def already_debriefed(memory, coin, direction, debrief_at_approx, trade_unique_key=""):
    """
    Check if this specific trade was already debriefed.
    Uses coin+direction+trade_unique_key (resolved_at or tp_hit) to avoid
    dropping the 2nd trade for the same coin+direction in the same batch.
    Falls back to 5-minute timestamp proximity when trade_unique_key matches.
    """
    for d in memory.get("debriefs", []):
        if d.get("coin") == coin and d.get("direction") == direction:
            # NEW: require trade-unique field to also match (resolved_at or tp_hit)
            # OLD key was just coin+direction — caused silent drops in same-batch duplicates
            stored_unique = (d.get("resolved_at", "") or d.get("tp_hit", "") or "")
            if trade_unique_key and stored_unique and trade_unique_key != stored_unique:
                continue  # different trade — same coin+direction but different resolution
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

    # Compute consecutive_losses per coin + P&L stats (v47.34) — most recent first.
    # Stored separately so coin_lessons[coin] direction-loop is not disturbed.
    coin_stats = {}
    for c in coin_lessons:
        c_debriefs = [d for d in memory.get("debriefs", []) if d.get("coin", "") == c]
        c_debriefs.sort(key=lambda d: d.get("debrief_at", ""), reverse=True)
        c_debriefs = c_debriefs[:30]  # v47.37B: time-decay — only last 30 trades per coin
        consec = 0
        for d in c_debriefs:
            if d.get("outcome", "").upper() == "LOSS":
                consec += 1
            else:
                break
        # Consecutive wins (v47.36) — positive mirror of consecutive_losses
        consec_wins = 0
        for d in c_debriefs:
            if d.get("outcome", "").upper() == "WIN":
                consec_wins += 1
            else:
                break
        # Accumulate all-time wins / losses / P&L per coin (v47.34)
        _cw = sum(1 for d in c_debriefs if d.get("outcome", "").upper() == "WIN")
        _cl = sum(1 for d in c_debriefs if d.get("outcome", "").upper() == "LOSS")
        _cpnl_total = 0.0
        _cpnl_count = 0
        for _cd in c_debriefs:
            _cpnl_raw = _cd.get("pnl")
            if _cpnl_raw is not None:
                try:
                    _cpnl_total += float(_cpnl_raw)
                    _cpnl_count += 1
                except (TypeError, ValueError):
                    pass
        # Per-coin TP profile (v47.39B) — track which exit level each coin hits
        _tp_profile: dict = {"TP1": 0, "TP2": 0, "TP3": 0, "TP4": 0, "SL": 0}
        for _cd in c_debriefs:
            _cd_out = _cd.get("outcome", "").upper()
            _cd_tp  = (_cd.get("tp_hit", "") or "").upper().strip()
            if _cd_out == "LOSS":
                _tp_profile["SL"] += 1
            elif _cd_tp in ("TP1", "TP2", "TP3", "TP4"):
                _tp_profile[_cd_tp] += 1
        # Direction-specific consecutive streaks (v47.39C)
        _long_dbs  = [d for d in c_debriefs if d.get("direction", "").upper() == "LONG"]
        _short_dbs = [d for d in c_debriefs if d.get("direction", "").upper() == "SHORT"]
        consec_wins_long = consec_losses_long = 0
        for _d3 in _long_dbs:
            if _d3.get("outcome", "").upper() == "WIN":
                consec_wins_long += 1
            else:
                break
        for _d3 in _long_dbs:
            if _d3.get("outcome", "").upper() == "LOSS":
                consec_losses_long += 1
            else:
                break
        consec_wins_short = consec_losses_short = 0
        for _d3 in _short_dbs:
            if _d3.get("outcome", "").upper() == "WIN":
                consec_wins_short += 1
            else:
                break
        for _d3 in _short_dbs:
            if _d3.get("outcome", "").upper() == "LOSS":
                consec_losses_short += 1
            else:
                break
        coin_stats[c] = {
            "consecutive_losses":  consec,
            "consecutive_wins":    consec_wins,
            "consecutive_wins_long":    consec_wins_long,
            "consecutive_wins_short":   consec_wins_short,
            "consecutive_losses_long":  consec_losses_long,
            "consecutive_losses_short": consec_losses_short,
            "wins":       _cw,
            "losses":     _cl,
            "pnl_total":  round(_cpnl_total, 4),
            "pnl_count":  _cpnl_count,
            "tp_profile": _tp_profile,
        }
    # Carry forward max_consecutive_wins_ever + personal best alert (v47.39F)
    try:
        _old_cs_pb = memory.get("coin_stats", {})
        for _pbc, _pbv in coin_stats.items():
            _new_streak = _pbv.get("consecutive_wins", 0)
            _old_max    = _old_cs_pb.get(_pbc, {}).get("max_consecutive_wins_ever", 0)
            _new_max    = max(_new_streak, _old_max)
            coin_stats[_pbc]["max_consecutive_wins_ever"] = _new_max
            if _new_streak > _old_max and _new_streak >= 3:
                send_telegram(
                    f"🏆 <b>NEW WIN RECORD</b> — {_pbc}\n"
                    f"<b>{_new_streak} consecutive wins</b> — new all-time high!\n"
                    f"Previous record: {_old_max}  Keep the momentum going! 🚀"
                )
    except Exception:
        pass  # non-critical
    # Win-streak broken alert (v47.38A) — fires when a hot coin just lost.
    try:
        _old_cs_wb = memory.get("coin_stats", {})
        for _wbc, _wbv in coin_stats.items():
            _old_streak_wb = _old_cs_wb.get(_wbc, {}).get("consecutive_wins", 0)
            _new_streak_wb = _wbv.get("consecutive_wins", 0)
            if _old_streak_wb >= 3 and _new_streak_wb == 0:
                send_telegram(
                    f"📉 <b>WIN STREAK BROKEN</b> — {_wbc}\n"
                    f"Was on <b>{_old_streak_wb} consecutive wins</b> — just LOST\n"
                    f"Momentum may have shifted; monitor closely"
                )
    except Exception:
        pass  # non-critical
    memory["coin_stats"] = coin_stats

    # Compute MTF bias win rates across all debriefs
    mtf_stats = {}
    for d in memory.get("debriefs", []):
        mtf = d.get("mtf_bias", "")
        if not mtf or mtf in ("", "MTF_UNKNOWN"):
            continue
        if mtf not in mtf_stats:
            mtf_stats[mtf] = {"wins": 0, "losses": 0}
        if d.get("outcome", "").upper() == "WIN":
            mtf_stats[mtf]["wins"] += 1
        else:
            mtf_stats[mtf]["losses"] += 1
    memory["mtf_stats"] = mtf_stats

    # Compute signal score tier win rates (v47.22)
    # Tiers: 0-4 (weak), 5-6 (below floor / marginal), 7-8 (good), 9-10 (elite)
    score_tier_stats = {
        "0-4":  {"wins": 0, "losses": 0},
        "5-6":  {"wins": 0, "losses": 0},
        "7-8":  {"wins": 0, "losses": 0},
        "9-10": {"wins": 0, "losses": 0},
    }
    for d in memory.get("debriefs", []):
        _sc = d.get("score")
        if _sc is None:
            continue
        try:
            _sc = float(_sc)
        except (TypeError, ValueError):
            continue
        _tier = "0-4" if _sc <= 4 else ("5-6" if _sc <= 6 else ("7-8" if _sc <= 8 else "9-10"))
        if d.get("outcome", "").upper() == "WIN":
            score_tier_stats[_tier]["wins"] += 1
        else:
            score_tier_stats[_tier]["losses"] += 1
    memory["score_tier_stats"] = score_tier_stats

    # Compute score prediction accuracy per tier (v47.26)
    # "Correct" = high score predicts WIN, low score predicts LOSS.
    # ELITE(9-10) / GOOD(7-8): predicted WIN → correct if actual WIN
    # MARGINAL(5-6) / LOW(0-4): predicted LOSS → correct if actual LOSS
    _score_accuracy = {
        "ELITE":    {"correct": 0, "incorrect": 0},
        "GOOD":     {"correct": 0, "incorrect": 0},
        "MARGINAL": {"correct": 0, "incorrect": 0},
        "LOW":      {"correct": 0, "incorrect": 0},
    }
    for _d in memory.get("debriefs", []):
        _sc = _d.get("score")
        if _sc is None:
            continue
        try:
            _sc = float(_sc)
        except (TypeError, ValueError):
            continue
        _out = _d.get("outcome", "").upper()
        if _out not in ("WIN", "LOSS"):
            continue
        _acc_tier = ("ELITE" if _sc >= 9 else
                     "GOOD" if _sc >= 7 else
                     "MARGINAL" if _sc >= 5 else "LOW")
        _predicted_win = (_sc >= 7)    # ELITE/GOOD → expect WIN
        _actual_win    = (_out == "WIN")
        if _predicted_win == _actual_win:
            _score_accuracy[_acc_tier]["correct"] += 1
        else:
            _score_accuracy[_acc_tier]["incorrect"] += 1
    memory["score_accuracy"] = _score_accuracy

    # Score calibration drift (v47.39D) — write flag when ELITE signals lose >40%
    try:
        _elite_acc       = _score_accuracy.get("ELITE", {})
        _elite_correct   = _elite_acc.get("correct", 0)
        _elite_incorrect = _elite_acc.get("incorrect", 0)
        _elite_total     = _elite_correct + _elite_incorrect
        _cd_flag_path    = os.path.join(SCRIPT_DIR, "calibration_drift.json")
        if _elite_total >= 10:
            _elite_loss_rate = _elite_incorrect / _elite_total
            if _elite_loss_rate > 0.40:
                import json as _json_cd
                _cd_data = {
                    "issue":           "ELITE_SIGNALS_UNDERPERFORMING",
                    "elite_loss_rate": round(_elite_loss_rate, 3),
                    "elite_total":     _elite_total,
                    "elite_incorrect": _elite_incorrect,
                    "note": (f"ELITE signals (score≥9) losing {_elite_loss_rate*100:.0f}% "
                             f"({_elite_incorrect}/{_elite_total}) — scorer may need recalibration"),
                    "flagged_at": datetime.now(BKK).strftime("%Y-%m-%d %H:%M"),
                }
                with open(_cd_flag_path, "w", encoding="utf-8") as _cdf:
                    _json_cd.dump(_cd_data, _cdf, indent=2)
                log(f"   ⚠ CALIBRATION DRIFT: ELITE loss rate {_elite_loss_rate*100:.0f}% → flag written")
            else:
                if os.path.exists(_cd_flag_path):
                    os.remove(_cd_flag_path)
    except Exception:
        pass  # non-critical

    # Exit quality tracking by score tier (v47.35) ─────────────────────────────
    # Tracks which TP level (or SL) was hit per score tier.
    # Helps assess whether TP targets are calibrated for ELITE vs GOOD vs MARGINAL.
    _exit_tiers = ("ELITE", "GOOD", "MARGINAL", "LOW")
    _exit_slots  = ("TP1", "TP2", "TP3", "TP4", "SL", "other")
    _exit_stats  = {t: {s: 0 for s in _exit_slots} | {"total": 0} for t in _exit_tiers}
    for _ed in memory.get("debriefs", []):
        _esc = _ed.get("score")
        if _esc is None:
            continue
        try:
            _esc = float(_esc)
        except (TypeError, ValueError):
            continue
        _eout = _ed.get("outcome", "").upper()
        if _eout not in ("WIN", "LOSS"):
            continue
        _etier = ("ELITE" if _esc >= 9 else "GOOD" if _esc >= 7 else
                  "MARGINAL" if _esc >= 5 else "LOW")
        _etp   = (_ed.get("tp_hit", "") or "").upper().strip()
        if _eout == "LOSS":
            _ekey = "SL"
        elif _etp.startswith("TP") and _etp in ("TP1", "TP2", "TP3", "TP4"):
            _ekey = _etp
        else:
            _ekey = "other"
        _exit_stats[_etier][_ekey]    += 1
        _exit_stats[_etier]["total"]  += 1
    memory["exit_stats"] = _exit_stats

    # TP calibration suggestion (v47.36) ─────────────────────────────────────
    # If ELITE signals are mostly stopping at TP1, TPs may be too aggressive.
    # If ELITE signals are >60% TP3+, TPs may be too conservative.
    # Writes tp_calibration.json when imbalance detected; clears it when balanced.
    try:
        _tpc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tp_calibration.json")
        _elite_es = _exit_stats.get("ELITE", {})
        _tpc_total = _elite_es.get("total", 0)
        if _tpc_total >= 10:
            _tpc_tp1    = _elite_es.get("TP1", 0)
            _tpc_tp34   = _elite_es.get("TP3", 0) + _elite_es.get("TP4", 0)
            _tpc_tp1_rt = _tpc_tp1  / _tpc_total
            _tpc_hi_rt  = _tpc_tp34 / _tpc_total
            if _tpc_tp1_rt > 0.60:
                _tpc_msg = (
                    f"ELITE signals stopping mostly at TP1 "
                    f"({_tpc_tp1}/{_tpc_total} = {_tpc_tp1_rt*100:.0f}%) — "
                    f"TPs may be too aggressive; consider tightening TP2/TP3 targets"
                )
                _tpc_data = {
                    "issue":      "TP_TOO_AGGRESSIVE",
                    "tp1_rate":   round(_tpc_tp1_rt, 3),
                    "tp34_rate":  round(_tpc_hi_rt, 3),
                    "elite_total": _tpc_total,
                    "note":       _tpc_msg,
                    "updated_at": datetime.now(BKK).strftime("%Y-%m-%d %H:%M"),
                }
                with open(_tpc_path, "w", encoding="utf-8") as _tpcf:
                    json.dump(_tpc_data, _tpcf, indent=2)
            elif _tpc_hi_rt > 0.60:
                _tpc_msg = (
                    f"ELITE signals frequently reaching TP3+ "
                    f"({_tpc_tp34}/{_tpc_total} = {_tpc_hi_rt*100:.0f}%) — "
                    f"TPs may be too conservative; consider widening TP2/TP3 targets"
                )
                _tpc_data = {
                    "issue":      "TP_TOO_CONSERVATIVE",
                    "tp1_rate":   round(_tpc_tp1_rt, 3),
                    "tp34_rate":  round(_tpc_hi_rt, 3),
                    "elite_total": _tpc_total,
                    "note":       _tpc_msg,
                    "updated_at": datetime.now(BKK).strftime("%Y-%m-%d %H:%M"),
                }
                with open(_tpc_path, "w", encoding="utf-8") as _tpcf:
                    json.dump(_tpc_data, _tpcf, indent=2)
            else:
                # Balanced — clear any stale calibration file
                if os.path.exists(_tpc_path):
                    os.remove(_tpc_path)
    except Exception:
        pass  # non-critical

    # Per-proxy win correlation (v47.31) — identifies miscalibrated scorer dimensions
    # Tracks two inferable proxies from stored debrief fields:
    #   Confidence (dim 1 proxy): high/med/low confidence buckets
    #   MTF alignment (dim 6 proxy): ideal/aligned/neutral/counter/sideways
    _dim_corr = {
        "conf_high":    {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # confidence ≥90
        "conf_med":     {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # confidence 75-89
        "conf_low":     {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # confidence <75
        "mtf_ideal":    {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # 4H+1H ideal entry
        "mtf_aligned":  {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # 4H confirms direction, non-ideal 1H
        "mtf_neutral":  {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # no MTF data or unknown
        "mtf_counter":  {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # 4H opposes direction
        "mtf_sideways": {"wins": 0, "losses": 0, "pnl_total": 0.0, "pnl_count": 0},   # 4H sideways (indecision)
    }
    _dim_age_now = datetime.now(BKK)  # for pattern memory aging (v47.39E)
    for _d in memory.get("debriefs", []):
        _dout = _d.get("outcome", "").upper()
        if _dout not in ("WIN", "LOSS"):
            continue
        _dis_win = (_dout == "WIN")
        # Extract P&L for attribution (v47.33) — used alongside wins/losses per bucket
        try:
            _d_pnl_val = float(_d.get("pnl") or 0)
            _d_has_pnl = _d.get("pnl") is not None
        except (TypeError, ValueError):
            _d_pnl_val = 0.0
            _d_has_pnl = False
        # Pattern memory aging (v47.39E) — debriefs >60 days weighted 0.5×
        _d_age_wt = 1.0
        try:
            _d_ts_raw = (_d.get("debrief_at") or _d.get("resolved_at") or "")[:16]
            if _d_ts_raw:
                _d_dt = datetime.strptime(_d_ts_raw, "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
                if (_dim_age_now - _d_dt).days >= 60:
                    _d_age_wt = 0.5
        except Exception:
            pass

        # Confidence proxy (dim 1)
        try:
            _dc_conf = float(_d.get("confidence", 0) or 0)
            if _dc_conf >= 90:
                _dck = "conf_high"
            elif _dc_conf >= 75:
                _dck = "conf_med"
            else:
                _dck = "conf_low"
            if _dis_win: _dim_corr[_dck]["wins"]   += _d_age_wt
            else:        _dim_corr[_dck]["losses"] += _d_age_wt
            if _d_has_pnl:
                _dim_corr[_dck]["pnl_total"] += _d_pnl_val * _d_age_wt
                _dim_corr[_dck]["pnl_count"] += _d_age_wt
        except Exception:
            pass

        # MTF alignment proxy (dim 6)
        _dc_mtf = (_d.get("mtf_bias") or "").upper()
        _dc_dr  = (_d.get("direction") or "").upper()
        if _dc_mtf in ("4H_BULL_1H_PULLBACK", "4H_BEAR_1H_BOUNCE",
                       "4H_BULL_1H_BOT", "4H_BEAR_1H_TOP"):
            _dmk = "mtf_ideal"
        elif "SIDEWAYS" in _dc_mtf:
            _dmk = "mtf_sideways"
        elif _dc_mtf.startswith("4H_BULL") and _dc_dr == "LONG":
            _dmk = "mtf_aligned"
        elif _dc_mtf.startswith("4H_BEAR") and _dc_dr == "SHORT":
            _dmk = "mtf_aligned"
        elif _dc_mtf.startswith("4H_BULL") and _dc_dr == "SHORT":
            _dmk = "mtf_counter"
        elif _dc_mtf.startswith("4H_BEAR") and _dc_dr == "LONG":
            _dmk = "mtf_counter"
        else:
            _dmk = "mtf_neutral"
        if _dis_win: _dim_corr[_dmk]["wins"]   += _d_age_wt
        else:        _dim_corr[_dmk]["losses"] += _d_age_wt
        if _d_has_pnl:
            _dim_corr[_dmk]["pnl_total"] += _d_pnl_val * _d_age_wt
            _dim_corr[_dmk]["pnl_count"] += _d_age_wt

    memory["dim_correlation"] = _dim_corr

    # ── Dim health → scorer_tune.json (v47.32) ───────────────────────────────
    # When MTF dims underperform, escalate signal_scorer.py penalties automatically.
    # MTF counter: WR ≤ 30% over ≥15 trades → MTF_COUNTER_PENALTY -1 → -2
    # MTF sideways: WR ≤ 20% over ≥15 trades → MTF_SIDEWAYS_PENALTY -2 → -3
    # signal_scorer.py reads this file at import time.
    try:
        _st_path    = os.path.join(SCRIPT_DIR, "scorer_tune.json")
        _st_overrides: dict = {}
        _dc_now     = memory.get("dim_correlation", {})

        _mtf_ctr   = _dc_now.get("mtf_counter", {})
        _ctr_total = _mtf_ctr.get("wins", 0) + _mtf_ctr.get("losses", 0)
        if _ctr_total >= 15:
            _ctr_wr = _mtf_ctr.get("wins", 0) / _ctr_total
            if _ctr_wr <= 0.30:
                _st_overrides["MTF_COUNTER_PENALTY"] = -2
                log(f"   🎛 SCORER_TUNE: MTF_COUNTER_PENALTY → -2 "
                    f"(WR={_ctr_wr*100:.1f}% over {_ctr_total} trades)")

        _mtf_sw   = _dc_now.get("mtf_sideways", {})
        _sw_total = _mtf_sw.get("wins", 0) + _mtf_sw.get("losses", 0)
        if _sw_total >= 15:
            _sw_wr = _mtf_sw.get("wins", 0) / _sw_total
            if _sw_wr <= 0.20:
                _st_overrides["MTF_SIDEWAYS_PENALTY"] = -3
                log(f"   🎛 SCORER_TUNE: MTF_SIDEWAYS_PENALTY → -3 "
                    f"(WR={_sw_wr*100:.1f}% over {_sw_total} trades)")

        if _st_overrides:
            _st_overrides["tuned_at"] = bkk_now_str()
            _st_overrides["note"] = "Auto-tuned by debrief — MTF dim underperformance escalation"
            _old_st: dict = {}
            try:
                with open(_st_path, "r", encoding="utf-8") as _stf_r:
                    _old_st = json.load(_stf_r)
            except Exception:
                pass
            _st_changed = any(
                _old_st.get(k) != v for k, v in _st_overrides.items()
                if k not in ("tuned_at", "note")
            )
            if _st_changed:
                with open(_st_path, "w", encoding="utf-8") as _stf_w:
                    json.dump(_st_overrides, _stf_w, indent=2)
                log(f"   🎛 scorer_tune.json written: {_st_overrides}")
        else:
            # No escalation needed — remove file so scorer reverts to defaults
            try:
                if os.path.exists(_st_path):
                    os.remove(_st_path)
                    log("   🎛 scorer_tune.json cleared — MTF dims within normal range")
            except Exception:
                pass
    except Exception as _st_e:
        log(f"   ⚠ scorer_tune.json write failed (non-critical): {_st_e}")

    # Auto-blocklist: coins with ≥3 losses + 0 wins per direction (v47.28 LONG / v47.29 SHORT)
    # Writes coin_blocklist_auto.json — read by bot.py at startup.
    _aged_out_longs:  list = []   # initialised here; populated inside try below
    _aged_out_shorts: list = []   # used by probation block after the except
    try:
        _bl_long_wins: dict   = {}
        _bl_long_losses: dict  = {}
        _bl_short_wins: dict  = {}
        _bl_short_losses: dict = {}
        for _d in memory.get("debriefs", []):
            _bc  = _d.get("coin", "").upper()
            _bdr = _d.get("direction", "").upper()
            _bot = _d.get("outcome", "").upper()
            if not _bc or _bdr not in ("LONG", "SHORT"):
                continue
            if _bdr == "LONG":
                if _bot == "WIN":
                    _bl_long_wins[_bc]   = _bl_long_wins.get(_bc, 0) + 1
                elif _bot == "LOSS":
                    _bl_long_losses[_bc] = _bl_long_losses.get(_bc, 0) + 1
            else:  # SHORT
                if _bot == "WIN":
                    _bl_short_wins[_bc]   = _bl_short_wins.get(_bc, 0) + 1
                elif _bot == "LOSS":
                    _bl_short_losses[_bc] = _bl_short_losses.get(_bc, 0) + 1
        _auto_blocked_longs  = sorted([
            c for c, l in _bl_long_losses.items()
            if l >= 3 and _bl_long_wins.get(c, 0) == 0
        ])
        _auto_blocked_shorts = sorted([
            c for c, l in _bl_short_losses.items()
            if l >= 3 and _bl_short_wins.get(c, 0) == 0
        ])

        # ── Auto-blocklist aging (v47.31) ────────────────────────────────────
        # Coins blocked for >7 days with no fresh LOSS are auto-expired.
        # "Fresh" = any LOSS in the debrief history after the coin was first blocked.
        # Prevents permanent bans from a brief bad streak months ago.
        _bl_path = os.path.join(SCRIPT_DIR, "coin_blocklist_auto.json")
        _EXPIRY_DAYS = 7
        _now_bl_dt   = datetime.now(BKK)

        # Load existing blocked_since timestamps
        _existing_bl_data = {}
        try:
            if os.path.exists(_bl_path):
                with open(_bl_path, "r", encoding="utf-8") as _blf_old:
                    _existing_bl_data = json.load(_blf_old)
        except Exception:
            pass
        _existing_since = _existing_bl_data.get("blocked_since", {})

        # Build most-recent-LOSS timestamp per (coin, direction)
        _last_bl_loss: dict = {}
        for _dbl in memory.get("debriefs", []):
            if _dbl.get("outcome", "").upper() != "LOSS":
                continue
            _blc  = _dbl.get("coin", "").upper()
            _bldr = _dbl.get("direction", "").upper()
            _blts = _dbl.get("debrief_at", "")
            _blkey = f"{_blc}_{_bldr}"
            if _blts > _last_bl_loss.get(_blkey, ""):
                _last_bl_loss[_blkey] = _blts

        def _check_aged_out(coin_up, direction_up):
            """True if most recent LOSS for this coin+direction is >_EXPIRY_DAYS days old."""
            _bkey = f"{coin_up}_{direction_up}"
            _lts  = _last_bl_loss.get(_bkey, "")
            if not _lts:
                return False   # no LOSS at all — shouldn't happen but be safe
            try:
                _ldt = datetime.strptime(_lts[:16], "%Y-%m-%d %H:%M").replace(tzinfo=BKK)
                return (_now_bl_dt - _ldt).days >= _EXPIRY_DAYS
            except Exception:
                return False

        _aged_out_longs  = []
        _aged_out_shorts = []
        _blocked_since_out: dict = {}

        _final_blocked_longs = []
        for _blc in _auto_blocked_longs:
            if _check_aged_out(_blc, "LONG"):
                _aged_out_longs.append(_blc)
            else:
                _final_blocked_longs.append(_blc)
                _bskey = f"{_blc}_LONG"
                _blocked_since_out[_bskey] = _existing_since.get(_bskey, bkk_now_str())

        _final_blocked_shorts = []
        for _blc in _auto_blocked_shorts:
            if _check_aged_out(_blc, "SHORT"):
                _aged_out_shorts.append(_blc)
            else:
                _final_blocked_shorts.append(_blc)
                _bskey = f"{_blc}_SHORT"
                _blocked_since_out[_bskey] = _existing_since.get(_bskey, bkk_now_str())

        _auto_blocked_longs  = _final_blocked_longs
        _auto_blocked_shorts = _final_blocked_shorts

        if _aged_out_longs or _aged_out_shorts:
            for _agc in _aged_out_longs:
                log(f"   ⏳ AUTO-BLOCKLIST EXPIRED (LONG): {_agc} — no LOSS in >{_EXPIRY_DAYS}d")
            for _agc in _aged_out_shorts:
                log(f"   ⏳ AUTO-BLOCKLIST EXPIRED (SHORT): {_agc} — no LOSS in >{_EXPIRY_DAYS}d")
            _al_parts = []
            if _aged_out_longs:  _al_parts.append(f"LONGS [{', '.join(_aged_out_longs)}]")
            if _aged_out_shorts: _al_parts.append(f"SHORTS [{', '.join(_aged_out_shorts)}]")
            try:
                send_telegram(
                    f"⏳ <b>AUTO-BLOCKLIST EXPIRED</b> — {' | '.join(_al_parts)}\n"
                    f"No loss in >{_EXPIRY_DAYS} days. Coin(s) re-allowed — monitor first trades."
                )
            except Exception:
                pass
        # ── End aging block ──────────────────────────────────────────────────

        _bl_data = {
            "blocked_longs":  _auto_blocked_longs,
            "blocked_shorts": _auto_blocked_shorts,
            "blocked_since":  _blocked_since_out,
            "updated_at":     bkk_now_str(),
            "note": "Auto-generated by debrief — ≥3 losses + 0 wins per direction; 7-day expiry",
        }
        with open(_bl_path, "w", encoding="utf-8") as _blf:
            json.dump(_bl_data, _blf, indent=2)
        if _auto_blocked_longs:
            log(f"   🚫 AUTO-BLOCKLIST LONG: {', '.join(_auto_blocked_longs)}")
        if _auto_blocked_shorts:
            log(f"   🚫 AUTO-BLOCKLIST SHORT: {', '.join(_auto_blocked_shorts)}")
    except Exception as _bl_e:
        log(f"   ⚠ Auto-blocklist write failed (non-critical): {_bl_e}")

    # ── Probation watchlist (v47.32) ─────────────────────────────────────────
    # Coins that expire from the auto-blocklist enter a 3-trade probation period.
    # Any WIN clears probation. All losses re-block the coin immediately.
    # File: blocklist_watchlist.json — read by strategist (warning) + morning briefing.
    try:
        _wl_path = os.path.join(SCRIPT_DIR, "blocklist_watchlist.json")
        _existing_wl: dict = {}
        try:
            if os.path.exists(_wl_path):
                with open(_wl_path, "r", encoding="utf-8") as _wlf_r:
                    _existing_wl = json.load(_wlf_r)
        except Exception:
            pass
        _watchlist: dict = _existing_wl.get("watchlist", {})

        # ── Add newly expired coins to watchlist ──────────────────────────────
        for _agc in _aged_out_longs:
            _wkey = f"{_agc}_LONG"
            if _wkey not in _watchlist:
                _watchlist[_wkey] = {
                    "coin": _agc, "direction": "LONG",
                    "probation_trades": 3,
                    "probation_started": bkk_now_str(),
                }
                log(f"   🔶 PROBATION: {_agc} LONG — 3 trades to prove itself (expired from blocklist)")
        for _agc in _aged_out_shorts:
            _wkey = f"{_agc}_SHORT"
            if _wkey not in _watchlist:
                _watchlist[_wkey] = {
                    "coin": _agc, "direction": "SHORT",
                    "probation_trades": 3,
                    "probation_started": bkk_now_str(),
                }
                log(f"   🔶 PROBATION: {_agc} SHORT — 3 trades to prove itself (expired from blocklist)")

        # ── Review existing watchlist entries ─────────────────────────────────
        _to_clear_wl: list   = []
        _to_reblock_long_wl: list  = []
        _to_reblock_short_wl: list = []
        for _wkey, _wentry in list(_watchlist.items()):
            _wc  = _wentry.get("coin", "")
            _wdr = _wentry.get("direction", "")
            _wst = _wentry.get("probation_started", "")
            _wpt = int(_wentry.get("probation_trades", 3))
            if not (_wc and _wdr and _wst):
                continue
            # Count WIN / LOSS debriefs since probation started
            _prob_wins   = 0
            _prob_losses = 0
            for _dbl in memory.get("debriefs", []):
                if (_dbl.get("coin", "").upper()      != _wc or
                    _dbl.get("direction", "").upper()  != _wdr):
                    continue
                _dbl_ts = _dbl.get("debrief_at", "") or _dbl.get("ts", "")
                if _dbl_ts < _wst:
                    continue  # trade was before probation started
                _dbl_out = _dbl.get("outcome", "").upper()
                if _dbl_out == "WIN":
                    _prob_wins += 1
                elif _dbl_out == "LOSS":
                    _prob_losses += 1
            if _prob_wins > 0:
                # Any win → coin proved itself → clear probation
                _to_clear_wl.append(_wkey)
                log(f"   ✅ PROBATION CLEARED: {_wc} {_wdr} — {_prob_wins}W on probation")
                try:
                    send_telegram(
                        f"✅ <b>PROBATION CLEARED</b> — {_wc} {_wdr}\n"
                        f"Won on probation ({_prob_wins}W / {_prob_losses}L). Full trading resumed."
                    )
                except Exception:
                    pass
            elif _prob_losses >= _wpt:
                # Used all probation trades, all losses → re-block
                _to_clear_wl.append(_wkey)
                if _wdr == "LONG":
                    _to_reblock_long_wl.append(_wc)
                else:
                    _to_reblock_short_wl.append(_wc)
                log(f"   🔴 PROBATION FAILED: {_wc} {_wdr} — {_prob_losses}L, re-blocked")
                try:
                    send_telegram(
                        f"🔴 <b>PROBATION FAILED</b> — {_wc} {_wdr} re-BLOCKED\n"
                        f"All {_prob_losses} probation trades were losses. Added back to auto-blocklist."
                    )
                except Exception:
                    pass

        for _wkey in _to_clear_wl:
            _watchlist.pop(_wkey, None)

        # Re-add failed probation coins back to coin_blocklist_auto.json
        if _to_reblock_long_wl or _to_reblock_short_wl:
            try:
                _rbl_path = os.path.join(SCRIPT_DIR, "coin_blocklist_auto.json")
                _rbl_data: dict = {}
                if os.path.exists(_rbl_path):
                    with open(_rbl_path, "r", encoding="utf-8") as _rblf:
                        _rbl_data = json.load(_rblf)
                for _rc in _to_reblock_long_wl:
                    if _rc not in _rbl_data.get("blocked_longs", []):
                        _rbl_data.setdefault("blocked_longs", []).append(_rc)
                    _rbl_data.setdefault("blocked_since", {})[f"{_rc}_LONG"] = bkk_now_str()
                for _rc in _to_reblock_short_wl:
                    if _rc not in _rbl_data.get("blocked_shorts", []):
                        _rbl_data.setdefault("blocked_shorts", []).append(_rc)
                    _rbl_data.setdefault("blocked_since", {})[f"{_rc}_SHORT"] = bkk_now_str()
                _rbl_data["updated_at"] = bkk_now_str()
                with open(_rbl_path, "w", encoding="utf-8") as _rblf:
                    json.dump(_rbl_data, _rblf, indent=2)
            except Exception as _rbl_e:
                log(f"   ⚠ Probation re-block write failed: {_rbl_e}")

        # Write updated watchlist
        _wl_out = {
            "watchlist": _watchlist,
            "updated_at": bkk_now_str(),
            "note": "Coins on probation after auto-blocklist expiry — 3 trades to prove or re-block",
        }
        with open(_wl_path, "w", encoding="utf-8") as _wlf_w:
            json.dump(_wl_out, _wlf_w, indent=2)
        if _watchlist:
            log(f"   🔶 PROBATION watchlist: {', '.join(_watchlist.keys())}")
    except Exception as _wl_e:
        log(f"   ⚠ Probation watchlist write failed (non-critical): {_wl_e}")

    # Auto-tune score floor (v47.23): if tier 5-6 underperforms, raise gate to 6
    # Threshold: ≥8 trades in tier 5-6 AND WR < 45% → write scorer_config.json
    # trader.py reads this at startup to override SCORE_MIN_TRADER constant.
    try:
        _t56 = score_tier_stats.get("5-6", {})
        _t56_w = _t56.get("wins", 0)
        _t56_l = _t56.get("losses", 0)
        _t56_n = _t56_w + _t56_l
        _cfg_path = os.path.join(SCRIPT_DIR, "scorer_config.json")
        if _t56_n >= 8:
            _t56_wr = _t56_w / _t56_n
            _new_floor = 6 if _t56_wr < 0.45 else 5
            _old_cfg = {}
            try:
                with open(_cfg_path, "r", encoding="utf-8") as _cf:
                    _old_cfg = json.load(_cf)
            except Exception:
                pass
            if _old_cfg.get("SCORE_MIN_TRADER") != _new_floor:
                _cfg_data = {"SCORE_MIN_TRADER": _new_floor,
                             "auto_tuned_at": bkk_now_str(),
                             "basis": f"tier5-6: {_t56_w}W/{_t56_l}L = {_t56_wr*100:.1f}% WR"}
                with open(_cfg_path, "w", encoding="utf-8") as _cf:
                    json.dump(_cfg_data, _cf, indent=2)
                log(f"   🎛 AUTO-TUNE: SCORE_MIN_TRADER → {_new_floor} "
                    f"(tier5-6 WR={_t56_wr*100:.1f}% over {_t56_n} trades) → scorer_config.json")
    except Exception as _at_e:
        log(f"   ⚠ Auto-tune write failed (non-critical): {_at_e}")

    # Auto-write AVOID lessons for chronic pattern+time loss combos (v47.25)
    # Logic: for each (coin, direction, pattern, 4h-slot) combo, if ≥3 losses
    # AND WR < 40%, write an [AVOID] lesson into coin_lessons if not already present.
    try:
        _combo_stats: dict = {}   # (coin, direction, pat_short, slot) → {wins, losses}
        _ts_fmt = "%Y-%m-%d %H:%M"
        for _db in memory.get("debriefs", []):
            _c  = _db.get("coin", "")
            _dr = _db.get("direction", "")
            _pa = _db.get("pattern", "").strip()[:50]
            _ts = _db.get("ts", "").replace(" BKK", "")
            if not (_c and _dr and _pa and _ts):
                continue
            try:
                _dt   = __import__("datetime").datetime.strptime(_ts[:16], _ts_fmt)
                _slot = (_dt.hour // 4) * 4
            except Exception:
                continue
            _key = (_c, _dr, _pa, _slot)
            if _key not in _combo_stats:
                _combo_stats[_key] = {"wins": 0, "losses": 0}
            _out = _db.get("outcome", "").upper()
            if _out == "WIN":
                _combo_stats[_key]["wins"] += 1
            elif _out == "LOSS":
                _combo_stats[_key]["losses"] += 1

        _new_avoid_count = 0
        _cl = memory.get("coin_lessons", {})
        for (_c, _dr, _pa, _slot), _cv in _combo_stats.items():
            _tot = _cv["wins"] + _cv["losses"]
            if _cv["losses"] < 3 or _tot < 3:
                continue
            _wr = _cv["wins"] / _tot
            if _wr >= 0.40:
                continue
            # Build the lesson text
            _lesson = (
                f"[AVOID] {_pa} at {_slot:02d}:00 BKK — "
                f"{_cv['losses']}L/{_tot} = {_wr*100:.0f}% WR (chronic loss combo)"
            )
            # Check not already present
            _cl.setdefault(_c, {}).setdefault(_dr, [])
            _existing = _cl[_c][_dr]
            _already  = any(_pa[:30] in ex and f"{_slot:02d}:00" in ex for ex in _existing)
            if not _already:
                _existing.append(_lesson)
                _cl[_c][_dr] = _existing[-5:]   # keep last 5 per coin+direction
                _new_avoid_count += 1
                log(f"   🚫 AUTO-AVOID: {_c} {_dr} — {_pa[:40]} @ {_slot:02d}:00 BKK "
                    f"({_cv['losses']}L/{_tot}, {_wr*100:.0f}% WR)")
        memory["coin_lessons"] = _cl
        if _new_avoid_count:
            log(f"   🚫 Pattern+time AVOID lessons written: {_new_avoid_count} new combo(s)")
    except Exception as _av_e:
        log(f"   ⚠ Pattern+time AVOID write failed (non-critical): {_av_e}")

    try:
        _tmp = MEMORY_FILE + ".tmp"
        with open(_tmp, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        os.replace(_tmp, MEMORY_FILE)
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


# ═══════════════════════════════════════════════════════════════
# MULTI-AGENT CONSENSUS LAYER  (Principle 5)
# Cross-reference Strategist's pre-trade call vs actual outcome.
# ═══════════════════════════════════════════════════════════════

def load_strategist_decision(coin, direction):
    """
    Load the Strategist's last decision for this coin+direction.
    Returns a dict with keys: decision, confidence, reasoning — or None.
    """
    try:
        with open(STRATEGIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for d in data.get("decisions", []):
            if (d.get("coin", "").upper() == coin.upper()
                    and d.get("direction", "").upper() == direction.upper()):
                return d
    except Exception:
        pass
    return None


def consensus_verdict(strat_decision, outcome):
    """
    Given the Strategist's pre-trade call and the actual outcome,
    return a short verdict for the debrief context.
    """
    if not strat_decision:
        return "No Strategist decision found for this trade (may have pre-dated Strategist)."

    action = strat_decision.get("action", strat_decision.get("decision", "UNKNOWN")).upper()
    if "APPROVE" in action:
        if outcome == "WIN":
            return f"✅ CONSENSUS VALIDATED — Strategist APPROVED, trade WON. Reinforce this assessment pattern."
        else:
            return f"❌ CONSENSUS MISS — Strategist APPROVED but trade LOST. Review approval logic for this setup."
    elif "VETO" in action:
        if outcome == "WIN":
            return f"⚠️ VETO WAS WRONG — Strategist VETOED but trade would have WON. Review veto criteria."
        else:
            return f"✅ VETO SAVED US — Strategist VETOED and trade would have LOST. Veto logic validated."
    elif "REDUCE" in action:
        return f"📉 STRATEGIST REDUCED SIZE — outcome was {outcome}."
    return f"Strategist action: {action} | Outcome: {outcome}"


def _extract_mtf_bias(pattern_str):
    """
    Extract mtf_bias from pattern string like "Bull flag [4H_BULL_1H_PULLBACK]".
    Returns the bias string or "" if not found.
    """
    import re as _re
    m = _re.search(r'\[([A-Z0-9_]{5,30})\]', str(pattern_str))
    if m:
        candidate = m.group(1)
        # Only accept known MTF bias format strings
        if candidate.startswith(("4H_", "MTF_")):
            return candidate
    return ""


def build_debrief_prompt(trade):
    """Build the user message for Claude Haiku debrief."""
    coin      = trade.get("coin", "?")
    direction = trade.get("direction", "?")
    outcome   = trade.get("outcome", "?")
    tp_hit    = trade.get("tp_hit", "")
    pnl       = float(trade.get("pnl", 0) or 0)           # sheet may send as string; cast to float
    pattern   = trade.get("pattern", "unknown")
    mtf_bias  = trade.get("mtf_bias", "") or _extract_mtf_bias(pattern)
    confidence= float(trade.get("confidence", 0) or 0)   # tracker sends as string; cast to float
    entry     = trade.get("entry", 0)
    exit_price= trade.get("exit_price", 0)

    outcome_detail = f"{outcome}"
    if tp_hit:
        outcome_detail += f" — {tp_hit} hit"
    if pnl is not None:  # include 0.0 breakeven closes
        outcome_detail += f" — P&L: {pnl:+.1f}%"

    mtf_note = f"\n  MTF Bias:   {mtf_bias} (4H+1H chart structure at signal time)" if mtf_bias else ""

    # ── Multi-agent consensus layer (Principle 5) ─────────────
    strat_decision = load_strategist_decision(coin, direction)
    consensus      = consensus_verdict(strat_decision, outcome)
    strat_note     = ""
    if strat_decision:
        action    = strat_decision.get("action", strat_decision.get("decision", "?"))
        reasoning = strat_decision.get("reasoning", strat_decision.get("reason", ""))
        strat_note = (
            f"\nStrategist Pre-Trade Call:\n"
            f"  Action:    {action}\n"
            f"  Reasoning: {reasoning}\n"
            f"  Consensus: {consensus}"
        )

    return f"""Trade to debrief:
  Coin:       {coin}
  Direction:  {direction}
  Pattern:    {pattern}{mtf_note}
  Confidence: {confidence:.0f}%
  Entry:      {entry:.6g}
  Exit:       {exit_price:.6g}
  Outcome:    {outcome_detail}
{strat_note}
Context:
  We use 10× leverage on Bybit demo.
  A+ entries move immediately to TP2+. Poor entries sit near entry or reverse before recovering.
  Our known loser patterns: RS failure, dead cat bounce, meme continuation, "Continuation breakout" standalone.
  Our known winner patterns: Stage 5 distribution collapse (SHORT), Stage 2 expansion (LONG).
  MTF bias context: 4H_BULL_1H_PULLBACK = ideal LONG entry. 4H_BEAR_1H_BOUNCE = ideal SHORT entry.
  4H_SIDEWAYS = structural indecision — these should rarely win.
  If Strategist was WRONG (approved a loser / vetoed a winner), your lesson should address WHY.
  If mtf_bias was 4H_SIDEWAYS and trade lost — lesson should flag "avoid 4H_SIDEWAYS entries".

Analyse this trade including the Strategist consensus. Return JSON only."""


# ═══════════════════════════════════════════════════════════════
# CLAUDE API CALL
# ═══════════════════════════════════════════════════════════════

def call_debrief_claude(prompt):
    """Call Claude Haiku for a single trade debrief. Returns parsed dict or None."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=30.0)
    msg = client.messages.create(
        model=DEBRIEF_MODEL,
        max_tokens=450,   # raised from 320 — prevents truncation mid-JSON on multi-field responses
        system=[{"type": "text", "text": DEBRIEF_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip() if msg.content else ""
    if not raw:
        return None

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
    debriefs_written = []

    for trade in trades:
        coin      = trade.get("coin", "?")
        direction = trade.get("direction", "?")
        outcome   = trade.get("outcome", "?")

        # Refresh now per trade — prevents false dedup when batch shares one timestamp
        # (e.g. 5 trades in same run: trades 2–5 would all match trade 1's timestamp within 5min)
        now = bkk_now_str()

        # Skip if already debriefed (duplicate call guard)
        # Use resolved_at or tp_hit as trade-unique key to avoid dropping
        # 2nd trade for same coin+direction resolved in the same batch.
        _trade_unique = trade.get("resolved_at", "") or trade.get("tp_hit", "") or ""
        if already_debriefed(memory, coin, direction, now, _trade_unique):
            log(f"   Skip {coin} {direction} — already debriefed")
            continue

        log(f"   Debriefing {coin} {direction} {outcome}...")

        # Load Strategist context for consensus (Principle 5)
        strat_decision = load_strategist_decision(coin, direction)
        consensus_note = consensus_verdict(strat_decision, outcome)

        prompt = build_debrief_prompt(trade)
        try:
            result = call_debrief_claude(prompt)
        except Exception as _e:
            log(f"   ⚠ Claude call failed for {coin} {direction}: {_e}")
            result = None  # will fall through to the fallback minimal entry

        if not result:
            log(f"   ✗ Claude parse failed for {coin} {direction}")
            # Write minimal entry without Claude analysis
            result = {
                "entry_quality": "?" ,
                "why":    f"{outcome} — Claude unavailable",
                "lesson": "Review manually",
                "flag":   "NEUTRAL",
            }

        _pattern_str = trade.get("pattern", "")
        _mtf_bias_parsed = _extract_mtf_bias(_pattern_str)

        entry = {
            "coin":          coin,
            "direction":     direction,
            "outcome":       outcome,
            "tp_hit":        trade.get("tp_hit", ""),
            "resolved_at":   trade.get("resolved_at", ""),   # stored for dedup uniqueness
            "ts":            trade.get("ts", ""),             # signal generation time (v47.27)
            "pnl":           float(trade.get("pnl", 0) or 0),
            "pattern":       _pattern_str,
            "mtf_bias":      _mtf_bias_parsed,               # e.g. "4H_BULL_1H_PULLBACK"
            "confidence":    trade.get("confidence", 0),
            "entry_quality": result.get("entry_quality", "?"),
            "why":           result.get("why", ""),
            "lesson":        result.get("lesson", ""),
            "flag":          result.get("flag", "NEUTRAL"),
            "debrief_at":    now,
            # Signal scorer quality score (v47.22) — from strategist_decisions.json
            "score":         strat_decision.get("score") if strat_decision else None,
            # Multi-agent consensus (Principle 5)
            "strat_action":  strat_decision.get("action", "") if strat_decision else "",
            "consensus":     consensus_note,
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

    # ── Sync trade_logger after every resolution ─────────────────
    # Keeps trade_log.json current so Strategist scorer WR is live.
    try:
        from trade_logger import sync_from_sheets as _tl_sync
        print("\n📊 Syncing trade_logger (post-debrief)...")
        _tl_sync()
    except Exception as _tl_e:
        log(f"   ⚠ trade_logger sync failed (non-critical): {_tl_e}")

    # ── Telegram summary (ops channel) — multi-agent consensus ──
    lines = [f"🧠 <b>TEAM DEBRIEF</b> — {len(debriefs_written)} trade(s) | Multi-Agent Consensus"]
    for d in debriefs_written:
        icon      = "✅" if d["outcome"] == "WIN" else "❌"
        flag_icon = "🔁" if d["flag"] == "REINFORCE" else ("🚫" if d["flag"] == "AVOID" else "➡️")
        pnl_str   = f"{d['pnl']:+.1f}%" if d.get("pnl") is not None else ""
        consensus = d.get("consensus", "")
        mtf_tag   = f" [{d['mtf_bias']}]" if d.get("mtf_bias") else ""
        _sc       = d.get("score")
        score_tag = f" 📊{_sc:.0f}/10" if _sc is not None else ""
        lines.append(
            f"  {icon} <b>{d['coin']} {d['direction']}</b> [{d['entry_quality']}]{mtf_tag}{score_tag} {pnl_str}\n"
            f"  Why: {d['why']}\n"
            f"  {flag_icon} Lesson: {d['lesson']}\n"
            f"  🤝 {consensus}"
        )
    send_telegram("\n".join(lines))

    # ── Score tier drift alert (v47.29) ──────────────────────────────────────
    # Fire immediate Telegram alert if any tier crosses below 45% accuracy over ≥10 trades.
    # Catches scorer decay in real-time — don't wait for Sunday analyze_shorts.py run.
    try:
        _drift_alerts = []
        _sacc_fresh = memory.get("score_accuracy", {})
        for _tier_name in ("ELITE", "GOOD", "MARGINAL"):
            _tc = _sacc_fresh.get(_tier_name, {}).get("correct", 0)
            _ti = _sacc_fresh.get(_tier_name, {}).get("incorrect", 0)
            _tt = _tc + _ti
            if _tt < 10:
                continue
            _tacc = _tc / _tt * 100
            if _tacc < 45:
                if _tier_name == "ELITE":
                    _advice = "recalibrate dim weights or raise ELITE gate to 9.5"
                elif _tier_name == "GOOD":
                    _advice = "scores 7-8 underperform — raise gate to 8"
                else:
                    _advice = "scorer not flagging losers — review dims 3+5"
                _drift_alerts.append(
                    f"  🚨 {_tier_name}: {_tacc:.0f}% acc ({_tc}✓/{_ti}✗, {_tt} trades)\n"
                    f"     → {_advice}"
                )
        if _drift_alerts:
            _alert_msg = (
                "🚨 <b>SCORER DRIFT ALERT</b> — accuracy below 45% threshold:\n"
                + "\n".join(_drift_alerts)
                + "\n\nReview signal_scorer.py dims and thresholds."
            )
            send_telegram(_alert_msg)

        # ── Score gate auto-tune (v47.30) ─────────────────────────────────────
        # If any tier drifted, bump SCORE_MIN_TRADER to 7 via score_gate_override.json.
        # If ALL tracked tiers have recovered (≥55% over ≥10 trades), revert the override.
        _sgov_path = os.path.join(SCRIPT_DIR, "score_gate_override.json")
        if _drift_alerts:
            # Write / refresh the override
            _current_override = 5   # default floor
            try:
                if os.path.exists(_sgov_path):
                    with open(_sgov_path, "r", encoding="utf-8") as _sgr:
                        _current_override = int(json.load(_sgr).get("SCORE_MIN_TRADER", 5))
            except Exception:
                pass
            _new_floor = max(_current_override, 7)   # bump to at least 7; never lower
            try:
                with open(_sgov_path, "w", encoding="utf-8") as _sgw:
                    json.dump({
                        "SCORE_MIN_TRADER": _new_floor,
                        "reason":           "scorer drift >45% threshold — auto-bumped by debrief",
                        "since":            bkk_now_str(),
                    }, _sgw, indent=2)
                log(f"   🎛 score_gate_override.json written: SCORE_MIN_TRADER={_new_floor}")
            except Exception as _sge:
                log(f"   ⚠ score_gate_override write failed: {_sge}")
        else:
            # Check for recovery — all tiers ≥55% over ≥10 trades → revert override
            _all_recovered = True
            for _r_tier in ("ELITE", "GOOD", "MARGINAL"):
                _rc = _sacc_fresh.get(_r_tier, {}).get("correct", 0)
                _ri = _sacc_fresh.get(_r_tier, {}).get("incorrect", 0)
                _rt = _rc + _ri
                if _rt < 10:
                    _all_recovered = False   # insufficient data — leave override in place
                    break
                if _rc / _rt < 0.55:
                    _all_recovered = False
                    break
            if _all_recovered and os.path.exists(_sgov_path):
                try:
                    os.remove(_sgov_path)
                    log("   ✅ score_gate_override.json REMOVED — all tiers ≥55% accuracy (scorer recovered)")
                    send_telegram("✅ <b>SCORER RECOVERED</b> — all tiers ≥55% accuracy. score_gate_override.json removed; SCORE_MIN_TRADER reverts to default.")
                except Exception:
                    pass

        # ── Score drift EARLY WARNING (v47.33) ────────────────────────────────
        # Warning zone: 45-54% accuracy over ≥10 trades (fires BEFORE gate at <45%).
        # Sends ⚠️ Telegram + writes score_drift_warning.json so morning briefing
        # can surface it alongside the harder score_gate_override.json alert.
        try:
            _sdw_path = os.path.join(SCRIPT_DIR, "score_drift_warning.json")
            _warn_tiers: list = []
            _sacc_w = memory.get("score_accuracy", {})
            for _wt in ("ELITE", "GOOD", "MARGINAL"):
                _wc = _sacc_w.get(_wt, {}).get("correct", 0)
                _wi = _sacc_w.get(_wt, {}).get("incorrect", 0)
                _wn = _wc + _wi
                if _wn >= 10:
                    _wacc = _wc / _wn
                    if 0.45 <= _wacc < 0.55:   # warning zone — below 45% is already handled above
                        _warn_tiers.append((_wt, _wacc, _wn))

            if _warn_tiers:
                # Load existing warning file to avoid re-alerting identical state
                _existing_warn: dict = {}
                try:
                    if os.path.exists(_sdw_path):
                        with open(_sdw_path, "r", encoding="utf-8") as _sdwr:
                            _existing_warn = json.load(_sdwr)
                except Exception:
                    pass

                _new_warn_data = {
                    "warned_tiers": {t: {"accuracy": round(a, 4), "n": n}
                                     for t, a, n in _warn_tiers},
                    "since": _existing_warn.get("since", bkk_now_str()),
                    "updated_at": bkk_now_str(),
                    "note": "Score accuracy 45-54%: pre-gate drift warning",
                }

                _tier_lines = [f"{t}: {a*100:.1f}% ({n} trades)" for t, a, n in _warn_tiers]
                _warn_msg = (
                    f"⚠️ <b>SCORE DRIFT WARNING</b>\n"
                    f"Tier accuracy slipping into 45-54% warning zone "
                    f"(gate fires at &lt;45%):\n"
                    + "\n".join(f"  • {l}" for l in _tier_lines)
                    + "\n\nMonitor debrief cycles — if accuracy drops below 45% the score gate will raise automatically."
                )
                send_telegram(_warn_msg)
                with open(_sdw_path, "w", encoding="utf-8") as _sdww:
                    json.dump(_new_warn_data, _sdww, indent=2)
                log(f"   ⚠ Score drift WARNING written: {[t for t,_,_ in _warn_tiers]}")

            else:
                # No tiers in warning zone — clear stale warning file if present
                if os.path.exists(_sdw_path):
                    try:
                        os.remove(_sdw_path)
                        log("   ✅ score_drift_warning.json cleared — all tiers exited warning zone")
                    except Exception:
                        pass
        except Exception as _sdw_e:
            log(f"   ⚠ Score drift warning check failed (non-critical): {_sdw_e}")

    except Exception:
        pass  # non-critical


def main():
    """
    Entry point when called by tracker.py via subprocess.
    Argument: JSON string of trade list.
    """
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   🧠  WHALE-STREAM DEBRIEF AGENT v47.26              ║")
    print("║   Post-Trade Learning — every loss teaches us        ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    if len(sys.argv) < 2:
        log("✗ No trade data argument provided. Usage: python whale_stream_debrief.py '<json>'")
        _mark_done(details={"error": "no_arg"})
        return

    try:
        if "--from-file" in sys.argv and len(sys.argv) > 2:
            # New protocol: tracker writes JSON to a temp file to avoid Windows 8191-char CLI limit
            _data_path = sys.argv[1]  # first positional arg is the .json temp file path
            with open(_data_path, "r", encoding="utf-8") as _f:
                trades = json.load(_f)
            try:
                os.remove(_data_path)  # clean up temp file
            except Exception:
                pass
        else:
            trades = json.loads(sys.argv[1])  # old protocol — backwards compat
        if not isinstance(trades, list):
            trades = [trades]
    except Exception as e:
        log(f"✗ Failed to parse trade data: {e}")
        _mark_done(details={"error": "parse_failed"})
        return

    log(f"=== Debrief run — {len(trades)} trade(s) to analyse ===")
    run_debrief(trades)
    _mark_done(details={"trades": len(trades)})
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
