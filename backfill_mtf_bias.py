"""
backfill_mtf_bias.py — ONE-TIME script (v47.20)
================================================
Re-extracts mtf_bias from the 'pattern' field of all existing debrief entries
in pattern_memory.json and rebuilds mtf_stats from scratch.

Run ONCE after deploying v47.20.  Safe to re-run — idempotent.

Usage:
    python backfill_mtf_bias.py
"""

import os
import re
import json
from datetime import datetime, timezone, timedelta

BKK = timezone(timedelta(hours=7))
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MEM_PATH  = os.path.join(BASE_DIR, "pattern_memory.json")
BACKUP_PATH = MEM_PATH + ".pre_backfill_bak"


def extract_mtf_bias(pattern_str: str) -> str:
    """Extract MTF bias tag from a pattern string, e.g. 'Bull flag [4H_BULL_1H_PULLBACK]'."""
    m = re.search(r'\[([A-Z0-9_]{5,30})\]', str(pattern_str))
    if m:
        candidate = m.group(1)
        if candidate.startswith(("4H_", "MTF_")):
            return candidate
    return ""


def main():
    print("=" * 60)
    print("BACKFILL MTF BIAS — WHALE-STREAM v47.20")
    print("=" * 60)

    if not os.path.exists(MEM_PATH):
        print(f"❌ pattern_memory.json not found at: {MEM_PATH}")
        return

    with open(MEM_PATH, encoding="utf-8") as f:
        memory = json.load(f)

    debriefs = memory.get("debriefs", [])
    print(f"   Found {len(debriefs)} debrief entries.")

    # ── Backup original ────────────────────────────────────────
    with open(BACKUP_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Backup saved → {BACKUP_PATH}")

    # ── Backfill mtf_bias on each entry ───────────────────────
    updated = 0
    already = 0
    no_pattern = 0

    for d in debriefs:
        pattern = d.get("pattern", "")
        if not pattern:
            no_pattern += 1
            continue

        extracted = extract_mtf_bias(pattern)

        existing = d.get("mtf_bias", "")
        if existing and existing not in ("", "MTF_UNKNOWN"):
            already += 1
            # Even if already set, re-extract in case it was wrong
            if extracted and extracted != existing:
                print(f"   ↪ {d.get('coin','?')} pattern updated: {existing!r} → {extracted!r}")
                d["mtf_bias"] = extracted
                updated += 1
            continue

        if extracted:
            d["mtf_bias"] = extracted
            updated += 1
        else:
            d["mtf_bias"] = d.get("mtf_bias", "")   # leave as-is (might be "" already)

    print(f"   Updated:       {updated} entries with new/corrected mtf_bias")
    print(f"   Already set:   {already} entries (unchanged)")
    print(f"   No pattern:    {no_pattern} entries (skipped)")

    # ── Rebuild mtf_stats from scratch ────────────────────────
    mtf_stats: dict = {}
    for d in debriefs:
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
    memory["debriefs"]  = debriefs

    # ── Save ──────────────────────────────────────────────────
    tmp = MEM_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)
    os.replace(tmp, MEM_PATH)

    print(f"\n   ✅ pattern_memory.json saved.")
    print(f"\n{'─'*40}")
    print("   MTF BIAS WIN RATE SUMMARY (rebuilt):")
    print(f"{'─'*40}")
    if mtf_stats:
        for bias, cnts in sorted(mtf_stats.items()):
            w   = cnts["wins"]
            l   = cnts["losses"]
            tot = w + l
            wr  = 100 * w / tot if tot > 0 else 0
            flag = "✅" if wr >= 60 else ("⚠️ " if wr >= 45 else "🚫")
            note = " (< 3 trades)" if tot < 3 else ""
            print(f"  {flag} {bias:<30} {w}W/{l}L = {wr:.0f}%{note}")
    else:
        print("  (no mtf_bias entries found in any debrief)")

    print(f"\n   Done at {datetime.now(BKK).strftime('%Y-%m-%d %H:%M BKK')}")
    print("   Run this script ONCE. If you re-run it, the backup will be overwritten.")


if __name__ == "__main__":
    main()
