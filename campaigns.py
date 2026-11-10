"""Green Truck holiday pages. One shareable URL per prospect company.

These pages are Green Truck only: no other trucks, no marketplace.
Photographs come from static/images/green-truck/manifest.json, with
optional server-side overrides in instance/campaign_photos/.
"""

import csv
import hashlib
import io
import json
import logging
import math
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import quote

from flask import abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from sqlalchemy import func, inspect
from werkzeug.security import generate_password_hash
from app import app, db
from green_truck_menu import (
    CLASSIC_MENU,
    ENTREES,
    campaign_fee_rate,
    combo_charge,
    combo_description,
    combo_label,
    campaign_days,
    combo_price,
    combo_price_id,
    combo_product_id,
    combo_unit_cents,
    combos_needed,
    minimum_amount,
    minimum_label,
)
from models import (
    CampaignPage,
    CampaignView,
    EmailLog,
    Event,
    FoodTruck,
    Organizer,
    Pledge,
    QuoteRequest,
)
from payments import authorize_card
from utils import (
    charge_stripe_payment,
    generate_ticket_code,
    release_and_notify_pledgers,
    send_conditional_pledge_confirmation,
    send_email,
)

HERO_FILE = "truck-exterior-02.jpg"
VINTAGE_FILE = "truck-desert-vintage-01.jpg"

CSV_FIELDS = [
    "company",
    "contact_name",
    "contact_email",
    "personal_note",
    "logo_url",
    "suggested_dates",
    "give_back_cause",
    "slug",
    "sponsor_anonymous",
]

DEMO_CAMPAIGNS = [
    {
        "slug": "northwind-labs",
        "company_name": "Northwind Labs",
        "contact_name": "Avery Chen",
        "contact_email": "avery@northwind.example",
        "personal_note": "Avery — for the Culver City floor. The truck can sit in the lot and cook to order, or we can drop a holiday lunch at the desk. December is open.",
        "suggested_dates": ["2026-12-04", "2026-12-09", "2026-12-11", "2026-12-16"],
        "give_back_cause": "a local school garden",
    },
    {
        "slug": "harbor-and-pine",
        "company_name": "Harbor & Pine",
        "contact_name": "Jordan Hale",
        "contact_email": "jordan@harborandpine.example",
        "personal_note": "Jordan — Playa Vista offices are an easy roll for us. Happy to park the truck for the team or pack a staff lunch and leave it with you.",
        "suggested_dates": ["2026-12-08", "2026-12-10", "2026-12-15", "2026-12-17"],
        "give_back_cause": "",
    },
    {
        "slug": "lumen-desk",
        "company_name": "Lumen Desk",
        "contact_name": "Sam Okonkwo",
        "contact_email": "sam@lumendesk.example",
        "personal_note": "Sam — Santa Monica is on the route. If the lot is tight, drop-off is just as good. Tell me the headcount and I’ll price the day.",
        "suggested_dates": ["2026-12-03", "2026-12-07", "2026-12-14", "2026-12-18"],
        "give_back_cause": "",
    },
    {
        "slug": "preview",
        "company_name": "Preview Office",
        "contact_name": "Pat Example",
        "contact_email": "pat@preview.example",
        "personal_note": "Pat — this sample page is for trying the truck day. Share it with the office. Nothing here is a real customer.",
        "suggested_dates": ["2026-12-04", "2026-12-11", "2026-12-18"],
        "give_back_cause": "",
    },
]

WEEKDAYS = (
    ("mon", "Mon"),
    ("tue", "Tue"),
    ("wed", "Wed"),
    ("thu", "Thu"),
    ("fri", "Fri"),
)
_WEEKDAY_NAME = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value):
    slug = _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-")
    return slug[:80]


def possessive(name):
    name = (name or "").strip()
    if name.lower().endswith("s"):
        return f"{name}'"
    return f"{name}'s"


def parse_dates(raw):
    dates = []
    for part in re.split(r"[|;,]", raw or ""):
        part = part.strip()
        if not part:
            continue
        try:
            dates.append(datetime.strptime(part, "%Y-%m-%d").date().isoformat())
        except ValueError:
            continue
    # Keep order, drop duplicates.
    seen = set()
    unique = []
    for item in dates:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def format_date(iso_date):
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%a, %b %-d")
    except ValueError:
        return iso_date


def safe_logo(url):
    url = (url or "").strip()
    if url.startswith("https://") and " " not in url and len(url) <= 500:
        return url
    return ""


def static_photo_dir():
    return os.path.join(app.root_path, "static", "images", "green-truck")


def override_photo_dir():
    return os.path.join(app.instance_path, "campaign_photos")


def _static_url(filename):
    return url_for("static", filename=f"images/green-truck/img/{filename}")


def _upload_url(filename):
    return url_for("campaign_photo_file", filename=filename)


def _manifest_images():
    path = os.path.join(static_photo_dir(), "manifest.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        logging.warning("Could not read Green Truck photo manifest")
        return []
    images = data.get("images") or []
    return [item for item in images if item.get("filename")]


def _overrides():
    path = os.path.join(override_photo_dir(), "overrides.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def resolve_photo(item):
    """Build src/srcset for one manifest image. Missing files stay placeholders."""
    filename = os.path.basename(item.get("filename") or "")
    stem = filename.rsplit(".", 1)[0]
    photo = {
        "id": stem,
        "file": filename,
        "category": item.get("category") or "",
        "alt": item.get("description") or "Green Truck",
        "caption": item.get("description") or "",
        "width": int(item.get("width") or 1600),
        "height": int(item.get("height") or 1067),
        "src": None,
        "srcset": None,
        "webp_srcset": None,
        "placeholder": True,
        "vintage": filename == VINTAGE_FILE,
    }
    override = _overrides().get(stem)
    if override and os.path.isfile(os.path.join(override_photo_dir(), override)):
        small = f"{stem}-800.jpg"
        photo.update(src=_upload_url(override), placeholder=False, vintage=filename == VINTAGE_FILE)
        if os.path.isfile(os.path.join(override_photo_dir(), small)):
            photo["srcset"] = f"{_upload_url(small)} 800w, {_upload_url(override)} 1600w"
        return photo
    folder = os.path.join(static_photo_dir(), "img")
    jpg_path = os.path.join(folder, filename)
    if not filename or not os.path.isfile(jpg_path):
        return photo
    photo["src"] = _static_url(filename)
    photo["placeholder"] = False
    if filename == VINTAGE_FILE:
        small_webp = f"{stem}-480.webp"
        if os.path.isfile(os.path.join(folder, small_webp)):
            photo["webp_srcset"] = f"{_static_url(small_webp)} 480w"
        photo["srcset"] = None
        return photo
    webp_800 = f"{stem}-800.webp"
    webp_1600 = f"{stem}-1600.webp"
    parts = []
    if os.path.isfile(os.path.join(folder, webp_800)):
        parts.append(f"{_static_url(webp_800)} 800w")
    if os.path.isfile(os.path.join(folder, webp_1600)):
        parts.append(f"{_static_url(webp_1600)} 1600w")
    if parts:
        photo["webp_srcset"] = ", ".join(parts)
    return photo


def photo_library():
    library = {}
    for item in _manifest_images():
        photo = resolve_photo(item)
        if photo["id"]:
            library[photo["file"]] = photo
    return library


def photo_list():
    return [resolve_photo(item) for item in _manifest_images()]


def _visitor_hash():
    salt = str(app.secret_key or "")
    raw = f"{salt}|{request.remote_addr or ''}|{request.user_agent.string[:160] if request.user_agent else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _record_view(page):
    if request.args.get("preview") == "1" and session.get("admin_id"):
        return
    referrer = (request.referrer or "")[:300]
    db.session.add(CampaignView(
        campaign_id=page.id,
        visitor_hash=_visitor_hash(),
        referrer=referrer,
    ))
    db.session.commit()


def _notify_email():
    return (os.environ.get("CAMPAIGN_NOTIFY_EMAIL") or os.environ.get("ADMIN_EMAIL") or "").strip()


def _send_quote_email(page, quote):
    recipient = _notify_email()
    if not recipient or app.config.get("MAIL_SUPPRESS_SEND"):
        return False
    format_label = {
        "truck": "Truck in the lot",
        "dropoff": "Drop-off catering",
    }.get(quote.service_format, "Classic menu")
    give = "No"
    if quote.give_back:
        give = f"Yes — {quote.give_back_percent or 10}% for {quote.cause or 'a cause they will name'}"
        if quote.preorder_requested:
            give += ". They want a private pre-order page."
    body = (
        f"New Green Truck holiday request from {page.company_name}\n\n"
        f"Page: {request.url_root.rstrip('/')}/c/{page.slug}\n"
        f"Contact: {quote.organizer_name} <{quote.organizer_email}>\n"
        f"Format: {format_label}\n"
        f"Date: {quote.event_date}\n"
        f"Headcount: {quote.headcount}\n"
        f"Location: {quote.location}\n"
        f"Give-back: {give}\n"
        f"Notes: {quote.notes or '—'}\n"
    )
    return send_email(recipient, f"Holiday truck request — {page.company_name}", body)


def _require_admin():
    if not session.get("admin_id"):
        return redirect(url_for("admin_login"))
    return None


def ensure_desk_check():
    """One fictional office so the event page has a public URL. Not a customer."""
    if os.environ.get("APP_ENV") == "testing":
        return
    if CampaignPage.query.filter_by(slug="desk-check").first():
        return
    page = CampaignPage(
        slug="desk-check",
        company_name="Desk Check",
        contact_name="Pat Example",
        contact_email="pat@desk-check.example",
        personal_note="Pat — this sample page is for the office event layout. It is not a customer.",
    )
    page.set_suggested_dates(["2026-12-04", "2026-12-11", "2026-12-18"])
    db.session.add(page)
    db.session.commit()


def ensure_anon_check():
    """Fictional anonymous-sponsor page. Not a customer."""
    if os.environ.get("APP_ENV") == "testing":
        return
    if CampaignPage.query.filter_by(slug="anon-check").first():
        return
    page = CampaignPage(
        slug="anon-check",
        company_name="Anon Check",
        contact_name="Alex Example",
        contact_email="alex@anon-check.example",
        personal_note="This sample page checks the unnamed host. It is not a customer.",
        sponsor_anonymous=True,
    )
    page.set_suggested_dates(["2026-12-02", "2026-12-09", "2026-12-16"])
    db.session.add(page)
    db.session.commit()


E2E_SLUGS = {"e2e-fund", "e2e-miss"}
E2E_FUND_GOAL = 36.0


def ensure_e2e_checks():
    """Two fictional offices for a Stripe test-card walk. Not customers."""
    if os.environ.get("APP_ENV") == "testing":
        return
    samples = (
        ("e2e-fund", "E2E Fund", "pat@e2e-fund.example", "This sample funds on two test combos. It is not a customer."),
        ("e2e-miss", "E2E Miss", "pat@e2e-miss.example", "This sample is released before the goal. It is not a customer."),
    )
    for slug, company, email, note in samples:
        if CampaignPage.query.filter_by(slug=slug).first():
            continue
        page = CampaignPage(
            slug=slug,
            company_name=company,
            contact_name="Pat Example",
            contact_email=email,
            personal_note=note,
        )
        page.set_suggested_dates(["2026-12-04", "2026-12-11", "2026-12-18"])
        db.session.add(page)
    db.session.commit()


def _e2e_page(slug):
    if slug not in E2E_SLUGS:
        return None
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page or not (page.contact_email or "").endswith(".example"):
        return None
    return page


def seed_demo_campaigns():
    """Fictional prospects only. Never real customer names or inboxes."""
    if os.environ.get("APP_ENV") == "production":
        return
    flag = (os.environ.get("SEED_DEMO_DATA") or "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    for item in DEMO_CAMPAIGNS:
        page = CampaignPage.query.filter_by(slug=item["slug"]).first()
        if page:
            continue
        page = CampaignPage(
            slug=item["slug"],
            company_name=item["company_name"],
            contact_name=item["contact_name"],
            contact_email=item["contact_email"],
            personal_note=item["personal_note"],
            give_back_cause=item["give_back_cause"],
        )
        page.set_suggested_dates(item["suggested_dates"])
        db.session.add(page)
    db.session.commit()


def upsert_campaign_row(row):
    company = (row.get("company") or "").strip()
    if not company:
        return None, "Each row needs a company name."
    slug = slugify(row.get("slug") or company)
    if not slug:
        return None, f"Could not make a URL slug for {company}."
    logo = (row.get("logo_url") or "").strip()
    if logo and not safe_logo(logo):
        logo = ""
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page:
        page = CampaignPage(slug=slug, company_name=company)
        db.session.add(page)
    page.company_name = company[:160]
    page.contact_name = (row.get("contact_name") or "")[:120]
    page.contact_email = (row.get("contact_email") or "")[:200]
    note = (row.get("personal_note") or "").strip()
    if not note:
        note = (
            f"We would like to bring Green Truck to {company} this December — "
            "the truck in the lot, or a holiday lunch dropped at the office."
        )
    page.personal_note = note[:2000]
    page.logo_url = safe_logo(logo)
    page.give_back_cause = (row.get("give_back_cause") or "")[:200]
    page.set_suggested_dates(parse_dates(row.get("suggested_dates") or ""))
    if "sponsor_anonymous" in row:
        page.sponsor_anonymous = (row.get("sponsor_anonymous") or "").strip().lower() in {"1", "true", "yes", "on"}
    return page, None


def _campaign_counts():
    views = dict(db.session.query(CampaignView.campaign_id, func.count(CampaignView.id)).group_by(CampaignView.campaign_id))
    unique = dict(
        db.session.query(CampaignView.campaign_id, func.count(func.distinct(CampaignView.visitor_hash)))
        .group_by(CampaignView.campaign_id)
    )
    requests = dict(db.session.query(QuoteRequest.campaign_id, func.count(QuoteRequest.id)).group_by(QuoteRequest.campaign_id))
    return views, unique, requests


def ensure_campaign_columns():
    """Add sponsor fields on databases created before this flow."""
    try:
        columns = {col["name"] for col in inspect(db.engine).get_columns("campaign_page")}
    except Exception:
        db.session.rollback()
        return
    additions = {
        "event_id": "INTEGER",
        "office_address": "VARCHAR(240)",
        "guest_count": "INTEGER",
        "preferred_weekday": "VARCHAR(3)",
        "booked_date": "VARCHAR(10)",
        "available_dates": "TEXT",
        "host_token": "VARCHAR(64)",
        "goal_notified": "BOOLEAN",
        "sponsor_anonymous": "BOOLEAN NOT NULL DEFAULT false" if db.engine.dialect.name == "postgresql" else "BOOLEAN DEFAULT 0",
    }
    changed = False
    for name, column_type in additions.items():
        if name in columns:
            continue
        db.session.execute(db.text(f"ALTER TABLE campaign_page ADD COLUMN {name} {column_type}"))
        changed = True
    if changed:
        db.session.commit()


def weekday_dates(weekday):
    """Every matching weekday from Dec 1 through Dec 19, 2026."""
    target = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}.get(weekday)
    if target is None:
        return []
    cursor = date(2026, 12, 1)
    last = date(2026, 12, 19)
    found = []
    while cursor <= last:
        if cursor.weekday() == target:
            found.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return found


def _host_map():
    hosts = session.get("campaign_hosts")
    return hosts if isinstance(hosts, dict) else {}


def _remember_host(page):
    hosts = _host_map()
    hosts[page.slug] = page.host_token
    session["campaign_hosts"] = hosts
    session.modified = True


def _is_host(page):
    token = _host_map().get(page.slug)
    return bool(page.host_token and token and token == page.host_token)


def _green_truck():
    truck = FoodTruck.query.filter_by(name="Green Truck").first()
    if truck:
        return truck
    truck = FoodTruck(
        name="Green Truck",
        description="Classic menu. Combo is an entree, a side, and a drink.",
        sales_goal=float(minimum_amount()),
        status="approved",
        registration_fee_charged=True,
        approved_at=datetime.utcnow(),
    )
    truck.set_menu_items([{
        "name": "Combo",
        "price": combo_price(),
        "description": combo_description(),
    }])
    db.session.add(truck)
    db.session.flush()
    return truck


def _sponsor_organizer(page, name, email=None):
    email = (email or page.contact_email or f"sponsor-{page.slug}@example.com").strip()[:120]
    organizer = Organizer.query.filter_by(email=email).first()
    if organizer:
        if name:
            organizer.name = name[:100]
        return organizer
    organizer = Organizer(
        email=email,
        name=(name or page.company_name)[:100],
        password_hash=generate_password_hash(secrets.token_urlsafe(24)),
    )
    db.session.add(organizer)
    db.session.flush()
    return organizer


def _status_label(page):
    event = page.event
    if not event:
        return ""
    if event.status == "cancelled":
        return "cancelled"
    if page.booked_date and event.organizer_entree_claimed:
        return "booked"
    if page.booked_date:
        return "date picked"
    if event.is_goal_met():
        return "goal met"
    return "started"


def campaign_closes_at(event):
    """When this office campaign must be captured or released.

    Stripe card holds last about seven days. Close two hours before that
    so a sleeping host still beats capture_before.
    """
    started = event.created_at or datetime.utcnow()
    configured = started + timedelta(days=campaign_days())
    hold_limit = started + timedelta(days=7) - timedelta(hours=2)
    return min(configured, hold_limit)


def _countdown_label(closes_at):
    remaining = closes_at - datetime.utcnow()
    seconds = remaining.total_seconds()
    if seconds <= 0:
        return "Closed"
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    if days:
        return f"{days}d {hours}h {minutes}m left"
    return f"{hours}h {minutes}m left"


def _cancel_for_deadline(page, event):
    release_and_notify_pledgers(event)
    event.status = "cancelled"
    recipient = (page.contact_email or (event.organizer.email if event.organizer else ""))[:120]
    subject = f"{page.company_name} truck day ended"
    body = (
        f"{page.company_name} did not reach ${minimum_amount():,} in {campaign_days()} days. "
        "Card holds were released. No one was charged."
    )
    sent = False
    if recipient and not app.config.get("MAIL_SUPPRESS_SEND"):
        sent = bool(send_email(recipient, subject, body))
    else:
        logging.info("Deadline email logged, not sent, for %s", page.slug)
    if event.organizer and event.organizer.email and event.organizer.email != recipient:
        send_email(
            event.organizer.email,
            f"Event Cancelled: {event.name}",
            f"Your event '{event.name}' has been cancelled.\n\nPending card holds were released. No one was charged.",
        )
    _log_campaign_email(recipient, subject, body, sent)
    db.session.commit()
    logging.info("Campaign %s cancelled at the deadline", page.slug)


def sweep_campaign_deadlines(only_page=None):
    """Capture a met goal, or cancel and release holds once the window closes.

    Render's free plan sleeps, so this also runs on campaign and admin views.
    A cron hit to /campaigns/sweep is what covers a week when nobody visits.
    """
    query = CampaignPage.query.filter(CampaignPage.event_id.isnot(None))
    if only_page is not None:
        query = query.filter(CampaignPage.id == only_page.id)
    closed = 0
    now = datetime.utcnow()
    for page in query.all():
        event = page.event
        if not event or event.status != "pending":
            continue
        if event.is_goal_met():
            _capture_pending(page, event)
            continue
        if now >= campaign_closes_at(event):
            _cancel_for_deadline(page, event)
            closed += 1
    return closed


def _office_dates(page):
    chosen = page.get_available_dates()
    if chosen:
        return chosen
    return weekday_dates(page.preferred_weekday)


def office_city(address):
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    if len(parts) < 2:
        return ""
    city = parts[1]
    if len(city) <= 2 and city.isalpha():
        return ""
    return city


def _pledge_meta(pledge):
    items = pledge.get_selected_menu_items()
    return items[0] if items else {}


def _public_name(full):
    parts = [part for part in (full or "").split() if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][:1].upper()}."


def _event_pledges(event_id):
    if not event_id:
        return []
    return Pledge.query.filter_by(event_id=event_id).order_by(Pledge.created_at.desc()).all()


def _find_by_code(event_id, code):
    if not code:
        return None
    for pledge in _event_pledges(event_id):
        if _pledge_meta(pledge).get("referral_code") == code and pledge.status != "cancelled":
            return pledge
    return None


def _referred_meals(event_id, code):
    total = 0
    price = combo_price() or 1
    for pledge in _event_pledges(event_id):
        meta = _pledge_meta(pledge)
        if meta.get("referred_by") != code or pledge.status == "cancelled":
            continue
        qty = meta.get("quantity")
        total += int(qty) if isinstance(qty, int) else int(round((pledge.amount or 0) / price))
    return total


def _qr_markup(text):
    import segno
    from markupsafe import Markup
    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="svg", xmldecl=False, nl=False, scale=3, border=1, dark="#111111")
    return Markup(buffer.getvalue().decode())


def _public_host(page):
    """Name the public page may use. Anonymous sponsors stay unnamed."""
    if page.sponsor_anonymous:
        return "A coworker"
    name = (page.contact_name or "").strip()
    return name or "A coworker"


def _host_line(page):
    office = page.company_name
    if page.sponsor_anonymous or not (page.contact_name or "").strip():
        return f"A coworker is bringing Green Truck to {office}."
    return f"{_public_host(page)} is bringing Green Truck to {office}."


def _sponsor_paste(page, url):
    goal = f"${minimum_amount():,}"
    days = campaign_days()
    price = combo_price()
    if page.sponsor_anonymous:
        return (
            f"We're bringing Green Truck to the office for the holidays. "
            f"${price} combo — entree, side, and drink. "
            f"Nobody is charged unless we hit {goal} in {days} days. {url}"
        )
    return (
        f"I'm bringing Green Truck to the office for the holidays. "
        f"${price} combo — entree, side, and drink. "
        f"Nobody is charged unless we hit {goal} in {days} days. "
        f"Then I pick the date, and my meal is on us. {url}"
    )


def _share_pack(url, company, remaining, when, lead="", percent_label=""):
    progress = f"{percent_label}. " if percent_label else ""
    text = (
        f"{lead} {progress}We're {remaining} combos from a Green Truck day at {company} on {when}. "
        f"${combo_price()} entree+side+drink, only charged if we hit the goal: {url}"
    ).strip()
    return {
        "url": url,
        "text": text,
        "mailto": "mailto:?subject=" + quote(f"Green Truck at {company}") + "&body=" + quote(text),
        "sms": "sms:?&body=" + quote(text),
        "qr": _qr_markup(url),
    }


def _when_label(page, event):
    weekday = _WEEKDAY_NAME.get(page.preferred_weekday or "", "")
    if page.booked_date and event and getattr(event, "date", None):
        return event.date.strftime("%a, %b %-d, %Y · %-I:%M %p")
    if weekday:
        return f"{weekday} · date set when the goal is met"
    return "Date set when the goal is met"


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(value):
    text = (value or "").strip()
    return bool(text) and len(text) <= 120 and _EMAIL_RE.match(text)


def _progress_percent(raised, goal, goal_met):
    """Whole-number progress. Floor it, and never say 100% before the goal is met."""
    if goal_met:
        return 100, "100%"
    if not goal or raised <= 0:
        return 0, "0%"
    whole = math.floor((float(raised) / float(goal)) * 100)
    if whole < 1:
        return 0, "<1%"
    return min(whole, 99), f"{min(whole, 99)}%"


def _milestone(percent):
    if percent >= 100:
        return "The office made it."
    if percent >= 75:
        return "Almost there."
    if percent >= 50:
        return "Halfway there."
    if percent >= 25:
        return "A quarter of the way."
    return ""


def _urgent_label(closes_at, gap):
    seconds = max(0, (closes_at - datetime.utcnow()).total_seconds())
    total_minutes = int(seconds // 60)
    return f"Ends in {total_minutes // 60:02d}:{total_minutes % 60:02d}. {gap} combos to go or nobody eats."


def office_snapshot(page):
    event = page.event
    price = combo_price()
    raised = float(event.current_pledges or 0) if event else 0.0
    meals = int(round(raised / price)) if price else 0
    goal_amount = float(event.pledge_goal) if event and event.pledge_goal else float(minimum_amount())
    needed = max(1, math.ceil(goal_amount / price)) if price else combos_needed()
    gap = max(0, needed - meals)
    pledges = _event_pledges(page.event_id)
    team_meals = 0
    wall = []
    for pledge in pledges:
        if pledge.status == "cancelled":
            continue
        meta = _pledge_meta(pledge)
        qty = meta.get("quantity")
        count = int(qty) if isinstance(qty, int) else int(round((pledge.amount or 0) / (price or 1)))
        if meta.get("team"):
            team_meals += count
        label = _public_name(meta.get("supporter") or "")
        if label and len(wall) < 5:
            wall.append({"name": label, "count": count, "team": bool(meta.get("team"))})
    weekday = _WEEKDAY_NAME.get(page.preferred_weekday or "", "")
    when = _when_label(page, event)
    share_url = url_for("campaign_page", slug=page.slug, _external=True)
    if event:
        percent, percent_label = _progress_percent(
            raised, event.get_total_goal_amount(), event.is_goal_met()
        )
    else:
        percent, percent_label = 0, "0%"
    share = _share_pack(share_url, page.company_name, gap, when, _host_line(page), percent_label)
    closes = None
    urgent = False
    countdown = ""
    if event and event.created_at and event.status == "pending" and not event.is_goal_met():
        closes = campaign_closes_at(event)
        urgent = (closes - datetime.utcnow()).total_seconds() <= 48 * 3600
        countdown = _urgent_label(closes, gap) if urgent else _countdown_label(closes)
    return {
        "started": event is not None,
        "host": _is_host(page),
        "raised": raised,
        "to_go": max(0, goal_amount - raised),
        "meals": meals,
        "goal": goal_amount,
        "needed": needed,
        "gap": gap,
        "team_meals": team_meals,
        "wall": wall,
        "percent": percent,
        "percent_label": percent_label,
        "milestone": _milestone(percent),
        "goal_met": bool(event and event.is_goal_met()),
        "booked": bool(page.booked_date and event and event.organizer_entree_claimed),
        "booked_label": format_date(page.booked_date) if page.booked_date else "",
        "when": when,
        "city": office_city(page.office_address),
        "dates": [(item, format_date(item)) for item in _office_dates(page)],
        "status": _status_label(page),
        "share_url": share["url"],
        "share_text": share["text"],
        "mailto": share["mailto"],
        "sms": share["sms"],
        "qr": share["qr"],
        "weekday_label": weekday,
        "free_meal": bool(event and event.organizer_entree_claimed),
        "cancelled": bool(event and event.status == "cancelled"),
        "closes_at": closes.strftime("%Y-%m-%dT%H:%M:%SZ") if closes else "",
        "countdown": countdown,
        "urgent": urgent,
        "close_gap": bool(event and _is_host(page) and percent >= 75 and not event.is_goal_met() and gap > 0),
        "host_line": _host_line(page) if event else "",
        "paste": _sponsor_paste(page, share_url) if event else "",
        "days": campaign_days(),
        "anonymous": bool(page.sponsor_anonymous),
        "ticket_host": "Your office's host" if page.sponsor_anonymous else _public_host(page),
    }


def _log_campaign_email(recipient, subject, body, sent):
    db.session.add(EmailLog(
        recipient=(recipient or "unconfigured")[:120],
        subject=subject[:200],
        body=body,
        status="sent" if sent else "logged",
        sent_at=datetime.utcnow() if sent else None,
    ))


def _notify_goal(page, event):
    if page.goal_notified:
        return
    recipient = (page.contact_email or (event.organizer.email if event.organizer else ""))[:120]
    subject = f"{page.company_name} reached the Green Truck goal"
    body = (
        f"{page.company_name} reached ${minimum_amount():,}. "
        f"Pick one {office_snapshot(page)['weekday_label'] or 'day'} in December.\n"
        f"{url_for('campaign_page', slug=page.slug, _external=True)}"
    )
    sent = False
    if recipient and not app.config.get("MAIL_SUPPRESS_SEND"):
        sent = bool(send_email(recipient, subject, body))
    else:
        logging.info("Goal email logged, not sent, for %s to %s", page.slug, recipient or "nobody")
    _log_campaign_email(recipient, subject, body, sent)
    page.goal_notified = True


def _ticket_body(page, event, pledge, total):
    subtotal = pledge.amount or 0
    fee = pledge.processing_fee or 0
    rate_label = f"{campaign_fee_rate() * 100:.1f}".rstrip("0").rstrip(".")
    host_label = "Your office's host" if page.sponsor_anonymous else (page.contact_name or "Your office's host")
    return (
        f"Thank you for your pledge! Your payment has been processed.\n\n"
        f"PAYMENT BREAKDOWN:\nCombos: ${subtotal:.2f}\n"
        f"Service fee ({rate_label}%): ${fee:.2f}\nTotal Charged: ${total:.2f}\n\n"
        f"Host: {host_label}\n\n"
        f"E-TICKET CODE: {pledge.ticket_code}\n\nEvent: {event.name}\nDate: {event.date}\n"
        f"Location: {event.location}\n\nShow this code at the food truck to redeem your meal."
    )


def _send_ticket(page, event, pledge, total):
    subject = f"Your E-Ticket for {event.name}"
    body = _ticket_body(page, event, pledge, total)
    sent = False
    if pledge.email and not app.config.get("MAIL_SUPPRESS_SEND"):
        sent = bool(send_email(pledge.email, subject, body))
    else:
        logging.info("E-ticket logged, not sent, for pledge %s", pledge.id)
    _log_campaign_email(pledge.email, subject, body, sent)
    pledge.ticket_sent = sent
    return sent


def _capture_pending(page, event):
    """Capture authorized pledges once the office has reached the goal."""
    pending = Pledge.query.filter_by(event_id=event.id, status="pending").all()
    for pledge in pending:
        intent_id = pledge.stripe_payment_intent_id or ""
        if intent_id.startswith("sim_") or pledge.stripe_token == "simulated":
            pledge.status = "charged"
            pledge.charged_at = datetime.utcnow()
            pledge.ticket_code = pledge.ticket_code or generate_ticket_code()
            logging.info("Simulated capture for pledge %s on event %s", pledge.id, event.id)
            _send_ticket(page, event, pledge, (pledge.amount or 0) + (pledge.processing_fee or 0))
            continue
        result = charge_stripe_payment(intent_id, pledge.amount, f"Food Truck Event: {event.name}")
        if not result.get("success"):
            logging.error("Capture failed for pledge %s: %s", pledge.id, result.get("error"))
            continue
        pledge.status = "charged"
        pledge.charged_at = datetime.utcnow()
        pledge.ticket_code = pledge.ticket_code or generate_ticket_code()
        total = result.get("total_charged") or ((pledge.amount or 0) + (pledge.processing_fee or 0))
        logging.info("Captured %s for %s total %s", intent_id, page.slug, total)
        _send_ticket(page, event, pledge, total)
    if event.status == "pending":
        event.status = "funded"
    _notify_goal(page, event)
    db.session.commit()


def _settle(page, event, pledge):
    event.update_pledge_total()
    if event.is_goal_met():
        _capture_pending(page, event)
        return
    try:
        gift = pledge.is_gift
        if gift and not pledge.recipient_email:
            pledge.is_gift = False
        send_conditional_pledge_confirmation(pledge, event)
        pledge.is_gift = gift
    except Exception:
        logging.exception("Conditional pledge email failed for pledge %s", pledge.id)


def _thanks_view(page):
    code = (request.args.get("thanks") or "").strip()
    if not code or not page.event_id:
        return None
    pledge = _find_by_code(page.event_id, code)
    if not pledge:
        return None
    meta = _pledge_meta(pledge)
    url = url_for("campaign_page", slug=page.slug, r=code, _external=True)
    when = _when_label(page, page.event)
    gap = max(0, combos_needed() - int(round((page.event.current_pledges or 0) / (combo_price() or 1))))
    _, percent_label = _progress_percent(
        page.event.current_pledges or 0,
        page.event.get_total_goal_amount(),
        page.event.is_goal_met(),
    )
    pack = _share_pack(url, page.company_name, gap, when, percent_label=percent_label)
    return {
        "url": pack["url"],
        "text": pack["text"],
        "mailto": pack["mailto"],
        "sms": pack["sms"],
        "qr": pack["qr"],
        "brought": _referred_meals(page.event_id, code),
        "ticket": pledge.ticket_code or "",
        "gift": bool(pledge.is_gift),
        "recipient": pledge.recipient_name or "",
        "quantity": int(meta.get("quantity") or 1),
    }


def _render_campaign(page, form=None, errors=None, open_sheet=None):
    office = office_snapshot(page)
    if open_sheet is None:
        open_sheet = bool(office["started"] or errors)
    return render_template(
        "campaigns/page.html",
        page=page,
        photos=photo_library(),
        possessive_name=possessive(page.company_name),
        classic_menu=CLASSIC_MENU,
        entrees=ENTREES,
        minimum_label=minimum_label(),
        combo_label=combo_label(),
        combo_price=combo_price(),
        unit_cents=combo_unit_cents(),
        fee_rate=campaign_fee_rate(),
        weekdays=WEEKDAYS,
        office=office,
        form=form or {},
        errors=errors or [],
        open_sheet=open_sheet,
        stripe_key=app.config.get("STRIPE_PUBLISHABLE_KEY") or "",
        payments_mode=app.config.get("PAYMENTS_MODE"),
        thanks=_thanks_view(page),
        open_pledge=request.endpoint == "campaign_pledge" and bool(errors),
        just_started=request.args.get("started") == "1",
    )


@app.route("/c/<slug>")
def campaign_page(slug):
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page:
        abort(404)
    token = (request.args.get("host") or "").strip()
    ref = (request.args.get("r") or "").strip()
    if token and page.host_token and token == page.host_token:
        _remember_host(page)
    if ref:
        refs = session.get("campaign_refs") or {}
        if not isinstance(refs, dict):
            refs = {}
        refs[page.slug] = ref[:32]
        session["campaign_refs"] = refs
        session.modified = True
    if (token or ref) and not request.args.get("thanks"):
        return redirect(url_for("campaign_page", slug=slug))
    sweep_campaign_deadlines(page)
    _record_view(page)
    return _render_campaign(page)


@app.route("/c/<slug>/card.png")
def campaign_card(slug):
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page:
        abort(404)
    office = office_snapshot(page)
    from PIL import Image, ImageDraw, ImageFont
    card = Image.new("RGB", (1200, 630), (17, 17, 17))
    board = os.path.join(static_photo_dir(), "img", "brand-classic-menu-board-01.jpg")
    if os.path.isfile(board):
        photo = Image.open(board).convert("RGB")
        photo.thumbnail((560, 630))
        card.paste(photo, (1200 - photo.width, 0))
    draw = ImageDraw.Draw(card)
    font = ImageFont.load_default(size=54)
    small = ImageFont.load_default(size=32)
    draw.text((48, 70), f"Green Truck X {page.company_name}"[:42], fill="white", font=font)
    draw.text((48, 150), (office.get("host_line") or "")[:64], fill=(255, 244, 230), font=small)
    draw.text((48, 200), f"{office['meals']} of {office['needed']} combos", fill="white", font=small)
    draw.text((48, 230), office["milestone"], fill=(255, 220, 180), font=small)
    draw.rounded_rectangle((48, 320, 620, 356), radius=18, fill=(255, 255, 255, ))
    fill_to = 48 + int(572 * (office["percent"] / 100))
    draw.rounded_rectangle((48, 320, max(66, fill_to), 356), radius=18, fill=(196, 122, 48))
    out = io.BytesIO()
    card.save(out, format="PNG")
    out.seek(0)
    return app.response_class(out.getvalue(), mimetype="image/png")


def _send_sponsor_started(page):
    """Mail the host their steps. Logged for admin when SMTP is off."""
    url = url_for("campaign_page", slug=page.slug, _external=True)
    paste = _sponsor_paste(page, url)
    subject = f"You started a Green Truck day for {page.company_name}"
    body = (
        f"{_host_line(page)}\n\n"
        "You're bringing the truck in for the holidays. Coworkers each chip in for a combo. "
        f"Nobody is charged unless the office hits ${minimum_amount():,} in {campaign_days()} days. "
        "Then you pick the date, and your meal is on us.\n\n"
        "How it works for you\n"
        "1. Share your link in Slack, email, or the group chat.\n"
        "2. Watch the meter. Nudge people before the countdown ends.\n"
        "3. When it hits the goal, pick your date.\n"
        "4. We confirm and show up.\n\n"
        f"Paste this:\n{paste}\n"
    )
    recipient = (page.contact_email or "")[:120]
    sent = False
    if recipient and not app.config.get("MAIL_SUPPRESS_SEND"):
        sent = bool(send_email(recipient, subject, body))
    else:
        logging.info("Sponsor start email logged, not sent, for %s", page.slug)
    _log_campaign_email(recipient, subject, body, sent)
    db.session.commit()


@app.route("/c/<slug>/start", methods=["POST"])
def campaign_start(slug):
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page:
        abort(404)
    if (request.form.get("company_website") or "").strip():
        return redirect(url_for("campaign_page", slug=slug))
    form = {
        "organizer_name": (request.form.get("organizer_name") or "").strip(),
        "organizer_email": (request.form.get("organizer_email") or "").strip(),
        "office_address": (request.form.get("office_address") or "").strip(),
        "guest_count": (request.form.get("guest_count") or "").strip(),
        "weekday": (request.form.get("weekday") or "").strip(),
        "sponsor_anonymous": request.form.get("sponsor_anonymous") == "1",
    }
    errors = []
    if not form["organizer_name"]:
        errors.append("Add your name.")
    if not form["organizer_email"]:
        errors.append("Add your email.")
    elif not _valid_email(form["organizer_email"]):
        errors.append("That email doesn't look right.")
    if not form["office_address"]:
        errors.append("Add the office address.")
    try:
        guests = int(form["guest_count"])
        if guests < 1 or guests > 5000:
            raise ValueError
    except ValueError:
        guests = None
        errors.append("Add an approximate guest count.")
    if form["weekday"] not in _WEEKDAY_NAME:
        errors.append("Pick a weekday.")
    if errors:
        return _render_campaign(page, form=form, errors=errors, open_sheet=True), 400
    if page.event_id:
        _remember_host(page)
        return redirect(url_for("campaign_page", slug=slug))

    organizer = _sponsor_organizer(page, form["organizer_name"], form["organizer_email"])
    truck = _green_truck()
    event = Event(
        name=f"{page.company_name} Holiday Truck Day"[:200],
        description=combo_label(),
        date=datetime(2026, 12, 31, 18, 0),
        location=form["office_address"][:200],
        organizer_id=organizer.id,
        food_truck_id=truck.id,
        markup_percentage=0,
        pledge_goal=E2E_FUND_GOAL if page.slug == "e2e-fund" else float(minimum_amount()),
        status="pending",
        organizer_fee_charged=True,
    )
    event.set_selected_menu_items([{
        "name": "Combo",
        "price": combo_price(),
        "original_price": combo_price(),
        "marked_up_price": combo_price(),
        "description": combo_description(),
    }])
    db.session.add(event)
    db.session.flush()
    page.event_id = event.id
    page.contact_name = form["organizer_name"][:120]
    page.contact_email = form["organizer_email"][:120]
    page.office_address = form["office_address"][:240]
    page.guest_count = guests
    page.preferred_weekday = form["weekday"]
    page.host_token = secrets.token_urlsafe(24)
    page.booked_date = None
    page.goal_notified = False
    page.sponsor_anonymous = bool(form["sponsor_anonymous"])
    db.session.commit()
    _remember_host(page)
    _send_sponsor_started(page)
    logging.info("Campaign %s started as event %s without the organizer fee", page.slug, event.id)
    return redirect(url_for("campaign_page", slug=slug, started=1))


@app.route("/c/<slug>/pledge", methods=["POST"])
def campaign_pledge(slug):
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page or not page.event:
        abort(404)
    if (request.form.get("company_website") or "").strip():
        return redirect(url_for("campaign_page", slug=slug))
    sweep_campaign_deadlines(page)
    event = page.event
    if event.status == "cancelled":
        return _render_campaign(page, errors=["This truck day ended before the goal. Cards were not charged."], open_sheet=True), 400
    if event.status not in {"pending", "funded", "approved", "completed"}:
        return _render_campaign(page, errors=["This truck day is no longer taking combos."], open_sheet=True), 400

    form = {
        "supporter_name": (request.form.get("supporter_name") or "").strip(),
        "supporter_email": (request.form.get("supporter_email") or "").strip(),
        "quantity": (request.form.get("quantity") or "1").strip(),
        "entree": (request.form.get("entree") or "").strip(),
    }
    errors = []
    if not form["supporter_name"]:
        errors.append("Add your name.")
    email = form["supporter_email"]
    if "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Add your email.")
    try:
        quantity = int(form["quantity"])
        if quantity < 1 or quantity > 200:
            raise ValueError
    except ValueError:
        quantity = 1
        errors.append("Choose how many combos.")
    entree_names = {item["name"] for item in ENTREES}
    if form["entree"] and form["entree"] not in entree_names:
        form["entree"] = ""
    is_gift = request.form.get("gift") == "on"
    recipient = (request.form.get("recipient_name") or "").strip()
    recipient_email = (request.form.get("recipient_email") or "").strip()
    team = request.form.get("team_pool") == "1" and quantity in {5, 10, 20}
    if is_gift and not recipient:
        errors.append("Add the recipient's name.")
    if recipient_email and ("@" not in recipient_email or "." not in recipient_email.split("@")[-1]):
        errors.append("That recipient email does not look right.")
    if errors:
        return _render_campaign(page, form=form, errors=errors, open_sheet=True), 400

    subtotal_cents, fee_cents, total_cents = combo_charge(quantity)
    amount = subtotal_cents / 100.0
    processing_fee = fee_cents / 100.0
    payment_method = (request.form.get("stripe_payment_method") or "").strip()
    intent_id = None
    token = "simulated"
    description = f"Green Truck Office Combo x{quantity} - {page.company_name}"
    metadata = {
        "product_id": combo_product_id(),
        "price_id": combo_price_id(),
        "quantity": quantity,
        "campaign_slug": page.slug,
        "event_id": event.id,
        "subtotal": f"{amount:.2f}",
        "fee": f"{processing_fee:.2f}",
        "fee_rate": f"{campaign_fee_rate():.3f}",
    }
    if app.config.get("PAYMENTS_MODE") == "stripe":
        if not payment_method:
            return _render_campaign(page, form=form, errors=["Add a card."], open_sheet=True), 400
        try:
            intent_id, intent_status = authorize_card(
                amount + processing_fee,
                email,
                description,
                payment_method,
                request.url_root,
                metadata=metadata,
                amount_cents=total_cents,
            )
        except Exception:
            logging.exception("Could not authorize pledge for %s", page.slug)
            return _render_campaign(page, form=form, errors=["The card could not be authorized."], open_sheet=True), 400
        if not intent_id:
            return _render_campaign(page, form=form, errors=["The card could not be authorized."], open_sheet=True), 400
        logging.info("Campaign %s authorized %s status %s", page.slug, intent_id, intent_status)
        if intent_status not in {"requires_capture", "succeeded"}:
            return _render_campaign(page, form=form, errors=["The card could not be authorized."], open_sheet=True), 400
        token = payment_method
    elif app.config.get("PAYMENTS_MODE") != "simulate":
        return _render_campaign(page, form=form, errors=["Payments are not configured."], open_sheet=True), 400
    else:
        intent_id = f"sim_{uuid.uuid4().hex}"

    referred_by = ""
    refs = session.get("campaign_refs") or {}
    prior_code = refs.get(page.slug) if isinstance(refs, dict) else ""
    prior = _find_by_code(event.id, prior_code)
    if prior and prior.email.lower() != email.lower():
        referred_by = prior_code
    referral_code = secrets.token_hex(4)
    pledge = Pledge(
        email=email[:120],
        amount=amount,
        processing_fee=processing_fee,
        stripe_token=token,
        stripe_payment_intent_id=intent_id,
        event_id=event.id,
        status="pending",
        is_gift=is_gift,
        recipient_name=recipient[:120] if is_gift else None,
        recipient_email=recipient_email[:120] if is_gift and recipient_email else None,
        ticket_code=generate_ticket_code() if is_gift else None,
    )
    pledge.set_selected_menu_items([{
        "name": form["entree"] or "Combo",
        "description": combo_description(),
        "price": combo_price(),
        "quantity": quantity,
        "supporter": form["supporter_name"][:120],
        "entree": form["entree"],
        "team": team,
        "referral_code": referral_code,
        "referred_by": referred_by,
    }])
    db.session.add(pledge)
    db.session.commit()
    _settle(page, event, pledge)
    return redirect(url_for("campaign_page", slug=slug, thanks=referral_code))


@app.route("/c/<slug>/book", methods=["POST"])
def campaign_book(slug):
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page or not page.event:
        abort(404)
    if not _is_host(page):
        abort(403)
    chosen = (request.form.get("event_date") or "").strip()
    allowed = set(_office_dates(page))
    if chosen not in allowed or not page.event.is_goal_met():
        return _render_campaign(page, errors=["Pick one of the open days."], open_sheet=True), 400
    event = page.event
    event.date = datetime.strptime(chosen, "%Y-%m-%d").replace(hour=11)
    event.status = "approved"
    event.approved_at = datetime.utcnow()
    event.organizer_entree_claimed = True
    page.booked_date = chosen
    _capture_pending(page, event)
    recipient = (page.contact_email or event.organizer.email or "")[:120]
    subject = f"Your meal is on us — {page.company_name}"
    body = (
        f"{page.company_name} is booked for {format_date(chosen)}. "
        "Your meal is on us.\n"
        f"{url_for('campaign_page', slug=page.slug, _external=True)}"
    )
    sent = False
    if recipient and not app.config.get("MAIL_SUPPRESS_SEND"):
        sent = bool(send_email(recipient, subject, body))
    else:
        logging.info("Booking email logged, not sent, for %s", page.slug)
    _log_campaign_email(recipient, subject, body, sent)
    db.session.commit()
    return redirect(url_for("campaign_page", slug=slug))


@app.route("/c/<slug>/test-payments")
def campaign_test_payments(slug):
    """Stripe status for the fictional end-to-end slugs only."""
    page = _e2e_page(slug)
    if not page or not page.event:
        abort(404)
    import stripe
    rows = []
    for pledge in Pledge.query.filter_by(event_id=page.event_id).all():
        intent_id = pledge.stripe_payment_intent_id or ""
        stripe_status = None
        if intent_id and not intent_id.startswith("sim_") and stripe.api_key:
            try:
                stripe_status = stripe.PaymentIntent.retrieve(intent_id).status
            except Exception as exc:
                stripe_status = f"error:{exc.__class__.__name__}"
        rows.append({
            "id": intent_id,
            "pledge_status": pledge.status,
            "stripe_status": stripe_status,
            "amount": pledge.amount,
        })
    event = page.event
    return {
        "slug": slug,
        "event_status": event.status,
        "goal": event.pledge_goal,
        "raised": event.current_pledges,
        "payments": rows,
    }


@app.route("/c/<slug>/test-release", methods=["POST"])
def campaign_test_release(slug):
    """Cancel leftover test-card holds on the fictional miss slug."""
    page = _e2e_page(slug)
    if not page or not page.event:
        abort(404)
    event = page.event
    release_and_notify_pledgers(event)
    event.status = "cancelled"
    db.session.commit()
    logging.info("Released test holds for %s", slug)
    return campaign_test_payments(slug)


@app.route("/campaigns/sweep", methods=["GET", "POST"])
def campaign_sweep():
    """Release holds on campaigns whose window has closed.

    Page views and the admin list already run this. A Render cron should
    also call it, because the free plan sleeps and card holds expire.
    """
    expected = (os.environ.get("CAMPAIGN_SWEEP_TOKEN") or "").strip()
    supplied = (request.args.get("token") or request.headers.get("X-Sweep-Token") or "").strip()
    if not session.get("admin_id") and not (expected and supplied == expected):
        abort(403)
    closed = sweep_campaign_deadlines()
    return {"closed": closed}


@app.route("/c/<slug>/quote", methods=["POST"])
def campaign_quote(slug):
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page:
        abort(404)
    if (request.form.get("company_website") or "").strip():
        return redirect(url_for("campaign_page", slug=slug, requested=1))

    form = {
        "organizer_name": (request.form.get("organizer_name") or "").strip(),
        "organizer_email": (request.form.get("organizer_email") or "").strip(),
        "service_format": (request.form.get("service_format") or "classic").strip(),
        "event_date": (request.form.get("event_date") or "").strip(),
        "headcount": (request.form.get("headcount") or "").strip(),
        "location": (request.form.get("location") or "").strip(),
        "notes": (request.form.get("notes") or "").strip(),
        "give_back": request.form.get("give_back") == "on",
        "cause": (request.form.get("cause") or "").strip(),
        "give_back_percent": (request.form.get("give_back_percent") or "").strip(),
        "preorder": request.form.get("preorder") == "on",
    }
    errors = []
    if not form["organizer_name"]:
        errors.append("Add your name.")
    if "@" not in form["organizer_email"] or "." not in form["organizer_email"].split("@")[-1]:
        errors.append("Add a real email so Kam can reply.")
    if form["service_format"] not in {"truck", "dropoff", "classic"}:
        form["service_format"] = "classic"
    if not form["event_date"]:
        errors.append("Pick a date, or type one in.")
    try:
        headcount = int(form["headcount"])
        if headcount < 1 or headcount > 5000:
            raise ValueError
    except ValueError:
        headcount = None
        errors.append("Add a headcount.")
    percent = None
    if form["give_back"]:
        try:
            percent = int(form["give_back_percent"] or "10")
            if percent < 1 or percent > 100:
                raise ValueError
        except ValueError:
            errors.append("Give-back percent should be between 1 and 100.")

    if errors:
        return _render_campaign(page, form=form, errors=errors, open_sheet=True), 400

    quote = QuoteRequest(
        campaign_id=page.id,
        organizer_name=form["organizer_name"][:120],
        organizer_email=form["organizer_email"][:200],
        service_format=form["service_format"],
        event_date=form["event_date"][:40],
        headcount=headcount,
        location=(form["location"] or "Not specified")[:240],
        notes=form["notes"][:2000],
        give_back=form["give_back"],
        cause=(form["cause"] or page.give_back_cause or "")[:200] if form["give_back"] else "",
        give_back_percent=percent if form["give_back"] else None,
        preorder_requested=bool(form["give_back"] and form["preorder"]),
        email_notified=False,
    )
    db.session.add(quote)
    db.session.commit()
    try:
        quote.email_notified = _send_quote_email(page, quote)
        db.session.commit()
    except Exception:
        logging.exception("Campaign notification failed for %s", page.slug)
        db.session.rollback()
    first_name = (form["organizer_name"].split() or [""])[0][:40]
    recap_line = " · ".join(
        bit for bit in (format_date(form["event_date"]), f"{headcount} people") if bit
    )
    recaps = session.get("campaign_quote_recaps") or {}
    recaps[slug] = {"first_name": first_name, "line": recap_line}
    session["campaign_quote_recaps"] = recaps
    session.modified = True
    logging.info("Campaign quote saved for %s", page.slug)
    return redirect(url_for("campaign_page", slug=slug, requested=1))


@app.route("/campaign-photos/<filename>")
def campaign_photo_file(filename):
    if not re.fullmatch(r"[a-z0-9-]+(?:-800)?\.jpg", filename or ""):
        abort(404)
    directory = override_photo_dir()
    path = os.path.join(directory, filename)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(directory, filename, max_age=86400)


@app.route("/admin/campaigns")
def admin_campaigns():
    blocked = _require_admin()
    if blocked:
        return blocked
    sweep_campaign_deadlines()
    pages = CampaignPage.query.order_by(CampaignPage.created_at.desc()).all()
    views, unique, requests = _campaign_counts()
    offices = {page.id: office_snapshot(page) for page in pages}
    slots = photo_list()
    filled = sum(1 for slot in slots if not slot["placeholder"])
    return render_template(
        "admin/campaigns.html",
        pages=pages,
        views=views,
        unique=unique,
        requests=requests,
        photo_slots=slots,
        photos_filled=filled,
        photos_total=len(slots),
        csv_fields=CSV_FIELDS,
        offices=offices,
    )


@app.route("/admin/campaigns/sample.csv")
def admin_campaign_sample_csv():
    blocked = _require_admin()
    if blocked:
        return blocked
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerow({
        "company": "Northwind Labs",
        "contact_name": "Avery Chen",
        "contact_email": "avery@northwind.example",
        "personal_note": "A short note from Kam. This row is fake sample data.",
        "logo_url": "",
        "suggested_dates": "2026-12-04|2026-12-09|2026-12-11",
        "give_back_cause": "a local school garden",
        "slug": "northwind-labs",
    })
    return app.response_class(buffer.getvalue(), mimetype="text/csv")


@app.route("/admin/campaigns/import", methods=["POST"])
def admin_campaign_import():
    blocked = _require_admin()
    if blocked:
        return blocked
    upload = request.files.get("csv_file")
    if not upload or not upload.filename:
        flash("Choose a CSV file.", "error")
        return redirect(url_for("admin_campaigns"))
    raw = upload.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        flash("That CSV is larger than 2MB.", "error")
        return redirect(url_for("admin_campaigns"))
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("Save the CSV as UTF-8 and try again.", "error")
        return redirect(url_for("admin_campaigns"))
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "company" not in {(name or "").strip().lower() for name in reader.fieldnames}:
        flash("The CSV needs a company column.", "error")
        return redirect(url_for("admin_campaigns"))
    created = 0
    errors = []
    for index, original in enumerate(reader, start=2):
        if index > 501:
            errors.append("Stopped after 500 rows.")
            break
        row = {(key or "").strip().lower(): (value or "").strip() for key, value in original.items()}
        page, error = upsert_campaign_row(row)
        if error:
            errors.append(f"Row {index}: {error}")
            continue
        if page is not None:
            created += 1
    db.session.commit()
    flash(f"Saved {created} campaign page{'s' if created != 1 else ''}.", "success")
    for error in errors[:8]:
        flash(error, "error")
    return redirect(url_for("admin_campaigns"))


@app.route("/admin/campaigns/<int:campaign_id>")
def admin_campaign_detail(campaign_id):
    blocked = _require_admin()
    if blocked:
        return blocked
    page = CampaignPage.query.get_or_404(campaign_id)
    sweep_campaign_deadlines(page)
    quotes = QuoteRequest.query.filter_by(campaign_id=page.id).order_by(QuoteRequest.created_at.desc()).all()
    recent_views = (
        CampaignView.query.filter_by(campaign_id=page.id)
        .order_by(CampaignView.viewed_at.desc())
        .limit(25)
        .all()
    )
    unique = (
        db.session.query(func.count(func.distinct(CampaignView.visitor_hash)))
        .filter(CampaignView.campaign_id == page.id)
        .scalar()
        or 0
    )
    pledges = []
    if page.event_id:
        pledges = Pledge.query.filter_by(event_id=page.event_id).order_by(Pledge.created_at.desc()).all()
    goal_mail = []
    if page.contact_email:
        goal_mail = (
            EmailLog.query.filter_by(recipient=page.contact_email[:120])
            .order_by(EmailLog.created_at.desc())
            .limit(8)
            .all()
        )
    return render_template(
        "admin/campaign_detail.html",
        page=page,
        quotes=quotes,
        pledges=pledges,
        goal_mail=goal_mail,
        office=office_snapshot(page),
        recent_views=recent_views,
        view_count=CampaignView.query.filter_by(campaign_id=page.id).count(),
        unique_count=unique,
        date_choices=_office_dates(page),
    )


@app.route("/admin/campaigns/<int:campaign_id>/dates", methods=["POST"])
def admin_campaign_dates(campaign_id):
    blocked = _require_admin()
    if blocked:
        return blocked
    page = CampaignPage.query.get_or_404(campaign_id)
    raw = request.form.get("available_dates") or ""
    chosen = []
    for line in raw.splitlines():
        item = line.strip()
        if not item:
            continue
        try:
            chosen.append(datetime.strptime(item, "%Y-%m-%d").date().isoformat())
        except ValueError:
            flash(f"Skipped {item}. Dates look like 2026-12-04.", "error")
    page.set_available_dates(chosen)
    db.session.commit()
    flash("Available dates saved." if chosen else "Cleared the date list. The weekday defaults apply.", "success")
    return redirect(url_for("admin_campaign_detail", campaign_id=page.id))


@app.route("/admin/campaigns/photos", methods=["POST"])
def admin_campaign_photo_upload():
    blocked = _require_admin()
    if blocked:
        return blocked
    slot_id = (request.form.get("slot") or "").strip()
    known = {item["id"] for item in photo_list()}
    if slot_id not in known:
        flash("Choose a photo slot from the list.", "error")
        return redirect(url_for("admin_campaigns"))
    upload = request.files.get("photo")
    if not upload or not upload.filename:
        flash("Choose an image.", "error")
        return redirect(url_for("admin_campaigns"))
    data = upload.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        flash("Images need to be 8MB or smaller.", "error")
        return redirect(url_for("admin_campaigns"))
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(data))
        image = image.convert("RGB")
    except Exception:
        flash("That file is not a JPEG, PNG, or WebP.", "error")
        return redirect(url_for("admin_campaigns"))
    directory = override_photo_dir()
    os.makedirs(directory, exist_ok=True)
    large = image.copy()
    large.thumbnail((1600, 1600))
    small = image.copy()
    small.thumbnail((800, 800))
    large_name = f"{slot_id}.jpg"
    small_name = f"{slot_id}-800.jpg"
    large.save(os.path.join(directory, large_name), "JPEG", quality=82, optimize=True)
    small.save(os.path.join(directory, small_name), "JPEG", quality=82, optimize=True)
    override_path = os.path.join(directory, "overrides.json")
    overrides = {}
    if os.path.exists(override_path):
        try:
            with open(override_path, "r", encoding="utf-8") as handle:
                overrides = json.load(handle)
        except (OSError, ValueError):
            overrides = {}
    overrides[slot_id] = large_name
    with open(override_path, "w", encoding="utf-8") as handle:
        json.dump(overrides, handle)
    flash(f"Photograph saved in the {slot_id} frame. It is stored on the server, not in git.", "success")
    return redirect(url_for("admin_campaigns"))


try:
    ensure_campaign_columns()
except Exception:
    db.session.rollback()
    logging.exception("Could not add campaign sponsor columns")
