# 🐳 WHALE-STREAM — Real-Trade Readiness Checklist

> Last updated: 2026-06-21
> Current status: **TESTING PHASE** — Not yet ready for live capital

---

## 📊 Current Stats (as of 2026-06-21 BKK — v46.3 active)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Win Rate | 50.7% | ≥ 50% | ✅ PASS |
| Long Win Rate | 63.2% | ≥ 55% | ✅ PASS |
| Short Win Rate | 37.8% | ≥ 45% | ❌ FAIL |
| Expectancy | +35.7% | > 0% | ✅ PASS |
| Profit Factor | 1.43 | ≥ 1.3 | ✅ PASS |
| Resolved Trades | 75 | ≥ 100 | ❌ FAIL |
| EXPIRED Rate | ~50% | < 15% | ❌ FAIL (historical) |

**Root cause found today**: v46.1 Bybit filter only checked `symbol in bybit_map` but allowed coins with `price=0`. ZEC, AKT, DEXE passed the filter → signaled → no Bybit price in tracker → EXPIRED. **Fixed in v46.2** with `price > 0` requirement.

## 🛠️ v46.2 Improvements Applied (2026-06-21)

| Fix | Impact | Description |
|-----|--------|-------------|
| SHORT OVERSOLD REJECT | 🔴 HIGH | Reject SHORT if coin already down >20% in 7d or >12% in 24h |
| Stage Filter Tightened | 🔴 HIGH | Only Stage 4-5 shorts allowed (was only Stage 1 rejected) |
| SHORT Entry Rule | 🟡 MEDIUM | Wait for dead-cat bounce to resistance — not breakdown candle |
| Bybit Filter Bug Fix | 🔴 HIGH | Require price>0 — prevents ZEC/AKT/DEXE signaling |
| SHORT WR in Graveyard | 🟡 MEDIUM | Explicit SHORT WR + auto-blacklist now shown in graveyard |
| Bull Market Short Veto | 🔴 HIGH | BTC 7d >+8% → skip shorts unless 97% confidence |
| Stats _is_real_pnl filter | 🟡 MEDIUM | print_stats + circuit breaker now exclude old ratio data |
| **Programmatic SHORT filter** | 🔴 HIGH | Python hard-drops shorts below 95% conf when WR<40%, below 93% when WR<45% |

---

## ✅ Gate 1: Data Quality (Must Pass All)

- [ ] **Minimum 100 properly-resolved trades** (WIN or LOSS, not EXPIRED)
  - Current: 75 resolved. Need 25 more.
  - v46.1 Bybit filter now prevents new EXPIRED accumulation.

- [ ] **EXPIRED rate below 15%** of all trades
  - Current: 76 expired out of 151 total = 50%. Historic problem.
  - All future signals (post v46.1) should expire at near-0%.
  - Target: wait for old expired trades to be replaced by new clean ones.

- [ ] **No bot errors in last 7 days** — check bot_log.txt for exceptions

- [ ] **Tracker running cleanly for 7 days** — no crashes, no "no Bybit price found" for valid coins

---

## ✅ Gate 2: Performance (Must Pass All)

- [ ] **Win Rate ≥ 50%** over the last 100 resolved trades
  - Current: 50.7% total, but sample includes old noisy data.
  - Need 100-trade rolling window confirmed.

- [ ] **Short Win Rate ≥ 45%**
  - Current: 37.8%. This is the weakest point.
  - v46.2 applies 5 new short quality rules — expected to materially improve next 20-30 trades.
  - Key fixes: OVERSOLD REJECT, Stage 4-5 ONLY, better entry discipline, Bybit filter bug fixed.

- [ ] **Expectancy > +15%** per trade at 10x leverage
  - Current: +35.7% ✅ (strong edge)

- [ ] **Profit Factor ≥ 1.3**
  - Current: 1.43 ✅

- [ ] **Max Drawdown < -200%** in last 30 trades
  - Current: -576% total (includes old bad data). Need clean-data window.

- [ ] **No loss streak > 6 in a row** during the test period
  - Current: 5× loss streak (borderline). Circuit breaker is active.

---

## ✅ Gate 3: System Reliability (Must Pass All)

- [ ] **Task Scheduler confirmed running** both Bot and Tracker tasks
  - Bot: every 2 hours ✅
  - Tracker: every 30 minutes ✅

- [ ] **Google Sheets logging working** — every signal has correct entry zone, SL, TP levels

- [ ] **Dashboard auto-updating** — dashboard.html regenerated after each tracker run ✅ (now fixed)

- [ ] **Cache saving working every bot run** — confirm in bot_log.txt ("✓ Cache: WRITE successful")

- [ ] **API cost below $0.05/day** — 2-call architecture saving ~$0.0126/run at current volume

---

## ✅ Gate 4: Paper Trading Test (whale_stream_trader.py)

- [ ] **Run whale_stream_trader.py on Bybit Demo for 2 weeks**
  - This simulates real trades using live prices but demo money.
  - Verifies: order placement, TP hit detection, SL triggers, position sizing.

- [ ] **At least 20 demo trades completed** with correct entry/exit behavior

- [ ] **Demo P&L tracks within 10%** of tracker's theoretical P&L

- [ ] **No critical errors** in trader_log.txt during demo period

---

## ✅ Gate 5: Real Account Setup (Final Steps Before Live)

- [ ] **Create Bybit account** (if not already done)

- [ ] **Complete KYC verification** on Bybit

- [ ] **Generate Bybit API keys** (permissions: Read + Trade, no Withdrawal)
  - Store in whale_stream_trader.py (never commit to git)

- [ ] **Fund account with test capital** — start with minimum viable amount
  - Suggested start: $200-500 USDT
  - This limits max loss while proving the system works live

- [ ] **Set Bybit account to Spot trading only** (no futures for first phase)

---

## ✅ Gate 6: Risk Rules (Hard Rules, Never Break)

These rules apply once live trading begins:

| Rule | Value |
|------|-------|
| Max position size | 5% of account per trade |
| Max daily loss | -15% of account (stop all trading for the day) |
| Circuit breaker | Stop if last 12 trades P&L < -100% cumulative |
| Loss streak halt | Pause after 5 consecutive losses — review market |
| Max open positions | 3 at any time |
| Leverage cap | 3x real money (10x in paper/tracking only) |
| Compounding | Only compound after 30 profitable live trades |

> ⚠️ **NOTE**: The 10x leverage shown in tracker stats is THEORETICAL.
> For real money, start at 2-3x maximum until 50+ live trades are proven.

---

## 🗓️ Estimated Timeline to Live

| Phase | Duration | Goal |
|-------|----------|------|
| Current (v46.2 active) | Now → ~1 week | Bybit filter fix clears EXPIRED backlog; 100 resolved within ~7 days |
| Short WR validation | 1-2 weeks | Confirm short WR ≥ 40% with v46.2 rules (Stage 4-5 only + OVERSOLD REJECT) |
| Demo trading | 2 weeks | Run whale_stream_trader.py on Bybit Demo while accumulating real data |
| Live with micro-capital | Week 3-4 | $200-500 USDT, 2-3x leverage (after Gates 1-4 passed) |
| Scale up | After 30 live wins | Increase capital and leverage gradually |

---

## 📝 What Makes a Signal "Ready to Trade Live"

A signal is worth taking when ALL are true:
1. Confidence ≥ 88% (bot only outputs ≥ 88%)
2. Coin is listed on Bybit spot (v46.1 filter ensures this)
3. Volume > $10M/day (enriched in bot)
4. Circuit breaker is NOT active
5. No more than 2 positions already open in same direction

---

## 🎯 The Mission

> "The poor and disadvantaged are waiting for us."
>
> We trade with discipline and purpose — not greed.
> Every decision is made by data, not emotion.
> The edge is real. We protect it by following the rules.

---

*Generated by WHALE-STREAM v46.3 | Auto-updated with each milestone*
