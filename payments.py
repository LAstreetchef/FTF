"""Card payments for office campaigns.

Launch provider is Stripe. Authorizations use manual capture, so a card
is charged only when the office reaches its goal. Apple Pay and Google Pay
are welcome when they arrive as a card PaymentMethod. Cash App Pay is not
offered.

TODO: Braintree Venmo can be a second provider behind authorize_card,
capture_card, and release_card. Do not add it until that provider exists.
"""

import stripe
from utils import charge_stripe_payment, create_stripe_payment_intent, release_stripe_hold

PROVIDER = "stripe"


def authorize_card(amount, email, description, payment_method, return_url):
    """Authorize a card and leave it uncaptured. Returns (intent id, status)."""
    intent_id = create_stripe_payment_intent(amount, email, description)
    if not intent_id:
        return None, None
    intent = stripe.PaymentIntent.confirm(
        intent_id,
        payment_method=payment_method,
        return_url=return_url,
    )
    return intent_id, intent.status


def capture_card(payment_intent_id, amount, description):
    return charge_stripe_payment(payment_intent_id, amount, description)


def release_card(payment_intent_id):
    return release_stripe_hold(payment_intent_id)
