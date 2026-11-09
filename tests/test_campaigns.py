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
    assert b"Coachella" in body
    assert b"Malibu" in body
    assert b"fetchpriority=\"high\"" in body
    assert b"loading=\"lazy\"" in body
    assert b"truck-desert-vintage-01" in body
    assert b"gt-vintage" in body
    assert b"Food Truck Login" not in body
    assert b"Choose a food truck" not in body
    manifest = json.loads(open("static/images/green-truck/manifest.json").read())
    for item in manifest["images"]:
        assert item["filename"].encode() in body

    with app.app_context():
        record = CampaignPage.query.filter_by(slug="northwind-labs").one()
        assert CampaignView.query.filter_by(campaign_id=record.id).count() == 1


def test_quote_is_stored_without_sending_mail(client):
    _login_admin(client)
    _import_sample(client)
    response = client.post("/c/northwind-labs/quote", data={
        "organizer_name": "Riley Quinn",
        "organizer_email": "riley@northwind.example",
        "service_format": "truck",
        "event_date": "2026-12-09",
        "headcount": "60",
        "location": "1200 Example Ave, Culver City",
        "notes": "Loading dock on the west side.",
        "give_back": "on",
        "cause": "a local school garden",
        "give_back_percent": "10",
        "preorder": "on",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Request received" in response.data

    with app.app_context():
        quote = QuoteRequest.query.filter_by(organizer_email="riley@northwind.example").one()
        assert quote.service_format == "truck"
        assert quote.headcount == 60
        assert quote.give_back is True
        assert quote.preorder_requested is True
        assert quote.email_notified is False
        campaign_id = quote.campaign_id

    detail = client.get(f"/admin/campaigns/{campaign_id}")
    assert detail.status_code == 200
    assert b"Riley Quinn" in detail.data
    assert b"In admin only" in detail.data


def test_admin_preview_does_not_count_as_a_view(client):
    _login_admin(client)
    _import_sample(client)
    assert client.get("/c/harbor-and-pine?preview=1").status_code == 200
    with app.app_context():
        page = CampaignPage.query.filter_by(slug="harbor-and-pine").one()
        assert CampaignView.query.filter_by(campaign_id=page.id).count() == 0


def test_unknown_campaign_is_404(client):
    assert client.get("/c/not-a-real-company").status_code == 404
