from data.binance_futures import get_open_interest


def get_oi(symbol):

    try:

        data = get_open_interest(symbol)

        return float(
            data["openInterest"]
        )

    except Exception:

        return 0.0