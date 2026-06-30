#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║    WHALE-STREAM v47.46 — Market Intelligence Module          ║
║                                                              ║
║  Provides three real-data layers BEFORE signal selection:    ║
║  1. Fear & Greed Index  (alternative.me — free)              ║
║  2. Bybit Funding Rate + Open Interest  (public endpoint)    ║
║  3. 4H Candle Technical Indicators: RSI14, EMA20/50,         ║
║     Volume ratio, ATR14, Trend direction                     ║
║                                                              ║
║  All endpoints are PUBLIC — no API key required.             ║
║  Called by whale_stream_bot.py before Claude signal prompt.  ║
║  Writes market_context.json for strategist + briefing.       ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import io
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# Force UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
elif hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BKK = timezone(timedelta(hours=7))
BYBIT_PUBLIC_URL = "https://api.bybit.com"   # always public URL, same for demo + live
SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
MARKET_CTX_FILE  = os.path.join(SCRIPT_DIR, "market_context.json")


# ══════════════════════════════════════════════════════════════════
# FUNCTION 1 — Fear & Greed Index
# ══════════════════════════════════════════════════════════════════

def get_fear_greed() -> dict:
    """
    Fetch Crypto Fear & Greed Index from alternative.me.
    Returns dict with value, label, signal, long_bias, note.
    Never crashes — returns NEUTRAL default on any error.
    """
    try:
        r = requests.get(
            "https://api.alternative.me/fng/?limit=1",
            timeout=8
        )
        r.raise_for_status()
        data  = r.json()["data"][0]
        value = int(data["value"])
        label = data["value_classification"]

        if value <= 25:
            signal    = "EXTREME_FEAR"
            long_bias = "BLOCK"
            note      = f"F&G {value} ({label}) — BLOCK all LONGs, SHORT-only mode"
        elif value <= 40:
            signal    = "FEAR"
            long_bias = "REDUCE"
            note      = f"F&G {value} ({label}) — max 1 LONG, require conf ≥95%"
        elif value <= 60:
            signal    = "NEUTRAL"
            long_bias = "NORMAL"
            note      = f"F&G {value} ({label}) — standard rules apply"
        elif value <= 75:
            signal    = "GREED"
            long_bias = "NORMAL"
            note      = f"F&G {value} ({label}) — standard rules apply"
        else:
            signal    = "EXTREME_GREED"
            long_bias = "REDUCE"
            note      = f"F&G {value} ({label}) — raise LONG floor to 95%, squeeze risk high"

        print(f"   📡 F&G: {value} ({label}) → {signal}")
        return {"value": value, "label": label, "signal": signal,
                "long_bias": long_bias, "note": note}

    except Exception as e:
        print(f"   ⚠ F&G fetch failed: {e} — using NEUTRAL default")
        return {"value": 50, "label": "Unknown", "signal": "NEUTRAL",
                "long_bias": "NORMAL", "note": "F&G unavailable — standard rules apply"}


# ══════════════════════════════════════════════════════════════════
# FUNCTION 2 — Bybit Funding Rate + Open Interest
# ══════════════════════════════════════════════════════════════════

def get_funding_oi(symbols: list) -> dict:
    """
    Fetch Bybit funding rate + open interest for a list of USDT symbols.
    symbols: ["BTCUSDT", "ETHUSDT", ...]
    Returns dict keyed by base coin (BTC, ETH, ...):
        {
            "BTC": {
                "funding_rate": 0.0002,
                "oi_usd": 5_000_000_000,
                "bias": "NEUTRAL",
                "note": "Funding 0.020% — balanced"
            }, ...
        }
    """
    result = {}
    symbols = symbols[:40]   # cap at 40

    for sym in symbols:
        try:
            r = requests.get(
                f"{BYBIT_PUBLIC_URL}/v5/market/tickers",
                params={"category": "linear", "symbol": sym},
                timeout=8
            )
            r.raise_for_status()
            item = r.json().get("result", {}).get("list", [{}])[0]
            fr   = float(item.get("fundingRate", 0) or 0)
            oi   = float(item.get("openInterest", 0) or 0)

            if fr > 0.0005:
                bias = "CROWDED_LONG"
                note = f"Funding {fr*100:.3f}% — longs crowded, dump risk"
            elif fr < -0.0005:
                bias = "CROWDED_SHORT"
                note = f"Funding {fr*100:.3f}% — shorts crowded, squeeze risk"
            else:
                bias = "NEUTRAL"
                note = f"Funding {fr*100:.3f}% — balanced"

            coin = sym.replace("USDT", "")
            result[coin] = {"funding_rate": fr, "oi_usd": oi, "bias": bias, "note": note}
            time.sleep(0.05)

        except Exception as e:
            coin = sym.replace("USDT", "")
            print(f"   ⚠ Funding/OI fetch failed for {sym}: {e}")
            result[coin] = {"funding_rate": 0.0, "oi_usd": 0.0,
                            "bias": "NEUTRAL", "note": "Data unavailable"}

    crowded = [c for c, v in result.items() if v["bias"] != "NEUTRAL"]
    print(f"   📊 Funding/OI: {len(result)} coins fetched"
          + (f" | Crowded: {', '.join(crowded)}" if crowded else " | All balanced"))
    return result


# ══════════════════════════════════════════════════════════════════
# FUNCTION 3 — 4H Candle Technical Indicators
# ══════════════════════════════════════════════════════════════════

def _ema(values: list, period: int) -> float:
    """Compute EMA of a price series. Returns last EMA value."""
    if len(values) < period:
        return sum(values) / len(values)
    k   = 2.0 / (period + 1)
    ema = sum(values[:period]) / period   # seed with SMA
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _rsi(closes: list, period: int = 14) -> float:
    """Wilder's RSI(14) from a list of closing prices (oldest first)."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def _atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """ATR(14) as percentage of last close."""
    if len(closes) < 2:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i]  - closes[i - 1])
        )
        trs.append(tr)
    atr_val = sum(trs[-period:]) / min(len(trs), period)
    return round(atr_val / closes[-1] * 100, 2) if closes[-1] else 0.0


def get_coin_indicators(symbols: list) -> dict:
    """
    Fetch 4H candles from Bybit and compute technical indicators.
    symbols: ["BTCUSDT", "ETHUSDT", ...]
    Returns dict keyed by base coin:
        {
            "BTC": {
                "rsi_4h":    58.2,
                "ema20":     65000.0,
                "ema50":     63000.0,
                "ema_signal": "BULL",
                "vol_ratio": 1.3,
                "vol_label": "HIGH",
                "atr_pct":   2.1,
                "trend":     "UP",
                "summary":   "RSI=58 EMA=BULL(20>50) VOL=HIGH ATR=2.1% TREND=UP"
            }, ...
        }
    """
    result  = {}
    symbols = symbols[:40]   # cap at 40

    for sym in symbols:
        try:
            r = requests.get(
                f"{BYBIT_PUBLIC_URL}/v5/market/kline",
                params={"category": "linear", "symbol": sym,
                        "interval": "240", "limit": "55"},
                timeout=10
            )
            r.raise_for_status()
            raw = r.json().get("result", {}).get("list", [])
            if len(raw) < 20:
                time.sleep(0.1)
                continue

            # Bybit returns newest first — reverse to oldest→newest
            raw    = list(reversed(raw))
            opens  = [float(c[1]) for c in raw]
            highs  = [float(c[2]) for c in raw]
            lows   = [float(c[3]) for c in raw]
            closes = [float(c[4]) for c in raw]
            vols   = [float(c[5]) for c in raw]

            rsi_val  = _rsi(closes)
            ema20    = round(_ema(closes, 20), 6)
            ema50    = round(_ema(closes, 50), 6)
            atr_pct  = _atr(highs, lows, closes)
            last_vol = vols[-1]
            avg_vol  = sum(vols[-20:]) / 20 if len(vols) >= 20 else sum(vols) / len(vols)
            vol_ratio = round(last_vol / avg_vol, 2) if avg_vol else 1.0

            ema_signal = "BULL" if ema20 > ema50 else "BEAR"
            vol_label  = "HIGH" if vol_ratio > 1.5 else ("LOW" if vol_ratio < 0.7 else "NORMAL")
            last_close = closes[-1]

            if last_close > ema20 and ema20 > ema50:
                trend = "UP"
            elif last_close < ema20 and ema20 < ema50:
                trend = "DOWN"
            else:
                trend = "SIDEWAYS"

            coin    = sym.replace("USDT", "")
            summary = (f"RSI={rsi_val} EMA={ema_signal}(20{'>' if ema20>ema50 else '<'}50) "
                       f"VOL={vol_label} ATR={atr_pct}% TREND={trend}")

            result[coin] = {
                "rsi_4h":     rsi_val,
                "ema20":      ema20,
                "ema50":      ema50,
                "ema_signal": ema_signal,
                "vol_ratio":  vol_ratio,
                "vol_label":  vol_label,
                "atr_pct":    atr_pct,
                "trend":      trend,
                "summary":    summary
            }
            time.sleep(0.1)

        except Exception as e:
            coin = sym.replace("USDT", "")
            print(f"   ⚠ Indicators fetch failed for {sym}: {e}")

    up   = sum(1 for v in result.values() if v["trend"] == "UP")
    down = sum(1 for v in result.values() if v["trend"] == "DOWN")
    print(f"   📈 Indicators: {len(result)} coins — UP:{up} DOWN:{down} SIDEWAYS:{len(result)-up-down}")
    return result


# ══════════════════════════════════════════════════════════════════
# MASTER FUNCTION — run_market_intel()
# ══════════════════════════════════════════════════════════════════

def run_market_intel(candidate_symbols: list) -> dict:
    """
    Fetch all three intelligence layers and write market_context.json.
    candidate_symbols: list of USDT-suffixed symbols, e.g. ["BTCUSDT", ...]
    Returns combined dict.
    """
    print("   🧠 Market Intelligence: fetching F&G + Funding/OI + 4H Indicators...")

    fg       = get_fear_greed()
    funding  = get_funding_oi(candidate_symbols)
    indics   = get_coin_indicators(candidate_symbols)

    ctx = {
        "fear_greed":   fg,
        "funding_oi":   funding,
        "indicators":   indics,
        "generated_at": datetime.now(BKK).isoformat()
    }

    try:
        with open(MARKET_CTX_FILE, "w", encoding="utf-8") as f:
            json.dump(ctx, f, indent=2)
        print(f"   ✅ market_context.json written ({len(indics)} coins)")
    except Exception as e:
        print(f"   ⚠ Could not write market_context.json: {e}")

    return ctx


def load_market_context() -> dict:
    """
    Read market_context.json written by the bot this cycle.
    Returns empty dict if file missing or stale (>6h old).
    Used by strategist.py and morning_briefing.py.
    """
    try:
        with open(MARKET_CTX_FILE, "r", encoding="utf-8") as f:
            ctx = json.load(f)
        # staleness check
        gen_at = datetime.fromisoformat(ctx.get("generated_at", "2000-01-01T00:00:00+07:00"))
        age_h  = (datetime.now(BKK) - gen_at).total_seconds() / 3600
        if age_h > 6:
            print(f"   ⚠ market_context.json is {age_h:.1f}h old — ignoring")
            return {}
        return ctx
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════
# FORMAT HELPERS — used by bot.py to inject into Claude prompt
# ══════════════════════════════════════════════════════════════════

def format_fg_for_prompt(fg: dict) -> str:
    """Return 2-line F&G block for Claude prompt."""
    return (
        f"📊 FEAR & GREED INDEX: {fg['value']} — {fg['label']} ({fg['signal']})\n"
        f"   Rule: {fg['note']}"
    )


def format_indicators_for_prompt(indics: dict, funding: dict) -> str:
    """
    Return compact per-coin indicator table for Claude prompt.
    Format: COIN | RSI | EMA | VOL | ATR | TREND | FUNDING
    """
    if not indics:
        return "⚠ 4H indicators unavailable this cycle."

    lines = ["📈 4H TECHNICAL INDICATORS (real candle data — use this for trend confirmation):"]
    lines.append("COIN     | RSI  | EMA    | VOL    | ATR   | TREND    | FUNDING")
    lines.append("-" * 72)

    for coin, d in sorted(indics.items()):
        fi    = funding.get(coin, {})
        f_tag = ""
        if fi.get("bias") == "CROWDED_LONG":
            f_tag = "⚠CROWDED_L"
        elif fi.get("bias") == "CROWDED_SHORT":
            f_tag = "⚠CROWDED_S"
        else:
            fr = fi.get("funding_rate", 0)
            f_tag = f"{fr*100:+.3f}%"

        rsi_tag = "OVBOUGHT" if d["rsi_4h"] > 70 else ("OVERSOLD" if d["rsi_4h"] < 30 else f"{d['rsi_4h']}")
        lines.append(
            f"{coin:<8} | {rsi_tag:<4} | {d['ema_signal']:<6} | {d['vol_label']:<6} "
            f"| {d['atr_pct']:<5}% | {d['trend']:<8} | {f_tag}"
        )

    lines.append("")
    lines.append("⚠ SIGNAL RULES FROM INDICATOR DATA:")
    lines.append("  LONG:  Require TREND=UP + EMA=BULL + RSI<70. If EMA=BEAR or TREND=DOWN → skip or raise conf to 97%.")
    lines.append("  SHORT: Require TREND=DOWN + EMA=BEAR. CROWDED_SHORT funding → risk of squeeze, raise conf to 97%.")
    lines.append("  If FUNDING=CROWDED_LONG → do NOT open LONG (overcrowded, dump risk).")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "AAVEUSDT", "AEROUSDT",
        "JUPUSDT", "TIAUSDT", "XPLAUSDT", "NEARUSDT", "EIGENUSDT"
    ]
    print("=" * 60)
    print("  WHALE-STREAM Market Intelligence — Standalone Test")
    print("=" * 60)
    ctx = run_market_intel(test_symbols)
    print()
    print(format_fg_for_prompt(ctx["fear_greed"]))
    print()
    print(format_indicators_for_prompt(ctx["indicators"], ctx["funding_oi"]))
    print()
    print("✅ market_context.json written. Test complete.")
