import csv
import os
from datetime import datetime


FILE = "history/signals.csv"


def log_signal(signal):

    os.makedirs(
        "history",
        exist_ok=True
    )

    new_file = not os.path.exists(FILE)

    with open(
        FILE,
        "a",
        newline=""
    ) as f:

        writer = csv.writer(f)

        if new_file:

            writer.writerow([

                "time",

                "symbol",

                "direction",

                "entry_low",

                "entry_high",

                "stop_loss",

                "tp1",

                "tp2",

                "tp3",

                "tp4",

                "confidence",

                "pattern",

                "funding",

                "oi",

                "btc_regime"

            ])

        writer.writerow([

            datetime.now(),

            signal["symbol"],

            signal["direction"],

            signal["entry_low"],

            signal["entry_high"],

            signal["stop_loss"],

            signal["tp1"],

            signal["tp2"],

            signal["tp3"],

            signal["tp4"],

            signal["confidence"],

            signal["pattern"],

            signal["funding_rate"],

            signal["oi_change"],

            signal["btc_regime"]

        ])