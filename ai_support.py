import os
import json
import time
from datetime import datetime
from openai import OpenAI
from models import SupportConversation, SupportMessage, FoodTruck, Event, Organizer, Pledge
from app import db

# the newest OpenAI model is "gpt-5" which was released August 7, 2025.
# do not change this unless explicitly requested by the user
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

FOOD_TRUCK_KNOWLEDGE_BASE = """
You are a helpful customer support assistant for the Food Truck Fundraiser platform. Here's what you need to know:

## Platform Overview
The Food Truck Fundraiser platform enables community crowdfunding for food truck events. Food truck owners register by paying a $25 fee, event organizers create fundraising campaigns by paying a $5 fee, and community members pledge for meal tickets. Payments are only processed if events reach their funding goals.

## Key Features & Processes

### For Food Truck Owners:
- Registration requires a $25 fee for platform access
- After payment, trucks are automatically approved and can participate immediately
- Owners create profiles with menu items, pricing, and business details
- They can participate in multiple events organized by different people

### For Event Organizers:
- Registration is free, but creating each event requires a $5 fee
- Organizers select approved food trucks and set menu pricing with markup
- They set pledge goals and manage event details (date, location, description)
- Organizers get a free entree if their event is successful

### For Community Members (Pledgers):
- Browse active events and pledge for meal tickets
- Payments are only charged if events reach their funding goals
- Receive e-tickets via email when events are successful
- Can pledge for multiple menu items from the same event

### Payment Processing:
- All payments processed securely through Stripe
- Food truck registration: $25 (one-time fee for platform access)
- Event creation: $5 per event for organizers
- Pledges: Only charged when events meet their goals
- Platform handles all payment processing and e-ticket distribution

### Event Lifecycle:
1. Organizer pays $5 fee and creates event
2. Community members make pledges (not charged yet)
3. If pledge goal is met, all pledges are charged
4. E-tickets are automatically sent to pledgers
5. Food truck provides meals at the event
6. Platform handles payouts to food trucks

## Common Issues & Solutions

### Payment Issues:
- "My payment failed" → Check card details, try different payment method
- "I was charged but not approved" → Payments auto-approve, check dashboard status
- "Can I get a refund?" → Direct to contact admin for refund requests

### Account Issues:
- "Can't log in" → Verify email/password, offer password reset
- "Account not approved" → Explain auto-approval after payment
- "Need to update profile" → Guide to dashboard settings

### Event Questions:
- "How do pledges work?" → Explain conditional charging when goals are met
- "What if event doesn't reach goal?" → No charges, pledges automatically cancelled
- "When do I get my e-ticket?" → Sent automatically when event is funded and approved

### Platform Navigation:
- Registration flows for different user types
- How to find and pledge for events
- Dashboard features for managing trucks/events

## Escalation Triggers
Escalate to human support when users ask about:
- Refunds or billing disputes
- Technical issues you cannot resolve
- Account suspension or bans
- Custom business arrangements
- Legal or compliance questions

## Tone & Style
- Friendly and helpful
- Use simple, everyday language (users are non-technical)
- Be specific about next steps
- Acknowledge user frustration when appropriate
- Offer alternatives when possible

Remember: You can access real-time data about events, trucks, and pledges to provide accurate information.
"""

def get_ai_response(conversation_id, user_message, conversation_history=None):
    """
    Get AI response for user message with context about the platform
    """
    start_time = time.time()
    
    try:
        # Build conversation context
        messages = [
            {"role": "system", "content": FOOD_TRUCK_KNOWLEDGE_BASE}
        ]
        
        # Add conversation history if available
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages for context
                if msg.sender_type == 'user':
                    messages.append({"role": "user", "content": msg.content})
                elif msg.sender_type == 'ai':
                    messages.append({"role": "assistant", "content": msg.content})
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        # Get AI response
        response = openai_client.chat.completions.create(
            model="gpt-5",  # the newest OpenAI model is "gpt-5" which was released August 7, 2025
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        processing_time = time.time() - start_time
        
        # Calculate confidence based on response characteristics
        confidence = calculate_confidence(ai_response, user_message)
        
        return {
            'response': ai_response,
            'confidence': confidence,
            'processing_time': processing_time,
            'tokens_used': response.usage.total_tokens,
            'model': "gpt-5",
            'should_escalate': should_escalate_to_human(ai_response, user_message, confidence)
        }
        
    except Exception as e:
        return {
            'response': "I'm having trouble connecting right now. Let me get a human to help you instead.",
            'confidence': 0.0,
            'processing_time': time.time() - start_time,
            'tokens_used': 0,
            'model': "error",
            'should_escalate': True,
            'error': str(e)
        }

def calculate_confidence(ai_response, user_message):
    """
    Calculate confidence score based on response characteristics
    """
    confidence = 0.8  # Base confidence
    
    # Lower confidence for certain phrases that indicate uncertainty
    uncertainty_phrases = [
        "i'm not sure", "i don't know", "might be", "possibly", 
        "let me check", "i think", "probably", "maybe"
    ]
    
    response_lower = ai_response.lower()
    for phrase in uncertainty_phrases:
        if phrase in response_lower:
            confidence -= 0.2
            break
    
    # Lower confidence for very short responses (might be incomplete)
    if len(ai_response) < 50:
        confidence -= 0.1
    
    # Higher confidence for responses with specific platform terminology
    platform_terms = [
        "food truck", "pledge", "organizer", "registration fee", 
        "event", "stripe", "e-ticket", "funding goal"
    ]
    
    for term in platform_terms:
        if term in response_lower:
            confidence += 0.05
            break
    
    return max(0.0, min(1.0, confidence))

def should_escalate_to_human(ai_response, user_message, confidence):
    """
    Determine if conversation should be escalated to human support
    """
    # Always escalate if confidence is very low
    if confidence < 0.3:
        return True
    
    # Escalation keywords in user message
    escalation_keywords = [
        "refund", "billing", "dispute", "charge", "fraud",
        "legal", "lawsuit", "complaint", "manager", "supervisor",
        "human", "person", "speak to someone", "not working",
        "broken", "bug", "error", "can't", "won't", "doesn't work"
    ]
    
    user_lower = user_message.lower()
    for keyword in escalation_keywords:
        if keyword in user_lower:
            return True
    
    # Escalate if AI suggests it
    escalation_phrases = [
        "let me get a human", "contact support", "speak with someone",
        "escalate", "transfer you", "human representative"
    ]
    
    response_lower = ai_response.lower()
    for phrase in escalation_phrases:
        if phrase in response_lower:
            return True
    
    return False

def get_platform_context():
    """
    Get current platform statistics for AI context
    """
    try:
        total_trucks = FoodTruck.query.filter_by(status='approved').count()
        total_events = Event.query.count()
        active_events = Event.query.filter_by(status='pending').count()
        total_pledges = Pledge.query.count()
        
        return f"""
Current Platform Status:
- {total_trucks} approved food trucks
- {total_events} total events created
- {active_events} currently active events
- {total_pledges} total pledges made
"""
    except:
        return "Platform statistics temporarily unavailable."

def generate_conversation_summary(conversation):
    """
    Generate AI summary of conversation for admin review
    """
    try:
        # Get all messages
        messages = conversation.messages
        
        if not messages:
            return "No messages in conversation."
        
        # Build conversation text
        conversation_text = ""
        for msg in messages:
            sender = msg.sender_type.upper()
            conversation_text += f"{sender}: {msg.content}\n"
        
        # Generate summary
        response = openai_client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system", 
                    "content": "Summarize this customer support conversation in 2-3 sentences. Focus on the user's main issue and current status."
                },
                {"role": "user", "content": conversation_text}
            ],
            max_tokens=150
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return f"Summary generation failed: {str(e)}"