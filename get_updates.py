import requests

BOT_TOKEN = "8698016942:AAEXfkc7nUtmwyPFBcMygHZUhLaNQoaUs8A"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"

print("URL =", url)

response = requests.get(url)

print(response.status_code)
print(response.text)