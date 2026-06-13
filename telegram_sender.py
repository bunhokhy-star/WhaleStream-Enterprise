import requests

BOT_TOKEN = "8698016942:AAEXfkc7nUtmwyPFBcMygHZUhLaNQoaUs8A"
CHAT_ID = "-1003964668992"


def send_message(message):

    url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(
        url,
        data=payload,
        timeout=30
    )

    print(response.text)