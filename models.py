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
    
    # Organizer pledge tracking ($5 charge for creating event)
    organizer_fee_charged = db.Column(db.Boolean, default=False)
    organizer_fee_payment_intent = db.Column(db.String(255))  # Stripe payment intent ID
    organizer_entree_claimed = db.Column(db.Boolean, default=False)  # Whether organizer got their free entree
    
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
    
    def get_progress_percentage(self):
        """Calculate progress percentage towards goal"""
        if self.pledge_goal <= 0:
            return 0
        return min(100, (self.current_pledges / self.pledge_goal) * 100)
    
    def is_goal_met(self):
        """Check if pledge goal is met"""
        return self.current_pledges >= self.pledge_goal
    
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
        
        # Calculate profit based on markup percentage applied to the goal amount
        # The profit is the markup percentage of the total sales needed to reach the goal
        markup_ratio = self.markup_percentage / 100.0
        base_amount_needed = self.pledge_goal / (1 + markup_ratio)
        profit_amount = self.pledge_goal - base_amount_needed
        
        return round(profit_amount, 2)
    
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
    
    # Transfer functionality fields
    transfer_token = db.Column(db.String(64), unique=True)  # For email confirmation
    transfer_target_event_id = db.Column(db.Integer, db.ForeignKey('event.id'))  # Target event for transfer
    transfer_initiated_at = db.Column(db.DateTime)  # When transfer was requested

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
    amount = db.Column(db.Float, nullable=False)  # Amount to be paid out
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    payout_method = db.Column(db.String(50), default='stripe')  # stripe, manual, etc.
    
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
