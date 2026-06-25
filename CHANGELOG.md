# WHALE-STREAM CHANGELOG

## v46.52 — 2026-06-25 — Debrief confidence cast fix + Strategist Task Scheduler

### 2 Fixes — runtime crash prevention, Strategist now live in scheduler

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | HIGH | **`confidence` string→float cast in `whale_stream_debrief.py`.** The Debrief Agent receives `confidence` as a raw string from the tracker (e.g. `"78"`). The `build_debrief_prompt()` function formatted it with `:.0f` (float format), which raises `ValueError` on the first real debrief and silently kills the background process. Fixed by casting at read time: `confidence = float(trade.get("confidence", 0) or 0)`. Caught by post-ship audit agent before any live trade triggered it. | whale_stream_debrief.py |
| 2 | MEDIUM | **`WhaleStreamStrategist` task registered in Windows Task Scheduler.** `ADD_STRATEGIST_TASK.bat` run as Administrator — task confirmed created, status Ready, next run 2026-06-26 00:10. Full 8-agent team now fully scheduled. | Task Scheduler |

---

## v46.51 — 2026-06-25 — Post-Trade Debrief Agent + Continuous Learning Loop

### 3 Improvements — institutional memory, pattern learning, Strategist intelligence

| # | Severity | Improvement | File |
|---|----------|-------------|------|
| 1 | HIGH | **New `whale_stream_debrief.py` — Post-Trade Debrief Agent.** Called automatically after every WIN or LOSS. Passes trade data to Claude Haiku which analyses WHY the trade won or lost, grades the entry quality (A+/A/B/C/D), extracts a 15-word actionable lesson, and flags it REINFORCE/AVOID/NEUTRAL. Results written to `pattern_memory.json` with coin-specific lessons and pattern-level aggregates. Max 200 debriefs retained. Telegram summary sent to ops channel after each debrief run. | whale_stream_debrief.py (new) |
| 2 | HIGH | **Debrief Agent wired into `whale_stream_tracker.py`.** After the WIN/LOSS Telegram alert is sent for each resolved trade, the tracker adds the trade to `_newly_resolved`. After the batch Sheets update, a single `subprocess.Popen` fires the Debrief Agent in the background — non-blocking, so tracker performance is unaffected. If the debrief script doesn't exist, tracker continues normally. | whale_stream_tracker.py |
| 3 | HIGH | **Strategist now reads `pattern_memory.json` before every decision.** New `load_pattern_memory()` function reads the debrief memory file. For each signal being evaluated, if coin-specific lessons exist (e.g. "TIA LONG: [REINFORCE] Reinforce Stage 2 + negative funding"), they are injected into the Claude prompt under `=== PATTERN MEMORY ===`. Avoid-pattern and prefer-pattern lists also injected. The learning loop is now closed: trade resolves → Debrief writes lesson → Strategist reads lesson → better decision next run. | whale_stream_strategist.py |
| 4 | MEDIUM | **Telegram signal/ops channel split.** Signal posts (the per-run WHALE-STREAM signal tables) now go to `TELEGRAM_SIGNAL_CHAT_ID` — a clean, noise-free channel for signals only. Operational alerts (circuit breaker, balance, regime, debrief summaries, run stats) stay on `TELEGRAM_CHAT_ID` (ops). To enable: add `TELEGRAM_SIGNAL_CHAT_ID = "-100..."` to `local_config.py`. If not set, both channels receive the same content as before (backwards-compatible fallback). | whale_stream_bot.py |

**Learning loop:**
```
Bot (Scout) → [signals] → Strategist (reads pattern_memory) → [decisions] → Trader (executes)
                                                                                    ↓
                                              pattern_memory ← Debrief Agent ← Tracker (resolves)
```

**New team roster as of v46.51:**
| Role | Script | Schedule | Job |
|------|--------|----------|-----|
| 🔭 Scout | whale_stream_bot.py | :00 every 2h | Screen 200 coins, generate 3+3 signals |
| 🧠 Strategist | whale_stream_strategist.py | :10 every 4h | Review signals + read pattern memory |
| ⚡ Trader | whale_stream_trader.py | :20 every 4h | Execute only approved signals |
| 👁 Monitor | whale_stream_monitor.py | continuous | Track open position fills |
| 📊 Tracker | whale_stream_tracker.py | every 30 min | Resolve trades + trigger Debrief |
| 📓 Debrief | whale_stream_debrief.py | after each trade | Analyse WHY, write lesson to pattern_memory |
| 🩺 Analyzer | RUN_ANALYZE_SHORTS.bat | Thu + Sun | Weekly pattern intelligence update |
| 📢 Briefing | morning_briefing.py | 7 AM daily | Capital health + yesterday P&L |

---

## v46.50 — 2026-06-25 — Strategist Agent Added (Signal Quality Council)

### 3 Improvements — new team member, pre-trade review layer, entry quality assessment

| # | Severity | Improvement | File |
|---|----------|-------------|------|
| 1 | HIGH | **New `whale_stream_strategist.py` — Signal Quality Council.** A new team member runs at :10 (between Bot :00 and Trader :20). The Bot (Scout) finds the best setups in the market. The Strategist asks: "Should WE take THIS trade, given OUR history on this coin?" It reads the latest OPEN signals from Sheets, pulls per-coin trade history (last 60 rows), reads current portfolio state, fetches BTC 7d% for regime check, then calls Claude Haiku to evaluate each signal. Output: `strategist_decisions.json` with APPROVE / VETO / REDUCE_SIZE per signal, plus Telegram summary. | whale_stream_strategist.py (new) |
| 2 | HIGH | **Strategist veto integrated into `whale_stream_trader.py`.** Before placing any order, the Trader now reads `strategist_decisions.json`. VETO'd signals are skipped with reason logged. REDUCE_SIZE signals are traded at 50% of normal size (using per-coin `_coin_size_mult` to avoid contaminating other signals). Graceful degradation: if the file doesn't exist (Strategist didn't run), all signals proceed normally. | whale_stream_trader.py |
| 3 | MEDIUM | **`ADD_STRATEGIST_TASK.bat` — schedules Strategist in Task Scheduler.** Run as Administrator to add `WhaleStreamStrategist` task at :10 past every 4-hour mark (00:10, 04:10, 08:10, 12:10, 16:10, 20:10 BKK). Team schedule is now: Bot :00 → Strategist :10 → Trader :20. | ADD_STRATEGIST_TASK.bat (new) |

**Strategist auto-veto rules (encoded in its system prompt):**
- Last trade on this coin+direction = LOSS → VETO (momentum broken)
- Pattern = RS failure / dead cat bounce / meme → VETO (0% WR in live data)
- SHORT at 90-92% confidence without Stage 4-5 distribution → VETO (confidence paradox)
- LONG in bear market (BTC 7d < -8%) with confidence < 97% → VETO
- SHORT in bull market (BTC 7d > +8%) with confidence < 97% → VETO

**Full team roster as of v46.50:**
| Role | Script | Schedule | Job |
|------|--------|----------|-----|
| 🔭 Scout | whale_stream_bot.py | :00 every 2h | Screen 200 coins, generate 3+3 signals |
| 🧠 Strategist | whale_stream_strategist.py | :10 every 4h | Review signal quality, APPROVE/VETO/REDUCE |
| ⚡ Trader | whale_stream_trader.py | :20 every 4h | Execute only approved signals |
| 👁 Monitor | whale_stream_monitor.py | continuous | Track open position fills |
| 📊 Tracker | whale_stream_tracker.py | every 30 min | Resolve completed trades |
| 🩺 Analyzer | RUN_ANALYZE_SHORTS.bat | Thu + Sun | Pattern intelligence update |
| 📢 Briefing | morning_briefing.py | 7 AM daily | Capital health + yesterday P&L |

---

## v46.49 — 2026-06-25 — Strategy Intelligence + Bear Market Bias Fix + CB Cleared

### 5 Improvements — market regime bias, pattern intelligence from 141 live trades, circuit breaker cleared

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | CRITICAL | **Circuit breaker manually cleared.** `paused.flag` deleted. CB triggered June 24 22:20 after 3 consecutive losses during a bear market swing. All 3 current open positions (JTO SHORT, TIA LONG, AAVE LONG) are profitable; Gate 4 breach mode (0.40x size, max 4 positions) provides risk containment going forward. | paused.flag |
| 2 | HIGH | **BEAR MARKET LONG VETO added to prompt.** Mirror rule of the existing BULL MARKET SHORT VETO. If BTC 7d% < -8% OR market regime = Bear Expansion, skip ALL LONGs unless confidence ≥ 97% with confirmed accumulation pattern. This directly addresses the directional bias problem: bot was entering LONGs into a falling bear market. Rule prevents "fighting the trend" losses. | whale_stream_bot.py |
| 3 | HIGH | **SHORT coin history mirror rule added.** "Do not repeat a SHORT on a coin whose last trade was a LOSS at SL" — symmetric to the existing LONG rule at line 513. Previously LONGs had this protection but SHORTs did not. | whale_stream_bot.py |
| 4 | HIGH | **Pattern intelligence block added to prompt.** Inserted PATTERN INTELLIGENCE section derived from 141 resolved live trades. Key learnings encoded: (a) Stage 5 distribution patterns = 85-100% SHORT WR, prefer these. (b) RS failure pattern = 0% SHORT WR, avoid. (c) SHORT 90-92% confidence band paradox: only 36.4% WR — avoid this band without strong distribution confirmation. (d) Stage 2 expansion = best LONG pattern (100% WR). (e) AERO (100%/8 trades) and TIA (100%/4 trades) are star LONG coins; ZRO/HYPE/COMP blocked. | whale_stream_bot.py |
| 5 | HIGH | **Gate 4 SHORT block removed.** Previous Gate 4 breach mode was "LONG only, max 4 positions." Changed to "BOTH directions, max 4 positions, 0.40x size." Rationale: SHORT WR is 68.7% overall (vs LONG 52.7%), and in a bear market SHORTs are the primary profit driver. Blocking SHORTs in Gate 4 = blocking our best trades exactly when we need recovery. | whale_stream_trader.py |

---

## v46.48 — 2026-06-25 — Critical Filter + Stability Fixes

### 5 Fixes — top-3 filter scope, Gate 4 alert sentinel, bat message, milestone state, tracker encoding

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | CRITICAL | **Top-3 filter now applied to Telegram + Sheets.** Previously the top-3 filter only ran inside `log_to_google_sheets()`, meaning Telegram showed ALL signals (8 LONG + 5 SHORT) while only 3+3 went to Sheets. Fixed by applying the filter to `signal_data` in `main()` BEFORE `build_telegram_message()` is called. Now Telegram, Sheets, and the trader all see only top 3 LONG + top 3 SHORT per run. | whale_stream_bot.py |
| 2 | HIGH | **Gate 4 Telegram alert now fires once (not every run).** The 🔴 GATE 4 BREACH MODE alert was comparing `_prev_mult != 0.40` which was always True, so it sent a Telegram alert every 4h run while breach mode was active. Fixed with a `gate4_breach.flag` sentinel file — alert fires once on entry, cleared when balance recovers above $425. | whale_stream_trader.py |
| 3 | LOW | **CLEAR_PAUSE.bat stale "2-hour cycle" message fixed.** Updated bat file to say "4-hour cycle" instead of "2-hour cycle". | CLEAR_PAUSE.bat |
| 4 | MEDIUM | **milestone_state.json premature 150 milestone removed.** Removed 150 from the fired list. The 150-trade milestone fired when actual count was 141. Will re-fire correctly when genuinely reaching 150 resolved trades. | milestone_state.json |
| 5 | CRITICAL | **Tracker UnicodeEncodeError cp1252 crash loop fixed.** Added UTF-8 reconfiguration at top of `whale_stream_tracker.py` `__main__` block. Tracker was crashing on every run with cp1252 codec failure when printing emoji characters, causing WIN/LOSS results not to be written to Sheets. | whale_stream_tracker.py |

---

## v46.47 — 2026-06-24 (Top-3 Signal Filter — Best-of-Best Only)

### 2 Improvements — signal quality over quantity + LONG confidence floor raised to 90%

| # | Severity | Improvement | File |
|---|----------|-------------|------|
| 1 | HIGH | **Top-3 LONG + Top-3 SHORT filter added.** After both Claude batches run and all raw signals are combined, a new filter sorts each direction by confidence (descending) and keeps only the top 3 per side. Lower-confidence signals are dropped before any order is placed or Sheets row is written. A `🎯 TOP-3 FILTER` log line shows how many were dropped each run. Goal: enter only highest-conviction trades to maximize win rate and P&L per trade — critical for capital preservation and go-live confidence. Header banner updated from "8 signals (5 LONG + 3 SHORT)" to "top 3 LONG + top 3 SHORT". | whale_stream_bot.py |
| 2 | HIGH | **LONG minimum confidence raised from 88% to 90%.** Updated `CONFIDENCE FILTER` in prompt: `Reject < 88%` → `Reject < 90%`. TIER 2 floor now starts at 90% (was 88%). Combined with the Top-3 filter, this ensures only the highest-conviction LONG setups are entered. Previous step: v46.45 raised 85% → 88%; this step raises 88% → 90%. SHORT minimum unchanged at 95%. | whale_stream_bot.py |

---

## v46.46 — 2026-06-24 (2h Bot Frequency + Daily P&L Summary + Thursday Analysis)

### 3 Improvements — scheduling tightened, daily accountability added

| # | Severity | Improvement | File |
|---|----------|-------------|------|
| 1 | HIGH | **Bot frequency changed from 4h to 2h.** Created `CHANGE_TO_2H.bat` (deletes and re-creates both Task Scheduler tasks at /MO 2). Updated `ADD_BOT_TASK.bat` to default to 2h going forward (`/MO 2`, schedule comments updated: 06:00/08:00/10:00/... instead of 06:00/10:00/14:00/...). `ADD_TRADER_TASK.bat` was already on /MO 2; updated echo comment "valid for 4 hours" → "2 hours". | CHANGE_TO_2H.bat, ADD_BOT_TASK.bat, ADD_TRADER_TASK.bat |
| 2 | MEDIUM | **Yesterday's P&L section in morning briefing.** Added `parse_yesterday_pnl()` that reads Google Sheets (same gspread/service account auth as tracker) and finds rows where `resolved_at` starts with yesterday's BKK date. Reports resolved count, W/L, WR%, and net P&L sum in Telegram message. Falls back gracefully if Sheets unavailable or no trades resolved. | morning_briefing.py |
| 3 | LOW | **Thursday added as second analyze_shorts.py auto-run day.** Morning briefing now triggers analyze_shorts.py on Thursday (weekday 3) and Sunday (weekday 6) so SHORT recovery detection fires mid-week. Uses subprocess.run with 120s timeout, matching the tracker pattern. | morning_briefing.py |

---

## v46.45 — 2026-06-24 (LONG Avoid List + Gate 4 Recovery Alert + JSON Fix + WLD Ban + 88% LONG Min + Wider Zones)

### 6 Fixes — LONG coin filtering, Gate 4 crossing notification, JSON parse robustness, signal quality improvements

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | HIGH | **LONG_COIN_AVOID_LIST hard block.** Added `LONG_COIN_AVOID_LIST = ["COMP", "HYPE", "ZRO"]` constant near `SHORT_RECOVERY_COINS`. Before placing any LONG order, the trader now checks this list and skips with log `⏭ Skipping {coin} LONG — on LONG avoid list (poor historical WR)`. These three coins have poor historical LONG win rates and were generating losing trades. | whale_stream_trader.py |
| 2 | HIGH | **Gate 4 recovery Telegram alert.** `write_balance_file()` now reads the previous balance from `bybit_balance.json` before overwriting it. If the old balance was < $425 and the new balance is >= $425, fires a 🟢 GATE 4 CLEARED Telegram alert prompting a review of the July 1 go-live decision. Crossing detection is one-shot per crossing event (old < 425, new >= 425). | whale_stream_trader.py |
| 3 | HIGH | **JSON parse "Extra data" error fixed.** Added `_extract_first_json_object()` brace-depth scanner. When Claude emits two concatenated JSON objects, the old `rfind('}')` captured the wrong endpoint causing `json.loads` to raise "Extra data: line 2 column 1 (char N)". New logic walks character-by-character tracking brace depth and string escapes, returning ONLY the first complete `{...}` object and ignoring everything after it. Applied in the delimiter path, the code-fence fallback, and the final brace-search fallback. | whale_stream_bot.py |
| 4 | MEDIUM | **WLD hard ban confirmed in prompt SHORT blocklist.** WLD is in `SHORT_COIN_BLOCKLIST` (code-level enforcement) and explicitly in the prompt's `SHORT SIGNAL BLOCKLIST` section with entry: `• WLD — 0% SHORT WR across 2 trades (avg loss: −50%) BANNED from SHORTs`. Code-level blocklist rejects any WLD SHORT signal before it reaches Google Sheets. | whale_stream_bot.py |
| 5 | MEDIUM | **Raised LONG minimum confidence to 88% (from 85%).** Updated `CONFIDENCE FILTER` in prompt: `Reject < 85%` → `Reject < 88%`. TIER 3 band `85–87%` removed; TIER 2 now starts at 88% as the minimum qualifying setup. SHORT minimum unchanged at 95%. | whale_stream_bot.py |
| 6 | HIGH | **Wider LONG entry zones to reduce 54% expiry rate.** Updated `ENTRY ZONE WIDTH RULE`: entry zone TOP may now be set at current price (not just 1–3% below) when BTC 24h momentum is positive (>+1%) or funding rate is strongly negative (<−0.03%). Updated expiry rate stat from 67% → 54% (current measured rate). | whale_stream_bot.py |

---

## v46.44 — 2026-06-24 (Gate 4 Breach Mode + Balance Staleness Fix + Entry Price Rules)

### 3 Improvements — parallel agent delivery, capital protection layer 2

| # | Severity | Improvement | File |
|---|----------|-------------|------|
| 1 | CRITICAL | **Balance file written even when circuit breaker is paused.** Moved Bybit balance fetch + `write_balance_file()` to execute BEFORE the `paused.flag` guard. Previously, `bybit_balance.json` went stale for the entire duration of any circuit breaker pause — the June 23 circuit breaker ran for 14+ hours and the morning briefing showed $434 (stale) instead of $405.35 (real). Now the balance file is always current. | whale_stream_trader.py |
| 2 | HIGH | **Gate 4 breach capital preservation mode.** When drawdown exceeds 15%, overrides size multiplier to 0.40 (below the normal 0.60 floor), blocks ALL SHORT signals, caps positions at 4, and fires a 🔴 GATE 4 BREACH MODE Telegram alert. Activates automatically — no human intervention needed. | whale_stream_trader.py |
| 3 | HIGH | **Entry price deviation rules in bot prompt.** Added explicit Bybit limit order constraints to signal generation: LONGs 0.5–2% below mark, SHORTs 0.5–2% above mark, hard reject if >4% deviation. Directly targets the repeated retCode=10001 "Price invalid" failures (H SHORT at 7.6% from mark, etc.) that have been wasting runs for days. | whale_stream_bot.py |

---

## v46.43 — 2026-06-24 (Morning Briefing Capital Health Alerts)

### 1 Critical Fix — morning briefing was blind to circuit breaker and Gate 4 breach

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | CRITICAL | **Capital health section in morning_briefing.py.** Added: drawdown % calculation, Gate 4 status line (OK/Warning/Breach), circuit breaker detection (`paused.flag`), stale balance warning when trader is paused, system flags section (repair/conservative/paused), and trader status now says "🚨 PAUSED" instead of a false "✅ Running". The June 23 circuit breaker fired at 18:20 BKK and the 7am June 24 briefing would have shown nothing — this fixes that permanently. | morning_briefing.py |

---

## v46.42 — 2026-06-24 (Capital Protection + SHORT Conservative Phase)

### 3 Improvements Shipped — direct response to $66 drawdown root-cause analysis

| # | Severity | Improvement | File |
|---|----------|-------------|------|
| 1 | HIGH | **Max 8 concurrent open positions cap.** Before placing any order, reads `bybit_balance.json` → `open_positions`. If ≥ 8, skips the entire run and fires Telegram alert. Prevents multiple SL hits simultaneously wiping the Gate 4 buffer. At current 11 open positions, this activates immediately. | whale_stream_trader.py |
| 2 | HIGH | **Drawdown-based position size scaling.** Computes live drawdown from `bybit_balance.json`. Full size if drawdown < 8%; 75% size if 8–12%; 60% size if ≥ 12%. At current 13.2% drawdown, all new orders trade at 60% size. Scales back up automatically as balance recovers. Per-order Telegram shows the scaling notice. | whale_stream_trader.py |
| 3 | MEDIUM | **SHORT Conservative Phase (soft landing after REPAIR MODE).** When repair mode auto-exits, a `short_conservative.flag` is created. While active: bot prompt restricts to max 1 SHORT/run, ≥93% confidence, H/FF only. Tracker counts H/FF SHORTs resolved — exits conservative phase after 10 trades with ≥50% WR (extends by 10 more if WR < 50%). Dashboard shows blue 🔵 banner. Full lifecycle: flag creation (tracker) → prompt injection (bot) → auto-exit (tracker). | whale_stream_tracker.py, whale_stream_bot.py |

---

## v46.41 — 2026-06-23 (Complete CHZ Cleanup — second-pass audit)

### 6 Fixes Shipped (all CHZ residue from v46.40 partial cleanup)

| # | File | Fix |
|---|------|-----|
| 1 | whale_stream_bot.py | Header banner `v45.0` → `v46.41`; version strings in prompt, Telegram, and startup banner bumped to v46.41 |
| 2 | whale_stream_bot.py | `_rc_coins` dict removed CHZ entry (`{"H": (0,0), "FF": (0,0), "CHZ": (0,0)}` → `{"H": (0,0), "FF": (0,0)}`); comment updated |
| 3 | whale_stream_bot.py | BTC momentum gate strings corrected: `≥91%` → `≥95% REPAIR MODE` in 4 places + fallback string |
| 4 | whale_stream_bot.py | Example JSON rank-2 SHORT was CHZ (malformed coin) — replaced with H using realistic price levels |
| 5 | whale_stream_trader.py | Comment `SHORT_RECOVERY_COINS (H, FF, CHZ)` → `(H, FF)`; Telegram message `"Only H/FF/CHZ allowed."` → `"Only H/FF allowed."` |
| 6 | whale_stream_tracker.py | `_rc_set`, `_rc_coins` removed CHZ; removed `rc_chz_w/rc_chz_l` variable; dashboard HTML header + CHZ span removed; Gate 3 sub text `H/FF/CHZ` → `H/FF`; Telegram repair-mode auto-exit message `H/FF/CHZ` → `H/FF`; recovery loop `["H","FF","CHZ"]` → `["H","FF"]`; no-trades-yet message updated |

---

## v46.40 — 2026-06-23 (Security Hardening + Sonnet Restored + CHZ Fix)

### 3 Fixes Shipped

| # | Severity | Fix | Files |
|---|----------|-----|-------|
| 1 | HIGH | **Bybit API keys moved to local_config.py.** `BYBIT_API_KEY` and `BYBIT_API_SECRET` were hardcoded in 4 files. Moved to `local_config.py` (gitignored) with `try/except` env var fallback. Critical before July 1 live key swap — live keys must never appear in git history. Updated `local_config.py.example` with Bybit key placeholders. | whale_stream_trader.py, whale_stream_tracker.py, whale_stream_monitor.py, check_bybit_orphans.py, local_config.py, local_config.py.example |
| 2 | MEDIUM | **Switched back to claude-sonnet-4-6.** Haiku was activated in v46.39 for cost savings ($1.62→$0.35/day). User confirmed cost is affordable — reverted to Sonnet for best signal quality. Haiku kept as documented fallback option in comments. | whale_stream_bot.py |
| 3 | LOW | **CHZ consistency fix.** CHZ was in `MALFORMED_COIN_BLOCKLIST` (bot.py) but still listed as a preferred SHORT recovery coin in both the prompt and `SHORT_RECOVERY_COINS` (trader.py). Removed CHZ from `SHORT_RECOVERY_COINS`. Added explicit CHZ ban to the `SHORT SIGNAL BLOCKLIST` section of the prompt. Updated REPAIR MODE preferred coins: `H, FF, CHZ` → `H, FF`. | whale_stream_bot.py, whale_stream_trader.py |

---

## v46.39 — 2026-06-23 (Haiku Model Switch — cost optimization)

Switched `CLAUDE_MODEL` from `claude-sonnet-4-6` to `claude-haiku-4-5-20251001` (~75% cost reduction). Reverted in v46.40 after user confirmed cost is affordable.

---

## v46.38 — 2026-06-23 (Macro Event Guard + Token Unlock Calendar)

### 2 Features Shipped

| # | Severity | Feature | File |
|---|----------|---------|------|
| 1 | HIGH | **Macro Event Guard.** Added `MACRO_EVENTS_2026` hardcoded calendar (FOMC + CPI dates from federalreserve.gov + bls.gov). Added `check_macro_event_risk()` that checks current UTC time against all events. Injects into graveyard prompt: 🔴 HIGH if event <4h (confidence ≥93% required, default STAY OUT), 🟡 MEDIUM if <12h (prefer SHORTs, avoid LONG breakouts), 🔴 POST if 0–2h after event (market still settling). No new API key needed — fully hardcoded. | whale_stream_bot.py |
| 2 | MEDIUM | **Token Unlock Calendar.** Added `_UNLOCK_SLUG_MAP` (23 coins) and `check_token_unlock_risk()` that calls DefiLlama emission API per coin. Warns when ≥3% of circulating supply unlocks in next 48h with `⚠️ TOKEN UNLOCK — COIN: X.X% ... AVOID LONG`. Fails silently (per-coin `try/except` + outer `try/except`) — never blocks the trading cycle. Free API, no key needed. | whale_stream_bot.py |

Version bumped to v46.38 in: `WHALE_STREAM_PROMPT`, Telegram header, startup banner.

Accurate FOMC + CPI dates (sources verified 2026-06-23):
- FOMC remaining 2026: Jul 29, Sep 16, Oct 28, Dec 9
- CPI remaining 2026: Jul 14, Aug 12, Sep 11, Oct 14, Nov 10, Dec 10

---

## v46.37 — 2026-06-23 (LONG Coin Blocklist: ZRO + HYPE)

### 1 Fix Shipped

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | MEDIUM | **Block LONG dead-weight coins ZRO and HYPE.** Post P&L-repair analysis (2026-06-23) confirmed ZRO: 0W/2L LONG WR 0%, avg P&L −59.5% and HYPE: 0W/2L LONG WR 0%, avg P&L −54.3%. Both rated POOR. Added to `LONG_COIN_BLOCKLIST` in bot.py (code-enforced rejection, same as SHORT permanent ban). Also updated the graveyard prompt to (a) always show the static LONG ban list to the AI, (b) lowered the dynamic LONG avoid list threshold from 3 to 2 losses to match the blocklist, (c) exclude already-banned coins from the dynamic list to avoid duplication. | whale_stream_bot.py |

**Post-repair gate status (2026-06-23 07:29 BKK):**
- Gate 1: ⬜ 100/150 (67%) — need 50 more by July 1
- Gate 2: ✅ PASS — LONG avg P&L = +51.0% per trade (corrected)
- Gate 3: ✅ PASS — SHORT WR = 59.2% (29W/20L)
- System: ✅ FULL MODE — all signals active

**Also completed this session:**
- Git repo initialized locally (all 59 files committed at v46.36)
- Historical P&L repair: 105 corrupted values fixed in Google Sheets via `repair_pnl_history.py`

---

## v46.36 — 2026-06-23 (3-Agent Sprint: SL Validation + P&L Fix + TP Upgrade)

### 3 Fixes Shipped

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | HIGH | **Bot-side malformed SL validation.** Bot was writing signals with SL on wrong side of entry to Google Sheets (CHZ SHORT: SL ≤ entry; CHZ/GRT/FF LONG: SL ≥ entry). Tracker caught these and skipped them but they STILL occupied sheet rows and expired as wasted slots after 72h. Fix: (a) Added `MALFORMED_COIN_BLOCKLIST = {"CHZ"}` — CHZ skipped entirely both directions, (b) Added full SL/TP direction + minimum distance validation block in `log_to_google_sheets()` BEFORE any row is written — malformed signals now `continue` without touching the sheet at all (not even as INVALID), (c) Added `CRITICAL SL VALIDATION` rule block to AI prompt reinforcing that SL for LONG must be strictly below entry and SHORT must be strictly above, with explicit note about low-price coins not using rounded SL numbers. | whale_stream_bot.py |
| 2 | CRITICAL | **P&L Google Sheets corruption fix.** Root cause: when tracker wrote P&L as `"+218.75%"` with `value_input_option="USER_ENTERED"`, Google Sheets interprets the `%` as a percentage operator and stores `2.1875` (÷100) internally. On re-read via `get_all_values()`, cells with no explicit format return the raw decimal `"2.1875"` instead of `"218.75%"`. This caused: (1) any P&L < 150% stored as a decimal < 1.5 — excluded by `_is_real_pnl()` threshold, making most real trades invisible to stats; (2) P&L ≥ 150% included but at 1/100th actual value (e.g., 218.75% counted as 2.19%), causing wildly wrong Total P&L, Avg Win, Profit Factor, and Expectancy. Fix: appended `" [T]"` suffix to all tracker P&L writes — `f"{pnl:+.2f}% [T]"` and `f"{_blended:+.2f}% [T]"`. Google Sheets treats these as text (can't interpret due to suffix), stored correctly. `_parse_pnl()` already handles this via regex that ignores suffixes. Note: historical trades (before this fix) retain corrupted values in the sheet; a one-time correction script is a future task. | whale_stream_tracker.py |
| 3 | MEDIUM | **TP_HIT upgrade via Bybit avgExitPrice.** TP distribution was 61 TP1 / 1 TP2 / 1 TP3 because: tracker marks WIN when 30-min snapshot sees price past TP1, but Bybit's TP2 reduce-only order might fill AFTER price retraces. `check_result()` already checks TP2 before TP1 in priority, so a direct TP2 hit is captured correctly. The gap is when TP1 hits in one snapshot and the Bybit TP2 order fills in a later (unseen) interval. Fix: in the Bybit closed P&L write-back block, when a row is confirmed matched and `COL_TP_HIT == "TP1"`, compare Bybit's `avgExitPrice` against TP2/TP3 levels. If avgExitPrice confirms TP2/TP3 was actually filled (±0.5% tolerance), upgrade `COL_TP_HIT` to `"TP1+TP2"` or `"TP1+TP3"` and fire a Telegram alert. | whale_stream_tracker.py |

**Note on historical P&L stats:** Win Rate (60%) and streak data are unaffected (count-based, not P&L). All P&L-derived stats (Total P&L, Avg Win, Profit Factor, Expectancy) computed from the sheet before this fix are unreliable due to the percentage corruption. These will self-correct as new trades resolve with the `[T]` suffix. A bulk historical repair script is a future task.

---

## v46.35 — 2026-06-23 (Circuit Breaker False Alarm Fix)

### 2 Fixes Shipped

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | HIGH | **Root cause — missing `resolved_at` in in-memory dict.** When a trade resolved during the current tracker run, `all_parsed[-1].update()` was NOT setting `"resolved_at": now_str`. The circuit breaker sorts by `resolved_at` and slices `[-12:]`, so trades resolved in the current run had `resolved_at=""` → sorted to position 0 (earliest) → the `[-12:]` window picked OLD trades (including losses from prior periods) instead of actual recent wins. Fixed by adding `"resolved_at": now_str` to the in-memory dict update at line 1594. | whale_stream_tracker.py |
| 2 | MEDIUM | **Win-streak override guard.** Both `print_stats()` and `write_dashboard_html()` now suppress the circuit breaker warning/flag when `cur_streak_count >= 5 and last_status == "WIN"`. This prevents any residual false alarms from stale sheet data during confirmed win streaks. In `write_dashboard_html()`, the streak calculation was moved above the circuit breaker check (was below) so the variable is available when needed. | whale_stream_tracker.py |

---

## v46.34 — 2026-06-22 (retCode=10001 Price Clamp Fix)

### 1 Fix Shipped (Task #164)

| # | Severity | Fix | File |
|---|----------|-----|------|
| 11 | HIGH | Entry price clamp to mark ± 2.5%. Previous guard was 8% (entry too far from mark → skip). Bybit's actual dynamic price band is ~3%, so entries within 3–8% of mark were being submitted and silently rejected with `retCode=10001 "Price invalid"`. Affected OP, TRX, SEI, XLM, and critically H SHORT + FF SHORT (the two Gate 3 recovery coins). Fix: new constant `BYBIT_PRICE_CLAMP_PCT = 2.5`. After the 8% guard passes, entry is clamped to `[mark × 0.975, mark × 1.025]`. SL is re-validated after clamping (if clamp broke the SL direction relationship, trade is skipped). Log line emitted: `⚠ Entry price {x} is {n}% from mark — clamping to {y}`. Estimated recovery: 7–14 additional orders placed per week. | whale_stream_trader.py |

---

## v46.33 — 2026-06-22 (Near-Real-Time Monitor + ADD_MONITOR_TASK.bat)

### 1 Feature Shipped (Task #156)

| # | Task | Files Created |
|---|------|---------------|
| 156 | `whale_stream_monitor.py` — near-real-time Bybit fill detector. Runs every 2 minutes via Task Scheduler. On each run: fetches all open positions, compares to `monitor_state.json` (position sizes at last check), and detects: (1) **Partial close** (~50% size reduction → TP1 hit): fires Telegram "TP1 PARTIAL CLOSE" alert and immediately calls `/v5/position/trading-stop` to move SL to `avgPrice` (breakeven), so the trade is risk-free within 2 min of TP1 filling. (2) **Full close** (position disappeared): fires Telegram "POSITION CLOSED" alert noting tracker will mark WIN/LOSS at next 30-min run. New positions are silently added to state on first detection. All events logged to `monitor_log.txt`. `ADD_MONITOR_TASK.bat` + `run_monitor.bat` created to register the 2-min Task Scheduler job. | whale_stream_monitor.py, ADD_MONITOR_TASK.bat, run_monitor.bat |

---

## v46.32 — 2026-06-22 (Audit Fix Sprint — 10 Pre-Live Bugs Resolved)

### 10 Fixes Shipped (Task #158)

| # | Severity | Fix | File |
|---|----------|-----|------|
| 1 | CRITICAL | `PAUSED_FILE` renamed from `"trader_paused.flag"` → `"paused.flag"` — was silently split from tracker's PAUSED_FILE, meaning Gate 5 circuit breaker never actually paused the trader | whale_stream_trader.py |
| 2 | HIGH | `slTriggerBy` changed from `"LastPrice"` → `"MarkPrice"` — prevents wick-stops on thin candles that never reach mark price | whale_stream_trader.py |
| 3 | HIGH | `tpTriggerBy` changed from `"LastPrice"` → `"MarkPrice"` — aligns TP triggers with standard practice | whale_stream_trader.py |
| 4 | HIGH | Fallback single-close (qty too small to split) now targets `tp1` instead of `bybit_tp` (TP2/TP3) — ensures profit lock even on smallest positions | whale_stream_trader.py |
| 5 | HIGH | Risk cap now uses `len(already_active)` (positions + pending entry orders) instead of `n_positions` (open positions only) — no longer underestimates deployed capital | whale_stream_trader.py |
| 6 | HIGH | Circuit breaker `check_circuit_breaker()` now filters rows by `COL_BYBIT_ID.strip()` — only counts bot-placed trades, not manual rows that pollute the streak count. Row padding extended to 18 to reach col 17. | whale_stream_trader.py |
| 7 | HIGH | `_is_real_pnl()` threshold lowered from `abs(p) >= 5` → `abs(p) >= 1.5` — was excluding valid losses when SL was <0.5% from entry at 10× leverage | whale_stream_tracker.py |
| 8 | MEDIUM | Bybit closed P&L write-back now adds `avgEntryPrice` within ±3% guard — prevents wrong P&L match when same coin is traded twice within 6h | whale_stream_tracker.py |
| 9 | HIGH | Signal Graveyard fetch failure in `fetch_signal_graveyard()` now sends a Telegram warning alert instead of silently returning 50% WR | whale_stream_bot.py |
| 10 | LOW | Telegram credentials moved from inside `main()` to module-level constants in `analyze_shorts.py` | analyze_shorts.py |

---

## v46.31 — 2026-06-22 (SL-to-Breakeven After TP1)

### 1 Feature Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 155 | SL-to-breakeven after TP1 partial-close. Every trader run now calls `get_open_positions_full()` to fetch live Bybit positions, then checks the sheet for rows where `STATUS=WIN` and `TP_HIT=TP1` (TP1 confirmed by tracker). For any matching open position whose stop loss is still below entry (LONG) or above entry (SHORT), calls `/v5/position/trading-stop` to move the SL to the Bybit `avgPrice` (actual fill entry = breakeven). Prices are tick-rounded via `get_instrument_info()` + `round_price()` + `fmt_price()` for Bybit compatibility. Fires a "🛡 SL MOVED TO BREAKEVEN" Telegram alert showing old vs new SL. Already-tightened positions (SL ≥ entry for LONG) are logged and skipped. Wraps in try/except so any failure is non-fatal. New helper function `get_open_positions_full()` added alongside `get_open_positions()`. | whale_stream_trader.py |

---

## v46.30 — 2026-06-22 (Gate 1 Milestone Telegram Bursts)

### 1 Feature Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 154 | Gate 1 milestone Telegram bursts. When the total resolved-trade count first crosses 50, 75, 100, 125, or 150, the tracker fires a dedicated celebration message to the Whale-Stream Telegram group showing the milestone reached, overall WR, LONG WR, and average P&L (real trades only). The 150-trade burst signals "Gate 1 complete — real capital assessment window is now open." Each milestone fires exactly once; state persisted in `milestone_state.json` so restarts and re-runs don't duplicate messages. | whale_stream_tracker.py |

---

## v46.29 — 2026-06-22 (TIER Badge + Actual vs Estimated P&L Audit)

### 2 Features Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 152 | TIER badge in Telegram order alert. Order alert now shows `🏆 TIER 1 ELITE` (92%+), `✅ TIER 2` (88–91%), or `🟡 TIER 3` (85–87%) after the direction label. Previously only TIER 1 had a badge (`🌟TIER 1`); TIER 2 and TIER 3 were silent. Console `tier_display` now also shows full TIER label. Makes it immediately obvious which tier of calibration system is firing on each trade. | whale_stream_trader.py |
| 153 | Actual vs estimated P&L comparison in `analyze_shorts.py`. New section "ACTUAL vs ESTIMATED P&L (Bybit write-back v46.27+)" inserted after monthly WR trend. Splits resolved LONGs into Bybit-actual (`[B]` suffix) vs tracker-estimated (no `[B]`). Shows coverage %, actual WIN/LOSS avg P&L, estimated avg vs actual avg, and a gap verdict: whether fills beat estimates (upside bias), lag them (slippage/fees), or match. P&L parser in `analyze_shorts.py` updated to use regex extraction so `[B]` suffix no longer produces `None` for all write-back values. `is_bybit` flag added to each `resolved` record. | analyze_shorts.py |

---

## v46.28 — 2026-06-22 (TP2/TP3 Pursuit Completion Tracking)

### 1 Feature Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 151 | TP2/TP3 pursuit completion check in tracker. For every WIN row where `TP_HIT == "TP1"` AND a Bybit order ID exists AND the row was resolved within the last 72h: checks current price against TP2/TP3. If current price confirms the Bybit limit order filled (≥TP2 for LONG, ≤TP2 for SHORT), upgrades `COL_TP_HIT` to `"TP1+TP2"` or `"TP1+TP3"` and rewrites `COL_PNL` with the blended 50/50 P&L (avg of TP1 P&L + TP2 P&L). Updates are batched into the existing single sheet write. Fires a "🎯 PARTIAL CLOSE COMPLETE" Telegram alert showing which TP was reached, the exit price, and blended P&L. Uses already-loaded `_bybit_cache` prices — zero additional API calls. | whale_stream_tracker.py |

---

## v46.27 — 2026-06-22 (Bybit Closed P&L Write-Back + Stale Orders + Monthly WR Trend)

### 3 Features Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 148 | Stale Bybit entry order detector. `get_stale_entry_orders()` queries `/v5/order/realtime`, filters out `reduceOnly=True` orders (partial-close orders are expected to stay open), and returns entry orders >72h old with no matching OPEN signal in the sheet. If any are found, a Telegram alert fires listing the stale order IDs and symbols. Guards against orphaned entry orders that didn't get logged or weren't caught by the orphan checker. | whale_stream_trader.py |
| 149 | Month-by-month LONG WR trend in `analyze_shorts.py`. New section inserted before "LONG WR by coin" groups all resolved LONGs by `YYYY-MM`, shows per-month trade count, wins, WR%, avg P&L, and a trend arrow (↑/→/↓ vs prior month). Trajectory summary compares first-vs-last month WR delta: >+5pp = improving, <-5pp = declining, else stable. Gives a clear picture of whether LONG performance is getting better or worse over time. | analyze_shorts.py |
| 150 | Bybit closed P&L write-back to Google Sheets. Each tracker run now fetches `/v5/position/closed-pnl` (up to 200 records) and matches against resolved WIN/LOSS rows by symbol + resolved_at timestamp proximity (±6h window). Matched rows get their COL_PNL overwritten with actual realised P&L formatted as `+XX.XX% [B]` — replacing the tracker's estimated P&L (which assumed TP price as fill). `_parse_pnl()` updated to use regex extraction so the `[B]` suffix doesn't break stats or dashboard. Auth constants + `bybit_request_auth()` + `fetch_bybit_closed_pnl()` added to tracker. `COL_BYBIT_ID = 17` added to tracker column constants. Already-written rows (containing `[B]`) are skipped to avoid repeated re-writes. | whale_stream_tracker.py |

---

## v46.26 — 2026-06-22 (Orphan Window + TP Distribution + TIER 1 TP3 Requirement)

### 3 Fixes/Features Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 145 | Extended orphan checker TYPE C window from 24h → 72h. With partial closes now active (50%@TP1 + 50%@TP2/TP3), the Bybit TP2/TP3 order can legally remain open 2–3 days after the tracker resolves WIN/TP1. The previous 24h window would flip these back to TYPE A (CRITICAL) false alarms on day 2. 72h matches the tracker's own 72h expiry window, giving full coverage. | check_bybit_orphans.py |
| 146 | TP hit distribution in `analyze_shorts.py` now shows per-TP avg P&L alongside hit counts. Each TP level row includes avg P&L for trades that resolved at that level. Added "TP2+ vs TP1 uplift" line showing the avg P&L advantage of riding to a higher TP. TIER 1 target note on TP3/TP4 rows. Header updated to note partial close strategy. SHORT TP distribution gets the same per-TP P&L treatment. | analyze_shorts.py |
| 147 | Bot prompt: TIER 1 signals (92%+) MUST now include a TP3 value. Without TP3, the auto-trader cannot use TP3 targeting and the 50% remainder gets no close order. New rule added to CONFIDENCE CALIBRATION: "If you cannot identify a credible TP3, downgrade to TIER 2 rather than omit it." Ensures the full TP3 → partial-close pipeline actually fires on TIER 1 trades. | whale_stream_bot.py |

---

## v46.25 — 2026-06-22 (Monday Gate Snapshot + Partial Close at TP1)

### 2 Features Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 143 | Monday Gate 1 progress snapshot Telegram. Every Monday the tracker fires a dedicated "📅 MONDAY GATE SNAPSHOT" Telegram showing: Gate 1 status (WR vs 60% target, trades logged, wins needed), Gate 2 status (all-time LONG WR vs 58%), and total resolved LONGs. Mirrors the existing Sunday weekly summary block (`weekday() == 0`). Computed fresh from `all_parsed` so it's always current. | whale_stream_tracker.py |
| 144 | Partial close at TP1 — 50% profit lock-in with remainder riding to TP2/TP3. When a trade targets above TP1 (TP2 or TP3), the entry order is placed WITHOUT a built-in takeProfit. Immediately after, `place_partial_closes()` places two reduce-only limit orders: 50% of qty at TP1 (guaranteed lock-in) and 50% at the higher target. If the position is too small to split, a single fallback close order is placed at the higher TP. `place_order()` updated to accept `tp_price=None` for SL-only entries. Telegram order alert shows the partial split detail. | whale_stream_trader.py |

---

## v46.24 — 2026-06-22 (Repair Mode Auto-Exit + TP3 Targeting for TIER 1)

### 2 Features Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 141 | SHORT repair mode now auto-exits when H/FF/CHZ combined WR ≥ 55% over ≥ 6 resolved trades. Each tracker run checks the criteria inside the existing `_in_repair` block (right after `_rc_real_shorts` is built). On trigger: deletes `short_repair.flag`, sends a dedicated "🎉 SHORT REPAIR MODE LIFTED" Telegram alert with WR and trade count, updates `_in_repair` and `_short_status_line` for the rest of that run. Previously repair mode could only be lifted manually. | whale_stream_tracker.py |
| 142 | TP3 targeting for TIER 1 trades in the auto-trader. When a signal has confidence ≥ 92% (TIER 1), the trader now attempts to use TP3 as the Bybit take-profit, provided TP3 is valid (correct side of TP2). Falls through to TP2 if TP3 is absent/invalid, then to TP1. TIER 2/3 trades (<92%) continue to target TP2 as before. Also: confidence value parsed from col 2 and included in Telegram order alert ("Conf: 94% ∣ ...") and debug print shows TIER label and TP3 value. | whale_stream_trader.py |

---

## v46.23 — 2026-06-22 (Confidence Tier Analysis + Dynamic LONG Avoid List)

### 2 Features Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 138 | Add LONG confidence tier WR breakdown to `analyze_shorts.py` to validate v46.21 calibration. New section "LONG WIN RATE BY CONFIDENCE TIER (v46.21)" splits resolved LONGs into TIER 1 (92%+), TIER 2 (88–91%), TIER 3 (85–87%) and reports trade count, WR, avg P&L, avg WIN P&L, avg LOSS P&L per tier. Includes automatic verdict: if TIER 1 has 3+ trades, prints whether TIER 1 outperforms TIER 2, matches it, or falls short — with the calibration conclusion. If fewer than 3 TIER 1 trades exist, reports how many are logged and prompts for more data. | analyze_shorts.py |
| 139 | Dynamic LONG avoid list injected into bot prompt graveyard at runtime. `fetch_signal_graveyard()` now scans all resolved LONGs and builds a per-coin W/L map. Any coin with 0 wins over 3+ LONG attempts gets added to `_long_avoid` list. When non-empty, appends a `🚫 LONG AVOID LIST` block to the graveyard prompt with explicit "DO NOT LONG" directive, coin names, and override threshold of 97%+. Logged to console at each run. Mirrors the existing SHORT auto-blacklist mechanism for LONGs. | whale_stream_bot.py |

---

## v46.22 — 2026-06-22 (Orphan Checker: TYPE C TP2 Pursuit Detection)

### 1 Fix Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 137 | Orphan checker fired TYPE A CRITICAL for TP2 pursuit positions introduced by v46.19. When the tracker resolves WIN/TP1, the Bybit order targeting TP2 stays open — the orphan checker saw "Bybit position + no OPEN sheet row" and sent a false alarm. Fix: `get_sheet_signals()` now also collects WIN rows resolved in the last 24h. TYPE A logic excludes coins with a recent WIN row. New TYPE C ("TP2 Pursuit") classification reports these as INFO, with a friendly Telegram note saying the position is intentionally chasing TP2. True orphans (no OPEN row, no recent WIN row) still fire TYPE A CRITICAL. | check_bybit_orphans.py |

---

## v46.21 — 2026-06-22 (Unlock 92%+ Confidence Scores for Elite LONG Setups)

### 1 Feature Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 136 | Signals clustering at 88–90% confidence — bot never outputting 92%+. Root cause 1: no explicit criteria told the model when a setup earns the top band, so it defaulted conservatively to the middle range. Root cause 2: the example JSON had SHORTs at 88–89% (now below the 95% minimum), anchoring SHORT scores below the legal threshold. Fix 1: added CONFIDENCE CALIBRATION section with explicit TIER 1/2/3 bands and six actionable conditions that MUST trigger a 92%+ score (negative funding, RS vs BTC ≥3%, Stage 2-3 with rising OI, multi-TF confluence, etc.). Fix 2: updated example JSON to show realistic values — LONGs at 94%/92%/88%, SHORTs at 96%/95% — conforming to current rules. | whale_stream_bot.py |

---

## v46.20 — 2026-06-22 (Remove Stale Hardcoded WRs from SHORT Repair Prompt)

### 1 Fix Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 135 | Remove hardcoded H/FF/CHZ win rates from static WHALE_STREAM_PROMPT. The static system message had `H — 75% WR (3W/1L)`, `FF — 100% WR (2W/0L)`, `CHZ — 100% WR (1W/0L)` that would go stale as trades accumulated. The dynamic injection at `fetch_signal_graveyard()` (line ~694) already computes live WRs from resolved trades and injects them into the graveyard block each run. Fix: replaced hardcoded values with "See SHORT RECOVERY MODE ACTIVE section in graveyard for current W/L data" — Claude now reads live data from the graveyard instead of contradictory stale figures in the system prompt. | whale_stream_bot.py |

---

## v46.19 — 2026-06-22 (Trader TP2 Targeting — Capture More Upside)

### 1 Feature Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 134 | Trader now uses TP2 as the Bybit order take-profit when TP2 is present and valid (correct side of TP1), falling back to TP1 when TP2 is absent or zero. Root cause: Bybit orders always targeted TP1 only, resulting in TP distribution of 55 TP1 / 0 TP2 / 1 TP3 despite signals having TP2 in column 7. Fix: parse `tp2_str` from `row[COL_TP2]`, validate direction (`tp2 > tp1` for LONG, `tp2 < tp1` for SHORT), and pass `bybit_tp` (TP2 when valid, TP1 otherwise) to `place_order`. Debug print shows TP1/TP2 values and which level Bybit is targeting. Telegram alert updated to show `TP1`/`TP2` label. | whale_stream_trader.py, whale_stream_bot.py |

---

## v46.18 — 2026-06-22 (Trader Price Invalid Fix — 86% Order Failure Rate)

### 1 Fix Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 133 | Fix 86% trader order failure ("Price invalid" retCode=10001): `round_price()` called `str(tick_size)` which gives `"1e-05"` in Python for tick sizes ≤ 0.00001. `"." not in "1e-05"` → `decimals = 0` → `round(0.054, 0)` = `0.0` → Bybit receives price `"0.0"` → "Price invalid". Affected all low-price altcoins with small tick sizes (TRX, SEI, OP, WIF, FF, H). Fixed with `_count_decimals()` helper using `f"{tick:.10f}".rstrip("0")` to always get plain decimal notation. Also added `fmt_price()` to explicitly format all price strings sent to the Bybit API. Added DEBUG output on failure showing exact values sent. | whale_stream_trader.py |

---

## v46.17 — 2026-06-22 (Circuit Breaker False Alarm Fix)

### 1 Fix Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 131 | Fix circuit breaker false alarm: `resolved[-12:]` used Google Sheets row order (logging timestamp), not resolution timestamp. During a 10× WIN streak the circuit breaker still fired because recently-logged OPEN signals sit at the bottom of the sheet — so "last 12 resolved by row" picked up older clustered losses from earlier in the sheet. Fix: sort `resolved` by `resolved_at` (column 16, `"YYYY-MM-DD HH:MM"`) before taking `[-12:]`, applied in both `print_stats` and `write_dashboard_html`. | whale_stream_tracker.py |

---

## v46.16 — 2026-06-22 (Log Analyzer Truncation Stat Fix)

### 1 Fix Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 128 | Fix analyze_logs.py truncation stat: regex matched old `stop_reason=` format only, missing all `stop=` format entries → reported false 45.5% alarm. Root cause: log format changed in v46.4 from `stop_reason=X` to `stop=X`. Fixed regex to `stop(?:_reason)?=`. Real picture: 24/74 historical API calls truncated (pre-v46.4 with 8k limit), 0% truncation on all v46.15+ runs (50% headroom on 16k limit). Updated output labels to clarify historical vs current. | analyze_logs.py |

---

## v46.15 — 2026-06-22 (CEO Full-Codebase Audit + Fix Session)

### 8 Audit Fixes Shipped

| Fix | Issue | Files |
|-----|-------|-------|
| #A | 93% vs 95% SHORT confidence contradiction in REPAIR MODE prompt block | whale_stream_bot.py |
| #B | UTF-8 TextIOWrapper fix missing from trader.py (emoji crashes in Task Scheduler) | whale_stream_trader.py |
| #C | ADD_ORPHAN_CHECK_TASK.bat + ADD_LOG_ANALYZER_TASK.bat called python.exe directly, bypassing PYTHONIOENCODING; created run_orphan_check.bat + run_log_analyzer.bat wrappers | 2 BAT files + 2 new wrappers |
| #D | Schedule header comment said "2 hours" in 2 places in bot.py (should be 4h) | whale_stream_bot.py |
| #E | Gate 1 ETA used signal `ts` instead of `resolved_at` → pessimistic ETA estimate | whale_stream_tracker.py |
| #F | Dead `_conf_bar()` function removed; stale docstrings updated (300→200 coins, 6→8 signals, 2h→4h); stale weekly_summary comment fixed | whale_stream_bot.py + tracker.py |
| #G | Hardcoded "2026-06-21 audit" date in trader REPAIR MODE Telegram message | whale_stream_trader.py |
| #H | `profit_factor = 0` when no losses in dashboard (should be ∞); display shows "∞" symbol | whale_stream_tracker.py |

### Audit Summary
Full 4-agent parallel audit run on all 4 Python scripts + 10 support files. **17 checklist items across trader + analyze_shorts, 13 items for bot.py, 13 items for tracker.py, 13 items for ops/BAT files** — all now PASS. No syntax errors. No import errors. No dead critical logic.

---

## v46.14 — 2026-06-22 (CEO Autonomy Session — continued 10)

### 2 Tasks Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 111 | Add UTF-8 encoding fix to bot.py (bot crashed in Task Scheduler — no io.TextIOWrapper) | whale_stream_bot.py |
| 112 | Add ENTRY ZONE WIDTH RULE to prompt — target 67% LONG expiry rate | whale_stream_bot.py |

### Key Improvements
- **UTF-8 crash fixed (CRITICAL)**: `whale_stream_bot.py` was missing the `io.TextIOWrapper` encoding fix that `whale_stream_tracker.py` has had since Task #31. Every scheduled Task Scheduler run that lacked `PYTHONIOENCODING=utf-8` in the environment crashed at the first `print()` call. Now bot.py sets UTF-8 stdout/stderr at import time — same pattern as tracker.py (lines 26-29), Python 3.14 compatible.
- **Entry zone width guidance added**: Historical data (analysis_shorts.txt run 2026-06-21) shows **67% of all LONG signals expire unused** — price never pulls back to the entry zone in 72h. Root cause: Claude was setting narrow zones only 1-2% wide, which market frequently skips over. New `ENTRY ZONE WIDTH RULE` injected into prompt:
  - Entry zone BOTTOM must be ≥5–8% below TOP (min zone width 4% of top)
  - Stage 2 expansion plays may use near-market entry
  - Explicit instruction: "prefer filled signals" — a wider zone that fills beats a tight zone that expires
  - Target: reduce expiry rate from 67% → below 45%

---

## v46.13 — 2026-06-22 (CEO Autonomy Session — continued 9 — FINAL)

### 1 Task Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 110 | Show SHORT signal coin names in bot end-of-run Telegram during REPAIR MODE | whale_stream_bot.py |

### Key Improvement
- **Recovery coin visibility per run**: Bot end-of-run Telegram now shows `2🔴 SHORT [H, CHZ — recovery]` instead of just `2🔴 SHORT` when `short_repair.flag` is present. Makes every bot run's recovery contribution immediately visible without checking analyze_shorts.py.

---

### Session Summary (CEO Autonomy — Tasks #96–#110)
This session shipped 15 tasks across 4 scripts + 2 docs, focusing on SHORT recovery observability and correctness:

| File | Tasks |
|------|-------|
| whale_stream_bot.py | #96, #103, #105, #107, #109, #110, #106, #108 (v-bumps + prompt fixes) |
| whale_stream_tracker.py | #98, #101, #104 (Gate 6, Telegram, dashboard) |
| analyze_shorts.py | #99 (recovery progress section) |
| whale_stream_trader.py | #102 (module-level constant) |
| SHORT_RECOVERY_PLAYBOOK.md | #97 (stale note removed) |
| CHANGELOG.md | continuous |

**Key themes**: (1) Critical "ts" bug unblocked Gate 1 ETA, 60h alerts, Gate 6 checklist. (2) SHORT recovery progress now visible in 3 places: analyze_shorts output, 30-min Telegram, dashboard. (3) Dynamic recovery coin WRs in graveyard prompt — auto-updates as H/FF/CHZ accumulate trades. (4) No more mixed signals in REPAIR MODE.

---

## v46.12 — 2026-06-22 (CEO Autonomy Session — continued 8)

### 2 Tasks Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 107 | v46.11 bump (covered prior) | — |
| 108 | Suppress "SHORT WR CRITICAL ≥95%" graveyard warning when REPAIR MODE active | whale_stream_bot.py |

### Key Improvement
- **No mixed signals in REPAIR MODE**: Previously, when `short_repair.flag` exists and SHORT WR < 40%, Claude saw both "REQUIRE SHORT CONFIDENCE ≥ 95% OR SKIP SHORTS" AND "SHORT RECOVERY MODE ACTIVE — H/FF/CHZ at 93%". These contradicted each other. Now the threshold warning is suppressed entirely in REPAIR MODE — the recovery guidance block handles all SHORT instruction.
- **`_in_repair_mode` variable**: Pre-computed once at the start of the graveyard block and reused for both the threshold check and the recovery guidance injection (DRY cleanup).

---

## v46.11 — 2026-06-22 (CEO Autonomy Session — continued 7)

### 1 Task Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 106 | Dynamic H/FF/CHZ WR in graveyard SHORT recovery prompt (was hardcoded 3W/1L etc.) | whale_stream_bot.py |

### Key Improvement
- **Live recovery WR in prompt**: The graveyard's SHORT RECOVERY MODE block now computes H/FF/CHZ WRs from actual resolved SHORT data each run. Previously hardcoded to "H (3W/1L — 75% WR)" etc. — these numbers would silently go stale as more trades accumulated. Now Claude always sees current WR for each recovery coin, with auto-updated priority notes (← BEST, ← Promising, ← Monitor closely, ← No trades yet).

---

## v46.10 — 2026-06-22 (CEO Autonomy Session — continued 6)

### 1 Task Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 104 | Dashboard: SHORT recovery coin row (H/FF/CHZ W/L + wins needed) visible when REPAIR MODE active | whale_stream_tracker.py |

### Key Improvement
- **Dashboard recovery strip**: When `short_repair.flag` exists, a yellow-tinted banner now appears between the Gate Status row and Stat Cards. Shows H=3W/1L, FF=2W/0L, CHZ=1W/0L and "Need N more wins → 50% last-20". Pre-computed as a Python string variable to avoid nested f-string quote conflicts (Python < 3.12 compatible).

---

## v46.9 — 2026-06-22 (CEO Autonomy Session — continued 5)

### 6 Tasks Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 97 | Remove stale "verify WLD/AVAX" note from SHORT_RECOVERY_PLAYBOOK.md | SHORT_RECOVERY_PLAYBOOK.md |
| 98 | Fix Gate 6 in _update_gate_checklist to use resolved_at (not ts) — consistent with dashboard | whale_stream_tracker.py |
| 99 | SHORT recovery progress section in analyze_shorts.py (H/FF/CHZ per-coin WR, wins needed) | analyze_shorts.py |
| 100 | Syntax verify analyze_shorts.py (manual review — bash unavailable) | — |
| 101 | SHORT recovery coin summary in 30-min Telegram (H/FF/CHZ WR + wins needed to hit 50%) | whale_stream_tracker.py |
| 102 | Move SHORT_RECOVERY_COINS to module level in whale_stream_trader.py | whale_stream_trader.py |

### Key Improvements
- **Documentation cleaned**: Stale "verify WLD/AVAX" note removed from playbook (all 8 coins confirmed in blocklist since v46.5).
- **Gate 6 consistency**: Dashboard and checklist auto-updater now both use `resolved_at` for weekly grouping (trades counted in the week they RESOLVED, not when they were signaled).
- **Recovery visibility x3**: SHORT recovery progress now surfaced in three places: (1) analyze_shorts.py has a new "SHORT RECOVERY PROGRESS" section with per-coin table + ETA, (2) 30-min Telegram now shows "🔄 Recovery: H=3W/1L FF=2W/0L CHZ=1W/0L | need N more wins", (3) dashboard Gate 3 card already shows dynamic mode.
- **Code cleanliness**: SHORT_RECOVERY_COINS promoted from inline loop variable to module-level constant in trader.

---

## v46.8 — 2026-06-21 (CEO Autonomy Session — continued 4)

### 1 Task Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 95 | CRITICAL BUG: add "ts" field to all_parsed dict — Gate 1 ETA, 60h expiry alert, Gate 6 weekly check were all silently failing | whale_stream_tracker.py |

### Critical Bug Fixed
- **Root cause**: `all_parsed.append()` included coin/signal/status/pnl/tp_hit/resolved_at but NOT `"ts"` (signal timestamp). Three features silently broke:
  1. **Gate 1 ETA** (Task #68): `_r.get("ts", "")` always got `""`, datetime.strptime failed silently → showed "insufficient data" every run despite having valid timestamps in Sheets.
  2. **60h CRITICAL expiry alert** (Task #78): `age_h` calculation always failed → no CRITICAL alerts ever fired for old trades.
  3. **Gate 6 weekly check** in `_update_gate_checklist()`: `r["ts"][:10]` used for week grouping → `week_pnl` always stayed empty → Gate 6 always showed 0/3 weeks.
- **Fix**: Added `"ts": ts_str` to the `all_parsed.append()` dict. One line, three features restored.
- **Unaffected**: Dashboard Gate 6 card uses `resolved_at` (not `ts`) — it was correct throughout.

---

## v46.7 — 2026-06-21 (CEO Autonomy Session — continued 3)

### 4 Tasks Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 91 | Selective SHORT unlock: H/FF/CHZ allowed even in REPAIR MODE | whale_stream_trader.py |
| 92 | SHORT ban list in prompt updated (add WLD/INJ/AVAX) | whale_stream_bot.py |
| 93 | Gate 3 dashboard card dynamic repair mode display | whale_stream_tracker.py |
| 93 | SHORT repair mode prompt: add preferred recovery coins (H/FF/CHZ) | whale_stream_bot.py |

### Key Improvements
- **Deadlock broken**: Previously ALL SHORTs were blocked in REPAIR MODE — WR could never recover. Now H(75% WR), FF(100%), CHZ(100%) are allowed through even when short_repair.flag exists. Recovery can now happen automatically.
- **Prompt alignment**: SHORT REPAIR MODE guidance in WHALE_STREAM_PROMPT now explicitly lists H/FF/CHZ as preferred recovery coins and reminds Claude to prioritize them.
- **Dashboard**: Gate 3 card now dynamically shows "REPAIR MODE — recovery: H/FF/CHZ only" vs "FULL MODE" based on flag file, plus W/L counts.
- **Complete ban list**: WLD, INJ, AVAX now in both code (SHORT_COIN_BLOCKLIST) and prompt ban list text.

### Recovery Path (Gate 3)
SHORT WR needs to reach 50% over 20 trades. Current: 25% (6W/18L).
Math: need ~12 more SHORT WINs from next ~20 trades to hit 50%.
Recovery coins (H/FF/CHZ) are now unlocked and will accumulate results.

---

## v46.6 — 2026-06-21 (CEO Autonomy Session — continued 2)

### 10 Tasks Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 80 | v46.5 version bump + CHANGELOG for Tasks #72-#79 | whale_stream_bot.py, CHANGELOG.md |
| 81 | Heartbeat monitor: Telegram alert if bot misses a run | whale_stream_tracker.py |
| 82 | ADD_BOT_TASK.bat comment fix (6h → 4h) | ADD_BOT_TASK.bat |
| 83 | Rank-5 parse verification (all paths confirmed clean) | — |
| 84 | Add WLD/INJ/AVAX to SHORT_COIN_BLOCKLIST (safety fix) | whale_stream_bot.py |
| 85 | Gate 2 WR + SHORT repair status in tracker Telegram | whale_stream_tracker.py |
| 86 | LONG WR by pattern section in analyze_shorts.py | analyze_shorts.py |
| 87 | Permanent SHORT ban list injected into graveyard prompt | whale_stream_bot.py |
| 88 | LONG WR decay alert (<50%) in tracker Telegram | whale_stream_tracker.py |
| 89 | SHORT recovery approved coins (H/FF/CHZ) in graveyard prompt | whale_stream_bot.py |

### Key Improvements
- **Safety fix**: WLD (0W/2L), INJ (0W/2L), AVAX (0W/1L) now code-blocked in SHORT_COIN_BLOCKLIST. Full list: ENA, XLM, BCH, VVV, ZRO, WLD, INJ, AVAX.
- **Heartbeat monitor**: Tracker alerts via Telegram if bot_log.txt not updated in >5h during 06:00-23:00 BKK active hours.
- **Telegram enriched**: Every 30-min tracker run now shows Gate 2 status, SHORT repair mode, and LONG WR decay warning.
- **Pattern analysis**: analyze_shorts.py now shows LONG WR breakdown by pattern type with ⭐/✅/⚠️/❌ ratings.
- **Graveyard prompt**: Permanent ban list (8 coins) shown every run. SHORT recovery mode injects approved coins (H 75%, FF 100%, CHZ 100%) to steer Claude toward winning pairs.
- **Version tracking**: ADD_BOT_TASK.bat updated to 4h schedule to match live Task Scheduler config.

### Gate Status as of 2026-06-21
- Gate 1: ❌ ~80/150 trades (ETA ~2-3 days at ~30/day with new 4h/5-LONG schedule)
- Gate 2: ❓ (run analyze_shorts.py — LONG WR likely 55-60%)
- Gate 3: ❌ SHORT WR 25% — REPAIR MODE (approved coins: H, FF, CHZ)
- Gate 4: ✅ ~$492.58
- Gate 5: ✅ No circuit breaker
- Gate 6: ❌ <3 consecutive profitable weeks

---

## v46.5 — 2026-06-21 (CEO Autonomy Session — continued)

### 8 Tasks Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 72 | LONG WR by coin ranked table in analyze_shorts.py | analyze_shorts.py |
| 73 | Dashboard auto-refresh (5min) + Gate 6 card | whale_stream_tracker.py |
| 74 | Signal expiry rate analysis in analyze_shorts.py | analyze_shorts.py |
| 75 | Coin performance table injected into bot prompt | whale_stream_bot.py |
| 76 | Bot run frequency 6h → 4h (6 runs/day) | UPDATE_BOT_SCHEDULE_4H.bat (new), Task Scheduler |
| 77 | LONG signals per run 4 → 5 (~30/day vs prior 16) | whale_stream_bot.py |
| 78 | 60h CRITICAL expiry alert in tracker Telegram | whale_stream_tracker.py |
| 79 | Executive summary header at top of analyze_shorts | analyze_shorts.py |

### Key Improvements
- **Gate 1 acceleration**: 4h schedule × 5 LONGs/run = ~30 signals/day (was 16). ETA drops ~3 weeks → ~10 days.
- **Signal graveyard feedback loop**: Coin performance (last 30 LONGs, min 2 trades) injected into bot prompt each run.
- **Expiry visibility**: EXPIRED trades now tracked separately with count, rate, and avg P&L. >25% rate triggers warning.
- **Dashboard**: 5-min auto-refresh, Gate 6 now visible alongside Gates 1/2/3, last-updated timestamp in header.
- **Critical alerts**: Trades ≥60h old flagged 🚨 CRITICAL in Telegram (vs just 48-59h ⚠️ EXPIRING SOON).
- **Analysis**: Executive summary banner at top of analyze_shorts.py output for quick health snapshot.

### Gate Status as of 2026-06-21
- Gate 1: ❌ ~80/150 trades (~10-day ETA at 30/day)
- Gate 2: ❓ (run analyze_shorts.py)
- Gate 3: ❌ SHORT WR 25% — REPAIR MODE
- Gate 4: ✅ ~$492.58
- Gate 5: ✅ No circuit breaker
- Gate 6: ❌ <3 consecutive profitable weeks

---

## v46.4 — 2026-06-21 (CEO Autonomy Session)

### 21 Tasks Shipped

| # | Task | Files Changed |
|---|------|---------------|
| 47 | Increase LONG signals 3→4 per run | whale_stream_bot.py |
| 48 | Replace hardcoded SHORT skip with short_repair.flag system | whale_stream_trader.py |
| 49 | Add SHORT recovery auto-trigger to analyze_shorts.py | analyze_shorts.py |
| 50 | Gate 1 progress counter in bot end-of-run Telegram | whale_stream_bot.py |
| 51 | Auto-run analyze_shorts.py every Sunday via tracker | whale_stream_tracker.py |
| 52 | LONG P&L Gate 2 section in analyze_shorts.py | analyze_shorts.py |
| 53 | Verify 4-LONG correlation rule — no gap found | — |
| 54 | Gate 1/2/3 status section in dashboard + fix SHORT WR to 24% | whale_stream_tracker.py |
| 55 | Code-level SHORT coin blocklist (ENA/XLM/BCH/VVV/ZRO) | whale_stream_bot.py |
| 56 | Post-run pipeline summary Telegram in tracker | whale_stream_tracker.py |
| 57 | LONG confidence threshold recommendation in analyze_shorts.py | analyze_shorts.py |
| 58 | Bybit demo balance low-balance alert ($450 threshold) | whale_stream_trader.py |
| 59 | Circuit breaker raised 3→5 consecutive losses in REPAIR MODE | whale_stream_trader.py |
| 60 | Rolling LONG WR (last 20) in tracker run Telegram | whale_stream_tracker.py |
| 61 | TP hit distribution (TP1/TP2/TP3/TP4) in analyze_shorts.py | analyze_shorts.py |
| 62 | audit_open_signals.py — stale OPEN signal audit tool | audit_open_signals.py (new) |
| 63 | LONG coin blocklist framework + auto-suggestion in analyze_shorts | whale_stream_bot.py, analyze_shorts.py |
| 64 | Gate checklist auto-updater every Sunday | whale_stream_tracker.py, GATE5_REAL_CAPITAL_CHECKLIST.md |
| 65 | check_bybit_orphans.py — Bybit position orphan detector | check_bybit_orphans.py (new) |
| 66 | analyze_logs.py — log health report parser | analyze_logs.py (new) |
| 67 | OPEN pipeline count in bot end-of-run Telegram | whale_stream_bot.py |
| 68 | Gate 1 ETA calculator in tracker Telegram | whale_stream_tracker.py |
| 69 | SHORT_RECOVERY_PLAYBOOK.md | SHORT_RECOVERY_PLAYBOOK.md (new) |
| 70 | ADD_ORPHAN_CHECK_TASK.bat + ADD_LOG_ANALYZER_TASK.bat | (new) |
| 71 | v46.4 version bump + CHANGELOG.md | all 3 main scripts |

### Key Architecture Changes
- **SHORT REPAIR MODE**: Flag-file system replaces hardcoded skip. auto-recovers when WR >= 50%.
- **Fake entry elimination**: Two-filter system (wrong P&L sign + abs < 5%) applied at bot, graveyard, and analysis layers.
- **Gate status visibility**: Dashboard, Telegram, and weekly MD checklist all now show live gate status.
- **Code-level blocklists**: SHORT_COIN_BLOCKLIST and LONG_COIN_BLOCKLIST enforce bans independent of Claude's prompt.
- **Sunday automation**: weekly_summary + analyze_shorts + gate checklist update all fire automatically.
- **Observability**: 4 new standalone tools (audit_open_signals, check_bybit_orphans, analyze_logs, analyze_shorts).

### Gate Status as of 2026-06-21
- Gate 1: ❌ 80/150 trades
- Gate 2: ❓ (run analyze_shorts.py)
- Gate 3: ❌ 24.0% SHORT WR — REPAIR MODE
- Gate 4: ✅ $492.58 (-1.5%)
- Gate 5: ✅ No circuit breaker
- Gate 6: ❌ <3 consecutive profitable weeks

---

## v46.3 — Prior session
- WIN/LOSS misclassification investigation (Task #38)
- ENA blocklist, SHORT suspension, TP1 minimum distance rule (Task #42)
- Signal quality KPI in Telegram (Task #46)
- SHORT confidence raised to 95% minimum
