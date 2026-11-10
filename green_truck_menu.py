"""Classic menu, combo price, and goal for Green Truck campaign pages.

Verbatim from Kam's Drive doc "Classic Street and Extended Menu", 2025-06-09.
The office reaches GREEN_TRUCK_MINIMUM by coworkers pre-buying COMBO_PRICE meals.
"""

import math
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
    return f"Minimum ${minimum_amount():,}"


def combo_price():
    raw = (os.environ.get("COMBO_PRICE") or "18").strip()
    try:
        amount = int(raw)
    except ValueError:
        amount = 18
    if amount < 1:
        amount = 18
    return amount


def combo_description():
    text = (os.environ.get("COMBO_DESCRIPTION") or "entree + side + drink").strip()
    return text or "entree + side + drink"


def combo_label():
    return f"Combo ${combo_price()} · {combo_description()}"


def combos_needed():
    return math.ceil(minimum_amount() / combo_price())


def campaign_days():
    """How long an office campaign stays open after the sponsor starts it."""
    raw = (os.environ.get("CAMPAIGN_DAYS") or "7").strip()
    try:
        days = int(raw)
    except ValueError:
        days = 7
    if days < 1:
        days = 7
    return days


ENTREES = [
    item for item in CLASSIC_MENU
    if item["name"] not in {"Golden Rounds", "Cilantro-lime Fresca (seasonal)"}
]
