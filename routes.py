from flask import render_template, request, redirect, url_for, session, flash, jsonify, make_response
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

@app.route('/test-credentials')
def test_credentials():
    """Simple credential testing page"""
    return render_template('test_credentials.html')

# Admin Routes
@app.route('/iframe-debug')
def iframe_debug():
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
    """

@app.route('/quick-admin-login')
def quick_admin_login():
    """Quick login for admin in iframe contexts"""
    try:
        admin = Admin.query.filter_by(username='truckstopsla@gmail.com').first()
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

@app.route('/quick-organizer-login')
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
                sync_results.append(f"Updated: {truck_data['name']}")
            else:
                new_truck = FoodTruck(
                    name=truck_data['name'],
                    description=truck_data['description'],
                    menu_items=json.dumps(truck_data['menu_items']),
                    sales_goal=truck_data['sales_goal']
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

@app.route('/test-admin-login-xyz123', methods=['GET', 'POST'])
def test_admin_login():
    """Debug route to test admin login credentials"""
    try:
        if request.method == 'POST':
            username = request.form.get('username', 'truckstopsla@gmail.com')
            password = request.form.get('password', 'password')
        else:
            username = 'truckstopsla@gmail.com'
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
                'username': 'truckstopsla@gmail.com',
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
            
            logging.info(f"Organizer {email} logged in successfully, session set with organizer_id: {organizer.id}")
            logging.info(f"Session contents after login: {dict(session)}")
            flash('Successfully logged in', 'success')
            
            # Always return a smart page that handles both iframe and regular contexts
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Organizer Login Success</title>
                <script>
                    console.log('Organizer login successful!');
                    console.log('In iframe:', window.self !== window.top);
                    console.log('Server detected embedded:', {str(is_embedded).lower()});
                    
                    // Wait a moment for session to be saved, then redirect
                    // Immediately redirect to dashboard within iframe instead of parent
                    setTimeout(function() {{
                        console.log('Redirecting to organizer dashboard in iframe...');
                        window.location.href = '{url_for('organizer_dashboard')}';
                    }}, 1000);
                </script>
            </head>
            <body>
                <div style="text-align: center; margin-top: 50px;">
                    <h2>✅ Organizer Login Successful!</h2>
                    <p>Redirecting to dashboard...</p>
                    <p>If not redirected: <a href="{url_for('organizer_dashboard')}" target="_top">Click here for Dashboard</a></p>
                    <hr>
                    <small>
                        Debug: Iframe detected: {is_embedded}<br>
                        Referrer: {request.referrer}<br>
                        Session ID: {session.get('organizer_id', 'None')}
                    </small>
                </div>
            </body>
            </html>
            """
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
            
            # Debug logging
            logging.debug(f"Organizer registration attempt - Email: {email}, Name: {name}")
            
            # Validation
            if not email or not name or not password:
                flash('All fields are required', 'error')
                logging.debug("Registration failed: Missing fields")
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

@app.route('/organizer/dashboard')
def organizer_dashboard():
    # Enhanced debugging for iframe session issues
    organizer_id = session.get('organizer_id')
    user_type = session.get('user_type')
    is_embedded = request.referrer and 'thefoodtruckstop.com' in request.referrer
    
    logging.info(f"Dashboard access - Organizer ID: {organizer_id}, User type: {user_type}, Embedded: {is_embedded}")
    logging.info(f"Session data: {dict(session)}")
    logging.info(f"Request cookies: {dict(request.cookies)}")
    
    if not organizer_id:
        logging.warning("Dashboard access denied - no organizer_id in session, redirecting to login")
        return redirect(url_for('organizer_login'))
    
    organizer = Organizer.query.get(session['organizer_id'])
    if not organizer:
        flash('Organizer not found', 'error')
        return redirect(url_for('organizer_login'))
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
        if not truck:
            flash('Food truck not found', 'error')
            return redirect(url_for('organizer_create_event'))
        
        event = Event(
            name=request.form['name'],
            description=request.form['description'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M'),
            location=request.form['location'],
            organizer_id=session['organizer_id'],
            food_truck_id=truck_id,
            markup_percentage=float(request.form['markup_percentage']),
            pledge_goal=truck.sales_goal if truck.sales_goal else 1000.0
        )
        
        # Parse selected menu items with markup
        selected_items = []
        selected_item_ids = request.form.getlist('selected_items')
        truck_menu = truck.get_menu_items() if truck else []
        
        for item_id in selected_item_ids:
            item_idx = int(item_id)
            if item_idx < len(truck_menu):
                item = truck_menu[item_idx].copy()
                item['original_price'] = item['price']
                item['marked_up_price'] = item['price'] * (1 + event.markup_percentage / 100)
                selected_items.append(item)
        
        # If no menu items were selected (frontend issue), auto-select all items with 15% markup
        if not selected_items and truck_menu:
            for item in truck_menu:
                fallback_item = item.copy()
                fallback_item['original_price'] = item['price']
                fallback_item['marked_up_price'] = round(item['price'] * 1.15, 2)  # 15% default markup
                selected_items.append(fallback_item)
        
        event.set_selected_menu_items(selected_items)
        
        db.session.add(event)
        db.session.commit()
        
        # Send notification email to admin
        organizer = Organizer.query.get(session['organizer_id'])
        organizer_name = organizer.name if organizer else "Unknown Organizer"
        send_email(
            'truckstopsla@gmail.com',
            f"New Event Created: {event.name}",
            f"A new event has been created:\n\nEvent: {event.name}\nOrganizer: {organizer_name}\nFood Truck: {truck.name}\nDate: {event.date}\nLocation: {event.location}\nPledge Goal: ${event.pledge_goal:.2f}"
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
@app.route('/login-admin-direct-xyz123', methods=['GET', 'POST'])
def login_admin_direct():
    """Direct admin login for troubleshooting"""
    if request.method == 'POST':
        # Process login
        admin = Admin.query.filter_by(username='truckstopsla@gmail.com').first()
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
            Login as Admin (truckstopsla@gmail.com)
        </button></p>
    </form>
    
    <p><a href="/admin/login">Go to regular login page</a></p>
    <p><a href="/admin/dashboard">Try accessing dashboard directly</a></p>
    """

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
            
            return f"""
            {debug_info}Admin user updated successfully!<br>
            Old hash: {old_hash}<br>
            Password test: {'PASS' if test_result else 'FAIL'}<br><br>
            <strong>You can now login with truckstopsla@gmail.com / password</strong><br><br>
            <hr>
            <h4>Quick Login Test:</h4>
            <form action="/admin/login" method="POST" style="margin: 10px 0;">
                <input type="hidden" name="username" value="truckstopsla@gmail.com">
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
                username='truckstopsla@gmail.com',
                password_hash=generate_password_hash('password')
            )
            db.session.add(new_admin)
            db.session.commit()
            
            # Test the password
            test_result = check_password_hash(new_admin.password_hash, 'password')
            
            return f"""
            {debug_info}Admin user created successfully!<br>
            Password test: {'PASS' if test_result else 'FAIL'}<br><br>
            <strong>You can now login with truckstopsla@gmail.com / password</strong><br><br>
            <hr>
            <h4>Quick Login Test:</h4>
            <form action="/admin/login" method="POST" style="margin: 10px 0;">
                <input type="hidden" name="username" value="truckstopsla@gmail.com">
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
@app.route('/test-organizer-reg')
def test_organizer_registration():
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
