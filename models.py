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

class FoodTruckOwner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    business_name = db.Column(db.String(100), nullable=False)
    business_license = db.Column(db.String(100))
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Approval status
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    
    # Relationships
    food_trucks = db.relationship('FoodTruck', backref='owner', lazy=True)

class FoodTruck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    menu_items = db.Column(db.Text)  # JSON string of menu items
    sales_goal = db.Column(db.Float, nullable=False)  # Minimum pledges required
    
    # New fields for food truck registration system
    owner_id = db.Column(db.Integer, db.ForeignKey('food_truck_owner.id'))
    cuisine_type = db.Column(db.String(100))
    logo_url = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    
    # Contact and business info
    contact_email = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    website = db.Column(db.String(200))
    instagram = db.Column(db.String(100))
    
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
    
    def is_approved(self):
        """Check if food truck is approved for events"""
        return self.status == 'approved'

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
    
    def can_be_deleted(self):
        """Check if event can be safely deleted"""
        charged_pledges = [p for p in self.pledges.all() if p.status == 'charged']
        return len(charged_pledges) == 0
    
    def get_deletion_warnings(self):
        """Get warnings about deleting this event"""
        warnings = []
        pledges = self.pledges.all()
        charged_pledges = [p for p in pledges if p.status == 'charged']
        
        if charged_pledges:
            warnings.append(f"Has {len(charged_pledges)} charged pledges - cannot delete")
        elif pledges:
            warnings.append(f"Has {len(pledges)} pending pledges - will send cancellation emails")
        
        if self.status == 'approved':
            warnings.append("Event is already approved")
            
        return warnings

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

class AuthToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    organizer_id = db.Column(db.Integer, db.ForeignKey('organizer.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class PledgeTransfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Transfer details
    source_event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    target_event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    organizer_id = db.Column(db.Integer, db.ForeignKey('organizer.id'), nullable=False)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # pending, consent_requested, completed, cancelled
    consent_requested_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Transfer summary
    total_pledges_requested = db.Column(db.Integer, default=0)  # Number of pledges to transfer
    total_amount_requested = db.Column(db.Float, default=0.0)  # Total amount to transfer
    pledges_consented = db.Column(db.Integer, default=0)  # Number of pledges that consented
    amount_transferred = db.Column(db.Float, default=0.0)  # Actual amount transferred
    
    # Relationships
    source_event = db.relationship('Event', foreign_keys=[source_event_id], backref='outgoing_transfers')
    target_event = db.relationship('Event', foreign_keys=[target_event_id], backref='incoming_transfers')
    organizer = db.relationship('Organizer', backref='pledge_transfers')

class PledgeTransferConsent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('pledge_transfer.id'), nullable=False)
    pledge_id = db.Column(db.Integer, db.ForeignKey('pledge.id'), nullable=False)
    
    # Consent tracking
    consent_token = db.Column(db.String(64), unique=True, nullable=False)  # Unique token for consent link
    status = db.Column(db.String(20), default='pending')  # pending, consented, declined
    responded_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transfer = db.relationship('PledgeTransfer', backref='consent_requests')
    pledge = db.relationship('Pledge', backref='transfer_consents')

class Payout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Event and truck association
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    food_truck_id = db.Column(db.Integer, db.ForeignKey('food_truck.id'), nullable=False)
    
    # Payout details
    total_sales = db.Column(db.Float, nullable=False)  # Total sales from the event
    platform_fee = db.Column(db.Float, default=0.0)  # Our commission/fee
    payout_amount = db.Column(db.Float, nullable=False)  # Amount paid to food truck
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    initiated_by = db.Column(db.Integer, db.ForeignKey('admin.id'))
    processed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Payment details
    payment_method = db.Column(db.String(50))  # bank_transfer, check, etc.
    transaction_id = db.Column(db.String(100))  # External payment processor ID
    notes = db.Column(db.Text)
    
    # Relationships
    event = db.relationship('Event', backref='payouts')
    food_truck = db.relationship('FoodTruck', backref='payouts')
    admin = db.relationship('Admin', backref='processed_payouts')
