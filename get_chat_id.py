import requests

BOT_TOKEN = "8698016942:AAEXfkc7nUtmwyPFBcMygHZUhLaNQoaUs8A"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

r = requests.get(url)

print(r.text)