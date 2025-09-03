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

# Configure Flask-Mail for Gmail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('GMAIL_USERNAME', 'truckstopsla@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('GMAIL_PASSWORD', 'your-app-password')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('GMAIL_USERNAME', 'truckstopsla@gmail.com')

# Configure Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
app.config['STRIPE_PUBLISHABLE_KEY'] = os.environ.get('STRIPE_PUBLISHABLE_KEY')

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
        
        # Advanced deployment-safe system with permanent backup storage
        try:
            # First, create all tables including backup system
            db.create_all()
            logging.info("Database tables created/verified")
            
            # Import models after table creation
            from models import Event, EventBackup
            import json
            
            # Check if Event table has data
            event_count = Event.query.count()
            logging.info(f"Event table has {event_count} events")
            
            if event_count == 0:
                # Check for previous backup and restore
                latest_backup = EventBackup.query.order_by(EventBackup.created_at.desc()).first()
                if latest_backup:
                    logging.info("Found previous backup - attempting restore")
                    try:
                        backup_data = json.loads(latest_backup.backup_data)
                        restored_count = 0
                        
                        for event_data in backup_data:
                            # Create new event from backup data
                            event = Event()
                            for key, value in event_data.items():
                                if key != 'id' and hasattr(event, key):
                                    if key in ['date', 'created_at', 'approved_at'] and value:
                                        # Handle datetime fields
                                        from datetime import datetime
                                        setattr(event, key, datetime.fromisoformat(value.replace('Z', '+00:00')))
                                    else:
                                        setattr(event, key, value)
                            
                            db.session.add(event)
                            restored_count += 1
                        
                        db.session.commit()
                        logging.info(f"✅ RESTORED {restored_count} events from backup!")
                        
                    except Exception as restore_error:
                        logging.error(f"Restore failed: {restore_error}")
                        db.session.rollback()
            
            # Always create a fresh backup of current data for next deployment
            events = Event.query.all()
            if events:
                logging.info(f"Creating backup of {len(events)} events for next deployment")
                
                backup_data = []
                for event in events:
                    event_dict = {}
                    for column in event.__table__.columns:
                        value = getattr(event, column.name)
                        if hasattr(value, 'isoformat'):
                            value = value.isoformat()
                        event_dict[column.name] = value
                    backup_data.append(event_dict)
                
                # Store backup in permanent table
                backup = EventBackup()
                backup.backup_data = json.dumps(backup_data)
                backup.backup_type = 'automatic'
                
                db.session.add(backup)
                db.session.commit()
                logging.info("✅ Event backup created for future deployments")
                
        except Exception as e:
            # Fallback - still create tables
            logging.error(f"Advanced backup system failed ({e}) - creating basic tables")
            db.create_all()
        
        # Create default admin if not exists
        from models import Admin
        from werkzeug.security import generate_password_hash
        
        admin = Admin.query.filter_by(username='truckstopsla@gmail.com').first()
        if not admin:
            admin = Admin()
            admin.username = 'truckstopsla@gmail.com'
            admin.password_hash = generate_password_hash('password')
            db.session.add(admin)
            db.session.commit()
            logging.info("Default admin created")
        
        logging.info("Application initialization completed successfully")
        
    except Exception as e:
        logging.error(f"Application initialization failed: {str(e)}", exc_info=True)
        raise
