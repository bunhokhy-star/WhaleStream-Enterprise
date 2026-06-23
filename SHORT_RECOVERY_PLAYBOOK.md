# WHALE-STREAM — SHORT RECOVERY PLAYBOOK

> **Purpose:** Step-by-step rules for safely resuming SHORT signals after repair mode lifts.
> SHORT repair mode was triggered on 2026-06-21 when true SHORT WR was found to be 25%
> (6W/24 real trades). Last-20 rolling WR is 30.0% — 20 percentage points below the 50%
> recovery target. This document defines the recovery protocol.

---

## WHAT TRIGGERS RECOVERY

Recovery is **automatic** when `analyze_shorts.py` detects:
- Last 20 real SHORT trades WR ≥ 50%
- `short_repair.flag` is deleted by the script
- Telegram alert fired: "SHORT WR RECOVERED — REPAIR MODE LIFTED"

Manual override: Run `LIFT_SHORT_REPAIR.bat` and type YES (use only if you have strong reason).

---

## CURRENT STATE (as of 2026-06-21)

| Metric | Value |
|--------|-------|
| Total SHORTs placed | 24 |
| SHORT WR overall | 25.0% (6W / 18L) |
| Last-20 rolling WR | 30.0% (6W / 14L) |
| Gap to recovery target | 20.0% below 50% |
| Avg confidence on SHORT WINs | 88.2% |
| Avg confidence on SHORT LOSSes | 89.1% |
| Winning SHORT coins | H (75%), FF (100%), CHZ (100%) |
| SHORT wins all hit | TP1 only — no TP2/TP3/TP4 reached |
| Avg SHORT win P&L | +145.2% |

**Key finding:** Confidence level has NO predictive power for SHORTs — WINs and LOSSes have
virtually identical average confidence (88.2% vs 89.1%). Higher confidence does NOT improve
SHORT outcomes. The 90–92% band is performing WORST (14.3% WR).

---

## PHASE 1: FIRST 20 RECOVERY SHORTS (Days 1–5 after flag lifts)

### Confidence floor
**Minimum 90% confidence** for the first 20 SHORT trades after repair mode lifts.

> Note: Because confidence has no predictive power in SHORT signals, raising the floor above 90%
> does not improve outcomes — it only reduces signal volume. Keep at 90% and rely on
> coin/pattern filtering instead.

### Coin rules for Phase 1 — PERMANENT BANS (never trade SHORT again)

Based on `analysis_shorts.txt` SHORT LOSSES BY COIN section:

| Coin | SHORT Record | Avg Conf | Avg Loss | Ban type |
|------|-------------|----------|----------|----------|
| ENA  | 0W / 5L — WR: 0% | 89.4% | ~-60.6% | PERMANENT |
| WLD  | 0W / 2L — WR: 0% | 91.0% | ~-49.7% | PERMANENT |
| INJ  | 0W / 2L — WR: 0% | 89.0% | ~-59.8% | PERMANENT |
| XLM  | 0W / 2L — WR: 0% | 88.5% | ~-38.0% | PERMANENT |
| BCH  | 0W / 2L — WR: 0% | 87.5% | ~-44.0% | PERMANENT |
| VVV  | 0W / 2L — WR: 0% | 89.0% | ~-57.9% | PERMANENT |
| ZRO  | 0W / 1L — WR: 0% | 89.0% | ~-40.9% | PERMANENT |
| AVAX | 0W / 1L — WR: 0% | 86.0% | ~-49.1% | PERMANENT |

These coins must be in `SHORT_COIN_BLOCKLIST` in `whale_stream_bot.py` — code enforced.
✅ All 8 coins confirmed in blocklist as of v46.5 (Task #84).

### Coin rules for Phase 1 — APPROVED SHORT COINS (known winners)

Only coins with a demonstrated SHORT win record should be prioritised during recovery:

| Coin | SHORT Record | Notes |
|------|-------------|-------|
| H    | 3W / 1L — WR: 75% | Best SHORT coin in the dataset — prioritise |
| FF   | 2W / 0L — WR: 100% | Small sample but perfect record — allow |
| CHZ  | 1W / 0L — WR: 100% | Small sample — allow but watch closely |

For all other coins not in the permanent ban list and not in the approved list above:
require independent structural confirmation before accepting (see Pattern rules below).

### TP1 minimum distance (already enforced in code)
- SHORT TP1 must be ≥ 3% from entry midpoint
- Enforced in `log_to_google_sheets()` — signals with smaller TP1 rejected as INVALID

---

## WHAT A VALID RECOVERY SHORT LOOKS LIKE

Root causes of the SHORT failure: wrong-direction SL placement and TP1 too close to entry
(fake WINs). Both are caught at code level. But pattern selection also matters — see below.

A valid recovery SHORT must clear ALL of these:

1. SL/TP direction check: SL above entry, TP1 below entry ✅ code-enforced
2. TP1 ≥ 3% from entry ✅ code-enforced
3. Coin not in permanent ban list ✅ code-enforced
4. Confidence ≥ 90% — prompt instruction
5. Pattern from the TRUST list below — prompt instruction
6. NOT during BTC dominance > 58% (alt SHORTs fail in BTC flight-to-safety)

---

## PATTERNS: TRUST vs AVOID

Based on `analysis_shorts.txt` SHORT WIN RATE BY PATTERN — actual trade outcomes:

### Patterns that produced SHORT WINs (trust in recovery phase)

| Pattern | Record | Notes |
|---------|--------|-------|
| laggard breakdown | 1W / 0L — 100% | Strong directional conviction |
| rs failure — dead (cat) | 1W / 0L — 100% | Dead cat failure = continuation down |
| 7d persistent downtrend (-14.71%) | 1W / 0L — 100% | Trend continuation, strong negative 7d |
| rs failure — catastrophic | 1W / 0L — 100% | Severe RS failure = momentum SHORT |
| breakdown continuation (large %) | 1W / 0L — 100% | Breakdown with -16.19% continuation |
| stage 5 distribution collapse | 1W / 0L — 100% | Wyckoff distribution confirmed |

**Common thread in SHORT WINs:** Large percentage moves already in motion (-13% to -16% context),
clear structural breakdown confirmed, or genuine stage 5 distribution. These are NOT early shorts —
they are confirmation-based entries where the move has already started.

### Patterns that produced ONLY SHORT LOSSes (avoid in recovery phase)

| Pattern | Record | Notes |
|---------|--------|-------|
| rs failure — 7d | 0W / 2L | Relative strength failure alone, insufficient |
| lh/ll breakdown | 0W / 3L (across variants) | Lower high/low structure — too early |
| 7d negative divergence | 0W / 1L | Divergence without confirmation |
| rs failure (small %) | 0W / 3L (across variants) | RS failure with small 7d negative % |
| breakdown continuation (small %) | 0W / 1L | -1.41% context — too shallow |
| dead cat bounce failure | 0W / 1L | Timing risk — bounce may continue |
| rs failure — stage | 0W / 1L | Stage-based RS failure, vague |
| lh/ll structure — breakdown | 0W / 1L | Structure play without momentum |
| bearish continuation — stage | 0W / 1L | Stage-based continuation, insufficient |
| breakdown — small 24h move | 0W / 1L | -3.42% 24h — too shallow for entry |
| stage 5 distribution (non-collapse) | 0W / 1L | Distribution without collapse trigger |
| breakdown retest | 0W / 1L | Retest timing risky — bounce risk |

**Summary of what to avoid:** Any SHORT based on structure alone (LH/LL, RS failure with
small %, early distribution) without a large confirmed move. The market is currently in a
regime where these early-pattern SHORTs reverse.

---

## PHASE 2: AFTER 20 RECOVERY SHORTS (Ongoing)

Once 20 SHORTs have been placed post-repair and the rolling WR tracks at ≥ 50%:

- Maintain 90% confidence floor for SHORTs (confidence is not predictive — don't lower it further)
- Allow maximum 2 SHORTs per run (keep at 2 during stabilisation, not 3)
- Continue monitoring via `analyze_shorts.py` every Sunday
- Reassess coin ban list — if a coin not on the approved list achieves 2+ SHORT wins, it may be added to the approved list

If WR drops below 45% at any point in a rolling 10-trade window → re-enter repair mode
manually by running:

```
echo SHORT re-entered repair mode %date% %time% > C:\Users\MAX\WhaleStream\short_repair.flag
```

---

## MONITORING DASHBOARD

After repair mode lifts, check these weekly:

| Metric | Target | How to check |
|--------|--------|--------------|
| SHORT WR (last 20) | ≥ 50% | `analyze_shorts.py` → SHORT RECOVERY DETECTION section |
| SHORT confidence predictiveness | WINs > LOSSes conf by ≥ 2% | `analyze_shorts.py` → SHORT WR BY CONFIDENCE BAND |
| No banned coin slippage | 0 violations | `analyze_logs.py` → INVALID signal counts |
| TP1 minimum enforced | 0 fake WINs | Filter: abs(P&L) ≥ 5% on all SHORT WINs |
| Approved coin coverage | ≥ 3 coins producing wins | SHORT WINS BY COIN section |

**Warning sign:** If SHORT WINs continue to cluster exclusively on H/FF/CHZ while other
coins keep losing, the system has a coin-selection problem, not a general SHORT problem.

---

## EMERGENCY RE-ENTRY

If SHORT WR collapses again after recovery (< 40% in 10 trades):

1. Re-create `short_repair.flag`:
   ```
   echo EMERGENCY REPAIR MODE > C:\Users\MAX\WhaleStream\short_repair.flag
   ```
2. Run `analyze_shorts.py` immediately to diagnose
3. Check `analyze_logs.py` for INVALID signal pattern — are blocklisted coins slipping through?
4. Review last 10 SHORT signal patterns in Google Sheets — are LOSS-pattern types re-appearing?
5. Check if any new coins with 0% WR over 3+ trades need to be added to permanent ban list

---

## CHECKLIST: BEFORE ACCEPTING FIRST POST-RECOVERY SHORT

Run through this before the system fires its first SHORT after flag lifts:

- [ ] `short_repair.flag` is confirmed deleted (not just absent — check `analyze_shorts.py` output)
- [ ] SHORT_COIN_BLOCKLIST in `whale_stream_bot.py` includes: ENA, WLD, INJ, XLM, BCH, VVV, ZRO, AVAX
- [ ] Coin is either on the approved list (H, FF, CHZ) or has a verified breakdown pattern with large % move
- [ ] Pattern matches the TRUST list above — not a structure-only play
- [ ] Confidence ≥ 90%
- [ ] BTC dominance < 58%
- [ ] TP1 is ≥ 3% below entry (will be rejected at code level if not, but verify)

---

*Created: 2026-06-21 | Updated: 2026-06-21 | WHALE-STREAM v46.8 | CEO Autonomy Mode*
*Source data: `analysis_shorts.txt` run at 2026-06-21 22:49 — 24 total SHORTs, 6W/18L, 25.0% WR*
*Update Phase 1 → Phase 2 transition date when 20 recovery SHORTs complete.*
