import os
import logging
import stripe
from flask import Flask, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from translations import get_text, get_language_from_request

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
mail = Mail()

# Create the app
app = Flask(__name__)

# Enforce SESSION_SECRET in production - critical security requirement
session_secret = os.environ.get("SESSION_SECRET")
database_url = os.environ.get("DATABASE_URL")

# Detect production environment based on database URL
is_production = database_url and "ep-young-bush-adblwffc.c-2.us-east-1.aws.neon.tech" in database_url

if is_production and not session_secret:
    logging.error("🚨 CRITICAL SECURITY ERROR: SESSION_SECRET environment variable is required in production")
    logging.error("🚨 Application startup FAILED due to missing session secret")
    raise ValueError("SESSION_SECRET environment variable is required in production")
elif not session_secret:
    # Development fallback
    logging.warning("⚠️  Using development session secret - not suitable for production")
    app.secret_key = "dev-secret-key-change-in-production"
else:
    app.secret_key = session_secret
    if is_production:
        logging.info("✅ Production session secret configured")
    else:
        logging.info("✅ Development session secret configured")

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure session cookies for production security
app.config.update(
    SESSION_COOKIE_SECURE=True,      # Require HTTPS
    SESSION_COOKIE_HTTPONLY=True,    # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE='Lax',   # CSRF protection while maintaining functionality
    SESSION_COOKIE_DOMAIN=None,      # Don't restrict domain
    SESSION_COOKIE_PATH='/',         # Available on all paths
    PERMANENT_SESSION_LIFETIME=3600  # 1 hour for production security
)

# Configure the database with proper environment separation
database_url = os.environ.get("DATABASE_URL")

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    # Determine if this is production or development based on database URL
    if "ep-young-bush-adblwffc.c-2.us-east-1.aws.neon.tech" in database_url:
        logging.info("Database configured (PRODUCTION): ep-young-bush-adblwffc.c-2.us-east-1.aws.neon.tech")
    else:
        logging.info(f"Database configured (DEVELOPMENT): {database_url.split('@')[1].split('/')[0] if '@' in database_url else 'local'}")
else:
    # Fallback for local development
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
    logging.info("Database configured (LOCAL): SQLite fallback")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "pool_timeout": 10,  # Add connection timeout
    "connect_args": {
        "connect_timeout": 10,  # PostgreSQL connection timeout
        "application_name": "food_truck_app",
        "options": "-c statement_timeout=30000"  # 30 second statement timeout (proper format)
    }
}

# Configure Flask-Mail for Network Solutions (2024 updated settings)
# Try multiple server configurations for maximum compatibility
# First try the updated 2024 server
app.config['MAIL_SERVER'] = 'netsol-smtp-oxcs.hostingplatform.com'
app.config['MAIL_PORT'] = 587  # Back to TLS port
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USERNAME', 'support@foodtruckfundraiser.com')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD_NEW', 'your-email-password')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_USERNAME', 'support@foodtruckfundraiser.com')

# Configure Stripe - Smart mode switching with flexible key detection
# Check for available keys first
secret_key = os.environ.get('STRIPE_SECRET_KEY')
publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY')
live_secret_key = os.environ.get('STRIPE_SECRET_KEY_LIVE')
live_publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY_LIVE')

# Determine if we have live keys available
has_live_keys = (secret_key and secret_key.startswith('sk_live_')) or (live_secret_key and live_secret_key.startswith('sk_live_'))
has_test_keys = (secret_key and secret_key.startswith('sk_test_'))

# Check test mode preference but override if we only have live keys
STRIPE_TEST_MODE = os.environ.get('STRIPE_TEST_MODE', 'false').lower() == 'true'

if STRIPE_TEST_MODE and has_test_keys:
    # Test mode requested and test keys available
    stripe.api_key = secret_key
    app.config['STRIPE_PUBLISHABLE_KEY'] = publishable_key
    app.config['STRIPE_MODE'] = 'test'
    logging.info("🧪 STRIPE TEST MODE ENABLED - Using test keys (4242 cards will work)")
elif has_live_keys:
    # Live mode - use live keys (prefer standard names, fallback to _LIVE suffix)
    if secret_key and secret_key.startswith('sk_live_'):
        # Live keys stored under standard names
        live_secret = secret_key
        live_pub = publishable_key
    else:
        # Live keys stored under _LIVE suffix
        live_secret = live_secret_key
        live_pub = live_publishable_key
    
    if not live_secret or not live_pub:
        logging.error("❌ Live mode detected but keys incomplete")
        raise ValueError("Live Stripe keys are incomplete")
    
    stripe.api_key = live_secret
    app.config['STRIPE_PUBLISHABLE_KEY'] = live_pub
    app.config['STRIPE_MODE'] = 'live'
    logging.info("💳 STRIPE LIVE MODE ENABLED - Processing real payments")
    logging.info("🔑 Live keys configured successfully")
    logging.info("⚠️  PRODUCTION MODE: Real charges will be processed")
    
    # Verification that live key is properly set
    if not stripe.api_key.startswith('sk_live_'):
        logging.error("🚨 CRITICAL: Live key not properly set!")
        stripe.api_key = live_secret
        logging.info("🔧 Live key assignment corrected")
elif STRIPE_TEST_MODE and has_live_keys:
    # Test mode requested but only live keys available - override to live mode
    if secret_key and secret_key.startswith('sk_live_'):
        live_secret = secret_key
        live_pub = publishable_key
    else:
        live_secret = live_secret_key
        live_pub = live_publishable_key
    
    stripe.api_key = live_secret
    app.config['STRIPE_PUBLISHABLE_KEY'] = live_pub
    app.config['STRIPE_MODE'] = 'live'
    logging.warning("⚠️  STRIPE_TEST_MODE=true requested but only live keys available")
    logging.info("💳 STRIPE LIVE MODE ENABLED - Overriding test mode setting")
    logging.info("🔑 Live keys configured successfully")
    logging.warning("⚠️  PRODUCTION MODE: Real charges will be processed despite test mode request")
else:
    # Fallback to test mode if test keys available
    if secret_key and secret_key.startswith('sk_test_'):
        stripe.api_key = secret_key
        app.config['STRIPE_PUBLISHABLE_KEY'] = publishable_key
        app.config['STRIPE_MODE'] = 'test'
        logging.info("🧪 STRIPE TEST MODE (FALLBACK) - Using available test keys")
    else:
        logging.error("❌ No usable Stripe keys found")
        logging.error(f"Secret key available: {bool(secret_key)}")
        logging.error(f"Publishable key available: {bool(publishable_key)}")
        logging.error("ℹ️  Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY environment variables")
        raise ValueError("No usable Stripe keys available")

# Initialize extensions
db.init_app(app)
mail.init_app(app)

# Configure app for iframe embedding
@app.after_request
def after_request(response):
    # Allow embedding in iframes from your custom domain
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    # Minimal CSP for iframe compatibility only
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self' https://www.thefoodtruckstop.com https://thefoodtruckstop.com *.squarespace.com *.sqsp.com *.squarespace-cdn.com"
    
    # Configure ALL cookies for iframe/cross-origin use
    if 'Set-Cookie' in response.headers:
        cookies = response.headers.getlist('Set-Cookie')
        response.headers['Set-Cookie'] = []
        for cookie in cookies:
            # Ensure all cookies have the right attributes for iframe embedding
            if 'SameSite' not in cookie and 'Secure' not in cookie:
                # Add both Secure and SameSite=None for iframe compatibility
                cookie = cookie.rstrip('; ')  # Remove trailing semicolons
                cookie += '; Secure; SameSite=None'
            elif 'SameSite' not in cookie:
                cookie = cookie.rstrip('; ')
                cookie += '; SameSite=None'
            elif 'Secure' not in cookie:
                cookie = cookie.rstrip('; ')
                cookie += '; Secure'
            response.headers.add('Set-Cookie', cookie)
    
    # Add CORS headers for cross-origin requests
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Origin'] = 'https://www.thefoodtruckstop.com'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    
    return response

# Global error handlers for production
@app.errorhandler(404)
def not_found_error(error):
    logging.warning(f"404 error: {request.url}")
    try:
        return render_template('404.html'), 404
    except Exception:
        return '<h1>Page Not Found</h1><p>The requested page could not be found.</p>', 404

@app.errorhandler(500)
def internal_error(error):
    try:
        db.session.rollback()
    except Exception:
        pass
    logging.error(f"500 error: {str(error)}", exc_info=True)
    try:
        return render_template('500.html'), 500
    except Exception:
        return '<h1>Internal Server Error</h1><p>An internal error has occurred.</p>', 500

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error
    logging.error(f"Unhandled exception: {str(e)}", exc_info=True)
    
    # If it's an HTTP exception, return it
    if hasattr(e, 'code'):
        return e
    
    # Otherwise, return a generic 500 error
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        return render_template('500.html'), 500
    except Exception:
        return '<h1>Internal Server Error</h1><p>An unexpected error has occurred.</p>', 500

with app.app_context():
    try:
        # Make translation functions available in templates
        app.jinja_env.globals.update(get_text=get_text)
        app.jinja_env.globals.update(get_language_from_request=get_language_from_request)
        
        import models
        import routes
        
        # Test database connection quickly for startup
        logging.info("Testing database connection...")
        db.session.execute(db.text('SELECT 1'))
        logging.info("Database connection successful")
        
        # Quick database info (minimal queries for faster startup)
        try:
            result = db.session.execute(db.text("SELECT current_database()")).fetchone()
            db_name = result[0] if result else "unknown"
            logging.info(f"Connected to database: {db_name}")
        except Exception as e:
            logging.warning(f"Database verification failed: {str(e)}")
        
        # File-based backup system that survives deployments
        try:
            # First, create all tables
            db.create_all()
            logging.info("Database tables created/verified")
            
            # Import models and backup system
            from models import Event
            from backup_system import backup_events_to_file, restore_events_from_file
            from datetime import datetime
            
            # Check if Event table has data
            event_count = Event.query.count()
            logging.info(f"Event table has {event_count} events")
            
            if event_count == 0:
                # Try to restore from file backup
                logging.info("Event table is empty - checking for file backup...")
                
                restored_events = restore_events_from_file()
                if restored_events:
                    logging.info(f"Found file backup with {len(restored_events)} events - restoring...")
                    
                    try:
                        restored_count = 0
                        
                        for event_data in restored_events:
                            # Create new event from backup data
                            event = Event()
                            for key, value in event_data.items():
                                if key != 'id' and hasattr(event, key):
                                    if key in ['date', 'created_at', 'approved_at'] and value:
                                        # Handle datetime fields
                                        if isinstance(value, str):
                                            setattr(event, key, datetime.fromisoformat(value.replace('Z', '+00:00')))
                                        else:
                                            setattr(event, key, value)
                                    else:
                                        setattr(event, key, value)
                            
                            db.session.add(event)
                            restored_count += 1
                        
                        db.session.commit()
                        logging.info(f"✅ RESTORED {restored_count} events from file backup!")
                        
                    except Exception as restore_error:
                        logging.error(f"File restore failed: {restore_error}")
                        db.session.rollback()
                else:
                    logging.info("No file backup found - starting with empty Event table")
            
            # Always create a fresh file backup of current data
            events = Event.query.all()
            if events:
                logging.info(f"Creating file backup of {len(events)} events")
                backup_events_to_file(events)
                logging.info("✅ File backup created for future deployments")
                
        except Exception as e:
            # Fallback - still create tables
            logging.error(f"File backup system failed ({e}) - creating basic tables")
            db.create_all()
        
        # Create default admin if not exists
        from models import Admin
        from werkzeug.security import generate_password_hash
        
        admin = Admin.query.filter_by(username='support@foodtruckfundraiser.com').first()
        if not admin:
            admin = Admin()
            admin.username = 'support@foodtruckfundraiser.com'
            admin.password_hash = generate_password_hash('password')
            db.session.add(admin)
            db.session.commit()
            logging.info("Default admin created")
        
        logging.info("Application initialization completed successfully")
        
    except Exception as e:
        logging.error(f"Application initialization failed: {str(e)}", exc_info=True)
        raise
