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
        
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            session['user_type'] = 'admin'
            flash('Successfully logged in as admin', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
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
            if pledge.stripe_token:
                success = charge_stripe_payment(pledge.stripe_token, pledge.amount, f"Food Truck Event: {event.name}")
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
    """Public page listing all active events"""
    events = Event.query.filter(Event.status.in_(['pending', 'funded'])).order_by(Event.created_at.desc()).all()
    return render_template('events/list.html', events=events)

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
