def format_signal(signal):

    msg = ""

    msg += (
        f"🐳 {signal['symbol']} LONG 🐳\n\n"
    )

    msg += (
        f"CONFIDENCE: "
        f"{signal['confidence']}%\n\n"
    )

    msg += (
        f"Funding: "
        f"{signal['funding_rate']}\n"
    )

    msg += (
        f"OI Change: "
        f"{signal['oi_change']}%\n\n"
    )

    msg += (
        f"15m: {signal['15m']}\n"
    )

    msg += (
        f"30m: {signal['30m']}\n"
    )

    msg += (
        f"1h: {signal['1h']}\n"
    )

    msg += (
        f"4h: {signal['4h']}\n"
    )

    msg += (
        f"1d: {signal['1d']}\n\n"
    )

    msg += (
        f"ENTRY:\n"
        f"{signal['entry_low']} - "
        f"{signal['entry_high']}\n\n"
    )

    msg += (
        f"SL:\n"
        f"{signal['stop_loss']}\n\n"
    )

    msg += (
        f"TP1: {signal['tp1']}\n"
    )

    msg += (
        f"TP2: {signal['tp2']}\n"
    )

    msg += (
        f"TP3: {signal['tp3']}\n"
    )

    msg += (
        f"TP4: {signal['tp4']}\n"
    )

    return msg