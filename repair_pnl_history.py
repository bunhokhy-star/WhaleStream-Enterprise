"""
repair_pnl_history.py — One-time script to fix corrupted P&L values in Google Sheets.

ROOT CAUSE:
  When whale_stream_tracker.py wrote P&L as "+218.75%" using value_input_option="USER_ENTERED",
  Google Sheets interpreted the % sign as the percentage operator and stored 2.1875 (÷ 100)
  as the cell value. On re-read via get_all_values(), cells without explicit format return
  "2.1875" instead of "218.75%", causing all P&L stats to be wrong.

FIX APPLIED IN v46.36:
  New P&L writes now use "+218.75% [T]" suffix (stored as text, Sheets can't misinterpret it).
  This script repairs HISTORICAL rows that still have the old corrupted format.

USAGE:
  python repair_pnl_history.py           # Dry run — shows changes without applying
  python repair_pnl_history.py --apply   # Applies all fixes to Google Sheets
"""

import sys
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Auto-install dependencies ──────────────────────────────────────────────────
import importlib, subprocess
for pkg in ("gspread", "oauth2client"):
    try:
        importlib.import_module(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet",
                               "--break-system-packages"])

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ── Config (matches whale_stream_tracker.py) ───────────────────────────────────
GOOGLE_SHEET_ID       = "1R21mkduSpbki2HmlNJMHM95-LkGS0q-AKHE1HVIfMmI"
GOOGLE_CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "google_credentials.json")
SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

COL_STATUS     = 11   # L — "WIN" / "LOSS" / "OPEN" / "EXPIRED"
COL_PNL        = 15   # P — P&L%

DRY_RUN = "--apply" not in sys.argv


def _try_float(s):
    """Parse raw cell string as float. Returns None on failure."""
    try:
        return float(str(s).strip())
    except (ValueError, TypeError):
        return None


def classify_cell(raw: str):
    """
    Returns (action, new_value, reason) or (None, None, reason_to_skip).

    Actions:
      "multiply100"  — plain decimal, multiply × 100 and add % [T]
      "add_suffix"   — already has %, just add [T] suffix
      "already_ok"   — has [T] or [B], skip
      "skip"         — empty, error, or unrecognised
    """
    raw = raw.strip()
    if not raw or raw in ("", "#N/A", "#ERROR!", "—", "None"):
        return "skip", None, "empty/error"

    # Already correctly formatted
    if " [T]" in raw or " [B]" in raw:
        return "already_ok", None, "already has [T]/[B]"

    # Contains % sign → might be formatted text like "218.75%" or "60.00%"
    if "%" in raw:
        m = re.search(r"([+-]?\d+(?:\.\d+)?)", raw)
        if not m:
            return "skip", None, "has % but can't parse number"
        val = float(m.group(1))
        new = f"{val:+.2f}% [T]"
        return "add_suffix", new, f"has % → add [T]: {raw!r} → {new!r}"

    # Plain number (no % sign)
    val = _try_float(raw)
    if val is None:
        return "skip", None, f"can't parse as float: {raw!r}"

    # Heuristic: corrupted P&L stored as decimal (all real trades at 10× leverage
    # have P&L in range -100% to +300%, stored as -1.0 to +3.0 after Sheets ÷100).
    # Values > 3.5 were probably entered correctly as plain percentages (e.g., 218.75).
    if abs(val) > 3.5:
        # Already a percentage value, just missing the suffix
        new = f"{val:+.2f}% [T]"
        return "add_suffix", new, f"large plain number → % [T]: {raw!r} → {new!r}"
    else:
        # Small decimal — multiply × 100 to recover original percentage
        corrected = val * 100
        new = f"{corrected:+.2f}% [T]"
        return "multiply100", new, f"decimal × 100: {raw!r} ({val}) → {new!r}"


def main():
    print("=" * 62)
    print(f"  WHALE-STREAM P&L History Repair  —  {'DRY RUN' if DRY_RUN else '⚡ APPLY MODE'}")
    print("=" * 62)
    print()

    # Use google.oauth2 directly — bypasses gspread.auth which fails on some Python 3.14 setups
    from google.oauth2.service_account import Credentials as _GCreds
    import gspread as _gspread
    _SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _GCreds.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=_SCOPES)
    gc = _gspread.Client(auth=creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    ws = sh.get_worksheet(0)

    rows = ws.get_all_values()
    print(f"Sheet rows loaded: {len(rows)}")
    print()

    repairs = []     # (row_1based, col_1based, new_val, reason)
    counts  = {"already_ok": 0, "skip": 0, "multiply100": 0, "add_suffix": 0}

    for i, row in enumerate(rows):
        row_num = i + 1
        if row_num == 1:
            continue  # header

        if len(row) <= max(COL_STATUS, COL_PNL):
            continue

        status = str(row[COL_STATUS]).strip().upper()
        if status not in ("WIN", "LOSS"):
            continue

        raw_pnl = str(row[COL_PNL]).strip() if len(row) > COL_PNL else ""
        action, new_val, reason = classify_cell(raw_pnl)

        counts[action] = counts.get(action, 0) + 1

        if action in ("multiply100", "add_suffix"):
            repairs.append((row_num, COL_PNL + 1, new_val, reason, status))

    # ── Summary ──────────────────────────────────────────────────────────────
    total_resolved = counts["already_ok"] + counts["skip"] + counts["multiply100"] + counts["add_suffix"]
    print(f"Resolved rows scanned  : {total_resolved}")
    print(f"  Already correct [T]/[B]: {counts['already_ok']}")
    print(f"  Skipped (empty/error)  : {counts['skip']}")
    print(f"  Needs repair           : {len(repairs)}")
    print(f"    — Decimal × 100      : {counts['multiply100']}")
    print(f"    — Add [T] suffix     : {counts['add_suffix']}")
    print()

    if not repairs:
        print("✓ Nothing to repair — all P&L values look clean.")
        return

    print("Cells to repair:")
    print(f"  {'Row':>4}  {'Status':6}  {'Old value':>20}  →  New value")
    print(f"  {'-'*4}  {'-'*6}  {'-'*20}     {'-'*25}")
    for row_num, col_num, new_val, reason, status in repairs:
        # Extract old value for display
        old_raw = rows[row_num - 1][COL_PNL] if len(rows[row_num - 1]) > COL_PNL else ""
        print(f"  {row_num:>4}  {status:6}  {old_raw:>20}  →  {new_val}")
    print()

    if DRY_RUN:
        print("DRY RUN complete. No changes made.")
        print("Run with --apply to apply fixes:")
        print("    python repair_pnl_history.py --apply")
    else:
        print(f"Writing {len(repairs)} fixes to Google Sheets...")
        batch_data = []
        for row_num, col_num, new_val, reason, status in repairs:
            cell_a1 = gspread.utils.rowcol_to_a1(row_num, col_num)
            batch_data.append({
                "range": cell_a1,
                "values": [[new_val]]
            })

        # Write in chunks of 100 to stay within Sheets API limits
        CHUNK = 100
        for start in range(0, len(batch_data), CHUNK):
            chunk = batch_data[start:start + CHUNK]
            ws.batch_update(chunk, value_input_option="RAW")
            print(f"  ✓ Wrote rows {start+1}–{min(start+CHUNK, len(batch_data))}")

        print()
        print(f"✅ Done! {len(repairs)} P&L values repaired.")
        print("Stats will now reflect real P&L on the next tracker run.")
        print("Run analyze_shorts.py to see corrected performance breakdown.")


if __name__ == "__main__":
    main()
