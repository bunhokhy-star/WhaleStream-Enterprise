from execution.bybit_client import session


def get_wallet():

    result = session.get_wallet_balance(
        accountType="UNIFIED"
    )

    return result