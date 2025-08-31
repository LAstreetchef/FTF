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
        
        # Create PaymentIntent
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            capture_method='manual',  # Don't charge immediately
            receipt_email=customer_email,
            description=description,
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
        
        if intent.status == 'requires_capture':
            # Update the PaymentIntent amount to include processing fee
            total_amount_cents = int(total_amount_with_fee * 100)
            
            stripe.PaymentIntent.modify(
                payment_intent_id,
                amount=total_amount_cents,
                description=f"{description} (includes $%.2f processing fee)" % processing_fee
            )
            
            # Capture the updated payment
            intent = stripe.PaymentIntent.capture(payment_intent_id)
            logging.info(f"Successfully charged PaymentIntent {payment_intent_id} - Original: ${original_amount:.2f}, Fee: ${processing_fee:.2f}, Total: ${total_amount_with_fee:.2f}")
            return {'success': True, 'processing_fee': processing_fee, 'total_charged': total_amount_with_fee}
        else:
            logging.error(f"PaymentIntent {payment_intent_id} not in capturable state: {intent.status}")
            return {'success': False, 'error': f'Payment not capturable: {intent.status}'}
            
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
