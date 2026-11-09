import logging
import os
import re

import stripe
from dotenv import load_dotenv
from flask import Flask, abort, render_template, request
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()


def _env_flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _app_env():
    value = (os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development").strip().lower()
    if value == "dev":
        return "development"
    return value


def _normalize_database_url(url):
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _database_target(url):
    """Return a log-safe description of the database. Never include credentials."""
    if url.startswith("sqlite"):
        return "sqlite"
    without_scheme = url.split("://", 1)[-1]
    if "@" in without_scheme:
        host = without_scheme.split("@", 1)[1].split("/", 1)[0]
        return f"postgresql host {host}"
    return "postgresql"


class Base(DeclarativeBase):
    pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()],
)

db = SQLAlchemy(model_class=Base)
mail = Mail()
app = Flask(__name__)

APP_ENV = _app_env()
IS_PRODUCTION = APP_ENV == "production"
IS_TESTING = APP_ENV == "testing"
app.config["APP_ENV"] = APP_ENV

session_secret = os.environ.get("SESSION_SECRET")
if IS_PRODUCTION and not session_secret:
    raise ValueError("SESSION_SECRET is required when APP_ENV=production")
if not session_secret:
    session_secret = "dev-insecure-change-me"
    logging.warning(
        "SESSION_SECRET is not set. Using an insecure development key. "
        "Set SESSION_SECRET before sharing this process with anyone else."
    )
app.secret_key = session_secret

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

iframe_embed = _env_flag("IFRAME_EMBED", False)
secure_cookies = _env_flag("SESSION_COOKIE_SECURE", IS_PRODUCTION or iframe_embed)
samesite = "None" if iframe_embed else os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
if iframe_embed:
    secure_cookies = True

app.config.update(
    SESSION_COOKIE_SECURE=secure_cookies,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=samesite,
    SESSION_COOKIE_DOMAIN=None,
    SESSION_COOKIE_PATH="/",
    PERMANENT_SESSION_LIFETIME=3600,
    PREFERRED_URL_SCHEME="https" if IS_PRODUCTION else "http",
)

database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url:
    database_url = _normalize_database_url(database_url)
elif IS_PRODUCTION:
    raise ValueError("DATABASE_URL is required when APP_ENV=production")
else:
    os.makedirs(app.instance_path, exist_ok=True)
    database_url = "sqlite:///" + os.path.join(app.instance_path, "app.db")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
logging.info("Database configured (%s): %s", APP_ENV, _database_target(database_url))

if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine_options = {"connect_args": connect_args}
    if database_url.endswith(":memory:") or database_url.rsplit("/", 1)[-1] == ":memory:":
        engine_options["poolclass"] = StaticPool
else:
    engine_options = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "pool_timeout": 10,
        "connect_args": {
            "connect_timeout": 10,
            "application_name": "food_truck_fundraiser",
            "options": "-c statement_timeout=30000",
        },
    }
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

mail_username = os.environ.get("MAIL_USERNAME") or os.environ.get("EMAIL_USERNAME") or ""
mail_password = (
    os.environ.get("MAIL_PASSWORD")
    or os.environ.get("EMAIL_PASSWORD")
    or os.environ.get("EMAIL_PASSWORD_NEW")
    or ""
)
mail_sender = os.environ.get("MAIL_DEFAULT_SENDER") or mail_username or "noreply@localhost"
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "localhost")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = _env_flag("MAIL_USE_TLS", True)
app.config["MAIL_USE_SSL"] = _env_flag("MAIL_USE_SSL", False)
app.config["MAIL_USERNAME"] = mail_username or None
app.config["MAIL_PASSWORD"] = mail_password or None
app.config["MAIL_DEFAULT_SENDER"] = mail_sender
app.config["MAIL_SUPPRESS_SEND"] = _env_flag(
    "MAIL_SUPPRESS_SEND",
    IS_TESTING or not (mail_username and mail_password),
)
if app.config["MAIL_SUPPRESS_SEND"]:
    logging.info("Email sending is suppressed (set MAIL_USERNAME and MAIL_PASSWORD to send mail)")
else:
    logging.info("Email configured via %s", app.config["MAIL_SERVER"])


def configure_payments():
    """Select Stripe test mode, live mode, or a local simulation.

    Test mode is the default. Live charges require STRIPE_TEST_MODE=false and live keys.
    Outside production, missing keys keep the app usable with a clearly labeled simulation.
    """
    secret = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    publishable = (os.environ.get("STRIPE_PUBLISHABLE_KEY") or "").strip()
    live_secret = (os.environ.get("STRIPE_SECRET_KEY_LIVE") or "").strip()
    live_publishable = (os.environ.get("STRIPE_PUBLISHABLE_KEY_LIVE") or "").strip()
    test_mode = _env_flag("STRIPE_TEST_MODE", True)

    app.config["STRIPE_PUBLISHABLE_KEY"] = None
    app.config["STRIPE_MODE"] = "unconfigured"
    app.config["PAYMENTS_MODE"] = "disabled"
    stripe.api_key = None

    if test_mode:
        if secret.startswith("sk_test_") and publishable.startswith("pk_test_"):
            stripe.api_key = secret
            app.config["STRIPE_PUBLISHABLE_KEY"] = publishable
            app.config["STRIPE_MODE"] = "test"
            app.config["PAYMENTS_MODE"] = "stripe"
            logging.info("Stripe test mode enabled")
            return
        live_key_present = secret.startswith("sk_live_") or live_secret.startswith("sk_live_")
        if live_key_present:
            message = (
                "STRIPE_TEST_MODE is on, but a live secret key is configured. "
                "Refusing to charge real cards. Set STRIPE_TEST_MODE=false only when you intend to take live payments."
            )
            if IS_PRODUCTION:
                raise ValueError(message)
            logging.error(message)
            return
        message = (
            "Stripe test keys are not set. Provide STRIPE_SECRET_KEY (sk_test_...) and "
            "STRIPE_PUBLISHABLE_KEY (pk_test_...)."
        )
        if IS_PRODUCTION:
            raise ValueError(message + " Both are required when APP_ENV=production.")
        logging.warning(message + " Local payment simulation is enabled.")
        app.config["PAYMENTS_MODE"] = "simulate"
        return

    if secret.startswith("sk_live_") and publishable.startswith("pk_live_"):
        chosen_secret, chosen_pub = secret, publishable
    elif live_secret.startswith("sk_live_") and live_publishable.startswith("pk_live_"):
        chosen_secret, chosen_pub = live_secret, live_publishable
    else:
        raise ValueError(
            "STRIPE_TEST_MODE=false requires live keys in STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY, "
            "or in STRIPE_SECRET_KEY_LIVE and STRIPE_PUBLISHABLE_KEY_LIVE."
        )
    stripe.api_key = chosen_secret
    app.config["STRIPE_PUBLISHABLE_KEY"] = chosen_pub
    app.config["STRIPE_MODE"] = "live"
    app.config["PAYMENTS_MODE"] = "stripe"
    logging.warning("Stripe live mode enabled. Real charges will be processed.")


configure_payments()

db.init_app(app)
mail.init_app(app)

_MAINTENANCE_ROUTES = re.compile(
    r"/(?:force-template-refresh-xyz123|sync-data-xyz123|fix-menu-items-xyz123|"
    r"database-sync-admin-xyz456|clear-cache-and-refresh-xyz789|fix-database-integrity-xyz999|"
    r"database-sync-xyz456|production-setup-abc999|auto-fix-all-menus-xyz123|"
    r"admin/fix-organizer-pledges-xyz789|admin/update-pledge-totals-xyz456|"
    r"login-admin-direct-xyz123|fix-duplicate-events-abc123|fix-phantom-pledges-xyz789|"
    r"remove-organizer-pledges-abc123|admin/create-missing-payouts-xyz456|"
    r"setup-admin-secret-xyz123|debug-admin-login|quick-admin-login|quick-organizer-login|"
    r"test-credentials|iframe-debug)(?:/|$)"
)

_IFRAME_ORIGINS = {
    "https://www.thefoodtruckstop.com",
    "https://thefoodtruckstop.com",
}


@app.before_request
def block_legacy_maintenance_routes():
    """Old Replit repair URLs created accounts and bypassed auth. They stay disabled."""
    if _MAINTENANCE_ROUTES.search(request.path):
        abort(404)


@app.after_request
def after_request(response):
    if iframe_embed:
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors 'self' https://www.thefoodtruckstop.com "
            "https://thefoodtruckstop.com *.squarespace.com *.sqsp.com *.squarespace-cdn.com"
        )
        origin = request.headers.get("Origin")
        if origin in _IFRAME_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    else:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@app.errorhandler(404)
def not_found_error(error):
    logging.warning("404 error: %s", request.url)
    try:
        return render_template("404.html"), 404
    except Exception:
        return "<h1>Page Not Found</h1><p>The requested page could not be found.</p>", 404


@app.errorhandler(500)
def internal_error(error):
    try:
        db.session.rollback()
    except Exception:
        pass
    logging.error("500 error: %s", error, exc_info=True)
    try:
        return render_template("500.html"), 500
    except Exception:
        return "<h1>Internal Server Error</h1><p>An internal error has occurred.</p>", 500


@app.errorhandler(Exception)
def handle_exception(e):
    logging.error("Unhandled exception: %s", e, exc_info=True)
    if hasattr(e, "code"):
        return e
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        return render_template("500.html"), 500
    except Exception:
        return "<h1>Internal Server Error</h1><p>An unexpected error has occurred.</p>", 500


def _seed_admin():
    from models import Admin
    from werkzeug.security import generate_password_hash

    admin_email = (os.environ.get("ADMIN_EMAIL") or "").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD") or ""
    if not admin_email or not admin_password:
        logging.info("ADMIN_EMAIL or ADMIN_PASSWORD is unset; no admin account was created")
        return
    admin = Admin.query.filter_by(username=admin_email).first()
    if admin:
        return
    admin = Admin(username=admin_email, password_hash=generate_password_hash(admin_password))
    db.session.add(admin)
    db.session.commit()
    logging.info("Admin account created for %s", admin_email)


def _seed_demo_content():
    """Optional local sample truck, organizer, and event. Never runs in production."""
    if not _env_flag("SEED_DEMO_DATA"):
        return
    if IS_PRODUCTION:
        logging.warning("SEED_DEMO_DATA is ignored when APP_ENV=production")
        return

    from datetime import datetime, timedelta

    from models import Event, FoodTruck, FoodTruckOwner, Organizer
    from werkzeug.security import generate_password_hash

    owner_email = (os.environ.get("DEMO_OWNER_EMAIL") or "owner@example.com").strip()
    owner_password = os.environ.get("DEMO_OWNER_PASSWORD") or ""
    organizer_email = (os.environ.get("DEMO_ORGANIZER_EMAIL") or "organizer@example.com").strip()
    organizer_password = os.environ.get("DEMO_ORGANIZER_PASSWORD") or ""
    if not owner_password or not organizer_password:
        logging.warning(
            "SEED_DEMO_DATA is set but DEMO_OWNER_PASSWORD or DEMO_ORGANIZER_PASSWORD is missing; skipping demo data"
        )
        return

    owner = FoodTruckOwner.query.filter_by(email=owner_email).first()
    if not owner:
        owner = FoodTruckOwner(
            email=owner_email,
            name="Demo Truck Owner",
            phone="310-555-0100",
            business_name="Green Truck",
            business_license="DEMO-LICENSE",
            password_hash=generate_password_hash(owner_password),
            status="approved",
        )
        db.session.add(owner)
        db.session.flush()

    truck = FoodTruck.query.filter_by(owner_id=owner.id).first()
    if not truck:
        truck = FoodTruck(
            name="Green Truck",
            description="Sample organic food truck used for local development.",
            owner_id=owner.id,
            cuisine_type="Organic",
            contact_email=owner_email,
            contact_phone=owner.phone,
            sales_goal=500.0,
            status="approved",
            registration_fee_charged=True,
            approved_at=datetime.utcnow(),
        )
        truck.set_menu_items([
            {"name": "Carnitas Taco", "price": 4.5, "description": "Organic carnitas, onion, cilantro"},
            {"name": "Veggie Bowl", "price": 11.0, "description": "Seasonal vegetables and grains"},
        ])
        db.session.add(truck)
        db.session.flush()

    organizer = Organizer.query.filter_by(email=organizer_email).first()
    if not organizer:
        organizer = Organizer(
            email=organizer_email,
            name="Demo Organizer",
            password_hash=generate_password_hash(organizer_password),
        )
        db.session.add(organizer)
        db.session.flush()

    if Event.query.count() == 0:
        event = Event(
            name="Sample Community Lunch",
            description="Local sample fundraiser so you can browse events and try a pledge.",
            date=datetime.utcnow() + timedelta(days=30),
            location="Culver City, CA",
            organizer_id=organizer.id,
            food_truck_id=truck.id,
            markup_percentage=15.0,
            pledge_goal=truck.sales_goal or 500.0,
            status="pending",
            organizer_fee_charged=True,
        )
        selected_items = []
        for item in truck.get_menu_items():
            price = float(item.get("price") or 0)
            selected_items.append({
                **item,
                "original_price": price,
                "marked_up_price": round(price * (1 + (event.markup_percentage or 0) / 100), 2),
            })
        event.set_selected_menu_items(selected_items)
        db.session.add(event)

    db.session.commit()
    logging.info("Demo owner, organizer, truck, and sample event are ready")


def _maybe_restore_events():
    if not _env_flag("RESTORE_EVENT_BACKUP"):
        return
    from datetime import datetime

    from backup_system import restore_events_from_file
    from models import Event

    if Event.query.count() > 0:
        return
    restored_events = restore_events_from_file()
    if not restored_events:
        logging.info("RESTORE_EVENT_BACKUP is set, but no backup file was found")
        return
    restored_count = 0
    for event_data in restored_events:
        event = Event()
        for key, value in event_data.items():
            if key == "id" or not hasattr(event, key):
                continue
            if key in {"date", "created_at", "approved_at"} and isinstance(value, str) and value:
                setattr(event, key, datetime.fromisoformat(value.replace("Z", "+00:00")))
            else:
                setattr(event, key, value)
        db.session.add(event)
        restored_count += 1
    db.session.commit()
    logging.info("Restored %s events from the JSON backup", restored_count)


with app.app_context():
    from translations import get_language_from_request, get_text

    app.jinja_env.globals.update(
        get_text=get_text,
        get_language_from_request=get_language_from_request,
    )

    import models  # noqa: F401
    import routes  # noqa: F401
    import campaigns  # noqa: F401

    try:
        db.session.execute(db.text("SELECT 1"))
        logging.info("Database connection successful")
    except Exception as exc:
        db.session.rollback()
        logging.error("Database connection failed: %s", exc)
        raise

    try:
        db.create_all()
        logging.info("Database tables created or verified")
        _maybe_restore_events()
        _seed_demo_content()
        _seed_admin()
        from campaigns import seed_demo_campaigns
        seed_demo_campaigns()
        logging.info("Application initialization completed")
    except Exception:
        db.session.rollback()
        logging.error("Application initialization failed", exc_info=True)
        raise
