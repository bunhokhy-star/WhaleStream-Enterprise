# 🐳 WHALE-STREAM — Autonomous Crypto Trading System

**Current version:** v46.41  
**Status:** Live on Bybit Demo · Gate 1 in progress · July 1 go-live target

---

## What This Is

WHALE-STREAM is a fully autonomous cryptocurrency trading bot powered by Claude (Anthropic AI). It runs 24/7, analyzes market conditions across 50+ coins, generates high-confidence trade signals, and executes orders on Bybit — with no human intervention required after setup.

The system is built to be **institutional-grade in discipline, retail-accessible in cost.**

---

## The Mission

This project exists to build a sustainable, compounding income stream — with profits directed toward supporting people in poverty and disadvantaged communities. Every edge we build in the algorithm is capital that can do real good in the world.

---

## How It Works

```
Every 4 hours:
  whale_stream_bot.py        ← Claude analyzes 50+ coins, outputs 5 LONG signals
  whale_stream_trader.py     ← Places real orders on Bybit (demo → live July 1)
  whale_stream_tracker.py    ← Tracks open trades, resolves WIN/LOSS, updates Sheets
  whale_stream_monitor.py    ← Near-real-time fill detection between runs
  morning_briefing.py        ← 7am Bangkok daily Telegram summary
```

---

## Key Features

- **Claude AI signal generation** — institutional market regime analysis, tournament-style coin scoring
- **Macro Event Guard** — hardcoded FOMC/CPI calendar (2026), auto-avoids entries 4h before events
- **Token Unlock Calendar** — DefiLlama API integration, warns on ≥3% supply unlocks in 48h
- **SHORT Repair Mode** — automatic flag-file system, selective unlock for recovery coins
- **Circuit Breaker** — pauses trading after 3 consecutive losses
- **TP1 → SL-to-breakeven** — risk-free position management after first target hit
- **Partial close at TP1** — 50% lock-in, let the rest run to TP2/TP3
- **Gate system** — 6 gates between demo and live capital deployment
- **Telegram notifications** — every order, WIN/LOSS, weekly P&L, Gate 1 progress

---

## Gate System (Demo → Live)

| Gate | Requirement | Status |
|------|-------------|--------|
| Gate 1 | 100/150 resolved trades | 🟡 In progress |
| Gate 2 | LONG win rate ≥ 60% | 🟡 Accumulating |
| Gate 3 | SHORT win rate ≥ 50% | 🟡 In repair mode |
| Gate 4 | Max drawdown < 15% | 🟡 Monitoring |
| Gate 5 | Real capital checklist passed | ✅ Pre-approved |
| Gate 6 | 3 consecutive profitable weeks | 🟡 Accumulating |

---

## Setup

### Prerequisites
- Python 3.10+
- Bybit Demo account (api-demo.bybit.com)
- Claude API key (console.anthropic.com)
- Telegram Bot (via @BotFather)
- Google Sheets + Service Account (`google_credentials.json`)

### Installation

```bash
git clone https://github.com/bunhokhy-star/WhaleStream-Enterprise.git
cd WhaleStream-Enterprise
pip install anthropic gspread requests pybit
```

### Configuration

```bash
cp local_config.py.example local_config.py
# Edit local_config.py with your real API keys (never committed to git)
```

Add your `google_credentials.json` to the project root (also gitignored).

### Schedule (Windows Task Scheduler)

Run the `.bat` files as Administrator to register automated tasks:

```
ADD_BOT_TASK.bat       ← Bot every 4 hours
ADD_TRADER_TASK.bat    ← Trader 20 min after bot
ADD_TRACKER_TASK.bat   ← Tracker 40 min after bot
ADD_MONITOR_TASK.bat   ← Monitor every 30 min
ADD_BRIEFING_TASK.bat  ← Morning briefing 7am daily
```

---

## Architecture

```
whale_stream_bot.py      Main AI engine — Claude API, signal generation
whale_stream_tracker.py  WIN/LOSS resolver, Google Sheets, dashboard
whale_stream_trader.py   Bybit order placement, risk management
whale_stream_monitor.py  Fill detector, TP/SL monitor
analyze_shorts.py        Performance analytics, gate status
morning_briefing.py      Daily Telegram briefing
check_bybit_orphans.py   Orphan position detector
analyze_logs.py          Log health reporter
```

---

## Security

- **`google_credentials.json`** — gitignored, never committed
- **`local_config.py`** — gitignored, never committed (use `local_config.py.example` as template)
- All API keys loaded at runtime from local config, never hardcoded in source

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.

---

*Built with purpose. Every trade is a step toward something that matters.*
