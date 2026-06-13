from pybit.unified_trading import HTTP

from execution.exceptions import BybitConfigError

try:
    from config_bybit import API_KEY, API_SECRET, DEMO
except Exception as exc:
    raise BybitConfigError(
        "Missing config_bybit.py. Create it locally with API_KEY, API_SECRET, and DEMO=True."
    ) from exc


def _validate_config():
    if not API_KEY or API_KEY in ("YOUR_API_KEY", "PASTE_YOUR_API_KEY"):
        raise BybitConfigError("API_KEY is missing in config_bybit.py")

    if not API_SECRET or API_SECRET in ("YOUR_API_SECRET", "PASTE_YOUR_API_SECRET"):
        raise BybitConfigError("API_SECRET is missing in config_bybit.py")


def get_session():
    _validate_config()

    return HTTP(
        api_key=API_KEY,
        api_secret=API_SECRET,
        demo=DEMO,
    )


session = get_session()
