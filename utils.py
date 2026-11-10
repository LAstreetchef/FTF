import os
import logging
import stripe
import secrets
import string
from flask_mail import Message
from flask import render_template, request
from app import mail, db
from datetime import datetime

def send_email(recipient, subject, body, html=None):
    """Send email using Flask-Mail with Gmail SMTP"""
    try:
        msg = Message(
            subject=subject,
            recipients=[recipient],
            body=body if not html else None,
            html=html if html else body
        )
        mail.send(msg)
        logging.info(f"Email sent to {recipient}: {subject}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email to {recipient}: {str(e)}")
        return False

def generate_ticket_code():
    """Generate a unique e-ticket code"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(8))

def create_stripe_payment_intent(amount, customer_email, description, metadata=None, amount_cents=None):
    """Create a Stripe PaymentIntent for future charging.

    Cards only. Apple Pay and Google Pay may arrive as a card PaymentMethod.
    Do not add Cash App Pay.
    """
    try:
        # Convert amount to cents unless the caller already passed the Price total.
        cents = int(amount_cents) if amount_cents is not None else int(amount * 100)
        
        # Get the current stripe key that was configured in app.py based on test mode
        current_key = stripe.api_key
        mode = "TEST" if current_key and current_key.startswith('sk_test_') else "LIVE"
        logging.info(f"Creating payment intent in {mode} mode")

        meta = {
            "customer_email": (customer_email or "")[:500],
            "description": (description or "")[:500],
        }
        for key, value in (metadata or {}).items():
            if value is None:
                continue
            meta[str(key)[:40]] = str(value)[:500]
        
        # Create PaymentIntent with current configured key
        intent = stripe.PaymentIntent.create(
            amount=cents,
            currency='usd',
            capture_method='manual',  # Don't charge immediately
            receipt_email=customer_email,
            description=description,
            # Cards only. Apple Pay and Google Pay can still arrive as a card.
            # Do not add cashapp or other redirect methods.
            payment_method_types=['card'],
            automatic_payment_methods={'enabled': False},
            metadata=meta,
        )
        
        logging.info(f"Created PaymentIntent {intent.id} for ${amount}")
        return intent.id
        
    except Exception as e:
        logging.error(f"Error creating PaymentIntent: {str(e)}")
        return None

def release_stripe_hold(payment_intent_id):
    """Release an uncaptured authorization. Simulated pledges have nothing to release."""
    if not payment_intent_id or str(payment_intent_id).startswith("sim_"):
        return True
    if not stripe.api_key:
        logging.info("No Stripe key; hold %s will expire on its own", payment_intent_id)
        return False
    try:
        stripe.PaymentIntent.cancel(payment_intent_id)
        logging.info("Released hold %s", payment_intent_id)
        return True
    except Exception as exc:
        logging.error("Could not release hold %s: %s", payment_intent_id, exc)
        return False


def release_and_notify_pledgers(event):
    """Release uncaptured card holds and send the cancellation email.

    Shared by admin deletion and by a campaign that misses its deadline.
    """
    from models import Pledge

    pledges = Pledge.query.filter_by(event_id=event.id).all()
    when = event.date.strftime("%B %d, %Y at %I:%M %p") if event.date else "the scheduled day"
    for pledge in pledges:
        if pledge.status != "pending":
            continue
        release_stripe_hold(pledge.stripe_payment_intent_id)
        pledge.status = "cancelled"
        send_email(
            pledge.email,
            f"Event Cancelled: {event.name}",
            f"We regret to inform you that the event '{event.name}' scheduled for {when} has been cancelled.\n\n"
            f"Your pledge of ${pledge.amount:.2f} has not been charged and no payment was processed.\n\n"
            "We apologize for any inconvenience.",
        )
    return pledges


def charge_stripe_payment(payment_intent_id, original_amount, description):
    """Charge a previously created PaymentIntent with 4.5% processing fee"""
    try:
        # Use the correct Stripe key based on current mode configuration
        current_key = stripe.api_key
        mode = "TEST" if current_key and current_key.startswith('sk_test_') else "LIVE"
        
        if not current_key:
            logging.error("CRITICAL: No Stripe key configured for payment charging")
            return {'success': False, 'error': 'Payment system not configured'}
        
        # Calculate total amount including processing fee
        total_amount_with_fee = calculate_total_with_processing_fee(original_amount)
        processing_fee = calculate_processing_fee(original_amount)
        
        logging.info(f"Charging payment in {mode} mode")
        
        # Retrieve the PaymentIntent
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        logging.info(f"PaymentIntent {payment_intent_id} current status: {intent.status}")
        
        if intent.status == 'requires_capture':
            # Payment intent already includes processing fee from pledge creation
            # Just capture without modifying amount
            intent = stripe.PaymentIntent.capture(payment_intent_id)
            
            # Get actual charged amount from the captured intent
            actual_charged_amount = intent.amount / 100.0  # Convert from cents
            
            logging.info(f"Successfully charged PaymentIntent {payment_intent_id} - Total charged: ${actual_charged_amount:.2f}")
            return {'success': True, 'processing_fee': processing_fee, 'total_charged': actual_charged_amount}
            
        elif intent.status == 'requires_payment_method':
            # This should not happen in production with proper payment collection
            # Log the issue and return error - customer needs to complete payment properly
            logging.error(f"PaymentIntent {payment_intent_id} requires payment method - payment was not properly collected during pledge creation")
            return {'success': False, 'error': 'Payment method not properly attached - please contact customer to retry their pledge'}
                
        else:
            logging.error(f"PaymentIntent {payment_intent_id} in unexpected state: {intent.status}")
            return {'success': False, 'error': f'Payment not processable: {intent.status}'}
            
    except Exception as e:
        logging.error(f"Error charging PaymentIntent {payment_intent_id}: {str(e)}")
        return {'success': False, 'error': str(e)}

def format_currency(amount):
    """Format amount as currency"""
    return f"${amount:.2f}"

def calculate_marked_up_price(original_price, markup_percentage):
    """Calculate price with markup"""
    return original_price * (1 + markup_percentage / 100)

def calculate_processing_fee(amount):
    """Calculate 4.5% credit card processing fee"""
    return amount * 0.045

def calculate_total_with_processing_fee(amount):
    """Calculate total amount including 4.5% processing fee"""
    processing_fee = calculate_processing_fee(amount)
    return amount + processing_fee

# ===== TEMPLATED EMAIL FUNCTIONS =====

def log_email_sent(recipient, subject, email_type, pledge_id=None, event_id=None):
    """Log that an email was sent to prevent duplicates"""
    try:
        from models import EmailLog
        email_log = EmailLog(
            recipient=recipient,
            subject=subject,
            status='sent',
            sent_at=datetime.utcnow()
        )
        # Add metadata for deduplication
        if pledge_id or event_id:
            email_log.body = f"pledge_id:{pledge_id}, event_id:{event_id}, type:{email_type}"
        
        db.session.add(email_log)
        db.session.commit()
        logging.info(f"Email logged: {recipient} - {subject}")
    except Exception as e:
        logging.error(f"Failed to log email: {str(e)}")

def check_email_already_sent(recipient, email_type, pledge_id=None, event_id=None):
    """Check if a specific email type was already sent to prevent duplicates"""
    try:
        from models import EmailLog
        
        # Check for existing email log with same type and identifiers
        query = EmailLog.query.filter_by(recipient=recipient, status='sent')
        
        if pledge_id or event_id:
            search_text = f"pledge_id:{pledge_id}, event_id:{event_id}, type:{email_type}"
            existing = query.filter(EmailLog.body.contains(search_text)).first()
            return existing is not None
        
        return False
    except Exception as e:
        logging.error(f"Failed to check email log: {str(e)}")
        return False

def send_templated_email(template_path, recipient, subject, context, email_type, pledge_id=None, event_id=None):
    """Send a templated email with idempotency checks"""
    try:
        # Check if already sent
        if check_email_already_sent(recipient, email_type, pledge_id, event_id):
            logging.info(f"Email {email_type} already sent to {recipient} - skipping")
            return True
        
        # Render template
        html_content = render_template(template_path, **context)
        
        # Send email
        success = send_email(recipient, subject, None, html=html_content)
        
        if success:
            # Log the email
            log_email_sent(recipient, subject, email_type, pledge_id, event_id)
        
        return success
        
    except Exception as e:
        logging.error(f"Failed to send templated email {template_path} to {recipient}: {str(e)}")
        return False

def send_conditional_pledge_confirmation(pledge, event):
    """Send confirmation for conditional pledge (not charged yet)"""
    try:
        ticket_link = f"{request.url_root}ticket/{pledge.ticket_code}" if pledge.ticket_code else None
        
        context = {
            'pledge': pledge,
            'event': event,
            'ticket_link': ticket_link
        }
        
        if pledge.is_gift:
            # Send to gift giver
            giver_success = send_templated_email(
                'emails/conditional_gift_pledge_confirmation.html',
                pledge.email,
                f"Gift Meal Pledge Confirmation - {event.name}",
                context,
                'conditional_gift_pledge',
                pledge_id=pledge.id
            )
            
            # Send to gift recipient
            recipient_success = send_templated_email(
                'emails/conditional_gift_recipient_notification.html',
                pledge.recipient_email,
                f"Gift Meal Pledge - {event.name}",
                context,
                'conditional_gift_recipient',
                pledge_id=pledge.id
            )
            
            return giver_success and recipient_success
        else:
            return send_templated_email(
                'emails/conditional_pledge_confirmation.html',
                pledge.email,
                f"Pledge Confirmation - {event.name}",
                context,
                'conditional_pledge',
                pledge_id=pledge.id
            )
    except Exception as e:
        logging.error(f"Failed to send conditional pledge confirmation for pledge {pledge.id}: {str(e)}")
        return False

def send_immediate_payment_confirmation(pledge, event, total_charged):
    """Send confirmation for immediate payment with e-ticket"""
    try:
        # Don't send if already sent to prevent duplicates
        if pledge.ticket_sent:
            logging.info(f"E-ticket already sent for pledge {pledge.id} - skipping")
            return True
        
        ticket_link = f"{request.url_root}ticket/{pledge.ticket_code}"
        
        context = {
            'pledge': pledge,
            'event': event,
            'ticket_link': ticket_link,
            'total_charged': total_charged
        }
        
        if pledge.is_gift:
            # Send to gift giver
            giver_success = send_templated_email(
                'emails/immediate_gift_payment_confirmation.html',
                pledge.email,
                f"Gift Meal Confirmed & Paid - {event.name}",
                context,
                'immediate_gift_payment',
                pledge_id=pledge.id
            )
            
            # Send e-ticket to gift recipient
            recipient_success = send_templated_email(
                'emails/immediate_gift_recipient_ticket.html',
                pledge.recipient_email,
                f"Your E-Ticket Ready! - {event.name}",
                context,
                'immediate_gift_ticket',
                pledge_id=pledge.id
            )
            
            success = giver_success and recipient_success
        else:
            success = send_templated_email(
                'emails/immediate_payment_confirmation.html',
                pledge.email,
                f"Payment Confirmed & E-Ticket Ready - {event.name}",
                context,
                'immediate_payment',
                pledge_id=pledge.id
            )
        
        # Mark e-ticket as sent if successful
        if success:
            pledge.ticket_sent = True
            db.session.commit()
        
        return success
        
    except Exception as e:
        logging.error(f"Failed to send immediate payment confirmation for pledge {pledge.id}: {str(e)}")
        return False

def send_goal_reached_notification(pledge, event):
    """Send notification when event reaches its funding goal"""
    try:
        context = {
            'pledge': pledge,
            'event': event
        }
        
        if pledge.is_gift:
            # Send to gift giver
            giver_success = send_templated_email(
                'emails/goal_reached_gift_notification.html',
                pledge.email,
                f"Gift Meal Event Funded! - {event.name}",
                context,
                'goal_reached_gift',
                pledge_id=pledge.id,
                event_id=event.id
            )
            
            # Send to gift recipient
            recipient_success = send_templated_email(
                'emails/goal_reached_gift_recipient_notification.html',
                pledge.recipient_email,
                f"Gift Meal Confirmed! - {event.name}",
                context,
                'goal_reached_gift_recipient',
                pledge_id=pledge.id,
                event_id=event.id
            )
            
            return giver_success and recipient_success
        else:
            return send_templated_email(
                'emails/goal_reached_notification.html',
                pledge.email,
                f"Event Funded! - {event.name}",
                context,
                'goal_reached',
                pledge_id=pledge.id,
                event_id=event.id
            )
    except Exception as e:
        logging.error(f"Failed to send goal reached notification for pledge {pledge.id}: {str(e)}")
        return False

def send_admin_goal_reached_notification(event):
    """Send notification to admin when an event reaches its goal"""
    try:
        context = {
            'event': event,
            'pledge_count': len(event.pledges)
        }
        
        body = f"""The event '{event.name}' has reached its funding goal of ${event.get_total_goal_amount():.2f}.

Event Details:
- Total Raised: ${event.current_pledges:.2f}
- Pledge Goal: ${event.pledge_goal:.2f}
- Markup: {event.markup_percentage:.1f}%
- Number of Pledgers: {len(event.pledges)}
- Event Date: {event.date.strftime('%B %d, %Y at %I:%M %p')}
- Location: {event.location}

Please review and approve the event to charge all pledges.

View Event: {request.url_root}admin/events"""
        
        return send_email(
            'support@foodtruckfundraiser.com',
            f"Event Goal Met: {event.name}",
            body
        )
    except Exception as e:
        logging.error(f"Failed to send admin notification for event {event.id}: {str(e)}")
        return False

def send_food_truck_goal_reached_notification(event):
    """Send notification to food truck when event reaches its goal"""
    try:
        if not event.food_truck or not event.food_truck.contact_email:
            logging.info(f"No food truck contact email for event {event.id}")
            return True
        
        body = f"""Congratulations! Your event '{event.name}' has reached its funding goal of ${event.get_total_goal_amount():.2f}!

Event Details:
- Total Raised: ${event.current_pledges:.2f}
- Number of Pledgers: {len(event.pledges)}
- Event Date: {event.date.strftime('%B %d, %Y at %I:%M %p')}
- Location: {event.location}

Your event will be reviewed and approved soon. Once approved, all pledges will be charged and you'll receive your payout.

Thank you for participating in our platform!

Best regards,
The Food Truck Fundraiser Team"""
        
        return send_email(
            event.food_truck.contact_email,
            f"Event Funded: {event.name}",
            body
        )
    except Exception as e:
        logging.error(f"Failed to send food truck notification for event {event.id}: {str(e)}")
        return False
