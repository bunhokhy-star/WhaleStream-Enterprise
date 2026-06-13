import json
import os

FILE_NAME = "oi_history.json"


def load_history():

    if not os.path.exists(FILE_NAME):
        return {}

    with open(FILE_NAME, "r") as f:
        return json.load(f)


def save_history(data):

    with open(FILE_NAME, "w") as f:
        json.dump(data, f, indent=4)