from app import db
from datetime import datetime
from sqlalchemy import func
import json

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Organizer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    events = db.relationship('Event', backref='organizer', lazy=True)

class FoodTruck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    menu_items = db.Column(db.Text)  # JSON string of menu items
    sales_goal = db.Column(db.Float, nullable=False)  # Minimum pledges required
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    events = db.relationship('Event', backref='food_truck', lazy=True)
    
    def get_menu_items(self):
        """Parse menu items from JSON string"""
        try:
            return json.loads(self.menu_items) if self.menu_items else []
        except:
            return []
    
    def set_menu_items(self, items):
        """Set menu items as JSON string"""
        self.menu_items = json.dumps(items)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    
    # Foreign keys
    organizer_id = db.Column(db.Integer, db.ForeignKey('organizer.id'), nullable=False)
    food_truck_id = db.Column(db.Integer, db.ForeignKey('food_truck.id'), nullable=False)
    
    # Menu and pricing
    selected_menu_items = db.Column(db.Text)  # JSON string of selected items with markup
    markup_percentage = db.Column(db.Float, default=0.0)
    pledge_goal = db.Column(db.Float, nullable=False)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # pending, funded, approved, completed, cancelled
    current_pledges = db.Column(db.Float, default=0.0)
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    pledges = db.relationship('Pledge', backref='event', lazy=True)
    
    def get_selected_menu_items(self):
        """Parse selected menu items from JSON string"""
        try:
            return json.loads(self.selected_menu_items) if self.selected_menu_items else []
        except:
            return []
    
    def set_selected_menu_items(self, items):
        """Set selected menu items as JSON string"""
        self.selected_menu_items = json.dumps(items)
    
    def get_progress_percentage(self):
        """Calculate progress percentage towards goal"""
        if self.pledge_goal <= 0:
            return 0
        return min(100, (self.current_pledges / self.pledge_goal) * 100)
    
    def is_goal_met(self):
        """Check if pledge goal is met"""
        return self.current_pledges >= self.pledge_goal
    
    def update_pledge_total(self):
        """Update current pledges total from all pledges"""
        total = db.session.query(func.sum(Pledge.amount)).filter_by(event_id=self.id).scalar() or 0
        self.current_pledges = total
        db.session.commit()

class Pledge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    stripe_token = db.Column(db.String(200))  # Stripe payment method ID
    stripe_payment_intent_id = db.Column(db.String(200))  # For tracking charges
    
    # Event association
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # pending, charged, cancelled
    charged_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # E-ticket details
    ticket_code = db.Column(db.String(50), unique=True)
    ticket_sent = db.Column(db.Boolean, default=False)

class EmailLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
