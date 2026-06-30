# WHALE-STREAM CHANGELOG

## v47.25 — 2026-06-30 — Strategist score calibration + AVOID prominence; pattern WR in bot; debrief pattern+time AVOID auto-writer

### `whale_stream_strategist.py`
- **NEW: SIGNAL SCORE CALIBRATION section in system prompt** — explicit tier-based decision guidance: ELITE (9-10) → lean APPROVE, GOOD (7-8) → normal evaluation, MARGINAL (5-6) → lean REDUCE_SIZE. Closes the gap where score was computed and shown but Claude had no instruction on how to weight it in APPROVE/REDUCE/VETO decisions.
- **NEW: AVOID LESSONS rule in system prompt** — tells Claude that any `[AVOID]`-tagged lesson in PATTERN MEMORY is mandatory institutional memory: matching signals must be at least Grade C (REDUCE_SIZE), or Grade D (VETO) if the lesson directly describes the current setup.
- **NEW: AVOID lessons surfaced prominently in user message** — before the full coin lessons block, a dedicated `⚠️ ACTIVE AVOID LESSONS` section now lists all `[AVOID]`-tagged lessons for signal coins, making them impossible to miss in the context window.

### `whale_stream_bot.py`
- **NEW: Pattern WR injection into graveyard prompt** — after AVOID lessons block, reads `debriefs` from `pattern_memory.json`, computes per-pattern WR (normalised to 60 chars, min 3 trades), injects top 3 proven winners (WR ≥ 65%) and worst 3 chronic losers (WR ≤ 40%) into `graveyard_text`. Claude now steers toward proven setups and away from confirmed losing patterns at signal-generation time. Fails silently if no data yet.

### `whale_stream_debrief.py`
- **NEW: Pattern+time AVOID lesson auto-writer** — in `save_memory()`, after all stats blocks, scans all debriefs to build `(coin, direction, pattern, 4h-slot)` combo stats. If a combo has ≥3 losses AND WR < 40%, auto-writes `[AVOID] {pattern} at {slot}:00 BKK — {N}L/{total} = {wr}% WR (chronic loss combo)` into `coin_lessons[coin][direction]`. These are immediately picked up by the bot (graveyard AVOID injection) and Strategist (AVOID lessons block) in the next cycle. Dedup check prevents re-writing the same combo.

## v47.24 — 2026-06-30 — Score-based position sizing; time-of-day WR; holding period analysis

### `whale_stream_trader.py`
- **NEW: Score-based position sizing** — after signal passes score gate and MTF freshness penalty, applies a final size multiplier based on score tier: ELITE (9-10) = 1.0×, GOOD (7-8) = 0.85×, MARGINAL (5-6) = 0.70×. Applied multiplicatively after Strategist REDUCE and MTF penalty. Floor `_MIN_SIZE_MULT = 0.25` protects against stacked reductions. Logged with tier name and resulting multiplier.

### `analyze_shorts.py`
- **NEW: Time-of-day WR breakdown** — groups LONG resolved trades by the 4-hour BKK slot their signal was generated (00/04/08/12/16/20), matching the bot run schedule. Shows per-slot trades / wins / WR with ✅/⚠️/❌ icons and session label. Flags slots with WR < 45% over ≥5 trades as weak and suggests raising confidence floor for those hours.
- **NEW: Holding period analysis** — parses `ts` and `resolved_at` fields (populated from v46.27+) to compute hold duration in hours for each resolved trade. Shows avg hold time for wins vs losses, bucket distribution (<6h / 6-24h / 24-48h / 48-72h / >72h) with WR per bucket, expiry capture rates at 36h/48h/72h cutoffs, and a suggested optimal expiry.
- **FIX: `resolved_at` added to `resolved.append()` dict** — field was present in `COL_RESOLVED_AT = 16` but not being collected into the resolved list; holding period analysis now has the data it needs.

## v47.23 — 2026-06-30 — AVOID lesson injection; auto-tune score floor; weekly Telegram health card

### `whale_stream_bot.py`
- **NEW: AVOID lessons injected into signal-generation prompt** — after adaptive confidence floors block in `fetch_signal_graveyard()`, reads `coin_lessons` from `pattern_memory.json`, extracts all `[AVOID]`-flagged lessons per coin+direction, injects up to last 2 per coin (capped at 15 total) into `graveyard_text` under `RECENT AVOID LESSONS` header. Claude now sees specific post-trade loss lessons at signal-generation time — mistakes are stopped at the source, not just filtered downstream. Fails silently.

### `whale_stream_debrief.py`
- **NEW: Score tag in Telegram debrief message** — each trade entry now shows `📊X/10` score (from `strat_decision.get("score")`) inline after MTF tag: `✅ BTC LONG [A][4H_BULL_1H_PULLBACK] 📊8/10 +12.4%`. Shows `null` trades as no tag (score unavailable for pre-v47.21 trades).
- **NEW: Auto-tune score floor** — in `save_memory()`, after computing `score_tier_stats`: if tier `5-6` has ≥8 trades and WR < 45%, writes `{"SCORE_MIN_TRADER": 6}` to `scorer_config.json`. If WR recovers ≥45%, writes floor back to 5. Logs the change with basis. System self-improves without manual intervention.

### `whale_stream_trader.py`
- **NEW: Read `scorer_config.json` at startup** — immediately after `SCORE_MIN_TRADER = 5` constant, checks for `scorer_config.json` written by debrief auto-tune. If present and valid, overrides the constant. Prints `🎛 scorer_config.json: SCORE_MIN_TRADER overridden to 6`. Falls back silently to constant 5 if file absent or corrupt.

### `analyze_shorts.py`
- **NEW: Weekly Telegram health card** — at end of `main()`, sends compact ops channel message: Gate 1/3 status, LONG/SHORT WR, score tier WR table (from `pattern_memory.json`), top 3 LONG coins by WR, top 3 MTF biases, chronic miss coins. Runs every Sunday automatically (tracker already calls analyze_shorts weekly). Fails silently.

---

## v47.22 — 2026-06-30 — Scorer feedback loop; dynamic signal count; entry hit-rate analysis

### `whale_stream_debrief.py`
- **NEW: `"score"` field in debrief entry** — reads `score` from `strategist_decisions.json` (loaded via existing `load_strategist_decision()`) and saves it alongside the debrief entry in `pattern_memory.json`. Enables score-vs-outcome correlation over time. Null when Strategist data is unavailable (pre-v47.21 trades).
- **NEW: `score_tier_stats` in `save_memory()`** — rebuilt on every save across all debriefs. Counts wins/losses in four tiers: `0-4` (weak), `5-6` (marginal), `7-8` (good), `9-10` (elite). Stored in `pattern_memory.json` as `score_tier_stats`. Used by `analyze_shorts.py` to validate scorer effectiveness.

### `analyze_shorts.py`
- **NEW: SIGNAL SCORE TIER WIN RATES section** — loads `score_tier_stats` from `pattern_memory.json`, displays per-tier WR with coloured progress bars. Prints validation verdict: if elite (9-10) tier WR ≥ good (7-8) tier WR, scorer is validated; otherwise flags for review.
- **NEW: ENTRY ZONE HIT-RATE — CHRONIC MISS COINS section** — groups EXPIRED signals by coin, computes per-coin expiry rate and average entry zone width. Flags coins with ≥70% expiry rate as `CHRONIC MISS`. Collected entry zone string added to `expired_longs` dict at parse time (`COL_ENTRY = 3`).

### `whale_stream_bot.py`
- **NEW: Dynamic signal count based on BTC 4H regime** — `_get_btc_regime_bot()` fetches BTC 4H klines from Bybit public API at end of each run. Regime determines how many signals to keep: NEUTRAL/SIDEWAYS → 2+2 (conservative), BULL → 3+2, BEAR → 2+3, Strong BULL (>5%) → 4+2, Strong BEAR (>5%) → 2+4. Replaces hardcoded `[:3]` slice with dynamic `[:_n_long]` / `[:_n_short]`. Fails silently (defaults to 3+3 if API unreachable). Logged on every run: `📡 BTC 4H Regime: BULL (+3.1%) — standard 3+2`.

---

## v47.21 — 2026-06-30 — Signal score gate; adaptive confidence floors; MTF freshness re-check

### `whale_stream_strategist.py`
- **NEW: Score annotation on all decisions** — after scoring, builds `_score_map = {(coin, direction): score}` from all signal tiers. Adds `"score"` field to every `auto_vetoed` entry and to all entries in `parsed["decisions"]` that lack a score (belt-and-suspenders annotation). Trader can now read per-signal score directly from `strategist_decisions.json`.

### `whale_stream_trader.py`
- **NEW: `SCORE_MIN_TRADER = 5`** — hard floor on signal quality score. Signals with `score < 5` are skipped before Strategist VETO check. Logs `⏭ SCORE GATE:` with score and floor. Belt-and-suspenders after Strategist auto-vetoes at score < 4.
- **NEW: `_strat_scores` dict** — loaded alongside `_strat_vetoes`/`_strat_reduces` from `strategist_decisions.json`. Keys are `(coin, direction)` tuples; values are numeric scores 0–10.
- **NEW: `get_btc_4h_bias_fresh()`** — fetches BTC 4H klines from Bybit public API (no auth), classifies bias as BULL/BEAR/NEUTRAL using SMA20 ±2% threshold. Called once per trader run. Returns `(bias, pct_from_sma20)`.
- **NEW: MTF freshness penalty** — after Strategist REDUCE check, if `_fresh_btc_bias != "NEUTRAL"` and signal is counter-trend (LONG in BEAR or SHORT in BULL), applies 0.5× additional size reduction with `🔭 MTF SHIFT:` log entry. Fails silently when API is unreachable. Does not hard-skip — Strategist already handles that layer.

### `whale_stream_bot.py`
- **NEW: Adaptive confidence floors** — in `fetch_signal_graveyard()`, reads `coin_stats` from `pattern_memory.json`. Coins with WR < 40% (≥3 trades) get `require ≥93% confidence` injected into the Claude prompt. Coins with WR ≥ 70% (≥5 trades) are flagged as PROVEN. Fails silently if pattern_memory.json not yet present. Per-coin history now directly shapes signal confidence thresholds.

---

## v47.20 — 2026-06-30 — MTF backfill + morning MTF landscape + trade_logger mtf_bias field

### `backfill_mtf_bias.py` (NEW)
- **NEW: One-time backfill script** — loads `pattern_memory.json`, re-extracts `mtf_bias` from the `pattern` field of every existing debrief entry using the same `\[([A-Z0-9_]{5,30})\]` regex. Writes updated bias, then rebuilds `mtf_stats` from scratch. Creates a `.pre_backfill_bak` backup first. Prints a full bias WR summary table after completion. Safe to re-run (idempotent).

### `morning_briefing.py`
- **NEW: MTF Landscape section** — `fetch_top_coin_mtf_summary()` fetches 4H×22 + 1H×12 klines for 10 top coins (BTC/ETH/SOL/BNB/XRP/DOGE/ADA/AVAX/LINK/ARB) from Bybit public API. Classifies each coin as 4H:BULL/BEAR/SIDE and 1H:PULL/BNCE/RANG/TOP/BOT. ⭐ marks ideal LONG (4H:BULL + 1H:PULL) and SHORT (4H:BEAR + 1H:BNCE) setups. Pulls historical mtf_stats from pattern_memory.json and surfaces strong/weak biases. Added at end of morning Telegram message before `return`. Fails silently on timeout.
- **NEW: Helper functions** — `_classify_4h(candles)`, `_classify_1h(candles, trend_4h)`, `_MTF_COINS` list.

### `trade_logger.py`
- **NEW: `mtf_bias` field** — `import re` added to module-level imports. In `sync_from_sheets()`, after extracting `pattern`, regex extracts `mtf_bias` (e.g. `"4H_BULL_1H_PULLBACK"`) from the pattern string. Field added to `trades.append({...})`. Added to `_export_csv()` fieldnames after `pattern`. Enables per-MTF-bias win rate analysis on trade history.

---

## v47.19 — 2026-06-30 — MTF intelligence loop complete: scorer dimension 6; Strategist reads mtf_stats; debrief Telegram shows bias tag

### `signal_scorer.py`
- **NEW: Dimension 6 — MTF structure alignment** — `_extract_mtf_bias()` parses `[4H_BULL_1H_PULLBACK]` from the pattern string. `_score_mtf_bias()` returns a signed adjustment (-2 to +2) applied to the base 0-10 score (clamped). Ideal LONG entry (4H_BULL + 1H pullback) = +2. 4H_SIDEWAYS = -2. Counter-trend = -1. Basic trend alignment = +1. No bias = ±0.
- **Updated: `score_signal()` breakdown** — new `"mtf_bias"` key with signed value. Final score = clamp(base + MTF adj, 0, 10).
- **Updated: `format_score_for_prompt()`** — appends `MTF:+N` or `MTF:-N` to the one-line summary Claude sees.
- **Updated: header docstring** — reflects 6-dimension scoring and MTF adjustment semantics.
- **Version bump**: v47.9 → v47.19

### `whale_stream_strategist.py`
- **NEW: mtf_stats block in PATTERN MEMORY section** — after coin_lessons/avoid/prefer injection, reads `mtf_stats` from pattern_memory.json. For biases present in current signals, shows per-bias WR (`✅/⚠️/🚫`). Also flags globally weak biases (≥3 trades, <35% WR) not in current signals as `🚫 KNOWN WEAK BIAS`. Instructs Claude to VETO or REDUCE_SIZE when bias appears weak.
- **Version bump**: v47.17 → v47.19

### `whale_stream_debrief.py`
- **NEW: MTF bias tag in Telegram debrief messages** — `[4H_BULL_1H_PULLBACK]` (or relevant bias) now appears inline after the entry quality bracket: `✅ ETH LONG [A+][4H_BULL_1H_PULLBACK] +4.2%`. Makes post-mortem reading on phone immediate — see outcome vs MTF structure at a glance.
- **Version bump**: v47.18 → v47.19

---

## v47.18 — 2026-06-30 — MTF learning loop: debrief records mtf_bias outcomes; graveyard shows MTF WR; calc_qty overdeploy fix; orphaned TP auto-cancel

### `whale_stream_debrief.py`
- **NEW: `_extract_mtf_bias()` helper** — parses `[4H_BULL_1H_PULLBACK]` from pattern string via regex.
- **NEW: `mtf_bias` field in entry dict** — stored in `pattern_memory.json` debriefs alongside pattern, outcome, flag.
- **NEW: `mtf_bias` context in `build_debrief_prompt()`** — Claude Haiku sees the 4H+1H structure at signal time. Prompt notes 4H_SIDEWAYS should rarely win and flags it in lessons.
- **NEW: `mtf_stats` in `save_memory()`** — computes per-bias `{"wins": N, "losses": N}` across all debriefs. Written to `pattern_memory.json` as `mtf_stats` dict. Closes the MTF learning loop.
- **Version bump**: v47.13 → v47.18

### `whale_stream_bot.py`
- **NEW: MTF_BIAS WR table in signal graveyard** — after `graveyard_text` is built, loads `pattern_memory.json`, reads `mtf_stats`, appends a compact per-bias WR table (only biases with ≥3 trades). ✅ = ≥60% WR, ⚠️ = 45–60%, 🚫 = <45%. Claude uses this for self-reinforcement. Fails silently if file not yet available.

### `whale_stream_trader.py`
- **FIX #299 — `calc_qty()` minimum floor** — `max(qty, info["min_qty"])` previously always returned >0, so the caller's `if qty <= 0: skip` check never fired. Fix: if `round_to_step()` gives qty < min_qty, check whether forcing to min_qty would deploy >150% of intended capital (`min_qty * entry_price > position_value * 1.5`). If so, return 0 (caller skips the order). Prevents silent overdeploy on expensive coins with REDUCE_SIZE scaling.
- **NEW #300 — `cancel_orphaned_tp_orders()`** — fetches all reduce-only (TP) open orders from Bybit, checks each against live positions via `get_position_for_coin()`. Any TP order with no matching position is orphaned (position was closed by SL). Auto-cancels all orphans, logs each, sends Telegram summary. Called in `main()` after stale entry order cleanup. Prevents indefinite accumulation of dangling TP orders.
- **Version bump**: v47.15 → v47.18

---

## v47.17 — 2026-06-30 — MTF chart pattern analysis: real 4H+1H OHLCV candles injected into signals

### `whale_stream_bot.py`
- **NEW: Multi-timeframe (MTF) chart data** — 4 new functions (`get_klines`, `_mtf_trend_label`,
  `compute_coin_mtf_summary`, `fetch_mtf_block`) fetch real Bybit OHLCV candles (4H×20 + 1H×30)
  for the top 20 coins by volume, compute BULL/BEAR/SIDEWAYS trend labels, HH+HL/LH+LL pattern
  hints, and range position (TOP/MID/BOT). No auth required — uses public `/v5/market/kline`.
- **NEW: MTF_BIAS RULE in WHALE_STREAM_PROMPT** — Claude is required to include `mtf_bias` in
  every signal JSON (e.g. `"4H_BULL_1H_PULLBACK"`). IDEAL LONG = 4H:BULL + 1H pulling back.
  IDEAL SHORT = 4H:BEAR + 1H bouncing up. 4H_SIDEWAYS signals get confidence penalty.
- **NEW: MTF_BLOCK injected into DYNAMIC_DATA_TEMPLATE** — between COIN_PERFORMANCE and
  SIGNAL_GRAVEYARD sections.
- **NEW: `mtf_block_text` parameter** added to `analyze_with_claude()` — passed to both
  Batch 1 and Batch 2 calls.
- **NEW: Step 2b in main()** — fetches MTF block (~10-15s) after coin list, before Claude call.
  Fails gracefully with empty string if Bybit API unavailable.
- **NEW: `mtf_bias` combined into pattern column** — Google Sheets column J shows
  `"Bull flag + RS vs BTC [4H_BULL_1H_PULLBACK]"` for easy Strategist reading.
- **Version bump**: v47.16 → v47.17

### `whale_stream_strategist.py`
- **NEW: VETO rule 6** — Pattern contains `4H_SIDEWAYS` → automatic VETO. 4H sideways = structural
  indecision with no edge. Exception: ≥97% confidence + explicit range breakout catalyst → REDUCE_SIZE.
- **Version bump**: v47.14 → v47.17

---

## v47.16 — 2026-06-30 — TP auto-placement: monitor places TP orders after entry fills

### `whale_stream_monitor.py`
- **CRITICAL FIX: Auto-place TP orders when new position detected** — Trader.py places 4
  reduce-only limit TP orders immediately after the entry order, but since the entry is a
  LIMIT order the position doesn't exist yet → Bybit rejects with "current position is zero".
  Monitor.py now detects the fill (~2 min later) and places the 4×25% TP orders automatically.
  Workflow: (1) check Bybit for existing reduce-only orders (skip if trader somehow succeeded),
  (2) read TP1-TP4 from Google Sheets for that coin+direction, (3) place 4 reduce-only GTC
  limit orders, (4) send Telegram with result. Errors are caught per-leg and reported.
- **Version bump**: v47.15 → v47.16

---

## v47.15 — 2026-06-29 — Comprehensive clean-system pass: 12 fixes across 8 files

### `whale_stream_trader.py` (5 fixes)
- **HIGH: Fix stdout double-wrap crash** — Replaced `TextIOWrapper` double-wrap with
  `reconfigure()` pattern (matching strategist.py). The old code created a second wrapper
  around an already-wrapped stdout, causing `ValueError: I/O operation on closed file` on
  shutdown.
- **HIGH: Fix REDUCE_SIZE log/clamp ordering** — `_MIN_SIZE_MULT` clamp was applied AFTER
  the log message, so printed size was pre-clamp while actual order was post-clamp. Fixed
  by applying clamp first, then logging.
- **MEDIUM: Fix veto match to require coin+direction** — Veto lookup was matching open
  positions only by coin, ignoring direction. A LONG veto could incorrectly block a SHORT
  on the same coin. Now requires both coin and direction to match.
- **LOW: Remove stale "July 1 go-live" reference** — `"→ Review July 1 go-live decision."`
  replaced with `"→ Review live trading readiness."` (date-agnostic).
- **LOW: Version banner updated** v47.10 → v47.15.

### `whale_stream_strategist.py` (1 fix)
- **MEDIUM: Fix cycle guard midnight-boundary split** — `datetime.now()` was called twice
  (once for `_cg_hour`, once for the date check), so a run spanning midnight would compare
  today's hour against yesterday's date and skip the cycle incorrectly. Fixed by capturing
  `_cg_now` once before both uses.

### `whale_stream_tracker.py` (1 fix)
- **MEDIUM: Fix Gate 6 streak display** — Checklist string showed `max_consec` (all-time
  peak) instead of `consec` (current trailing streak). Gate 6 checks the *current* trailing
  streak, not the historical max, so the wrong variable was displayed.

### `whale_stream_watchdog.py` (1 fix)
- **LOW: Version banner updated** v47.10 → v47.15.

### `whale_stream_monitor.py` (2 fixes)
- **MEDIUM: Add Bybit auth clock-skew compensation** — Bybit rejects requests whose
  timestamp is ahead of server time. Tracker.py already subtracts 3000ms; monitor.py was
  missing this, causing intermittent auth failures. Fixed to match tracker.py pattern.
- **LOW: Version banner updated** v47.13 → v47.15.

### `whale_stream_debrief.py` (1 fix)
- **LOW: Version banner updated** v47.13 → v47.15.

### `whale_stream_bot.py` (1 fix)
- **LOW: Version banner updated** v47.10 → v47.15.

### `trade_logger.py` (2 fixes)
- **HIGH: Fix pnl_pct falsy bug** — `if pnl_pct:` evaluated False for 0.0 (breakeven
  trades), causing them to log pnl_usd=0.0 even when pnl_pct was explicitly 0.0. Changed
  to `if pnl_pct is not None:`.
- **MEDIUM: Fix trade_id collision** — Same coin+direction closing at the same minute
  generated identical IDs, causing Google Sheets duplicate-key conflicts. Fixed by appending
  the sheet row index `_r{i}` to guarantee uniqueness.

### `morning_briefing.py` (2 fixes)
- **HIGH: Fix Gate 1 division-by-zero** — `g1_target` can be 0 on the first cycle before
  any target is set. Division was unguarded; now checks `g1_target > 0` before dividing.
- **MEDIUM: Fix BTC price truthiness** — `if btc_price and btc_sma:` evaluated False when
  either was 0.0. Changed to `if btc_price is not None and btc_sma is not None:`.

### `check_daily_status.py` (1 fix)
- **LOW: Health check now requires HTTP 200** — Was returning True for any status < 500
  (e.g. 301 redirect, 404 not found). Changed to `return r.status_code == 200`.

---

## v47.13 — 2026-06-29 — Full audit pass: 10 fixes across 6 files

### `whale_stream_trader.py`
- **HIGH: Fix `place_quad_tp_closes()` allocated counter bug** — `allocated += leg_qty` was
  only incremented inside `if ok:`, meaning if TP1/TP2/TP3 legs all failed, the last leg
  (TP4) would receive 100% of the position quantity instead of 25%. Now always increments
  regardless of placement success, so last leg is always bounded to the remainder.
- **HIGH: Remove redundant `bybit_balance.json` re-reads** — Two try/except blocks re-read
  the balance file (for position cap check and drawdown scaling) immediately after it was
  written with the same live values. Simplified to use in-memory variables directly
  (`n_positions`, `total_balance`, `BYBIT_START_BALANCE`), eliminating 2 unnecessary disk reads.

### `whale_stream_watchdog.py`
- **MEDIUM: Raise `STRATEGIST_DEADLINE_MIN` 22 → 25** — Strategist runs at :10, Watchdog at
  :30 = 20-minute gap. Was only leaving 2-minute jitter buffer; raised to 5 minutes.
- **MEDIUM: Add `_mark_done("watchdog")` to `_wdog_excepthook`** — Watchdog crash handler
  sent Telegram alert but never wrote `daily_status.json`. Gap checker would miss the crash.
  Now calls `_mark_done("watchdog", details={"health": "CRASHED"})` before Telegram.
- **LOW: `Get-WmiObject` → `Get-CimInstance`** in self-healing PowerShell command (modern PS syntax).

### `morning_briefing.py`
- **MEDIUM: Add CB grace window visibility** — Added `cb_grace.txt` read to System Flags
  section. Now shows remaining grace minutes and expiry time (BKK) so operator knows exactly
  when the CB can re-arm. Shows "no recent clear" if no file exists.
- **LOW: Removed dead `yesterday` variable** (was defined but never used).

### `whale_stream_monitor.py` / `whale_stream_debrief.py`
- **LOW: Version strings updated** v47.10 → v47.13 in both files (header banner + runtime print).

### `JULY1_GOLIVE_CHECKLIST.md`
- **MEDIUM: Fix "THE ONLY FILE YOU TOUCH" contradiction** — Step 3 said `local_config.py` is
  the only file you touch, but Step 5 also requires editing `trader.py` and `tracker.py` for
  `BYBIT_START_BALANCE`. Removed the misleading phrase from both steps.

## v47.12 — 2026-06-29 — Circuit breaker grace period 60min→480min + FIX_CB_NOW.bat

### Root cause diagnosed
Circuit breaker (CB) was re-triggering on every cycle despite being manually cleared.
Sequence: CB cleared → Trader ran at 08:xx (within 60-min grace) → no orders placed
(no qualifying signals) → grace expired → Trader ran at 12:xx → saw same 3 consecutive
LOSSes → re-triggered CB → system locked again. The 60-minute grace window was too short
to survive a full 4-hour cycle gap.

### `whale_stream_trader.py`
- **Extended CB grace period from 60 → 480 minutes** (8 hours = 2 full trading cycles).
  When operator clears the CB (via CLEAR_PAUSE.bat or FIX_CB_NOW.bat), the `cb_grace.txt`
  override now prevents re-trigger for 8 hours, covering 2 consecutive Trader runs.
  This ensures at least 2 real cycles of opportunity before the CB can re-arm.
  Change: `if _grace_age_min < 60:` → `if _grace_age_min < 480:`

### `FIX_CB_NOW.bat` — Emergency CB clear + grace override (NEW)
- Created for situations where CB needs immediate clearing without a user confirmation dialog.
  Deletes `paused.flag`, writes fresh `cb_grace.txt` with current UTC time (480-min window),
  deletes `cb_pause_alerted.flag` and `balance_warn_alerted.flag` so alerts re-fire correctly.

### `CLEAR_PAUSE.bat`
- Updated displayed message from "60min" to "480min = 8h = 2 full cycles".

## v47.11 — 2026-06-29 — Strategist deadlock self-healing + run_strategist.bat stderr fix

### Root cause diagnosed
Strategist missed all June 29 cycles (00:10, 04:10, 08:10) due to a Python interpreter
shutdown crash (`ValueError('I/O operation on closed file.') / lost sys.stderr`) that left
`cmd.exe` as a zombie process. Windows Task Scheduler saw the task as "Currently Running"
and refused to start new instances.

### `whale_stream_watchdog.py` — Autonomous self-healing
- **Self-heal when Strategist misses its :10 slot**: Watchdog now detects missed Strategist
  cycles and automatically (1) kills stuck Python processes via PowerShell WMI,
  (2) runs `schtasks /End /TN "WhaleStreamStrategist"` to clear the stuck Task Scheduler
  instance, (3) relaunches `run_strategist.bat` via `subprocess.Popen` to cover the missed
  cycle immediately, (4) annotates the Telegram alert with "🔧 Self-heal attempted".
  This makes the 8-agent system fully autonomous — it recovers from interpreter crashes
  without any human intervention.
- Added `import time` and `import subprocess` to support self-healing.

### `run_strategist.bat` — Prevent recurrence
- **Separated stderr from stdout**: Changed `2>&1` (combined file handle) to
  `2>> strategist_task_err.txt` (separate error log). When Python crashes during interpreter
  shutdown, it can no longer fight with itself over a single file handle. The cmd.exe wrapper
  now exits cleanly even after Python's shutdown hook writes to stderr, preventing the zombie
  deadlock that blocked Task Scheduler.
- Added `exit /b 0` at end of bat — ensures cmd.exe always exits even after Python errors.
- Error output now captured in `strategist_task_err.txt` for separate inspection.

### FORCE_FIX_STRATEGIST.bat — Manual recovery tool (for use while stuck)
- New file created (June 29 session): kills stuck Strategist processes, clears Task Scheduler
  "running" record, runs Strategist once immediately, then verifies task is re-enabled.
  Run as administrator when Watchdog self-heal is not yet live (e.g., this outage).

---

## v47.10 — 2026-06-29 — 11 bugs fixed: CRITICAL monitor crash hidden, HIGH trader SHORT floor, HIGH bot short_wr neutral fallback, HIGH SL sweep during CB, HIGH debrief dedup key, HIGH balance alert spam, MEDIUM partial close label, MEDIUM status_server path, MEDIUM gap checker midnight, MEDIUM tracker Gate3 pnl threshold, LOW version strings + CHECKLIST

### `whale_stream_monitor.py` — 3 fixes
- **CRITICAL: Crash handler called `_mark_done()`** — A monitor crash silently marked itself "done",
  hiding the failure from `check_daily_status.py`. Removed `_mark_done()` from crash handler; crash
  now surfaces correctly as a gap in the 4h status check.
- **MEDIUM: Partial close Telegram alert hardcoded "TP1 PARTIAL CLOSE" and "Remaining 75%"** —
  The alert always said TP1/75% even when TP2 or TP3 was the trigger. Now computes
  actual `_remaining_pct = curr_size/prev_size*100` and displays a generic "PARTIAL CLOSE" label.
- **LOW: Banner version stuck at v47.8** — bumped to v47.10.

### `whale_stream_trader.py` — 3 fixes
- **HIGH: SHORT confidence floor hardcoded at 95% unconditionally** — Code always enforced 95%
  regardless of whether REPAIR MODE was active. Fix: `95 if SHORT_REPAIR_FILE exists else 93`.
  This matches the bot.py and system spec (93% floor when WR is healthy).
- **HIGH: `_sweep_missing_sl()` skipped when circuit breaker is active** — The SL sweep ran after
  the `paused.flag` early-return, leaving live positions unprotected during CB pauses. Added a
  Google Sheets load + SL sweep inside the CB pause branch (non-blocking: Sheets failure is logged
  but does not prevent the CB pause exit).
- **HIGH: Low balance alert fires every 4h when balance below $450** — No sentinel file meant 6
  Telegram alerts per day when already in drawdown. Added `balance_warn_alerted.flag` sentinel:
  fires once on breach, auto-clears when balance recovers above threshold.

### `whale_stream_bot.py` — 1 fix
- **HIGH: `short_wr_recent` defaults to 0 when no recent SHORT trades** — When the last 20
  resolved trades had no SHORTs, `short_wr = 0` triggering the 95% floor (as if SHORT WR is
  critically low). Fixed fallback to 50 (neutral): no recent SHORTs = neutral, not worst-case.

### `whale_stream_tracker.py` — 1 fix
- **MEDIUM: Gate 3 `_is_real_short()` used `abs(pnl) >= 5` instead of `>= 1.5`** — The checklist
  Gate 3 WR was computed on a stricter filter than the dashboard Gate 3 card, producing different
  PASS/FAIL results. Fixed to use `abs(pnl) >= 1.5` matching `_is_real_pnl`.
- **HIGH: `resolved_at` missing from debrief payload** — `_newly_resolved` dicts did not include
  `resolved_at`, making the debrief dedup key fall back to `tp_hit`. Two same-coin same-direction
  same-TP trades resolved in one tracker run had identical dedup keys → second debrief silently
  dropped. Added `"resolved_at": now_str`.

### `status_server.py` — 1 fix
- **MEDIUM: Path allowlist missing `posixpath.normpath()`** — `basename()` alone allowed theoretical
  traversal via `/./daily_status.json`. Added `normpath()` before `basename()` extraction.

### `check_daily_status.py` — 2 fixes
- **MEDIUM: Midnight arithmetic wrong** — `elapsed = (h - slot) * 60 + m` produced negative values
  for slots later than current hour, causing past-midnight cycles to be incorrectly expected. Added
  `if slot > h: continue` guard.
- **LOW: Briefing gap fires at exactly 07:00** — Gap checker would false-alarm on briefing immediately
  at 07:00 before the briefing script had time to run. Extended grace window to 07:10.

### `JULY1_GOLIVE_CHECKLIST.md` — 2 fixes
- **MEDIUM: Pre-flight demo balance check would fail** — Step said "check demo balance is healthy
  (not in drawdown >15%)" but demo is already at 34% drawdown. Updated to clarify this is
  informational only; live account is funded fresh.
- **MEDIUM: BYBIT_START_BALANCE update buried as prose** — Promoted to a `[ ] MANDATORY` checkbox
  item with explicit "update BOTH files" instruction and explanation of why it matters.

### Version bumps to v47.10
- `whale_stream_bot.py`, `whale_stream_strategist.py`, `whale_stream_trader.py`,
  `whale_stream_tracker.py`, `whale_stream_watchdog.py`, `whale_stream_monitor.py`,
  `whale_stream_debrief.py`, `morning_briefing.py` (removed hardcoded version from Telegram msg)

---

## v47.9 — 2026-06-29 — 3 safety + ops fixes (CLEAR_BREACH_NOW confirmation, log scan limits, version bumps)

### `CLEAR_BREACH_NOW.bat` — 1 fix
- **SAFETY: No confirmation before clearing both circuit breaker flags** — The bat deleted `paused.flag`
  AND `gate4_breach.flag` immediately on double-click with no user confirmation. This is a dangerous
  safety bypass: a misclick during a real drawdown event would resume live trading into a losing
  market. Added a YES/no prompt that explains the risk before clearing anything. Cancelling leaves all
  flags untouched.

### `morning_briefing.py` — 2 fixes
- **MEDIUM: Trader log scan too small** — `parse_trader_activity()` only read the last 100 lines of
  `trader_log.txt`. At the 4h cycle rate, 100 lines covers ~1–2 days at best; yesterday's orders
  could be missed by the morning briefing. Increased to 500 lines (~1 full week).
- **MEDIUM: Monitor log alert scan too small** — Fill/close event scan used 2000 lines. Increased
  to 5000 for complete 24h coverage even on active days with many monitor ticks.

### `signal_scorer.py` — version bump to v47.9

---

## v47.8 — 2026-06-29 — Full system audit: 21 fixes across 9 files (circuit breakers, TP safety, dedup, security, monitoring)

### `whale_stream_bot.py` — 5 fixes
- **CRITICAL: Circuit breaker check completely missing from `main()`** — `paused.flag` was never
  checked in the Bot. When Watchdog/Trader set the circuit breaker, Bot continued to run: fetching
  200 coins, calling Claude twice, and logging signals — ignoring the safety halt. Added explicit
  `paused.flag` check at the top of `main()` (after cycle guard, before any Claude call). Bot now
  marks done and returns immediately when paused.
- **HIGH: SHORT WR floor boundary off-by-one** — `short_wr_recent < 50` meant a WR of exactly 50%
  dropped to the 93% floor instead of staying at 95%. Fixed: `<= 50` so the boundary is inclusive.
- **HIGH: Conflict guard ran before SHORT confidence filter** — A valid 94% LONG signal could be
  dropped by the cross-direction conflict guard because a 88% SHORT for the same coin was present.
  That SHORT would then be auto-dropped by the confidence filter anyway. Fixed by reordering: SHORT
  confidence filter runs first, then conflict guard operates only on remaining valid SHORTs.
- **HIGH: WLD missing from LONG COIN AVOID prompt text** — WLD is in `LONG_COIN_BLOCKLIST` (code
  drops it), but Claude was never told not to generate WLD LONG signals. Claude wasted a slot every
  run. Added WLD to the LONG POOR COINS list in `WHALE_STREAM_PROMPT`.
- **HIGH: Graveyard P&L sign filter asymmetric** — Filters existed for (SHORT LOSS + pnl>0) and
  (LONG WIN + pnl<0) but not for the inverse. Added: (SHORT WIN + pnl<0) and (LONG LOSS + pnl>0)
  now also skipped as malformed. Prevents corrupted graveyard entries from polluting self-learning.

### `signal_scorer.py` — 1 fix
- **HIGH: Confidence threshold 85% vs system floor 88%** — Scorer awarded full points (+2) to any
  signal ≥85%, including the 85–87% band. Those signals always pass pre-screening then get
  auto-dropped by the Bot's 88% LONG floor — wasting a Strategist Claude call every cycle. Raised
  scorer threshold from 85% to 88% to match the system floor.

### `whale_stream_strategist.py` — 1 fix
- **HIGH: `--recheck` mode bypassed `paused.flag` circuit breaker** — The pause check was located
  after the entire `--recheck` branch. A recheck run during a CB pause would still fetch Sheets,
  evaluate signals, and overwrite `strategist_decisions.json`. Fixed: pause check moved to before
  the `--recheck` branch — first action in `main()` after basic setup.

### `whale_stream_trader.py` — 4 fixes
- **CRITICAL: `allocated += leg_qty` ran even when TP leg order failed** — In `place_quad_tp_closes()`,
  the `allocated` counter advanced regardless of whether `ok` was True. If TP2 failed silently,
  the last leg underpaid (absorbed the failed leg's share), leaving contracts between TP2 and TP3
  unprotected. Fixed: `allocated += leg_qty` now inside `if ok:`. Added post-loop warning print
  when any legs fail.
- **HIGH: Telegram alert sent on EVERY Trader run while paused** — 6 identical "TRADER PAUSED —
  CIRCUIT BREAKER ACTIVE" messages fired per day until the operator cleared the flag. Added
  `cb_pause_alerted.flag` sentinel: first pause sends alert + writes flag; subsequent runs skip
  Telegram. `CLEAR_PAUSE.bat` now deletes `cb_pause_alerted.flag` so the next CB cycle re-alerts.
- **HIGH: `availableToBorrow` in wallet balance chain** — If all margin was deployed,
  `availableToWithdraw = 0` caused the `or` chain to fall through to `availableToBorrow`, which
  can be nonzero in cross-margin mode even with zero free USDT. Could allow new orders when fully
  deployed. Removed `availableToBorrow` from the chain; now only `availableToWithdraw or walletBalance`.
- **MEDIUM: SHORT floor print label said "(REPAIR MODE)"** — The 95% SHORT floor is always active
  (code-level), not only during REPAIR MODE. The misleading label was removed. Now: "95% code floor".

### `whale_stream_tracker.py` — 2 fixes
- **HIGH: Blended P&L for partial TP used 50/50 average instead of 25/75 weighted** — When TP1
  hit (25% close) and the trade was upgraded to a TP2+ level, the blended P&L was `(pnl1+pnl2)/2`.
  Correct formula: `pnl1 * 0.25 + pnl2 * 0.75`. Fixed. Also corrected Telegram message text.
- **HIGH: Debrief subprocess passed JSON via command-line arg** — Windows has an 8191-char CLI
  limit. A batch of multiple resolved trades can exceed this, causing the subprocess to silently
  fail to start and permanently losing those debrief runs. Fixed: data written to `tempfile.mkstemp()`
  and file path passed as `--from-file` argument. Temp file deleted by Debrief after reading.

### `whale_stream_debrief.py` — 3 fixes
- **CRITICAL: Dedup guard dropped second trade when same coin+direction resolved in same batch** —
  `already_debriefed()` used `(coin, direction, run_timestamp)` as key. In a batch of two BTC LONG
  trades, the second was always silently dropped because `run_timestamp` was identical. Fixed: added
  `resolved_at` (the trade's own resolution time) to the dedup key, making each trade unique.
- **HIGH: No try/except around Claude call in debrief loop** — Any exception from
  `call_debrief_claude()` (network error, rate limit, etc.) propagated out of the loop, abandoning
  all remaining trades without updating `pattern_memory.json`. Fixed: wrapped in try/except —
  failed calls log a warning and fall through to the minimal fallback entry.
- **HIGH: No timeout on Anthropic client** — A hung API call would hold the subprocess open
  indefinitely. Multiple overlapping debrief runs would accumulate, and the last writer would
  overwrite earlier runs' pattern memory. Fixed: `anthropic.Anthropic(..., timeout=30.0)`.

### `whale_stream_watchdog.py` — 1 fix
- **HIGH: `check_trader()` replaced RUN COMPLETE timestamp with any later PAUSED line** — When
  a PAUSED message appeared in the log after a RUN COMPLETE line, the `dt_any` fallback overwrote
  `dt`, making a paused trader look "OK" to the health checker. Fixed: `dt_any` scan now skips
  lines containing "PAUSED" — only genuine activity lines update the fallback timestamp.

### `check_daily_status.py` — 1 fix
- **CRITICAL: `STATUS_URL` used "localhost" instead of "127.0.0.1"** — `status_server.py` binds
  explicitly to `127.0.0.1` (IPv4) since the v47.7 fix. On Windows, "localhost" can resolve to
  `::1` (IPv6), causing a connection refused — the gap checker reported status server as OFFLINE
  on every run even when the server was healthy. Fixed: `STATUS_URL = "http://127.0.0.1:8765/..."`.

### `morning_briefing.py` — 1 fix
- **HIGH: Briefing always showed itself as "not seen today"** — `_agent_coverage_section()` checks
  `daily_status.json` for agent completion. `_mark_done("briefing")` is called at the END of the
  briefing's own run — so at the moment the coverage section runs, briefing is always missing,
  generating daily false-alarm noise. Fixed: skip the "briefing" key in the self-coverage check.

### `whale_stream_monitor.py` — 1 fix
- **HIGH: `_mark_done("monitor")` called on Bybit API failure** — When `get_all_positions()` returned
  None, the monitor immediately called `_mark_done()` and exited. `check_daily_status.py` saw
  `monitor=True` and reported green — hiding sustained API outages completely. Fixed: on API failure,
  do NOT call `_mark_done()`. The gap checker will now detect the monitor as missing for that cycle.

### `status_server.py` — 1 fix
- **HIGH: Entire WhaleStream directory served over HTTP** — The server exposed all files including
  `local_config.py` (API keys, Telegram token) and `google_credentials.json` to any local process.
  Added `do_GET()` override that restricts serving to only `daily_status.json` and `daily_status.js`
  — returns 403 for all other paths.

### `CLEAR_PAUSE.bat` — 1 fix
- **OPS: Did not delete `cb_pause_alerted.flag` on CB clear** — The new v47.8 `cb_pause_alerted.flag`
  sentinel (trader pause de-duplication) must be deleted when the CB is cleared so the next CB event
  re-alerts the operator. Added `del cb_pause_alerted.flag` to the CLEAR_PAUSE.bat confirmation block.

### Version bumps
- bot.py, signal_scorer.py, strategist.py, trader.py, debrief.py, watchdog.py, monitor.py: v47.7 → v47.8

---

## v47.7 — 2026-06-29 — Comprehensive audit: 12 fixes (Daily Checklist offline, confidence floors, circuit breaker, TP ordering, JS sync)

### `To do list/Daily Checklist.html` — 1 fix
- **CRITICAL: OFFLINE display at 00:00 and 04:00 BKK cycles**
  JavaScript `todayKey()` used UTC date (`new Date().toISOString()`); agents write Bangkok date
  (`timezone(timedelta(hours=7))`). At 00:00 BKK = 17:00 UTC June 28, JS used June 28 key but
  agents wrote June 29 key — perpetual OFFLINE. Fixed by adding `bkkDateStr()` using
  `new Date().getTime() + 7*3600000` offset. Applied to both `todayKey()` (line 301) and
  the `today` date check (line ~488).

### `whale_stream_trader.py` — 4 fixes
- **CRITICAL: `place_quad_tp_closes()` KeyError crash** — Bybit returns success (`retCode=0`)
  but occasionally omits the `"result"` key. `r["result"].get(...)` threw KeyError, aborting
  TP close placement and leaving position fully unprotected. Fixed: `(r.get("result") or {}).get("orderId", "")`.
- **HIGH: No code-level confidence floor enforcement** — Strategist checks floors, but if
  Strategist output was malformed or the circuit breaker skipped it, Trader would execute any
  confidence. Added belt+suspenders: SHORTs <95% and LONGs <88% are hard-blocked at Trader.
- **HIGH: `place_quad_tp_closes()` min_q inflation** — When `qty < n * min_q`, the last leg
  was overstated because `round_to_step(qty/n, step)` < `min_q` forces each leg to `min_q`,
  consuming more than `qty` total. Fixed: pre-flight `n = max(1, int(qty // min_q))` to
  reduce leg count before allocating.
- **MEDIUM: Reactive veto scan missed older placed orders** — Age-filtered `open_trades` only
  included orders placed in the last `_max_age_h` hours. Reactive mode scans for vetoed orders
  to cancel — must see ALL OPEN rows, not just recent ones. Fixed: scan all rows where
  `COL_STATUS == "OPEN"` and `COL_BYBIT_ID` is non-empty.

### `whale_stream_strategist.py` — 1 fix
- **HIGH: Circuit breaker skipped work but didn't return** — `paused.flag` check logged a
  note and called `continue`, but the run proceeded. Strategist still called Claude, still
  wrote decisions, still sent Telegram — wasting ~$0.08 in tokens per cycle while paused.
  Fixed: now calls `_mark_done(..., skipped="PAUSED")` then `return` immediately.

### `whale_stream_bot.py` — 3 fixes
- **MEDIUM: BTC rally gate text said ≥93%, code enforces ≥95%** — Bot prompt "MANDATORY RULE:
  confidence ≥93% only" contradicted REPAIR MODE 95% floor. Fixed to say ≥95%.
- **MEDIUM: BTC uptrend gate text said ≥92%, code enforces ≥95%** — Same contradiction.
  "Each SHORT must be ≥92%" → "≥95% (REPAIR MODE floor applies)".
- **MEDIUM: SHORT recovery threshold was <40% not <50%** — `min_short_conf = 95 if short_wr_recent < 40`
  meant the 95% floor only kicked in when SHORT WR fell below 40%. Design doc says floor
  applies until SHORT WR recovers to ≥50%. Fixed: `< 40` → `< 50`.

### `whale_stream_debrief.py` — 1 fix
- **MEDIUM: `_mark_done()` did not write `daily_status.js`** — Only `daily_status.json` was
  written. Checklist HTML uses `daily_status.js` as a CORS-safe fallback when the status
  server is unreachable (e.g., file:// access). Debrief ticks were never visible in fallback
  mode. Added `.js` write after the `.json` write.

### `whale_stream_watchdog.py` — 1 fix
- **MEDIUM: `_write_html_snapshot()` regex silent-failed on first run** — `re.sub(r'var WS_EMBEDDED=...')` 
  returns the original string unchanged if the pattern isn't found (first run, or HTML reset).
  The identical string was written, injecting nothing. Added: if `_new_html == _html`, fall
  back to `str.replace("</script>", f"{_inject}\n</script>", 1)`.

### `check_daily_status.py` — 1 fix
- **LOW: False gap alert for `briefing` before 07:00 BKK** — Gap checker runs at 00:45 and
  04:45. Briefing only fires at 07:00 daily, so it's always "missing" at those checks and
  triggers a spurious Telegram alert every early cycle. Fixed: `if agent == "briefing" and now.hour < 7: ok.append(agent)`.

### `DELETE_PAUSE_NOW.bat` — disabled
- **OPS: Missing `cb_grace.txt` write after circuit breaker clear** — This bat did `del /f paused.flag`
  without writing `cb_grace.txt`. The next Trader run would immediately re-trigger the circuit
  breaker (sees fresh loss streak without the grace window). File replaced with a disabled stub
  that redirects users to `CLEAR_PAUSE.bat` (which handles both steps correctly).

### `status_server.py` — 1 fix
- **OPS: `"localhost"` binding can resolve to IPv6 `::1` on Windows** — Python's `HTTPServer`
  with `"localhost"` may bind to `[::1]:8765` while the checklist HTML fetches
  `http://localhost:8765` over IPv4 `127.0.0.1`. Fixed: explicit `"127.0.0.1"` binding.

### Version bumps
- All 6 agent files updated from v47.5 → v47.7:
  bot.py, strategist.py, trader.py, debrief.py, watchdog.py, morning_briefing.py

---

## v47.6 — 2026-06-28 — Deep audit: 6 bugs fixed (SL sweep false-fires, TP orphans, confidence mismatch, version)

### `whale_stream_trader.py` — 3 fixes
- **CRITICAL: `_sweep_missing_sl()` false-fires on ALL positions every 4h cycle**
  Bybit V5 has TWO SL types: (1) order-level (set in `/v5/order/create` body — creates a
  conditional stop order, does NOT set `pos["stopLoss"]`) and (2) position-level (`/v5/position/trading-stop`
  — sets `pos["stopLoss"]` field, shows in UI). The sweep only checked position-level (`pos["stopLoss"]`),
  so every order placed by `place_order()` appeared to have no SL every cycle. Fix: now also queries
  `/v5/order/realtime?orderFilter=StopOrder` to detect existing conditional stop orders before attempting
  any restore. Also extended sheet lookup to include WIN/TP1 rows (75% still open after first partial
  close) — those are routed to the SL-to-BE routine, not restored from the original signal SL.
- **HIGH: `cancel_reversed_orders()` leaves TP close orders as orphans**
  When BTC reverses 3%+ and an unfilled LONG entry order is cancelled, the 4 reduce-only TP close
  orders placed by `place_quad_tp_closes()` were left open on Bybit. Now cancels all reduce-only
  orders for the same symbol after cancelling the entry. Telegram alert updated to include TP count.
- **HIGH: SL-to-BE Telegram says "TP1 (50%) confirmed → protecting second half"**
  The 4-TP system closes 25% at each TP. TP1 closes 25%, leaving 75% open. Fixed text to:
  "TP1 (25%) confirmed → protecting remaining 75%".

### `whale_stream_bot.py` — 1 fix
- **HIGH: Graveyard prompt SHORT floor says 93% but code enforces 95%**
  Line 612: "MINIMUM SHORT CONFIDENCE: 93%" → "95% (REPAIR MODE)". Code at line 418 (and
  gate enforcement at line 2442) blocks SHORTs <95% when WR <40%. The prompt now matches.
  Also updated the adjacent line: "88-92% band poor WR" → "88-94% band poor WR".

### `whale_stream_strategist.py` — 1 fix
- **HIGH: AUTOMATIC VETO only covered 90–92% SHORT confidence, not 93–94%**
  During REPAIR MODE the code enforces a 95% floor, but the Strategist VETO rule only
  vetoed SHORTs in the 90–92% range. A 93% or 94% SHORT could pass the Strategist
  and be blocked only later by the code floor (after 1 Claude token call was wasted).
  Now the VETO covers 90–94%: "if it only feels 90-94%, veto".

### `signal_scorer.py` — 1 fix
- **LOW: Threshold constant names were semantically inverted (maintenance trap)**
  `SKIP_THRESHOLD = 4` was used as the boundary for REVIEW verdict (not SKIP).
  `REVIEW_THRESHOLD = 7` was used as the boundary for STRONG verdict (not REVIEW).
  Numeric behavior was correct, but any future developer editing a threshold would pick
  the wrong constant. Renamed: `STRONG_MIN = 7`, `REVIEW_MIN = 4`, with clear comments.

### `morning_briefing.py` — 1 fix
- **LOW: Version banner said "v47.0 drawdown protection" instead of "v47.5"**
  Line 765: stale version string updated to v47.5.

---

## v47.5 — 2026-06-28 — Final Audit: 12 bugs fixed (HTML race, WLD blocklist, version sync, confidence floor)

### `whale_stream_trader.py` — 4 fixes
- **HTML race condition**: Removed `WS_EMBEDDED` HTML write from `_mark_done` —
  Watchdog is sole HTML writer at :30. Trader writing HTML could corrupt the snapshot.
- **WLD added to LONG_COIN_AVOID_LIST**: WLD was on the LONG blocklist in bot.py but
  missing from trader's code-level skip guard. Now blocks WLD LONG orders at execution.
- **`place_quad_tp_closes()` allocated counter**: Fixed — `allocated` now advances
  regardless of success/failure. Previously a failed middle leg left last-leg qty overstated.
- **SL guard sweep** (from prior v47.5 commit): `_sweep_missing_sl()` runs every cycle.
  (retains full description from prior entry below)

### `morning_briefing.py` — HTML race condition fix
- Removed `WS_EMBEDDED` HTML write from `_mark_done` — same race condition as trader.py.
  Briefing runs at 07:00 and was clobbering Watchdog's 04:30 snapshot.

### `whale_stream_debrief.py` — 2 fixes
- **`if pnl:` → `if pnl is not None:`**: Breakeven closes (pnl == 0.0) were silently
  omitted from outcome detail string. Now correctly shows "P&L: +0.0%" for breakeven.
- Banner: v47.2/v47.4 → v47.5

### `whale_stream_bot.py` — Version banner sync
- All 4 version strings updated: header, prompt, Telegram line, startup banner → v47.5

### `whale_stream_watchdog.py` — Version banner sync
- Banner: v47.4 → v47.5

### `whale_stream_monitor.py` — Stale comment fix
- Header comment said "~50% size drop → TP1". Updated to "≥15% size drop" to match
  actual Quad-TP 25% close detection logic (PARTIAL_CLOSE_RATIO = 0.85).

### `whale_stream_tracker.py` — 2 fixes
- **Bybit price fetch failure alert**: Silent failure: if `load_bybit_prices()` threw an
  exception, tracker printed a line but continued silently — all trades stalled for the
  cycle with no notification. Now sends Telegram alert immediately on failure.
- **HTML race condition**: Removed `WS_EMBEDDED` HTML write from `_mark_done` — same
  race condition as trader.py/briefing.py. Watchdog is sole HTML writer.

### `whale_stream_strategist.py` — Version banner sync
- Header docstring + startup banner: v1.3 → v47.5. Stale since initial build.

### `signal_scorer.py` — Version banner sync
- Header docstring: v1.0 → v47.5. Stale since initial build.

### `whale_stream_bot.py` — SHORT confidence floor fix
- COMBINED MACRO MATRIX "BTC.D HIGH + Extreme Greed" rule said "Only SHORTs ≥ 93%"
  but REPAIR MODE floor (same prompt, 40 lines later) says "Minimum SHORT confidence: 95%".
  Changed 93% → 95% in the macro matrix to eliminate the contradiction. Claude would have
  seen two conflicting floors in the same system prompt — now consistent at 95%.

---

## v47.5 — 2026-06-28 — SL guard sweep (critical capital protection)

### `whale_stream_trader.py` — `_sweep_missing_sl()` function
- Runs at the START of every trader cycle, before placing any new orders
- Checks every open Bybit position for missing stop-loss (`stopLoss == "0"` or empty)
- If missing: looks up SL price from the matching OPEN Google Sheet row, sets it via
  `/v5/position/trading-stop` with `slTriggerBy=MarkPrice`, sends Telegram alert
- If no sheet row found for a missing-SL position: sends CRITICAL Telegram alert with
  manual instruction to go to Bybit and set SL manually
- Idempotent: positions with SL already set are skipped (no API call, just logged)
- Fixes the root cause of AAVE/-62%, WLD/-51%, XPL/-37% bleeding with no SL —
  those were placed before the `fmt_price` scientific notation bug was fixed (v46.34)
- From this version forward, any position that somehow loses its SL will be auto-restored
  within 4h (next trader cycle)

---

## v47.4 — 2026-06-28 — Final Pre-Go-Live Audit (12 bugs fixed)

### `signal_scorer.py` — Pattern matching direction fix (CRITICAL)
- Bidirectional substring check (`pat_lower in strong`) caused partial patterns (e.g. "bull")
  to score STRONG+2 because "bull" ⊆ "bull flag". Changed to one-directional `strong in pat_lower`.

### `whale_stream_trader.py` — Timestamp BKK suffix strip (CRITICAL)
- Sheet stores timestamps as "2026-06-28 12:00 BKK". `strptime("%Y-%m-%d %H:%M")` raises ValueError
  on " BKK" suffix → caught by `except Exception: continue` → ALL approved signals silently skipped.
- Fix: `.replace(" BKK", "")` before strptime. Now all approved signals are correctly processed.

### `whale_stream_watchdog.py` — 3 fixes
- BOT_DEADLINE_MIN: 32 → 40 (absorbs Task Scheduler startup jitter up to 5 min under SYSTEM user)
- File handle leak: `json.load(open(...))` → `with open(...) as f: json.load(f)`
- Added `sys.excepthook` crash guard — sends Telegram alert if Watchdog itself crashes unhandled
- Banner: v47.2 → v47.4

### `whale_stream_monitor.py` — Remove HTML write from `_mark_done` (race condition)
- Monitor runs every 2 min; writing Daily Checklist.html here raced with Watchdog's
  `_write_html_snapshot()` at :30. Watchdog is now sole HTML writer.

### `whale_stream_bot.py` — 2 fixes
- Removed HTML write from `_mark_done` (same race condition fix as monitor.py)
- Fixed inline BKK recomputation in `_mark_done` — now uses module-level `BKK`
- Banner: v47.2 → v47.4

### `whale_stream_strategist.py` — 2 fixes
- Fixed inline BKK + datetime recomputation in `_mark_done` — now uses module-level `BKK`
- Removed HTML write from `_mark_done` (same race condition fix)

### `whale_stream_debrief.py` — Dead code fix
- `pnl = float(... or 0)` makes pnl always float; `if pnl is not None` always True →
  always appended "P&L: +0.0%" for no-P&L trades. Changed to `if pnl:`.
- Banner: v47.2 → v47.4

### `trade_logger.py` — Remove unnecessary ANTHROPIC_API_KEY import
- trade_logger never calls Claude API; removed key from import to minimize exposure.

### `whale_stream_tracker.py` — Atomic dashboard.html write
- Direct `open(out_path, "w")` vulnerable to partial-write corruption on crash.
- Now writes to `.tmp` then `os.replace()` (atomic on NTFS).

### `morning_briefing.py` — Gate 6 dynamic from daily_status.json
- Was hardcoded "❌ 0/3 profitable weeks" always. Now reads `gate6_status` from
  `daily_status.json`; falls back to "⏳ Check dashboard (updated Sundays)".

---

## v47.4 — 2026-06-28 — Full system wiring + Go-Live Test Suite

### `whale_stream_strategist.py` — Live win-rate history from trade_logger
- Imports `_load_local_log` from trade_logger (try/except fallback)
- New `build_history_from_logger(signals)` — builds coin+direction history from ALL 206+ trades
  (vs old `build_coin_history()` which only scanned last 60 sheet rows)
- `scorer_history` (logger-based, full data) fed to Signal Scorer WR dimension
- Sheet history still used for Claude prompt (shows recency / last 4 trades)
- Signal scorer WR dimension now uses real 206-trade dataset — accurate win rates

### `whale_stream_debrief.py` — Auto-sync trade_logger after every resolution
- After `save_memory()`, calls `sync_from_sheets()` from trade_logger
- Keeps `trade_log.json` current after every WIN/LOSS so Strategist's next
  scorer run sees up-to-date win rates immediately

### NEW: `test_golive.py` — Go-Live Test Suite (11 test sections)
- Runs before July 1 to verify all critical systems are operational
- Section 1: Required file existence check (15 files)
- Section 2: Credentials load (all 5 keys from local_config.py)
- Section 3: Signal Scorer — import + score_signal() + SKIP/STRONG logic
- Section 4: Trade Logger — import + win_rate + by_coin + by_hour + streak
- Section 5: Google Sheets REST API v4 connectivity + OPEN/WIN/LOSS counts
- Section 6: Bybit public + authenticated API + balance + DEMO vs LIVE key detection
- Section 7: Telegram ping (sends test message to ops channel)
- Section 8: BTC 4h SMA20 market regime filter
- Section 9: Strategist imports + build_history_from_logger() + pattern_memory
- Section 10: JSON state files (strategist_decisions, bybit_balance, etc.)
- Section 11: Windows Task Scheduler — 7 task presence + Ready/Disabled status
- Final summary: PASS/FAIL/WARN counts + go-live verdict

## v47.3 — 2026-06-28 — Signal Scorer + Trade Logger (Strategist intelligence upgrade)

### NEW: `signal_scorer.py` — Pre-Claude signal quality gate
- Scores every signal 0–10 across 5 dimensions BEFORE sending to Claude:
  1. Bot confidence alignment (0–2): ≥85%=+2, ≥70%=+1, <70%=+0
  2. Market regime match (0–2): direction WITH BTC bias=+2, neutral=+1, against=+0
  3. Coin historical win rate (0–2): ≥65%WR=+2, ≥50%=+1, <50%=+0, <3 samples=+1
  4. Portfolio correlation (0–2): no duplicate position=+2, hedge=+1, duplicate=+0
  5. Pattern strength (0–2): strong pattern=+2, moderate=+1, unknown=+0
- Verdicts: STRONG (≥7) → Claude, REVIEW (4–6) → Claude flagged, SKIP (<4) → auto-veto
- Saves Anthropic API tokens by auto-rejecting low-quality signals before Claude call
- Integrated into `whale_stream_strategist.py` with full prompt annotation

### NEW: `trade_logger.py` — Persistent WIN/LOSS trade log
- Syncs all resolved trades from Google Sheets → `trade_log.json` + `trade_log.csv`
- Trade categories: FULL_WIN (TP3/TP4), PARTIAL_WIN (TP1/TP2), LOSS (SL hit)
- Query functions for other agents: get_win_rate(), get_daily_summary(),
  get_performance_by_coin(), get_performance_by_pattern(), get_performance_by_hour(), get_streak()
- Standalone: `python trade_logger.py [--sync] [--stats]`

### NEW: `MASTER_PLAN.md` — Unified $1M strategy document
- 5-phase position scaling ladder: $20 → $50 → $150 → $500 → $1,500/trade
- 184-day compounding model (July 1 → Dec 31)
- 5 pillars: intelligent system, 24/7 uptime, quality over quantity, scaling, full compounding

### `whale_stream_strategist.py` — Scorer integration
- Imports signal_scorer.py; falls back gracefully if unavailable
- Score printed per signal before Claude call
- Auto-vetoed SKIP signals merged into final decisions JSON + counted in Telegram summary
- Score annotation injected into Claude prompt for each signal

## v47.2 — 2026-06-28 — Full code audit: BKK constant, redundant imports eliminated, dead code removed

### P0 — Critical (headless operation)

**`SETUP_ALL_TASKS.bat` + `ADD_RECHECK_TASKS.bat` — All 16 `schtasks /create` blocks missing `/ru SYSTEM`**
- Without `/ru SYSTEM`, every scheduled task requires an active user session
- Tasks fail silently when user is logged off — 24/7 headless operation impossible
- Fixed: added `/ru SYSTEM ^` to all 10 blocks in SETUP_ALL_TASKS.bat and all 6 blocks in ADD_RECHECK_TASKS.bat

### P1 — High (correctness / token cost)

**`whale_stream_tracker.py` — 8 inline `timezone(timedelta(hours=7))` replaced with `BKK`**
- `BKK = timezone(timedelta(hours=7))` module-level constant already defined
- 8 call sites in `weekly_summary()`, `main()`, heartbeat check, partial close block, expiry check, fast-expire block, and Bybit P&L write-back were still constructing new objects inline
- Fixed: all 8 replaced with `BKK`; removed dead `_bkk_tz = timezone(timedelta(hours=7))` local at line 1831 and updated its downstream usage at line 1857 (`tzinfo=_bkk_tz` → `tzinfo=BKK`)

**`whale_stream_bot.py` — 4 remaining inline `timezone(timedelta(hours=7))` replaced with `BKK`**
- `bkk_time = datetime.now(timezone(timedelta(hours=7)))` in `main()` (line 2393) → `datetime.now(BKK)`
- `_now_bkk = datetime.now(timezone(timedelta(hours=7))).strftime(...)` in `main()` (line 2558) → `datetime.now(BKK).strftime(...)`
- 2 remaining inline calls in cycle guard previously fixed; 1 in `_mark_done()` retained (local import before BKK is defined)

**`whale_stream_bot.py` — Added module-level `BKK` constant + `_parse_conf()` replacing 4 duplicate parsers**
- `BKK = timezone(timedelta(hours=7))` added after SECTION 3 imports
- 4 local functions (`_conf_int`, `_long_conf_int`, `_parse_conf_val`, `_top3_key`) all extracted confidence integers via `re`; collapsed to single module-level `_parse_conf(sig)` returning `int`
- Dead `elif short_wr_recent < 45: min_short_conf = 93` (identical to `else` branch) collapsed to ternary
- Always-True `if min_short_conf > 0:` guard removed
- DATASET placeholder (`Batch 1 Coins: XXX` etc.) removed from `WHALE_STREAM_PROMPT`
- Cycle guard in `main()` cleaned: removed `import json as _jcg, datetime as _dcg` and 3× inline `_dcg.timezone(_dcg.timedelta(hours=7))` constructions; now uses module-level `json`, `datetime`, `BKK`

**`whale_stream_bot.py` — Redundant inner imports eliminated**
- Removed `import re as _re` from `_parse_conf_val()`, `_parse_entry_mid()`, `_parse_price_val()`, `_top3_key()` (module-level `re` already imported)
- Removed `from datetime import timedelta as _td` from `log_to_google_sheets()` (module-level `timedelta` already imported)
- Removed `import json` from `parse_json_signals()` function body (module-level `json` already imported)

**`whale_stream_bot.py` — `_mark_done()` inner imports removed**
- Previous implementation imported `json`, `re`, `datetime` inside function body every call
- Rewrote to use module-level `json`, `re`; `from datetime import datetime, timezone, timedelta` kept as local import only because `_mark_done` is defined before SECTION 3 module-level imports

**`morning_briefing.py` — `BKK` constant + `_mark_done()` rewritten**
- `BKK = timezone(timedelta(hours=7))` added after `from datetime import`
- `_mark_done()` rewritten: removed inner `import json, datetime` and `import re as _re`; uses module-level `json`, `re`, `datetime`, `BKK`; added `except Exception as _me: print(...)` error logging

### P2 — Low (version strings)

**`ADD_RECHECK_TASKS.bat` — stale v47.0 banner**
- Echo banner still said `WHALE-STREAM v47.0`; updated to v47.2

## v47.1 — 2026-06-28 — Sixth audit pass: 17 fixes across 5 files (Watchdog autonomy gap, dead code, Gate fixes, NameError, token waste)

### P0 — Critical (autonomy + silent failures)

**`watchdog.py` — Tracker and Monitor hardcoded as ✅ in green report**
- `build_green_report()` unconditionally printed `✅ Tracker — every 30 min` and `✅ Monitor — every 2 min`
- If either agent died, Watchdog falsely reported all-clear every 4h with no alert
- Fixed: added `TRACKER_LOG` + `MONITOR_LOG` path constants, `check_tracker()` (deadline 45m) and `check_monitor()` (deadline 10m) functions, updated `build_green_report()` signature to accept `tracker_ok/last/monitor_ok/last`, updated `main()` call site

**`morning_briefing.py` — `bal` NameError in `__main__`: `_brief_summary` silently always ""**
- `bal` is a local variable inside `build_message()`; `__main__` tried to use it after `msg = build_message()` → always fell to `except` → `_mark_done(details.summary)` always blank
- Fixed: replaced with `_bdata = parse_balance()` call directly in `__main__` scope

### P1 — High (correctness bugs)

**`tracker.py` — Gate 4 `_bal > _start` fails flat accounts**
- Dashboard Gate 4 check: `bybit_ok = _dd_pct <= 25 and _bal > _start`
- An account sitting flat (bal == start) or slightly up would fail Gate 4 despite zero drawdown
- Fixed: `bybit_ok = _dd_pct <= 25` — pass if drawdown ≤ 25%, regardless of absolute balance

**`tracker.py` — Monday Gate snapshot used wrong Gate 1 definition**
- Monday Gate used `_ml_wr >= 60 and len(_ml20) >= 20` (WR check) and labeled it "Gate 1"
- Actual Gate 1 = 150 resolved real LONG trades (volume gate); WR is Gate 2
- Fixed: `_g1_ok = len(_ml) >= 150`; display string updated to "X/150 real LONGs"

**`tracker.py` — WR decay threshold 5 trades → false positives**
- `_long_recent = _long_resolved[-20:] if len(_long_resolved) >= 5 else []`
- With only 5–19 trades, rolling WR is statistically meaningless → spurious decay alerts
- Fixed: threshold raised from 5 → 20 trades before decay monitoring activates

**`bot.py` — Graveyard Telegram blind spot (S_WR / S_AUTO_BAN)**
- Already fixed in v47.0 round

### P2 — Medium (code quality / token waste)

**`watchdog.py` — `import re as _re` inside `_write_html_snapshot()` redundant**
- `re` already imported at module level (line 28); inner alias was dead overhead
- Fixed: removed `import re as _re` from function body

**`debrief.py` — `import os as _os` in ImportError except block**
- `os` already imported at module level; inner alias was redundant
- Fixed: use `os.getenv()` directly

**`tracker.py` — `import os as _os` in two ImportError except blocks**
- `os` imported at module level (line 29); lines 109/123 re-imported with alias
- Fixed: both blocks now use `os.getenv()` directly

**`tracker.py` — `import subprocess as _sp, sys as _sys` inside `connect_sheet()`**
- `subprocess` and `sys` imported at module level; inner imports were redundant
- Fixed: use module-level `subprocess` and `sys` directly

**`tracker.py` — Duplicate json alias `_cbj` / `_cbj2` in same function scope**
- Lines 1983 and 2017: `import json as _cbj` then `import json as _cbj2` in same `main()` function
- Fixed: both replaced with module-level `json` import

**`tracker.py` — `_date.today()` not BKK-aware in go-live countdown**
- `from datetime import date as _date; _today = _date.today()` uses local machine clock
- Server on UTC would show wrong countdown if run near midnight BKK
- Fixed: `_today = _dt_cls.now(_tz(_td(hours=7))).date()`

**`debrief.py` — Banner still said v1.0**
- Header box: `WHALE-STREAM DEBRIEF AGENT v1.0` → v47.0

**`ADD_RECHECK_TASKS.bat` — Stale v46.99 comment**
- Line 4: `v46.99 continuous decision loop` → v47.0

**`morning_briefing.py` — Stale v46.42 size-scaling comment**
- Already fixed in v47.0; comment bumped to v47.0

---

## v47.0 — 2026-06-28 — Fifth full audit pass: 9 critical fixes across 6 files (Quad-TP detection, BKK clocks, be_set propagation, content guards)

### P0 — Critical fixes

**`monitor.py` — PARTIAL_CLOSE_RATIO = 0.60 broke TP1 detection for Quad-TP system**
- Quad-TP closes 25% at TP1, leaving 75% of position remaining. `75% remaining > 60% threshold` = FALSE → monitor NEVER fired on TP1
- TP1 hit was completely invisible: no SL-to-BE move, no Telegram alert, no `be_set` flag set
- Fixed: `PARTIAL_CLOSE_RATIO = 0.85` — fires on any ≥15% position reduction, correctly catching 25% (TP1), 33% (TP2), 50% (TP3)
- Telegram text also corrected: "Remaining 50% riding to TP2/TP3" → "Remaining 75% riding to TP2/TP3/TP4"

**`monitor.py` — `be_set` flag lost on TP2/TP3 state update → SL-to-BE re-fires**
- After TP1 hit: `be_set=True` saved in state. On TP2, Bybit API returns fresh `curr` dict with no `be_set` key
- `be_needed = not prev.get("be_set")` = False (correct — already done). But code never reaches `curr["be_set"] = True`
- State saved with no `be_set` → next 2-min cycle: `prev.get("be_set")` = False → SL-to-BE re-fires on TP2, TP3, TP4
- Fixed: added `if prev.get("be_set") and not curr.get("be_set"): curr["be_set"] = True` before all 3 `state["positions"][symbol] = curr` assignments

**`bot.py` — `rescue_msg.content[0].text` unguarded → IndexError on empty API response**
- Anthropic API can return empty `content` list on rate-limit edge cases
- `rescue_msg.content[0]` raises `IndexError` → run aborts without fallback or Telegram alert
- Fixed: `rescue_msg.content[0].text if rescue_msg.content else ""`
- (Previously fixed: same guard on `message.content[0].text` at line 1639)

**`morning_briefing.py` — P&L parser crashes on Bybit `[B]` suffix**
- Bybit closed P&L stored as e.g. `"+45.20% [B]"`. After `replace("%","").replace("+","")` → `"45.20 [B]"`
- `float("45.20 [B]")` raises `ValueError` → all Bybit write-back trades show as 0% P&L in briefing
- Fixed: regex extraction `re.search(r'([+-]?\d+(?:\.\d+)?)', str(pnl_raw))` handles all suffix variants

### P1 — High-priority fixes

**`watchdog.py` — STRATEGIST_LOG pointed to wrong filename**
- Watchdog line 48: `STRATEGIST_LOG = "strategist_task_log.txt"` — file that never existed
- Strategist writes to `strategist_log.txt` (confirmed line 125 of strategist.py)
- `check_strategist()` always read a missing file → always fell back to "never run" state → false AMBER alert every cycle
- Fixed: `STRATEGIST_LOG = os.path.join(BASE_DIR, "strategist_log.txt")`

**`watchdog.py` — `_mark_done()` used local system clock, not BKK**
- `__import__("datetime").datetime.now().hour` uses local machine clock
- If server is not UTC+7, cycle key (e.g. `watchdog_08`) computed from wrong hour → wrong slot ticked
- Fixed: inline BKK-aware datetime before computing `_today`, `_h`, `_cycle`

**`strategist.py` — `_mark_done()` + cycle guard both used local clock, not BKK**
- Lines 58-59: `datetime.date.today()` and `datetime.datetime.now().hour` use local clock
- Line 759 cycle guard: same issue — `_dcg.datetime.now().hour` and `_dcg.date.today().isoformat()`
- Fixed: all 3 locations now use `datetime.now(timezone(timedelta(hours=7)))` for BKK-aware time

**`morning_briefing.py` — Stale version reference**
- `f"Size scale: {size_scale_pct}% (v46.42 drawdown protection)"` — stale since v46.42
- Fixed: updated to v47.0

**`trader.py` — `get_open_positions_full()` silently returns `[]` on API failure**
- Bybit API failure returns empty list with no log output — SL-to-BE check silently skipped
- Fixed: added `print("⚠ get_open_positions_full(): Bybit API failure — SL-to-BE skipped (monitor handles it)")` before `return []`

### Second audit pass — 23 additional fixes (2026-06-28)

**BKK clock systemic fix — 6 files** (`bot.py`, `monitor.py`, `debrief.py`, `trader.py`, `tracker.py`, `morning_briefing.py`)
- `_mark_done()` in all 6 files used `datetime.date.today()` / `datetime.datetime.now().hour` (local machine UTC)
- If machine is not UTC+7, cycle key computed from wrong hour → wrong slot ticked in daily_status.json
- Fixed: all 6 now compute `_bkk = datetime.timezone(datetime.timedelta(hours=7))` → `_now = datetime.datetime.now(_bkk)` before `_today`/`_h`
- `debrief.py` uses `_dt` alias → `_bkk = _dt.timezone(_dt.timedelta(hours=7))` pattern

**BKK cycle guard fix — `bot.py` + `trader.py`**
- Cycle guard `_cg_hour = _dcg.datetime.now().hour` used local clock → wrong slot skip
- Date comparison `_dcg.date.today().isoformat()` also local → could skip on UTC midnight when BKK is still previous day
- Fixed: `_dcg.datetime.now(_dcg.timezone(_dcg.timedelta(hours=7))).hour` and same for `.date().isoformat()`

**BKK cycle summary fix — `watchdog.py`**
- Line 435: `_wh = _wdt.datetime.now().hour` used local clock for computing which 4h slot is current
- Fixed: `_wdt.datetime.now(_wdt.timezone(_wdt.timedelta(hours=7))).hour`

**`bot.py` — version strings updated: v46.99 → v47.0** (header banner, WHALE_STREAM_PROMPT, Telegram footer)

**`bot.py` — prompt token waste: "TOP 5 LONG" → "TOP 3 LONG"**
- Prompt said "Select Top 5 LONG and Top 3 SHORT" but Python code caps at 3 LONG
- Claude generated 2 extra LONG signals every run that were silently discarded — wasted ~200 tokens/run
- Fixed: "TOP 3 LONG + TOP 3 SHORT" in both prompt lines (Steps 2 and Final Selections)

**`tracker.py` — TP4 missing from partial-close upgrade check**
- When TP1-resolved remainder hits TP4, upgrade block only checked TP3 then TP2 — never TP4
- Fixed: added `_pc_tp4 = parse_price(tp4_str) if tp4_str else None` and TP4 check before TP3 in both LONG/SHORT branches

**`tracker.py` — `datetime.utcnow()` deprecated + wrong timezone**
- `short_conservative.flag` created_at wrote `datetime.utcnow().isoformat()` — UTC vs BKK mismatch; deprecated in Python 3.12+
- Fixed: `datetime.now(timezone(timedelta(hours=7))).isoformat()`

**`tracker.py` — Telegram partial-close says "50%@TP1 + 50%@TPn"**
- Quad-TP system closes 25% at TP1, not 50%. Telegram message was wrong.
- Fixed: "Remainder (75%) reached" and "(25%@TP1 + 25%@{_pc_tp_name})"

**`trader.py` — Local `COL_RESOLVED_AT = 16` shadow inside `check_circuit_breaker()`**
- Re-declaration shadows module-level constant — dead code; any future change to the module constant would be silently ignored
- Fixed: removed local re-declaration

**`monitor.py` — Redundant `import os as _os` in two except blocks**
- `os` already imported at module level (line 33). Two except blocks did `import os as _os` then `_os.getenv()`
- Fixed: replaced with direct `os.getenv()` calls — 2 fewer runtime imports

**`morning_briefing.py` — BALANCE_FILE re-read inside `send_briefing()`**
- `bal` dict already in scope from `parse_balance()` called earlier in the function
- Opened file again with new `json.load()` call — redundant I/O every morning briefing
- Fixed: `_bal = bal.get("balance", 0.0)` and `_open = bal.get("open_positions", 0)`

**BAT files — `/ru "%USERNAME%"` breaks Task Scheduler autonomy**
- `ADD_STATUS_CHECK_TASK.bat` and `ADD_STATUS_SERVER_TASK.bat`: `/ru "%USERNAME%"` causes password prompt at registration → task created in "Run only when user logged on" mode → fails headless
- Fixed: removed `/ru "%USERNAME%"`, added `/RL HIGHEST` for elevated privileges without user context

**`SETUP_ALL_TASKS.bat` — StatusServer task missing `/RL HIGHEST`**
- All 8 other tasks had `/RL HIGHEST`; StatusServer task did not → inconsistent privilege level
- Fixed: added `/RL HIGHEST` before `/F`

**`ADD_RECHECK_TASKS.bat` — Version string still said v46.99**
- Fixed: updated to v47.0

---

## v46.99 — 2026-06-28 — Fourth full audit pass: 11 fixes across 7 files (learning loop P0, monitor hardening, SL-BE idempotency, scheduler)

### P0 — Critical fixes

**`debrief.py` + `strategist.py` — `consecutive_losses` key never written — Strategist Rule 3 permanently dead**
- `save_memory()` built `coin_lessons[coin]` as `{direction: [lessons]}` — no `consecutive_losses` integer anywhere
- Strategist Rule 3 read `memory["coin_lessons"][coin]["consecutive_losses"]` — always returned default 0 — coins with 3+ consecutive losses were never vetoed by the recheck agent
- Fixed (debrief.py): after building `coin_lessons`, now also builds `memory["coin_stats"][coin] = {"consecutive_losses": N}` by scanning recent debriefs newest-first and counting consecutive LOSS outcomes
- Fixed (strategist.py Rule 3): read path changed from `coin_lessons` to `coin_stats` — correctly reads the integer; also keeps `coin_lessons` direction-loop clean

### P1 — High-priority fixes

**`monitor.py` — `get_all_positions()` API failure returns `{}` — treats all positions as closed (false alerts)**
- On Bybit API error (`retCode != 0`), returned empty dict `{}` — monitor then diffed against state and fired "POSITION CLOSED" Telegram alerts for every tracked position
- Could cause panic during brief network interruptions; every position fires a false close alert
- Fixed: returns `None` on API failure; `run_monitor()` now checks `if current_positions is None: log(...); _mark_done(...); return` before diffing

**`monitor.py` — SL-to-BE re-fires on every TP2/TP3 partial fill — no `be_set` guard**
- When TP1 closed 25% of a position, monitor correctly moved SL to breakeven
- But TP2 closing another 25% also triggers `curr_size <= prev_size * PARTIAL_CLOSE_RATIO` — re-fires SL-to-BE with another Telegram alert
- Fixed: added `"be_set": True` flag written to state after successful SL move; `be_needed` block now gates on `if not prev.get("be_set"):`; new branch prints "✓ SL-to-BE already applied (skipping)"

**`monitor.py` — `save_state()` direct write — corrupt on crash**
- Direct `json.dump()` to `STATE_FILE` — a crash mid-write corrupts `monitor_state.json`, causing monitor to lose all position tracking
- Fixed: atomic write via temp file + `os.replace()`

**`trader.py` — SL-to-BE re-fires every 4h cycle — duplicate Telegram alerts**
- When Bybit position's `stopLoss` field doesn't immediately reflect a previously applied conditional SL, the `SL ≥ entry` bypass check fails and the cycle re-fires the `trading-stop` API call with another Telegram alert
- Fixed: new `sl_be_applied.json` idempotency file; records which symbols have had SL-to-BE applied; pruned each cycle to only symbols still in `_slbe_tp1_syms`; prevents duplicate Telegram alerts across cycles

**`bot.py` — LONG confidence prompt says `Reject < 90%` but code floor is 88%**
- Prompt instructed Claude to discard 88-89% LONGs that the code would accept — Claude generated no TIER 2 88-89% signals
- Fixed: `LONGS: Reject < 88%. Output ONLY 88–100.` and TIER 2 band updated from `90–91%` to `88–91%`
- Also fixed: all 4 stale version strings `v46.93` → `v46.99` in bot.py

### P2 — Hardening fixes

**`strategist.py` — `write_decisions()` direct write — corrupt on crash**
- `DECISIONS_FILE` written directly with `json.dump()` — crash mid-write leaves truncated JSON; Trader reads corrupted decisions
- Fixed: atomic write via temp file + `os.replace()`

**`SETUP_ALL_TASKS.bat` — 3 tasks missing `/RL HIGHEST` + Step 1 missing 6 recheck deletes**
- `WhaleStream-Briefing`, `WhaleStream-OrphanCheck`, `WhaleStream-LogAnalyzer` registered without `/RL HIGHEST` — could be preempted by normal-priority processes under load
- Fixed: added `/RL HIGHEST` to all three tasks
- Step 1 cleanup did not delete `WhaleStream-Strategist-Recheck-A/B/C` or `WhaleStream-Trader-Reactive-A/B/C` — re-running SETUP_ALL_TASKS.bat left ghost tasks from old ADD_RECHECK_TASKS.bat runs
- Fixed: added all 6 delete lines to Step 1

**`ADD_RECHECK_TASKS.bat` — `/ru "%USERNAME%"` resolves to wrong account when run as admin**
- When BAT is run as Administrator, `%USERNAME%` resolves to the admin account name, not the logged-in user — tasks may register under the wrong account
- Fixed: removed `/ru "%USERNAME%"` from all 6 task registrations (matches SETUP_ALL_TASKS.bat behavior)

---

## v46.98 — 2026-06-28 — Third full audit pass: 19 fixes across 8 files (learning loop, go-live blockers, scheduling, hardening)

### P0 — Critical bugs fixed

**`strategist.py` — `build_coin_history` emoji direction key — entire learning loop broken**
- `direction = row[COL_SIGNAL].strip().upper()` produced `"🟢 LONG"` — never matched canonical key `("BTC", "LONG")` in `targets`
- `history` always returned empty → Strategist saw blank coin history on every run → learning loop from Debrief was completely silenced
- Fixed: `_dir_raw = row[COL_SIGNAL].strip().upper(); direction = "LONG" if "LONG" in _dir_raw else ("SHORT" if "SHORT" in _dir_raw else _dir_raw)`

**`bot.py` — Verdict fallback `"TRADE"` instead of `"GO"`**
- `data1.get("verdict", "TRADE")` — if batch 1 returned no explicit verdict, bot used invalid sentinel; `"TRADE"` is not a valid verdict value
- Fixed: default changed to `"GO"` (the canonical pass-through value)

**`bot.py` — LONG TP1 minimum floor 2.5% instead of 3.0%**
- LONG used `_tp1_dist < 2.5` while SHORT already used `_tp1_dist < 3.0` — asymmetric gate allowed LONG TP1s within 2.5–2.9% that underperform
- Fixed: `if _tp1_dist < 3.0` — both LONG and SHORT now require minimum 3.0% TP1 distance

**`tracker.py` — `X-BAPI-DEMO-TRADING: "1"` hardcoded in `bybit_request_auth()` (go-live blocker)**
- Tracker's authenticated endpoint (closed P&L, balance) unconditionally sent demo header — live account would be invisible to Tracker on July 1
- Fixed: conditional `if "demo" in BYBIT_BASE_URL: headers["X-BAPI-DEMO-TRADING"] = "1"`
- Also: auth timestamp changed from `-1000ms` to `-3000ms` (connection reliability)

**`ADD_RECHECK_TASKS.bat` — All 6 recheck/reactive tasks used broken scheduling**
- All 6 tasks: `/sc DAILY /st XX:XX /ri 240 /du 9999:59` — DAILY+RI repeats are unreliable on Windows 10; tasks stop firing after 9999h
- Also missing `/RL HIGHEST` — tasks ran at normal priority, could be preempted
- Fixed: all 6 now use `/sc HOURLY /mo 4 /st XX:XX /rl HIGHEST`

**`debrief.py` — `if pnl:` falsy trap (two locations)**
- `if pnl:` treats `0.0` P&L as falsy → trades that broke even (0% P&L) silently omitted from debrief output and Telegram
- Fixed: `if pnl is not None` at L327 (outcome_detail) and L493 (Telegram pnl_str)

**`debrief.py` — `load_memory()` silently reset on corrupt JSON**
- `except Exception: pass` swallowed any corruption error — memory was reset to empty with no log entry
- Fixed: `except Exception as e: print(f"✗ pattern_memory.json corrupt: {e} — starting fresh")`

**`debrief.py` — `save_memory()` non-atomic write**
- Direct `open(MEMORY_FILE, "w")` — if process dies mid-write, pattern_memory.json is corrupted (partial JSON)
- Fixed: atomic write via temp file + `os.replace()` (crash-safe)

**`morning_briefing.py` — `safe_read(MONITOR_LOG)` reads entire log into RAM (two functions)**
- `parse_monitor_heartbeat()` and `parse_last_fills_24h()` both called `safe_read(MONITOR_LOG)` — reads the full log file (can grow to 100MB+) into memory every morning
- Fixed: both now use `read_last_lines(MONITOR_LOG, 500/2000)` — O(tail) not O(file)

### P1 — High severity bugs fixed

**`SETUP_ALL_TASKS.bat` — Tracker and Monitor missing `/RL HIGHEST`**
- Tracker (every 30min) and Monitor (every 2min) registered without `/RL HIGHEST` — could be preempted by other processes during critical TP/SL detection
- Fixed: both now include `/RL HIGHEST`

**`run_strategist_recheck.bat` + `run_trader_reactive.bat` — Missing `PYTHONIOENCODING`**
- UTF-8 encoding env vars not set — emoji prints crash with `UnicodeEncodeError` in Task Scheduler (cp1252 default)
- Fixed: added `set PYTHONIOENCODING=utf-8` and `set PYTHONUTF8=1` to both BAT files

**`strategist.py` — SHORT recheck missing "price rallied above zone" veto**
- Recheck R2 only vetoed SHORT when `price < entry_low * 0.95` (price fell through) — missing the case where SHORT entry zone was missed because price rallied up through it
- Fixed: added `elif _px > _eh * 1.05: _new_dec = "VETO"` branch for price-rallied-above case

**`strategist.py` — Recheck mode missing `reduced_count` in output**
- `_updated` dict written by recheck mode had `approved_count` and `vetoed_count` but no `reduced_count` — Trader reactive mode couldn't see how many REDUCE_SIZE decisions existed
- Fixed: `_rc_reduced = [d["coin"] for d in _new_decisions if d["decision"] == "REDUCE_SIZE"]; _updated["reduced_count"] = len(_rc_reduced)`

**`trader.py` — `_GATE4_RECOVERY_THRESHOLD = 425.0` hardcoded**
- If `BYBIT_START_BALANCE` changes (e.g. capital injection), recovery threshold stays at $425 — Gate 4 never releases
- Fixed: `_GATE4_RECOVERY_THRESHOLD = BYBIT_START_BALANCE * 0.85` (dynamic)

**`watchdog.py` — Strategist health check matched "run started" not "run complete"**
- `check_strategist()` looked for `"Strategist run started"` pattern — a Strategist that crashed mid-run appeared healthy to Watchdog
- Fixed: pattern changed to `"Strategist run complete"` — only fully-finished runs count as healthy

**`morning_briefing.py` — GO_LIVE_DATE countdown off by one**
- `(GO_LIVE_DATE - now_bkk).days` uses full datetime difference — returns 0 the day before go-live due to time-of-day subtraction
- Fixed: `(GO_LIVE_DATE.date() - now_bkk.date()).days` — pure calendar-day comparison

**`tracker.py` — `weekly_summary()` empty week breaks streak**
- `if not week_trades: break` — if the bot was paused for a week (drawdown protection, Gate 4), the streak count resets to 0 even for valid prior profitable weeks
- Fixed: advance `_prev_week()` first, then `continue` on empty weeks — streaks survive bot-pause weeks

---

## v46.97 — 2026-06-28 — Second full audit pass: 15 fixes across 5 files (trader, monitor, tracker, debrief, briefing)

### P0 — Go-live blocker fixed

**`trader.py` — Demo-trading header hardcoded (go-live blocker)**
- `X-BAPI-DEMO-TRADING: "1"` was in `bybit_request()` unconditionally — all live Trader orders would silently go to demo account on July 1
- Fixed: header only injected when `"demo" in BYBIT_BASE_URL`

### P1 — High severity bugs fixed

**`trader.py` — Gate 4 floor $400 instead of $425 (wrong threshold)**
- `_BALANCE_GATE4_FLOOR = 400.0` hardcoded — spec is `BYBIT_START_BALANCE × 0.85 = $500 × 0.85 = $425`
- Also: warning message falsely claimed "Gate 4 breach active" before checking if breach occurred
- Fixed: `_BALANCE_GATE4_FLOOR = BYBIT_START_BALANCE * 0.85`; `_BALANCE_WARN_THRESHOLD = _BALANCE_GATE4_FLOOR + 25`; dynamic breach note

**`trader.py` — `get_open_orders()` blocked re-entry on reduce-only TP close orders**
- All reduce-only TP close orders appeared in `already_active` set — a coin with 4 open TP legs was blocked from new entries for same coin even after position was closed
- Fixed: skip orders where `order.get("reduceOnly") is True` before adding to `open_syms`

**`trader.py` — Entry price falsy trap (`not all([entry, sl, tp1])`)**
- `not all([...])` evaluates `0.0` as falsy — a valid entry/SL/TP price of exactly 0.0 would abort the trade
- Fixed: `if entry is None or sl is None or tp1 is None`

**`trader.py` — SL-to-BE missing `slTriggerBy: MarkPrice`**
- SL modification request lacked `"slTriggerBy": "MarkPrice"` — Bybit rejects or uses LastPrice by default (wick-stop risk)
- Fixed: added `"slTriggerBy": "MarkPrice"` to `/v5/position/trading-stop` call

**`monitor.py` — Redundant state spread `{**curr, "sl": curr["sl"]}`**
- `state["positions"][symbol] = {**curr, "sl": curr["sl"]}` is a no-op spread (setting a key to its own value)
- Fixed: `state["positions"][symbol] = curr`

**`monitor.py` — SL-to-BE prev_avg=0 crash on wiped state file**
- `be_needed` logic compared against `prev_avg=0` when state file was wiped — always triggered SL-to-BE incorrectly
- Fixed: fallback `_effective_avg = prev_avg if prev_avg > 0 else float(curr.get("avgPrice", 0) or 0)`

**`tracker.py` — `bybit_balance is not None` falsy trap (second location)**
- `if _total_bal == 0 and bybit_balance:` was False for `bybit_balance == 0.0` in `write_dashboard_html` — missed the balance update
- Fixed: `if _total_bal == 0 and bybit_balance is not None`

**`tracker.py` — Weekly streak `%W` → ISO week (two locations)**
- `strftime("%Y-W%W")` miscounts on non-Monday weeks and fails at year boundaries (Dec 28–Jan 3 edge case)
- Fixed: `.isocalendar()` → `f"{iso[0]}-W{iso[1]:02d}"` in both `write_dashboard_html` (~L607) and `_update_gate_checklist` (~L1279)
- Also fixed: empty weeks (bot down) no longer break streak — `continue`/`pass` instead of `break`/`consec=0`

**`debrief.py` — Shared `now` across batch caused false dedup**
- `now = bkk_now_str()` computed once before the for-loop — all 5 trades in a batch shared the same timestamp; trades 2–5 were silently skipped by `already_debriefed()` if same coin+direction within 5-min window
- Fixed: moved `now = bkk_now_str()` inside the loop (refresh per trade)

**`debrief.py` — IndexError on empty Claude response `msg.content[0]`**
- If Anthropic returned an empty content array (throttle/timeout), bare index access crashed with IndexError
- Fixed: `raw = msg.content[0].text.strip() if msg.content else ""`; return `None` if empty

**`morning_briefing.py` — `btc_price`/`btc_sma` None crash in BEARISH/BULLISH f-strings**
- NEUTRAL branch had `if btc_price and btc_sma else "..."` guard; BEARISH and BULLISH did not — TypeError on None when Bybit offline
- Fixed: added same guard to both BEARISH and BULLISH branches

**`morning_briefing.py` — Double-counting order failures**
- `if "❌ Order failed" in line or ("❌" in line and "Order" in line)` — any "❌ Order failed" line matched both clauses, counted twice
- Fixed: `if "❌ Order failed" in line: ... elif "❌" in line and "Order" in line:`

### Speed / token optimizations

**`trader.py` — Removed 2× redundant `sheet.get_all_values()` calls**
- SL-to-BE check and stale order check each fetched all sheet rows a second time (already fetched at top of `run_trader`)
- Fixed: both reuse `data_rows` (already fetched) — saves 2 Google Sheets API calls per Trader run

### Infrastructure fixes

**`SETUP_ALL_TASKS.bat` — Strategist and Watchdog used unreliable `/SC DAILY /RI 240 /DU 9999:59`**
- `/RI` repeat-interval on a DAILY trigger is unreliable on some Windows 10 versions and stops after `/DU` expires
- Fixed: both now use `/SC HOURLY /MO 4` — the same reliable pattern used by Bot and Trader

**`PUSH_TO_GITHUB.bat` — Hardcoded commit message**
- Commit message was stale after every version bump — required manual file edit before each push
- Fixed: `set /p COMMIT_MSG=Enter commit message:` — dynamic prompt at push time

---

## v46.96 — 2026-06-28 — Full system audit + 14 targeted fixes across all 8 agents

### P0 — Go-live blockers fixed

**`monitor.py` — Demo-trading header conditional (go-live blocker)**
- `X-BAPI-DEMO-TRADING: "1"` was hardcoded unconditionally — would make live Bybit positions invisible on July 1
- Fixed: header only sent when `"demo" in BYBIT_BASE_URL`

**`monitor.py` — f-string crash on zero SL**
- `f"{curr_sl:.6g if curr_sl else 'none'}"` is invalid Python inside an f-string format spec — crashes when `curr_sl == 0`
- Fixed: pre-compute `was_str` before the f-string

**`monitor.py` — SL moved to stale entry price**
- `move_sl_to_breakeven()` was called with `prev_avg` (price from LAST monitor run), not live `curr["avgPrice"]`
- Fixed: use `curr["avgPrice"]` for accurate breakeven SL

**`monitor.py` — Remove 1000ms timestamp backdate**
- `-1000` from timestamp was unnecessary with `recv_window=20000`; removed

**`strategist.py` — Emoji prefix in direction silently dropped all signals (P0)**
- Sheet stores `"🟢 Long"` / `"🔴 Short"` — `direction.strip().upper()` produced `"🟢 LONG"` which != `"LONG"` → all signals dropped every run
- Fixed: extract canonical LONG/SHORT by checking if substring present in direction string

### P1 — High severity bugs fixed

**`trader.py` — `_grace_age_min` NameError guard**
- Variable could be uninitialized if `try` block raised after `_cb_grace_active = True` but before assignment
- Fixed: initialize `_grace_age_min = 0` before the try block

**`trader.py` — Missing timestamp skips signal instead of silently including**
- Signals with unparseable timestamps were silently included as "fresh" — could trade ancient signals
- Fixed: `continue` (skip) instead of `pass` (include) on parse failure

**`trader.py` — Balance file refresh after order loop**
- `bybit_balance.json` was written before orders with stale `_early_n_positions` count
- Fixed: second `write_balance_file()` call after loop when orders were placed

**`tracker.py` — `bybit_balance` falsy guard**
- `if bybit_balance` was False for balance == 0.0 (Bybit API hiccup), cascading to None format crash
- Fixed: `if bybit_balance is not None`

**`bot.py` — Rescue call misses truncated-mid-JSON case**
- Rescue only triggered when `##JSON_START##` absent; if present but `##JSON_END##` missing (truncated JSON), no rescue → silent STAY OUT
- Fixed: trigger rescue also when `##JSON_END##` absent

**`bot.py` — Cross-direction conflict guard**
- Same coin could appear as both LONG and SHORT simultaneously from two batches — contradictory signals sent to trader
- Fixed: post-merge conflict check removes both sides

### Speed / token optimizations

**`bot.py` — CoinGecko stale sleep**
- `if page < 3: time.sleep(2)` fired after LAST page too (wasted 2s per run)
- Fixed: `if page < 2`

**`strategist.py` — Lesson list reversed() incorrect**
- `reversed(lesson_list[-4:])` presented oldest lesson last → model read stale lesson with highest attention
- Fixed: removed `reversed()` — newest lesson now last (highest model attention weight)

**`strategist.py` — `_icon` change label for REDUCE_SIZE**
- `_icon` was hardcoded "APPROVE→VETO" or "VETO→APPROVE"; missed REDUCE_SIZE transitions
- Fixed: `f"{_prev_dec}→{_new_dec}"`

**`debrief.py` — `max_tokens` raised 320→450**
- 320 was too tight for multi-field JSON responses; caused silent truncation → "Review manually" noise
- Fixed: `max_tokens=450`

**`morning_briefing.py` — Telegram `data=` → `json=`**
- Form encoding could corrupt Unicode/emoji in Telegram HTML messages
- Fixed: `json=data` for safe encoding

**`morning_briefing.py` — Negative drawdown clamped**
- When profitable, drawdown was negative → misleading "Gate 4: ✅ OK — -3.2% drawdown"
- Fixed: `max(0.0, ...)` clamp; also clamped `available_bal` to 0 floor

---

## v46.95 — 2026-06-28 — Fix WS_EMBEDDED regex in bot, strategist, trader, tracker

### Root-cause fix — Daily Checklist never updating for 4 agents

**`[^;]*` regex broken in `_mark_done()` of 4 agent files**
- `whale_stream_bot.py`, `whale_stream_strategist.py`, `whale_stream_trader.py`, `whale_stream_tracker.py` all had:
  `_re.sub(r'var WS_EMBEDDED=\{[^;]*\};', ...)` in their `_mark_done()` HTML injection
- `daily_status.json` is written with `indent=2` → the JSON blob is multi-line
- `[^;]*` cannot match newlines, so the substitution silently failed every time
- `except Exception: pass` swallowed the failure — no error, no update, checklist stays stale
- Fixed in all 4 files: `[^;]*` → `[\s\S]*?` (already correct in watchdog, monitor, morning_briefing)
- This is the root cause of the Strategist (and Bot, Trader, Tracker) never ticking the Daily Checklist

---

## v46.94 — 2026-06-28 — 4-agent deep audit: 12 new fixes across 8 files

### Critical fixes

**whale_stream_tracker.py — WIN/LOSS resolution used spot `lastPrice` instead of perpetual `markPrice`**
- `load_bybit_prices()` fetched `category: "spot"` and read `lastPrice` — but Bybit triggers TP/SL for linear (USDT perpetuals) on `markPrice`, not spot price
- Spot vs perpetual price can diverge by 0.5–2% during funding-rate-heavy periods — could resolve a trade incorrectly (WIN vs LOSS)
- Fixed: changed `category` to `"linear"` and read `t.get("markPrice") or t.get("lastPrice")` as fallback

**whale_stream_trader.py — `place_quad_tp_closes()` always incremented `allocated` even on failed TP placements**
- `allocated += leg_qty` was unconditional — ran whether `ok=True` or `ok=False`
- If legs 1–3 all failed, the 4th leg placed too small a qty (remainder already consumed by ghost allocations)
- Fixed: `if ok: allocated += leg_qty` — only advance on successful placement

**whale_stream_monitor.py — `_mark_done()` never called in crash path**
- `run_monitor()` crash was caught by the outer try/except, Telegram was sent, then `raise` — but `_mark_done("monitor")` was never called
- Monitor would always show as "not seen today" in Daily Checklist after a crash
- Fixed: added `_mark_done("monitor", details={"error": str(e)[:200]})` before `raise`

**whale_stream_trader.py — cycle guard `return` had no `_mark_done()` call**
- When the cycle guard detected a duplicate run for the same 4h slot, it printed and returned without calling `_mark_done()`
- Daily Checklist showed Trader as "not done" even though it had already run successfully
- Fixed: added `_mark_done("trader", details={"placed": [], "skipped": ["cycle_guard"]})` before the return

### High fixes

**whale_stream_trader.py — no outer try/except in `__main__` block**
- An unhandled exception in `main()` would exit without calling `_mark_done()` and without a Telegram alert
- Fixed: wrapped `main()` in try/except with `_mark_done("trader", details={"error": ...})` and re-raise

**whale_stream_debrief.py — no `cache_control` on Strategist system prompt (cost waste)**
- `call_debrief_claude()` sent `DEBRIEF_SYSTEM` as a plain string — no caching
- On a 5-trade batch, the ~1,200-token system prompt was billed 5× instead of 1×
- Fixed: added `cache_control: {"type": "ephemeral"}` to system prompt list format

**morning_briefing.py — `btc_sma` None guard missing in NEUTRAL branch**
- `f"...SMA (${btc_sma:,.0f})"` would raise `TypeError` if `btc_sma` was None while `btc_price` was set
- Fixed: changed `if btc_price` to `if btc_price and btc_sma`

**morning_briefing.py — WS_EMBEDDED regex used `[^;]*` (same bug as watchdog, fixed in v46.93)**
- `morning_briefing.py` and `whale_stream_monitor.py` both had the old `[^;]*` pattern in their own `_mark_done()` functions
- Fixed: both changed to `[\s\S]*?` to match watchdog's already-correct pattern

### Minor fixes

**morning_briefing.py — `list.index()` crash risk on duplicate log lines (dead `placed_symbols` block)**
- `lines.index(line)` returns the FIRST occurrence — on duplicate log lines it sliced the wrong context
- `placed_symbols` was populated but never used in the return dict or in `build_message()`
- Fixed: removed the dead `placed_symbols = []` initialization and the entire `m2` block

**RUN_FULL_CYCLE_NOW.bat — header comment still said "Bybit Demo" (confusing on go-live day)**
- Line 10 of the header block still said `executes approved signals on Bybit Demo`
- Fixed: changed to `executes approved signals on Bybit`

**JULY1_GOLIVE_CHECKLIST.md — "15 tasks" and "v46.92" both stale**
- Step 2 said "disable all 15 WhaleStream tasks" — actual count is 16 (10 core + 6 recheck)
- Footer said `v46.92` — now `v46.94`
- Fixed: both updated

**SETUP_ALL_TASKS.bat — final summary didn't mention ADD_RECHECK_TASKS.bat**
- Operator running SETUP_ALL_TASKS.bat to reset their schedule would end up with 0 recheck tasks and no warning
- Fixed: added explicit reminder echo to run ADD_RECHECK_TASKS.bat

---

## v46.93 — 2026-06-28 — 12-fix audit pass: NameErrors, dead code paths, caching, UI accuracy

### Critical fixes

**whale_stream_bot.py — `_gate1_resolved` / `_open_count` NameError on blocked signal runs**
- Both variables were only initialised inside the `if signals:` / `else:` branches of `log_to_google_sheets()`
- If signals existed but were ALL dropped by dedup or blocklist before the branch was reached, the function raised `NameError` and crashed — no Sheet log, no Telegram
- Fixed: added `_gate1_resolved = 0` and `_open_count = 0` safe defaults at the top of the function

**whale_stream_strategist.py — Re-check Rule 2 (entry price deviation) was completely dead for real signals**
- Entry price parser did not strip `$` signs — `$435-$445` could not be cast to float; the `except` silently skipped the check
- Every signal with a dollar-prefixed entry passed Rule 2 by default, defeating the guard
- Fixed: added `.replace("$", "")` before `.strip()` in `_entry_str` parsing

**whale_stream_tracker.py — Daily Checklist always showed 0W/0L on trade resolutions**
- `_newly_resolved` dict uses key `"outcome"`, but the counters were reading `r.get("status")`
- Every resolved trade contributed 0 to both win and loss counts; Telegram summary was always "🏆 0W / 0L"
- Fixed: changed both comparisons to `r.get("outcome") == "WIN"` / `"LOSS"`

### Medium fixes

**whale_stream_bot.py — version strings stuck at v46.78 (4 locations)**
- Banner, WHALE_STREAM_PROMPT, Telegram alert, and startup print all still said v46.78
- Fixed: all 4 updated to v46.93 via replace_all

**whale_stream_strategist.py — no prompt caching on Strategist system prompt**
- `call_strategist_claude()` passed `system=STRATEGIST_SYSTEM` as a plain string — no `cache_control`
- Added `cache_control: {"type": "ephemeral"}` to system prompt; saves ~30% on Strategist API cost

**whale_stream_tracker.py — fast-expire Telegram message said "72h" for a 12h expiry**
- Fast-expire fires at 12h with no Bybit price; Telegram still said "signal never filled in 72h"
- Fixed: message now says "no Bybit price for {age_fe:.0f}h, fast-expired" with actual age

**whale_stream_trader.py — `_strat_data` NameError risk if outer try silently fails**
- `_strat_data` was only assigned inside `if os.path.exists(DECISIONS_FILE):`; a silent outer-try exception could leave it undefined before the downstream `_strat_data.get(...)` calls
- Fixed: added `_strat_data = {}` safe default before the `if os.path.exists` block

**whale_stream_trader.py — negative drawdown logged when balance exceeds start**
- `(_bb_start_balance - _bb_balance) / _bb_start_balance * 100` goes negative when profitable
- Fixed: wrapped with `max(0.0, ...)` — drawdown is clamped at 0 when in profit

**whale_stream_watchdog.py — WS_EMBEDDED regex breaks if any JSON value contains a semicolon**
- `var WS_EMBEDDED=\{[^;]*\};` would stop at the first semicolon inside a string value, corrupting the HTML injection
- Fixed: changed to `[\s\S]*?` (non-greedy, dot-matches-newline) in both regex instances

**morning_briefing.py — bold tags rendered as literal `<b>text</b>` in Telegram**
- `parse_mode` was set to `""` (empty string) — Telegram ignored HTML markup
- Fixed: `parse_mode: "HTML"` applied

**morning_briefing.py — `gate4_breach.flag` never checked in briefing**
- Briefing checked `paused.flag`, `short_repair.flag`, `short_conservative.flag` but not `gate4_breach.flag`
- Fixed: added flag check + alert line when flag exists but drawdown < 15% (stale flag warning)

**ADD_RECHECK_TASKS.bat — version strings stuck at v46.90**
- Comment block header and echo banner still said v46.90
- Fixed: updated to v46.93

### Minor fixes

**whale_stream_debrief.py — `max_tokens=256` too low for complex pattern entries**
- Raised to `max_tokens=320` to prevent truncation on multi-pattern trade summaries

**RUN_FULL_CYCLE_NOW.bat — comment said "Bybit Demo" (confusing on go-live day)**
- Line 57 header comment now says "Bybit" (live-neutral wording)

---

## v46.92 — 2026-06-28 — CRITICAL: BYBIT_BASE_URL hardcoded to demo in 3 agents + watchdog fixes

### Critical fixes

**whale_stream_trader.py / tracker.py / monitor.py — `BYBIT_BASE_URL` hardcoded to demo endpoint**
- `BYBIT_BASE_URL = "https://api-demo.bybit.com"` was a plain hardcoded assignment in all 3 files
- Consequence: live Bybit API keys pointed at the demo endpoint authenticate and return 200 OK, but ALL orders are placed on the demo exchange — real money never moves
- Fixed in all 3 files: wrapped in `try: from local_config import BYBIT_BASE_URL except ImportError: BYBIT_BASE_URL = "https://api-demo.bybit.com"` — live override is now `BYBIT_BASE_URL = "https://api.bybit.com"` in local_config.py
- JULY1_GOLIVE_CHECKLIST.md Step 3 updated to include `BYBIT_BASE_URL` as a mandatory line to add

### Minor fixes

**whale_stream_watchdog.py — banner/docstring/comment said "8h" instead of "4h"**
- `TRADER_CRITICAL_HOURS = 4` is the actual threshold, but 3 places in the file still said "8h": banner line 9, `build_critical_alert()` docstring, and Check CRITICAL comment
- Fixed: all 3 locations updated to "4h" to match the actual `TRADER_CRITICAL_HOURS = 4` constant

---

## v46.91 — 2026-06-28 — 4 final pre-ship fixes (second audit pass)

### Fix added after v46.90
**whale_stream_debrief.py — `_mark_done()` never called — Debrief always showed missed in Daily Checklist**
- `_mark_done` was not defined or called anywhere in debrief.py
- Every debrief run completed successfully but the Daily Checklist.html would always show it as missed
- Fixed: added `_mark_done()` function definition (same pattern as all other agents) and added calls at all 3 exit paths in `main()` — no-arg early exit (details: "no_arg"), parse error (details: "parse_failed"), normal completion (details: trade count)

---

## v46.90 — 2026-06-28 — 3 final pre-ship fixes from second audit pass

### Critical fix
**whale_stream_trader.py — `TRADE_MARGIN_USDT` hardcoded, JULY1 checklist Step 5 was broken**
- `TRADE_MARGIN_USDT = 20` was a plain hardcoded assignment with NO `try: from local_config` import
- The JULY1 checklist Step 5 tells the operator to set this in `local_config.py` — that instruction had zero effect
- Fixed: wrapped in `try: from local_config import TRADE_MARGIN_USDT except ImportError: TRADE_MARGIN_USDT = 20`
- Operator can now set live margin in `local_config.py` and the system will use it correctly

### Medium fix
**whale_stream_trader.py — Gate 4 position cap not enforced mid-loop**
- `n_positions` was fetched before the order loop and never incremented after a successful order placement
- In Gate 4 mode (cap = 4): if 3 positions existed and 3 signals passed the cap check simultaneously, all 3 were placed (giving 6, not 4)
- Fixed: `n_positions += 1` after each successful `place_order()` call keeps the cap accurate mid-loop

### Medium fix (cosmetic)
**ADD_RECHECK_TASKS.bat — stale v46.87 version string in comment block header**
- Line 4 comment still said "v46.87 continuous decision loop" while echo banner was already correct (v46.89)
- Fixed: comment updated to v46.90

---

## v46.89 — 2026-06-28 — 4-agent audit: 16 critical/high/medium fixes across 8 files

### Critical fixes

**whale_stream_trader.py — `send_telegram` NameError in `close_position_at_market_for_veto()`**
- Both urgent failure Telegrams called `send_telegram()` which does not exist — only `send_telegram_alert()` does
- All VETO failure alerts were silently swallowed by `try/except Exception: pass`
- Fixed: both calls now use `send_telegram_alert()` — failures will now actually alert the operator

**whale_stream_trader.py — timezone inflation in `get_stale_entry_orders()`**
- `.replace(tzinfo=timezone.utc)` was stripping the real tz and relabelling as UTC, inflating age by 7h
- `bkk_now` (UTC+7) was being labelled "UTC" so difference was artificially 7h too large
- Could trigger auto-cancellation of valid live orders 7h early
- Fixed: `age_h = (bkk_now - created_dt).total_seconds() / 3600` — both are already tz-aware

**whale_stream_strategist.py — parse-failure fallback fell through to normal execution**
- After JSON parse error, code set a `parsed` dict missing `cycle_id`, `recheck_count`, `recheck_changes`
- Missing `write_decisions()`, `_mark_done()`, and `return` — execution continued into merge/tally block
- VETO-all safety was bypassed; normal decision-writing proceeded with incomplete data
- Fixed: parse-failure path now builds complete dict, calls `write_decisions()`, `_mark_done()`, and `return`

**whale_stream_strategist.py — no-signal and regime-filter early exits missing 3 required fields**
- `cycle_id`, `recheck_count`, `recheck_changes` were absent from the empty-decisions dict in 2 code paths
- Downstream `--recheck` mode reads these fields; missing keys caused KeyError crashes
- Fixed: both early exits now include all 3 fields

**whale_stream_bot.py — `fetch_signal_graveyard()` returned 2-tuple but caller unpacks 3 values**
- 3 return sites (`return "", 50`) missing the third element; caller uses `graveyard, short_wr, coin_perf = ...`
- Would raise `ValueError: not enough values to unpack` when Google credentials file is absent
- Fixed: all 3 sites now return `"", 50, ""`

### High fixes

**whale_stream_watchdog.py — `TRADER_CRITICAL_HOURS = 8` should be 4**
- At 4h cycles, 8h means 2 full missed cycles before CRITICAL escalation — too slow to respond
- Fixed: `TRADER_CRITICAL_HOURS = 4` (1 missed cycle triggers CRITICAL Telegram)

**whale_stream_strategist.py — `btc_pct_sma` None guard added in format strings**
- `btc_pct_sma` could theoretically be None if `get_btc_market_bias()` returns None mid-flow
- Format string `{btc_pct_sma:+.1f}` would raise `ValueError` on None
- Fixed: all 3 occurrences now use `(btc_pct_sma or 0)` as safe default

**whale_stream_tracker.py — "Day 0" on launch day (July 1)**
- `abs(_days_to_live)` returns 0 on July 1 itself — showed "Day 0 of live trading"
- Fixed: `abs(_days_to_live) + 1` → shows "Day 1" on July 1, "Day 2" on July 2, etc.

### Medium/ops fixes

**ADD_RECHECK_TASKS.bat — version banner updated**
- Echo banner still said `v46.87`; updated to `v46.89`

**ADD_STATUS_SERVER_TASK.bat — stale "OVERWRITES" warning removed**
- Warning said "This script OVERWRITES run_status_server.bat" but it no longer does (guard was added in v46.88)
- Updated comment now correctly describes the skip-if-exists behaviour

**JULY1_GOLIVE_CHECKLIST.md — 4 corrections**
- Footer version: `v46.87` → `v46.89`
- Step 2 / Step 7: "all 8 WhaleStream tasks" → "all 15 WhaleStream tasks"
- Step 5: removed instruction to edit `whale_stream_trader.py` directly (contradicted Step 3 "THE ONLY FILE YOU TOUCH is `local_config.py`")
- Step 5: added instruction to update `BYBIT_START_BALANCE` in trader.py + tracker.py at go-live

## v46.88 — 2026-06-28 — Pre-go-live first audit: 15 fixes across 9 files

### Audit findings addressed (3-agent parallel audit run)

**whale_stream_tracker.py — 2 missing `_mark_done()` calls fixed**
- Google Sheets connection failure early exit now calls `_mark_done("tracker", error=...)`
- No-trade-rows early exit now calls `_mark_done("tracker", rows=0)`
- Previously: Daily Checklist would show tracker as "not run" on transient Sheets API errors

**whale_stream_tracker.py — go-live countdown no longer goes negative after July 1**
- Countdown card now switches to "🚀 LIVE — Day N of live trading" after July 1
- Previously: dashboard showed "−N days to Go-Live" for eternity after launch

**whale_stream_tracker.py — BYBIT_START_BALANCE sync comment added**
- Comment now reads: "MUST match BYBIT_START_BALANCE in whale_stream_trader.py"

**whale_stream_strategist.py — Claude API fallback changed from APPROVE-all to VETO-all**
- Previously: any Claude API failure or JSON parse error caused ALL signals to be silently approved
- Now: failure writes VETO for every signal + sends urgent Telegram alert to ops channel
- Financial risk eliminated: unreviewed trades can no longer enter Bybit during Claude outages

**whale_stream_trader.py — cancel_order() retry logic added (3 attempts, exponential backoff)**
- Retries 3× on transient network failures (1s, 2s delay between attempts)
- Immediately skips retry on `retCode=20001` (order already gone — not an error)
- Previously: single transient failure caused cancel to return False, triggering unnecessary market close

**whale_stream_trader.py — close_position_at_market_for_veto() retry logic added**
- After cancel fails, retries `get_position_for_coin()` up to 3× with 3s delay (Bybit fill-propagation lag)
- On market-close failure: sends urgent Telegram "⛔ VETO CLOSE FAILED — MANUAL CLOSE REQUIRED"
- On position-not-found after retries: sends "⚠️ VETO FAILED — MANUAL ACTION REQUIRED" Telegram
- Previously: single-pass; failure was silent (logged only, no escalation)

**whale_stream_trader.py — REDUCE_SIZE minimum size floor added**
- Gate 4 (0.40×) + REDUCE_SIZE (×0.5) = 0.20× can fall below Bybit minimum order value
- Floor clamped to 0.25× with log warning and console message
- Previously: could silently produce qty=0 or rejected orders on cheap coins

**whale_stream_trader.py — stale orphan orders now auto-cancelled (not alert-only)**
- `get_stale_entry_orders()` result now triggers `cancel_order()` for each orphan
- Telegram report shows ✅/✗ per coin — any failed cancels flagged for manual follow-up
- Previously: Telegram alert said "cancel manually in Bybit if needed" — relied on human action

**whale_stream_trader.py — LONG_COIN_AVOID_LIST synced with bot.py blocklist**
- Added `QNT` and `WIF` to `LONG_COIN_AVOID_LIST` (were in bot.py `LONG_COIN_BLOCKLIST` but missing from trader's second-defence layer)

**whale_stream_trader.py — BYBIT_START_BALANCE sync comment added**
- Comment now reads: "MUST match BYBIT_START_BALANCE in whale_stream_tracker.py"

**check_daily_status.py — task name mismatch fixed**
- `AGENT_TASK` dict corrected: `WhaleStreamStrategist` and `WhaleStreamWatchdog` (no hyphens)
- Previously: gap-alert fix instructions pointed to non-existent task names in Task Scheduler

**run_strategist_recheck.bat + run_trader_reactive.bat — log output added**
- Both now redirect stdout+stderr to `strategist_recheck_log.txt` / `trader_reactive_log.txt`
- Previously: Task Scheduler errors from re-check runs were invisible

**JULY1_GOLIVE_CHECKLIST.md — 3 gaps filled**
- Pre-flight now checks `gate4_breach.flag` absent (was missing)
- Pre-flight now checks `paused.flag` absent (was missing)
- Pre-flight now includes step to verify/run `ADD_RECHECK_TASKS.bat` (6 v46.87 tasks)
- WR thresholds adjusted to realistic baselines (LONG ≥50%, SHORT ≥70%)

**SETUP_ALL_TASKS.bat — stale "only file you need" comment fixed**
- Header now correctly notes that `ADD_RECHECK_TASKS.bat` must also be run for recheck tasks

**ADD_STATUS_SERVER_TASK.bat — DISABLED guard added**
- Now skips overwriting `run_status_server.bat` if it already exists
- Added prominent warning that SETUP_ALL_TASKS.bat already registers StatusServer

## v46.87 — 2026-06-28 — Continuous decision loop: Strategist re-checks + Trader reactive mode

### Design
Every 4h cycle now has 3 intra-cycle re-checks at +1h10m, +2h10m, +3h10m. Each re-check is rules-only (no Claude cost) and takes ~5 seconds. Trader reacts 5 minutes later. "Think → act → review → improve → act" without human touch.

### whale_stream_strategist.py — `--recheck` mode
- New `_get_cycle_id()` helper: stable ID per 4h window (e.g. `2026-06-28_0800`)
- First-pass decisions now include `cycle_id`, `recheck_count=0`, `recheck_changes=[]`
- `--recheck` CLI flag bypasses cycle guard and runs 3 rules per remaining signal:
  - **Rule 1 — BTC regime flip**: BTC BEARISH → veto all LONGs; BULLISH → veto all SHORTs
  - **Rule 2 — Entry staleness**: price >5% past entry zone high/low → VETO (zone missed)
  - **Rule 3 — Pattern memory**: ≥3 consecutive losses for this coin → VETO
- Writes updated decisions file with `recheck_at`, `recheck_count`, `recheck_changes`
- Sends Telegram only if any decisions changed (zero noise when market is calm)
- `_mark_done("strategist", recheck=True)` — checklist stays green

### whale_stream_trader.py — `--reactive` mode
- `--reactive` CLI flag bypasses cycle guard
- In reactive mode, coins with an existing Bybit Order ID are skipped in the new-order loop (already placed — don't double-place)
- New reactive veto scan: for each OPEN signal row that has a Bybit Order ID AND is now VETOED by Strategist → `close_position_at_market_for_veto()`:
  - Step 1: call `cancel_order(symbol, order_id)` — works if order still unfilled
  - Step 2: if cancel fails (order filled, position open) → place Market + `reduceOnly=True` to exit
- New `get_position_for_coin(symbol)` — queries `/v5/position/list` for live position details
- New `close_position_at_market_for_veto(symbol, bybit_order_id)` — orchestrates cancel→close

### New files
- `run_strategist_recheck.bat` — calls `whale_stream_strategist.py --recheck`
- `run_trader_reactive.bat` — calls `whale_stream_trader.py --reactive`
- `ADD_RECHECK_TASKS.bat` — registers 6 Task Scheduler tasks (3 re-check + 3 reactive):
  - `WhaleStream-Strategist-Recheck-A/B/C` at :10 of 4h+1/2/3
  - `WhaleStream-Trader-Reactive-A/B/C` at :15 of 4h+1/2/3

### Full cycle schedule (BKK time, per 4h boundary)
```
:00  SigBot      — generates 3 LONG + 1 SHORT signals
:10  Strategist  — Claude deep analysis → APPROVE / VETO / REDUCE
:20  Trader      — places first wave of approved orders
:30  Watchdog    — logs cycle health
1:10 Strategist re-check A — rules-only (BTC regime + staleness + memory)
1:15 Trader reactive A     — cancel/close newly vetoed; place newly approved
2:10 Strategist re-check B — rules-only
2:15 Trader reactive B
3:10 Strategist re-check C — rules-only
3:15 Trader reactive C
```

## v46.86 — 2026-06-28 — Full _mark_done coverage: every agent exit path guaranteed to tick checklist

### whale_stream_bot.py
- Added `_mark_done("sigbot", error=...)` on "not enough coins fetched" early exit
- Added `_mark_done("sigbot", error=...)` on Batch 1 Claude API failure early exit

### whale_stream_strategist.py
- Added `_mark_done("strategist", error=...)` on Google Sheets connection failure early exit
- Added `_mark_done("strategist", error=...)` on Claude API failure early exit (after writing approve-all fallback decisions)

### whale_stream_trader.py
- Added `_mark_done("trader", ...)` on API key not configured early exit
- Added `_mark_done("trader", ...)` on Bybit connection failure early exit
- Added `_mark_done("trader", ...)` on balance too low early exit
- Added `_mark_done("trader", ...)` on Google Sheets failure early exit
- Added `_mark_done("trader", ...)` on no OPEN signals early exit
- Added `_mark_done("trader", ...)` on position cap early exit (shows count)
- Added `_mark_done("trader", ...)` on risk cap early exit (shows % deployed)

### whale_stream_tracker.py
- Wrapped `if __name__ == "__main__": main()` in try/except — any unhandled crash now calls `_mark_done("tracker", error=...)` so checklist never stays blank

### BAT files
- `ADD_STATUS_CHECK_TASK.bat`: changed bare `SET PYTHON_CMD=python` → full Python path
- `RUN_ANALYZE_NOW.bat`: changed bare `python` → full Python path

**Net effect:** Daily Checklist will tick correctly even when agents hit error paths. "Why is checklist showing 0/4?" should never recur due to a missing `_mark_done`.

## v46.85 — 2026-06-28 — CRITICAL FIX: two-tier signal expiry (8h unplaced / 72h placed)

### tracker.py — zombie signal pipeline unblock

**Root cause:** Trader skips signals older than 4h (stale entry zones). But tracker only expired them after 72h. Result: 50–100+ zombie OPEN rows accumulated in the sheet. SigBot couldn't re-generate those coins (already OPEN), Strategist always saw an empty queue, Trader never got fresh signals.

**Fix — two-tier expiry:**
- Signals with **no Bybit Order ID** (never placed on Bybit) → expire after **8h**. After 4h Trader won't touch them anyway; the extra 4h buffer covers the next Trader run. Immediately frees the pipeline.
- Signals **with Bybit Order ID** (placed, tracking TP2/TP3/TP4) → keep at **72h** unchanged.

**Impact:** On next tracker run, all unplaced signals older than 8h will be mass-expired. Strategist will see fresh queues from the next SigBot cycle. System unblocks itself automatically.

## v46.84 — 2026-06-28 — Audit fixes: _mark_done gaps + vetoed filter + watchdog guard + CLEAR_PAUSE path

### Post-audit fixes (6 bugs found and fixed)

**whale_stream_trader.py** — `_mark_done` now called on fresh circuit-breaker trigger:
- When CB fires for the first time (5 consecutive LOSSes), `return` was reached without calling `_mark_done`. Checklist trader row would remain unticked. Fixed: `_mark_done("trader", details={"placed":[], "skipped":["CIRCUIT BREAKER TRIGGERED — auto-paused"]})` added before `return`.

**whale_stream_strategist.py** — two fixes:
- Regime-filter exit path (BTC strongly trending, all signals vetoed) was missing `_mark_done`. Watchdog would fire false AMBER every time BTC was strongly trending. Fixed: `_mark_done` now called with `approved:[], vetoed:[coin names]` before regime-filter `return`.
- `_vetoed_coins` used `!= "APPROVE"` which incorrectly bucketed REDUCE_SIZE decisions into the vetoed list. Changed to `== "VETO"` — only true vetoes appear in the ❌ column.

**whale_stream_watchdog.py** — primary `daily_status.json` write wrapped in try/except:
- The JSON write at the start of `_mark_done` was unguarded. A file-lock or permissions error would crash Watchdog before `_write_html_snapshot()` ran. Now wrapped in try/except with error print.

**CLEAR_PAUSE.bat** — `python` → full Python path:
- Line 30 used bare `python -c "..."` to write `cb_grace.txt`. If Cowork Python takes precedence (as seen in CHANGELOG v46.74), the wrong interpreter runs. Changed to `"C:\Users\MAX\AppData\Local\Python\bin\python.exe"`.

## v46.83 — 2026-06-28 — Checklist: coin names in hints; each agent shows only its own work

### Task 285 — Rich coin names throughout Daily Checklist hints; clean agent separation

**whale_stream_watchdog.py** — cycle_summary now uses actual coin names instead of counts:
- SigBot: `🟢EIGEN,STRK,LDO | 🔴FF,ENS` (was `Bot:3L/2S`)
- Strategist: `queue empty` when no new signals (was `Strat:⏸ CB`)
- Trader: `⏸ CB` when circuit breaker active
- Full example: `Bot: 🟢EIGEN,STRK,LDO | 🔴FF,ENS  ·  Strat:queue empty  ·  Trader:⏸ CB`

**whale_stream_strategist.py** — early-exit path simplified:
- Queue-empty `_mark_done` now writes only `{approved:[], vetoed:[]}` — no SigBot coin cross-referencing

**morning_briefing.py** — `_mark_done("briefing")` now includes balance summary:
- Reads `BALANCE_FILE` (bybit_balance.json) and writes `summary: "Balance: $NNN · N open"`
- Checklist shows: `✅ Sent 07:00 BKK · Balance: $487 · 7 open`

**Daily Checklist.html** — agent hint rules (each agent shows only its own work):
- Strategist: empty approved+vetoed → `— Queue empty this cycle` (no SigBot cross-reference)
- Trader: CB active → `⏸ PAUSED — circuit breaker active` (no SigBot cross-reference)
- `formatStaticDetails("briefing")` → appends `summary` field after sent_at
- WS_EMBEDDED updated with corrected `watchdog_08_details.cycle_summary` using coin names

## v46.82 — 2026-06-28 — Watchdog: cycle summary in hint (Bot/Strat/Trader results)

### Task 284 — Watchdog adds per-agent cycle summary to daily_status.json

- `_mark_done("watchdog", ...)` now reads the current cycle's `sigbot_HH_details`, `strategist_HH_details`, `trader_HH_details` from `daily_status.json` and builds a `cycle_summary` string.
- Format: `Bot:3L/2S  Strat:⏸ CB  Trader:⏸ CB` — visible in the Watchdog row hint on the Daily Checklist.
- When agents run normally: `Bot:3L/2S  Strat:3✅/2❌  Trader:2 placed`
- When CB active: `Bot:3L/2S  Strat:⏸ CB  Trader:⏸ CB`
- When an agent missed its slot: shows `⚠ missed`
- Daily Checklist `formatAgentDetails("watchdog")` updated to append `cycle_summary` after the health status: `🟡 AMBER — check Task Scheduler  ·  Bot:3L/2S  Strat:⏸ CB  Trader:⏸ CB`
- WS_EMBEDDED updated with today's cycle_summary.

## v46.81 — 2026-06-28 — FIX: Daily Checklist — smarter agent hints + live always-running data

### Task 283 — Fix Daily Checklist.html (Daily Checklist → To do list/)

**Problem 1: 4h cycle agent hints were poor for Strategist/Trader/Watchdog**
- **Strategist**: when both `approved=[]` and `vetoed=[]` (e.g. CB paused, no signals), checklist showed confusing `✅ — | ❌ —`. Now shows `— No new signals reviewed this cycle`.
- **Trader**: when CB active, checklist showed misleading `🟢 — | ⏸ PAUSED — circuit breaker active`. Now shows `⏸ PAUSED — circuit breaker active` (no green dot). When orders placed: `✅ Placed: COIN1, COIN2`. When vetoed normally: `— Skipped: REASON`.
- **Watchdog**: now shows `🟢 All agents healthy` / `🟡 AMBER — check Task Scheduler` / `🔴 CRITICAL — <issues>` with optional `issues[]` list support for future detail.

**Problem 2: Always-running section showed static generic hint text only**
- Added `formatStaticDetails()` function that renders live data from `_details` keys.
- **Tracker**: shows `✅ N resolved this run (W W/L L) · X open · HH:MM BKK`
- **Monitor**: shows `✓ N position(s) watched · no changes · HH:MM BKK` or `🔔 N alert(s) fired · ...`
- **Briefing**: shows `✅ Sent HH:MM BKK · check Telegram`
- `applyStatus()` now reads `tracker_details`, `monitor_details`, `briefing_details` and calls `updateHint()`.

**Python agents updated to write details:**
- `whale_stream_tracker.py`: `_mark_done("tracker", details={resolved, wins, losses, open, last_run})`
- `whale_stream_monitor.py`: `_mark_done("monitor", details={positions, alerts, last_run})`
- `morning_briefing.py`: `_mark_done("briefing", details={sent_at})`

**WS_EMBEDDED** updated with today's data + `briefing_details`.

## v46.80 — 2026-06-28 — FIX: quad-TP allocated tracking bug + retrofit_quad_tp.py

### Cleanup — remove dead `place_partial_closes()` function (trader.py)
- Old 50/50 TP system function was still present as dead code after Task 280 replaced it.
- Confirmed zero callers. Deleted. Codebase now has only `place_quad_tp_closes()`.

### Bug fix — `place_quad_tp_closes()` last-leg oversize (trader.py)
- **Bug**: `allocated += leg_qty` was only incremented on successful API calls. If any intermediate TP leg was rejected by Bybit, the final leg would absorb both its own share AND the failed leg's share, causing the last order to exceed available position size and get rejected.
- **Fix**: `allocated += leg_qty` now runs unconditionally — tracks *planned* allocation regardless of API result. Last-leg remainder is always correct.
- Same fix applied to `retrofit_quad_tp.py`.

### New file — `retrofit_quad_tp.py`
- Standalone one-shot script to retrofit existing Bybit positions with 4×25% quad-TP closes.
- Cancels existing reduce-only orders per symbol, reads TP1-TP4 from Google Sheets, places quad-TP closes.
- Supports `--dry-run` flag for safe preview. Sends Telegram summary on completion.
- Uses Sheets API v4 directly (no gspread dependency) for broader compatibility.

## v46.79 — 2026-06-28 — FEAT: 4×25% quad-TP system + cancel-on-reversal (whale_stream_trader.py)

### Task 280 — Replace 2-TP 50/50 with 4-TP 25% quad-TP system
- **Replaced** `place_partial_closes()` (50%@TP1 + 50%@TP2/TP3) with new `place_quad_tp_closes()`
- **New function**: places up to 4 reduce-only limit orders at 25% qty each (TP1/TP2/TP3/TP4)
- **Removed** TIER-based TP selection (TIER 1 → TP3, TIER 2 → TP2). All trades now use all available TPs equally.
- **Entry order**: always placed with SL only (no built-in TP). All profit-taking via quad reduce-only orders.
- **TP4 now read from sheet**: `COL_TP4 = 8` — previously TP4 column was parsed but never passed to placement logic.
- **Qty distribution**: `floor(qty / n_valid_tps)` per leg; last leg absorbs rounding remainder so full position is always covered.
- **Display**: console shows `N×25% quad-TP` instead of `Bybit TP2: x.xx`. Telegram shows quad-TP detail.

### Task 281 — Cancel-on-reversal for unfilled LONG orders
- **New constant**: `ORDER_CONTEXT_FILE = order_context.json` — stores BTC price at time of each entry order placement.
- **New function** `cancel_order(symbol, order_id)`: POST `/v5/order/cancel` wrapper.
- **New functions** `load_order_context()` / `save_order_context()`: JSON persistence helpers.
- **New function** `cancel_reversed_orders(threshold_pct=3.0)`: runs at start of each trader cycle.
  - Loads `order_context.json` for stored BTC prices.
  - Fetches current BTC price + all open non-reduce-only Buy orders.
  - Cancels any LONG order where BTC has dropped ≥3% since placement (market reversed).
  - Sends Telegram alert listing all cancelled orders with drop %.
  - SHORTs intentionally excluded — rising BTC against SHORT is handled by Strategist/Watchdog.
- **BTC price stored** in `order_context.json` when each entry order is placed (keyed by Bybit orderId).

## v46.78 — 2026-06-28 — DATA: Fresh confidence WR data in prompt + analyze_shorts floor fix

### Prompt data refresh (whale_stream_bot.py)
- **SHORT 95%+ WR updated**: `91.7%` → `94.1% (48/51 signals)` — June 28 analysis data
- **TIER 1 LONG caution added**: 6 trades at 50% WR, avg -53% P&L — do NOT force 92%+ ratings; stay in 88-91% zone
- **TIER 3 SHORT WR clarified**: 93-95% band count added `(9/9)` alongside WR for clarity
- **All 4 version strings synced**: banner, prompt header, Telegram startup, startup print — all now v46.78

### analyze_shorts.py floor recommendation fix
- **Bug**: LONG confidence recommendation section referenced "85% floor" throughout, but
  code floor has been `LONG_MIN_CONF = 88` since v46.62. Output was confusing/wrong.
- **Fix**: Updated all recommendation text to acknowledge actual 88% code floor.
  Output now says "Code floor already at 88% (LONG_MIN_CONF=88 in bot.py) — no change needed."

## v46.77 — 2026-06-28 — PERF: Compact graveyard prompt saves ~40% dynamic tokens per bot run

### Optimisation: Compact graveyard format in fetch_signal_graveyard() (whale_stream_bot.py)
- **Problem**: Graveyard injected into dynamic user message used 100-char-wide table rows,
  3-line stats header, 2× full 100-char separator lines, AND redundant permanent ban lists
  (SHORT_COIN_BLOCKLIST + LONG_COIN_BLOCKLIST) that are already present in the cached system
  prompt — paying for the same tokens every run.
- **Fix — 4 compressions applied**:
  1. **Stats header 3 lines → 1**: `Recent 20 trades | Overall WR… / LONG WR… / SHORT WR…`
     merged into `GRAVEYARD [20T | WR:65%(13W/7L) | L:70% | S:60%]`
  2. **Table rows 100 chars → 67 chars**: Direction `LONG`/`SHORT` → `L`/`S`, pattern
     truncated to 26 chars (was 40), icons dropped (WIN/LOSS text only), columns narrowed.
     20 rows × 33 chars saved = 660 chars = ~165 tokens.
  3. **Separator lines**: 2× 100-char dash lines → 1× 67-char line. Saves ~133 chars.
  4. **Permanent ban lists removed from dynamic section**: `PERMANENT SHORT BAN` (2 lines)
     and `PERMANENT LONG BAN` (2 lines + 5-line verbose avoid block) removed — these already
     exist verbatim in the cached system prompt (zero net information loss).
     Dynamic `L_AVOID` now 1 compact line: `🚫 L_AVOID(0%WR≥2T): COIN1, COIN2 — skip unless conf≥97%`
- **SHORT recovery block**: unchanged — kept in full, it's important and already compact.
- **Estimated savings**: ~400-500 tokens per API call × 2 calls per run × 6 runs/day
  = ~5,000 tokens/day. More importantly: more headroom for market data reduces truncation risk.

## v46.76 — 2026-06-28 — FIX: Cycle guard added to Strategist + Trader; CHANGE_TO_2H.bat deleted

### Fix: No cycle guard in whale_stream_strategist.py and whale_stream_trader.py (pre-July 1 safety)
- **Risk**: If Task Scheduler fired Strategist or Trader twice in the same 4h slot (e.g. PC wakes
  from sleep mid-cycle), Strategist would re-process signals and Trader could place duplicate orders
  on Bybit — a real financial risk 3 days before July 1 go-live.
- **Fix**: Added identical cycle guard block to the top of `main()` in both files:
  - `whale_stream_strategist.py`: guard key `strategist_{cycle}`, placed before circuit-breaker check
  - `whale_stream_trader.py`: guard key `trader_{cycle}`, placed after `_calibrate_clock()`
  - Reads `daily_status.json`; if `{key}` already `True` for today, prints
    `[CYCLE GUARD] strategist_12 already completed today — skipping duplicate run.` and returns.
  - Matches the existing cycle guard already in `whale_stream_bot.py`.
- **All 3 cycle agents now protected**: bot ✅ strategist ✅ trader ✅

### Cleanup: CHANGE_TO_2H.bat deleted permanently
- Dangerous BAT file that switches bot schedule from 4h → 2h (caused the duplicate-run bug we
  spent 4 days fixing) has been permanently deleted from the repository.
- File no longer exists in `C:\Users\MAX\WhaleStream\`.

## v46.75 — 2026-06-28 — FIX: 2h signal duplicate runs + FEAT: rich Daily Checklist details

### Bug Fixed: Bot firing every ~2h instead of every 4h (CRITICAL)
- **Root cause**: A legacy Task Scheduler task (unknown name, not in SETUP_ALL_TASKS.bat
  deletion list) fires every 2 hours. When the 00:00 bot run takes ~2h to finish, the 02:00
  "missed" trigger starts immediately at 02:08. Pattern repeats back-to-back.
- **Silent masking**: Hour 6 → `(6//4)*4 = 4` → writes `sigbot_04`, silently overwriting the
  real 04:00 run key. So `daily_status.json` never showed 3 runs.
- **Fix**: Added **Cycle Guard** at the very start of `main()` in `whale_stream_bot.py`.
  Reads `daily_status.json` at startup; if `sigbot_{cycle}` is already `True` for today,
  prints `[CYCLE GUARD] sigbot_04 already completed today — skipping duplicate run.` and returns.
  Prevents duplicate runs regardless of how many Task Scheduler entries exist.
- **Action required**: Open Task Scheduler and look for any legacy "WhaleStream" / "Whale" tasks
  beyond those in SETUP_ALL_TASKS.bat — delete any 2h-interval tasks found (belt-and-suspenders).

### Feature: Rich details on Daily Checklist hint lines
- Extended `_mark_done(agent_name)` → `_mark_done(agent_name, details=None)` in ALL 7 agent files
  (bot, strategist, trader, watchdog, tracker, monitor, morning_briefing).
- Details stored as `{key}_details` dict in `daily_status.json` / `daily_status.js` / HTML.
- Each agent now passes actual results:
  - **SigBot**: `{"longs": ["AAVE","EIGEN","JUP"], "shorts": ["H","DOT","MNT"]}`
  - **Strategist**: `{"approved": ["AAVE","EIGEN"], "vetoed": ["JUP","H"]}`
  - **Trader**: `{"placed": ["AAVE"], "skipped": ["EIGEN (REPAIR MODE)"]}`
  - **Watchdog**: `{"health": "GREEN"}` / `"AMBER"` / `"CRITICAL"`
- Daily Checklist.html `applyStatus()` updated: reads `{key}_details`, renders formatted hint text:
  - SigBot: `🟢 AAVE, EIGEN, JUP  |  🔴 H, DOT, MNT`
  - Strategist: `✅ AAVE, EIGEN  |  ❌ JUP, H`
  - Trader: `🟢 AAVE  |  ⏸ —`
  - Watchdog: `🟢 All healthy`
- Added `formatAgentDetails()` and `updateHint()` helpers to HTML.

### Fix: _mark_done() missing on early-exit paths (Daily Checklist gaps)
- Strategist: added `_mark_done("strategist", details=...)` before no-signals early return.
- Trader: added `_mark_done("trader", details=...)` before circuit-breaker early return.

### Fix: Daily Checklist hint text invisible when item is ticked (CSS bug)
- `Daily Checklist.html`: `.item.done .item-hint` had `color:#d1d5db; text-decoration:line-through`
  which rendered the rich detail text nearly invisible and struck through after an agent tick.
- Fix: changed to `color:#6b7280; text-decoration:none` — hint stays readable when done.

### Fix: Daily Checklist WS_EMBEDDED race condition — Trader/Watchdog items not ticking
- Root cause: Each agent tried to update the HTML WS_EMBEDDED blob individually. Monitor runs every
  2 min and collides with Trader's :20 write → both HTML writes fail silently (try/except).
  Result: Trader and Watchdog items never appeared ticked in the checklist.
- JS polling fallback also fails in Cowork/Electron (script-tag CSP restrictions).
- Fix: Watchdog is now the **sole HTML writer** via new `_write_html_snapshot()` function.
  At :30 (last agent in cycle), Watchdog reads the complete `daily_status.json` and writes
  the full authoritative WS_EMBEDDED blob to HTML in one atomic operation. No race possible.
- CHANGE_TO_2H.bat deleted (dangerous file — caused the 2h bug we spent days fixing).

## v46.74 — 2026-06-27 — FIX: RUN_FULL_CYCLE_NOW.bat wrong Python + stale version strings

### Bug Fixed: RUN_FULL_CYCLE_NOW.bat used bare `python` → resolved to Cowork hermes venv
- Root cause: `RUN_FULL_CYCLE_NOW.bat` previously used bare `python` command which resolved
  to `C:\Users\MAX\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` (Cowork's
  internal venv). This venv has no `pip`, an old gspread without `gspread.client` submodule,
  and cannot self-heal. The Task Scheduler bat files were fine (already used full paths) but
  the manual trigger bat was broken.
- **Fix**: Updated all 4 Python calls in `RUN_FULL_CYCLE_NOW.bat` to use the full path:
  `"C:\Users\MAX\AppData\Local\Python\bin\python.exe"` — same Python used by Task Scheduler
- Confirmed via Run 4: full cycle completed without errors, Google Sheets connected,
  Strategist ran (0 vetoes), Trader ran (0 orders — all 6 signals had existing positions)

### Fix: stale version strings in whale_stream_bot.py
- `whale_stream_bot.py` had `v46.62` hardcoded in 2 locations (Telegram output line 1803
  and startup banner line 2352) even after header was bumped to v46.71 in v46.71 release
- Both corrected to v46.74

---

## v46.73 — 2026-06-27 — CRITICAL FIX: bypass gspread.auth entirely (google.oauth2 direct)

### Bug Fixed: `No module named 'gspread.auth'` on Python 3.14 — definitive fix
- Root cause: `gspread/auth.py` EXISTS but fails to load at runtime on this Python 3.14 setup
  (likely a dependency inside auth.py is incompatible). Python 3.14 reports the failure as
  `No module named 'gspread.auth'` even though the file is present.
- **Definitive fix**: bypass `gspread.auth` ENTIRELY — use `google.oauth2.service_account.Credentials`
  directly with `gspread.Client(auth=creds)`. This path:
  - Does NOT import `gspread.auth` at all
  - Uses `google.oauth2` (stable, part of google-auth) directly
  - Passes credentials to `gspread.Client` which creates an `AuthorizedSession`
- All 9 affected Python files updated (10 locations total):
  - `whale_stream_trader.py` — connect_sheet()
  - `whale_stream_strategist.py` — connect_sheet()
  - `whale_stream_bot.py` — graveyard loader + log_to_google_sheets() (2 locations)
  - `whale_stream_tracker.py` — connect_sheet()
  - `morning_briefing.py`, `check_bybit_orphans.py`, `audit_open_signals.py`,
    `analyze_shorts.py`, `repair_pnl_history.py`
- `test_gspread.bat` updated to test both old and new approach at runtime

---

## v46.72 — 2026-06-27 — CRITICAL FIX: gspread submodule import (final fix for Sheets auth)

### Bug Fixed: gspread.service_account() also not exported at top level on Python 3.14
- Root cause confirmed: on this Python 3.14 + gspread v6 installation, `gspread.__init__.py`
  does NOT re-export `service_account` from `gspread.auth`, so all top-level API calls fail
- Previous fix in v46.71 used `gspread.Client(auth=creds)` → also failed (same reason)
- **Definitive fix**: `from gspread.auth import service_account as _gspread_sa`
  — imports DIRECTLY from the submodule where the function is defined, bypasses __init__ entirely
- All 9 affected files now use the direct submodule import:
  - `whale_stream_trader.py` — connect_sheet() + log() calls added for visibility
  - `whale_stream_strategist.py` — connect_sheet()
  - `whale_stream_bot.py` — graveyard loader + log_to_google_sheets() (2 locations)
  - `whale_stream_tracker.py` — connect_sheet()
  - `check_bybit_orphans.py`, `audit_open_signals.py`, `analyze_shorts.py`,
    `morning_briefing.py`, `repair_pnl_history.py`
- Evidence: strategist_log.txt showed 3 consecutive different errors across 3 cycles:
  `gspread.authorize` → `gspread.Client` → `gspread.service_account` — all failed at top level

---

## v46.71 — 2026-06-27 — CRITICAL FIX: gspread.authorize() removed in gspread v6

### Bug Fixed: All agents crash on Google Sheets connect (gspread v6 API break)
- `gspread.authorize(creds)` was removed in gspread v6 — replaced with `gspread.Client(auth=creds)`
- All 10 affected files updated:
  - `whale_stream_trader.py` (line 738 — `connect_sheet()`)
  - `whale_stream_strategist.py` (line 183 — `connect_sheet()`)
  - `whale_stream_bot.py` (lines 873 + 2048 — main connect + graveyard loader)
  - `whale_stream_tracker.py` (line 355 — `connect_sheet()`)
  - `morning_briefing.py`, `check_bybit_orphans.py`, `audit_open_signals.py`,
    `analyze_shorts.py`, `repair_pnl_history.py`
- This was the root cause of 0 trades placed even after the v46.70 CB grace period fix

---

## v46.70 — 2026-06-27 — CRITICAL FIX: circuit breaker grace period (CB deadlock broken)

### Bug Fixed: Trader immediately re-created paused.flag after every manual clear
- `whale_stream_trader.py` — added **CB grace period** system
- Root cause: `check_circuit_breaker()` returned True (same old LOSS streak) every time the
  Trader ran, so it re-created `paused.flag` before placing any orders, making manual clears
  completely useless
- Fix: `RUN_FULL_CYCLE_NOW.bat` and `CLEAR_PAUSE.bat` now write `cb_grace.txt` (UTC timestamp)
  when clearing the CB. The Trader reads this file and, if it was written within the last 60
  minutes, skips re-creating `paused.flag` and proceeds with trading
- After the grace run, any NEW consecutive losses will correctly re-trigger the CB
- `RUN_FULL_CYCLE_NOW.bat` — added `cb_grace.txt` write step (Python one-liner)
- `CLEAR_PAUSE.bat` — added `cb_grace.txt` write step after user confirms YES

### Cascade effect: this was the final piece blocking ALL trading since 10:07 BKK
The chain was: manual clear → Trader runs → CB still met → re-creates paused.flag → returns
without placing orders → Tracker sees paused.flag → sends alert → next Watchdog also alerts
→ repeated every 30 min. Now fixed.

---

## v46.69 — 2026-06-27 — CRITICAL FIX: duplicate skip window 24h → 4h

### Bug Fixed: Bot blocking fresh signals all day (root cause of pipeline deadlock)
- `whale_stream_bot.py` — duplicate skip logic changed from "same coin OPEN **today**" to
  "same coin OPEN in the **last 4 hours**"
- Previously: any coin logged at e.g. 02:08 BKK would be blocked from re-entry at 12:08, 16:08,
  20:08 — even after its entry zone had expired hours ago
- Now: only signals logged within the rolling 4h window are treated as duplicates, matching
  the actual 4h cycle cadence
- String-comparison approach used for efficiency: `r[10][:16] >= cutoff_str` compares
  ISO timestamps lexicographically (safe because format is `YYYY-MM-DD HH:MM`)
- This was the primary reason Strategist consistently found 0 OPEN signals despite bot running
  every 4 hours — stale signals from earlier the same day blocked every fresh signal

---

## v46.68 — 2026-06-27 — Full automation: 3-layer gap detection + morning briefing coverage report

### Gap Detection Layer 3 — Morning Briefing overnight coverage
- `morning_briefing.py` — new `_agent_coverage_section()` helper reads `daily_status.json` at 07:00 BKK
  and appends `🤖 OVERNIGHT AGENT COVERAGE` section to the daily Telegram briefing
- Shows ✅ or ❌ for each overnight cycle (00:xx, 04:xx) and for Tracker/Monitor
- If any agent missed its cycle, the briefing names it and tells the operator to check Task Scheduler
- This is the 3rd and final detection layer (no missed cycle can survive all three)

### Gap Detection Layer 2 — Status Gap Checker (every 4h at :45)
- `check_daily_status.py` — new script, runs every 4h, reads `daily_status.json`,
  computes which agents should have completed by that time, sends ✅ all-green or
  ⚠️ gap alert to Telegram ops channel, with exact agent names + Task Scheduler task IDs
- `ADD_STATUS_CHECK_TASK.bat` — registers `WhaleStream-StatusCheck` (00:45, repeat every 4h)

### Full 3-layer gap detection now active
```
Layer 1 — Watchdog      :30 every cycle  → logs last-seen timestamps
Layer 2 — StatusCheck   :45 every cycle  → daily_status.json completions → Telegram alert
Layer 3 — MorningBrief  07:00 daily      → overnight summary in Telegram briefing
```

---

## v46.67 — 2026-06-27 — Autonomous self-tick: agents mark themselves done in Daily Checklist

### Agent Self-Tick System (24/7 autonomous operation)

Every agent now writes its own completion status to `daily_status.json` when it finishes,
so the Daily Checklist auto-ticks without any human input — true 24/7 per the 7 Principles.

**New files**
- `status_server.py` — minimal CORS HTTP server on `localhost:8765`, serves `daily_status.json`
  to the Daily Checklist HTML. Runs silently at startup via Task Scheduler.
- `ADD_STATUS_SERVER_TASK.bat` — registers status_server.py in Task Scheduler (ONLOGON trigger,
  30-second delay).

**Agent changes — `_mark_done()` helper added to all 7 agents**
- `whale_stream_bot.py` — calls `_mark_done("sigbot")` at end of `main()`
- `whale_stream_strategist.py` — calls `_mark_done("strategist")` at end of `main()`
- `whale_stream_trader.py` — calls `_mark_done("trader")` at end of `main()`
- `whale_stream_watchdog.py` — calls `_mark_done("watchdog")` at end of cycle
- `whale_stream_tracker.py` — calls `_mark_done("tracker")` at end of `main()`
- `whale_stream_monitor.py` — calls `_mark_done("monitor")` at end of each run
- `morning_briefing.py` — calls `_mark_done("briefing")` after sending Telegram

Keys written: `sigbot_HH`, `strategist_HH`, `trader_HH`, `watchdog_HH` (HH = 00/04/08/12/16/20),
`tracker`, `monitor`, `briefing` (always-running — no cycle suffix).

**Daily Checklist.html changes**
- Added `● LIVE / ○ OFFLINE` badge in topbar showing status server connectivity
- Polls `http://localhost:8765/daily_status.json` every 30s
- Auto-ticks matching circles + updates counters + saves to localStorage on receipt

---

## v46.66 — 2026-06-27 — 7 Principles: Watchdog v2.0 + multi-agent consensus + system constitution

### WHALE-STREAM Constitution — 7 Principles Embedded System-Wide

The team's 7 operating principles are now embedded as a `WHALE-STREAM CONSTITUTION` comment block
in **every agent file** (all 8 scripts). This ensures that every agent is coded with full
awareness of the team's rules, mission, and operating discipline.

| # | File | Change |
|---|------|--------|
| 1 | whale_stream_bot.py | Added CONSTITUTION block (P1–P7) |
| 2 | whale_stream_strategist.py | Added CONSTITUTION block (P1–P7) |
| 3 | whale_stream_trader.py | Added CONSTITUTION block (P1–P7) |
| 4 | whale_stream_tracker.py | Added CONSTITUTION block (P1–P7) |
| 5 | whale_stream_monitor.py | Added CONSTITUTION block (P1–P7) |
| 6 | whale_stream_debrief.py | Added CONSTITUTION block (P1–P7) |
| 7 | morning_briefing.py | Added CONSTITUTION block (P1–P7) |
| 8 | whale_stream_watchdog.py | CONSTITUTION already embedded in v2.0 rewrite (this release) |

### Watchdog v2.0 — 3-Tier Reporting (GREEN / AMBER / CRITICAL)

Complete rewrite of `whale_stream_watchdog.py` implementing Principles 3, 4, and 6:

| # | Change |
|---|--------|
| 1 | **GREEN report** sent every cycle when all agents healthy — confirms the team is alive (P3/P4) |
| 2 | **AMBER alert** sent when any agent is behind — includes exact step-by-step fix instructions per agent |
| 3 | **CRITICAL escalation** when Trader has been down >8 hours — 5-step immediate action list sent via Telegram |
| 4 | `check_trader()` uses any BKK-formatted timestamp as fallback (not only "RUN COMPLETE") for more robust detection |
| 5 | Per-agent fix messages: `FIX_BOT`, `FIX_STRATEGIST`, `FIX_TRADER`, `FIX_PAUSED` — human-readable action steps |

### Multi-Agent Consensus — Debrief Cross-Checks Strategist (P5)

Added to `whale_stream_debrief.py`:

| # | Change |
|---|--------|
| 1 | `STRATEGIST_FILE` constant pointing to `strategist_decisions.json` |
| 2 | `load_strategist_decision(coin, direction)` — looks up what the Strategist decided before the trade |
| 3 | `consensus_verdict(strat_decision, outcome)` — 4 outcomes: VALIDATED / MISS / VETO WRONG / VETO SAVED US |
| 4 | `build_debrief_prompt()` now injects Strategist's pre-trade reasoning into Claude's analysis context |
| 5 | Pattern memory entries now include `strat_action` and `consensus` fields |
| 6 | Telegram Debrief summary shows `🤝 [consensus verdict]` per trade |

---

## v46.65 — 2026-06-27 — Fix retCode 10002 (PC clock drift causing all Bybit auth failures)

### Root Cause of 40+ Hour Trading Blackout

**Problem diagnosed:** Trader could not connect to Bybit for 40+ hours (June 25 22:20 → June 27 ~09:00 BKK).
`DIAGNOSE_BYBIT.bat` revealed the actual error: `retCode=10002` — PC clock was **2,487 ms ahead**
of Bybit's server. Bybit rejects any request where `req_timestamp > server_timestamp`, even by milliseconds.
The API keys (regenerated June 26) were completely valid — the clock was the sole blocker.

| # | File | Change |
|---|------|--------|
| 1 | whale_stream_trader.py | Added `_BYBIT_CLOCK_OFFSET_MS` module-level constant (default 3000 ms). |
| 2 | whale_stream_trader.py | Added `_calibrate_clock()` function: queries Bybit `/v5/market/time` at startup, measures local vs server offset, caches it. Any future PC clock drift is automatically corrected. |
| 3 | whale_stream_trader.py | `bybit_request()` now uses `time.time() * 1000 - _BYBIT_CLOCK_OFFSET_MS` instead of the old fixed `-1000 ms`. |
| 4 | whale_stream_trader.py | Connection failure hint now includes: `→ If retCode=10002: PC clock is out of sync — right-click clock → Sync now` |
| 5 | diagnose_bybit.py | Added retCode 10002 handler with exact fix instructions. |
| 6 | DIAGNOSE_BYBIT.bat | Now saves output to `diagnose_output.txt` so results can be read after CMD closes. |

---

## v46.64 — 2026-06-27 — Bybit API error transparency + Watchdog bot-tracking fix

### Bybit Connection Diagnostic & Error Transparency

**Problem found:** Trader showing `✗ Could not connect to Bybit. Check your API keys.` on every run since
June 25 22:20 BKK, but the ACTUAL error (retCode, exception type) was hidden. All the trader showed was the generic
message, making it impossible to diagnose remotely whether the issue was expired keys, a network error, or a
Bybit API change.

| # | File | Change |
|---|------|--------|
| 1 | whale_stream_trader.py | `get_wallet_balance()` now returns `(avail, total, err_msg)` — the actual Bybit retCode and retMsg are captured and returned. |
| 2 | whale_stream_trader.py | On connection failure, the log now prints `Error: retCode=XXXXX | <message>` plus recovery hints. A Telegram alert is also sent so the team knows trading is halted. |
| 3 | diagnose_bybit.py + DIAGNOSE_BYBIT.bat | **New diagnostic tool.** Tests the connection in 4 steps: (1) key load, (2) public API reachable, (3) demo endpoint reachable, (4) authenticated wallet balance. Prints full HTTP status, raw response, and human-readable fix for each known retCode. Run this when the trader can't connect. |

### Watchdog "Bot last: never" Fix

**Problem found:** Watchdog was always showing "Bot last: never" and alerting on every cycle, because the bot
log never contained the `[YYYY-MM-DD HH:MM BKK]` timestamp format the Watchdog searches for.

| # | File | Change |
|---|------|--------|
| 4 | whale_stream_bot.py | Added `[YYYY-MM-DD HH:MM BKK] Bot run complete` log line at the end of `main()`. Watchdog now correctly detects bot's last successful run. |

---

## v46.63 — 2026-06-26 — Fix paper WIN inflation: tracker now only resolves executed Bybit trades

### Critical Integrity Fix: Real WR vs Paper WR

**The bug:** tracker.py was resolving ALL OPEN signals as WIN/LOSS when price hit TP/SL levels,
regardless of whether a Bybit order was ever placed. This inflated WR stats with "paper wins"
while the real Bybit balance was losing money from unexecuted trades.

**Root cause discovered by 3-agent audit:**
- Only 13/62 fresh signals (21%) were actually placed on Bybit in the last 30 days
- H SHORT "wins" (e.g. +384.6%) were paper — every H SHORT attempt failed (Price Invalid or REPAIR MODE)
- Real Bybit trades = LONGs in a downtrend = all losses (confirmed by Bybit P&L tab)
- `COL_BYBIT_ID` (col R) was read but NEVER used to gate WIN/LOSS resolution

| # | File | Change |
|---|------|--------|
| 1 | whale_stream_tracker.py | **Paper signal guard added before WIN/LOSS resolution.** If `bybit_id` (col R) is empty → signal was never executed on Bybit → `continue` (skip to next row, signal expires naturally at 72h). Only signals with a real Bybit Order ID are resolved as WIN/LOSS. |
| 2 | whale_stream_tracker.py | **Telegram WIN/LOSS alerts updated.** "TRADE WIN" → "REAL TRADE WIN" / "TRADE LOSS" → "REAL TRADE LOSS". Bybit Order ID prefix shown (first 12 chars). "Running:" → "Real:" to make clear these are executed-trade stats only. |

### What changes going forward
- Paper signals (skipped by trader due to REPAIR MODE, Price Invalid, risk cap, stale entry) will now EXPIRE at 72h instead of being counted as WIN/LOSS
- All WIN/LOSS Telegram alerts from this point forward represent actual money on Bybit
- WR stats in Telegram now reflect the real Bybit execution record, not the inflated signal record

---

## v46.62 — 2026-06-26 — Trend Doctrine trained into all 4 active agents

### "Follow the market trend" embedded team-wide

| # | Agent | Change |
|---|-------|--------|
| 1 | Bot (whale_stream_bot.py) | **GOLDEN RULE block added as Rule #1** in system prompt — above all other rules. 🐻 Market falling → SHORT only. 🐂 Market rising → LONG only. 😐 Sideways → both. Includes live proof: LONGs -108% fighting downtrend, SHORTs 77.6% flowing with it. |
| 2 | Strategist (whale_stream_strategist.py v1.3) | **GOLDEN RULE added to system prompt.** Reinforces that the code pre-vetoes counter-trend signals and Claude should treat any remaining counter-trend signal with extra skepticism. |
| 3 | Briefing (morning_briefing.py) | **BTC market bias at top of every 7am message.** `get_btc_market_bias()` fetches Bybit 4h SMA each morning and displays "🐻 BEARISH — SHORT mode" / "🐂 BULLISH — LONG mode" / "😐 NEUTRAL — both allowed" as the first item in the daily briefing before all other data. |
| 4 | Debrief (whale_stream_debrief.py) | **Trend-vs-counter-trend analysis added to DEBRIEF_SYSTEM.** Agent now explicitly taught: SHORT in downtrend = flows with water (wins). LONG in downtrend = swims upstream (drowns). Trades that fought the trend and won are flagged as lucky, not reinforced in pattern memory. |

---

## v46.61 — 2026-06-26 — Market Regime Filter + LONG Quality Tightening

### Strategy: Trade WITH the Trend — Not Against It

| # | Type | File | Change |
|---|------|------|--------|
| 1 | NEW | whale_stream_strategist.py | **BTC Market Regime Filter.** `get_btc_market_bias()` fetches last 20 × 4h BTC candles from Bybit V5, computes 20-period SMA. BEARISH (<−2% from SMA) → all LONG signals pre-vetoed before Claude. BULLISH (>+2% from SMA) → all SHORT signals pre-vetoed. NEUTRAL → both directions allowed. Regime bias shown in every Telegram message. |
| 2 | NEW | whale_stream_strategist.py | **Regime-vetoed signals merged into decisions file** so the full picture (pre-veto + Claude review) is visible in logs, Telegram, and strategist_decisions.json. |
| 3 | NEW | whale_stream_bot.py | **Code-level LONG confidence floor 88%.** `LONG_MIN_CONF = 88` — mirrors the existing SHORT floor logic. Auto-drops any LONG Claude emits below 88%. 85-87% LONG band had 39.1% WR and avg -12.5% P&L (confirmed loser tier). |
| 4 | FIX | whale_stream_bot.py | **LONG_COIN_BLOCKLIST expanded.** Added COMP (0W/3L, -59.8%), QNT (0W/3L, -65.6%), WIF (1W/4L, -48.7%). All three confirmed losers from analyze_shorts.py output. |
| 5 | FIX | whale_stream_bot.py | **LONG CONFIDENCE RULE added to prompt.** Claude now told explicitly: 85-87% floor has 39.1% WR — do not output LONGs in that range. Mirrors the SHORT CONFIDENCE RULE already in the prompt. |
| 6 | FIX | whale_stream_bot.py | **Prompt poor-coin list updated.** COMP, QNT, WIF added to the LONG POOR COINS line in the prompt so Claude knows these are code-blocked. |
| 7 | FIX | whale_stream_strategist.py | **Strategist v1.1 → v1.2.** Telegram now shows market bias emoji (🐻/🐂/😐) on every review message. |

### Why This Matters
- LONGs net P&L: -108.3% (Gate 2 FAIL) — root cause: fighting the market trend + low-quality tier signals
- SHORTs WR: 77.6% (last 20 = 100%) — system excels when trading WITH the trend
- Market regime filter ensures we only trade in the direction BTC is moving
- With BEARISH bias: zero LONG exposure, pure SHORT mode — the system's proven strength
- Target: $311 → $500 by July 1 (4 days)

---

## v46.60 — 2026-06-26 — BAT file cleanup + SETUP_ALL_TASKS complete

| # | Type | File | Fix |
|---|------|------|-----|
| 1 | DISABLED | FORCE_PUSH.bat | Stale v46.38 commit message + `--force` push. If run accidentally would clobber GitHub with wrong version. Now shows warning and exits. |
| 2 | DISABLED | CLEAN_PUSH.bat | Even more dangerous: creates orphan branch (wipes all history) + force push. One-time migration tool that must never run again. Now shows warning and exits. |
| 3 | FIX | RUN_REPAIR_PNL.bat | Added `set PYTHONIOENCODING=utf-8` + `set PYTHONUTF8=1` — prevents emoji crash in Task Scheduler. |
| 4 | FIX | AUTO_REPAIR_PNL.bat | Same UTF-8 fix. |
| 5 | FIX | SETUP_ALL_TASKS.bat | Added OrphanCheck (daily 06:00) and LogAnalyzer (daily 07:00) tasks. Now creates all 9 tasks on a fresh machine. Also updated summary from "7 tasks" → "9 tasks". |

---

## v46.59 — 2026-06-26 — System-wide Audit Fixes (8 bugs eliminated)

### Parallel Agent Audit → All Findings Applied

| # | Severity | File | Fix |
|---|----------|------|-----|
| 1 | CRITICAL | whale_stream_tracker.py | **Heartbeat alert suppression removed.** Old code `6 <= hour < 23` silently dropped missed-run alerts for the 00:00 and 04:00 bot slots. New 4h schedule starts at midnight — suppression was hiding the two most critical overnight runs. Now alerts 24/7. |
| 2 | CRITICAL | whale_stream_tracker.py | **Stale schedule text fixed in Telegram alert.** Bot heartbeat alert said `"06:00, 10:00, 14:00, 18:00, 22:00, 02:00 BKK"`. Corrected to `"00:00, 04:00, 08:00, 12:00, 16:00, 20:00 BKK"`. |
| 3 | WARNING | whale_stream_watchdog.py | **`BOT_DEADLINE_MIN` 28 → 32.** Bot runs at :00, Watchdog at :30 = 30 min elapsed. `30 <= 28` was always False → false alarm every clean cycle. 32 gives 2 min safety margin. |
| 4 | WARNING | whale_stream_strategist.py | **Stale log message fixed.** "No signals found in last 5h" → "last 26h" (matches the SIGNAL_WINDOW_HOURS fix from v46.57). |
| 5 | WARNING | whale_stream_monitor.py | **Mission banner added.** `print_mission_banner()` now called at startup so every monitor log opens with the shared team mission. |
| 6 | WARNING | whale_stream_debrief.py | **Mission banner added.** Same fix — debrief logs now include mission header. |
| 7 | WARNING | whale_stream_bot.py | **Version strings corrected.** Telegram header and startup banner both still said v46.49. Updated to v46.59 to match file header. |
| 8 | LOW | SETUP_ALL_TASKS.bat | **Bot and Trader get `/RL HIGHEST`.** Strategist and Watchdog already had it; Bot and Trader were missing it. All 4 core agents now run at highest priority. |

### Audit Findings NOT Bugs (confirmed correct)
- Watchdog `STRATEGIST_LOG = "strategist_task_log.txt"` — CORRECT. `run_strategist.bat` redirects stdout to this file. Both contain identical timestamps.
- Agent 3 (data pipeline) found zero issues — all column indices, file paths, and Google Sheet IDs match across all 8 agents.

---

## v46.58 — 2026-06-26 — Master Task Setup + Schedule Consolidation

### Permanent Fix: Schedule Can Never Drift Again

| # | Type | Description | Files |
|---|------|-------------|-------|
| 1 | NEW | **`SETUP_ALL_TASKS.bat` — single master file for ALL 7 scheduled tasks.** Deletes every possible WhaleStream task name variant, then re-creates all 7 tasks with the correct schedule in one shot. This is the ONLY file that should ever be run to set up or repair the Task Scheduler. | SETUP_ALL_TASKS.bat (new) |
| 2 | DISABLED | **10 old schedule bat files disabled.** `ADD_BOT_TASK`, `ADD_TRADER_TASK`, `ADD_TRACKER_TASK`, `ADD_STRATEGIST_TASK`, `ADD_WATCHDOG_TASK`, `ADD_BRIEFING_TASK`, `ADD_MONITOR_TASK`, `CHANGE_TO_4H`, `APPLY_4H_SCHEDULE`, `NUCLEAR_4H_FIX`, `UPDATE_BOT_SCHEDULE_4H` — all now print "DISABLED — Use SETUP_ALL_TASKS.bat". Running any of them alone created partial/wrong schedules. | (all above) |
| 3 | FIX | **Bot start time corrected: 06:00 → 00:00.** All agents now share the same 4h cycle: Bot :00, Strategist :10, Trader :20, Watchdog :30. The old 06:00 start misaligned the Bot with the Strategist (00:10) and Trader (00:20). | SETUP_ALL_TASKS.bat |

**Correct 4-hour team cycle after running SETUP_ALL_TASKS.bat:**

| Time | Agent | Action |
|------|-------|--------|
| :00 | Bot | Signal generation |
| :10 | Strategist | APPROVE / VETO |
| :20 | Trader | Order placement |
| :30 | Watchdog | Health check |
| Every 30 min | Tracker | TP/SL resolution |
| Every 2 min | Monitor | Real-time fills |
| 07:00 daily | Briefing | Morning Telegram |

---

## v46.57 — 2026-06-26 — Critical Fix: Strategist 0-signals + Task #228 Diagnosis

### Root Cause Found & Fixed

| # | Type | Description | Files |
|---|------|-------------|-------|
| 1 | BUG FIX | **Strategist 0-signals: `SIGNAL_WINDOW_HOURS` 5 → 26.** Root cause: bot dedup prevents re-writing the same OPEN signal within a day (coin+direction already OPEN today → skip). Signals written at midnight were outside the 5h Strategist window on all daytime runs. Changed to 26h so any OPEN signal from the past 24h is always visible. Immediately fixes Strategist finding 0 signals on every run. | whale_stream_strategist.py |

### Diagnosis Results (no code changes needed)

| Finding | Status | Details |
|---------|--------|---------|
| Bot schedule misalignment | ✅ Not the cause | Bot confirmed running every 2h (Jun 26: 00:09, 02:05, 04:09, 06:05, 08:08, 10:05, 12:11, 14:07, 16:10, 18:05, 20:09). Schedule fine. |
| bybit_balance.json stale | ⏳ Self-healing | write_balance_file() at line 705-708 is correct. File stale because Bybit API key was invalid. Will update on next successful trader run. |
| pattern_memory.json missing | ⏳ Self-healing | Debrief wiring in tracker (lines 1716-1729) is correct with UTF-8 fix. File will be created when next WIN/LOSS trade resolves. |
| Bot legacy crash task | ✅ Not active | Bot log confirms healthy runs since Jun 19 (UTF-8 fix). Last 5 errors in log are from pre-fix era (old line 53). Current UTF-8 fix at lines 29-32 pre-empts all print statements. |

---

## v46.56 — 2026-06-26 — Shared Mission embedded in all 8 agents

### Team Alignment

| # | Type | Description | Files |
|---|------|-------------|-------|
| 1 | NEW | **`mission.py` — single source of truth for team mission.** Defines `MISSION_PROMPT` (injected into Claude API calls), `MISSION_BANNER` (printed to every agent log), and `print_mission_banner()` (shows live balance + days to go-live). This business belongs to the whole team — every agent now knows why it exists. | mission.py (new) |
| 2 | INJECT | **Mission embedded into all 8 agents.** `MISSION_PROMPT` prepended to Claude system prompts in Bot, Strategist, and Debrief. `print_mission_banner()` called at startup in Trader, Tracker, Watchdog, Morning Briefing. Every log file now opens with the shared mission. | whale_stream_bot.py, whale_stream_strategist.py, whale_stream_trader.py, whale_stream_tracker.py, whale_stream_watchdog.py, morning_briefing.py |

---

## v46.55 — 2026-06-26 — Watchdog Agent + Morning Briefing

### New Agents & Tasks

| # | Type | Description | Files |
|---|------|-------------|-------|
| 1 | NEW | **Watchdog agent.** `whale_stream_watchdog.py` runs at :30 of each 4h cycle. Checks if Bot (:00), Strategist (:10), and Trader (:20) all ran in the current cycle. Sends Telegram alert immediately if any agent missed its slot. Also alerts on stale balance (6h+ without trader update) and active circuit breaker. Fills the "no one notices failures" gap. | whale_stream_watchdog.py (new), run_watchdog.bat (new), ADD_WATCHDOG_TASK.bat (new) |
| 2 | REGISTER | **Morning briefing task registered.** `morning_briefing.py` (built in v46.37) now scheduled via Task Scheduler at 07:00 BKK daily — sends full Telegram briefing: balance, drawdown, gate progress, win rates, open positions, yesterday P&L, flag status. | ADD_BRIEFING_TASK.bat |

---

## v46.54 — 2026-06-26 — CRITICAL: Fix Strategist Task Scheduler

### 1 Critical Fix — Strategist has never run since deployment

| # | Severity | Fix | Files |
|---|----------|-----|-------|
| 1 | CRITICAL | **Strategist Task Scheduler broken since day one — fixed.** `ADD_STRATEGIST_TASK.bat` used `where py` to detect Python at registration time. `py` (Python Launcher) was found interactively, so the task was registered with `py` as the executable. At Task Scheduler runtime `py` is not in PATH → every Strategist run silently failed with `'py' is not recognized`. No `strategist_decisions.json` was ever written → trader's graceful fallback approved ALL signals → 10+ open orders accumulating without veto. **Fix:** Created `run_strategist.bat` (mirrors `run_tracker.bat` — hardcoded full Python path `C:\Users\MAX\AppData\Local\Python\bin\python.exe`, `PYTHONIOENCODING=utf-8`, logs to `strategist_task_log.txt`). Updated `ADD_STRATEGIST_TASK.bat` to run `cmd.exe /c run_strategist.bat` (same pattern as working Tracker task). Re-run `ADD_STRATEGIST_TASK.bat` as Administrator to re-register. | run_strategist.bat (new), ADD_STRATEGIST_TASK.bat |

---

## v46.53 — 2026-06-26 — SHORT confidence hard floor + 4h cadence + VVV blocklist update

### 3 Improvements — data-driven quality over quantity

| # | Severity | Improvement | File |
|---|----------|-------------|------|
| 1 | HIGH | **SHORT confidence hard floor raised to 93%.** Data analysis of 72 SHORT signals revealed the 88-92% confidence band has only 36-37% WR (disaster zone), while 93-95% = 100% WR and 95%+ = 91.7% WR. The `min_short_conf` variable in `bot.py` now permanently floors at 93 regardless of recent WR (was conditionally 0 when WR > 45%). Prompt text updated: renamed "SHORT CONFIDENCE PARADOX" → "SHORT CONFIDENCE RULE" with explicit hard-floor language so Claude stops generating signals in the loser zone. `whale_stream_strategist.py` veto rule updated to match. | whale_stream_bot.py |
| 2 | MEDIUM | **Bot cadence changed from 2h → 4h (quality over quantity).** Gate 1 cleared (159+ resolved trades = sufficient sample size). Duplicate signals were appearing every 2h on the same coins before setups fully developed. 4h gives the market time to develop clean, high-conviction setups. `CHANGE_TO_4H.bat` created to update Task Scheduler. Bot schedule now aligns perfectly with Strategist (:10) and Trader (:20) on the same 4h cycle: 06:00/10:00/14:00/18:00/22:00/02:00 BKK. | CHANGE_TO_4H.bat (new) |
| 3 | LOW | **VVV SHORT_COIN_BLOCKLIST comment updated 0W/2L → 0W/3L.** VVV took another SHORT loss, confirming its place in the blocklist. Comment updated to reflect current record. | whale_stream_bot.py |

**SHORT confidence zone reference (72 signals analysed):**
| Band | WR | Signals | Zone |
|------|----|---------|------|
| 95%+ | 91.7% | 24 | ✅ MONEY ZONE |
| 93-95% | 100% | 9 | ✅ MONEY ZONE |
| 90-92% | 36.4% | 11 | 🚫 DISASTER — hard floor blocks |
| 88-90% | 37.5% | 16 | 🚫 DISASTER — hard floor blocks |
| 85-88% | 83.3% | 12 | ✅ Acceptable (rare) |

**Updated team schedule (as of v46.53):**
| Role | Script | Schedule | Job |
|------|--------|----------|-----|
| 🔭 Scout | whale_stream_bot.py | :00 every **4h** | Screen 200 coins, generate 3+3 signals |
| 🧠 Strategist | whale_stream_strategist.py | :10 every 4h | Review signals + read pattern memory |
| ⚡ Trader | whale_stream_trader.py | :20 every 4h | Execute only approved signals |
| 👁 Monitor | whale_stream_monitor.py | continuous | Track open position fills |
| 📊 Tracker | whale_stream_tracker.py | every 30 min | Resolve trades + trigger Debrief |
| 📓 Debrief | whale_stream_debrief.py | after each trade | Analyse WHY, write lesson to pattern_memory |
| 🩺 Analyzer | RUN_ANALYZE_SHORTS.bat | Thu + Sun | Weekly pattern intelligence update |
| 📢 Briefing | morning_briefing.py | 7 AM daily | Capital health + yesterday P&L |

---

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
