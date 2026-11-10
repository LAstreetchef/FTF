"""Classic menu, combo price, and goal for Green Truck campaign pages.

Verbatim from Kam's Drive doc "Classic Street and Extended Menu", 2025-06-09.
The office reaches GREEN_TRUCK_MINIMUM by coworkers pre-buying the Stripe combo.
COMBO_PRICE is only the fallback when that Price cannot be read.
"""

import logging
import math
import os

import stripe

# GTLA test-mode catalog. Not a secret. Live mode must set STRIPE_COMBO_PRICE_ID.
DEFAULT_TEST_PRICE_ID = "price_1UaEDhBgt3ltA59nFLiZXZ2E"
DEFAULT_TEST_PRODUCT_ID = "prod_VbR57kEpMXLiP4"

_COMBO_CACHE = {
    "price_id": None,
    "product_id": "",
    "unit_cents": None,
    "source": None,
}

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


def _fallback_unit_cents():
    raw = (os.environ.get("COMBO_PRICE") or "18").strip()
    try:
        amount = int(raw)
    except ValueError:
        amount = 18
    if amount < 1:
        amount = 18
    return amount * 100


def _test_mode():
    raw = (os.environ.get("STRIPE_TEST_MODE") if os.environ.get("STRIPE_TEST_MODE") is not None else "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def combo_price_id():
    explicit = (os.environ.get("STRIPE_COMBO_PRICE_ID") or "").strip()
    if explicit:
        return explicit
    if _test_mode():
        return DEFAULT_TEST_PRICE_ID
    return ""


def refresh_combo_price():
    """Read the Stripe Price once and cache unit_amount. Never creates a Price."""
    price_id = combo_price_id()
    fallback_product = DEFAULT_TEST_PRODUCT_ID if price_id == DEFAULT_TEST_PRICE_ID else ""
    fallback_cents = _fallback_unit_cents()
    if not price_id or not stripe.api_key:
        _COMBO_CACHE.update(
            price_id=price_id,
            product_id=fallback_product,
            unit_cents=fallback_cents,
            source="fallback",
        )
        logging.info("Combo price is the COMBO_PRICE fallback (Stripe price was not read)")
        return dict(_COMBO_CACHE)
    try:
        price = stripe.Price.retrieve(price_id)
        currency = str(getattr(price, "currency", "") or "").lower()
        unit = getattr(price, "unit_amount", None)
        product = getattr(price, "product", "") or ""
        if hasattr(product, "id"):
            product = product.id
        if currency != "usd" or unit is None:
            raise ValueError("Stripe price has no USD unit_amount")
        _COMBO_CACHE.update(
            price_id=price_id,
            product_id=str(product or fallback_product),
            unit_cents=int(unit),
            source="stripe",
        )
        logging.info("Combo price %s is %s cents", price_id, int(unit))
    except Exception:
        logging.exception("Could not read Stripe price %s; using COMBO_PRICE", price_id or "(unset)")
        _COMBO_CACHE.update(
            price_id=price_id,
            product_id=fallback_product,
            unit_cents=fallback_cents,
            source="fallback",
        )
    return dict(_COMBO_CACHE)


def combo_unit_cents():
    if _COMBO_CACHE["unit_cents"] is None or _COMBO_CACHE["price_id"] != combo_price_id():
        refresh_combo_price()
    return int(_COMBO_CACHE["unit_cents"])


def combo_product_id():
    if _COMBO_CACHE["unit_cents"] is None or _COMBO_CACHE["price_id"] != combo_price_id():
        refresh_combo_price()
    return _COMBO_CACHE["product_id"] or ""


def combo_price():
    cents = combo_unit_cents()
    if cents % 100 == 0:
        return cents // 100
    return cents / 100.0


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
