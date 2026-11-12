import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app import app, db
from models import Event, FoodTruck, FoodTruckOwner, Organizer, Pledge


def test_public_pages_and_health(client):
    for path in ("/health", "/", "/events", "/los-angeles", "/houston",
                 "/food-truck/login", "/food-truck/register",
                 "/organizer/login", "/organizer/register", "/admin/login"):
        response = client.get(path)
        assert response.status_code == 200, path

    health = client.get("/health").get_json()
    assert health["status"] == "healthy"
    assert health["database"] == "connected"


def test_legacy_maintenance_routes_are_not_reachable(client):
    for path in (
        "/login-admin-direct-xyz123",
        "/production-setup-abc999",
        "/database-sync-xyz456",
        "/auto-fix-all-menus-xyz123",
        "/test-credentials",
    ):
        assert client.get(path).status_code == 404, path


def test_food_truck_owner_can_register_login_and_add_a_truck(client):
    register = client.post("/food-truck/register", data={
        "email": "owner@example.com",
        "name": "Avery Owner",
        "phone": "310-555-0199",
        "business_name": "Green Truck",
        "business_license": "LIC-1",
        "password": "owner-password",
    }, follow_redirects=True)
    assert register.status_code == 200
    assert b"Registration successful" in register.data or b"Login" in register.data

    login = client.post("/food-truck/login", data={
        "email": "owner@example.com",
        "password": "owner-password",
    }, follow_redirects=True)
    assert login.status_code == 200
    assert b"Invalid email or password" not in login.data

    created = client.post("/food-truck/add-truck", data={
        "name": "Green Truck",
        "description": "Organic plates for community fundraisers",
        "cuisine_type": "Organic",
        "contact_email": "owner@example.com",
        "contact_phone": "310-555-0199",
        "sales_goal": "750",
    }, follow_redirects=True)
    assert created.status_code == 200

    payouts = client.get("/food-truck/payouts")
    assert payouts.status_code == 200
    assert b"update_food_truck_payout_settings" not in payouts.data or b"Payout" in payouts.data

    with app.app_context():
        owner = FoodTruckOwner.query.filter_by(email="owner@example.com").one()
        truck = FoodTruck.query.filter_by(owner_id=owner.id).one()
        assert truck.name == "Green Truck"
        assert truck.sales_goal == 750

    with app.app_context():
        truck = FoodTruck.query.filter_by(name="Green Truck").one()
        truck_id = truck.id

    menu = client.post(f"/food-truck/edit/{truck_id}", data={
        "action": "update_menu",
        "item_name_0": "Carnitas Taco",
        "item_price_0": "4.50",
        "item_description_0": "Onion and cilantro",
    }, follow_redirects=True)
    assert menu.status_code == 200

    app.config["PAYMENTS_MODE"] = "simulate"
    try:
        paid = client.post(
            f"/food-truck/confirm-registration-fee-payment/{truck_id}",
            data={"simulate": "1"},
            follow_redirects=True,
        )
        assert paid.status_code == 200
    finally:
        app.config["PAYMENTS_MODE"] = "stripe"

    with app.app_context():
        truck = db.session.get(FoodTruck, truck_id)
        assert truck.registration_fee_charged is True
        assert truck.status == "approved"
        assert truck.get_menu_items()[0]["name"] == "Carnitas Taco"


def test_organizer_can_create_an_event(client):
    with app.app_context():
        owner = FoodTruckOwner(
            email="truck@example.com",
            name="Truck Owner",
            business_name="Green Truck",
            password_hash="unused",
            status="approved",
        )
        db.session.add(owner)
        db.session.flush()
        truck = FoodTruck(
            name="Green Truck",
            description="Organic",
            owner_id=owner.id,
            sales_goal=500,
            status="approved",
            registration_fee_charged=True,
        )
        truck.set_menu_items([{"name": "Veggie Bowl", "price": 11.0, "description": "Grains"}])
        db.session.add(truck)
        db.session.commit()
        truck_id = truck.id

    registered = client.post("/organizer/register", data={
        "name": "Event Organizer",
        "email": "organizer@example.com",
        "password": "organizer-password",
        "terms_agreement": "on",
    }, follow_redirects=True)
    assert registered.status_code == 200

    with app.app_context():
        assert Organizer.query.filter_by(email="organizer@example.com").count() == 1

    event_date = (datetime.utcnow() + timedelta(days=21)).strftime("%Y-%m-%dT18:00")
    created = client.post("/organizer/create-event", data={
        "name": "School Lunch Fundraiser",
        "description": "Raise the truck minimum for Friday lunch.",
        "date": event_date,
        "location": "Culver City, CA",
        "food_truck_id": str(truck_id),
        "markup_percentage": "15",
        "selected_items": "0",
    }, follow_redirects=False)
    assert created.status_code in (302, 303)
    assert "/organizer/pay-fee/" in created.headers["Location"]

    with app.app_context():
        event = Event.query.filter_by(name="School Lunch Fundraiser").one()
        assert event.food_truck_id == truck_id
        assert event.organizer_fee_charged is False
        assert event.get_selected_menu_items()[0]["name"] == "Veggie Bowl"
        event_id = event.id

    app.config["PAYMENTS_MODE"] = "simulate"
    try:
        published = client.post(
            f"/organizer/confirm-fee-payment/{event_id}",
            data={"simulate": "1"},
            follow_redirects=True,
        )
        assert published.status_code == 200
    finally:
        app.config["PAYMENTS_MODE"] = "stripe"

    with app.app_context():
        event = db.session.get(Event, event_id)
        assert event.organizer_fee_charged is True

    listing = client.get("/events")
    assert listing.status_code == 200
    assert b"School Lunch Fundraiser" in listing.data


def test_pledge_uses_stripe_test_mode(client):
    with app.app_context():
        owner = FoodTruckOwner(
            email="truck2@example.com",
            name="Truck Owner",
            business_name="Green Truck",
            password_hash="unused",
            status="approved",
        )
        db.session.add(owner)
        db.session.flush()
        truck = FoodTruck(
            name="Green Truck",
            description="Organic",
            owner_id=owner.id,
            sales_goal=500,
            status="approved",
            registration_fee_charged=True,
        )
        truck.set_menu_items([
            {"name": "Veggie Bowl", "price": 20.0, "original_price": 20.0, "marked_up_price": 20.0, "description": "Grains"},
        ])
        db.session.add(truck)
        db.session.flush()
        organizer = Organizer(email="org2@example.com", name="Org", password_hash="unused")
        db.session.add(organizer)
        db.session.flush()
        event = Event(
            name="Pledge Test Event",
            description="Test",
            date=datetime.utcnow() + timedelta(days=10),
            location="Los Angeles, CA",
            organizer_id=organizer.id,
            food_truck_id=truck.id,
            markup_percentage=0,
            pledge_goal=500,
            status="pending",
            organizer_fee_charged=True,
        )
        event.set_selected_menu_items(truck.get_menu_items())
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    form = client.get(f"/events/{event_id}/pledge")
    assert form.status_code == 200
    assert b"pk_test_smoke" in form.data

    intent = MagicMock()
    intent.id = "pi_test_smoke"
    intent.status = "requires_capture"
    intent.amount = 2090

    with patch("utils.stripe.PaymentIntent.create", return_value=intent) as create_intent, \
         patch("routes.stripe.PaymentIntent.confirm", return_value=intent) as confirm_intent:
        response = client.post(f"/events/{event_id}/pledge", data={
            "email": "supporter@example.com",
            "amount": "20.00",
            "stripe_payment_method": "pm_card_visa",
        }, follow_redirects=True)

    assert response.status_code == 200, response.data[:500]
    assert create_intent.called
    assert confirm_intent.called
    kwargs = create_intent.call_args.kwargs
    assert kwargs["capture_method"] == "manual"
    assert kwargs["amount"] == 2090  # $20 + 4.5% fee, in cents
    assert kwargs["currency"] == "usd"

    with app.app_context():
        pledge = Pledge.query.filter_by(email="supporter@example.com").one()
        assert pledge.status == "pending"
        assert pledge.amount == 20
        assert pledge.stripe_payment_intent_id == "pi_test_smoke"
        assert abs(pledge.processing_fee - 0.90) < 0.001


def test_admin_login(client):
    response = client.post("/admin/login", data={
        "username": os.environ["ADMIN_EMAIL"],
        "password": os.environ["ADMIN_PASSWORD"],
    })
    assert response.status_code == 200
    assert b"Login Success" in response.data

    dashboard = client.get("/admin/dashboard")
    assert dashboard.status_code == 200
