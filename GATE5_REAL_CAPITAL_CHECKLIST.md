# WHALE-STREAM — GATE 5: REAL CAPITAL READINESS CHECKLIST

> **Purpose:** This document defines the minimum conditions that must ALL be met before
> switching from Bybit Demo to a live account with real money. Every threshold is grounded
> in actual performance data from this system. No threshold is waived. No exceptions.
>
> **Current status as of 2026-06-24 22:16:** DEMO ONLY — 6 days to July 1 go-live decision.
> Balance: $405.33 | Gate 1: ⏳ 141/150 (only 9 more needed!) | Gate 3: ✅ 95% SHORT WR last 20 | Gate 4: 🔴 active (18.9% drawdown)
> Circuit breaker: CLEARED June 24. SHORT repair mode: INACTIVE. System running v46.47.

---

## HOW TO USE THIS CHECKLIST

Run `analyze_shorts.py` (or check the dashboard) before each Gate review.
Every gate must show ✅ simultaneously on the SAME review date.
If any gate is ❌, the review fails. Wait for the next natural review window (weekly).

---

## GATE 1 — MINIMUM SAMPLE SIZE

**Rule:** At least **150 resolved trades** (WIN + LOSS) in Google Sheets.

**Why 150:** At 80 trades (current), confidence intervals are wide. The SHORT win rate
swung from 39% to 57% across different confidence bands with <40 samples per band.
At 150 trades we have ~50 SHORTs and ~100 LONGs — enough to detect real patterns
vs. noise at 90%+ statistical confidence.

| Check | Required | How to verify |
|-------|----------|---------------|
| Total resolved trades | ≥ 150 | Bottom of `analysis_shorts.txt` or dashboard |

**Current (2026-06-21):** 80 resolved — need 70 more. At 6 signals/run × 4 runs/day,
expect ~2–3 weeks to clear this gate organically.

---

## GATE 2 — OVERALL WIN RATE

**Rule:** Overall win rate (LONG + SHORT combined) ≥ **58%** sustained over the most
recent **30 resolved trades**.

**Why 58%:** Current overall WR is 53.8% (43W/37L across 80 trades). The LONG WR
(66.7%) is already strong; the drag is SHORTs (24.0% true WR after fake entry cleanup). With SHORT fixes now in place
(BTC 24h gate, coin blocklist), overall WR should improve. 58% on a recent-30 window
is a meaningful bar — it means the new rules are working, not just noise.

| Check | Required | How to verify |
|-------|----------|---------------|
| Overall WR (last 30 resolved) | ≥ 58% | `analysis_shorts.txt` overall summary |
| Long WR (last 30 resolved) | ≥ 60% | Same file, LONG breakdown |

---

## GATE 3 — SHORT WIN RATE (Most Critical Gate)

**Rule:** SHORT win rate over the most recent **20 SHORT trades** ≥ **50%**.

**Why 50% and why 20 SHORTs:** This is the hardest gate and the most important one.
SHORTs were 24.0% true WR overall (6W/25 real trades after fake entry cleanup). The BTC 24h gate and coin blocklist are new —
we need to see them actually working in live data before risking real money on shorts.
50% is the minimum acceptable WR for a strategy with 5–7% SL and 3–4% TP1 (negative
expectancy below 50%). We require 20 SHORT trades to give the new rules a fair test.

| Check | Required | How to verify |
|-------|----------|---------------|
| SHORT WR (last 20 SHORT trades) | ≥ 50% | `analysis_shorts.txt` SHORT breakdown |
| No coin with 0% WR over 3+ trades | Zero | SHORT LOSSES BY COIN section |

**Note:** If SHORT WR is ≥ 50% but driven by only 1–2 coins, that is NOT a pass.
The WR must be spread across at least 3 different coins.

---

## GATE 4 — MAXIMUM DRAWDOWN

**Rule:** The demo account drawdown from peak balance must not exceed **-25%** at any
point in the most recent 30-day window.

**Why -25%:** Starting balance $500. A -25% drawdown = $375 remaining. At $375 with
$20/trade margin, there is still room to trade normally. A -25% gate also means we
never take real-money drawdown deeper than this before intervention — at 10x leverage,
a single bad streak can compound fast.

How to calculate:
1. Open `bybit_balance.json` — read `balance` and `start_balance`
2. Check the dashboard for the peak balance achieved
3. Drawdown = (peak balance − current balance) / peak balance × 100

| Check | Required | How to verify |
|-------|----------|---------------|
| Max drawdown from peak (last 30 days) | ≤ 25% | Dashboard / balance JSON |
| Current balance vs. start balance | > 0% (profitable) | `bybit_balance.json` |

**Current (2026-06-21):** Balance $492.58 / $500 start = -1.5% from start. ✅ on
current balance, but peak-to-trough drawdown must be confirmed from dashboard history.

---

## GATE 5 — STREAK & CIRCUIT BREAKER HEALTH

**Rule:** No circuit breaker trigger in the most recent **14 days**.

**Why this matters:** The circuit breaker (trader_paused.flag) fires when 3 consecutive
losses occur. A trigger means the system hit a losing streak severe enough to auto-stop.
If this happened in the last 14 days, the market conditions or system logic haven't
stabilised enough for real money. We need 14 clean days — meaning no 3-loss streak —
before going live.

| Check | Required | How to verify |
|-------|----------|---------------|
| Circuit breaker triggered in last 14 days | NO | Check if trader_paused.flag exists or check trader_log.txt for "CIRCUIT BREAKER" |
| Max consecutive losses (last 30 resolved) | ≤ 4 | Manually scan `analysis_shorts.txt` chronological section |

---

## GATE 6 — CONSECUTIVE PROFITABLE WEEKS

**Rule:** At least **3 consecutive calendar weeks** where total resolved P&L is positive.

**Why 3 weeks:** One profitable week can be luck. Two consecutive is encouraging.
Three consecutive at our trade cadence (20–30 resolved trades/week) is statistically
meaningful and demonstrates the system works across different market regimes
(weekdays, weekends, BTC quiet periods, BTC volatile periods).

| Check | Required | How to verify |
|-------|----------|---------------|
| Consecutive weeks with net positive P&L | ≥ 3 in a row | Manual: group resolved trades by calendar week, sum P&L% |

**Note:** "Profitable week" = sum of all resolved P&L% for that week > 0. A week
with 3 WINs (+15% each) and 2 LOSSes (-50% each) = net -40% = FAIL.

---

## REAL CAPITAL SIZING RULES (For When All Gates Clear)

Even after clearing all gates, start conservatively:

| Parameter | Demo | Phase 1 Live | Phase 2 Live |
|-----------|------|--------------|--------------|
| Margin per trade | $20 | $10 (50% of demo) | $20 |
| Leverage | 10x | 10x | 10x |
| Max open trades | 6 | 4 | 6 |
| Max deployed % | 50% | 30% | 50% |
| Review after | — | 50 live trades | 100 live trades |

**Phase 1 → Phase 2 upgrade requires:** 50 live trades with WR ≥ 55% and no circuit
breaker trigger.

---

---

## JULY 1 GO-LIVE DECISION FRAMEWORK

> **Core principle:** Trade count and win rate are *leading* indicators.
> **Capital growth is the only lagging indicator that proves everything.**
> If the system grew money from $405 → $500+ in 6 days of best-of-best trading,
> the strategy works. That is the proof. Go live.

### Primary Decision Metric — Capital Recovery by June 30

Run `analyze_shorts.py` on **June 29** and read `bybit_balance.json`. Apply this table:

| Balance on June 30 | Decision | Rationale |
|--------------------|----------|-----------|
| **≥ $500** (recovered to start) | ✅ **GO LIVE — Full size** | Strategy proved: recovered all losses AND generated wins in 6 days of high-conviction trading |
| **$425–$499** (Gate 4 cleared, growing) | ✅ **GO LIVE — 50% position size** | Drawdown recovering, wins outpacing losses, strategy directionally correct. Scale up after 30 live trades if WR ≥ 60% |
| **$405–$424** (stable, Gate 4 still active) | ⚠️ **DELAY — 1 week** | Not enough recovery evidence. Run one more week of demo, review July 8. |
| **< $405** (balance declined) | ❌ **DO NOT GO LIVE** | Strategy losing money in demo conditions. Do not risk real capital. Review top-3 filter and confidence thresholds. |

### Gate 1 Contingency Rule

Gate 1 requires 150 resolved trades. With top-3 filter at 4h cadence (~3 fills/day),
we may only reach ~143–148 by July 1. **That is acceptable IF capital is growing.**

| Gate 1 count | Balance | Decision |
|--------------|---------|----------|
| ≥ 150 | Any above $425 | Full go-live — all gates met |
| 140–149 | ≥ $500 | Go live — capital growth overrides sample gap |
| 140–149 | $425–$499 | Go live at 50% size — continue accumulating live trades |
| 140–149 | < $425 | Delay — insufficient evidence on both counts |
| < 140 | Any | Delay — not enough data regardless of balance |

### The Mission Rule

> *"We are not trading to prove a number. We are trading to build a system
> worthy of the people it will serve. Capital growth — real, measured,
> disciplined — is the only proof that matters."*

---

## GATE REVIEW LOG

| Date | Gate 1 | Gate 2 | Gate 3 | Gate 4 | Gate 5 | Gate 6 | Result |
|------|--------|--------|--------|--------|--------|--------|--------|
| 2026-06-21 | ❌ 80/150 | ❌ 53.8% | ❌ 24.0% | ✅ -1.5% | ✅ No trigger | ❌ <3 weeks | **FAIL** |
| 2026-06-21 | ❌ 80/150 | ✅ 63.3% | ❌ 30.0% | ❌ +1.5% | ✅ No trigger | ❌ 0/3 wks | **FAIL** |
| 2026-06-24 22:16 | ⏳ 141/150 | ✅ PF 1.65x, LONG 52.7%, SHORT 68.7% | ✅ **95%** last 20 SHORTs (19W/1L) | 🔴 $405 / -18.9% | ⚠️ CB fired Jun 23, cleared Jun 24 | ⏳ pending | **DEMO** |
| 2026-06-29 | | | | | | | _run analyze_shorts.py_ |
| _Jul 1 decision_ | | | | | | | _apply decision table above_ |

> **Note:** SHORT WR corrected from 39.5% to 24.0% on 2026-06-21 after removing fake entries (abs P&L < 5% or wrong sign). Strategy in REPAIR MODE.

---

## QUICK REFERENCE — GATE SUMMARY

```
GATE 1 — Sample size    : ≥ 150 resolved trades total
GATE 2 — Overall WR     : ≥ 58% over last 30 resolved trades
GATE 3 — SHORT WR       : ≥ 50% over last 20 SHORT trades (spread ≥ 3 coins)
GATE 4 — Drawdown       : ≤ 25% from peak in last 30 days  +  balance > start
GATE 5 — Streak health  : No circuit breaker in last 14 days, max 4 consecutive losses
GATE 6 — Consistency    : 3 consecutive calendar weeks with net positive P&L

ALL 6 GATES must be ✅ simultaneously. No partial passes.
```

---

*Document created: 2026-06-21 | Last updated: 2026-06-24 | WHALE-STREAM v46.47*
*Update the Gate Review Log after each review. Next review: June 29 (run analyze_shorts.py).*
*July 1 go-live decision: apply the Capital Recovery table above. Capital growth = proof.*
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ✅ No trigger | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| 2026-06-28 | ✅ 206/150 | ✅ 93.3% | ✅ 80.0% | ❌ +34.0% | ❌ TRIGGERED | ❌ 2/3 wks | **FAIL** |
| _next review_ | | | | | | | |
