import csv
import os

from data.binance_klines import get_klines

SIGNAL_FILE = "history/signals.csv"
RESULT_FILE = "history/results.csv"


def evaluate_signals():

    if not os.path.exists(SIGNAL_FILE):
        return

    results = []

    with open(SIGNAL_FILE, newline="") as f:

        reader = csv.DictReader(f)

        for row in reader:

            symbol = row["symbol"]
            direction = row["direction"]

            sl = float(row["stop_loss"])

            tp1 = float(row["tp1"])
            tp2 = float(row["tp2"])
            tp3 = float(row["tp3"])
            tp4 = float(row["tp4"])

            candles = get_klines(
                symbol,
                "1h",
                100
            )

            result = "OPEN"
            r_multiple = 0

            mfe = 0
            mae = 0

            for candle in candles:

                high = float(candle[2])
                low = float(candle[3])

                if direction == "LONG":

                    mfe = max(mfe, high)
                    mae = min(mae if mae else low, low)

                    if high >= tp4:
                        result = "TP4"
                        r_multiple = 4
                        break

                    elif high >= tp3:
                        result = "TP3"
                        r_multiple = 3

                    elif high >= tp2:
                        result = "TP2"
                        r_multiple = 2

                    elif high >= tp1:
                        result = "TP1"
                        r_multiple = 1

                    if low <= sl:
                        if r_multiple == 0:
                            result = "SL"
                            r_multiple = -1
                        break

                else:

                    mfe = min(mfe if mfe else low, low)
                    mae = max(mae, high)

                    if low <= tp4:
                        result = "TP4"
                        r_multiple = 4
                        break

                    elif low <= tp3:
                        result = "TP3"
                        r_multiple = 3

                    elif low <= tp2:
                        result = "TP2"
                        r_multiple = 2

                    elif low <= tp1:
                        result = "TP1"
                        r_multiple = 1

                    if high >= sl:
                        if r_multiple == 0:
                            result = "SL"
                            r_multiple = -1
                        break

            row["result"] = result
            row["r_multiple"] = r_multiple
            row["mfe"] = round(mfe, 6)
            row["mae"] = round(mae, 6)

            results.append(row)

    with open(
        RESULT_FILE,
        "w",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=results[0].keys()
        )

        writer.writeheader()
        writer.writerows(results)

    print()
    print("Evaluation Finished")
    print("Results Updated")