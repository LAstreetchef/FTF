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
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
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

# Configure the database - ALWAYS use production database for consistency
# Force production database URL to prevent development/production sync issues
PRODUCTION_DATABASE_URL = "postgresql://neondb_owner:npg_3rnURNs4fLvp@ep-royal-morning-adkc9dgx.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Override any environment database URL with production URL
app.config["SQLALCHEMY_DATABASE_URI"] = PRODUCTION_DATABASE_URL
logging.info(f"Database configured (PRODUCTION): ep-royal-morning-adkc9dgx.c-2.us-east-1.aws.neon.tech")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
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

# Configure Stripe - Smart mode switching (defaults to LIVE for production)
# Set STRIPE_TEST_MODE=true environment variable to enable test mode
STRIPE_TEST_MODE = os.environ.get('STRIPE_TEST_MODE', 'false').lower() == 'true'

if STRIPE_TEST_MODE:
    # Test mode - for development and testing
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    app.config['STRIPE_PUBLISHABLE_KEY'] = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    app.config['STRIPE_MODE'] = 'test'
    logging.info("🧪 STRIPE TEST MODE ENABLED - Using test keys (4242 cards will work)")
else:
    # Live mode - for real payment processing
    live_secret_key = os.environ.get('STRIPE_SECRET_KEY_LIVE')
    live_publishable_key = os.environ.get('STRIPE_PUBLISHABLE_KEY_LIVE')
    
    if not live_secret_key or not live_publishable_key:
        logging.error("❌ Live Stripe keys not found in environment variables")
        raise ValueError("STRIPE_SECRET_KEY_LIVE and STRIPE_PUBLISHABLE_KEY_LIVE must be set for live mode")
    
    stripe.api_key = live_secret_key
    app.config['STRIPE_PUBLISHABLE_KEY'] = live_publishable_key
    app.config['STRIPE_MODE'] = 'live'
    logging.info(f"💳 STRIPE LIVE MODE ENABLED - Secret key: {live_secret_key[:20]}... Publishable key: {live_publishable_key[:20]}...")
    
    # Double-check the assignment worked (fix for mysterious test key persistence)
    if stripe.api_key != live_secret_key:
        logging.warning("🔧 Stripe key assignment failed, forcing direct assignment")
        import stripe as stripe_module
        stripe_module.api_key = live_secret_key
    
    # CRITICAL FIX: Force verification that live key is actually set
    if not stripe.api_key.startswith('sk_live_'):
        logging.error("🚨 CRITICAL: Live key not properly set despite configuration!")
        # Force override with live key
        stripe.api_key = live_secret_key
        logging.info("🔧 FORCED live key assignment completed")

# Initialize extensions
db.init_app(app)
mail.init_app(app)

# Configure app for iframe embedding
@app.after_request
def after_request(response):
    # Allow embedding in iframes from your custom domain
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self' https://www.thefoodtruckstop.com https://thefoodtruckstop.com"
    
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
