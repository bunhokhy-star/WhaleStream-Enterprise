from typing import Dict, Any

from execution.bybit_client import session
from execution.utils import assert_ok, safe_float


def get_wallet(account_type: str = "UNIFIED") -> Dict[str, Any]:
    response = session.get_wallet_balance(accountType=account_type)
    return assert_ok(response, "Get wallet balance")


def get_usdt_balance(account_type: str = "UNIFIED") -> Dict[str, float]:
    wallet = get_wallet(account_type)
    accounts = wallet.get("result", {}).get("list", [])

    if not accounts:
        return {"wallet_balance": 0.0, "available_balance": 0.0, "equity": 0.0}

    coins = accounts[0].get("coin", [])

    for coin in coins:
        if coin.get("coin") == "USDT":
            return {
                "wallet_balance": safe_float(coin.get("walletBalance")),
                "available_balance": safe_float(
                    coin.get("availableToWithdraw") or coin.get("availableToBorrow")
                ),
                "equity": safe_float(coin.get("equity")),
            }

    return {"wallet_balance": 0.0, "available_balance": 0.0, "equity": 0.0}
