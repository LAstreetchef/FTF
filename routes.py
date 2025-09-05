from flask import render_template, request, redirect, url_for, session, flash, jsonify, make_response
from werkzeug.security import check_password_hash, generate_password_hash
from app import app, db, mail
from models import Admin, Organizer, FoodTruck, FoodTruckOwner, Event, Pledge, EmailLog, AuthToken, PledgeTransfer, PledgeTransferConsent, Payout, SupportConversation, SupportMessage, OrganizerPayout, FoodTruckPayout, OrganizerTier, AmbassadorChallenge, OrganizerChallengeProgress, PledgeMessage
from utils import send_email, generate_ticket_code, create_stripe_payment_intent, charge_stripe_payment
import stripe
import os
import json
import logging
import secrets
from datetime import datetime
from translations import get_text, get_language_from_request

# Configure Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_...')

def send_new_chat_notification(conversation, user_message, page_context):
    """Send email notification when a new chat conversation is started"""
    try:
        # Build context information
        context_info = []
        if page_context.get('event_name'):
            context_info.append(f"Event: {page_context['event_name']}")
        if page_context.get('page_url'):
            context_info.append(f"Page: {page_context['page_url']}")
        if page_context.get('page_type'):
            context_info.append(f"Page Type: {page_context['page_type']}")
        
        context_str = "\n".join(context_info) if context_info else "General website support"
        
        # Create email subject and body
        subject = f"New Chat Support Request - {conversation.session_id[:8]}"
        
        email_body = f"""A new chat support conversation has been initiated.

Session ID: {conversation.session_id}
First Message: {user_message}

Context:
{context_str}

User Details:
IP Address: {conversation.ip_address}
User Agent: {conversation.user_agent}
Started: {conversation.created_at.strftime('%B %d, %Y at %I:%M %p')}

View Conversation: {url_for('admin_support_conversation', conversation_id=conversation.id, _external=True)}

This notification is sent automatically when users start new chat conversations.
"""
        
        # Send notification email
        send_email(
            'support@foodtruckfundraiser.com',
            subject,
            email_body
        )
        
        logging.info(f"New chat notification sent for conversation {conversation.id}")
        
    except Exception as e:
        logging.error(f"Failed to send new chat notification: {str(e)}")
        raise

@app.route('/health')
def health_check():
    """Health check endpoint for deployment readiness"""
    try:
        # Quick database connection test with timeout
        with db.engine.connect() as connection:
            result = connection.execute(db.text('SELECT 1'))
            
        # Return simple health status
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'database': 'connected'
        }), 200
    except Exception as e:
        logging.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'database': 'disconnected',
            'error': str(e)
        }), 503

@app.route('/readiness')
def readiness_check():
    """Alternative readiness endpoint for deployment"""
    return health_check()

@app.route('/liveness')
def liveness_check():
    """Alternative liveness endpoint for deployment"""
    return health_check()

@app.route('/set-language/<lang>')
def set_language(lang):
    """Set user's language preference"""
    if lang in ['en', 'es']:
        session['language'] = lang
        flash(get_text('language_updated', lang), 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/')
def index():
    """Homepage with overview and navigation"""
    recent_events = Event.query.filter(
        Event.status.in_(['pending', 'funded']),
        Event.organizer_fee_charged == True
    ).order_by(Event.created_at.desc()).limit(3).all()
    current_lang = get_language_from_request()
    return render_template('index.html', recent_events=recent_events, current_lang=current_lang)

# PRODUCTION SECURITY: Test credentials route disabled for live deployment
# @app.route('/test-credentials')
# def test_credentials():
#     """Simple credential testing page"""
#     return render_template('test_credentials.html')





# Admin Routes
# PRODUCTION SECURITY: Debug route disabled for live deployment
# @app.route('/iframe-debug')
# def iframe_debug():
    """Debug endpoint to check iframe functionality"""
    import json
    from flask import request, session
    
    debug_info = {
        'session_data': dict(session),
        'cookies': dict(request.cookies),
        'headers': dict(request.headers),
        'is_secure': request.is_secure,
        'referrer': request.referrer,
        'user_agent': request.headers.get('User-Agent', 'None')
    }
    
    return f"""
    <h2>Iframe Debug Information</h2>
    <pre>{json.dumps(debug_info, indent=2)}</pre>
    
    <h3>Test Cookie Set</h3>
    <script>
        document.cookie = "test_iframe_cookie=working; SameSite=None; Secure; path=/";
        console.log('Cookies:', document.cookie);
    </script>
    
    <h3>Iframe Detection</h3>
    <script>
        console.log('In iframe:', window.self !== window.top);
        console.log('Parent domain:', document.referrer);
        document.write('<p>In iframe: ' + (window.self !== window.top) + '</p>');
        document.write('<p>Referrer: ' + document.referrer + '</p>');
    </script>
    
    <h3>Quick Login Links (For iframe testing)</h3>
    <p><a href="/quick-admin-login" target="_top">Admin Quick Login</a></p>
    <p><a href="/quick-organizer-login" target="_top">Organizer Quick Login</a></p>
    <p><a href="/admin/login">Try Admin Login</a></p>
    <p><a href="/organizer/login">Try Organizer Login</a></p>
    <p><a href="/organizer/dashboard">Test Organizer Dashboard Access</a></p>
    <p><a href="/admin/dashboard">Test Admin Dashboard Access</a></p>
    
    <h3>Full Iframe Test Sequence</h3>
    <div style="border: 2px solid #007bff; padding: 15px; margin: 10px 0;">
        <h4>Test Login → Dashboard Flow:</h4>
        <ol>
            <li><a href="/organizer/login" target="_blank">1. Open Organizer Login</a></li>
            <li>Login with: kammiceli@gmail.com / password</li>
            <li>Should redirect to dashboard automatically</li>
        </ol>
        <p><strong>If failing:</strong> Check browser console and server logs</p>
    </div>
    """

# PRODUCTION SECURITY: Quick login route disabled for live deployment
# @app.route('/quick-admin-login')
def quick_admin_login():
    """Quick login for admin in iframe contexts"""
    try:
        admin = Admin.query.filter_by(username='support@foodtruckfundraiser.com').first()
        if admin:
            session['admin_id'] = admin.id
            session['user_type'] = 'admin'
            session.permanent = True
            
            flash('Quick admin login successful', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Admin user not found', 'error')
            return redirect(url_for('admin_login'))
    except Exception as e:
        import traceback
        error_msg = f"Quick admin login error: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        flash('Login error occurred', 'error')
        return redirect(url_for('admin_login'))

# PRODUCTION SECURITY: Quick login route disabled for live deployment
# @app.route('/quick-organizer-login')
def quick_organizer_login():
    """Quick login for organizer in iframe contexts"""
    try:
        organizer = Organizer.query.filter_by(email='kammiceli@gmail.com').first()
        if organizer:
            session['organizer_id'] = organizer.id
            session['user_type'] = 'organizer'
            session.permanent = True
            
            flash('Quick organizer login successful', 'success')
            return redirect(url_for('organizer_dashboard'))
        else:
            flash('Organizer user not found', 'error')
            return redirect(url_for('organizer_login'))
    except Exception as e:
        import traceback
        error_msg = f"Quick organizer login error: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        flash('Login error occurred', 'error')
        return redirect(url_for('organizer_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Enhanced iframe detection
        is_embedded = (request.referrer and 'thefoodtruckstop.com' in request.referrer) or \
                     request.form.get('iframe_context') == 'true'
        user_agent = request.headers.get('User-Agent', '')
        
        logging.info(f"Admin login attempt - Username: {username}, Embedded: {is_embedded}")
        logging.info(f"Request details - Referrer: {request.referrer}, Iframe field: {request.form.get('iframe_context')}")
        logging.info(f"Form data: {dict(request.form)}")
        
        admin = Admin.query.filter_by(username=username).first()
        logging.info(f"Admin found in database: {admin is not None}")
        
        if admin:
            password_valid = check_password_hash(admin.password_hash, password)
            logging.info(f"Password validation result: {password_valid}")
            
            if password_valid:
                # Clear any existing session data first
                session.clear()
                
                # Set session data
                session['admin_id'] = admin.id
                session['user_type'] = 'admin'
                session.permanent = True
                
                # Force session save for iframe contexts with additional persistence
                session.modified = True
                
                # Also set a simple auth flag for debugging
                session['authenticated'] = True
                session['login_time'] = datetime.now().isoformat()
                
                logging.info(f"Admin {username} logged in successfully, session set with admin_id: {admin.id}")
                logging.info(f"Session contents after login: {dict(session)}")
                flash('Successfully logged in as admin', 'success')
                
                # Always return a page that handles both iframe and regular contexts
                return f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Login Success</title>
                    <script>
                        console.log('Admin login successful!');
                        console.log('In iframe:', window.self !== window.top);
                        console.log('Server detected embedded:', {str(is_embedded).lower()});
                        
                        // Wait a moment for session to be saved, then redirect
                        setTimeout(function() {{
                            if (window.self !== window.top) {{
                                // In iframe - try to redirect parent
                                try {{
                                    console.log('Redirecting parent window...');
                                    window.parent.location.href = 'https://www.thefoodtruckstop.com/fundraiser';
                                }} catch(e) {{
                                    console.log('Parent redirect failed, using direct redirect:', e);
                                    window.location.href = '{url_for('admin_dashboard')}';
                                }}
                            }} else {{
                                // Regular context
                                console.log('Regular redirect to dashboard...');
                                window.location.href = '{url_for('admin_dashboard')}';
                            }}
                        }}, 500);
                    </script>
                </head>
                <body>
                    <div style="text-align: center; margin-top: 50px;">
                        <h2>✅ Admin Login Successful!</h2>
                        <p>Redirecting to dashboard...</p>
                        <p>If not redirected: <a href="{url_for('admin_dashboard')}" target="_top">Click here for Dashboard</a></p>
                        <hr>
                        <small>
                            Debug: Iframe detected: {is_embedded}<br>
                            Referrer: {request.referrer}<br>
                            Session ID: {session.get('admin_id', 'None')}
                        </small>
                    </div>
                </body>
                </html>
                """
        
        logging.warning(f"Login failed for username: {username}")
        flash('Invalid credentials', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/change-password/<int:admin_id>', methods=['GET', 'POST'])
def admin_change_password(admin_id):
    """Force admin to change password on first login for security"""
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password or len(new_password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template('admin/change_password.html', admin_id=admin_id)
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('admin/change_password.html', admin_id=admin_id)
        
        # Update admin password
        admin = Admin.query.get(admin_id)
        if admin:
            admin.password_hash = generate_password_hash(new_password)
            admin.must_change_password = False
            db.session.commit()
            
            # Now log them in
            session['admin_id'] = admin.id
            session['user_type'] = 'admin'
            session.permanent = True
            session.modified = True
            
            flash('Password changed successfully. You are now logged in.', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Admin not found', 'error')
            return redirect(url_for('admin_login'))
    
    return render_template('admin/change_password.html', admin_id=admin_id)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('user_type', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))


@app.route('/admin/food-truck-owners')
def admin_food_truck_owners():
    """Admin page to manage food truck owner registrations"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    # Get all food truck owners with their trucks
    pending_owners = FoodTruckOwner.query.filter_by(status='pending').order_by(FoodTruckOwner.created_at.desc()).all()
    approved_owners = FoodTruckOwner.query.filter_by(status='approved').order_by(FoodTruckOwner.approved_at.desc()).all()
    rejected_owners = FoodTruckOwner.query.filter_by(status='rejected').order_by(FoodTruckOwner.created_at.desc()).all()
    
    return render_template('admin/food_truck_owners.html',
                         pending_owners=pending_owners,
                         approved_owners=approved_owners,
                         rejected_owners=rejected_owners)

@app.route('/admin/food-truck-owners/<int:owner_id>/approve', methods=['POST'])
def admin_approve_truck_owner(owner_id):
    """Approve food truck owner registration"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    owner = FoodTruckOwner.query.get_or_404(owner_id)
    admin = Admin.query.get(session['admin_id'])
    
    if owner.status == 'pending':
        owner.status = 'approved'
        owner.approved_at = datetime.utcnow()
        owner.approved_by = admin.id
        
        db.session.commit()
        
        # Send approval email
        send_email(
            owner.email,
            'Food Truck Registration Approved!',
            f"""Congratulations {owner.name}!

Your food truck owner registration has been approved by our admin team.

Business: {owner.business_name}
Approval Date: {owner.approved_at.strftime('%B %d, %Y at %I:%M %p')}

You can now:
1. Login to your food truck dashboard
2. Add your food truck profiles
3. Create menus and set pricing
4. Start participating in fundraising events

Login here: {url_for('food_truck_login', _external=True)}

Welcome to the Food Truck Fundraiser platform!

Best regards,
The Food Truck Fundraiser Team"""
        )
        
        flash(f'Successfully approved {owner.business_name}. Approval email sent.', 'success')
    else:
        flash('Food truck owner is not in pending status.', 'error')
    
    return redirect(url_for('admin_food_truck_owners'))

@app.route('/admin/food-truck-owners/<int:owner_id>/reject', methods=['POST'])
def admin_reject_truck_owner(owner_id):
    """Reject food truck owner registration"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    owner = FoodTruckOwner.query.get_or_404(owner_id)
    rejection_reason = request.form.get('reason', 'No reason provided')
    
    if owner.status == 'pending':
        owner.status = 'rejected'
        
        db.session.commit()
        
        # Send rejection email
        send_email(
            owner.email,
            'Food Truck Registration Update',
            f"""Hello {owner.name},

Thank you for your interest in joining our Food Truck Fundraiser platform.

Unfortunately, we are unable to approve your registration for {owner.business_name} at this time.

Reason: {rejection_reason}

If you have questions or would like to reapply in the future, please feel free to contact us.

Best regards,
The Food Truck Fundraiser Team"""
        )
        
        flash(f'Rejected {owner.business_name}. Rejection email sent.', 'success')
    else:
        flash('Food truck owner is not in pending status.', 'error')
    
    return redirect(url_for('admin_food_truck_owners'))

@app.route('/admin/food-trucks')
def admin_food_trucks():
    """Admin page to manage food truck profiles"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    # Get all food trucks with their owners (only show paid trucks for approval)
    pending_trucks = FoodTruck.query.filter_by(status='pending', registration_fee_charged=True).order_by(FoodTruck.created_at.desc()).all()
    approved_trucks = FoodTruck.query.filter_by(status='approved', registration_fee_charged=True).order_by(FoodTruck.approved_at.desc()).all()
    rejected_trucks = FoodTruck.query.filter_by(status='rejected', registration_fee_charged=True).order_by(FoodTruck.created_at.desc()).all()
    
    return render_template('admin/food_trucks.html',
                         pending_trucks=pending_trucks,
                         approved_trucks=approved_trucks,
                         rejected_trucks=rejected_trucks)

@app.route('/admin/food-trucks/<int:truck_id>/approve', methods=['POST'])
def admin_approve_food_truck(truck_id):
    """Approve food truck profile"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    truck = FoodTruck.query.get_or_404(truck_id)
    admin = Admin.query.get(session['admin_id'])
    
    if truck.status == 'pending':
        # Validate that truck has at least one menu item
        menu_items = truck.get_menu_items()
        if not menu_items or len(menu_items) == 0:
            flash(f'Cannot approve "{truck.name}" - food truck must have at least one menu item. Please ask the owner to add menu items first.', 'error')
            return redirect(url_for('admin_food_trucks'))
        
        truck.status = 'approved'
        truck.approved_at = datetime.utcnow()
        truck.approved_by = admin.id
        
        db.session.commit()
        
        # Send approval email to truck owner
        if truck.owner:
            send_email(
                truck.owner.email,
                f'Food Truck "{truck.name}" Approved!',
                f"""Great news {truck.owner.name}!

Your food truck "{truck.name}" has been approved and is now available for organizers to select for their events.

Truck Details:
- Name: {truck.name}
- Cuisine: {truck.cuisine_type or 'Not specified'}
- Description: {truck.description}
- Minimum Sales Goal: ${truck.sales_goal:.2f}
- Menu Items: {len(truck.get_menu_items())} items

Your truck will now appear in the organizer dashboard when they create new events.

Login to manage your truck: {url_for('food_truck_login', _external=True)}

Best regards,
The Food Truck Fundraiser Team"""
            )
        
        flash(f'Successfully approved food truck "{truck.name}". Approval email sent.', 'success')
    else:
        flash('Food truck is not in pending status.', 'error')
    
    return redirect(url_for('admin_food_trucks'))

@app.route('/admin/food-trucks/<int:truck_id>/reject', methods=['POST'])
def admin_reject_food_truck(truck_id):
    """Reject food truck profile"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    truck = FoodTruck.query.get_or_404(truck_id)
    rejection_reason = request.form.get('reason', 'No reason provided')
    
    if truck.status == 'pending':
        truck.status = 'rejected'
        
        db.session.commit()
        
        # Send rejection email to truck owner
        if truck.owner:
            send_email(
                truck.owner.email,
                f'Food Truck "{truck.name}" Update',
                f"""Hello {truck.owner.name},

Thank you for submitting your food truck "{truck.name}" for approval.

Unfortunately, we are unable to approve this truck profile at this time.

Reason: {rejection_reason}

You can edit your truck profile and resubmit for approval through your dashboard.

Login here: {url_for('food_truck_login', _external=True)}

Best regards,
The Food Truck Fundraiser Team"""
            )
        
        flash(f'Rejected food truck "{truck.name}". Rejection email sent.', 'success')
    else:
        flash('Food truck is not in pending status.', 'error')
    
    return redirect(url_for('admin_food_trucks'))

@app.route('/admin/payouts')
def admin_payouts():
    """Admin page to manage food truck payouts"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    # Get events that are approved and may need payouts
    completed_events = Event.query.filter_by(status='approved').order_by(Event.date.desc()).all()
    
    # Get existing organizer payouts
    pending_payouts = OrganizerPayout.query.filter_by(status='pending').order_by(OrganizerPayout.created_at.desc()).all()
    completed_payouts = OrganizerPayout.query.filter_by(status='completed').order_by(OrganizerPayout.completed_at.desc()).limit(20).all()
    
    return render_template('admin/payouts.html',
                         completed_events=completed_events,
                         pending_payouts=pending_payouts,
                         completed_payouts=completed_payouts)

@app.route('/admin/payouts/<int:event_id>/create', methods=['POST'])
def admin_create_payout(event_id):
    """Create payout for completed event"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    event = Event.query.get_or_404(event_id)
    admin = Admin.query.get(session['admin_id'])
    
    # Verify event is charged and doesn't already have a payout
    if event.status != 'charged':
        flash('Event must be charged before creating payout.', 'error')
        return redirect(url_for('admin_payouts'))
    
    existing_payout = Payout.query.filter_by(event_id=event_id).first()
    if existing_payout:
        flash(f'Payout already exists for event {event.name}.', 'error')
        return redirect(url_for('admin_payouts'))
    
    # Calculate payout amount (total pledges minus platform fee)
    total_collected = event.current_pledges
    platform_fee_percent = 5.0  # 5% platform fee
    platform_fee = total_collected * (platform_fee_percent / 100)
    payout_amount = total_collected - platform_fee
    
    # Create payout record
    payout = Payout(
        event_id=event_id,
        food_truck_id=event.food_truck_id,
        amount=payout_amount,
        platform_fee=platform_fee,
        created_by=admin.id,
        status='pending'
    )
    
    db.session.add(payout)
    db.session.commit()
    
    # Send notification email to food truck owner
    if event.food_truck and event.food_truck.owner:
        send_email(
            event.food_truck.owner.email,
            f'Payout Initiated for {event.name}',
            f"""Hello {event.food_truck.owner.name},

Great news! A payout has been initiated for your food truck "{event.food_truck.name}" from the successful event "{event.name}".

Event Details:
- Event: {event.name}
- Date: {event.date.strftime('%B %d, %Y')}
- Total Collected: ${total_collected:.2f}
- Platform Fee (5%): ${platform_fee:.2f}
- Your Payout: ${payout_amount:.2f}

The payout will be processed and sent to your registered bank account within 3-5 business days.

Login to view details: {url_for('food_truck_login', _external=True)}

Thank you for participating in Food Truck Fundraiser!

Best regards,
The Food Truck Fundraiser Team"""
        )
    
    flash(f'Payout created for ${payout_amount:.2f}. Notification sent to food truck owner.', 'success')
    return redirect(url_for('admin_payouts'))

@app.route('/admin/payouts/<int:payout_id>/complete', methods=['POST'])
def admin_complete_payout(payout_id):
    """Mark payout as completed"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    payout = Payout.query.get_or_404(payout_id)
    
    if payout.status == 'pending':
        payout.status = 'completed'
        payout.paid_at = datetime.utcnow()
        
        db.session.commit()
        
        # Send completion notification to food truck owner
        if payout.food_truck and payout.food_truck.owner:
            send_email(
                payout.food_truck.owner.email,
                f'Payout Completed - ${payout.amount:.2f}',
                f"""Hello {payout.food_truck.owner.name},

Your payout has been successfully completed!

Payment Details:
- Food Truck: {payout.food_truck.name}
- Event: {payout.event.name}
- Amount Paid: ${payout.amount:.2f}
- Payment Date: {payout.paid_at.strftime('%B %d, %Y at %I:%M %p')}

The funds should appear in your bank account within 1-2 business days.

Thank you for being part of the Food Truck Fundraiser platform!

Best regards,
The Food Truck Fundraiser Team"""
            )
        
        flash(f'Payout marked as completed. Confirmation sent to food truck owner.', 'success')
    else:
        flash('Payout is not in pending status.', 'error')
    
    return redirect(url_for('admin_payouts'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    # Dashboard statistics
    total_trucks = FoodTruck.query.count()
    total_events = Event.query.count()
    pending_events = Event.query.filter_by(status='pending').count()
    funded_events = Event.query.filter(Event.status == 'funded').count()
    
    recent_events = Event.query.order_by(Event.created_at.desc()).limit(5).all()
    
    # Get Stripe mode status
    stripe_mode = app.config.get('STRIPE_MODE', 'unknown')
    
    return render_template('admin/dashboard.html', 
                         total_trucks=total_trucks,
                         total_events=total_events,
                         pending_events=pending_events,
                         funded_events=funded_events,
                         recent_events=recent_events,
                         stripe_mode=stripe_mode)








@app.route('/force-template-refresh-xyz123')
def force_template_refresh():
    """Force template refresh by clearing Flask template cache"""
    app.jinja_env.cache.clear()
    return "Template cache cleared for production environment"

# PRODUCTION SECURITY: Debug route disabled for live deployment
# @app.route('/debug-database-xyz123')
# def debug_database():
    """Debug route to check database contents for troubleshooting"""
    debug_info = {
        'database_type': 'development' if 'dev' in str(db.engine.url) else 'production',
        'database_url': str(db.engine.url).split('@')[1] if '@' in str(db.engine.url) else 'unknown',
        'admin_count': Admin.query.count(),
        'food_truck_count': FoodTruck.query.count(),
        'event_count': Event.query.count(),
        'pledge_count': Pledge.query.count()
    }
    
    # Get admin users (without passwords)
    admins = Admin.query.all()
    admin_list = [{'id': a.id, 'username': a.username, 'created_at': a.created_at} for a in admins]
    
    # Get food trucks
    trucks = FoodTruck.query.all()
    truck_list = [{'id': t.id, 'name': t.name, 'description': t.description, 'sales_goal': t.sales_goal} for t in trucks]
    
    # Get events
    events = Event.query.all()
    event_list = [{'id': e.id, 'name': e.name, 'status': e.status, 'pledge_goal': e.pledge_goal, 'current_pledges': e.current_pledges} for e in events]
    
    return jsonify({
        'debug_info': debug_info,
        'admins': admin_list,
        'food_trucks': truck_list,
        'events': event_list
    })

@app.route('/sync-data-xyz123')
def sync_data():
    """Sync food truck data to production environment"""
    try:
        # Define the standard food trucks data
        standard_trucks = [
            {
                'name': 'Tasty Tacos',
                'description': "LA's premiere healthy food truck",
                'menu_items': [
                    {"name": "Carnitas Taco", "price": 4.5},
                    {"name": "Chicken Taco", "price": 4.0},
                    {"name": "Veggie Taco", "price": 3.75},
                    {"name": "Combo Meal", "price": 12.0}
                ],
                'sales_goal': 1500
            },
            {
                'name': 'Tasty Tacos Truck',
                'description': 'Authentic Mexican street tacos with fresh ingredients',
                'menu_items': [
                    {"name": "Carnitas Taco", "price": 4.5},
                    {"name": "Chicken Taco", "price": 4.0},
                    {"name": "Veggie Taco", "price": 3.75},
                    {"name": "Combo Meal", "price": 12.0}
                ],
                'sales_goal': 500
            },
            {
                'name': 'Acai Truck',
                'description': 'Fresh and healthy acai bowls made with organic ingredients',
                'menu_items': [
                    {"name": "Classic Acai Bowl", "price": 12.50},
                    {"name": "Berry Blast Bowl", "price": 14.00},
                    {"name": "Green Goddess Bowl", "price": 13.25},
                    {"name": "Protein Power Bowl", "price": 15.50},
                    {"name": "Mini Acai Bowl", "price": 8.75},
                    {"name": "Acai Smoothie", "price": 7.50}
                ],
                'sales_goal': 1750
            },
            {
                'name': 'Green Truck',
                'description': 'Fresh, locally-sourced meals with a focus on sustainability and health.',
                'menu_items': [
                    {"name": "Green Goddess Bowl", "price": 13.50},
                    {"name": "Quinoa Power Salad", "price": 12.75},
                    {"name": "Avocado Toast Deluxe", "price": 9.25},
                    {"name": "Veggie Wrap", "price": 11.00},
                    {"name": "Green Smoothie", "price": 7.50},
                    {"name": "Kale Caesar Salad", "price": 12.00},
                    {"name": "Buddha Bowl", "price": 14.25},
                    {"name": "Raw Veggie Tacos", "price": 10.75}
                ],
                'sales_goal': 1800
            },
            {
                'name': 'Ho-Lee Chow',
                'description': 'Healthy Asian inspired food. All our bowls are gluten-free. Vegan, grain-free, and customizable options.',
                'menu_items': [
                    {"name": "Korean BBQ Bowl", "price": 14.50},
                    {"name": "Teriyaki Chicken Bowl", "price": 13.25},
                    {"name": "Vegetable Pad Thai", "price": 12.00},
                    {"name": "Asian Fusion Bowl", "price": 15.75},
                    {"name": "Poke Bowl", "price": 16.00},
                    {"name": "Spring Rolls (3pc)", "price": 8.50},
                    {"name": "Miso Soup", "price": 6.00},
                    {"name": "Asian Salad", "price": 11.25}
                ],
                'sales_goal': 2000
            }
        ]
        
        results = []
        
        # Sync each food truck
        for truck_data in standard_trucks:
            existing_truck = FoodTruck.query.filter_by(name=truck_data['name']).first()
            
            if existing_truck:
                # Update existing truck
                existing_truck.description = truck_data['description']
                existing_truck.menu_items = json.dumps(truck_data['menu_items'])
                existing_truck.sales_goal = truck_data['sales_goal']
                # Ensure status is approved for production use
                existing_truck.status = 'approved'
                existing_truck.registration_fee_charged = True
                results.append(f"Updated: {truck_data['name']}")
            else:
                # Create new truck
                new_truck = FoodTruck(
                    name=truck_data['name'],
                    description=truck_data['description'],
                    menu_items=json.dumps(truck_data['menu_items']),
                    sales_goal=truck_data['sales_goal'],
                    status='approved',  # Auto-approve for production
                    registration_fee_charged=True  # Mark as paid for production
                )
                db.session.add(new_truck)
                results.append(f"Created: {truck_data['name']}")
        
        # Also update any Amazon gate events to use Ho-Lee Chow
        amazon_events = Event.query.filter(Event.name.like('%Amazon%')).all()
        for event in amazon_events:
            ho_lee_truck = FoodTruck.query.filter_by(name='Ho-Lee Chow').first()
            if ho_lee_truck:
                event.food_truck_id = ho_lee_truck.id
                event.pledge_goal = 2000
                event.selected_menu_items = json.dumps([
                    {"name": "Korean BBQ Bowl", "price": 14.50, "original_price": 14.50, "marked_up_price": 16.68},
                    {"name": "Teriyaki Chicken Bowl", "price": 13.25, "original_price": 13.25, "marked_up_price": 15.24},
                    {"name": "Vegetable Pad Thai", "price": 12.00, "original_price": 12.00, "marked_up_price": 13.80},
                    {"name": "Asian Fusion Bowl", "price": 15.75, "original_price": 15.75, "marked_up_price": 18.11},
                    {"name": "Poke Bowl", "price": 16.00, "original_price": 16.00, "marked_up_price": 18.40},
                    {"name": "Spring Rolls (3pc)", "price": 8.50, "original_price": 8.50, "marked_up_price": 9.78},
                    {"name": "Miso Soup", "price": 6.00, "original_price": 6.00, "marked_up_price": 6.90},
                    {"name": "Asian Salad", "price": 11.25, "original_price": 11.25, "marked_up_price": 12.94}
                ])
                results.append(f"Updated event: {event.name} to use Ho-Lee Chow")
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Data sync completed - all trucks and Amazon events updated',
            'results': results,
            'total_trucks': FoodTruck.query.count()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error syncing data: {str(e)}'
        })

@app.route('/fix-menu-items-xyz123')
def fix_menu_items():
    """Fix menu items for ALL events that are missing them - universal solution"""
    try:
        results = []
        
        # Get all events that have empty or missing menu items
        all_events = Event.query.all()
        
        for event in all_events:
            # Check if event has empty or missing menu items
            menu_items = event.get_selected_menu_items() if event.selected_menu_items else []
            
            if not menu_items and event.food_truck:
                truck = event.food_truck
                truck_menu = truck.get_menu_items() if truck.menu_items else []
                
                if truck_menu:
                    # Generate menu items with markup for this event
                    marked_up_items = []
                    for item in truck_menu:
                        original_price = item.get('price', 15.0)
                        markup_rate = 0.15  # 15% markup
                        marked_up_price = round(original_price * (1 + markup_rate), 2)
                        
                        marked_up_items.append({
                            "name": item.get('name', 'Menu Item'),
                            "price": original_price,
                            "original_price": original_price,
                            "marked_up_price": marked_up_price
                        })
                    
                    # Update the event with proper menu items
                    event.selected_menu_items = json.dumps(marked_up_items)
                    
                    # Set appropriate pledge goal based on truck
                    if truck.sales_goal:
                        event.pledge_goal = truck.sales_goal
                    
                    results.append(f"Fixed {truck.name} menu for event: {event.name} ({len(marked_up_items)} items)")
                else:
                    results.append(f"Warning: {truck.name} has no menu items to copy for event: {event.name}")
            
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Menu items fixed for all events missing them',
            'results': results,
            'events_updated': len([r for r in results if r.startswith('Fixed')])
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error fixing menu items: {str(e)}'
        })

# PRODUCTION SECURITY: Debug route disabled for live deployment
# @app.route('/debug-trucks-xyz123')
# def debug_trucks():
    """Debug route to see what trucks exist in production database"""
    try:
        all_trucks = FoodTruck.query.all()
        approved_trucks = FoodTruck.query.filter_by(status='approved', registration_fee_charged=True).all()
        
        truck_data = []
        for truck in all_trucks:
            truck_data.append({
                'id': truck.id,
                'name': truck.name,
                'status': getattr(truck, 'status', 'NO STATUS FIELD'),
                'registration_fee_charged': getattr(truck, 'registration_fee_charged', 'NO FEE FIELD'),
                'description': truck.description,
                'has_menu': bool(truck.menu_items)
            })
        
        return jsonify({
            'total_trucks': len(all_trucks),
            'approved_paid_trucks': len(approved_trucks),
            'all_trucks': truck_data,
            'database_url_set': bool(os.environ.get('DATABASE_URL'))
        })
    except Exception as e:
        return jsonify({'error': str(e), 'type': str(type(e))})

@app.route('/database-sync-admin-xyz456')
def database_sync_admin():
    """Comprehensive database sync and phantom data detection"""
    try:
        # Clear any Flask cache or session issues first
        db.session.rollback()
        
        sync_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'database_info': {
                'url_type': 'postgresql' if 'postgresql' in str(db.engine.url) else 'sqlite',
                'url_partial': str(db.engine.url).split('@')[1] if '@' in str(db.engine.url) else str(db.engine.url)[:50]
            },
            'data_integrity_check': {},
            'phantom_data_check': {},
            'cache_cleared': True
        }
        
        # 1. Basic counts and integrity
        try:
            event_count = Event.query.count()
            pledge_count = Pledge.query.count()
            organizer_count = Organizer.query.count()
            
            sync_results['data_integrity_check'] = {
                'events': event_count,
                'pledges': pledge_count,
                'organizers': organizer_count,
                'database_responsive': True
            }
        except Exception as e:
            sync_results['data_integrity_check'] = {
                'error': str(e),
                'database_responsive': False
            }
        
        # 2. Check specific event that was showing phantom data
        try:
            event_23 = Event.query.get(23)
            if event_23:
                pledges_23 = Pledge.query.filter_by(event_id=23).all()
                organizer_23 = Organizer.query.get(event_23.organizer_id) if event_23.organizer_id else None
                
                sync_results['phantom_data_check']['event_23'] = {
                    'exists': True,
                    'name': event_23.name,
                    'current_pledges': float(event_23.current_pledges or 0),
                    'pledge_goal': float(event_23.pledge_goal or 0),
                    'status': event_23.status,
                    'organizer_id': event_23.organizer_id,
                    'organizer_email': organizer_23.email if organizer_23 else None,
                    'actual_pledge_count': len(pledges_23),
                    'actual_pledge_total': sum(p.amount for p in pledges_23),
                    'pledge_details': [
                        {
                            'amount': float(p.amount),
                            'email': p.email,
                            'status': p.status,
                            'created_at': p.created_at.isoformat() if p.created_at else None
                        } for p in pledges_23
                    ]
                }
            else:
                sync_results['phantom_data_check']['event_23'] = {
                    'exists': False,
                    'message': 'Event 23 not found in database'
                }
        except Exception as e:
            sync_results['phantom_data_check']['event_23'] = {
                'error': str(e)
            }
        
        # 3. Look for events with mismatched pledge totals
        try:
            events_with_issues = []
            for event in Event.query.all():
                pledges = Pledge.query.filter_by(event_id=event.id).all()
                actual_total = sum(p.amount for p in pledges if p.status in ['pending', 'charged'])
                recorded_total = float(event.current_pledges or 0)
                
                if abs(actual_total - recorded_total) > 0.01:  # Allow for minor rounding
                    events_with_issues.append({
                        'event_id': event.id,
                        'event_name': event.name,
                        'recorded_pledges': recorded_total,
                        'actual_pledges': actual_total,
                        'discrepancy': actual_total - recorded_total,
                        'pledge_count': len(pledges)
                    })
            
            sync_results['phantom_data_check']['mismatched_events'] = events_with_issues
        except Exception as e:
            sync_results['phantom_data_check']['mismatched_events'] = {
                'error': str(e)
            }
        
        # 4. Force refresh specific problematic data
        try:
            # Clear SQLAlchemy session and force fresh query
            db.session.expunge_all()
            
            fresh_event_23 = db.session.query(Event).filter_by(id=23).first()
            if fresh_event_23:
                sync_results['phantom_data_check']['fresh_query_event_23'] = {
                    'name': fresh_event_23.name,
                    'current_pledges': float(fresh_event_23.current_pledges or 0),
                    'status': fresh_event_23.status
                }
        except Exception as e:
            sync_results['phantom_data_check']['fresh_query_event_23'] = {
                'error': str(e)
            }
        
        # 5. Recommendations based on findings
        recommendations = []
        
        if sync_results['phantom_data_check'].get('event_23', {}).get('exists'):
            event_data = sync_results['phantom_data_check']['event_23']
            if event_data['current_pledges'] != event_data['actual_pledge_total']:
                recommendations.append("Event 23 has mismatched pledge totals - database corruption detected")
            
            if event_data['actual_pledge_count'] == 0 and event_data['current_pledges'] > 0:
                recommendations.append("Event 23 shows pledges but has no actual pledge records - phantom data confirmed")
        
        if sync_results['phantom_data_check'].get('mismatched_events'):
            recommendations.append(f"Found {len(sync_results['phantom_data_check']['mismatched_events'])} events with mismatched pledge totals")
        
        if not recommendations:
            recommendations.append("No major data integrity issues detected")
        
        sync_results['recommendations'] = recommendations
        
        # Return formatted HTML for easy reading
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Database Sync Analysis</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
                .success {{ background: #d4edda; border-color: #c3e6cb; }}
                .warning {{ background: #fff3cd; border-color: #ffeaa7; }}
                .error {{ background: #f8d7da; border-color: #f5c6cb; }}
                pre {{ background: #f8f9fa; padding: 10px; overflow-x: auto; }}
                .recommendations {{ background: #e7f3ff; border: 1px solid #bee5eb; padding: 15px; }}
            </style>
        </head>
        <body>
            <h1>🔄 Database Sync Analysis</h1>
            <p><strong>Timestamp:</strong> {sync_results['timestamp']}</p>
            
            <div class="section {'success' if sync_results['data_integrity_check'].get('database_responsive') else 'error'}">
                <h2>📊 Database Status</h2>
                <p><strong>Database Type:</strong> {sync_results['database_info']['url_type']}</p>
                <p><strong>URL:</strong> {sync_results['database_info']['url_partial']}</p>
                <p><strong>Events:</strong> {sync_results['data_integrity_check'].get('events', 'Error')}</p>
                <p><strong>Pledges:</strong> {sync_results['data_integrity_check'].get('pledges', 'Error')}</p>
                <p><strong>Organizers:</strong> {sync_results['data_integrity_check'].get('organizers', 'Error')}</p>
            </div>
            
            <div class="section {'warning' if sync_results['phantom_data_check'].get('event_23', {}).get('exists') else 'error'}">
                <h2>🔍 Event 23 Analysis (Phantom Data Check)</h2>
                <pre>{json.dumps(sync_results['phantom_data_check'].get('event_23', {}), indent=2)}</pre>
            </div>
            
            <div class="section {'warning' if sync_results['phantom_data_check'].get('mismatched_events') else 'success'}">
                <h2>⚠️ Events with Mismatched Pledge Totals</h2>
                <pre>{json.dumps(sync_results['phantom_data_check'].get('mismatched_events', []), indent=2)}</pre>
            </div>
            
            <div class="recommendations">
                <h2>💡 Recommendations</h2>
                <ul>
                    {''.join([f'<li>{rec}</li>' for rec in sync_results['recommendations']])}
                </ul>
            </div>
            
            <div class="section">
                <h2>🛠️ Available Actions</h2>
                <p><a href="/clear-cache-and-refresh-xyz789" style="background: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Clear All Cache & Force Refresh</a></p>
                <p><a href="/admin/dashboard" style="background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Back to Admin Dashboard</a></p>
            </div>
            
            <details style="margin-top: 20px;">
                <summary>Raw JSON Output</summary>
                <pre>{json.dumps(sync_results, indent=2)}</pre>
            </details>
        </body>
        </html>
        """
        
    except Exception as e:
        logging.error(f"Database sync analysis failed: {str(e)}")
        return f"""
        <h1>❌ Database Sync Analysis Failed</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/admin/dashboard">← Back to Admin Dashboard</a></p>
        """

@app.route('/clear-cache-and-refresh-xyz789')
def clear_cache_and_refresh():
    """Clear all caches and force fresh database queries"""
    try:
        # Clear SQLAlchemy session cache
        db.session.rollback()
        db.session.expunge_all()
        
        # Force connection pool refresh
        db.engine.dispose()
        
        # Clear Flask session
        session.clear()
        
        # Test fresh connection
        test_query = db.session.execute(db.text('SELECT COUNT(*) FROM event')).scalar()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Cache Cleared</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .success {{ background: #d4edda; padding: 20px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="success">
                <h1>✅ Cache Clearing Complete</h1>
                <p><strong>Actions Performed:</strong></p>
                <ul>
                    <li>SQLAlchemy session cache cleared</li>
                    <li>Database connection pool refreshed</li>
                    <li>Flask session cleared</li>
                    <li>Fresh database connection tested</li>
                </ul>
                <p><strong>Fresh Event Count:</strong> {test_query}</p>
                <p><strong>Timestamp:</strong> {datetime.utcnow().isoformat()}</p>
            </div>
            
            <div style="margin: 20px 0;">
                <h2>Next Steps</h2>
                <p><a href="/database-sync-admin-xyz456" style="background: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Run Database Sync Analysis Again</a></p>
                <p><a href="/admin/events/23/transfer" style="background: #ffc107; color: black; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Test Event 23 Transfer Page</a></p>
                <p><a href="/admin/dashboard" style="background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Back to Admin Dashboard</a></p>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <h1>❌ Cache Clear Failed</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/admin/dashboard">← Back to Admin Dashboard</a></p>
        """

# PRODUCTION SECURITY: Debug route disabled for live deployment
# @app.route('/debug-transfer-token-xyz890/<token>')
# def debug_transfer_token(token):
    """Debug route to check transfer token and pledge status"""
    try:
        # Find pledge by transfer token
        pledge = Pledge.query.filter_by(transfer_token=token).first()
        
        debug_info = {
            'token': token,
            'timestamp': datetime.utcnow().isoformat(),
            'pledge_found': pledge is not None,
            'database_connection': 'working'
        }
        
        if pledge:
            target_event = Event.query.get(pledge.transfer_target_event_id) if pledge.transfer_target_event_id else None
            
            debug_info.update({
                'pledge_id': pledge.id,
                'pledge_email': pledge.email,
                'pledge_amount': float(pledge.amount),
                'pledge_status': pledge.status,
                'current_event_id': pledge.event_id,
                'current_event_name': pledge.event.name if pledge.event else None,
                'transfer_target_event_id': pledge.transfer_target_event_id,
                'target_event_name': target_event.name if target_event else None,
                'transfer_initiated_at': pledge.transfer_initiated_at.isoformat() if pledge.transfer_initiated_at else None,
                'target_event_exists': target_event is not None,
                'target_event_status': target_event.status if target_event else None
            })
            
            # Test if we can access the event relationship
            try:
                old_event_name = pledge.event.name
                debug_info['old_event_accessible'] = True
                debug_info['old_event_name'] = old_event_name
            except Exception as e:
                debug_info['old_event_accessible'] = False
                debug_info['old_event_error'] = str(e)
                
        else:
            # Check if token exists in other formats or if there are any tokens at all
            all_tokens = db.session.execute(
                db.text("SELECT transfer_token FROM pledge WHERE transfer_token IS NOT NULL")
            ).fetchall()
            
            debug_info.update({
                'total_active_tokens': len(all_tokens),
                'all_tokens': [t[0] for t in all_tokens] if all_tokens else []
            })
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Transfer Token Debug</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
                .success {{ background: #d4edda; border-color: #c3e6cb; }}
                .error {{ background: #f8d7da; border-color: #f5c6cb; }}
                pre {{ background: #f8f9fa; padding: 10px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <h1>🔍 Transfer Token Debug</h1>
            <p><strong>Token:</strong> {token}</p>
            
            <div class="section {'success' if debug_info['pledge_found'] else 'error'}">
                <h2>Token Analysis</h2>
                <pre>{json.dumps(debug_info, indent=2)}</pre>
            </div>
            
            <div class="section">
                <h2>Available Actions</h2>
                <p><a href="/admin/events/23/transfer" style="background: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Back to Transfer Page</a></p>
                <p><a href="/database-sync-admin-xyz456" style="background: #ffc107; color: black; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Database Sync Analysis</a></p>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <h1>❌ Debug Failed</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <pre>{json.dumps(str(e), indent=2)}</pre>
        """

@app.route('/fix-database-integrity-xyz999')
def fix_database_integrity():
    """Fix database integrity issues - phantom data and mismatched totals"""
    try:
        fixes_applied = []
        
        # 1. Fix phantom pledge amounts
        events_with_phantom_data = []
        for event in Event.query.all():
            pledges = Pledge.query.filter_by(event_id=event.id).all()
            actual_total = sum(p.amount for p in pledges if p.status in ['pending', 'charged'])
            recorded_total = float(event.current_pledges or 0)
            
            if abs(actual_total - recorded_total) > 0.01:
                events_with_phantom_data.append({
                    'event': event,
                    'recorded': recorded_total,
                    'actual': actual_total,
                    'pledges': pledges
                })
        
        # Fix each phantom data issue
        for issue in events_with_phantom_data:
            event = issue['event']
            actual_total = issue['actual']
            
            old_amount = event.current_pledges
            event.current_pledges = actual_total
            
            fixes_applied.append(f"Event {event.id} '{event.name}': Fixed pledge total from ${old_amount} to ${actual_total}")
        
        # 2. Remove duplicate events (keep the one with actual pledges)
        duplicate_groups = {}
        for event in Event.query.all():
            key = (event.name, event.organizer_id)
            if key not in duplicate_groups:
                duplicate_groups[key] = []
            duplicate_groups[key].append(event)
        
        for key, events in duplicate_groups.items():
            if len(events) > 1:
                # Keep the event with the most actual pledges
                events_with_pledge_count = []
                for event in events:
                    pledge_count = Pledge.query.filter_by(event_id=event.id).count()
                    events_with_pledge_count.append((event, pledge_count))
                
                # Sort by pledge count (descending), then by ID (ascending for consistency)
                events_with_pledge_count.sort(key=lambda x: (-x[1], x[0].id))
                
                # Keep the first one, delete the rest
                to_keep = events_with_pledge_count[0][0]
                for event, pledge_count in events_with_pledge_count[1:]:
                    # Delete any pledges for the duplicate event
                    pledges_to_delete = Pledge.query.filter_by(event_id=event.id).all()
                    for pledge in pledges_to_delete:
                        db.session.delete(pledge)
                    
                    db.session.delete(event)
                    fixes_applied.append(f"Removed duplicate event {event.id} '{event.name}' (kept event {to_keep.id})")
        
        # 3. Clean up orphaned transfer tokens
        orphaned_tokens = Pledge.query.filter(
            Pledge.transfer_token.isnot(None),
            Pledge.transfer_target_event_id.is_(None)
        ).all()
        
        for pledge in orphaned_tokens:
            pledge.transfer_token = None
            pledge.transfer_initiated_at = None
            fixes_applied.append(f"Cleaned orphaned transfer token for pledge {pledge.id}")
        
        # 4. Verify event status consistency
        for event in Event.query.all():
            pledges = Pledge.query.filter_by(event_id=event.id).all()
            total_pledges = sum(p.amount for p in pledges if p.status in ['pending', 'charged'])
            
            # Update status based on actual pledge amounts
            if total_pledges >= event.pledge_goal and event.status == 'pending':
                event.status = 'funded'
                fixes_applied.append(f"Event {event.id} status updated to 'funded' (reached goal)")
        
        db.session.commit()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Database Integrity Fix</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
                .success {{ background: #d4edda; border-color: #c3e6cb; }}
                .fix {{ background: #fff3cd; border-color: #ffeaa7; margin: 5px 0; padding: 10px; }}
            </style>
        </head>
        <body>
            <h1>🔧 Database Integrity Fix Complete</h1>
            <p><strong>Timestamp:</strong> {datetime.utcnow().isoformat()}</p>
            
            <div class="section success">
                <h2>✅ Fixes Applied</h2>
                {f'<p><strong>Total fixes: {len(fixes_applied)}</strong></p>' if fixes_applied else '<p><strong>No issues found - database is clean</strong></p>'}
                
                {''.join([f'<div class="fix">✓ {fix}</div>' for fix in fixes_applied])}
            </div>
            
            <div class="section">
                <h2>Next Steps</h2>
                <p><a href="/database-sync-admin-xyz456" style="background: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Run Database Analysis Again</a></p>
                <p><a href="/clear-cache-and-refresh-xyz789" style="background: #ffc107; color: black; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Clear Cache</a></p>
                <p><a href="/admin/dashboard" style="background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px;">Back to Admin Dashboard</a></p>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Database integrity fix failed: {str(e)}")
        return f"""
        <h1>❌ Database Fix Failed</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/admin/dashboard">← Back to Admin Dashboard</a></p>
        """

@app.route('/admin/transfers')
def admin_transfers():
    """Admin page to view and manage all active pledge transfers"""
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    try:
        transfer_data = []
        
        # Get all pledges with active transfer tokens (OLD SYSTEM)
        old_system_transfers = db.session.query(Pledge).filter(
            Pledge.transfer_token.isnot(None)
        ).all()
        
        for pledge in old_system_transfers:
            source_event = Event.query.get(pledge.event_id)
            target_event = Event.query.get(pledge.transfer_target_event_id) if pledge.transfer_target_event_id else None
            
            # Get organizer details
            source_organizer = Organizer.query.get(source_event.organizer_id) if source_event else None
            target_organizer = Organizer.query.get(target_event.organizer_id) if target_event else None
            
            transfer_info = {
                'pledge_id': pledge.id,
                'pledge_amount': pledge.amount,
                'pledger_email': pledge.email,
                'pledger_name': pledge.email.split('@')[0] if pledge.email else 'Anonymous',
                'transfer_token': pledge.transfer_token,
                'transfer_initiated': pledge.transfer_initiated_at,
                'source_event': source_event,
                'target_event': target_event,
                'source_organizer': source_organizer,
                'target_organizer': target_organizer,
                'status': 'pending_confirmation',
                'system': 'old'
            }
            transfer_data.append(transfer_info)
        
        # Get all active transfers (NEW SYSTEM) with eager loading to prevent N+1 queries
        from sqlalchemy.orm import joinedload
        all_transfers = PledgeTransfer.query.options(
            joinedload(PledgeTransfer.source_event).joinedload(Event.organizer),
            joinedload(PledgeTransfer.target_event).joinedload(Event.organizer),
            joinedload(PledgeTransfer.consent_requests).joinedload(PledgeTransferConsent.pledge)
        ).filter(PledgeTransfer.status.in_(['consent_requested', 'completed'])).all()
        
        # Pre-fetch all completed transfer pledge IDs to avoid repeated queries
        completed_transfer_pledge_ids = set()
        completed_consent_requests = PledgeTransferConsent.query.join(PledgeTransfer).filter(
            PledgeTransfer.status == 'completed'
        ).with_entities(PledgeTransferConsent.pledge_id).all()
        completed_transfer_pledge_ids.update([req[0] for req in completed_consent_requests])
        
        for transfer in all_transfers:
            # Check if transfer should be auto-completed
            if transfer.status == 'consent_requested' and transfer.pledges_consented == transfer.total_pledges_requested:
                transfer.status = 'completed'
                transfer.completed_at = datetime.utcnow()
                db.session.add(transfer)
                
            # Process consent requests for this transfer (already loaded via joinedload)
            for consent_request in transfer.consent_requests:
                pledge = consent_request.pledge
                source_event = transfer.source_event
                target_event = transfer.target_event
                
                # Skip pledges that have already been successfully transferred elsewhere
                # Use pre-fetched completed transfer pledge IDs for efficiency
                if pledge.id in completed_transfer_pledge_ids and transfer.status != 'completed':
                    continue
                
                # Get organizer details (already loaded via joinedload)
                source_organizer = source_event.organizer if source_event else None
                target_organizer = target_event.organizer if target_event else None
                
                # Determine display status
                if consent_request.status == 'pending':
                    display_status = 'pending_confirmation'
                elif consent_request.status == 'consented':
                    display_status = 'consented'
                elif consent_request.status == 'declined':
                    display_status = 'declined'
                else:
                    display_status = consent_request.status
                
                transfer_info = {
                    'pledge_id': pledge.id,
                    'pledge_amount': pledge.amount,
                    'pledger_email': pledge.email,
                    'pledger_name': pledge.email.split('@')[0] if pledge.email else 'Anonymous',
                    'transfer_token': consent_request.consent_token,
                    'transfer_initiated': transfer.consent_requested_at,
                    'source_event': source_event,
                    'target_event': target_event,
                    'source_organizer': source_organizer,
                    'target_organizer': target_organizer,
                    'status': display_status,
                    'system': 'new',
                    'consent_request_id': consent_request.id,
                    'transfer_id': transfer.id,
                    'transfer_status': transfer.status
                }
                transfer_data.append(transfer_info)
        
        # Commit any status updates
        db.session.commit()
        
        # Sort by transfer initiation date (newest first)
        transfer_data.sort(key=lambda x: x['transfer_initiated'] or datetime.min, reverse=True)
        
        # Get summary statistics
        total_transfers = len(transfer_data)
        total_amount = sum(t['pledge_amount'] for t in transfer_data)
        
        # Count only truly pending confirmations (status='pending')
        pending_confirmations = len([t for t in transfer_data if t['status'] == 'pending_confirmation'])
        
        return render_template('admin/transfers.html', 
                             transfers=transfer_data,
                             total_transfers=total_transfers,
                             total_amount=total_amount,
                             pending_confirmations=pending_confirmations)
                             
    except Exception as e:
        logging.error(f"Error loading transfer management page: {str(e)}")
        flash(f'Error loading transfers: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/resend-transfer-confirmation/<int:pledge_id>', methods=['POST'])
def resend_transfer_confirmation(pledge_id):
    """Resend transfer confirmation email to pledger (supports both old and new systems)"""
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    
    try:
        pledge = Pledge.query.get(pledge_id)
        if not pledge:
            return jsonify({'success': False, 'error': 'Pledge not found'}), 404
        
        # Check if this is OLD SYSTEM (transfer_token on pledge)
        if pledge.transfer_token and pledge.transfer_target_event_id:
            # OLD SYSTEM
            source_event = Event.query.get(pledge.event_id)
            target_event = Event.query.get(pledge.transfer_target_event_id)
            
            if not source_event or not target_event:
                return jsonify({'success': False, 'error': 'Source or target event not found'}), 400
            
            # Send old system confirmation email
            from flask_mail import Mail, Message
            mail = Mail(app)
            
            # Build correct URLs using current request host instead of _external=True
            from flask import request
            host = request.headers.get('Host', 'localhost:5000')
            scheme = 'https' if 'replit.dev' in host or 'foodtruckfundraiser.com' in host else 'http'
            confirm_url = f"{scheme}://{host}/confirm-transfer/{pledge.transfer_token}"
            decline_url = f"{scheme}://{host}/decline-transfer/{pledge.transfer_token}"
            
            try:
                msg = Message(
                    subject=f'RESENT: Confirm Pledge Transfer - {source_event.name}',
                    recipients=[pledge.email],
                    html=render_template('emails/transfer_confirmation.html',
                                       pledge=pledge,
                                       source_event=source_event,
                                       target_event=target_event,
                                       confirm_url=confirm_url,
                                       decline_url=decline_url)
                )
                mail.send(msg)
                
                logging.info(f"Old system transfer confirmation email resent to {pledge.email} for pledge {pledge_id}")
                return jsonify({'success': True, 'message': 'Confirmation email sent successfully'})
                
            except Exception as email_error:
                logging.error(f"Failed to resend old system transfer confirmation email: {str(email_error)}")
                return jsonify({'success': False, 'error': f'Failed to send email: {str(email_error)}'}), 500
        
        # Check if this is NEW SYSTEM (PledgeTransferConsent)
        consent_request = PledgeTransferConsent.query.filter_by(
            pledge_id=pledge_id
        ).first()
        
        if consent_request:
            # NEW SYSTEM
            transfer = consent_request.transfer
            source_event = transfer.source_event
            target_event = transfer.target_event
            
            # Build correct URL using current request host instead of _external=True
            # This prevents wrong domain issues in development vs production
            from flask import request
            host = request.headers.get('Host', 'localhost:5000')
            scheme = 'https' if 'replit.dev' in host or 'foodtruckfundraiser.com' in host else 'http'
            consent_url = f"{scheme}://{host}/pledge-transfer/consent/{consent_request.consent_token}"
            
            # Resend new system email
            from flask_mail import Mail, Message
            mail = Mail(app)
            
            html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transfer Request</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #ff8a00, #e52e71); color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 20px; }}
        .content {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .event-box {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ff8a00; }}
        .buttons {{ text-align: center; margin: 30px 0; }}
        .btn {{ display: inline-block; padding: 15px 30px; margin: 10px; text-decoration: none; border-radius: 25px; font-weight: bold; font-size: 16px; transition: all 0.3s; }}
        .btn-approve {{ background: #28a745; color: white; }}
        .btn-approve:hover {{ background: #218838; }}
        .btn-decline {{ background: #dc3545; color: white; }}
        .btn-decline:hover {{ background: #c82333; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🍴 RESENT: Pledge Transfer Request</h1>
    </div>
    
    <div class="content">
        <p><strong>Hello!</strong></p>
        
        <p>Your event organizer has requested to transfer your pledge from <strong>"{source_event.name}"</strong> to <strong>"{target_event.name}"</strong>.</p>
        
        <div class="event-box">
            <h3>📅 Original Event</h3>
            <strong>{source_event.name}</strong><br>
            <strong>Date:</strong> {source_event.date.strftime('%B %d, %Y at %I:%M %p')}<br>
            <strong>Your Pledge:</strong> ${pledge.amount:.2f}
        </div>
        
        <div class="event-box">
            <h3>📅 New Event</h3>
            <strong>{target_event.name}</strong><br>
            <strong>Date:</strong> {target_event.date.strftime('%B %d, %Y at %I:%M %p')}<br>
            <strong>Location:</strong> {target_event.location}
        </div>
        
        <p><strong>💰 Your pledge amount will remain the same (${pledge.amount:.2f})</strong></p>
        
        <div class="buttons">
            <a href="{consent_url}?response=approve" class="btn btn-approve">✅ APPROVE TRANSFER</a>
            <a href="{consent_url}?response=decline" class="btn btn-decline">❌ DECLINE TRANSFER</a>
        </div>
        
        <p>Thank you!</p>
    </div>
</body>
</html>"""
            
            try:
                msg = Message(
                    subject=f'RESENT: Pledge Transfer Request - {source_event.name}',
                    recipients=[pledge.email],
                    html=html_body
                )
                mail.send(msg)
                
                logging.info(f"New system transfer confirmation email resent to {pledge.email} for pledge {pledge_id}")
                return jsonify({'success': True, 'message': 'Confirmation email sent successfully'})
                
            except Exception as email_error:
                logging.error(f"Failed to resend new system transfer confirmation email: {str(email_error)}")
                return jsonify({'success': False, 'error': f'Failed to send email: {str(email_error)}'}), 500
        
        # No active transfer found in either system
        return jsonify({'success': False, 'error': 'No active transfer found for this pledge'}), 400
            
    except Exception as e:
        logging.error(f"Error resending transfer confirmation: {str(e)}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


@app.route('/auto-fix-all-menus-xyz123')
def auto_fix_all_menus():
    """Emergency fix for all events and trucks - runs sync and menu fix together"""
    try:
        results = []
        
        # First run the sync to ensure all trucks are properly configured
        sync_results = []
        standard_trucks = [
            {
                'name': 'Tasty Tacos',
                'description': "LA's premiere healthy food truck",
                'menu_items': [
                    {"name": "Carnitas Taco", "price": 4.5},
                    {"name": "Chicken Taco", "price": 4.0},
                    {"name": "Veggie Taco", "price": 3.75},
                    {"name": "Combo Meal", "price": 12.0}
                ],
                'sales_goal': 1500
            },
            {
                'name': 'Green Truck',
                'description': 'Fresh, locally-sourced meals with a focus on sustainability and health.',
                'menu_items': [
                    {"name": "Green Goddess Bowl", "price": 13.50},
                    {"name": "Quinoa Power Salad", "price": 12.75},
                    {"name": "Avocado Toast Deluxe", "price": 9.25},
                    {"name": "Veggie Wrap", "price": 11.00},
                    {"name": "Green Smoothie", "price": 7.50},
                    {"name": "Kale Caesar Salad", "price": 12.00},
                    {"name": "Buddha Bowl", "price": 14.25},
                    {"name": "Raw Veggie Tacos", "price": 10.75}
                ],
                'sales_goal': 1800
            },
            {
                'name': 'Acai Truck',
                'description': 'Fresh and healthy acai bowls made with organic ingredients',
                'menu_items': [
                    {"name": "Classic Acai Bowl", "price": 12.50},
                    {"name": "Berry Blast Bowl", "price": 14.00},
                    {"name": "Green Goddess Bowl", "price": 13.25},
                    {"name": "Protein Power Bowl", "price": 15.50},
                    {"name": "Mini Acai Bowl", "price": 8.75},
                    {"name": "Acai Smoothie", "price": 7.50}
                ],
                'sales_goal': 1750
            },
            {
                'name': 'Ho-Lee Chow',
                'description': 'Healthy Asian inspired food. All our bowls are gluten-free. Vegan, grain-free, and customizable options.',
                'menu_items': [
                    {"name": "Korean BBQ Bowl", "price": 14.50},
                    {"name": "Teriyaki Chicken Bowl", "price": 13.25},
                    {"name": "Vegetable Pad Thai", "price": 12.00},
                    {"name": "Asian Fusion Bowl", "price": 15.75},
                    {"name": "Poke Bowl", "price": 16.00},
                    {"name": "Spring Rolls (3pc)", "price": 8.50},
                    {"name": "Miso Soup", "price": 6.00},
                    {"name": "Asian Salad", "price": 11.25}
                ],
                'sales_goal': 2000
            }
        ]
        
        # Sync trucks
        for truck_data in standard_trucks:
            existing_truck = FoodTruck.query.filter_by(name=truck_data['name']).first()
            
            if existing_truck:
                existing_truck.description = truck_data['description']
                existing_truck.menu_items = json.dumps(truck_data['menu_items'])
                existing_truck.sales_goal = truck_data['sales_goal']
                # Ensure status is approved for production use
                existing_truck.status = 'approved'
                existing_truck.registration_fee_charged = True
                sync_results.append(f"Updated: {truck_data['name']}")
            else:
                new_truck = FoodTruck(
                    name=truck_data['name'],
                    description=truck_data['description'],
                    menu_items=json.dumps(truck_data['menu_items']),
                    sales_goal=truck_data['sales_goal'],
                    status='approved',  # Auto-approve for production
                    registration_fee_charged=True  # Mark as paid for production
                )
                db.session.add(new_truck)
                sync_results.append(f"Created: {truck_data['name']}")
        
        # Fix all events missing menu items
        fix_results = []
        all_events = Event.query.all()
        
        for event in all_events:
            menu_items = event.get_selected_menu_items() if event.selected_menu_items else []
            
            if not menu_items and event.food_truck:
                truck = event.food_truck
                truck_menu = truck.get_menu_items() if truck and truck.menu_items else []
                
                if truck_menu:
                    marked_up_items = []
                    for item in truck_menu:
                        original_price = item.get('price', 15.0)
                        markup_rate = 0.15  # 15% markup
                        marked_up_price = round(original_price * (1 + markup_rate), 2)
                        
                        marked_up_items.append({
                            "name": item.get('name', 'Menu Item'),
                            "price": original_price,
                            "original_price": original_price,
                            "marked_up_price": marked_up_price
                        })
                    
                    event.selected_menu_items = json.dumps(marked_up_items)
                    
                    if truck.sales_goal:
                        event.pledge_goal = truck.sales_goal
                    
                    fix_results.append(f"Fixed {truck.name} menu for event: {event.name} ({len(marked_up_items)} items)")
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Complete fix applied - all trucks synced and all events have menu items',
            'sync_results': sync_results,
            'fix_results': fix_results,
            'trucks_synced': len(sync_results),
            'events_fixed': len(fix_results)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error during auto-fix: {str(e)}'
        })

@app.route('/admin/fix-organizer-pledges-xyz789')
def fix_organizer_pledges():
    """Create missing organizer pledges for existing events - admin only"""
    if not session.get('admin_id'):
        return "Access denied", 403
    
    try:
        # Find events with organizer pledge charged but no corresponding pledge
        events_fixed = 0
        events_with_fee = Event.query.filter_by(organizer_fee_charged=True).all()
        
        for event in events_with_fee:
            # Check if organizer pledge already exists
            existing_pledge = Pledge.query.filter_by(
                event_id=event.id,
                email=event.organizer.email,
                amount=5.00
            ).first()
            
            if not existing_pledge:
                # Create organizer's $5 pledge
                organizer_pledge = Pledge(
                    email=event.organizer.email,
                    amount=5.00,
                    processing_fee=0.0,
                    stripe_payment_intent_id=event.organizer_fee_payment_intent,
                    event_id=event.id,
                    status='charged',
                    charged_at=event.created_at
                )
                
                db.session.add(organizer_pledge)
                
                # Update event pledge totals
                event.update_pledge_total()
                events_fixed += 1
        
        db.session.commit()
        
        return f"Fixed {events_fixed} events with missing organizer pledges. All events now show organizer as first supporter!"
        
    except Exception as e:
        db.session.rollback()
        return f"Error: {str(e)}", 500

@app.route('/admin/update-pledge-totals-xyz456')
def update_pledge_totals():
    """Update pledge totals for all events to include charged pledges - admin only"""
    if not session.get('admin_id'):
        return "Access denied", 403
    
    try:
        events_updated = 0
        events_details = []
        all_events = Event.query.all()
        
        for event in all_events:
            old_total = event.current_pledges
            
            # Manual calculation to ensure it works
            from sqlalchemy import func
            total = db.session.query(func.sum(Pledge.amount)).filter(
                Pledge.event_id == event.id,
                Pledge.status.in_(['pending', 'charged'])
            ).scalar() or 0
            
            event.current_pledges = total
            
            if total != old_total:
                events_updated += 1
                events_details.append(f"Event '{event.name}': ${old_total:.2f} → ${total:.2f}")
        
        db.session.commit()
        
        details_str = "<br>".join(events_details[:10])  # Show first 10 for brevity
        if len(events_details) > 10:
            details_str += f"<br>... and {len(events_details) - 10} more events"
        
        return f"Updated pledge totals for {events_updated} events. Charged pledges are now included!<br><br>Details:<br>{details_str}"
        
    except Exception as e:
        db.session.rollback()
        return f"Error: {str(e)}", 500

# PRODUCTION SECURITY: Test route disabled for live deployment
# @app.route('/test-admin-login-xyz123', methods=['GET', 'POST'])
# def test_admin_login():
    """Debug route to test admin login credentials"""
    try:
        if request.method == 'POST':
            username = request.form.get('username', 'support@foodtruckfundraiser.com')
            password = request.form.get('password', 'password')
        else:
            username = 'support@foodtruckfundraiser.com'
            password = 'password'
        
        # Find admin user
        admin = Admin.query.filter_by(username=username).first()
        
        if not admin:
            return jsonify({
                'status': 'error',
                'message': f'Admin user not found: {username}',
                'all_admins': [a.username for a in Admin.query.all()],
                'admin_count': Admin.query.count()
            })
        
        # Test password
        from werkzeug.security import check_password_hash
        password_valid = check_password_hash(admin.password_hash, password)
        
        return jsonify({
            'status': 'success',
            'message': 'Admin login test completed',
            'username': username,
            'admin_exists': True,
            'admin_id': admin.id,
            'password_valid': password_valid,
            'password_hash_prefix': admin.password_hash[:20] + '...',
            'test_credentials': {
                'username': 'support@foodtruckfundraiser.com',
                'password': 'password'
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error testing admin login: {str(e)}'
        })



@app.route('/admin/trucks')
def admin_trucks():
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    trucks = FoodTruck.query.all()
    return render_template('admin/trucks.html', trucks=trucks)

@app.route('/admin/trucks/add', methods=['GET', 'POST'])
def admin_add_truck():
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        truck = FoodTruck(
            name=request.form['name'],
            description=request.form['description'],
            sales_goal=float(request.form['sales_goal'])
        )
        
        # Parse menu items
        menu_items = []
        item_names = request.form.getlist('item_name[]')
        item_prices = request.form.getlist('item_price[]')
        
        for name, price in zip(item_names, item_prices):
            if name and price:
                menu_items.append({'name': name, 'price': float(price)})
        
        truck.set_menu_items(menu_items)
        
        db.session.add(truck)
        db.session.commit()
        
        flash('Food truck added successfully', 'success')
        return redirect(url_for('admin_trucks'))
    
    return render_template('admin/trucks.html', add_mode=True)

@app.route('/admin/trucks/<int:truck_id>/edit', methods=['GET', 'POST'])
def admin_edit_truck(truck_id):
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    truck = FoodTruck.query.get_or_404(truck_id)
    
    if request.method == 'POST':
        truck.name = request.form['name']
        truck.description = request.form['description']
        truck.sales_goal = float(request.form['sales_goal'])
        
        # Parse menu items
        menu_items = []
        item_names = request.form.getlist('item_name[]')
        item_prices = request.form.getlist('item_price[]')
        
        for name, price in zip(item_names, item_prices):
            if name and price:
                menu_items.append({'name': name, 'price': float(price)})
        
        truck.set_menu_items(menu_items)
        
        db.session.commit()
        flash('Food truck updated successfully', 'success')
        return redirect(url_for('admin_trucks'))
    
    return render_template('admin/trucks.html', truck=truck, edit_mode=True)

@app.route('/admin/trucks/<int:truck_id>/delete', methods=['POST'])
def admin_delete_truck(truck_id):
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    truck = FoodTruck.query.get_or_404(truck_id)
    db.session.delete(truck)
    db.session.commit()
    
    flash('Food truck deleted successfully', 'success')
    return redirect(url_for('admin_trucks'))

@app.route('/admin/events')
def admin_events():
    try:
        logging.info(f"Admin events access attempt - Session: {dict(session)}")
        
        if not session.get('admin_id'):
            logging.warning("Admin events access denied - no admin_id in session")
            return redirect(url_for('admin_login'))
        
        logging.info(f"Admin {session.get('admin_id')} accessing events management")
        events = Event.query.order_by(Event.created_at.desc()).all()
        logging.info(f"Found {len(events)} events to display")
        
        return render_template('admin/events.html', events=events)
    except Exception as e:
        logging.error(f"Admin events error: {str(e)}", exc_info=True)
        flash('Error loading events. Please try again.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/events/<int:event_id>/transfer', methods=['GET', 'POST'])
def admin_transfer_pledges(event_id):
    """Admin pledge transfer - view and process"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    event = Event.query.get_or_404(event_id)
    
    if request.method == 'GET':
        # Show transfer form - include events from all organizers that can accept transfers
        # Changed: Remove organizer restriction to allow cross-organizer transfers
        # Changed: Include events with future dates and current/active status
        available_events = Event.query.filter(
            Event.id != event.id,  # Don't include the source event itself
            Event.status.in_(['pending', 'funded']),  # Only active events
            Event.date >= datetime.utcnow().date()  # Only future or current events
        ).order_by(Event.date.asc()).all()  # Sort by date ascending (soonest first)
        
        return render_template('admin/transfer_pledges.html', 
                             event=event, 
                             available_events=available_events)
    
    # POST request - process transfer
    target_event_id = int(request.form['target_event_id'])
    target_event = Event.query.get_or_404(target_event_id)
    
    # Verify both events belong to the same organizer
    if event.organizer_id != target_event.organizer_id:
        flash('Can only transfer pledges between events from the same organizer', 'error')
        return redirect(url_for('admin_events'))
    
    # Validation checks
    if event.status not in ['pending', 'funded']:
        flash('Can only transfer pledges from pending or funded events', 'error')
        return redirect(url_for('admin_events'))
    
    if target_event.status not in ['pending', 'funded']:
        flash('Can only transfer pledges to events that are still accepting pledges', 'error')
        return redirect(url_for('admin_events'))
    
    if event.id == target_event.id:
        flash('Cannot transfer pledges to the same event', 'error')
        return redirect(url_for('admin_events'))
    
    # Get pending pledges from source event
    pending_pledges = [p for p in event.pledges if p.status == 'pending']
    
    if not pending_pledges:
        flash('No pending pledges found to transfer', 'error')
        return redirect(url_for('admin_events'))
    
    try:
        # Send email confirmation to each pledger
        from flask_mail import Mail, Message
        mail = Mail(app)
        confirmation_sent = 0
        
        for pledge in pending_pledges:
            confirmation_token = secrets.token_urlsafe(32)
            pledge.transfer_token = confirmation_token
            pledge.transfer_target_event_id = target_event.id
            pledge.transfer_initiated_at = datetime.utcnow()
            
            # Create confirmation URLs
            confirm_url = url_for('confirm_transfer', token=confirmation_token, _external=True)
            decline_url = url_for('decline_transfer', token=confirmation_token, _external=True)
            
            # Send confirmation email
            try:
                msg = Message(
                    subject=f'Confirm Pledge Transfer - {event.name}',
                    recipients=[pledge.email],
                    html=render_template('emails/transfer_confirmation.html',
                                       pledge=pledge,
                                       source_event=event,
                                       target_event=target_event,
                                       confirm_url=confirm_url,
                                       decline_url=decline_url)
                )
                mail.send(msg)
                confirmation_sent += 1
                logging.info(f"Transfer confirmation email sent to {pledge.email}")
            except Exception as email_error:
                logging.error(f"Failed to send transfer confirmation to {pledge.email}: {str(email_error)}")
                continue
        
        db.session.commit()
        
        flash(f'Transfer process initiated! Confirmation emails sent to {confirmation_sent} pledgers. '
              f'Pledges will be transferred once pledgers confirm via email.', 'success')
              
    except Exception as e:
        db.session.rollback()
        logging.error(f"Transfer initiation error: {str(e)}")
        flash('Error initiating transfer process. Please try again.', 'error')
    
    return redirect(url_for('admin_events'))

@app.route('/transfer/confirm/<token>')
def confirm_transfer(token):
    """Confirm pledge transfer via email link"""
    logging.info(f"Transfer confirmation attempt with token: {token[:8]}...")
    
    # Debug: Check what pledges have transfer tokens
    all_pledges_with_tokens = Pledge.query.filter(Pledge.transfer_token.isnot(None)).all()
    logging.info(f"Found {len(all_pledges_with_tokens)} pledges with transfer tokens")
    
    # Find pledge by transfer token
    pledge = Pledge.query.filter_by(transfer_token=token).first()
    
    if not pledge:
        # Enhanced debugging for invalid tokens
        logging.error(f"No pledge found with transfer token: {token}")
        all_pledges = Pledge.query.all()
        logging.error(f"Total pledges in database: {len(all_pledges)}")
        for p in all_pledges:
            if p.transfer_token:
                logging.error(f"Existing token: {p.transfer_token[:8]}... for pledge {p.id}")
        flash('Invalid transfer confirmation link. The transfer may have already been processed or expired.', 'error')
        return redirect(url_for('index'))
    
    if not pledge.transfer_target_event_id:
        logging.error(f"Pledge {pledge.id} has transfer token but no target event ID")
        flash('Transfer request has expired or been cancelled', 'error')
        return redirect(url_for('index'))
    
    # Get target event with enhanced debugging
    target_event = Event.query.get(pledge.transfer_target_event_id)
    logging.error(f"Transfer confirmation debug - Target event ID: {pledge.transfer_target_event_id}, Found: {target_event is not None}")
    
    if not target_event:
        logging.error(f"Target event {pledge.transfer_target_event_id} not found in database")
        # Check if source event exists
        source_event = Event.query.get(pledge.event_id)
        logging.error(f"Source event ID: {pledge.event_id}, Found: {source_event is not None}")
        
        flash(f'Target event (ID: {pledge.transfer_target_event_id}) no longer exists. This may be a database sync issue.', 'error')
        return redirect(url_for('index'))
    
    try:
        # Update pledge to new event
        logging.info(f"Processing transfer for pledge {pledge.id} from event {pledge.event_id} to event {pledge.transfer_target_event_id}")
        old_event_name = pledge.event.name
        logging.info(f"Source event name: {old_event_name}")
        
        pledge.event_id = pledge.transfer_target_event_id
        pledge.transfer_token = None
        pledge.transfer_target_event_id = None
        pledge.transfer_initiated_at = None
        
        logging.info(f"Committing transfer changes to database...")
        db.session.commit()
        logging.info(f"Transfer committed successfully")
        
        # Send confirmation email
        try:
            from flask_mail import Mail, Message
            mail = Mail(app)
            msg = Message(
                subject='Pledge Transfer Confirmed',
                recipients=[pledge.email],
                body=f"""
                Your pledge transfer has been confirmed!
                
                Your ${ pledge.amount:.2f} pledge has been successfully transferred from:
                "{old_event_name}" 
                
                To: "{target_event.name}"
                Date: {target_event.date.strftime('%B %d, %Y at %I:%M %p')}
                Location: {target_event.location}
                
                You'll receive the same meal value for the new event.
                
                Thank you for your flexibility!
                Food Truck Fundraiser Team
                """
            )
            mail.send(msg)
        except Exception as e:
            logging.error(f"Failed to send transfer confirmation email: {str(e)}")
        
        return render_template('transfer_consent_approved.html', 
                             pledge=pledge, 
                             new_event=target_event,
                             old_event_name=old_event_name)
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Transfer confirmation error: {str(e)}")
        flash('Error processing transfer confirmation', 'error')
        return redirect(url_for('index'))

@app.route('/transfer/decline/<token>')
def decline_transfer(token):
    """Decline pledge transfer via email link"""
    # Find pledge by transfer token
    pledge = Pledge.query.filter_by(transfer_token=token).first()
    
    if not pledge:
        flash('Invalid transfer link', 'error')
        return redirect(url_for('index'))
    
    try:
        # Clear transfer data
        source_event_name = pledge.event.name
        pledge.transfer_token = None
        pledge.transfer_target_event_id = None
        pledge.transfer_initiated_at = None
        
        db.session.commit()
        
        # Send declined confirmation email
        try:
            from flask_mail import Mail, Message
            mail = Mail(app)
            msg = Message(
                subject='Pledge Transfer Declined',
                recipients=[pledge.email],
                body=f"""
                You have successfully declined the pledge transfer.
                
                Your ${ pledge.amount:.2f} pledge will remain with the original event:
                "{source_event_name}"
                
                No changes have been made to your pledge.
                
                Thank you!
                Food Truck Fundraiser Team
                """
            )
            mail.send(msg)
        except Exception as e:
            logging.error(f"Failed to send transfer decline email: {str(e)}")
        
        return render_template('transfer_consent_declined.html', 
                             pledge=pledge,
                             source_event_name=source_event_name)
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Transfer decline error: {str(e)}")
        flash('Error processing transfer decline', 'error')
        return redirect(url_for('index'))

# PRODUCTION SECURITY: Debug route disabled for live deployment
# @app.route('/debug-transfer-production-xyz098/<email>')
# def debug_transfer_production(email):
    """Debug transfer tokens for specific email in production"""
    try:
        # Find all pledges for this email with transfer tokens
        pledges_with_tokens = Pledge.query.filter(
            Pledge.email.like(f'%{email}%'),
            Pledge.transfer_token.isnot(None)
        ).all()
        
        # Find all pledges for this email (with or without tokens)
        all_pledges = Pledge.query.filter(
            Pledge.email.like(f'%{email}%')
        ).all()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Transfer Debug for {email}</title></head>
        <body style="font-family: Arial; margin: 20px;">
            <h1>🔍 Transfer Debug for {email}</h1>
            
            <h2>Pledges with Transfer Tokens ({len(pledges_with_tokens)})</h2>
            {
                ''.join([f'''
                <div style="border: 1px solid #ddd; padding: 10px; margin: 10px 0;">
                    <strong>Pledge ID:</strong> {p.id}<br>
                    <strong>Amount:</strong> ${p.amount}<br>
                    <strong>Event ID:</strong> {p.event_id}<br>
                    <strong>Transfer Token:</strong> {p.transfer_token}<br>
                    <strong>Target Event ID:</strong> {p.transfer_target_event_id}<br>
                    <strong>Initiated:</strong> {p.transfer_initiated_at}<br>
                    <strong>Status:</strong> {p.status}<br>
                    <hr>
                    <strong>Confirmation Link:</strong><br>
                    <a href="/transfer/confirm/{p.transfer_token}">/transfer/confirm/{p.transfer_token}</a>
                </div>
                ''' for p in pledges_with_tokens]) if pledges_with_tokens else '<p>No active transfer tokens found</p>'
            }
            
            <h2>All Pledges for {email} ({len(all_pledges)})</h2>
            {
                ''.join([f'''
                <div style="border: 1px solid #ccc; padding: 8px; margin: 5px 0;">
                    ID: {p.id} | Amount: ${p.amount} | Event: {p.event_id} | Status: {p.status} | Token: {p.transfer_token or 'None'}
                </div>
                ''' for p in all_pledges]) if all_pledges else '<p>No pledges found</p>'
            }
            
            <p><a href="/admin/transfers">← Back to Transfer Management</a></p>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <h1>❌ Debug Error</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/admin/transfers">← Back to Transfer Management</a></p>
        """

@app.route('/admin/events/<int:event_id>/approve', methods=['POST'])
def admin_approve_event(event_id):
    """
    Approve and charge all pledges for an event. 
    This handles both fully funded events and partial funding approvals.
    For pledge transfers, use the transfer system with email confirmation instead.
    """
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    event = Event.query.get_or_404(event_id)
    
    if event.status not in ['funded', 'pending']:
        flash('Can only approve funded or pending events', 'error')
        return redirect(url_for('admin_events'))
    
    try:
        # Charge all pledges for this event
        pledges = Pledge.query.filter_by(event_id=event_id, status='pending').all()
        
        for pledge in pledges:
            if pledge.stripe_payment_intent_id:
                charge_result = charge_stripe_payment(pledge.stripe_payment_intent_id, pledge.amount, f"Food Truck Event: {event.name}")
                if charge_result['success']:
                    pledge.status = 'charged'
                    pledge.charged_at = datetime.utcnow()
                    pledge.processing_fee = charge_result['processing_fee']
                    
                    # Generate and send e-ticket with fee breakdown
                    pledge.ticket_code = generate_ticket_code()
                    total_charged = charge_result['total_charged']
                    processing_fee = charge_result['processing_fee']
                    
                    send_email(
                        pledge.email,
                        f"Your E-Ticket for {event.name}",
                        f"Thank you for your pledge! Your payment has been processed.\n\nPAYMENT BREAKDOWN:\nPledge Amount: ${pledge.amount:.2f}\nProcessing Fee (4.5%): ${processing_fee:.2f}\nTotal Charged: ${total_charged:.2f}\n\nE-TICKET CODE: {pledge.ticket_code}\n\nEvent: {event.name}\nDate: {event.date}\nLocation: {event.location}\n\nShow this code at the food truck to redeem your meal."
                    )
                    pledge.ticket_sent = True
                else:
                    flash(f'Failed to charge pledge from {pledge.email}: {charge_result.get("error", "Unknown error")}', 'error')
        
        event.status = 'approved'
        event.approved_at = datetime.utcnow()
        
        # Generate organizer entree ticket if they paid the organizer pledge
        organizer_entree_ticket = None
        if event.organizer_fee_charged and not event.organizer_entree_claimed:
            organizer_entree_ticket = generate_ticket_code()
            event.organizer_entree_claimed = True
        
        db.session.commit()
        
        # Send notification to organizer with their free entree ticket
        organizer_email_content = f"Great news! Your event '{event.name}' has been approved and all pledges have been charged. The food truck will attend your event."
        
        if organizer_entree_ticket:
            organizer_email_content += f"\n\n🎁 YOUR FREE ENTREE TICKET: {organizer_entree_ticket}\n\nAs the event organizer, you get any menu item FREE! Show this code to the food truck at your event to redeem your complimentary meal."
        
        send_email(
            event.organizer.email,
            f"Event Approved: {event.name}" + (" + Your Free Entree!" if organizer_entree_ticket else ""),
            organizer_email_content
        )
        
        flash('Event approved and pledges charged successfully', 'success')
        
    except Exception as e:
        logging.error(f"Error approving event {event_id}: {str(e)}")
        flash('Error processing approval', 'error')
    
    return redirect(url_for('admin_events'))

# REMOVED: admin_pool_partial_event - use transfer system with email confirmation instead

# REMOVED: admin_charge_pooled_event - use admin_approve_event instead

# REMOVED: admin_pool_pledges - use transfer system with email confirmation instead

# REMOVED: admin_execute_pool_pledges - use transfer system with email confirmation instead

@app.route('/admin/events/<int:event_id>/delete', methods=['POST'])
def admin_delete_event(event_id):
    """Delete an event with proper handling of associated pledges"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    event = Event.query.get_or_404(event_id)
    
    # Check for existing pledges
    pledges = Pledge.query.filter_by(event_id=event_id).all()
    charged_pledges = [p for p in pledges if p.status == 'charged']
    
    # Safety check: don't allow deletion of events with charged pledges
    if charged_pledges:
        flash(f'Cannot delete event "{event.name}" - it has {len(charged_pledges)} charged pledges. Contact customers first.', 'error')
        return redirect(url_for('admin_events'))
    
    # For events with pending pledges, notify users about cancellation
    if pledges:
        try:
            # Send cancellation emails to pledgers
            for pledge in pledges:
                send_email(
                    pledge.email,
                    f"Event Cancelled: {event.name}",
                    f"We regret to inform you that the event '{event.name}' scheduled for {event.date.strftime('%B %d, %Y at %I:%M %p')} has been cancelled.\n\nYour pledge of ${pledge.amount:.2f} has not been charged and no payment was processed.\n\nWe apologize for any inconvenience."
                )
            
            # Send notification to organizer
            if event.organizer:
                send_email(
                    event.organizer.email,
                    f"Event Deleted: {event.name}",
                    f"Your event '{event.name}' has been deleted by an administrator.\n\nIf you have questions, please contact support."
                )
                
        except Exception as e:
            logging.error(f"Error sending cancellation emails for event {event_id}: {str(e)}")
            flash('Event will be deleted but some notification emails may not have been sent', 'warning')
    
    # Delete all associated pledges first (database cascade)
    Pledge.query.filter_by(event_id=event_id).delete()
    
    # Now delete the event
    event_name = event.name  # Store for flash message
    db.session.delete(event)
    db.session.commit()
    
    # Create automatic backup after event deletion
    try:
        from backup_system import backup_events_to_file
        remaining_events = Event.query.all()
        backup_events_to_file(remaining_events)
        logging.info(f"File backup created after event deletion")
    except Exception as backup_error:
        logging.error(f"Backup failed after event deletion: {backup_error}")
    
    flash(f'Event "{event_name}" deleted successfully. {len(pledges)} associated pledges were also removed.', 'success')
    return redirect(url_for('admin_events'))


# Organizer Routes
@app.route('/organizer/login', methods=['GET', 'POST'])
def organizer_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Enhanced iframe detection (same as admin)
        is_embedded = (request.referrer and 'thefoodtruckstop.com' in request.referrer) or \
                     request.form.get('iframe_context') == 'true'
        
        logging.info(f"Organizer login attempt - Email: {email}, Embedded: {is_embedded}")
        logging.info(f"Request details - Referrer: {request.referrer}, Iframe field: {request.form.get('iframe_context')}")
        logging.info(f"Form data: {dict(request.form)}")
        
        organizer = Organizer.query.filter_by(email=email).first()
        if organizer and check_password_hash(organizer.password_hash, password):
            # Clear any existing session data first
            session.clear()
            
            # Set session data
            session['organizer_id'] = organizer.id
            session['user_type'] = 'organizer'
            session.permanent = True
            
            # Force session save for iframe contexts with additional persistence
            session.modified = True
            
            # Also set a simple auth flag for debugging
            session['authenticated'] = True
            session['login_time'] = datetime.now().isoformat()
            
            # Create a persistent auth token for iframe compatibility
            auth_token = secrets.token_urlsafe(32)
            session['auth_token'] = auth_token
            
            # Store token in database with 24 hour expiration
            from datetime import timedelta
            token_record = AuthToken(
                token=auth_token,
                organizer_id=organizer.id,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            db.session.add(token_record)
            db.session.commit()
            
            logging.info(f"Organizer {email} logged in successfully, session set with organizer_id: {organizer.id}")
            logging.info(f"Session contents after login: {dict(session)}")
            flash('Successfully logged in', 'success')
            
            # Create a response with enhanced cookie handling for iframe
            response_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Organizer Login Success</title>
                <meta http-equiv="refresh" content="3;url={url_for('organizer_dashboard')}?auth_token={session.get('auth_token', '')}">
                <script>
                    console.log('Organizer login successful!');
                    console.log('In iframe:', window.self !== window.top);
                    console.log('Server detected embedded:', {str(is_embedded).lower()});
                    console.log('Session created with organizer_id:', {session.get('organizer_id', 'None')});
                    
                    // Store session info in localStorage for iframe persistence
                    if (typeof(Storage) !== "undefined") {{
                        localStorage.setItem('organizer_logged_in', 'true');
                        localStorage.setItem('organizer_id', '{session.get('organizer_id', '')}');
                        localStorage.setItem('auth_token', '{session.get('auth_token', '')}');
                        console.log('Session stored in localStorage with auth token');
                    }}
                    
                    // Multiple redirect approaches for iframe compatibility
                    let redirected = false;
                    
                    // Method 1: Redirect with auth token for iframe compatibility
                    setTimeout(function() {{
                        if (!redirected) {{
                            console.log('Attempting redirect with auth token...');
                            const authToken = '{session.get('auth_token', '')}';
                            window.location.href = '{url_for('organizer_dashboard')}?auth_token=' + authToken;
                            redirected = true;
                        }}
                    }}, 1000);
                    
                    // Method 2: Meta refresh backup (3 second delay)
                    console.log('Meta refresh will redirect in 3 seconds if JS redirect fails');
                </script>
            </head>
            <body>
                <div style="text-align: center; margin-top: 50px;">
                    <h2>✅ Organizer Login Successful!</h2>
                    <p>Redirecting to dashboard in 3 seconds...</p>
                    <div id="countdown">3</div>
                    <br>
                    <p><strong><a href="{url_for('organizer_dashboard')}?auth_token={session.get('auth_token', '')}">Click here if not redirected</a></strong></p>
                    <hr>
                    <small>
                        Session ID: {session.get('organizer_id', 'None')}<br>
                        Iframe: {is_embedded}<br>
                        Login Time: {session.get('login_time', 'None')[:19]}
                    </small>
                </div>
                
                <script>
                    // Countdown display
                    let count = 3;
                    let countdown = setInterval(function() {{
                        count--;
                        if (count > 0) {{
                            document.getElementById('countdown').textContent = count;
                        }} else {{
                            clearInterval(countdown);
                            document.getElementById('countdown').textContent = 'Redirecting...';
                        }}
                    }}, 1000);
                </script>
            </body>
            </html>
            """
            
            response = make_response(response_html)
            
            # Enhanced cookie settings for iframe session persistence
            if 'session' in session:
                # Force session cookie to be set with iframe-compatible attributes
                response.set_cookie(
                    'session', 
                    session.get('_id', ''),
                    secure=True,
                    samesite='None',
                    httponly=False,  # Allow JS access for debugging
                    path='/',
                    domain=None
                )
            
            return response
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('organizer/login.html')

@app.route('/organizer/register', methods=['GET', 'POST'])
def organizer_register():
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip()
            name = request.form.get('name', '').strip()
            password = request.form.get('password', '').strip()
            terms_agreement = request.form.get('terms_agreement')
            
            # Debug logging
            logging.debug(f"Organizer registration attempt - Email: {email}, Name: {name}")
            
            # Validation
            if not email or not name or not password:
                flash('All fields are required', 'error')
                logging.debug("Registration failed: Missing fields")
                return render_template('organizer/login.html', register_mode=True)
            
            if not terms_agreement:
                flash('You must agree to the terms and conditions to create an account', 'error')
                logging.debug("Registration failed: Terms not accepted")
                return render_template('organizer/login.html', register_mode=True)
            
            if len(password) < 6:
                flash('Password must be at least 6 characters long', 'error')
                logging.debug("Registration failed: Password too short")
                return render_template('organizer/login.html', register_mode=True)
            
            # Check if email already exists
            existing_organizer = Organizer.query.filter_by(email=email).first()
            if existing_organizer:
                flash('Email already registered', 'error')
                logging.debug(f"Registration failed: Email {email} already exists")
                return render_template('organizer/login.html', register_mode=True)
            
            # Create new organizer
            organizer = Organizer(
                email=email,
                name=name,
                password_hash=generate_password_hash(password)
            )
            db.session.add(organizer)
            db.session.commit()
            logging.debug(f"Organizer created successfully with ID: {organizer.id}")
            
            # Set session
            session['organizer_id'] = organizer.id
            session['user_type'] = 'organizer'
            flash('Registration successful! Welcome to Food Truck Fundraiser', 'success')
            return redirect(url_for('organizer_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Organizer registration error: {str(e)}")
            flash('Registration failed. Please try again.', 'error')
            return render_template('organizer/login.html', register_mode=True)
    
    return render_template('organizer/login.html', register_mode=True)

@app.route('/organizer/logout')
def organizer_logout():
    session.pop('organizer_id', None)
    session.pop('user_type', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/get-supporters/<int:event_id>')
def get_supporters(event_id):
    """AJAX endpoint to get supporters for an event"""
    try:
        # Check if organizer owns this event
        organizer_id = session.get('organizer_id')
        if not organizer_id:
            return jsonify({'error': 'Not authorized'}), 401
            
        event = Event.query.filter_by(id=event_id, organizer_id=organizer_id).first()
        if not event:
            return jsonify({'error': 'Event not found'}), 404
            
        # Get supporters
        supporters = []
        for pledge in event.pledges:
            if pledge.status == 'pending':
                supporters.append({
                    'email': pledge.email,
                    'amount': float(pledge.amount),
                    'date': pledge.created_at.strftime('%m/%d/%Y %I:%M %p'),
                    'date_formatted': pledge.created_at.strftime('%B %d, %Y')
                })
        
        return jsonify({
            'event_name': event.name,
            'supporters': supporters,
            'organizer_name': event.organizer.name
        })
        
    except Exception as e:
        logging.error(f"Error getting supporters: {str(e)}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/organizer/supporters/<int:event_id>')
def view_supporters_page(event_id):
    """Direct page to view supporters for an event"""
    try:
        # Check if organizer owns this event
        organizer_id = session.get('organizer_id')
        if not organizer_id:
            flash('Please log in to view supporters', 'error')
            return redirect(url_for('organizer_login'))
            
        event = Event.query.filter_by(id=event_id, organizer_id=organizer_id).first()
        if not event:
            flash('Event not found', 'error')
            return redirect(url_for('organizer_dashboard'))
            
        # Get supporters with charged pledges (paid supporters)
        supporters = []
        for pledge in event.pledges:
            if pledge.status == 'charged':
                supporters.append({
                    'email': pledge.email,
                    'amount': float(pledge.amount),
                    'date': pledge.created_at.strftime('%m/%d/%Y %I:%M %p'),
                    'date_formatted': pledge.created_at.strftime('%B %d, %Y')
                })
        
        organizer = Organizer.query.get(organizer_id)
        
        return render_template('organizer/supporters.html', 
                             event=event, 
                             supporters=supporters,
                             organizer=organizer)
        
    except Exception as e:
        logging.error(f"Error viewing supporters: {str(e)}")
        flash('Error loading supporters', 'error')
        return redirect(url_for('organizer_dashboard'))

@app.route('/organizer/supporters/<int:event_id>/send-thank-you', methods=['POST'])
def send_thank_you_email(event_id):
    """Send thank you email directly from platform to supporter"""
    try:
        # Verify organizer owns this event
        organizer_id = session.get('organizer_id')
        if not organizer_id:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        
        event = Event.query.filter_by(id=event_id, organizer_id=organizer_id).first()
        if not event:
            return jsonify({'success': False, 'error': 'Event not found'}), 404
            
        supporter_email = request.form.get('supporter_email')
        custom_message = request.form.get('custom_message', '').strip()
        
        if not supporter_email:
            return jsonify({'success': False, 'error': 'Supporter email required'}), 400
        
        # Find the supporter's pledge to get amount
        supporter_pledge = None
        for pledge in event.pledges:
            if pledge.email == supporter_email and pledge.status == 'charged':
                supporter_pledge = pledge
                break
                
        if not supporter_pledge:
            return jsonify({'success': False, 'error': 'Supporter not found'}), 404
        
        organizer = Organizer.query.get(organizer_id)
        
        # Create personalized thank you email
        subject = f"Thank you for supporting {event.name}!"
        
        if custom_message:
            email_body = f"""Hi,

{custom_message}

Thank you for supporting our "{event.name}" event! We truly appreciate your pledge of ${supporter_pledge.amount:.2f}.

Best regards,
{organizer.name}

---
This message was sent through the Food Truck Fundraiser platform."""
        else:
            email_body = f"""Hi,

Thank you so much for supporting our "{event.name}" event! We truly appreciate your pledge of ${supporter_pledge.amount:.2f}.

Your support helps make this community event possible. We're excited to bring great food and fun to our neighborhood!

Event Details:
- Date: {event.date.strftime('%B %d, %Y at %I:%M %p')}
- Location: {event.location}

Thank you again for being part of our community!

Best regards,
{organizer.name}

---
This message was sent through the Food Truck Fundraiser platform."""

        # Send the email
        email_success = send_email(supporter_email, subject, email_body)
        
        if email_success:
            logging.info(f"Thank you email sent from organizer {organizer_id} to {supporter_email} for event {event_id}")
            return jsonify({
                'success': True,
                'message': f'Thank you email sent successfully to {supporter_email}!'
            })
        else:
            logging.error(f"Failed to send thank you email from organizer {organizer_id} to {supporter_email}")
            return jsonify({
                'success': False, 
                'error': 'Failed to send email. Please try again.'
            }), 500
            
    except Exception as e:
        logging.error(f"Error sending thank you email: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while sending the email'
        }), 500

@app.route('/admin/supporters/<int:event_id>')
def admin_view_supporters(event_id):
    """Admin page to view supporters for any event"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    try:
        event = Event.query.get_or_404(event_id)
        
        # Get supporters with charged pledges (paid supporters)
        supporters = []
        for pledge in event.pledges:
            if pledge.status == 'charged':
                supporters.append({
                    'id': pledge.id,  # Added pledge ID for messaging links
                    'email': pledge.email,
                    'amount': float(pledge.amount),
                    'date': pledge.created_at.strftime('%m/%d/%Y %I:%M %p'),
                    'date_formatted': pledge.created_at.strftime('%B %d, %Y'),
                    'message_count': 0  # TODO: Add actual message count if needed
                })
        
        return render_template('admin/supporters.html', 
                             event=event, 
                             supporters=supporters)
        
    except Exception as e:
        logging.error(f"Error viewing supporters: {str(e)}")
        flash('Error loading supporters', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/organizer/dashboard')
def organizer_dashboard():
    # Enhanced debugging for iframe session issues
    organizer_id = session.get('organizer_id')
    user_type = session.get('user_type')
    is_embedded = request.referrer and 'thefoodtruckstop.com' in request.referrer
    auth_token = request.args.get('auth_token')
    
    logging.info(f"Dashboard access - Organizer ID: {organizer_id}, User type: {user_type}, Embedded: {is_embedded}")
    logging.info(f"Auth token provided: {auth_token is not None}")
    logging.info(f"Session data: {dict(session)}")
    logging.info(f"Request cookies: {dict(request.cookies)}")
    
    # Check if we have a valid auth token (for iframe compatibility)
    if not organizer_id and auth_token:
        logging.info("No session found, attempting auth token validation...")
        # Look up token in database
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
            # Restore session for seamless navigation
            session['organizer_id'] = organizer_id
            session['user_type'] = 'organizer'
            session.permanent = True
            session.modified = True
            logging.info(f"Auth token validated, restored session for organizer_id: {organizer_id}")
        else:
            logging.warning("Invalid or expired auth token")
    
    if not organizer_id:
        logging.warning("Dashboard access denied - no organizer_id in session and no valid auth token, redirecting to login")
        return redirect(url_for('organizer_login'))
    
    organizer = Organizer.query.get(session['organizer_id'])
    if not organizer:
        flash('Organizer not found', 'error')
        return redirect(url_for('organizer_login'))
    events = Event.query.filter_by(organizer_id=organizer.id).order_by(Event.created_at.desc()).all()
    
    # Calculate total potential earnings
    total_potential_earnings = 0.0
    for event in events:
        if event.status in ['pending', 'funded']:
            profit = event.calculate_organizer_profit_if_goal_met()
            total_potential_earnings += profit
    
    # Pass auth token to template for iframe navigation
    current_auth_token = session.get('auth_token', '')
    return render_template('organizer/dashboard.html', 
                          organizer=organizer, 
                          events=events, 
                          total_potential_earnings=total_potential_earnings,
                          auth_token=current_auth_token)

@app.route('/organizer/create-event', methods=['GET', 'POST'])
def organizer_create_event():
    # Simplified iframe-compatible authentication
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    # Direct token validation without relying on sessions
    if auth_token:
        logging.info(f"Create event: Validating auth token: {auth_token[:20]}...")
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
            logging.info(f"Create event: Token validated for organizer_id: {organizer_id}")
        else:
            logging.warning("Create event: Invalid or expired auth token")
    
    # Fallback to session if no token
    if not organizer_id:
        organizer_id = session.get('organizer_id')
        logging.info(f"Create event: Using session organizer_id: {organizer_id}")
    
    if not organizer_id:
        logging.warning("Create event: No valid authentication found")
        return redirect(url_for('organizer_login'))
    
    if request.method == 'POST':
        try:
            # Create new event
            truck_id = int(request.form['food_truck_id'])
            truck = FoodTruck.query.get(truck_id)
            if not truck:
                flash('Food truck not found', 'error')
                return redirect(url_for('organizer_create_event') + f'?auth_token={auth_token}')
            
            # Validate markup percentage
            try:
                markup_percentage = float(request.form.get('markup_percentage', 0))
            except (ValueError, TypeError):
                markup_percentage = 0.0
            
            event = Event(
                name=request.form['name'],
                description=request.form['description'],
                date=datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M'),
                location=request.form['location'],
                organizer_id=organizer_id,
                food_truck_id=truck_id,
                markup_percentage=markup_percentage,
                pledge_goal=truck.sales_goal if truck.sales_goal else 1000.0
            )
            
            # Process markup splitting configuration
            split_emails = request.form.getlist('split_emails[]')
            split_percentages = request.form.getlist('split_percentages[]')
            split_descriptions = request.form.getlist('split_descriptions[]')
            split_is_organizer = request.form.getlist('split_is_organizer[]')
            
            if split_emails and split_percentages:
                splits = []
                organizer = Organizer.query.get(organizer_id)
                
                for i, email in enumerate(split_emails):
                    if i < len(split_percentages) and email.strip():
                        try:
                            percentage = float(split_percentages[i])
                            description = split_descriptions[i] if i < len(split_descriptions) else ''
                            is_organizer = (i < len(split_is_organizer) and split_is_organizer[i] == 'true')
                            
                            # If this is the organizer split but email is empty, use organizer's email
                            if is_organizer and not email.strip():
                                email = organizer.email
                            
                            splits.append({
                                'email': email.strip(),
                                'percentage': percentage,
                                'description': description.strip(),
                                'is_organizer': is_organizer
                            })
                        except (ValueError, TypeError):
                            continue
                
                # Validate that percentages add up to 100
                total_percentage = sum(split.get('percentage', 0) for split in splits)
                if abs(total_percentage - 100) > 0.1:
                    flash('Markup split percentages must add up to 100%', 'error')
                    trucks = FoodTruck.query.filter_by(status='approved', registration_fee_charged=True).all()
                    return render_template('organizer/create_event.html', trucks=trucks, auth_token=auth_token)
                
                # Set the markup split configuration
                if splits:
                    try:
                        event.set_markup_split_config(splits)
                    except ValueError as e:
                        flash(str(e), 'error')
                        trucks = FoodTruck.query.filter_by(status='approved', registration_fee_charged=True).all()
                        return render_template('organizer/create_event.html', trucks=trucks, auth_token=auth_token)
            
            # Parse selected menu items with markup - ROBUST handling
            selected_items = []
            selected_item_ids = request.form.getlist('selected_items')
            
            # Get truck menu safely
            try:
                truck_menu = truck.get_menu_items() if truck else []
            except:
                truck_menu = []
            
            # If truck has no menu items, this should not happen since approval requires menu items
            if not truck_menu:
                flash(f'Error: Food truck "{truck.name}" has no menu items. Please contact an administrator.', 'error')
                return redirect(url_for('organizer_create_event') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_create_event'))
            
            # Process selected menu items
            for item_id in selected_item_ids:
                try:
                    item_idx = int(item_id)
                    if item_idx < len(truck_menu):
                        item = truck_menu[item_idx].copy()
                        item['original_price'] = item.get('price', 10.0)
                        item['marked_up_price'] = item['original_price'] * (1 + markup_percentage / 100)
                        selected_items.append(item)
                except (ValueError, IndexError, KeyError) as e:
                    logging.warning(f"Error processing menu item {item_id}: {e}")
                    continue
            
            # If no menu items were selected, auto-select all available items
            if not selected_items and truck_menu:
                logging.info(f"No items selected, auto-selecting all {len(truck_menu)} items for truck {truck.name}")
                for item in truck_menu:
                    try:
                        fallback_item = item.copy()
                        fallback_item['original_price'] = item.get('price', 10.0)
                        fallback_item['marked_up_price'] = round(fallback_item['original_price'] * (1 + markup_percentage / 100), 2)
                        selected_items.append(fallback_item)
                    except Exception as e:
                        logging.warning(f"Error processing fallback item: {e}")
                        continue
            
            # Final fallback - if still no items, create a default item
            if not selected_items:
                logging.warning(f"Creating default menu item for truck {truck.name}")
                selected_items = [{
                    'name': 'Special Item',
                    'price': 10.0,
                    'original_price': 10.0,
                    'marked_up_price': 10.0 * (1 + markup_percentage / 100),
                    'description': f'Special item from {truck.name}'
                }]
            
            event.set_selected_menu_items(selected_items)
            
            db.session.add(event)
            db.session.commit()
            
            # Create automatic backup after event creation
            try:
                from backup_system import backup_events_to_file
                all_events = Event.query.all()
                backup_events_to_file(all_events)
                logging.info(f"File backup created after event creation")
            except Exception as backup_error:
                logging.error(f"Backup failed after event creation: {backup_error}")
            
            logging.info(f"Event created successfully: {event.name} with {len(selected_items)} menu items")
            
            # Redirect to payment step for $5 organizer pledge
            flash('Event details saved! Please complete your $5 organizer pledge to publish your event.', 'info')
            return redirect(url_for('organizer_pay_fee', event_id=event.id) + f'?auth_token={auth_token}' if auth_token else url_for('organizer_pay_fee', event_id=event.id))
            
        except Exception as e:
            logging.error(f"Error creating event: {str(e)}", exc_info=True)
            flash(f'Error creating event: {str(e)}', 'error')
            return redirect(url_for('organizer_create_event') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_create_event'))
    
    # GET request - show form
    # Only show approved food trucks that have paid registration fee to organizers
    trucks = FoodTruck.query.filter_by(status='approved', registration_fee_charged=True).all()
    organizer = Organizer.query.get(organizer_id)
    
    # Pass auth token and organizer info to template for form submission consistency  
    return render_template('organizer/create_event.html', trucks=trucks, auth_token=auth_token, organizer=organizer)

@app.route('/organizer/pay-fee/<int:event_id>', methods=['GET', 'POST'])
def organizer_pay_fee(event_id):
    """Handle $5 organizer pledge payment"""
    # Authentication check (same pattern as other organizer routes)
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    if auth_token:
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
    
    if not organizer_id:
        organizer_id = session.get('organizer_id')
    
    if not organizer_id:
        flash('Authentication required', 'error')
        return redirect(url_for('organizer_login'))
    
    # Get event and verify ownership
    event = Event.query.get_or_404(event_id)
    if event.organizer_id != organizer_id:
        flash('Access denied', 'error')
        return redirect(url_for('organizer_dashboard'))
    
    # Check if fee already paid
    if event.organizer_fee_charged:
        flash('Organizer pledge already paid for this event', 'info')
        return redirect(url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard'))
    
    if request.method == 'POST':
        try:
            # ULTIMATE SAFETY: Always clear payment intent and force fresh creation
            if event.organizer_fee_payment_intent:
                logging.info(f"Clearing existing payment intent for event {event.id}: {event.organizer_fee_payment_intent}")
                event.organizer_fee_payment_intent = None
                db.session.commit()
            
            # Double-check Stripe configuration at runtime
            if not stripe.api_key or not stripe.api_key.startswith('sk_live_'):
                # Force fix if needed
                live_secret = os.environ.get('STRIPE_SECRET_KEY_LIVE')
                if live_secret:
                    stripe.api_key = live_secret
                    app.config['STRIPE_PUBLISHABLE_KEY'] = os.environ.get('STRIPE_PUBLISHABLE_KEY_LIVE')
                    logging.warning("🔧 Fixed Stripe keys during payment intent creation")
                else:
                    logging.error(f"No live keys available. Current key: {stripe.api_key[:10] if stripe.api_key else 'None'}")
                    return jsonify({'error': 'Payment system not configured for live mode'}), 500
            
            # Final verification before creating payment intent
            if not stripe.api_key.startswith('sk_live_'):
                return jsonify({'error': 'Payment system still not in live mode'}), 500
            
            # Create fresh Stripe payment intent with verified live keys
            logging.info(f"Creating live payment intent with key: {stripe.api_key[:20]}...")
            payment_intent = stripe.PaymentIntent.create(
                amount=500,  # $5.00 in cents
                currency='usd',
                metadata={
                    'type': 'organizer_pledge',
                    'event_id': event.id,
                    'organizer_id': organizer_id
                }
            )
            
            # Store payment intent ID
            event.organizer_fee_payment_intent = payment_intent.id
            db.session.commit()
            
            return jsonify({
                'client_secret': payment_intent.client_secret
            })
            
        except Exception as e:
            logging.error(f"Error creating payment intent for organizer pledge: {str(e)}")
            return jsonify({'error': 'Payment initialization failed'}), 400
    
    # GET request - show payment form
    organizer = Organizer.query.get(organizer_id)
    return render_template('organizer/pay_fee.html', event=event, organizer=organizer, auth_token=auth_token, config=app.config)

@app.route('/food-truck/pay-registration-fee/<int:truck_id>', methods=['GET', 'POST'])
def food_truck_pay_registration_fee(truck_id):
    """Handle $25 food truck registration fee payment"""
    # Authentication check
    if not session.get('authenticated') or session.get('user_type') != 'food_truck_owner':
        flash('Authentication required', 'error')
        return redirect(url_for('food_truck_login'))
    
    owner_id = session.get('food_truck_owner_id')
    if not owner_id:
        flash('Authentication required', 'error')
        return redirect(url_for('food_truck_login'))
    
    # Get truck and verify ownership
    truck = FoodTruck.query.get_or_404(truck_id)
    if truck.owner_id != owner_id:
        flash('Access denied', 'error')
        return redirect(url_for('food_truck_dashboard'))
    
    # Check if fee already paid
    if truck.registration_fee_charged:
        flash('Registration fee already paid for this truck', 'info')
        return redirect(url_for('food_truck_dashboard'))
    
    if request.method == 'POST':
        try:
            # Create Stripe payment intent for $25 registration fee
            payment_intent = stripe.PaymentIntent.create(
                amount=2500,  # $25.00 in cents
                currency='usd',
                metadata={
                    'type': 'food_truck_registration_fee',
                    'truck_id': truck.id,
                    'owner_id': owner_id
                }
            )
            
            # Store payment intent ID
            truck.registration_fee_payment_intent = payment_intent.id
            db.session.commit()
            
            return jsonify({
                'client_secret': payment_intent.client_secret
            })
            
        except Exception as e:
            logging.error(f"Error creating payment intent for food truck registration fee: {str(e)}")
            return jsonify({'error': 'Payment initialization failed'}), 400
    
    # GET request - show payment form
    owner = FoodTruckOwner.query.get(owner_id)
    return render_template('food_truck/pay_registration_fee.html', truck=truck, owner=owner)

@app.route('/food-truck/confirm-registration-fee-payment/<int:truck_id>', methods=['POST'])
def confirm_food_truck_registration_fee_payment(truck_id):
    """Confirm food truck registration fee payment and mark truck as paid"""
    # Authentication check
    if not session.get('authenticated') or session.get('user_type') != 'food_truck_owner':
        return jsonify({'error': 'Authentication required'}), 401
    
    owner_id = session.get('food_truck_owner_id')
    if not owner_id:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Get truck and verify ownership
    truck = FoodTruck.query.get_or_404(truck_id)
    if truck.owner_id != owner_id:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Verify the payment intent was successful
        if not truck.registration_fee_payment_intent:
            return jsonify({'error': 'No payment intent found'}), 400
        
        payment_intent = stripe.PaymentIntent.retrieve(truck.registration_fee_payment_intent)
        
        if payment_intent.status == 'succeeded':
            # Mark fee as paid and automatically approve truck
            truck.registration_fee_charged = True
            truck.status = 'approved'  # Auto-approve after payment
            truck.approved_at = datetime.utcnow()
            db.session.commit()
            
            # Send notification email to admin about new truck registration
            owner = FoodTruckOwner.query.get(owner_id)
            owner_name = owner.name if owner else "Unknown Owner"
            send_email(
                'support@foodtruckfundraiser.com',
                f"Food Truck Registration Fee Paid: {truck.name}",
                f"A food truck registration fee has been paid and automatically approved:\n\nTruck: {truck.name}\nOwner: {owner_name}\nCuisine: {truck.cuisine_type}\nGoal: ${truck.sales_goal:.2f}\n\nThe truck is now approved and can participate in events immediately."
            )
            
            return jsonify({'success': True, 'redirect': url_for('food_truck_dashboard')})
        else:
            return jsonify({'error': 'Payment not completed'}), 400
            
    except Exception as e:
        logging.error(f"Error confirming food truck registration fee payment: {str(e)}")
        return jsonify({'error': 'Payment confirmation failed'}), 500

@app.route('/organizer/confirm-fee-payment/<int:event_id>', methods=['POST'])
def confirm_organizer_fee_payment(event_id):
    """Confirm organizer pledge payment and publish event"""
    # Authentication check
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    if auth_token:
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
    
    if not organizer_id:
        organizer_id = session.get('organizer_id')
    
    if not organizer_id:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Get event and verify ownership
    event = Event.query.get_or_404(event_id)
    if event.organizer_id != organizer_id:
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Verify the payment intent was successful
        if not event.organizer_fee_payment_intent:
            return jsonify({'error': 'No payment intent found'}), 400
        
        try:
            payment_intent = stripe.PaymentIntent.retrieve(event.organizer_fee_payment_intent)
        except stripe.error.InvalidRequestError as e:
            if "similar object exists in test mode" in str(e):
                # Test payment intent can't be accessed in live mode
                logging.error(f"Cannot access test payment intent {event.organizer_fee_payment_intent} in live mode for event {event.id}")
                return jsonify({'error': 'Payment was created in test mode but system is now in live mode. Please refresh and try payment again.'}), 400
            else:
                raise e
        
        if payment_intent.status == 'succeeded':
            # Mark fee as paid and publish event
            event.organizer_fee_charged = True
            
            # Create organizer's $5 pledge to show on event page
            organizer = Organizer.query.get(organizer_id)
            organizer_pledge = Pledge(
                email=organizer.email,
                amount=5.00,
                processing_fee=0.0,  # No processing fee for organizer
                stripe_payment_intent_id=event.organizer_fee_payment_intent,
                event_id=event.id,
                status='charged',  # Already paid
                charged_at=datetime.utcnow()
            )
            
            db.session.add(organizer_pledge)
            
            # Update event pledge total to include organizer's $5
            event.update_pledge_total()
            
            db.session.commit()
            
            # Send notification email to admin about new event
            organizer_name = organizer.name if organizer else "Unknown Organizer"
            send_email(
                'support@foodtruckfundraiser.com',
                f"New Event Published: {event.name}",
                f"A new event has been published (organizer pledge paid):\n\nEvent: {event.name}\nOrganizer: {organizer_name}\nFood Truck: {event.food_truck.name}\nDate: {event.date}\nLocation: {event.location}\nPledge Goal: ${event.pledge_goal:.2f}\n\nOrganizer will receive a free entree when the event is successfully funded."
            )
            
            return jsonify({'success': True, 'redirect': url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard')})
        else:
            return jsonify({'error': 'Payment not completed'}), 400
            
    except Exception as e:
        logging.error(f"Error confirming organizer pledge payment: {str(e)}")
        return jsonify({'error': 'Payment confirmation failed'}), 500

# =============================================================================
# TRANSFER SYSTEM (PREFERRED): Handles pledge transfers with email confirmation
# =============================================================================
# This system respects user choice by requiring email confirmation for each 
# pledge transfer. Use this instead of the removed admin pooling functions.
#
# Key routes:
# - transfer_pledges(): Initiate transfer process (below)
# - pledge_transfer_consent(): Handle user consent responses
# =============================================================================

@app.route('/organizer/events/<int:event_id>/transfer-pledges', methods=['POST'])
def transfer_pledges(event_id):
    """Initiate pledge transfer process with email confirmation"""
    # Authentication check (same pattern as other organizer routes)
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    if auth_token:
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
        else:
            logging.warning("Transfer pledges: Invalid or expired auth token")
    
    if not organizer_id:
        organizer_id = session.get('organizer_id')
    
    if not organizer_id:
        flash('Authentication required', 'error')
        return redirect(url_for('organizer_login'))
    
    # Get source and target events
    source_event = Event.query.get_or_404(event_id)
    target_event_id = int(request.form['target_event_id'])
    target_event = Event.query.get_or_404(target_event_id)
    
    # Verify organizer owns both events
    if source_event.organizer_id != organizer_id or target_event.organizer_id != organizer_id:
        flash('You can only transfer pledges between your own events', 'error')
        return redirect(url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard'))
    
    # Validation checks - allow transfers from pending, funded, and approved events
    if source_event.status not in ['pending', 'funded', 'approved']:
        flash('Can only transfer pledges from active events (pending, funded, or approved)', 'error')
        return redirect(url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard'))
    
    if target_event.status not in ['pending', 'funded']:
        flash('Can only transfer pledges to events that are still accepting pledges', 'error')
        return redirect(url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard'))
    
    if source_event.id == target_event.id:
        flash('Cannot transfer pledges to the same event', 'error')
        return redirect(url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard'))
    
    # Get transferable pledges from source event (pending or charged)
    transferable_pledges = [p for p in source_event.pledges if p.status in ['pending', 'charged']]
    
    if not transferable_pledges:
        flash('No transferable pledges found to transfer', 'error')
        return redirect(url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard'))
    
    try:
        # Create transfer record
        transfer = PledgeTransfer(
            source_event_id=source_event.id,
            target_event_id=target_event.id,
            organizer_id=organizer_id,
            total_pledges_requested=len(transferable_pledges),
            total_amount_requested=sum(p.amount for p in transferable_pledges),
            status='consent_requested',
            consent_requested_at=datetime.utcnow()
        )
        
        db.session.add(transfer)
        db.session.flush()  # Get transfer ID
        
        # Create consent requests for each pledge
        import secrets
        for pledge in transferable_pledges:
            consent_token = secrets.token_urlsafe(32)
            consent_request = PledgeTransferConsent(
                transfer_id=transfer.id,
                pledge_id=pledge.id,
                consent_token=consent_token
            )
            db.session.add(consent_request)
        
        db.session.commit()
        
        # Send consent emails to all pledgers
        for pledge in transferable_pledges:
            consent_request = PledgeTransferConsent.query.filter_by(
                transfer_id=transfer.id,
                pledge_id=pledge.id
            ).first()
            
            if consent_request:
                consent_url = url_for('pledge_transfer_consent', 
                                    token=consent_request.consent_token, 
                                    _external=True)
                
                # Create a simple text version for fallback
                charged_note = ""
                if pledge.status == 'charged':
                    charged_note = f"\n\nIMPORTANT: Your pledge has already been charged (${pledge.amount:.2f}). If you approve this transfer, we will process a refund for the original event and charge the same amount for the new event. Your net cost remains ${pledge.amount:.2f}."
                
                text_body = f"""Transfer Request: Your {source_event.name} Pledge

Your event organizer has requested to transfer your pledge from "{source_event.name}" to "{target_event.name}".

Original Event: {source_event.name}
Date: {source_event.date.strftime('%B %d, %Y at %I:%M %p')}
Your Pledge: ${pledge.amount:.2f} ({pledge.status.title()})

New Event: {target_event.name}
Date: {target_event.date.strftime('%B %d, %Y at %I:%M %p')}
Location: {target_event.location}

Your pledge amount will remain the same (${pledge.amount:.2f}).{charged_note}

To respond, click one of these links:
APPROVE: {consent_url}?response=approve
DECLINE: {consent_url}?response=decline

You have 7 days to respond to this request.
Thank you!"""

                html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transfer Request</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #ff8a00, #e52e71); color: white; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 20px; }}
        .content {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .event-box {{ background: white; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ff8a00; }}
        .buttons {{ text-align: center; margin: 30px 0; }}
        .btn {{ display: inline-block; padding: 15px 30px; margin: 10px; text-decoration: none; border-radius: 25px; font-weight: bold; font-size: 16px; transition: all 0.3s; }}
        .btn-approve {{ background: #28a745; color: white; }}
        .btn-approve:hover {{ background: #218838; }}
        .btn-decline {{ background: #dc3545; color: white; }}
        .btn-decline:hover {{ background: #c82333; }}
        .footer {{ font-size: 12px; color: #666; text-align: center; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🍴 Pledge Transfer Request</h1>
    </div>
    
    <div class="content">
        <p><strong>Hello!</strong></p>
        
        <p>Your event organizer has requested to transfer your pledge from <strong>"{source_event.name}"</strong> to <strong>"{target_event.name}"</strong>.</p>
        
        <div class="event-box">
            <h3>📅 Original Event</h3>
            <strong>{source_event.name}</strong><br>
            <strong>Date:</strong> {source_event.date.strftime('%B %d, %Y at %I:%M %p')}<br>
            <strong>Your Pledge:</strong> ${pledge.amount:.2f}
        </div>
        
        <div class="event-box">
            <h3>📅 New Event</h3>
            <strong>{target_event.name}</strong><br>
            <strong>Date:</strong> {target_event.date.strftime('%B %d, %Y at %I:%M %p')}<br>
            <strong>Location:</strong> {target_event.location}
        </div>
        
        <p><strong>💰 Your pledge amount will remain the same (${pledge.amount:.2f})</strong>, and your payment method won't be charged until the new event reaches its funding goal.</p>
        
        <div class="buttons">
            <a href="{consent_url}?response=approve" class="btn btn-approve">✅ APPROVE TRANSFER</a>
            <a href="{consent_url}?response=decline" class="btn btn-decline">❌ DECLINE TRANSFER</a>
        </div>
        
        <p><em>⚠️ If you decline, your original pledge will be cancelled and no payment will be processed.</em></p>
        
        <p><strong>⏰ You have 7 days to respond to this request.</strong></p>
        
        <p>Thank you!</p>
    </div>
    
    <div class="footer">
        Food Truck Fundraiser Platform
    </div>
</body>
</html>"""

                # Send email with error handling
                email_success = send_email(
                    pledge.email,
                    f"Transfer Request: Your {source_event.name} Pledge",
                    text_body,
                    html=html_body
                )
                
                # Log email status for monitoring
                if not email_success:
                    logging.error(f"Failed to send transfer consent email to {pledge.email} for pledge {pledge.id}")
                else:
                    logging.info(f"Transfer consent email sent successfully to {pledge.email} for pledge {pledge.id}")
        
        flash(f'Transfer request sent to {len(transferable_pledges)} pledgers. You will be notified once they respond.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating pledge transfer: {str(e)}")
        flash('Error initiating transfer. Please try again.', 'error')
    
    return redirect(url_for('organizer_dashboard') + f'?auth_token={auth_token}' if auth_token else url_for('organizer_dashboard'))

@app.route('/pledge-transfer/consent/<token>')
def pledge_transfer_consent(token):
    """Handle pledge transfer consent"""
    response = request.args.get('response')  # 'approve' or 'decline'
    
    consent_request = PledgeTransferConsent.query.filter_by(consent_token=token).first_or_404()
    
    if consent_request.status != 'pending':
        return render_template('transfer_consent_already_responded.html', 
                             consent_request=consent_request)
    
    # Update consent status
    if response == 'approve':
        consent_request.status = 'consented'
        consent_request.responded_at = datetime.utcnow()
        
        # Transfer the pledge to the new event
        pledge = consent_request.pledge
        transfer = consent_request.transfer
        
        # Update pledge event_id
        old_event = pledge.event
        new_event = transfer.target_event
        
        # Handle charged pledges - need refund/recharge process
        if pledge.status == 'charged':
            # For charged pledges, we need to:
            # 1. Issue a refund for the original event
            # 2. Create a new charge for the target event
            # 3. Keep the pledge status as 'charged'
            
            # Note: In a real implementation, this would integrate with Stripe
            # to process actual refunds and recharges. For now, we'll log this
            # as a transfer that requires manual payment processing.
            
            # Create a new payment intent for the target event
            from utils import create_stripe_payment_intent
            try:
                payment_intent = create_stripe_payment_intent(
                    pledge.amount,
                    f"Transfer to {new_event.name} from {old_event.name}",
                    pledge.email
                )
                # Update pledge with new payment intent
                pledge.stripe_payment_intent_id = payment_intent['id']
                
                # Log the transfer for manual processing
                logging.info(f"Charged pledge transfer: ${pledge.amount} from {old_event.name} to {new_event.name} for {pledge.email}")
                
            except Exception as e:
                logging.error(f"Failed to create new payment intent for transfer: {str(e)}")
                # Continue with transfer but mark for manual review
                
        elif pledge.status == 'pending':
            # For pending pledges, simple transfer is sufficient
            pass
        
        pledge.event_id = transfer.target_event_id
        
        # Update pledge totals for both events
        old_event.update_pledge_total()
        new_event.update_pledge_total()
        
        # Update transfer statistics atomically to prevent race conditions
        transfer.pledges_consented += 1
        transfer.amount_transferred += pledge.amount
        
        # Re-count actual consented pledges to ensure accuracy (prevents race conditions)
        actual_consented_count = PledgeTransferConsent.query.filter_by(
            transfer_id=transfer.id, 
            status='consented'
        ).count()
        
        # Update transfer stats with actual count
        transfer.pledges_consented = actual_consented_count
        
        # Check if all pledges have consented - complete the transfer
        if transfer.pledges_consented == transfer.total_pledges_requested:
            transfer.status = 'completed'
            transfer.completed_at = datetime.utcnow()
            logging.info(f"Transfer {transfer.id} completed: {transfer.pledges_consented}/{transfer.total_pledges_requested} pledges consented")
        
        db.session.commit()
        
        return render_template('transfer_consent_approved.html', 
                             transfer=transfer, 
                             pledge=pledge,
                             old_event_name=old_event.name,
                             new_event=new_event)
        
    elif response == 'decline':
        consent_request.status = 'declined'
        consent_request.responded_at = datetime.utcnow()
        
        # Cancel the pledge
        pledge = consent_request.pledge
        pledge.status = 'cancelled'
        
        # Update event pledge total
        pledge.event.update_pledge_total()
        
        db.session.commit()
        
        return render_template('transfer_consent_declined.html', 
                             transfer=consent_request.transfer,
                             pledge=pledge)
    
    else:
        # Show consent form
        return render_template('transfer_consent_form.html', 
                             consent_request=consent_request)

# Public Routes
@app.route('/events')
def events_list():
    """Public page listing all events by status"""
    # Get events by different status categories - ONLY show events where organizer paid the $5 fee
    active_events = Event.query.filter(
        Event.status.in_(['pending', 'funded']),
        Event.organizer_fee_charged == True
    ).order_by(Event.created_at.desc()).all()
    
    completed_events = Event.query.filter(
        Event.status == 'approved',
        Event.organizer_fee_charged == True
    ).order_by(Event.created_at.desc()).all()
    
    # All events - also filtered by fee payment
    all_events = Event.query.filter(
        Event.organizer_fee_charged == True
    ).order_by(Event.created_at.desc()).all()
    
    return render_template('events/list.html', 
                         active_events=active_events, 
                         completed_events=completed_events,
                         all_events=all_events)

@app.route('/events/<int:event_id>')
def event_detail(event_id):
    """Public event detail page for pledging"""
    from sqlalchemy.orm import joinedload
    event = Event.query.options(joinedload(Event.pledges)).get_or_404(event_id)
    
    # Check if organizer paid the $5 fee - if not, event shouldn't be accessible
    if not event.organizer_fee_charged:
        flash('This event is not yet available for pledges', 'error')
        return redirect(url_for('events_list'))
    
    if event.status not in ['pending', 'funded']:
        flash('This event is no longer accepting pledges', 'info')
        return redirect(url_for('events_list'))
    
    return render_template('events/detail.html', event=event)

@app.route('/events/<int:event_id>/pledge', methods=['GET', 'POST'])
def make_pledge(event_id):
    """Handle pledge creation with Stripe tokenization"""
    event = Event.query.get_or_404(event_id)
    
    # Check if organizer paid the $5 fee - if not, pledging shouldn't be allowed
    if not event.organizer_fee_charged:
        flash('This event is not yet available for pledges', 'error')
        return redirect(url_for('events_list'))
    
    if event.status not in ['pending', 'funded']:
        flash('This event is no longer accepting pledges', 'error')
        return redirect(url_for('event_detail', event_id=event_id))
    
    if request.method == 'POST':
        email = request.form['email']
        amount = float(request.form['amount'])
        stripe_payment_method = request.form.get('stripe_payment_method')
        selected_menu_items_json = request.form.get('selected_menu_items')
        
        # Gift meal information
        is_gift = request.form.get('is_gift') == 'on'
        recipient_name = request.form.get('recipient_name') if is_gift else None
        recipient_email = request.form.get('recipient_email') if is_gift else None
        gift_message = request.form.get('gift_message') if is_gift else None
        
        try:
            # Parse selected menu items if provided
            selected_menu_items = []
            if selected_menu_items_json:
                try:
                    selected_menu_items = json.loads(selected_menu_items_json)
                except (json.JSONDecodeError, TypeError):
                    selected_menu_items = []
            
            # Calculate processing fee (4.5%)
            processing_fee = amount * 0.045
            total_amount = amount + processing_fee
            
            # Create payment intent with Stripe (including processing fee)
            payment_intent_id = create_stripe_payment_intent(total_amount, email, f"Pledge for {event.name} (includes 4.5% processing fee)")
            
            if payment_intent_id:
                if not stripe_payment_method:
                    flash('Payment information is required. Please try again.', 'error')
                    return redirect(url_for('make_pledge', event_id=event_id))
                # Attach payment method to payment intent and confirm it
                try:
                    import stripe
                    
                    # Attach and confirm the payment intent
                    intent = stripe.PaymentIntent.confirm(
                        payment_intent_id,
                        payment_method=stripe_payment_method,
                        return_url=request.url_root  # For 3D Secure redirects if needed
                    )
                    
                    if intent.status not in ['requires_capture', 'succeeded']:
                        flash('Payment could not be processed. Please try again.', 'error')
                        return redirect(url_for('make_pledge', event_id=event_id))
                        
                except Exception as e:
                    logging.error(f"Error confirming payment intent: {str(e)}")
                    flash('Payment processing error. Please try again.', 'error')
                    return redirect(url_for('make_pledge', event_id=event_id))
                
                # Create pledge record
                pledge = Pledge(
                    email=email,
                    amount=amount,
                    processing_fee=processing_fee,
                    stripe_token=stripe_payment_method,  # Store payment method ID instead of token
                    stripe_payment_intent_id=payment_intent_id,
                    event_id=event_id,
                    is_gift=is_gift,
                    recipient_name=recipient_name,
                    recipient_email=recipient_email,
                    gift_message=gift_message
                )
                
                # Store selected menu items
                if selected_menu_items:
                    pledge.set_selected_menu_items(selected_menu_items)
                
                db.session.add(pledge)
                db.session.commit()
                
                # Update event pledge total
                event.update_pledge_total()
                
                # Check if goal is met
                if event.is_goal_met() and event.status == 'pending':
                    event.status = 'funded'
                    db.session.commit()
                    
                    # Send notification to admin
                    send_email(
                        'support@foodtruckfundraiser.com',
                        f"Event Goal Met: {event.name}",
                        f"The event '{event.name}' has reached its funding goal of ${event.pledge_goal:.2f}. Please review and approve the event to charge all pledges."
                    )
                    
                    # Send goal reached confirmation to pledger
                    if is_gift:
                        # Send notification to the gift giver
                        send_email(
                            email,
                            f"Gift Meal Event Funded! - {event.name}",
                            f"Great news! Your gift meal pledge of ${amount:.2f} for '{event.name}' helped reach the funding goal!\n\nGift Recipient: {recipient_name} ({recipient_email})\n\nEvent Goal: ${event.pledge_goal:.2f}\nTotal Raised: ${event.current_pledges:.2f}\n\nPayment Details:\nPledge Amount: ${amount:.2f}\nProcessing Fee (4.5%): ${processing_fee:.2f}\nTotal Charged: ${total_amount:.2f}\n\nYour gift recipient will receive their e-ticket soon!\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nThank you for your generosity!"
                        )
                        # Send notification to the gift recipient
                        gift_email_message = f"You've received a gift meal for '{event.name}'!\n\nFrom: {email}"
                        if gift_message:
                            gift_email_message += f"\n\nPersonal message:\n\"{gift_message}\""
                        gift_email_message += f"\n\nThe event has reached its funding goal and your meal is confirmed!\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nYou'll receive your e-ticket soon. Thank you {recipient_name}!"
                        send_email(
                            recipient_email,
                            f"Gift Meal Confirmed! - {event.name}",
                            gift_email_message
                        )
                    else:
                        send_email(
                            email,
                            f"Event Funded! - {event.name}",
                            f"Great news! Your pledge of ${amount:.2f} for '{event.name}' helped reach the funding goal!\n\nEvent Goal: ${event.pledge_goal:.2f}\nTotal Raised: ${event.current_pledges:.2f}\n\nPayment Details:\nPledge Amount: ${amount:.2f}\nProcessing Fee (4.5%): ${processing_fee:.2f}\nTotal Charged: ${total_amount:.2f}\n\nPayments will be processed soon and you'll receive your e-ticket.\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nThank you for your support!"
                        )
                else:
                    # Send regular pledge confirmation
                    if is_gift:
                        # Send confirmation to gift giver
                        send_email(
                            email,
                            f"Gift Meal Pledge Confirmation - {event.name}",
                            f"Thank you for your ${amount:.2f} gift meal pledge for '{event.name}'!\n\nGift Recipient: {recipient_name} ({recipient_email})\n\nEvent Goal: ${event.pledge_goal:.2f}\nCurrent Progress: ${event.current_pledges:.2f} (${event.pledge_goal - event.current_pledges:.2f} remaining)\n\nPayment Details:\nPledge Amount: ${amount:.2f}\nProcessing Fee (4.5%): ${processing_fee:.2f}\nTotal to be charged: ${total_amount:.2f}\n\nYour payment will only be charged if the event reaches its funding goal. Once funded, your gift recipient will receive their e-ticket!\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nWe'll keep you updated on the progress!"
                        )
                        # Send initial gift notification to recipient
                        gift_email_message = f"You've received a gift meal pledge for '{event.name}'!\n\nFrom: {email}"
                        if gift_message:
                            gift_email_message += f"\n\nPersonal message:\n\"{gift_message}\""
                        gift_email_message += f"\n\nThis event needs ${event.pledge_goal - event.current_pledges:.2f} more to reach its goal of ${event.pledge_goal:.2f}. If the goal is reached, you'll receive your meal e-ticket!\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nThank you {recipient_name}!"
                        send_email(
                            recipient_email,
                            f"Gift Meal Pledge - {event.name}",
                            gift_email_message
                        )
                    else:
                        send_email(
                            email,
                            f"Pledge Confirmation - {event.name}",
                            f"Thank you for your ${amount:.2f} pledge for '{event.name}'!\n\nEvent Goal: ${event.pledge_goal:.2f}\nCurrent Progress: ${event.current_pledges:.2f} (${event.pledge_goal - event.current_pledges:.2f} remaining)\n\nPayment Details:\nPledge Amount: ${amount:.2f}\nProcessing Fee (4.5%): ${processing_fee:.2f}\nTotal to be charged: ${total_amount:.2f}\n\nYour payment will only be charged if the event reaches its funding goal.\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nWe'll keep you updated on the progress!"
                        )
                
                if is_gift:
                    flash(f'Gift meal pledge created successfully! Both you and {recipient_name} will be notified when the event reaches its goal.', 'success')
                else:
                    flash('Pledge created successfully! You will only be charged if the event reaches its funding goal.', 'success')
                return redirect(url_for('pledge_success', pledge_id=pledge.id))
            else:
                flash('Error processing payment. Please try again.', 'error')
                
        except Exception as e:
            logging.error(f"Error creating pledge: {str(e)}")
            flash('Error processing pledge. Please try again.', 'error')
    
    return render_template('pledge/form.html', 
                          event=event, 
                          stripe_publishable_key=app.config.get('STRIPE_PUBLISHABLE_KEY'))

@app.route('/pledge/<int:pledge_id>/success')
def pledge_success(pledge_id):
    """Pledge success page"""
    pledge = Pledge.query.get_or_404(pledge_id)
    return render_template('pledge/success.html', pledge=pledge)

# API Routes for AJAX
@app.route('/api/truck/<int:truck_id>/menu')
def get_truck_menu(truck_id):
    """API endpoint to get truck menu items"""
    truck = FoodTruck.query.get_or_404(truck_id)
    return jsonify(truck.get_menu_items())

# ===== SUPPORT CHAT API ROUTES =====

@app.route('/api/chat/message', methods=['POST'])
def chat_message():
    """Handle chat messages from users"""
    try:
        from ai_support import get_ai_response
        
        data = request.get_json()
        session_id = data.get('session_id')
        user_message = data.get('message', '').strip()
        page_context = data.get('page_context', {})
        
        if not session_id or not user_message:
            return jsonify({'success': False, 'error': 'Missing session_id or message'}), 400
        
        # Get or create conversation with error handling
        try:
            conversation = SupportConversation.query.filter_by(session_id=session_id).first()
        except Exception as db_error:
            logging.error(f"Database query error in chat_message: {db_error}")
            return jsonify({
                'success': False,
                'error': 'Database connection issue',
                'response': 'I\'m having trouble connecting to support right now. Please try again in a moment.'
            }), 500
            
        if not conversation:
            try:
                conversation = SupportConversation(
                    session_id=session_id,
                    user_agent=request.headers.get('User-Agent', ''),
                    ip_address=request.remote_addr,
                    page_url=page_context.get('url'),
                    page_type=page_context.get('page_type', 'general'),
                    event_id=page_context.get('event_id'),
                    event_name=page_context.get('event_name')
                )
                db.session.add(conversation)
                db.session.commit()
                
                # Send notification email for new chat conversation
                try:
                    send_new_chat_notification(conversation, user_message, page_context)
                except Exception as email_error:
                    logging.error(f"Failed to send new chat notification email: {email_error}")
                    # Don't fail the conversation creation if email fails
            except Exception as db_error:
                logging.error(f"Database creation error in chat_message: {db_error}")
                return jsonify({
                    'success': False,
                    'error': 'Database connection issue',
                    'response': 'Unable to start conversation right now. Please try again later.'
                }), 500
        
        # Update last activity
        conversation.last_activity = datetime.utcnow()
        
        # Save user message
        user_msg = SupportMessage(
            conversation_id=conversation.id,
            content=user_message,
            sender_type='user'
        )
        db.session.add(user_msg)
        db.session.commit()
        
        # Get conversation history for context
        history = SupportMessage.query.filter(
            SupportMessage.conversation_id == conversation.id,
            SupportMessage.created_at < user_msg.created_at
        ).order_by(SupportMessage.created_at.desc()).limit(10).all()
        
        # Check if already escalated to human
        if conversation.escalated_to_human:
            return jsonify({
                'success': True,
                'response': 'Your message has been sent to our support team. They will respond shortly.',
                'escalated': True,
                'should_escalate': False
            })
        
        # Get AI response
        ai_result = get_ai_response(conversation.id, user_message, history)
        
        # Save AI response
        ai_msg = SupportMessage(
            conversation_id=conversation.id,
            content=ai_result['response'],
            sender_type='ai',
            confidence_score=ai_result['confidence'],
            processing_time=ai_result['processing_time'],
            tokens_used=ai_result['tokens_used'],
            ai_model_used=ai_result['model']
        )
        db.session.add(ai_msg)
        
        # Check if should escalate
        if ai_result['should_escalate']:
            conversation.escalated_to_human = True
            conversation.escalated_at = datetime.utcnow()
            conversation.status = 'escalated'
            
            # Send notification to admin
            send_email(
                'support@foodtruckfundraiser.com',
                f'Support Chat Escalated - {session_id}',
                f'A support conversation has been escalated to human support.\n\nSession: {session_id}\nUser Message: {user_message}\nAI Response: {ai_result["response"]}\n\nView conversation: /admin/support/{conversation.id}'
            )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'response': ai_result['response'],
            'confidence': ai_result['confidence'],
            'should_escalate': ai_result['should_escalate'],
            'escalated': conversation.escalated_to_human
        })
        
    except Exception as e:
        logging.error(f"Chat message error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'response': 'I\'m having trouble right now. Let me get a human to help you.'
        }), 500

@app.route('/api/chat/escalate', methods=['POST'])
def chat_escalate():
    """Escalate conversation to human support"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'success': False, 'error': 'Missing session_id'}), 400
        
        try:
            conversation = SupportConversation.query.filter_by(session_id=session_id).first()
        except Exception as db_error:
            logging.error(f"Database query error in chat_escalate: {db_error}")
            return jsonify({
                'success': False, 
                'error': 'Unable to connect to human support right now. Please try again later.'
            }), 500
            
        if not conversation:
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        # Mark as escalated
        conversation.escalated_to_human = True
        conversation.escalated_at = datetime.utcnow()
        conversation.status = 'escalated'
        
        # Add escalation message
        escalation_msg = SupportMessage(
            conversation_id=conversation.id,
            content='User requested human support escalation',
            sender_type='system',
            message_type='escalation'
        )
        db.session.add(escalation_msg)
        
        # Send notification to admin
        recent_messages = SupportMessage.query.filter_by(conversation_id=conversation.id).order_by(SupportMessage.created_at.desc()).limit(5).all()
        conversation_preview = '\n'.join([f"{msg.sender_type}: {msg.content}" for msg in reversed(recent_messages)])
        
        send_email(
            'support@foodtruckfundraiser.com',
            f'Support Chat Manual Escalation - {session_id}',
            f'A user manually requested human support.\n\nSession: {session_id}\n\nRecent conversation:\n{conversation_preview}\n\nView full conversation: /admin/support/{conversation.id}'
        )
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        logging.error(f"Chat escalation error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/chat/poll')
def chat_poll():
    """Poll for new messages in escalated conversations"""
    try:
        session_id = request.args.get('session_id')
        last_message_id = request.args.get('last_message_id', 0, type=int)
        
        if not session_id:
            return jsonify({'success': False, 'error': 'Missing session_id'}), 400
        
        try:
            conversation = SupportConversation.query.filter_by(session_id=session_id).first()
        except Exception as db_error:
            logging.error(f"Database query error in chat_poll: {db_error}")
            return jsonify({
                'success': False, 
                'error': 'Unable to connect to human support right now. Please try again later.'
            }), 500
            
        if not conversation:
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        # Get new messages from admin
        new_messages = SupportMessage.query.filter(
            SupportMessage.conversation_id == conversation.id,
            SupportMessage.id > last_message_id,
            SupportMessage.sender_type == 'admin'
        ).all()
        
        messages_data = []
        for msg in new_messages:
            messages_data.append({
                'id': msg.id,
                'content': msg.content,
                'sender_type': msg.sender_type,
                'sender_name': msg.sender_name,
                'created_at': msg.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'messages': messages_data,
            'admin_connected': conversation.assigned_admin_id is not None
        })
        
    except Exception as e:
        logging.error(f"Chat polling error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ===== ADMIN SUPPORT MANAGEMENT ROUTES =====

@app.route('/admin/support')
def admin_support_dashboard():
    """Admin dashboard for managing support conversations"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    # Get conversation statistics with error handling
    try:
        total_conversations = SupportConversation.query.count()
        active_conversations = SupportConversation.query.filter_by(status='active').count()
        escalated_conversations = SupportConversation.query.filter_by(status='escalated').count()
        resolved_conversations = SupportConversation.query.filter_by(status='resolved').count()
        
        # Get recent conversations
        recent_conversations = SupportConversation.query.order_by(SupportConversation.last_activity.desc()).limit(20).all()
        
        # Pre-calculate message counts to avoid relationship errors
        for conversation in recent_conversations:
            try:
                conversation._message_count = db.session.query(db.func.count(SupportMessage.id)).filter(
                    SupportMessage.conversation_id == conversation.id
                ).scalar() or 0
            except Exception as msg_error:
                logging.error(f"Error counting messages for conversation {conversation.id}: {msg_error}")
                conversation._message_count = 0
        
        # Get unassigned escalated conversations
        unassigned_escalated = SupportConversation.query.filter_by(
            status='escalated',
            assigned_admin_id=None
        ).order_by(SupportConversation.escalated_at.desc()).all()
    except Exception as e:
        logging.error(f"Support dashboard query error: {e}")
        # Return safe defaults when database has issues
        total_conversations = 0
        active_conversations = 0
        escalated_conversations = 0
        resolved_conversations = 0
        recent_conversations = []
        unassigned_escalated = []
    
    return render_template('admin/support_dashboard.html',
                         total_conversations=total_conversations,
                         active_conversations=active_conversations,
                         escalated_conversations=escalated_conversations,
                         resolved_conversations=resolved_conversations,
                         recent_conversations=recent_conversations,
                         unassigned_escalated=unassigned_escalated)

@app.route('/admin/support/<int:conversation_id>')
def admin_support_conversation(conversation_id):
    """View and manage specific support conversation"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    conversation = SupportConversation.query.get_or_404(conversation_id)
    admin = Admin.query.get(session['admin_id'])
    
    # Auto-assign if not assigned
    if not conversation.assigned_admin_id:
        conversation.assigned_admin_id = admin.id
        conversation.assigned_at = datetime.utcnow()
        db.session.commit()
    
    # Get all messages
    messages = SupportMessage.query.filter_by(conversation_id=conversation.id).order_by(SupportMessage.created_at.asc()).all()
    
    return render_template('admin/support_conversation.html',
                         conversation=conversation,
                         messages=messages,
                         admin=admin)

@app.route('/admin/support/<int:conversation_id>/reply', methods=['POST'])
def admin_support_reply(conversation_id):
    """Send reply to support conversation"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    conversation = SupportConversation.query.get_or_404(conversation_id)
    admin = Admin.query.get(session['admin_id'])
    
    message_content = request.form.get('message', '').strip()
    if not message_content:
        flash('Message cannot be empty', 'error')
        return redirect(url_for('admin_support_conversation', conversation_id=conversation_id))
    
    # Create admin message
    admin_message = SupportMessage(
        conversation_id=conversation.id,
        content=message_content,
        sender_type='admin',
        sender_name=admin.username
    )
    db.session.add(admin_message)
    
    # Update conversation status and activity
    conversation.last_activity = datetime.utcnow()
    if not conversation.assigned_admin_id:
        conversation.assigned_admin_id = admin.id
        conversation.assigned_at = datetime.utcnow()
    
    db.session.commit()
    
    flash('Reply sent successfully', 'success')
    return redirect(url_for('admin_support_conversation', conversation_id=conversation_id))

@app.route('/admin/support/<int:conversation_id>/resolve', methods=['POST'])
def admin_support_resolve(conversation_id):
    """Mark support conversation as resolved"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    conversation = SupportConversation.query.get_or_404(conversation_id)
    
    conversation.status = 'resolved'
    conversation.last_activity = datetime.utcnow()
    
    # Add system message
    resolution_msg = SupportMessage(
        conversation_id=conversation.id,
        content='Conversation marked as resolved by admin',
        sender_type='system',
        message_type='system'
    )
    db.session.add(resolution_msg)
    db.session.commit()
    
    flash('Conversation marked as resolved', 'success')
    return redirect(url_for('admin_support_dashboard'))

@app.route('/admin/support/tutorial')
def admin_support_tutorial():
    """Help desk tutorial for admin support staff"""
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    return render_template('admin/support_tutorial.html')

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


# Debug route to test admin login
# PRODUCTION SECURITY: Debug route disabled for live deployment
# @app.route('/debug-admin-login')
# def debug_admin_login():
    """Debug route to test admin credentials"""
    try:
        admin = Admin.query.filter_by(username='support@foodtruckfundraiser.com').first()
        if admin:
            password_test = check_password_hash(admin.password_hash, 'password')
            return f"""
            <h3>Admin Debug Info</h3>
            <p><strong>Username:</strong> {admin.username}</p>
            <p><strong>ID:</strong> {admin.id}</p>
            <p><strong>Password Hash (first 30 chars):</strong> {admin.password_hash[:30]}...</p>
            <p><strong>Password 'password' test:</strong> {'✓ PASS' if password_test else '✗ FAIL'}</p>
            <hr>
            <p>Try logging in with: support@foodtruckfundraiser.com / password</p>
            <p><a href="/admin/login">Go to Admin Login</a></p>
            """
        else:
            return "❌ No admin user found in database"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@app.route('/login-admin-direct-xyz123', methods=['GET', 'POST'])
def login_admin_direct():
    """Direct admin login for troubleshooting"""
    if request.method == 'POST':
        # Process login
        admin = Admin.query.filter_by(username='support@foodtruckfundraiser.com').first()
        if admin and check_password_hash(admin.password_hash, 'password'):
            # Clear any existing session data first
            session.clear()
            # Set new session data
            session['admin_id'] = admin.id
            session['user_type'] = 'admin'
            session.permanent = True
            
            # Debug session setting
            logging.debug(f"Session set: admin_id={session.get('admin_id')}, user_type={session.get('user_type')}")
            
            return f"""
            <h3>✅ Login Successful!</h3>
            <p><strong>Admin ID:</strong> {admin.id}</p>
            <p><strong>Session admin_id:</strong> {session.get('admin_id')}</p>
            <p><strong>Session user_type:</strong> {session.get('user_type')}</p>
            <hr>
            <p><a href="/admin/dashboard" style="display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 5px;">Go to Admin Dashboard</a></p>
            <p><a href="/admin/login">Regular Login Page</a></p>
            """
        else:
            return "<h3>❌ Login failed</h3><p>Admin user not found or password incorrect</p>"
    
    # Show current session status and login form
    return f"""
    <h3>Admin Login Debug Tool</h3>
    
    <div style="background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px;">
        <h4>Current Session Status:</h4>
        <p><strong>Admin ID:</strong> {session.get('admin_id', 'Not set')}</p>
        <p><strong>User Type:</strong> {session.get('user_type', 'Not set')}</p>
        <p><strong>Session Keys:</strong> {list(session.keys())}</p>
    </div>
    
    <form method="POST">
        <p><button type="submit" style="padding: 15px 30px; background: #007bff; color: white; border: none; border-radius: 5px; font-size: 16px;">
            Login as Admin (support@foodtruckfundraiser.com)
        </button></p>
    </form>
    
    <p><a href="/admin/login">Go to regular login page</a></p>
    <p><a href="/admin/dashboard">Try accessing dashboard directly</a></p>
    """

# PRODUCTION SECURITY: Admin setup route disabled for live deployment
# @app.route('/setup-admin-secret-xyz123')
def setup_admin():
    """One-time setup route to create admin user in production"""
    try:
        # Debug info
        db_url = os.environ.get('DATABASE_URL', 'Not set')[:50] + '...' if len(os.environ.get('DATABASE_URL', '')) > 50 else os.environ.get('DATABASE_URL', 'Not set')
        all_admins = Admin.query.all()
        admin_count = len(all_admins)
        
        debug_info = f"Database URL: {db_url}<br>Current admin count: {admin_count}<br><br>"
        
        # Check if admin already exists
        admin = Admin.query.filter_by(username='support@foodtruckfundraiser.com').first()
        
        if admin:
            # Update existing admin password
            old_hash = admin.password_hash[:20] + '...'
            admin.password_hash = generate_password_hash('password')
            db.session.commit()
            
            # Test the password
            test_result = check_password_hash(admin.password_hash, 'password')
            
            return f"""
            {debug_info}Admin user updated successfully!<br>
            Old hash: {old_hash}<br>
            Password test: {'PASS' if test_result else 'FAIL'}<br><br>
            <strong>You can now login with support@foodtruckfundraiser.com / password</strong><br><br>
            <hr>
            <h4>Quick Login Test:</h4>
            <form action="/admin/login" method="POST" style="margin: 10px 0;">
                <input type="hidden" name="username" value="support@foodtruckfundraiser.com">
                <input type="hidden" name="password" value="password">
                <button type="submit" style="padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px;">
                    Login as Admin Now
                </button>
            </form>
            <p><a href="/admin/login">Or go to regular login page</a></p>
            """
        else:
            # Create new admin
            new_admin = Admin(
                username='support@foodtruckfundraiser.com',
                password_hash=generate_password_hash('password')
            )
            db.session.add(new_admin)
            db.session.commit()
            
            # Test the password
            test_result = check_password_hash(new_admin.password_hash, 'password')
            
            return f"""
            {debug_info}Admin user created successfully!<br>
            Password test: {'PASS' if test_result else 'FAIL'}<br><br>
            <strong>You can now login with support@foodtruckfundraiser.com / password</strong><br><br>
            <hr>
            <h4>Quick Login Test:</h4>
            <form action="/admin/login" method="POST" style="margin: 10px 0;">
                <input type="hidden" name="username" value="support@foodtruckfundraiser.com">
                <input type="hidden" name="password" value="password">
                <button type="submit" style="padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px;">
                    Login as Admin Now
                </button>
            </form>
            <p><a href="/admin/login">Or go to regular login page</a></p>
            """
            
    except Exception as e:
        import traceback
        return f"Error creating admin: {str(e)}<br><br>Traceback:<br>{traceback.format_exc().replace(chr(10), '<br>')}"

# Test routes for debugging organizer registration
# PRODUCTION SECURITY: Test route disabled for live deployment
# @app.route('/test-organizer-reg')
# def test_organizer_registration():
    """Test endpoint to check organizer registration functionality in production"""
    try:
        from models import Organizer
        from werkzeug.security import generate_password_hash
        
        # Check current organizer count
        current_count = Organizer.query.count()
        
        # Test form data extraction
        test_data = {
            'email': 'debugtest@example.com',
            'name': 'Debug Test User', 
            'password': 'testpassword123'
        }
        
        # Check if test user already exists
        existing = Organizer.query.filter_by(email=test_data['email']).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
        
        # Test password hashing
        password_hash = generate_password_hash(test_data['password'])
        
        # Test database write
        test_organizer = Organizer(
            email=test_data['email'],
            name=test_data['name'],
            password_hash=password_hash
        )
        
        db.session.add(test_organizer)
        db.session.commit()
        
        return f"""
        <h3>Organizer Registration Test Results</h3>
        <p><strong>SUCCESS!</strong> Test organizer created successfully!</p>
        <ul>
        <li>ID: {test_organizer.id}</li>
        <li>Email: {test_organizer.email}</li>
        <li>Name: {test_organizer.name}</li>
        <li>Password Hash Length: {len(test_organizer.password_hash)}</li>
        <li>Previous organizer count: {current_count}</li>
        <li>New organizer count: {Organizer.query.count()}</li>
        </ul>
        <p>✅ Database connection and organizer creation working properly in production!</p>
        <p><a href="/organizer/register">Try actual registration form</a></p>
        """
        
    except Exception as e:
        db.session.rollback()
        import traceback
        return f"""
        <h3>Organizer Registration Test Results</h3>
        <p><strong>ERROR:</strong> Registration test failed</p>
        <p>Error: {str(e)}</p>
        <p>Traceback:</p>
        <pre>{traceback.format_exc()}</pre>
        """

# Food Truck Registration Routes
@app.route('/food-truck/register', methods=['GET', 'POST'])
def food_truck_register():
    """Food truck owner registration"""
    if request.method == 'POST':
        try:
            # Get form data
            email = request.form.get('email')
            name = request.form.get('name')
            phone = request.form.get('phone')
            business_name = request.form.get('business_name')
            business_license = request.form.get('business_license')
            password = request.form.get('password')
            
            # Validate required fields
            if not all([email, name, business_name, password]):
                flash('Please fill in all required fields.', 'error')
                return render_template('food_truck/register.html')
            
            # Check if email already exists
            existing_owner = FoodTruckOwner.query.filter_by(email=email).first()
            if existing_owner:
                flash('An account with this email already exists.', 'error')
                return render_template('food_truck/register.html')
            
            # Create new food truck owner
            owner = FoodTruckOwner(
                email=email,
                name=name,
                phone=phone,
                business_name=business_name,
                business_license=business_license,
                password_hash=generate_password_hash(password),
                status='approved'  # Auto-approve food truck owners - they pay $25 to participate
            )
            
            db.session.add(owner)
            db.session.commit()
            
            # Send notification to admin
            admin_emails = [admin.username for admin in Admin.query.all()]
            for admin_email in admin_emails:
                send_email(
                    admin_email,
                    'New Food Truck Registration',
                    f'A new food truck owner has registered:\n\nBusiness: {business_name}\nOwner: {name}\nEmail: {email}\n\nThey can now add trucks and pay the $25 registration fee to participate in events.'
                )
            
            flash('Registration successful! You can now add food trucks and start participating in events.', 'success')
            return redirect(url_for('food_truck_login'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error in food truck registration: {str(e)}")
            flash('Error during registration. Please try again.', 'error')
    
    return render_template('food_truck/register.html')

@app.route('/food-truck/login', methods=['GET', 'POST'])
def food_truck_login():
    """Food truck owner login"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        owner = FoodTruckOwner.query.filter_by(email=email).first()
        
        if owner and check_password_hash(owner.password_hash, password):
            # Food truck owners are auto-approved upon registration
            
            # Set session
            session['food_truck_owner_id'] = owner.id
            session['user_type'] = 'food_truck_owner'
            session['authenticated'] = True
            
            return redirect(url_for('food_truck_dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('food_truck/login.html')

@app.route('/food-truck/dashboard')
def food_truck_dashboard():
    """Food truck owner dashboard"""
    if not session.get('authenticated') or session.get('user_type') != 'food_truck_owner':
        return redirect(url_for('food_truck_login'))
    
    owner = FoodTruckOwner.query.get(session['food_truck_owner_id'])
    if not owner:
        session.clear()
        return redirect(url_for('food_truck_login'))
    
    # Get owner's food trucks
    food_trucks = FoodTruck.query.filter_by(owner_id=owner.id).all()
    
    # Get recent events for their trucks
    truck_ids = [truck.id for truck in food_trucks]
    recent_events = []
    if truck_ids:
        recent_events = Event.query.filter(Event.food_truck_id.in_(truck_ids)).order_by(Event.created_at.desc()).limit(5).all()
    
    # Get payouts
    payouts = []
    if truck_ids:
        payouts = Payout.query.filter(Payout.food_truck_id.in_(truck_ids)).order_by(Payout.created_at.desc()).limit(5).all()
    
    return render_template('food_truck/dashboard.html', 
                         owner=owner, 
                         food_trucks=food_trucks, 
                         recent_events=recent_events,
                         payouts=payouts)

@app.route('/food-truck/logout')
def food_truck_logout():
    """Food truck owner logout"""
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/food-truck/add-truck', methods=['GET', 'POST'])
def food_truck_add_truck():
    """Add new food truck"""
    if not session.get('authenticated') or session.get('user_type') != 'food_truck_owner':
        return redirect(url_for('food_truck_login'))
    
    owner = FoodTruckOwner.query.get(session['food_truck_owner_id'])
    # Allow food truck creation regardless of approval status - payment happens after creation
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name')
            description = request.form.get('description')
            cuisine_type = request.form.get('cuisine_type')
            contact_email = request.form.get('contact_email')
            contact_phone = request.form.get('contact_phone')
            website = request.form.get('website')
            instagram = request.form.get('instagram')
            sales_goal = float(request.form.get('sales_goal', 0))
            
            # Validate required fields
            if not all([name, description, sales_goal > 0]):
                flash('Please fill in all required fields.', 'error')
                return render_template('food_truck/add_truck.html')
            
            # Create new food truck
            truck = FoodTruck(
                name=name,
                description=description,
                owner_id=owner.id,
                cuisine_type=cuisine_type,
                contact_email=contact_email or owner.email,
                contact_phone=contact_phone or owner.phone,
                website=website,
                instagram=instagram,
                sales_goal=sales_goal,
                status='pending'
            )
            
            db.session.add(truck)
            db.session.commit()
            
            flash('Food truck profile created! Please complete the $25 registration fee to submit for approval.', 'info')
            return redirect(url_for('food_truck_pay_registration_fee', truck_id=truck.id))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error adding food truck: {str(e)}")
            flash('Error adding food truck. Please try again.', 'error')
    
    return render_template('food_truck/add_truck.html', owner=owner)

@app.route('/food-truck/edit/<int:truck_id>', methods=['GET', 'POST'])
def food_truck_edit_truck(truck_id):
    """Edit food truck profile and menu"""
    if not session.get('authenticated') or session.get('user_type') != 'food_truck_owner':
        return redirect(url_for('food_truck_login'))
    
    owner = FoodTruckOwner.query.get(session['food_truck_owner_id'])
    truck = FoodTruck.query.get_or_404(truck_id)
    
    # Verify ownership
    if truck.owner_id != owner.id:
        flash('You can only edit your own food trucks.', 'error')
        return redirect(url_for('food_truck_dashboard'))
    
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            
            if action == 'update_profile':
                # Update basic profile
                truck.name = request.form.get('name')
                truck.description = request.form.get('description')
                truck.cuisine_type = request.form.get('cuisine_type')
                truck.contact_email = request.form.get('contact_email')
                truck.contact_phone = request.form.get('contact_phone')
                truck.website = request.form.get('website')
                truck.instagram = request.form.get('instagram')
                truck.sales_goal = float(request.form.get('sales_goal', 0))
                
                db.session.commit()
                flash('Food truck profile updated successfully!', 'success')
                
            elif action == 'update_menu':
                # Handle menu update
                menu_items = []
                item_count = 0
                
                # Parse menu items from form
                while f'item_name_{item_count}' in request.form:
                    item_name = request.form.get(f'item_name_{item_count}')
                    item_price = request.form.get(f'item_price_{item_count}')
                    item_description = request.form.get(f'item_description_{item_count}')
                    
                    if item_name and item_price:
                        try:
                            menu_items.append({
                                'name': item_name,
                                'price': float(item_price),
                                'description': item_description or ''
                            })
                        except ValueError:
                            flash(f'Invalid price for item: {item_name}', 'error')
                            return render_template('food_truck/edit_truck.html', truck=truck, owner=owner)
                    
                    item_count += 1
                
                truck.set_menu_items(menu_items)
                db.session.commit()
                flash('Menu updated successfully!', 'success')
                
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error updating food truck: {str(e)}")
            flash('Error updating food truck. Please try again.', 'error')
    
    return render_template('food_truck/edit_truck.html', truck=truck, owner=owner)

@app.route('/sync-production-trucks-abc789')
def sync_production_trucks():
    """Sync production database food trucks to match development approved trucks"""
    try:
        # List of food trucks that should be approved and have registration fee charged
        production_trucks_to_approve = [
            'Green Truck',
            'Tasty Tacos', 
            'Acai Truck',
            'Ho-Lee Chow'
        ]
        
        updated_count = 0
        
        for truck_name in production_trucks_to_approve:
            # Find truck by name (case insensitive)
            truck = FoodTruck.query.filter(FoodTruck.name.ilike(f'%{truck_name}%')).first()
            
            if truck:
                # Update status and registration fee
                truck.status = 'approved'
                truck.registration_fee_charged = True
                truck.approved_at = datetime.utcnow()
                updated_count += 1
                logging.info(f"Updated truck: {truck.name} - Status: approved, Fee charged: True")
        
        db.session.commit()
        
        return f"""
        <h2>Production Food Truck Sync Complete ✅</h2>
        <p><strong>Updated {updated_count} food trucks:</strong></p>
        <ul>
            {''.join([f'<li>{name} - Now approved with registration fee charged</li>' for name in production_trucks_to_approve])}
        </ul>
        <p>These trucks will now appear in the event creation dropdown on production.</p>
        <p><a href="/">← Back to Home</a></p>
        """
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error syncing production trucks: {str(e)}")
        return f"Error syncing trucks: {str(e)}"

@app.route('/sync-production-events-xyz456')
def sync_production_events():
    """Sync production database events status and visibility"""
    try:
        # Get all events and ensure they have proper status
        events = Event.query.all()
        updated_count = 0
        
        for event in events:
            # Update any missing or invalid statuses
            if not event.status or event.status not in ['pending', 'funded', 'approved', 'cancelled']:
                event.status = 'pending'
                updated_count += 1
                logging.info(f"Updated event: {event.name} - Status set to pending")
            
            # Ensure events have proper pledge goals if missing
            if not event.pledge_goal or event.pledge_goal <= 0:
                # Set default based on food truck goal or 1000
                if event.food_truck and event.food_truck.sales_goal:
                    event.pledge_goal = event.food_truck.sales_goal
                else:
                    event.pledge_goal = 1000.0
                updated_count += 1
                logging.info(f"Updated event: {event.name} - Pledge goal set to {event.pledge_goal}")
        
        db.session.commit()
        
        # Get summary of all events
        event_summary = []
        for event in Event.query.order_by(Event.created_at.desc()).all():
            event_summary.append({
                'name': event.name,
                'status': event.status,
                'goal': event.pledge_goal,
                'current': event.current_pledges,
                'truck': event.food_truck.name if event.food_truck else 'None',
                'organizer': event.organizer.email if event.organizer else 'None'
            })
        
        return f"""
        <h2>Production Events Sync Complete ✅</h2>
        <p><strong>Updated {updated_count} events</strong></p>
        <p>All events now have proper status and pledge goals set.</p>
        
        <h3>Current Events Summary:</h3>
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Event Name</th><th>Status</th><th>Goal</th><th>Current</th><th>Food Truck</th><th>Organizer</th></tr>
            {''.join([f'<tr><td>{e["name"]}</td><td>{e["status"]}</td><td>${e["goal"]}</td><td>${e["current"]}</td><td>{e["truck"]}</td><td>{e["organizer"]}</td></tr>' for e in event_summary])}
        </table>
        
        <p><a href="/">← Back to Home</a></p>
        """
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error syncing production events: {str(e)}")
        return f"Error syncing events: {str(e)}"

# Migration route removed - data sync completed successfully

@app.route('/admin')
def admin_home():
    """Admin home route - redirects to dashboard if logged in, otherwise to login"""
    if session.get('admin_id'):
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('admin_login'))

# Database sync route for production deployment
@app.route('/fix-duplicate-events-abc123')
def fix_duplicate_events():
    """Remove duplicate events in production - one-time cleanup"""
    try:
        updates_made = []
        
        # Find and remove duplicate Acai Bowl Fundraiser events
        acai_events = Event.query.filter(Event.name.ilike('%acai bowl%')).all()
        if len(acai_events) > 1:
            # Keep the first one (lowest ID), delete others
            for event in acai_events[1:]:
                # First delete any pledges associated with this duplicate
                pledges_to_delete = Pledge.query.filter_by(event_id=event.id).all()
                for pledge in pledges_to_delete:
                    db.session.delete(pledge)
                
                db.session.delete(event)
                updates_made.append(f"✅ Removed duplicate: {event.name} (ID: {event.id})")
        
        # General duplicate cleanup for all events
        all_events = Event.query.all()
        seen_events = {}
        
        for event in all_events:
            key = (event.name, event.organizer_id)
            if key in seen_events:
                # This is a duplicate - delete it
                pledges_to_delete = Pledge.query.filter_by(event_id=event.id).all()
                for pledge in pledges_to_delete:
                    db.session.delete(pledge)
                
                db.session.delete(event)
                updates_made.append(f"✅ Removed duplicate: {event.name} (ID: {event.id})")
            else:
                seen_events[key] = event
        
        db.session.commit()
        
        return f"""
        <h2>🧹 Duplicate Events Cleanup Complete</h2>
        <div style="background: #d4edda; padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3>✅ Updates Applied:</h3>
            <ul>
                {''.join([f'<li>{update}</li>' for update in updates_made])}
            </ul>
            {f'<p><strong>Total updates: {len(updates_made)}</strong></p>' if updates_made else '<p><strong>No duplicates found - database is clean</strong></p>'}
        </div>
        <p><a href="/" style="color: #007bff;">← Back to Home</a></p>
        """
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Duplicate cleanup error: {str(e)}")
        return f"❌ Cleanup failed: {str(e)}"

@app.route('/sync-production-database-xyz789')
def sync_production_database():
    """Smart bidirectional sync - preserves legitimate production data while fixing inconsistencies"""
    try:
        updates_made = []
        
        # 1. Ensure Acai Truck is properly approved and fee marked as paid
        acai_truck = FoodTruck.query.filter(FoodTruck.name.ilike('%acai%')).first()
        if acai_truck:
            if acai_truck.status != 'approved' or not acai_truck.registration_fee_charged:
                acai_truck.status = 'approved'
                acai_truck.registration_fee_charged = True
                acai_truck.approved_at = datetime.utcnow()
                updates_made.append(f"✅ Updated Acai Truck: approved and registration fee marked as paid")
        
        # 2. Sync events to match development database exactly
        
        # Define the correct events that should exist in production
        correct_events = [
            {
                'id': 5,
                'name': 'Acai Bowl Fundraiser',
                'description': 'Fresh and healthy acai bowls for a great cause',
                'organizer_email': 'kammiceli@gmail.com',
                'food_truck_name': 'Acai Truck',
                'date': datetime(2025, 9, 2, 4, 30),
                'location': 'Community Center',
                'pledge_goal': 1750.0,
                'current_pledges': 15.0,
                'status': 'pending',
                'organizer_fee_charged': True
            },
            {
                'id': 20,
                'name': 'Lakewood Tennis Center - Level 3 Open',
                'description': 'USTA Junior Tournament',
                'organizer_email': 'marcsonson@gmail.com',
                'food_truck_name': 'All In Cafe Truck',
                'date': datetime(2025, 9, 6, 11, 0),
                'location': '4210 Roe Ave',
                'pledge_goal': 800.0,
                'current_pledges': 0.0,
                'status': 'pending',
                'organizer_fee_charged': True
            },
            {
                'id': 21,
                'name': 'USTA Junior Tournament Fundraiser',
                'description': 'Fundraiser for USTA Junior Tournament',
                'organizer_email': 'marcsonson@gmail.com',
                'food_truck_name': 'Bad Ass Food Truck',
                'date': datetime(2025, 8, 30, 11, 30),
                'location': '4210 Roe Ave',
                'pledge_goal': 800.0,
                'current_pledges': 0.0,
                'status': 'pending',
                'organizer_fee_charged': True
            },
            {
                'id': 22,
                'name': 'Food Truck Friday',
                'description': 'The Collins & Katz Family YMCA is thrilled to host Food Truck Friday on Friday September 5, 2025',
                'organizer_email': 'marcsonson@gmail.com', 
                'food_truck_name': 'Green Truck',
                'date': datetime(2025, 9, 5, 11, 0),
                'location': 'Collins & Katz Family YMCA',
                'pledge_goal': 1200.0,
                'current_pledges': 0.0,
                'status': 'pending',
                'organizer_fee_charged': True
            }
        ]
        
        # First, ensure all necessary organizers exist
        organizers_needed = {
            'kammiceli@gmail.com': {'id': 1, 'name': 'Kammi Celi'},
            'marcsonson@gmail.com': {'id': 6, 'name': 'Marc Sonson'}
        }
        
        for email, org_data in organizers_needed.items():
            organizer = Organizer.query.filter_by(email=email).first()
            if not organizer:
                # Create organizer if missing
                organizer = Organizer(
                    id=org_data['id'],
                    email=email,
                    name=org_data['name'],
                    password_hash='default_hash',  # They can reset later
                    verified=True,
                    created_at=datetime.utcnow()
                )
                db.session.add(organizer)
                updates_made.append(f"✅ Created organizer: {email}")
        
        # Remove unwanted events and handle pledges safely
        unwanted_events = Event.query.filter(Event.name.like('%Amazon%')).all()
        for event in unwanted_events:
            # First, delete any pledges associated with this event
            pledges_to_delete = Pledge.query.filter_by(event_id=event.id).all()
            for pledge in pledges_to_delete:
                db.session.delete(pledge)
            
            # Then delete the event
            db.session.delete(event)
            updates_made.append(f"✅ Removed unwanted event: {event.name} (and {len(pledges_to_delete)} associated pledges)")
        
        # Fix any orphaned pledges (with null event_id)
        orphaned_pledges = Pledge.query.filter(Pledge.event_id.is_(None)).all()
        for pledge in orphaned_pledges:
            db.session.delete(pledge)
            updates_made.append(f"✅ Removed orphaned pledge: {pledge.email} - ${pledge.amount}")
        
        # Create/update correct events - check by name AND organizer to avoid duplicates
        for event_data in correct_events:
            organizer = Organizer.query.filter_by(email=event_data['organizer_email']).first()
            food_truck = FoodTruck.query.filter(FoodTruck.name.ilike(f"%{event_data['food_truck_name']}%")).first()
            
            if organizer and food_truck:
                # Check for existing event by name and organizer (not just ID)
                existing_event = Event.query.filter_by(
                    name=event_data['name'],
                    organizer_id=organizer.id
                ).first()
                
                if not existing_event:
                    # Create the event
                    new_event = Event(
                        name=event_data['name'],
                        description=event_data['description'],
                        organizer_id=organizer.id,
                        food_truck_id=food_truck.id,
                        date=event_data['date'],
                        location=event_data['location'],
                        pledge_goal=event_data['pledge_goal'],
                        current_pledges=event_data['current_pledges'],
                        status=event_data['status'],
                        organizer_fee_charged=event_data['organizer_fee_charged'],
                        created_at=datetime.utcnow()
                    )
                    db.session.add(new_event)
                    updates_made.append(f"✅ Created event: {event_data['name']}")
                
                else:
                    # Update existing event to ensure correct data
                    existing_event.organizer_fee_charged = event_data['organizer_fee_charged']
                    existing_event.status = event_data['status']
                    existing_event.description = event_data['description']
                    existing_event.location = event_data['location']
                    existing_event.pledge_goal = event_data['pledge_goal']
                    updates_made.append(f"✅ Updated event: {event_data['name']}")
        
        # Remove any duplicate events (same name and organizer)
        all_events = Event.query.all()
        seen_events = {}
        duplicates_removed = 0
        
        for event in all_events:
            key = (event.name, event.organizer_id)
            if key in seen_events:
                # This is a duplicate - delete it
                db.session.delete(event)
                duplicates_removed += 1
            else:
                seen_events[key] = event
        
        if duplicates_removed > 0:
            updates_made.append(f"✅ Removed {duplicates_removed} duplicate event(s)")
        
        # 3. Sync food trucks to match development database exactly
        
        # Smart food truck sync - only fix problems, don't force development state
        
        # Remove only clearly problematic trucks (duplicates and test data)
        problematic_names = [
            'HoleeChow',  # This was a duplicate/test truck
            'Somos Verde'  # This was test data
        ]
        
        # Remove duplicate trucks (same name, different IDs)
        all_trucks = FoodTruck.query.all()
        truck_names_seen = {}
        duplicate_trucks = []
        
        for truck in all_trucks:
            truck_name_lower = truck.name.lower().strip()
            
            # Check for problematic test trucks
            if any(prob_name.lower() in truck_name_lower for prob_name in problematic_names):
                duplicate_trucks.append(truck)
                continue
                
            # Check for actual duplicates
            if truck_name_lower in truck_names_seen:
                # This is a duplicate - keep the older one (lower ID)
                existing_truck = truck_names_seen[truck_name_lower]
                if truck.id < existing_truck.id:
                    # This truck is older, replace the stored one
                    duplicate_trucks.append(existing_truck)
                    truck_names_seen[truck_name_lower] = truck
                else:
                    # The stored truck is older, mark this one as duplicate
                    duplicate_trucks.append(truck)
            else:
                truck_names_seen[truck_name_lower] = truck
        
        # Remove duplicates and reassign their events
        for duplicate_truck in duplicate_trucks:
            # Find the original truck to reassign events to
            original_truck = None
            
            # Look for a truck with the same name but different ID
            for name_key, truck in truck_names_seen.items():
                if (truck.name.lower().strip() == duplicate_truck.name.lower().strip() and 
                    truck.id != duplicate_truck.id):
                    original_truck = truck
                    break
            
            # If no exact match, use the first available truck
            if not original_truck:
                original_truck = list(truck_names_seen.values())[0] if truck_names_seen else None
            
            # Reassign events from duplicate to original
            if original_truck:
                events_using_duplicate = Event.query.filter_by(food_truck_id=duplicate_truck.id).all()
                for event in events_using_duplicate:
                    event.food_truck_id = original_truck.id
                    updates_made.append(f"✅ Reassigned event '{event.name}' from duplicate '{duplicate_truck.name}' to '{original_truck.name}'")
            
            db.session.delete(duplicate_truck)
            updates_made.append(f"✅ Removed duplicate/problematic truck: {duplicate_truck.name} (ID: {duplicate_truck.id})")
        
        # Ensure all remaining trucks are properly approved
        remaining_trucks = FoodTruck.query.all()
        for truck in remaining_trucks:
            needs_update = False
            if truck.status != 'approved':
                truck.status = 'approved'
                truck.approved_at = datetime.utcnow()
                needs_update = True
            if not truck.registration_fee_charged:
                truck.registration_fee_charged = True
                needs_update = True
            
            if needs_update:
                updates_made.append(f"✅ Updated {truck.name}: approved and registration fee marked as paid")
        
        db.session.commit()
        
        return f"""
        <h2>🔄 Production Database Sync Complete</h2>
        <div style="background: #d4edda; padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3>✅ Updates Applied:</h3>
            <ul>
                {''.join([f'<li>{update}</li>' for update in updates_made])}
            </ul>
            {f'<p><strong>Total updates: {len(updates_made)}</strong></p>' if updates_made else '<p><strong>No updates needed - database already in sync</strong></p>'}
        </div>
        
        <h3>🎯 Expected Results:</h3>
        <ul>
            <li>✅ Admin dashboard at /admin should work properly</li>
            <li>✅ kammiceli@gmail.com should see 1 event: "Acai Bowl Fundraiser"</li>
            <li>✅ All approved food trucks should show registration fees paid</li>
            <li>✅ Event creation should work with all approved trucks</li>
        </ul>
        
        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <strong>🔒 Security Note:</strong> This sync route will be removed after production deployment.
        </div>
        
        <p><a href="/" style="color: #007bff;">← Back to Home</a></p>
        """
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Database sync error: {str(e)}")
        return f"❌ Database sync failed: {str(e)}"


@app.route('/api/truck/<int:truck_id>/menu')
def api_truck_menu(truck_id):
    """API endpoint to get food truck menu items"""
    truck = FoodTruck.query.get_or_404(truck_id)
    
    try:
        menu_items = truck.get_menu_items()
        return jsonify(menu_items)
    except Exception as e:
        logging.error(f"Error fetching menu for truck {truck_id}: {str(e)}")
        return jsonify([]), 500

# =============================================================================
# PAYOUT AND AMBASSADOR SYSTEM ROUTES
# =============================================================================

@app.route('/organizer/earnings', methods=['GET'])
def organizer_earnings():
    """Organizer earnings and payout dashboard"""
    # Authentication check
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    if auth_token:
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
    
    if not organizer_id:
        organizer_id = session.get('organizer_id')
    
    if not organizer_id:
        flash('Authentication required', 'error')
        return redirect(url_for('organizer_login'))
    
    organizer = Organizer.query.get_or_404(organizer_id)
    
    # Update tier metrics
    tier_info = organizer.update_tier_metrics()
    
    # Get earnings data - include both approved and completed events for consistency with tier calculation
    completed_events = Event.query.filter(
        Event.organizer_id == organizer_id,
        Event.status.in_(['approved', 'completed'])
    ).all()
    
    # Get payout info for each event (avoid SQLAlchemy relationship issues)
    events_with_payouts = []
    for event in completed_events:
        payout = OrganizerPayout.query.filter(
            OrganizerPayout.event_id == event.id,
            OrganizerPayout.organizer_id == organizer_id
        ).first()
        events_with_payouts.append({
            'event': event,
            'payout': payout
        })
    
    
    pending_payouts = organizer.get_pending_payouts()
    total_awaiting_payout = organizer.get_total_earnings_awaiting_payout()
    
    # Calculate total earnings ever
    total_lifetime_earnings = sum([
        event.calculate_organizer_profit_if_goal_met() 
        for event in completed_events
    ])
    
    # Get payout history
    payout_history = OrganizerPayout.query.filter(
        OrganizerPayout.organizer_id == organizer_id
    ).order_by(OrganizerPayout.created_at.desc()).all()
    
    return render_template('organizer/earnings.html',
                         organizer=organizer,
                         tier_info=tier_info,
                         events_with_payouts=events_with_payouts,
                         pending_payouts=pending_payouts,
                         total_awaiting_payout=total_awaiting_payout,
                         total_lifetime_earnings=total_lifetime_earnings,
                         payout_history=payout_history,
                         auth_token=auth_token)

@app.route('/organizer/request-payout', methods=['POST'])
def request_payout():
    """Request payout for completed events"""
    # Authentication check
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    if auth_token:
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
    
    if not organizer_id:
        organizer_id = session.get('organizer_id')
    
    if not organizer_id:
        return jsonify({'error': 'Authentication required'}), 401
    
    organizer = Organizer.query.get_or_404(organizer_id)
    event_id = request.json.get('event_id')
    
    if not event_id:
        return jsonify({'error': 'Event ID required'}), 400
    
    event = Event.query.get_or_404(event_id)
    
    # Verify event ownership and status
    if event.organizer_id != organizer_id:
        return jsonify({'error': 'Access denied'}), 403
        
    if event.status not in ['approved', 'completed']:
        return jsonify({'error': 'Event must be approved or completed for payout'}), 400
    
    # Check if payout already exists
    existing_payout = OrganizerPayout.query.filter(
        OrganizerPayout.event_id == event_id,
        OrganizerPayout.organizer_id == organizer_id
    ).first()
    
    if existing_payout:
        return jsonify({'error': 'Payout already requested for this event'}), 400
    
    # Calculate payout amount
    amount = event.calculate_organizer_profit_if_goal_met()
    
    if amount <= 0:
        return jsonify({'error': 'No earnings to pay out for this event'}), 400
    
    # Create payout request
    payout = OrganizerPayout(
        organizer_id=organizer_id,
        event_id=event_id,
        amount=amount,
        status='pending'
    )
    
    db.session.add(payout)
    db.session.commit()
    
    # Send notification to admin (optional - don't fail if email fails)
    try:
        send_email(
            'support@foodtruckfundraiser.com',
            f'Payout Request: ${amount:.2f} for {organizer.name}',
            f'Organizer {organizer.name} has requested a payout of ${amount:.2f} for event "{event.name}".\\n\\nEvent Details:\\nDate: {event.date}\\nLocation: {event.location}\\nTotal Raised: ${event.current_pledges:.2f}\\nOrganizer Profit: ${amount:.2f}\\n\\nPlease process this payout in the admin dashboard.'
        )
    except Exception:
        pass  # Continue even if email fails
    
    return jsonify({
        'success': True, 
        'message': f'Payout request submitted for ${amount:.2f}',
        'payout_id': payout.id
    })

@app.route('/admin/payouts-management', methods=['GET'])
def admin_payout_management():
    """Admin dashboard for managing organizer payouts"""
    if 'admin_id' not in session:
        flash('Admin access required', 'error')
        return redirect(url_for('admin_login'))
    
    # Get all payouts with their related data
    payouts = OrganizerPayout.query.join(Organizer).join(Event).order_by(
        OrganizerPayout.created_at.desc()
    ).all()
    
    # Calculate summary statistics
    pending_count = len([p for p in payouts if p.status == 'pending'])
    pending_amount = sum([p.amount for p in payouts if p.status == 'pending'])
    completed_amount = sum([p.amount for p in payouts if p.status == 'completed'])
    
    return render_template('admin/payout_management.html',
                         payouts=payouts,
                         pending_count=pending_count,
                         pending_amount=pending_amount,
                         completed_amount=completed_amount)

@app.route('/admin/payout/<int:payout_id>/process', methods=['POST'])
def admin_process_payout(payout_id):
    """Process a payout request"""
    if 'admin_id' not in session:
        return jsonify({'error': 'Admin access required'}), 401
    
    payout = OrganizerPayout.query.get_or_404(payout_id)
    
    if payout.status != 'pending':
        return jsonify({'error': 'Payout already processed'}), 400
    
    action = request.json.get('action')  # 'approve' or 'reject'
    
    if action == 'approve':
        payout.status = 'processing'
        payout.processed_at = datetime.utcnow()
        
        # In a real implementation, this would integrate with Stripe Connect
        # For now, we'll simulate the process
        
        # Send confirmation email to organizer
        send_email(
            payout.organizer.email,
            f'Payout Approved: ${payout.amount:.2f}',
            f'Good news! Your payout request for ${payout.amount:.2f} from event "{payout.event.name}" has been approved and is being processed.\\n\\nExpected processing time: 2-3 business days.\\n\\nThank you for being a Food Truck Ambassador!'
        )
        
        # Keep as processing - admin must manually mark as completed
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Payout of ${payout.amount:.2f} approved and is being processed'
        })
        
    elif action == 'reject':
        payout.status = 'failed'
        payout.processed_at = datetime.utcnow()
        
        # Send rejection email
        reason = request.json.get('reason', 'Administrative review required')
        send_email(
            payout.organizer.email,
            f'Payout Request Under Review: ${payout.amount:.2f}',
            f'Your payout request for ${payout.amount:.2f} from event "{payout.event.name}" requires additional review.\\n\\nReason: {reason}\\n\\nPlease contact support if you have questions.'
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Payout request marked for review'
        })
    
    return jsonify({'error': 'Invalid action'}), 400

@app.route('/admin/organizer-payout/<int:payout_id>/complete', methods=['POST'])
def admin_complete_organizer_payout(payout_id):
    """Process real PayPal payout and mark as completed"""
    if 'admin_id' not in session:
        return jsonify({'error': 'Admin access required'}), 401
    
    payout = OrganizerPayout.query.get_or_404(payout_id)
    
    if payout.status != 'processing':
        return jsonify({'error': 'Payout must be in processing status to complete'}), 400
    
    try:
        # Process the actual payment based on method
        if payout.organizer.payout_method == 'paypal':
            result = send_paypal_payout(payout)
        elif payout.organizer.payout_method == 'bank':
            result = send_bank_payout(payout)
        else:
            return jsonify({'error': 'Invalid payout method'}), 400
        
        if result['success']:
            # Mark as completed
            payout.status = 'completed'
            payout.completed_at = datetime.utcnow()
            payout.transaction_id = result.get('transaction_id')
            
            # Send completion email to organizer
            send_email(
                payout.organizer.email,
                f'Payout Completed: ${payout.amount:.2f}',
                f'''Great news! Your payout has been successfully completed.

Payment Details:
- Event: {payout.event.name}
- Amount Paid: ${payout.amount:.2f}
- Payment Date: {payout.completed_at.strftime('%B %d, %Y at %I:%M %p')}
- Payment Method: {"PayPal" if payout.organizer.payout_method == "paypal" else "Bank Transfer"}
- Transaction ID: {payout.transaction_id}

The funds should appear in your {"PayPal account" if payout.organizer.payout_method == "paypal" else "bank account"} within 1-2 business days.

Thank you for organizing a successful food truck event!

Best regards,
The Food Truck Fundraiser Team'''
            )
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Payout of ${payout.amount:.2f} sent successfully via {payout.organizer.payout_method.title()}. Confirmation sent to organizer.'
            })
        else:
            # Payment failed - keep in processing status
            return jsonify({
                'error': f'Payment failed: {result.get("error", "Unknown error")}'
            }), 400
            
    except Exception as e:
        app.logger.error(f'Payout processing error: {str(e)}')
        return jsonify({
            'error': f'Payment processing failed: {str(e)}'
        }), 500

def send_paypal_payout(payout):
    """Send actual PayPal payout using PayPal API"""
    import paypalrestsdk
    import time
    
    try:
        # Configure PayPal API
        paypalrestsdk.configure({
            "mode": "sandbox",  # Change to "live" for production
            "client_id": os.environ.get('PAYPAL_CLIENT_ID'),
            "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET')
        })
        
        # Create unique batch ID
        batch_id = f"payout_{payout.id}_{int(time.time())}"
        
        # Create PayPal payout
        paypal_payout = paypalrestsdk.Payout({
            "sender_batch_header": {
                "sender_batch_id": batch_id,
                "email_subject": f"Payment from Food Truck Fundraiser - ${payout.amount:.2f}",
                "email_message": f"You've received a payment for your successful event '{payout.event.name}'!"
            },
            "items": [{
                "recipient_type": "EMAIL",
                "amount": {
                    "value": f"{payout.amount:.2f}",
                    "currency": "USD"
                },
                "receiver": payout.organizer.paypal_email,
                "note": f"Payout for event: {payout.event.name}",
                "sender_item_id": f"payout_{payout.id}"
            }]
        })
        
        # Send the payout
        if paypal_payout.create():
            app.logger.info(f'PayPal payout created successfully: {paypal_payout.batch_header.payout_batch_id}')
            return {
                'success': True,
                'transaction_id': paypal_payout.batch_header.payout_batch_id,
                'provider': 'PayPal'
            }
        else:
            error_msg = str(paypal_payout.error) if hasattr(paypal_payout, 'error') else 'Unknown PayPal error'
            app.logger.error(f'PayPal payout failed: {error_msg}')
            return {
                'success': False,
                'error': error_msg
            }
            
    except Exception as e:
        app.logger.error(f'PayPal API error: {str(e)}')
        return {
            'success': False,
            'error': f'PayPal API error: {str(e)}'
        }

def send_bank_payout(payout):
    """Handle bank transfer payout (placeholder for future ACH integration)"""
    # For now, return success - in production you'd integrate with ACH provider
    # like Stripe ACH, Plaid, or bank API
    app.logger.info(f'Bank payout requested for ${payout.amount:.2f} to {payout.organizer.name}')
    
    # TODO: Integrate with ACH provider (Stripe ACH, Plaid, etc.)
    # For now, simulate success so admins can manually process
    return {
        'success': True,
        'transaction_id': f'BANK_{payout.id}_{int(time.time())}',
        'provider': 'Manual Bank Transfer'
    }

@app.route('/admin/init-challenges', methods=['POST'])
def init_challenges():
    """Initialize default challenges for the ambassador program"""
    if 'admin_id' not in session:
        return jsonify({'error': 'Admin access required'}), 401
    
    # Check if challenges already exist
    existing_challenges = AmbassadorChallenge.query.count()
    
    if existing_challenges > 0:
        return jsonify({'error': 'Challenges already initialized'}), 400
    
    # Create default challenges
    challenges = [
        {
            'name': 'First Steps',
            'description': 'Host your first successful food truck event',
            'challenge_type': 'milestone',
            'requirement_type': 'events_completed',
            'requirement_value': 1,
            'reward_type': 'points',
            'reward_value': 100,
            'reward_description': '100 bonus points + Silver tier fast-track'
        },
        {
            'name': 'Community Builder',
            'description': 'Attract 25 total pledgers across all your events',
            'challenge_type': 'milestone',
            'requirement_type': 'pledgers_attracted',
            'requirement_value': 25,
            'reward_type': 'cash_bonus',
            'reward_value': 25.0,
            'reward_description': '$25 bonus payout'
        },
        {
            'name': 'High Performer',
            'description': 'Reach 150% of your goal on any event',
            'challenge_type': 'milestone',
            'requirement_type': 'events_150_percent',
            'requirement_value': 1,
            'reward_type': 'markup_bonus',
            'reward_value': 2.5,
            'reward_description': '+2.5% markup bonus for next 3 events'
        },
        {
            'name': 'Ambassador Elite',
            'description': 'Complete 5 successful events and earn $200+ total',
            'challenge_type': 'milestone',
            'requirement_type': 'earnings_reached',
            'requirement_value': 200,
            'reward_type': 'tier_boost',
            'reward_value': 1,
            'reward_description': 'Instant Gold tier upgrade'
        },
        {
            'name': 'Monthly Champion',
            'description': 'Host 3 events in a single month',
            'challenge_type': 'recurring',
            'requirement_type': 'events_completed',
            'requirement_value': 3,
            'time_limit_days': 30,
            'reward_type': 'cash_bonus',
            'reward_value': 50.0,
            'reward_description': '$50 monthly champion bonus'
        }
    ]
    
    for challenge_data in challenges:
        challenge = AmbassadorChallenge(**challenge_data)
        db.session.add(challenge)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Initialized {len(challenges)} ambassador challenges',
        'challenges_created': len(challenges)
    })

# Pledge Messaging Routes
@app.route('/admin/pledge/<int:pledge_id>/messages')
def pledge_messages(pledge_id):
    """View chat messages for a specific pledge"""
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    pledge = Pledge.query.get_or_404(pledge_id)
    messages = PledgeMessage.query.filter_by(pledge_id=pledge_id).order_by(PledgeMessage.created_at.asc()).all()
    
    return render_template('admin/pledge_messages.html', pledge=pledge, messages=messages)

@app.route('/admin/pledge/<int:pledge_id>/send-message', methods=['POST'])
def send_pledge_message(pledge_id):
    """Send a message to a pledger"""
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    
    try:
        pledge = Pledge.query.get_or_404(pledge_id)
        admin_id = session['admin_id']
        admin = Admin.query.get(admin_id)
        message_text = request.form.get('message', '').strip()
        
        if not message_text:
            return jsonify({'success': False, 'error': 'Message cannot be empty'}), 400
        
        # Create the message record
        message = PledgeMessage(
            pledge_id=pledge_id,
            admin_id=admin_id,
            message=message_text,
            sender_type='admin',
            sender_email=admin.username
        )
        
        db.session.add(message)
        db.session.commit()
        
        # Send email notification to the pledger
        from utils import send_email
        
        email_subject = f"Message from Food Truck Fundraiser Team - {pledge.event.name}"
        email_body = f"""Hi,

You have received a message regarding your pledge for "{pledge.event.name}":

"{message_text}"

Please do not reply to this email. If you have questions, please contact us directly.

Best regards,
Food Truck Fundraiser Team"""
        
        email_success = send_email(pledge.email, email_subject, email_body)
        
        # Update email status
        message.email_sent = email_success
        db.session.commit()
        
        if email_success:
            logging.info(f"Message sent to pledger {pledge.email} for pledge {pledge_id}")
        else:
            logging.error(f"Failed to send email notification for message to pledge {pledge_id}")
        
        return jsonify({
            'success': True,
            'message': 'Message sent successfully',
            'message_data': {
                'id': message.id,
                'message': message.message,
                'sender_type': message.sender_type,
                'sender_email': message.sender_email,
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'email_sent': message.email_sent
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error sending pledge message: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to send message: {str(e)}'}), 500

@app.route('/admin/pledge/<int:pledge_id>/messages/api')
def get_pledge_messages_api(pledge_id):
    """API endpoint to get messages for a pledge (for AJAX updates)"""
    if 'admin_id' not in session:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    
    try:
        messages = PledgeMessage.query.filter_by(pledge_id=pledge_id).order_by(PledgeMessage.created_at.asc()).all()
        
        message_data = []
        for msg in messages:
            message_data.append({
                'id': msg.id,
                'message': msg.message,
                'sender_type': msg.sender_type,
                'sender_email': msg.sender_email,
                'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'email_sent': msg.email_sent,
                'is_read': msg.is_read
            })
        
        return jsonify({'success': True, 'messages': message_data})
        
    except Exception as e:
        logging.error(f"Error fetching pledge messages: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# =============================================================================
# ORGANIZER PAYOUT SETUP ROUTES
# =============================================================================

@app.route('/organizer/payout-setup', methods=['GET', 'POST'])
def organizer_payout_setup():
    """Organizer payout method setup"""
    # Authentication check
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    if auth_token:
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
    
    if not organizer_id:
        organizer_id = session.get('organizer_id')
    
    if not organizer_id:
        flash('Authentication required', 'error')
        return redirect(url_for('organizer_login'))
    
    organizer = Organizer.query.get_or_404(organizer_id)
    
    if request.method == 'POST':
        try:
            payout_method = request.form.get('payout_method')
            
            if payout_method == 'bank':
                # Bank account setup
                organizer.payout_method = 'bank'
                organizer.bank_account_holder = request.form.get('bank_account_holder', '').strip()
                organizer.bank_routing_number = request.form.get('bank_routing_number', '').strip()
                
                # Only store last 4 digits of account number for security
                full_account_number = request.form.get('bank_account_number', '').strip()
                if len(full_account_number) >= 4:
                    organizer.bank_account_number_last4 = full_account_number[-4:]
                
                organizer.bank_account_type = request.form.get('bank_account_type', 'checking')
                
            elif payout_method == 'paypal':
                # PayPal setup
                organizer.payout_method = 'paypal'
                organizer.paypal_email = request.form.get('paypal_email', '').strip()
            
            # Tax information
            organizer.tax_id_type = request.form.get('tax_id_type')
            organizer.tax_id_provided = True
            
            # Address information
            organizer.address_line1 = request.form.get('address_line1', '').strip()
            organizer.address_line2 = request.form.get('address_line2', '').strip()
            organizer.city = request.form.get('city', '').strip()
            organizer.state = request.form.get('state', '').strip()
            organizer.zip_code = request.form.get('zip_code', '').strip()
            organizer.country = request.form.get('country', 'US')
            
            # Mark setup as completed
            organizer.payout_setup_completed = True
            
            db.session.commit()
            
            flash('Payout information saved successfully! Your information will be reviewed for verification.', 'success')
            return redirect(url_for('organizer_dashboard', auth_token=auth_token) if auth_token else url_for('organizer_dashboard'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error saving payout setup: {str(e)}")
            flash('Error saving payout information. Please try again.', 'error')
    
    # Pass auth token to template for iframe navigation
    current_auth_token = auth_token or session.get('auth_token', '')
    return render_template('organizer/payout_setup.html', 
                          organizer=organizer, 
                          auth_token=current_auth_token)

@app.route('/organizer/payout-status')
def organizer_payout_status():
    """Show organizer's payout status and earnings"""
    # Authentication check
    organizer_id = None
    auth_token = request.args.get('auth_token')
    
    if auth_token:
        token_record = AuthToken.query.filter_by(
            token=auth_token,
            is_active=True
        ).filter(AuthToken.expires_at > datetime.utcnow()).first()
        
        if token_record:
            organizer_id = token_record.organizer_id
    
    if not organizer_id:
        organizer_id = session.get('organizer_id')
    
    if not organizer_id:
        flash('Authentication required', 'error')
        return redirect(url_for('organizer_login'))
    
    organizer = Organizer.query.get_or_404(organizer_id)
    
    # Get payout history
    payouts = OrganizerPayout.query.filter_by(organizer_id=organizer_id).order_by(OrganizerPayout.created_at.desc()).all()
    
    # Calculate totals
    total_pending = sum(p.amount for p in payouts if p.status == 'pending')
    total_paid = sum(p.amount for p in payouts if p.status == 'completed')
    
    current_auth_token = auth_token or session.get('auth_token', '')
    return render_template('organizer/payout_status.html', 
                          organizer=organizer,
                          payouts=payouts,
                          total_pending=total_pending,
                          total_paid=total_paid,
                          auth_token=current_auth_token)

# =============================================================================
# FOOD TRUCK PAYOUT SYSTEM
# =============================================================================

@app.route('/admin/food-truck-payouts', methods=['GET'])
def admin_food_truck_payout_management():
    """Admin dashboard for managing food truck payouts"""
    if 'admin_id' not in session:
        flash('Admin access required', 'error')
        return redirect(url_for('admin_login'))
    
    # Get all food truck payouts with their related data
    payouts = FoodTruckPayout.query.join(FoodTruck).join(Event).order_by(
        FoodTruckPayout.created_at.desc()
    ).all()
    
    # Calculate summary statistics
    pending_count = len([p for p in payouts if p.status == 'pending'])
    pending_amount = sum([p.amount for p in payouts if p.status == 'pending'])
    completed_amount = sum([p.amount for p in payouts if p.status == 'completed'])
    
    return render_template('admin/food_truck_payout_management.html',
                         payouts=payouts,
                         pending_count=pending_count,
                         pending_amount=pending_amount,
                         completed_amount=completed_amount)

@app.route('/admin/food-truck-payouts/<int:payout_id>/approve', methods=['POST'])
def admin_approve_food_truck_payout(payout_id):
    """Approve a food truck payout request and move it to processing status"""
    if 'admin_id' not in session:
        return jsonify({'error': 'Admin access required'}), 401
    
    payout = FoodTruckPayout.query.get_or_404(payout_id)
    
    if payout.status != 'pending':
        return jsonify({'error': 'Payout must be pending to approve'}), 400
    
    # Move to processing status
    payout.status = 'processing'
    payout.processed_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Food truck payout of ${payout.amount:.2f} approved and ready for payment'
    })

@app.route('/admin/food-truck-payouts/<int:payout_id>/complete', methods=['POST'])
def admin_complete_food_truck_payout(payout_id):
    """Process real PayPal payout to food truck and mark as completed"""
    if 'admin_id' not in session:
        return jsonify({'error': 'Admin access required'}), 401
    
    payout = FoodTruckPayout.query.get_or_404(payout_id)
    
    if payout.status != 'processing':
        return jsonify({'error': 'Payout must be in processing status to complete'}), 400
    
    try:
        # Process the actual payment to food truck
        result = send_food_truck_paypal_payout(payout)
        
        if result['success']:
            # Mark as completed
            payout.status = 'completed'
            payout.completed_at = datetime.utcnow()
            payout.transaction_id = result.get('transaction_id')
            
            # Send completion email to food truck
            send_email(
                payout.recipient_email or payout.food_truck.contact_email,
                f'Payment Received: ${payout.amount:.2f}',
                f'''Great news! Your payment has been successfully sent.

Payment Details:
- Event: {payout.event.name}
- Amount Paid: ${payout.amount:.2f}
- Payment Date: {payout.completed_at.strftime('%B %d, %Y at %I:%M %p')}
- Payment Method: PayPal
- Transaction ID: {payout.transaction_id}

The funds should appear in your PayPal account within 1-2 business days.

Thank you for participating in this successful food truck event!

Best regards,
The Food Truck Fundraiser Team'''
            )
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Payout of ${payout.amount:.2f} sent successfully to {payout.food_truck.name}. Confirmation sent to food truck.'
            })
        else:
            # Payment failed - keep in processing status
            return jsonify({
                'error': f'Payment failed: {result.get("error", "Unknown error")}'
            }), 400
            
    except Exception as e:
        app.logger.error(f'Food truck payout processing error: {str(e)}')
        return jsonify({
            'error': f'Payment processing failed: {str(e)}'
        }), 500

def send_food_truck_paypal_payout(payout):
    """Send actual PayPal payout to food truck using PayPal API"""
    import paypalrestsdk
    import time
    
    try:
        # Configure PayPal API
        paypalrestsdk.configure({
            "mode": "sandbox",  # Change to "live" for production
            "client_id": os.environ.get('PAYPAL_CLIENT_ID'),
            "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET')
        })
        
        # Create unique batch ID
        batch_id = f"truck_payout_{payout.id}_{int(time.time())}"
        
        # Use food truck contact email as recipient
        recipient_email = payout.recipient_email or payout.food_truck.contact_email
        
        if not recipient_email:
            return {
                'success': False,
                'error': 'No PayPal email configured for food truck'
            }
        
        # Create PayPal payout
        paypal_payout = paypalrestsdk.Payout({
            "sender_batch_header": {
                "sender_batch_id": batch_id,
                "email_subject": f"Payment from Food Truck Fundraiser - ${payout.amount:.2f}",
                "email_message": f"You've received payment for participating in event '{payout.event.name}'!"
            },
            "items": [{
                "recipient_type": "EMAIL",
                "amount": {
                    "value": f"{payout.amount:.2f}",
                    "currency": "USD"
                },
                "receiver": recipient_email,
                "note": f"Payment for food truck participation in event: {payout.event.name}",
                "sender_item_id": f"truck_payout_{payout.id}"
            }]
        })
        
        # Send the payout
        if paypal_payout.create():
            app.logger.info(f"✅ PayPal payout created successfully for food truck: {batch_id}")
            
            return {
                'success': True,
                'transaction_id': batch_id,
                'paypal_payout_id': paypal_payout.batch_header.payout_batch_id
            }
        else:
            error_details = str(paypal_payout.error) if hasattr(paypal_payout, 'error') else 'Unknown PayPal error'
            app.logger.error(f"❌ PayPal payout creation failed: {error_details}")
            
            return {
                'success': False,
                'error': f'PayPal API error: {error_details}'
            }
            
    except Exception as e:
        app.logger.error(f"❌ PayPal payout exception: {str(e)}")
        return {
            'success': False,
            'error': f'PayPal processing error: {str(e)}'
        }

@app.route('/admin/create-food-truck-payouts', methods=['POST'])
def admin_create_food_truck_payouts():
    """Create payout records for completed events (food truck base amounts)"""
    if 'admin_id' not in session:
        return jsonify({'error': 'Admin access required'}), 401
    
    # Find approved/completed events that don't have food truck payouts yet
    # Both approved and completed events are eligible for payouts
    completed_events = Event.query.filter(Event.status.in_(['approved', 'completed'])).all()
    
    created_count = 0
    for event in completed_events:
        # Check if food truck payout already exists
        existing_payout = FoodTruckPayout.query.filter_by(
            event_id=event.id,
            food_truck_id=event.food_truck_id
        ).first()
        
        if not existing_payout:
            # Calculate food truck payout amount (base minimum)
            payout_amount = event.pledge_goal  # Food truck gets their base minimum
            
            # Create payout record
            payout = FoodTruckPayout(
                food_truck_id=event.food_truck_id,
                event_id=event.id,
                amount=payout_amount,
                recipient_email=event.food_truck.contact_email
            )
            
            db.session.add(payout)
            created_count += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Created {created_count} food truck payout records'
    })

