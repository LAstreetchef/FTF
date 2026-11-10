import io
import json

from app import app, db
from models import CampaignPage, CampaignView, QuoteRequest


def _login_admin(client):
    response = client.post("/admin/login", data={
        "username": "admin@example.com",
        "password": "admin-password-123",
    })
    assert response.status_code == 200


def _import_sample(client):
    csv_body = (
        "company,contact_name,contact_email,personal_note,logo_url,suggested_dates,give_back_cause,slug\n"
        "Northwind Labs,Avery Chen,avery@northwind.example,A note for the Culver City floor.,,"
        "2026-12-04|2026-12-09|2026-12-11,a local school garden,northwind-labs\n"
        "Harbor & Pine,Jordan Hale,jordan@harborandpine.example,A Playa Vista note.,,2026-12-08|2026-12-15,,harbor-and-pine\n"
    )
    return client.post(
        "/admin/campaigns/import",
        data={"csv_file": (io.BytesIO(csv_body.encode()), "prospects.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_csv_import_and_green_truck_page(client):
    blocked = client.get("/admin/campaigns")
    assert blocked.status_code in (302, 303)

    _login_admin(client)
    imported = _import_sample(client)
    assert imported.status_code == 200
    assert b"Northwind Labs" in imported.data
    assert b"Copy link" in imported.data

    page = client.get("/c/northwind-labs")
    assert page.status_code == 200
    body = page.data
    assert b"Northwind Labs" in body and b"Holiday Truck Day" in body
    assert b"GTLA" in body
    assert b"A note from Kam" in body
    assert b"MotherTrucker Vegan Burger" in body
    assert b"Golden Rounds" in body
    assert b"Super-Food Salad Bowl" in body
    assert b"$1,750" in body
    assert b"Combo $18" in body
    assert b"Start our truck day" in body
    assert b"See the menu" in body
    assert b"only be charged if this event reaches its funding goal" not in body
    assert b"Coachella" in body
    assert b"Malibu" in body
    assert b"fetchpriority=\"high\"" in body
    assert b"loading=\"lazy\"" in body
    assert b"truck-desert-vintage-01" in body
    assert b"gt-vintage" in body
    assert b"Food Truck Login" not in body
    assert b"Choose a food truck" not in body
    footer = [
        b"brand-classic-menu-board-01.jpg",
        b"food-avocado-toast-herbs-01.jpg",
        b"brand-inspiration-card-01.jpg",
        b"brand-breakfast-popup-card-01.jpg",
        b"event-string-lights-crowd-01.jpg",
        b"cabin-wine-toast-01.jpg",
        b"food-mother-trucker-graphic-01.jpg",
        b"press-peta-award-01.jpg",
        b"truck-field-solar-01.jpg",
        b"food-burger-magenta-studio-01.jpg",
        b"food-veggie-burger-chips-01.jpg",
        b"food-paleo-bowl-egg-02.jpg",
    ]
    for name in footer:
        assert name in body
    # The rest of the library stays in the manifest but is not dumped into the strip.
    assert b"food-sliders-01.jpg" not in body

    with app.app_context():
        record = CampaignPage.query.filter_by(slug="northwind-labs").one()
        assert CampaignView.query.filter_by(campaign_id=record.id).count() == 1


def test_office_reaches_the_goal_and_books_a_day(client):
    from datetime import datetime
    from unittest.mock import MagicMock, patch

    from models import Event, Pledge

    _login_admin(client)
    _import_sample(client)
    started = client.post("/c/northwind-labs/start", data={
        "organizer_name": "Avery Chen",
        "office_address": "100 Example Ave, Culver City",
        "guest_count": "40",
        "weekday": "fri",
    }, follow_redirects=True)
    assert started.status_code == 200
    assert b"Share" in started.data
    assert b"0 of 98 combos" in started.data
    assert b"left" in started.data

    with app.app_context():
        page = CampaignPage.query.filter_by(slug="northwind-labs").one()
        event = Event.query.get(page.event_id)
        assert event.pledge_goal == 1750
        assert event.organizer_fee_charged is True
        assert event.organizer_fee_payment_intent is None
        assert event.status == "pending"
        assert page.preferred_weekday == "fri"
        campaign_id = page.id

    intent = MagicMock()
    intent.id = "pi_test_combo"
    intent.status = "requires_capture"
    intent.amount = 1881

    def _intent_for(amount_cents):
        created = MagicMock()
        created.id = f"pi_{amount_cents}"
        created.status = "requires_capture"
        created.amount = amount_cents
        return created

    catalog_price = MagicMock(unit_amount=1800, currency="usd", product="prod_VbR57kEpMXLiP4")
    with patch("green_truck_menu.stripe.Price.retrieve", return_value=catalog_price) as read_price, \
         patch("utils.stripe.PaymentIntent.create", side_effect=lambda **kwargs: _intent_for(kwargs["amount"])) as create_intent, \
         patch("payments.stripe.PaymentIntent.confirm", side_effect=lambda intent_id, **kwargs: _intent_for(intent.amount)) as confirm_intent, \
         patch("utils.stripe.PaymentIntent.retrieve", side_effect=lambda intent_id: _intent_for(1881)), \
         patch("utils.stripe.PaymentIntent.capture", side_effect=lambda intent_id: _intent_for(1881)):
        from green_truck_menu import refresh_combo_price
        loaded = refresh_combo_price()
        assert loaded["source"] == "stripe"
        assert read_price.called
        first = client.post("/c/northwind-labs/pledge", data={
            "supporter_name": "Sam Coworker",
            "supporter_email": "sam.coworker@example.com",
            "quantity": "1",
            "entree": "MotherTrucker Vegan Burger",
            "stripe_payment_method": "pm_card_visa",
        }, follow_redirects=True)
        assert first.status_code == 200, first.data[:400]
        assert create_intent.called
        assert confirm_intent.called
        created = create_intent.call_args.kwargs
        assert created["capture_method"] == "manual"
        assert created["amount"] == 1881
        assert created["metadata"]["subtotal"] == "18.00"
        assert created["metadata"]["fee"] == "0.81"
        assert created["metadata"]["fee_rate"] == "0.045"
        assert created["payment_method_types"] == ["card"]
        assert created["metadata"]["price_id"] == "price_1UaEDhBgt3ltA59nFLiZXZ2E"
        assert created["metadata"]["product_id"] == "prod_VbR57kEpMXLiP4"
        assert created["metadata"]["quantity"] == "1"
        assert created["metadata"]["campaign_slug"] == "northwind-labs"
        assert created["metadata"]["event_id"]
        assert created["description"] == "Green Truck Office Combo x1 - Northwind Labs"
        with app.app_context():
            pledge = Pledge.query.filter_by(email="sam.coworker@example.com").one()
            assert pledge.status == "pending"
            assert pledge.amount == 18
            assert abs(pledge.processing_fee - 0.81) < 0.001
        second = client.post("/c/northwind-labs/pledge", data={
            "supporter_name": "Sam Coworker",
            "supporter_email": "sam.coworker@example.com",
            "quantity": "97",
            "stripe_payment_method": "pm_card_visa",
        }, follow_redirects=True)
        assert second.status_code == 200

    with app.app_context():
        page = CampaignPage.query.filter_by(slug="northwind-labs").one()
        event = Event.query.get(page.event_id)
        assert event.is_goal_met()
        assert event.status == "funded"
        assert Pledge.query.filter_by(event_id=event.id, status="pending").count() == 0
        assert Pledge.query.filter_by(event_id=event.id, status="charged").count() == 2

    booked = client.post("/c/northwind-labs/book", data={"event_date": "2026-12-04"}, follow_redirects=True)
    assert booked.status_code == 200
    assert b"Your meal is on us" in booked.data

    with app.app_context():
        page = CampaignPage.query.filter_by(slug="northwind-labs").one()
        event = Event.query.get(page.event_id)
        assert page.booked_date == "2026-12-04"
        assert event.organizer_entree_claimed is True
        assert event.status == "approved"
        assert event.date == datetime(2026, 12, 4, 11, 0)

    detail = client.get(f"/admin/campaigns/{campaign_id}")
    assert detail.status_code == 200
    assert b"100 Example Ave, Culver City" in detail.data
    assert b"booked" in detail.data
    assert b"Your meal is on us" in detail.data
    assert b"logged" in detail.data
    listing = client.get("/admin/campaigns")
    assert b"Friday" in listing.data
    assert b"booked" in listing.data


def test_anonymous_sponsor_is_unnamed_on_the_page(client):
    _login_admin(client)
    _import_sample(client)
    response = client.post("/c/harbor-and-pine/start", data={
        "organizer_name": "Jordan Hale",
        "office_address": "50 Example St, Playa Vista",
        "guest_count": "20",
        "weekday": "tue",
        "sponsor_anonymous": "1",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"A coworker is bringing Green Truck to Harbor" in response.data
    assert b"How it works for you" in response.data
    assert b"Copy message" in response.data
    with app.app_context():
        page = CampaignPage.query.filter_by(slug="harbor-and-pine").one()
        assert page.sponsor_anonymous is True
        assert page.contact_name == "Jordan Hale"
    detail = client.get(f"/admin/campaigns/{page.id}")
    assert b"Jordan Hale" in detail.data
    assert b"Name off the page" in detail.data


def test_deadline_releases_uncaptured_holds(client):
    from datetime import datetime, timedelta

    from models import Event, Pledge

    _login_admin(client)
    _import_sample(client)
    assert client.post("/c/northwind-labs/start", data={
        "organizer_name": "Avery Chen",
        "office_address": "100 Example Ave, Culver City",
        "guest_count": "40",
        "weekday": "fri",
    }, follow_redirects=True).status_code == 200
    with app.app_context():
        page = CampaignPage.query.filter_by(slug="northwind-labs").one()
        event = Event.query.get(page.event_id)
        event.created_at = datetime.utcnow() - timedelta(days=8)
        event.current_pledges = 18
        db.session.add(Pledge(
            email="late@example.com",
            amount=18,
            processing_fee=0.81,
            stripe_token="simulated",
            stripe_payment_intent_id="sim_deadline",
            event_id=event.id,
            status="pending",
        ))
        db.session.commit()

    missed = client.get("/c/northwind-labs")
    assert missed.status_code == 200
    assert b"Cards were not charged" in missed.data
    with app.app_context():
        page = CampaignPage.query.filter_by(slug="northwind-labs").one()
        event = Event.query.get(page.event_id)
        pledge = Pledge.query.filter_by(stripe_payment_intent_id="sim_deadline").one()
        assert event.status == "cancelled"
        assert pledge.status == "cancelled"


def test_admin_preview_does_not_count_as_a_view(client):
    _login_admin(client)
    _import_sample(client)
    assert client.get("/c/harbor-and-pine?preview=1").status_code == 200
    with app.app_context():
        page = CampaignPage.query.filter_by(slug="harbor-and-pine").one()
        assert CampaignView.query.filter_by(campaign_id=page.id).count() == 0


def test_unknown_campaign_is_404(client):
    assert client.get("/c/not-a-real-company").status_code == 404
