from flask import render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from app import app, db, mail
from models import Admin, Organizer, FoodTruck, Event, Pledge, EmailLog
from utils import send_email, generate_ticket_code, create_stripe_payment_intent, charge_stripe_payment
import stripe
import os
import json
import logging
from datetime import datetime

# Configure Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_...')

@app.route('/')
def index():
    """Homepage with overview and navigation"""
    recent_events = Event.query.filter(Event.status.in_(['pending', 'funded'])).order_by(Event.created_at.desc()).limit(3).all()
    return render_template('index.html', recent_events=recent_events)

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Debug logging
        logging.debug(f"Admin login attempt for username: {username}")
        
        admin = Admin.query.filter_by(username=username).first()
        logging.debug(f"Admin found in database: {admin is not None}")
        
        if admin:
            password_valid = check_password_hash(admin.password_hash, password)
            logging.debug(f"Password validation result: {password_valid}")
            
            if password_valid:
                session['admin_id'] = admin.id
                session['user_type'] = 'admin'
                logging.debug(f"Admin logged in successfully, session set with admin_id: {admin.id}")
                flash('Successfully logged in as admin', 'success')
                return redirect(url_for('admin_dashboard'))
        
        logging.debug("Login failed - invalid credentials")
        flash('Invalid credentials', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('user_type', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

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
    
    return render_template('admin/dashboard.html', 
                         total_trucks=total_trucks,
                         total_events=total_events,
                         pending_events=pending_events,
                         funded_events=funded_events,
                         recent_events=recent_events)

@app.route('/debug-database-xyz123')
def debug_database():
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
                results.append(f"Updated: {truck_data['name']}")
            else:
                # Create new truck
                new_truck = FoodTruck(
                    name=truck_data['name'],
                    description=truck_data['description'],
                    menu_items=json.dumps(truck_data['menu_items']),
                    sales_goal=truck_data['sales_goal']
                )
                db.session.add(new_truck)
                results.append(f"Created: {truck_data['name']}")
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Data sync completed',
            'results': results,
            'total_trucks': FoodTruck.query.count()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Error syncing data: {str(e)}'
        })

@app.route('/test-admin-login-xyz123', methods=['GET', 'POST'])
def test_admin_login():
    """Test admin login functionality for debugging"""
    if request.method == 'POST':
        username = request.form.get('username', 'truckstopsla@gmail.com')
        password = request.form.get('password', 'password')
        
        try:
            admin = Admin.query.filter_by(username=username).first()
            if admin:
                password_valid = check_password_hash(admin.password_hash, password)
                
                if password_valid:
                    session['admin_id'] = admin.id
                    session['user_type'] = 'admin'
                    return f"""
                    <h3>✅ Login Test Successful!</h3>
                    <p><strong>Admin ID:</strong> {admin.id}</p>
                    <p><strong>Username:</strong> {admin.username}</p>
                    <p><strong>Session Set:</strong> admin_id = {session.get('admin_id')}</p>
                    <p><strong>Session Type:</strong> {session.get('user_type')}</p>
                    <hr>
                    <p><a href="/admin/dashboard">Go to Admin Dashboard</a></p>
                    <p><a href="/admin/login">Go to Regular Admin Login</a></p>
                    """
                else:
                    return f"""
                    <h3>❌ Password Invalid</h3>
                    <p><strong>Username found:</strong> {admin.username}</p>
                    <p><strong>Password hash (first 30):</strong> {admin.password_hash[:30]}...</p>
                    <p><strong>Password test result:</strong> {password_valid}</p>
                    """
            else:
                return f"""
                <h3>❌ Admin Not Found</h3>
                <p><strong>Searched for:</strong> {username}</p>
                <p><strong>Total admins in DB:</strong> {Admin.query.count()}</p>
                """
        except Exception as e:
            return f"<h3>❌ Error:</h3><p>{str(e)}</p>"
    
    return f"""
    <h3>Admin Login Test</h3>
    <form method="POST">
        <p><label>Username: <input type="text" name="username" value="truckstopsla@gmail.com"></label></p>
        <p><label>Password: <input type="password" name="password" value="password"></label></p>
        <p><button type="submit">Test Login</button></p>
    </form>
    <hr>
    <p><strong>Database Info:</strong></p>
    <p>Admin count: {Admin.query.count()}</p>
    <p>Database URL: {str(db.engine.url).split('@')[1] if '@' in str(db.engine.url) else 'unknown'}</p>
    """



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
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    events = Event.query.order_by(Event.created_at.desc()).all()
    return render_template('admin/events.html', events=events)

@app.route('/admin/events/<int:event_id>/approve', methods=['POST'])
def admin_approve_event(event_id):
    if not session.get('admin_id'):
        return redirect(url_for('admin_login'))
    
    event = Event.query.get_or_404(event_id)
    
    if event.status != 'funded':
        flash('Event must be funded before approval', 'error')
        return redirect(url_for('admin_events'))
    
    try:
        # Charge all pledges for this event
        pledges = Pledge.query.filter_by(event_id=event_id, status='pending').all()
        
        for pledge in pledges:
            if pledge.stripe_payment_intent_id:
                success = charge_stripe_payment(pledge.stripe_payment_intent_id, pledge.amount, f"Food Truck Event: {event.name}")
                if success:
                    pledge.status = 'charged'
                    pledge.charged_at = datetime.utcnow()
                    
                    # Generate and send e-ticket
                    pledge.ticket_code = generate_ticket_code()
                    send_email(
                        pledge.email,
                        f"Your E-Ticket for {event.name}",
                        f"Thank you for your pledge! Your e-ticket code is: {pledge.ticket_code}\n\nEvent: {event.name}\nDate: {event.date}\nLocation: {event.location}\n\nShow this code at the food truck to redeem your meal."
                    )
                    pledge.ticket_sent = True
                else:
                    flash(f'Failed to charge pledge from {pledge.email}', 'error')
        
        event.status = 'approved'
        event.approved_at = datetime.utcnow()
        db.session.commit()
        
        # Send notification to organizer
        send_email(
            event.organizer.email,
            f"Event Approved: {event.name}",
            f"Great news! Your event '{event.name}' has been approved and all pledges have been charged. The food truck will attend your event."
        )
        
        flash('Event approved and pledges charged successfully', 'success')
        
    except Exception as e:
        logging.error(f"Error approving event {event_id}: {str(e)}")
        flash('Error processing approval', 'error')
    
    return redirect(url_for('admin_events'))

# Organizer Routes
@app.route('/organizer/login', methods=['GET', 'POST'])
def organizer_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        organizer = Organizer.query.filter_by(email=email).first()
        if organizer and check_password_hash(organizer.password_hash, password):
            session['organizer_id'] = organizer.id
            session['user_type'] = 'organizer'
            flash('Successfully logged in', 'success')
            return redirect(url_for('organizer_dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('organizer/login.html')

@app.route('/organizer/register', methods=['GET', 'POST'])
def organizer_register():
    if request.method == 'POST':
        email = request.form['email']
        name = request.form['name']
        password = request.form['password']
        
        if Organizer.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
        else:
            organizer = Organizer(
                email=email,
                name=name,
                password_hash=generate_password_hash(password)
            )
            db.session.add(organizer)
            db.session.commit()
            
            session['organizer_id'] = organizer.id
            session['user_type'] = 'organizer'
            flash('Registration successful', 'success')
            return redirect(url_for('organizer_dashboard'))
    
    return render_template('organizer/login.html', register_mode=True)

@app.route('/organizer/logout')
def organizer_logout():
    session.pop('organizer_id', None)
    session.pop('user_type', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

@app.route('/organizer/dashboard')
def organizer_dashboard():
    if not session.get('organizer_id'):
        return redirect(url_for('organizer_login'))
    
    organizer = Organizer.query.get(session['organizer_id'])
    events = Event.query.filter_by(organizer_id=organizer.id).order_by(Event.created_at.desc()).all()
    
    return render_template('organizer/dashboard.html', organizer=organizer, events=events)

@app.route('/organizer/create-event', methods=['GET', 'POST'])
def organizer_create_event():
    if not session.get('organizer_id'):
        return redirect(url_for('organizer_login'))
    
    if request.method == 'POST':
        # Create new event
        truck_id = int(request.form['food_truck_id'])
        truck = FoodTruck.query.get(truck_id)
        
        event = Event(
            name=request.form['name'],
            description=request.form['description'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M'),
            location=request.form['location'],
            organizer_id=session['organizer_id'],
            food_truck_id=truck_id,
            markup_percentage=float(request.form['markup_percentage']),
            pledge_goal=truck.sales_goal
        )
        
        # Parse selected menu items with markup
        selected_items = []
        selected_item_ids = request.form.getlist('selected_items')
        truck_menu = truck.get_menu_items()
        
        for item_id in selected_item_ids:
            item_idx = int(item_id)
            if item_idx < len(truck_menu):
                item = truck_menu[item_idx].copy()
                item['original_price'] = item['price']
                item['marked_up_price'] = item['price'] * (1 + event.markup_percentage / 100)
                selected_items.append(item)
        
        event.set_selected_menu_items(selected_items)
        
        db.session.add(event)
        db.session.commit()
        
        # Send notification email to admin
        send_email(
            'truckstopsla@gmail.com',
            f"New Event Created: {event.name}",
            f"A new event has been created:\n\nEvent: {event.name}\nOrganizer: {event.organizer.name}\nFood Truck: {truck.name}\nDate: {event.date}\nLocation: {event.location}\nPledge Goal: ${event.pledge_goal:.2f}"
        )
        
        flash('Event created successfully', 'success')
        return redirect(url_for('organizer_dashboard'))
    
    # GET request - show form
    trucks = FoodTruck.query.all()
    return render_template('organizer/create_event.html', trucks=trucks)

# Public Routes
@app.route('/events')
def events_list():
    """Public page listing all events by status"""
    # Get events by different status categories
    active_events = Event.query.filter(Event.status.in_(['pending', 'funded'])).order_by(Event.created_at.desc()).all()
    completed_events = Event.query.filter(Event.status == 'approved').order_by(Event.created_at.desc()).all()
    all_events = Event.query.order_by(Event.created_at.desc()).all()
    
    return render_template('events/list.html', 
                         active_events=active_events, 
                         completed_events=completed_events,
                         all_events=all_events)

@app.route('/events/<int:event_id>')
def event_detail(event_id):
    """Public event detail page for pledging"""
    event = Event.query.get_or_404(event_id)
    
    if event.status not in ['pending', 'funded']:
        flash('This event is no longer accepting pledges', 'info')
        return redirect(url_for('events_list'))
    
    return render_template('events/detail.html', event=event)

@app.route('/events/<int:event_id>/pledge', methods=['GET', 'POST'])
def make_pledge(event_id):
    """Handle pledge creation with Stripe tokenization"""
    event = Event.query.get_or_404(event_id)
    
    if event.status not in ['pending', 'funded']:
        flash('This event is no longer accepting pledges', 'error')
        return redirect(url_for('event_detail', event_id=event_id))
    
    if request.method == 'POST':
        email = request.form['email']
        amount = float(request.form['amount'])
        stripe_token = request.form.get('stripe_token')
        
        try:
            # Create payment intent with Stripe
            payment_intent_id = create_stripe_payment_intent(amount, email, f"Pledge for {event.name}")
            
            if payment_intent_id:
                # Create pledge record
                pledge = Pledge(
                    email=email,
                    amount=amount,
                    stripe_token=stripe_token,
                    stripe_payment_intent_id=payment_intent_id,
                    event_id=event_id
                )
                
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
                        'truckstopsla@gmail.com',
                        f"Event Goal Met: {event.name}",
                        f"The event '{event.name}' has reached its funding goal of ${event.pledge_goal:.2f}. Please review and approve the event to charge all pledges."
                    )
                    
                    # Send goal reached confirmation to pledger
                    send_email(
                        email,
                        f"Event Funded! - {event.name}",
                        f"Great news! Your pledge of ${amount:.2f} for '{event.name}' helped reach the funding goal!\n\nEvent Goal: ${event.pledge_goal:.2f}\nTotal Raised: ${event.current_pledges:.2f}\n\nPayments will be processed soon and you'll receive your e-ticket.\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nThank you for your support!"
                    )
                else:
                    # Send regular pledge confirmation
                    send_email(
                        email,
                        f"Pledge Confirmation - {event.name}",
                        f"Thank you for your ${amount:.2f} pledge for '{event.name}'!\n\nEvent Goal: ${event.pledge_goal:.2f}\nCurrent Progress: ${event.current_pledges:.2f} (${event.pledge_goal - event.current_pledges:.2f} remaining)\n\nYour payment will only be charged if the event reaches its funding goal.\n\nEvent Details:\nDate: {event.date}\nLocation: {event.location}\n\nWe'll keep you updated on the progress!"
                    )
                
                flash('Pledge created successfully! You will only be charged if the event reaches its funding goal.', 'success')
                return redirect(url_for('pledge_success', pledge_id=pledge.id))
            else:
                flash('Error processing payment. Please try again.', 'error')
                
        except Exception as e:
            logging.error(f"Error creating pledge: {str(e)}")
            flash('Error processing pledge. Please try again.', 'error')
    
    return render_template('pledge/form.html', event=event)

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

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# Debug route to test admin login
@app.route('/debug-admin-login')
def debug_admin_login():
    """Debug route to test admin credentials"""
    try:
        admin = Admin.query.filter_by(username='truckstopsla@gmail.com').first()
        if admin:
            password_test = check_password_hash(admin.password_hash, 'password')
            return f"""
            <h3>Admin Debug Info</h3>
            <p><strong>Username:</strong> {admin.username}</p>
            <p><strong>ID:</strong> {admin.id}</p>
            <p><strong>Password Hash (first 30 chars):</strong> {admin.password_hash[:30]}...</p>
            <p><strong>Password 'password' test:</strong> {'✓ PASS' if password_test else '✗ FAIL'}</p>
            <hr>
            <p>Try logging in with: truckstopsla@gmail.com / password</p>
            <p><a href="/admin/login">Go to Admin Login</a></p>
            """
        else:
            return "❌ No admin user found in database"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# Setup route for production deployment
@app.route('/setup-admin-secret-xyz123')
def setup_admin():
    """One-time setup route to create admin user in production"""
    try:
        # Debug info
        db_url = os.environ.get('DATABASE_URL', 'Not set')[:50] + '...' if len(os.environ.get('DATABASE_URL', '')) > 50 else os.environ.get('DATABASE_URL', 'Not set')
        all_admins = Admin.query.all()
        admin_count = len(all_admins)
        
        debug_info = f"Database URL: {db_url}<br>Current admin count: {admin_count}<br><br>"
        
        # Check if admin already exists
        admin = Admin.query.filter_by(username='truckstopsla@gmail.com').first()
        
        if admin:
            # Update existing admin password
            old_hash = admin.password_hash[:20] + '...'
            admin.password_hash = generate_password_hash('password')
            db.session.commit()
            
            # Test the password
            test_result = check_password_hash(admin.password_hash, 'password')
            
            return f"{debug_info}Admin user updated successfully!<br>Old hash: {old_hash}<br>Password test: {'PASS' if test_result else 'FAIL'}<br><br><strong>You can now login with truckstopsla@gmail.com / password</strong>"
        else:
            # Create new admin
            new_admin = Admin(
                username='truckstopsla@gmail.com',
                password_hash=generate_password_hash('password')
            )
            db.session.add(new_admin)
            db.session.commit()
            
            # Test the password
            test_result = check_password_hash(new_admin.password_hash, 'password')
            
            return f"{debug_info}Admin user created successfully!<br>Password test: {'PASS' if test_result else 'FAIL'}<br><br><strong>You can now login with truckstopsla@gmail.com / password</strong>"
            
    except Exception as e:
        import traceback
        return f"Error creating admin: {str(e)}<br><br>Traceback:<br>{traceback.format_exc().replace(chr(10), '<br>')}"
