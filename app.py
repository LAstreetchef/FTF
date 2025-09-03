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
        
        # Deployment-safe table creation with proper migration handling
        try:
            # First, ensure ALL tables exist without recreating existing ones
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            logging.info(f"Found {len(existing_tables)} existing tables")
            
            # Check if Event table exists
            if 'event' in existing_tables:
                # Event table exists - check if it has data
                try:
                    event_count = db.session.execute(db.text("SELECT COUNT(*) FROM event")).scalar()
                    logging.info(f"Event table exists with {event_count} events")
                    
                    if event_count > 0:
                        # CRITICAL: Backup event data before any table operations
                        logging.info("Backing up event data before deployment operations")
                        backup_result = db.session.execute(db.text("""
                            CREATE TABLE IF NOT EXISTS event_backup AS 
                            SELECT * FROM event
                        """))
                        db.session.commit()
                        logging.info("Event data backed up successfully")
                    
                    # Create only missing tables, preserve existing ones
                    db.create_all()
                    
                    # Restore data if table was recreated
                    if event_count > 0:
                        current_count = db.session.execute(db.text("SELECT COUNT(*) FROM event")).scalar()
                        if current_count == 0:
                            logging.info("Event table was recreated - restoring data from backup")
                            db.session.execute(db.text("""
                                INSERT INTO event SELECT * FROM event_backup
                            """))
                            db.session.commit()
                            logging.info(f"Restored {event_count} events from backup")
                        
                        # Clean up backup table
                        db.session.execute(db.text("DROP TABLE IF EXISTS event_backup"))
                        db.session.commit()
                        
                except Exception as backup_error:
                    logging.error(f"Event backup/restore failed: {backup_error}")
                    # Still try to create tables
                    db.create_all()
            else:
                # No Event table - safe to create all
                logging.info("Event table not found - creating all tables")
                db.create_all()
                
        except Exception as e:
            # Fallback - create all tables
            logging.error(f"Migration failed ({e}) - falling back to create_all")
            db.create_all()
        
        logging.info("Database tables created/verified")
        
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
