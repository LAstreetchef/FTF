import os

from app import app, db
from models import CampaignPage

BASE = "https://events.greentruckonthego.com"
OLD_HOST = "food-truck-fundraiser.onrender.com"


def _page():
    with app.app_context():
        page = CampaignPage(
            slug="public-host-check",
            company_name="Public Host",
            contact_name="Pat Example",
            contact_email="pat@public-host.example",
            personal_note="Not a customer.",
        )
        db.session.add(page)
        db.session.commit()


def test_public_base_url_redirects_get_and_rewrites_links(client):
    _page()
    os.environ["PUBLIC_BASE_URL"] = BASE
    try:
        moved = client.get("/c/public-host-check", headers={"Host": OLD_HOST})
        assert moved.status_code == 301
        assert moved.headers["Location"] == f"{BASE}/c/public-host-check"

        kept = client.get("/c/public-host-check?thanks=1", headers={"Host": OLD_HOST})
        assert kept.headers["Location"] == f"{BASE}/c/public-host-check?thanks=1"

        health = client.get("/health", headers={"Host": OLD_HOST})
        assert health.status_code == 200

        hook = client.get("/stripe/webhook", headers={"Host": OLD_HOST})
        assert hook.status_code != 301

        posted = client.post(
            "/c/public-host-check/start",
            headers={"Host": OLD_HOST},
            data={},
        )
        assert posted.status_code != 301

        page = client.get("/c/public-host-check", headers={"Host": "events.greentruckonthego.com"})
        assert page.status_code == 200
        body = page.data
        assert f"{BASE}/c/public-host-check".encode() in body
        assert f"{BASE}/c/public-host-check/card.png".encode() in body
        assert b"food-truck-fundraiser.onrender.com" not in body
        assert b'rel="canonical"' in body
        assert b'property="og:url"' in body
    finally:
        os.environ.pop("PUBLIC_BASE_URL", None)


def test_without_public_base_url_the_render_host_stays(client):
    _page()
    os.environ.pop("PUBLIC_BASE_URL", None)
    stayed = client.get("/c/public-host-check", headers={"Host": OLD_HOST})
    assert stayed.status_code == 200
    assert b"food-truck-fundraiser.onrender.com/c/public-host-check" in stayed.data
