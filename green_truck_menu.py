"""Classic menu and minimum for Green Truck campaign pages.

Verbatim from Kam's Drive doc "Classic Street and Extended Menu", 2025-06-09.
No per-item prices. The catering minimum is separate.
"""

import os

CLASSIC_MENU = [
    {
        "name": "MotherTrucker Vegan Burger",
        "detail": "house-made vegan patty from local organic veg, mixed greens, heirloom tomato, Trucker Sauce, artisan bread",
    },
    {
        "name": "Organic Chicken Pesto Sandwich",
        "detail": "Mary's Farm chicken, mozzarella, roasted red peppers, arugula, house basil pesto, ciabatta",
    },
    {
        "name": "Organic Kale Yeah Bowl",
        "detail": "kale, quinoa, mushrooms, shaved beets, carrots, goddess dressing, sesame; option grilled chicken or vegan patty",
    },
    {
        "name": "Super-Food Salad Bowl",
        "detail": "red & gold quinoa, black beans, kale, avocado, broccolini, hemp, goji, cashew dressing",
    },
    {
        "name": "Golden Rounds",
        "detail": "hand-cut organic sweet potato rounds, flash fried, sea salt",
    },
    {
        "name": "Cilantro-lime Fresca (seasonal)",
        "detail": "light fresca sweetened with organic agave",
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
