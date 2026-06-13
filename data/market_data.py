from data.coingecko import get_market_data
from data.binance_futures import get_funding_rates
from data.oi import get_oi


class MarketData:

    def __init__(self):

        self.coins = []
        self.funding = {}
        self.oi = {}

    # ==========================
    # CoinGecko
    # ==========================

    def load_coins(self):

        self.coins = get_market_data()

        return self.coins

    # ==========================
    # Funding
    # ==========================

    def load_funding(self):

        data = get_funding_rates()

        self.funding = {}

        for row in data:

            symbol = row["symbol"].upper()

            self.funding[symbol] = float(
                row["lastFundingRate"]
            )

        return self.funding

    # ==========================
    # Open Interest
    # ==========================

    def load_oi(self, symbols):

        self.oi = {}

        for symbol in symbols:

            symbol = symbol.upper()

            self.oi[symbol] = get_oi(symbol)

        return self.oi

    # ==========================
    # Funding Lookup
    # ==========================

    def funding_rate(self, symbol):

        return self.funding.get(
            symbol.upper(),
            0.0
        )

    # ==========================
    # Open Interest Lookup
    # ==========================

    def open_interest(self, symbol):

        return self.oi.get(
            symbol.upper(),
            0.0
        )