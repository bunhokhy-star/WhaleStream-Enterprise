from config import ALLOWED_SYMBOLS

def analyze(coins):

    longs = []
    shorts = []

    for coin in coins:

        symbol = coin.get("symbol", "").upper()

        if symbol not in ALLOWED_SYMBOLS:
            continue

        market_cap = coin.get("market_cap") or 0
        volume = coin.get("total_volume") or 0

        change24 = coin.get(
            "price_change_percentage_24h_in_currency"
        ) or 0

        change7 = coin.get(
            "price_change_percentage_7d_in_currency"
        ) or 0

        if market_cap < 150_000_000:
            continue

        volume_mcap = volume / market_cap

        # =========================
        # LONG FILTER
        # =========================

        if change24 <= 0:
            continue

        if change7 <= 3:
            continue

        if volume_mcap < 0.03:
            continue

        score = 0

        if 1 <= change24 <= 15:
            score += 30

        if 3 <= change7 <= 35:
            score += 30

        if 0.03 <= volume_mcap <= 0.30:
            score += 20

        if market_cap > 500_000_000:
            score += 20

        if score >= 70:

            longs.append({
                "symbol": symbol,
                "score": score,
                "market_cap": market_cap,
                "volume_mcap": round(volume_mcap, 4),
                "change24": round(change24, 2),
                "change7": round(change7, 2)
            })

        # =========================
        # SHORT FILTER
        # =========================

        short_score = 0

        if market_cap >= 150_000_000:

            if change24 > 20:
                short_score += 40

            if change7 > 40:
                short_score += 40

            if volume_mcap > 0.30:
                short_score += 20

            if short_score >= 70:

                shorts.append({
                    "symbol": symbol,
                    "score": short_score,
                    "market_cap": market_cap,
                    "volume_mcap": round(volume_mcap, 4),
                    "change24": round(change24, 2),
                    "change7": round(change7, 2)
                })

    longs = sorted(
        longs,
        key=lambda x: x["score"],
        reverse=True
    )

    shorts = sorted(
        shorts,
        key=lambda x: x["score"],
        reverse=True
    )

    return longs[:3], shorts[:3]