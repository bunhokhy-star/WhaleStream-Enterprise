from config import ALLOWED_SYMBOLS

from data.binance_symbols import (
    get_binance_symbols
)


def analyze(coins):

    binance_symbols = get_binance_symbols()

    longs = []
    shorts = []

    STABLE_COINS = {
        "USDT",
        "USDC",
        "DAI",
        "FDUSD",
        "TUSD",
        "USDE",
        "USDS"
    }

    for coin in coins:

        symbol = coin.get(
            "symbol",
            ""
        ).upper()

        # ==========================
        # Stablecoin Filter
        # ==========================

        if symbol in STABLE_COINS:
            continue

        futures_symbol = symbol + "USDT"

        # ==========================
        # Binance Futures Filter
        # ==========================

        if futures_symbol not in binance_symbols:
            continue

        # ==========================
        # Allowed Symbol Filter
        # ==========================

        if symbol not in ALLOWED_SYMBOLS:
            continue

        market_cap = (
            coin.get("market_cap")
            or 0
        )

        volume = (
            coin.get("total_volume")
            or 0
        )

        change24 = (
            coin.get(
                "price_change_percentage_24h_in_currency"
            )
            or 0
        )

        change7 = (
            coin.get(
                "price_change_percentage_7d_in_currency"
            )
            or 0
        )

        # ==========================
        # Market Cap Filter
        # ==========================

        if market_cap < 150_000_000:
            continue

        if volume <= 0:
            continue

        volume_mcap = volume / market_cap

        # ==========================
        # LONG SCORE
        # ==========================

        long_score = 0

        if change24 > 0:
            long_score += 20

        if change7 > 0:
            long_score += 20

        if volume_mcap >= 0.03:
            long_score += 20

        if market_cap >= 500_000_000:
            long_score += 20

        if change24 > 3:
            long_score += 10

        if change7 > 3:
            long_score += 10

        if volume_mcap >= 0.10:
            long_score += 10

        if long_score >= 70:

            longs.append({

                "symbol": symbol,

                "score": long_score,

                "market_cap": market_cap,

                "volume_mcap": round(
                    volume_mcap,
                    4
                ),

                "change24": round(
                    change24,
                    2
                ),

                "change7": round(
                    change7,
                    2
                )

            })

        # ==========================
        # SHORT SCORE
        # ==========================

        short_score = 0

        if change24 < 0:
            short_score += 20

        if change7 < 0:
            short_score += 20

        if volume_mcap >= 0.03:
            short_score += 20

        if market_cap >= 500_000_000:
            short_score += 20

        if change24 < -3:
            short_score += 10

        if change7 < -10:
            short_score += 10

        if volume_mcap >= 0.10:
            short_score += 10

        if short_score >= 70:

            shorts.append({

                "symbol": symbol,

                "score": short_score,

                "market_cap": market_cap,

                "volume_mcap": round(
                    volume_mcap,
                    4
                ),

                "change24": round(
                    change24,
                    2
                ),

                "change7": round(
                    change7,
                    2
                )

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