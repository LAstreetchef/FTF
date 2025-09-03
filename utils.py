import os
import logging
import stripe
import secrets
import string
from flask_mail import Message
from app import mail
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

def create_stripe_payment_intent(amount, customer_email, description):
    """Create a Stripe PaymentIntent for future charging"""
    try:
        # Convert amount to cents
        amount_cents = int(amount * 100)
        
        # Create PaymentIntent with explicit payment method configuration
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            capture_method='manual',  # Don't charge immediately
            receipt_email=customer_email,
            description=description,
            # Restrict to card payments only to avoid redirect issues
            payment_method_types=['card'],
            # Disable automatic payment methods that require redirects
            automatic_payment_methods={'enabled': False},
            metadata={
                'customer_email': customer_email,
                'description': description
            }
        )
        
        logging.info(f"Created PaymentIntent {intent.id} for ${amount}")
        return intent.id
        
    except Exception as e:
        logging.error(f"Error creating PaymentIntent: {str(e)}")
        return None

def charge_stripe_payment(payment_intent_id, original_amount, description):
    """Charge a previously created PaymentIntent with 4.5% processing fee"""
    try:
        # Calculate total amount including processing fee
        total_amount_with_fee = calculate_total_with_processing_fee(original_amount)
        processing_fee = calculate_processing_fee(original_amount)
        
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
