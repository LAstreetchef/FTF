"""Classic menu and minimum for Green Truck campaign pages.

TODO(Kam): The menu page on greentruckonthego.com could not be used.
https://www.greentruckonthego.com/menu returns 404, and
https://www.greentruckonthego.com/projects is still lorem ipsum (checked
Nov 2026). The names and lines below are taken only from Green Truck photo
captions in static/images/green-truck/manifest.json. Replace CLASSIC_MENU
with the exact classic menu text. Do not add dishes that are not on it.
"""

import os

CLASSIC_MENU = [
    {
        "name": "Mother Trucker",
        "detail": "Vegan burger with pink sauce, pickles, and tomato.",
    },
    {
        "name": "Ultimate Mother",
        "detail": "Sprout burger.",
    },
    {
        "name": "Kale Yeah bowl",
        "detail": "Quinoa, beets, carrots, mushrooms, and goddess dressing.",
    },
    {
        "name": "Paleo bowl",
        "detail": "Egg, bacon, avocado, and kale.",
    },
    {
        "name": "Chipotle cheddar burger",
        "detail": "Caramelized onions and melted cheddar.",
    },
    {
        "name": "Chicken pesto sandwich",
        "detail": "Roasted red peppers and arugula on ciabatta.",
    },
    {
        "name": "Chili burger",
        "detail": "",
    },
    {
        "name": "Cilantro lime fresca",
        "detail": "",
    },
]


def minimum_amount():
    raw = (os.environ.get("GREEN_TRUCK_MINIMUM") or "1750").strip()
    try:
        amount = int(raw)
    except ValueError:
        amount = 1750
    if amount < 0:
        amount = 1750
    return amount


def minimum_label():
    return f"Minimum ${minimum_amount():,} + tip"
