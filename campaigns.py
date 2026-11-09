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
import os
import re
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from sqlalchemy import func
from app import app, db
from models import CampaignPage, CampaignView, QuoteRequest
from utils import send_email

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
]

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
    format_label = "Truck in the lot" if quote.service_format == "truck" else "Drop-off catering"
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
    return page, None


def _campaign_counts():
    views = dict(db.session.query(CampaignView.campaign_id, func.count(CampaignView.id)).group_by(CampaignView.campaign_id))
    unique = dict(
        db.session.query(CampaignView.campaign_id, func.count(func.distinct(CampaignView.visitor_hash)))
        .group_by(CampaignView.campaign_id)
    )
    requests = dict(db.session.query(QuoteRequest.campaign_id, func.count(QuoteRequest.id)).group_by(QuoteRequest.campaign_id))
    return views, unique, requests


@app.route("/c/<slug>")
def campaign_page(slug):
    page = CampaignPage.query.filter_by(slug=slug).first()
    if not page:
        abort(404)
    _record_view(page)
    saved = request.args.get("requested") == "1"
    return render_template(
        "campaigns/page.html",
        page=page,
        photos=photo_library(),
        possessive_name=possessive(page.company_name),
        date_choices=[(item, format_date(item)) for item in page.get_suggested_dates()],
        saved=saved,
        form={},
        errors=[],
    )


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
        "service_format": (request.form.get("service_format") or "").strip(),
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
    if form["service_format"] not in {"truck", "dropoff"}:
        errors.append("Choose the truck in your lot, or a drop-off.")
    if not form["event_date"]:
        errors.append("Pick a date, or type one in.")
    try:
        headcount = int(form["headcount"])
        if headcount < 1 or headcount > 5000:
            raise ValueError
    except ValueError:
        headcount = None
        errors.append("Add a headcount.")
    if not form["location"]:
        errors.append("Where should the truck park, or the food land?")
    percent = None
    if form["give_back"]:
        try:
            percent = int(form["give_back_percent"] or "10")
            if percent < 1 or percent > 100:
                raise ValueError
        except ValueError:
            errors.append("Give-back percent should be between 1 and 100.")

    if errors:
        return render_template(
            "campaigns/page.html",
            page=page,
            photos=photo_library(),
            possessive_name=possessive(page.company_name),
            date_choices=[(item, format_date(item)) for item in page.get_suggested_dates()],
            saved=False,
            form=form,
            errors=errors,
        ), 400

    quote = QuoteRequest(
        campaign_id=page.id,
        organizer_name=form["organizer_name"][:120],
        organizer_email=form["organizer_email"][:200],
        service_format=form["service_format"],
        event_date=form["event_date"][:40],
        headcount=headcount,
        location=form["location"][:240],
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
    pages = CampaignPage.query.order_by(CampaignPage.created_at.desc()).all()
    views, unique, requests = _campaign_counts()
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
    return render_template(
        "admin/campaign_detail.html",
        page=page,
        quotes=quotes,
        recent_views=recent_views,
        view_count=CampaignView.query.filter_by(campaign_id=page.id).count(),
        unique_count=unique,
    )


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
