from datetime import datetime


def format_signal(signal):

    now = datetime.now()

    msg = ""

    msg += (
        "TIMEZONE: Bangkok, Hanoi, Jakarta (GMT+7)\n"
    )

    msg += (
        f"DATE/TIME: "
        f"{now.strftime('%d-%m-%Y %H:%M')}\n\n"
    )

    msg += (
    f"🐳 {signal['symbol']} {signal['direction']} 🐳\n\n"
        )

    msg += (
        f"🧿 CONFIDENCE: "
        f"{signal['confidence']}%\n\n"
    )

    msg += (
        f"📊 PATTERN: "
        f"{signal['pattern']}\n\n"
    )

    msg += (
        f"📈 FUNDING: "
        f"{signal['funding_rate']}\n"
    )

    msg += (
        f"📈 OI CHANGE: "
        f"{signal['oi_change']}%\n\n"
    )

    msg += (
        f"✳️ ENTRY:\n"
        f"{signal['entry_low']} - "
        f"{signal['entry_high']}\n\n"
    )

    msg += (
        f"⛔ STOP LOSS:\n"
        f"{signal['stop_loss']}\n\n"
    )

    msg += (
        f"🎯 TP1: {signal['tp1']}\n"
    )

    msg += (
        f"🎯 TP2: {signal['tp2']}\n"
    )

    msg += (
        f"🎯 TP3: {signal['tp3']}\n"
    )

    msg += (
        f"🎯 TP4: {signal['tp4']}\n"
    )

    return msg