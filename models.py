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
    
    # Payout information
    payout_method = db.Column(db.String(50))  # 'bank', 'paypal', 'stripe'
    payout_setup_completed = db.Column(db.Boolean, default=False)
    
    # Bank account details (encrypted/hashed for security)
    bank_account_holder = db.Column(db.String(200))
    bank_routing_number = db.Column(db.String(50))
    bank_account_number_last4 = db.Column(db.String(10))  # Only store last 4 digits for security
    bank_account_type = db.Column(db.String(20))  # 'checking', 'savings'
    
    # PayPal information
    paypal_email = db.Column(db.String(200))
    
    # Stripe Connect (for future integration)
    stripe_account_id = db.Column(db.String(255))
    stripe_onboarding_completed = db.Column(db.Boolean, default=False)
    
    # Tax information
    tax_id_provided = db.Column(db.Boolean, default=False)
    tax_id_type = db.Column(db.String(20))  # 'ssn', 'ein', 'itin'
    
    # Address for tax purposes
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    country = db.Column(db.String(50), default='US')
    
    # Verification status
    payout_verified = db.Column(db.Boolean, default=False)
    verification_notes = db.Column(db.Text)
    verified_at = db.Column(db.DateTime)
    
    # Relationships
    events = db.relationship('Event', backref='organizer', lazy=True)
    
    def get_or_create_tier_info(self):
        """Get or create tier information for this organizer"""
        tier_info = OrganizerTier.query.filter_by(organizer_id=self.id).first()
        if not tier_info:
            tier_info = OrganizerTier(organizer_id=self.id)
            db.session.add(tier_info)
            db.session.commit()
        return tier_info
    
    def update_tier_metrics(self):
        """Update tier metrics based on current performance"""
        tier_info = self.get_or_create_tier_info()
        
        # Calculate successful events (approved/completed events)
        successful_events = Event.query.filter(
            Event.organizer_id == self.id,
            Event.status.in_(['approved', 'completed'])
        ).count()
        
        # Calculate total earnings from all events
        total_earnings = 0.0
        total_pledgers = 0
        events_150_percent = 0
        
        for event in self.events:
            if event.status in ['approved', 'completed']:
                profit = event.calculate_organizer_profit_if_goal_met()
                total_earnings += profit
                
                # Count pledgers (excluding organizer's own pledge)
                pledgers = len([p for p in event.pledges if p.amount != 5.0])
                total_pledgers += pledgers
                
                # Check if event reached 150% of goal
                if event.current_pledges >= (event.pledge_goal * 1.5):
                    events_150_percent += 1
        
        # Update tier info
        tier_info.successful_events = successful_events
        tier_info.total_earnings = total_earnings
        tier_info.total_pledgers_attracted = total_pledgers
        tier_info.events_reaching_150_percent = events_150_percent
        
        if successful_events > 0:
            tier_info.average_pledge_amount = total_earnings / successful_events
        
        # Recalculate tier
        tier_info.calculate_tier()
        db.session.commit()
        
        return tier_info
    
    def has_payout_method_setup(self):
        """Check if organizer has set up a payout method"""
        return self.payout_setup_completed and self.payout_method is not None
    
    def get_payout_display_info(self):
        """Get safe display information for payout method"""
        if not self.has_payout_method_setup():
            return "No payout method set up"
        
        if self.payout_method == 'bank' and self.bank_account_number_last4:
            return f"Bank account ending in {self.bank_account_number_last4}"
        elif self.payout_method == 'paypal' and self.paypal_email:
            return f"PayPal: {self.paypal_email}"
        elif self.payout_method == 'stripe':
            return "Stripe Connect account"
        else:
            return f"{self.payout_method.title()} account"
    
    def can_receive_payouts(self):
        """Check if organizer is eligible to receive payouts"""
        return (self.has_payout_method_setup() and 
                self.tax_id_provided and 
                self.payout_verified)
    
    def get_pending_payouts(self):
        """Get all pending payouts for this organizer"""
        return OrganizerPayout.query.filter(
            OrganizerPayout.organizer_id == self.id,
            OrganizerPayout.status == 'pending'
        ).all()
    
    def get_total_earnings_awaiting_payout(self):
        """Calculate total earnings waiting to be paid out"""
        total = 0.0
        
        # Check completed events without payouts
        for event in self.events:
            if event.status == 'completed':
                # Check if payout already exists
                existing_payout = OrganizerPayout.query.filter(
                    OrganizerPayout.event_id == event.id,
                    OrganizerPayout.organizer_id == self.id
                ).first()
                
                if not existing_payout:
                    profit = event.calculate_organizer_profit_if_goal_met()
                    total += profit
        
        return total

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
    
    # Payout information - TEMPORARILY DISABLED FOR DEPLOYMENT
    # Will be added via runtime migration after deployment succeeds
    # payout_method = db.Column(db.String(50))  # 'bank', 'paypal', 'stripe'
    # payout_setup_completed = db.Column(db.Boolean, default=False)
    
    # PayPal information
    # paypal_email = db.Column(db.String(200))
    
    # Bank account details (for security, only store last 4 digits)
    # bank_account_holder = db.Column(db.String(200))
    # bank_routing_number = db.Column(db.String(50))
    # bank_account_number_last4 = db.Column(db.String(10))  # Only last 4 digits
    # bank_account_type = db.Column(db.String(20))  # 'checking', 'savings'
    
    # Address for tax/legal purposes
    # address_line1 = db.Column(db.String(200))
    # address_line2 = db.Column(db.String(200))
    # city = db.Column(db.String(100))
    # state = db.Column(db.String(50))
    # zip_code = db.Column(db.String(20))
    # country = db.Column(db.String(50), default='US')
    
    # Verification status
    # payout_verified = db.Column(db.Boolean, default=False)
    # verification_notes = db.Column(db.Text)
    # verified_at = db.Column(db.DateTime)
    
    # Relationships
    food_trucks = db.relationship('FoodTruck', backref='owner', lazy=True)
    
    def has_payout_method_setup(self):
        """Check if food truck owner has set up a payout method"""
        try:
            return (hasattr(self, 'payout_setup_completed') and 
                    hasattr(self, 'payout_method') and 
                    self.payout_setup_completed and 
                    self.payout_method is not None)
        except:
            return False
    
    def get_payout_display_info(self):
        """Get safe display information for payout method"""
        try:
            if not self.has_payout_method_setup():
                return "No payout method set up"
                
            if (hasattr(self, 'payout_method') and hasattr(self, 'bank_account_number_last4') and 
                self.payout_method == 'bank' and self.bank_account_number_last4):
                return f"Bank account ending in {self.bank_account_number_last4}"
            elif (hasattr(self, 'payout_method') and hasattr(self, 'paypal_email') and 
                  self.payout_method == 'paypal' and self.paypal_email):
                return f"PayPal: {self.paypal_email}"
            elif hasattr(self, 'payout_method') and self.payout_method == 'stripe':
                return "Stripe account"
            elif hasattr(self, 'payout_method') and self.payout_method:
                return f"{self.payout_method.title()} account"
            else:
                return "No payout method set up"
        except:
            return "No payout method set up"
    
    def can_receive_payouts(self):
        """Check if food truck owner is eligible to receive payouts"""
        try:
            return (self.has_payout_method_setup() and 
                    self.status == 'approved' and
                    hasattr(self, 'payout_verified') and
                    self.payout_verified)
        except:
            return False

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
    
    # Registration fee tracking ($25 charge for creating profile)
    registration_fee_charged = db.Column(db.Boolean, default=False)
    registration_fee_payment_intent = db.Column(db.String(255))  # Stripe payment intent ID
    
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

class EventBackup(db.Model):
    """Permanent backup storage for Event data that survives deployments"""
    __tablename__ = 'event_backup_permanent'
    id = db.Column(db.Integer, primary_key=True)
    backup_data = db.Column(db.Text, nullable=False)  # JSON data of all events
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    backup_type = db.Column(db.String(50), default='pre_deployment')

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
    
    # Organizer fee tracking ($1.95 charge for creating event)
    organizer_fee_charged = db.Column(db.Boolean, default=False)
    organizer_fee_payment_intent = db.Column(db.String(255))  # Stripe payment intent ID
    organizer_entree_claimed = db.Column(db.Boolean, default=False)  # Whether organizer got their free entree
    
    # Markup splitting configuration
    markup_split_config = db.Column(db.Text)  # JSON string storing split configuration
    
    # Relationships
    pledges = db.relationship('Pledge', foreign_keys='Pledge.event_id', backref='event', lazy=True)
    
    def get_selected_menu_items(self):
        """Parse selected menu items from JSON string"""
        try:
            return json.loads(self.selected_menu_items) if self.selected_menu_items else []
        except:
            return []
    
    def set_selected_menu_items(self, items):
        """Set selected menu items as JSON string"""
        self.selected_menu_items = json.dumps(items)
    
    def get_markup_split_config(self):
        """Parse markup split configuration from JSON string"""
        try:
            return json.loads(self.markup_split_config) if self.markup_split_config else []
        except:
            return []
    
    def set_markup_split_config(self, splits):
        """Set markup split configuration as JSON string"""
        # Validate splits add up to 100%
        total_percentage = sum(split.get('percentage', 0) for split in splits)
        if abs(total_percentage - 100) > 0.01:  # Allow for small floating point errors
            raise ValueError("Split percentages must add up to 100%")
        
        self.markup_split_config = json.dumps(splits)
    
    def get_progress_percentage(self):
        """Calculate progress percentage towards goal"""
        total_goal = self.get_total_goal_amount()
        if total_goal <= 0:
            return 0
        return min(100, (self.current_pledges / total_goal) * 100)
    
    def is_goal_met(self):
        """Check if pledge goal is met"""
        return self.current_pledges >= self.get_total_goal_amount()
    
    def update_pledge_total(self):
        """Update current pledges total from active pledges (pending + charged)"""
        from sqlalchemy import func
        total = db.session.query(func.sum(Pledge.amount)).filter(
            Pledge.event_id == self.id,
            Pledge.status.in_(['pending', 'charged'])
        ).scalar() or 0
        self.current_pledges = total
        db.session.commit()
    
    def calculate_organizer_profit_if_goal_met(self):
        """Calculate how much money the organizer will make if the event reaches its goal"""
        if self.pledge_goal <= 0 or self.markup_percentage <= 0:
            return 0.0
        
        # NEW LOGIC: Markup is applied ON TOP of the food truck minimum
        # pledge_goal is the food truck minimum (base amount)
        # total_profit = food_truck_minimum * markup_percentage
        total_profit = self.pledge_goal * (self.markup_percentage / 100.0)
        
        # ORGANIZER GETS FULL MARKUP AMOUNT - they are responsible for splitting with designees
        # The markup splitting configuration is for informational purposes only
        # Organizer receives 100% of markup profit and handles their own distributions
        return round(total_profit, 2)
    
    def calculate_organizer_net_payout_if_goal_met(self):
        """Calculate the net amount organizer will receive after 4.5% processing fee"""
        gross_profit = self.calculate_organizer_profit_if_goal_met()
        if gross_profit <= 0:
            return 0.0
        processing_fee = round(gross_profit * 0.045, 2)  # 4.5% processing fee
        net_payout = round(gross_profit - processing_fee, 2)
        return net_payout
    
    def calculate_markup_splits_if_goal_met(self):
        """Calculate markup split amounts for all parties if goal is met"""
        if self.pledge_goal <= 0 or self.markup_percentage <= 0:
            return []
        
        # NEW LOGIC: Markup is applied ON TOP of the food truck minimum
        # pledge_goal is the food truck minimum (base amount)
        # total_profit = food_truck_minimum * markup_percentage
        total_profit = self.pledge_goal * (self.markup_percentage / 100.0)
        
        splits = self.get_markup_split_config()
        if not splits:
            # Default: 100% to organizer
            return [{'email': self.organizer.email, 'percentage': 100.0, 'amount': round(total_profit, 2), 'is_organizer': True}]
        
        # Calculate amounts for each split
        result = []
        for split in splits:
            amount = round(total_profit * (split.get('percentage', 0) / 100.0), 2)
            result.append({
                'email': split.get('email', ''),
                'percentage': split.get('percentage', 0),
                'amount': amount,
                'description': split.get('description', ''),
                'is_organizer': split.get('is_organizer', False)
            })
        
        return result
    
    def get_total_goal_amount(self):
        """Calculate the total amount needed including markup (food truck minimum + markup)"""
        if self.markup_percentage <= 0:
            return self.pledge_goal
        
        # Total goal = food truck minimum + markup amount
        markup_amount = self.pledge_goal * (self.markup_percentage / 100.0)
        return self.pledge_goal + markup_amount
    
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
    processing_fee = db.Column(db.Float, default=0.0)  # 4.5% processing fee
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
    
    # Selected menu items (JSON array of selected items with details)
    selected_menu_items = db.Column(db.Text)
    
    # Gift meal functionality
    recipient_name = db.Column(db.String(120))  # Name of gift recipient
    recipient_email = db.Column(db.String(120))  # Email of gift recipient
    gift_message = db.Column(db.Text)  # Personal message from giver to recipient
    is_gift = db.Column(db.Boolean, default=False)  # Whether this is a gift pledge
    
    # Transfer functionality fields
    transfer_token = db.Column(db.String(64), unique=True)  # For email confirmation
    transfer_target_event_id = db.Column(db.Integer, db.ForeignKey('event.id'))  # Target event for transfer
    transfer_initiated_at = db.Column(db.DateTime)  # When transfer was requested
    
    def set_selected_menu_items(self, items):
        """Store selected menu items as JSON"""
        if items:
            self.selected_menu_items = json.dumps(items)
        else:
            self.selected_menu_items = None
    
    def get_selected_menu_items(self):
        """Retrieve selected menu items from JSON"""
        if self.selected_menu_items:
            try:
                return json.loads(self.selected_menu_items)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

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

class SupportConversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Session tracking
    session_id = db.Column(db.String(64), unique=True, nullable=False)
    visitor_email = db.Column(db.String(120))  # Optional if user provides email
    visitor_name = db.Column(db.String(100))   # Optional if user provides name
    
    # Conversation status
    status = db.Column(db.String(20), default='active')  # active, escalated, resolved, abandoned
    escalated_to_human = db.Column(db.Boolean, default=False)
    escalated_at = db.Column(db.DateTime)
    
    # Assignment
    assigned_admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))
    assigned_at = db.Column(db.DateTime)
    
    # Page context for better support
    page_url = db.Column(db.String(500))  # URL where support was initiated
    page_type = db.Column(db.String(50))  # event_detail, organizer, admin, general
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))  # Related event if applicable
    event_name = db.Column(db.String(200))  # Event name for quick reference
    
    # Metadata
    user_agent = db.Column(db.String(500))
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Summary for admin
    conversation_summary = db.Column(db.Text)  # AI-generated summary of conversation
    
    # Relationships
    messages = db.relationship('SupportMessage', backref='conversation', lazy=True, order_by='SupportMessage.created_at')
    assigned_admin = db.relationship('Admin', backref='support_conversations')
    related_event = db.relationship('Event', backref='support_conversations')

class SupportMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('support_conversation.id'), nullable=False)
    
    # Message content
    content = db.Column(db.Text, nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)  # user, ai, admin
    sender_name = db.Column(db.String(100))  # For admin messages
    
    # Message metadata
    message_type = db.Column(db.String(20), default='text')  # text, system, escalation
    confidence_score = db.Column(db.Float)  # AI confidence in response (0.0-1.0)
    processing_time = db.Column(db.Float)   # How long AI took to respond
    
    # Status
    is_helpful = db.Column(db.Boolean)  # User feedback on AI responses
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # AI metadata
    ai_model_used = db.Column(db.String(50))  # Track which AI model was used
    tokens_used = db.Column(db.Integer)  # Track API usage

# =============================================================================
# PAYOUT AND AMBASSADOR SYSTEM
# =============================================================================

class OrganizerPayout(db.Model):
    """Track payouts to organizers for their event profits"""
    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('organizer.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    
    # Payout details
    gross_amount = db.Column(db.Float, nullable=False)  # Gross markup profit before processing fee
    processing_fee = db.Column(db.Float, default=0.0)  # 4.5% processing fee
    amount = db.Column(db.Float, nullable=False)  # Net amount to be paid out (after processing fee)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    payout_method = db.Column(db.String(50), default='stripe')  # stripe, manual, etc.
    transaction_id = db.Column(db.String(255))  # PayPal batch ID or other provider transaction ID
    
    # Stripe integration
    stripe_transfer_id = db.Column(db.String(255))  # Stripe transfer ID for tracking
    stripe_account_id = db.Column(db.String(255))  # Organizer's connected Stripe account
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    organizer = db.relationship('Organizer', backref='payouts')
    event = db.relationship('Event', backref='payout')

class FoodTruckPayout(db.Model):
    """Track payouts to food trucks for their event earnings (base minimum amounts)"""
    id = db.Column(db.Integer, primary_key=True)
    food_truck_id = db.Column(db.Integer, db.ForeignKey('food_truck.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    
    # Payout details
    amount = db.Column(db.Float, nullable=False)  # Amount to be paid out (usually the base minimum)
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    payout_method = db.Column(db.String(50), default='paypal')  # paypal, stripe, manual, etc.
    transaction_id = db.Column(db.String(255))  # PayPal batch ID or other provider transaction ID
    
    # Food truck contact info for payouts
    recipient_email = db.Column(db.String(120))  # Food truck owner's PayPal email
    
    # Stripe integration (backup method)
    stripe_transfer_id = db.Column(db.String(255))  # Stripe transfer ID for tracking
    stripe_account_id = db.Column(db.String(255))  # Food truck's connected Stripe account
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    food_truck = db.relationship('FoodTruck', backref='truck_payouts')
    event = db.relationship('Event', backref='truck_payout')

class PayoutSplit(db.Model):
    """Track split payouts for events with markup sharing"""
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    
    # Recipient details
    recipient_email = db.Column(db.String(120), nullable=False)
    recipient_description = db.Column(db.String(200))  # e.g., "Local Charity", "Organizer"
    percentage = db.Column(db.Float, nullable=False)  # Percentage of total markup
    amount = db.Column(db.Float, nullable=False)  # Calculated payout amount
    is_organizer = db.Column(db.Boolean, default=False)  # Whether this split goes to the organizer
    
    # Payout status
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    payout_method = db.Column(db.String(50), default='stripe')  # stripe, manual, etc.
    
    # Stripe integration
    stripe_transfer_id = db.Column(db.String(255))  # Stripe transfer ID for tracking
    stripe_account_id = db.Column(db.String(255))  # Recipient's connected Stripe account
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    event = db.relationship('Event', backref='payout_splits')

class OrganizerTier(db.Model):
    """Track organizer ambassador tiers and progression"""
    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('organizer.id'), nullable=False)
    
    # Tier information
    current_tier = db.Column(db.String(20), default='bronze')  # bronze, silver, gold
    tier_points = db.Column(db.Integer, default=0)
    successful_events = db.Column(db.Integer, default=0)
    total_earnings = db.Column(db.Float, default=0.0)
    
    # Performance metrics
    average_pledge_amount = db.Column(db.Float, default=0.0)
    total_pledgers_attracted = db.Column(db.Integer, default=0)
    events_reaching_150_percent = db.Column(db.Integer, default=0)  # Bonus metric
    
    # Tier benefits
    markup_bonus = db.Column(db.Float, default=0.0)  # Additional markup percentage
    priority_food_truck_access = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    tier_achieved_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    organizer = db.relationship('Organizer', backref='tier_info', uselist=False)
    
    def calculate_tier(self):
        """Calculate and update organizer tier based on performance"""
        old_tier = self.current_tier
        
        # Tier requirements
        if self.successful_events >= 10 and self.total_earnings >= 500:
            self.current_tier = 'gold'
            self.markup_bonus = 5.0  # Extra 5% markup allowed
            self.priority_food_truck_access = True
        elif self.successful_events >= 3 and self.total_earnings >= 100:
            self.current_tier = 'silver'  
            self.markup_bonus = 2.5  # Extra 2.5% markup allowed
            self.priority_food_truck_access = False
        else:
            self.current_tier = 'bronze'
            self.markup_bonus = 0.0
            self.priority_food_truck_access = False
            
        # Update timestamp if tier changed
        if old_tier != self.current_tier:
            self.tier_achieved_at = datetime.utcnow()
            
        self.last_updated = datetime.utcnow()
        
    def get_tier_color(self):
        """Get CSS color class for tier display"""
        tier_colors = {
            'bronze': 'text-warning',
            'silver': 'text-secondary', 
            'gold': 'text-warning'
        }
        return tier_colors.get(self.current_tier, 'text-muted')
        
    def get_tier_icon(self):
        """Get icon for tier display"""
        tier_icons = {
            'bronze': '🥉',
            'silver': '🥈',
            'gold': '🥇'
        }
        return tier_icons.get(self.current_tier, '🏅')
        
    def get_next_tier_requirements(self):
        """Get requirements for next tier"""
        if self.current_tier == 'bronze':
            return {
                'tier': 'silver',
                'events_needed': max(0, 3 - self.successful_events),
                'earnings_needed': max(0, 100 - self.total_earnings)
            }
        elif self.current_tier == 'silver':
            return {
                'tier': 'gold', 
                'events_needed': max(0, 10 - self.successful_events),
                'earnings_needed': max(0, 500 - self.total_earnings)
            }
        else:
            return None  # Already at highest tier

class AmbassadorChallenge(db.Model):
    """Track gamification challenges and rewards"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Challenge details
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    challenge_type = db.Column(db.String(50), nullable=False)  # milestone, recurring, special
    
    # Requirements
    requirement_type = db.Column(db.String(50))  # events_completed, earnings_reached, pledgers_attracted
    requirement_value = db.Column(db.Integer)
    time_limit_days = db.Column(db.Integer)  # For time-limited challenges
    
    # Rewards
    reward_type = db.Column(db.String(50))  # points, cash_bonus, tier_boost, markup_bonus
    reward_value = db.Column(db.Float)
    reward_description = db.Column(db.String(200))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrganizerChallengeProgress(db.Model):
    """Track individual organizer progress on challenges"""
    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('organizer.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('ambassador_challenge.id'), nullable=False)
    
    # Progress tracking
    current_progress = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)
    completion_date = db.Column(db.DateTime)
    reward_claimed = db.Column(db.Boolean, default=False)
    
    # Timestamps
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    organizer = db.relationship('Organizer', backref='challenge_progress')
    challenge = db.relationship('AmbassadorChallenge', backref='participant_progress')

class PledgeMessage(db.Model):
    """Chat-like messaging system for pledge communications"""
    id = db.Column(db.Integer, primary_key=True)
    pledge_id = db.Column(db.Integer, db.ForeignKey('pledge.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=True)
    
    # Message content
    message = db.Column(db.Text, nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)  # 'admin' or 'pledger'
    sender_email = db.Column(db.String(120), nullable=False)
    
    # Status
    is_read = db.Column(db.Boolean, default=False)
    email_sent = db.Column(db.Boolean, default=False)  # Track if email notification was sent
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    pledge = db.relationship('Pledge', backref='messages')
    admin = db.relationship('Admin', backref='sent_messages')
