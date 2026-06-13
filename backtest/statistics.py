import csv
import os


RESULT_FILE = "history/results.csv"


def show_statistics():

    if not os.path.exists(RESULT_FILE):

        print("No results found.")
        return

    with open(RESULT_FILE, newline="") as f:

        rows = list(csv.DictReader(f))

    total = len(rows)

    wins = 0
    losses = 0
    open_trades = 0

    long_total = 0
    long_wins = 0

    short_total = 0
    short_wins = 0

    confidence_sum = 0

    patterns = {}

    for row in rows:

        result = row["result"]
        direction = row["direction"]
        pattern = row["pattern"]

        confidence_sum += float(
            row["confidence"]
        )

        if result == "WIN":
            wins += 1

        elif result == "LOSS":
            losses += 1

        else:
            open_trades += 1

        if direction == "LONG":

            long_total += 1

            if result == "WIN":
                long_wins += 1

        else:

            short_total += 1

            if result == "WIN":
                short_wins += 1

        if pattern not in patterns:

            patterns[pattern] = {
                "win": 0,
                "total": 0
            }

        patterns[pattern]["total"] += 1

        if result == "WIN":

            patterns[pattern]["win"] += 1

    print()
    print("===================================")
    print("WHALESTREAM STATISTICS")
    print("===================================")
    print()

    print("Total Trades :", total)
    print("Wins         :", wins)
    print("Losses       :", losses)
    print("Open         :", open_trades)

    print()

    if total > 0:

        print(
            "Win Rate     :",
            round(
                wins / total * 100,
                2
            ),
            "%"
        )

        print(
            "Average Confidence :",
            round(
                confidence_sum / total,
                2
            )
        )

    print()

    if long_total:

        print(
            "LONG Win Rate :",
            round(
                long_wins / long_total * 100,
                2
            ),
            "%"
        )

    if short_total:

        print(
            "SHORT Win Rate:",
            round(
                short_wins / short_total * 100,
                2
            ),
            "%"
        )

    print()
    print("PATTERN PERFORMANCE")
    print("--------------------")

    for name, stats in patterns.items():

        rate = round(
            stats["win"] /
            stats["total"] * 100,
            2
        )

        print(
            name,
            "-",
            rate,
            "%"
        )