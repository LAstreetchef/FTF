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
You are a helpful customer support assistant for the Food Truck Fundraiser platform. Always provide specific, accurate answers based on the information below.

## Platform Overview
The Food Truck Fundraiser platform enables community crowdfunding for food truck events. Food truck owners register by paying a $25 fee, event organizers create fundraising campaigns by paying a $1.95 fee ($1.45 + $0.50 processing), and community members pledge for meal tickets. Payments are only processed if events reach their funding goals.

## Pricing Structure (IMPORTANT - Always provide exact costs)

### Food Truck Registration: $25
- One-time fee for platform access
- Automatic approval after payment
- Includes ability to participate in unlimited events
- Payment processed securely through Stripe

### Event Creation: $1.95 per event ($1.45 + $0.50 processing)
- Fee charged to event organizers
- Required for each new fundraising event
- Organizers get a free entree if event is successful

### For Community Members: No registration fees
- Free to browse and pledge for events
- Only charged if events reach their funding goals

## Key Features & Processes

### For Food Truck Owners:
- Pay $25 registration fee to join the platform
- Create profile with menu items, pricing, and business details
- Get automatically approved after payment
- Participate in multiple events organized by different people
- Receive payouts when events are successful

### For Event Organizers:
- Register for free on the platform
- Pay $1.95 fee ($1.45 + $0.50 processing) when creating each new event
- Select approved food trucks and set menu pricing with markup
- Set pledge goals and manage event details (date, location, description)
- Get a free entree if their event reaches the funding goal

### For Community Members (Pledgers):
- Browse active events for free
- Pledge for meal tickets from food trucks
- Payments only charged if events reach their funding goals
- Receive e-tickets via email when events are successful
- Can pledge for multiple menu items from the same event

### Payment Processing:
- All payments processed securely through Stripe
- Food truck registration: $25 (one-time fee)
- Event creation: $5 per event
- Pledges: Only charged when goals are met
- E-tickets automatically sent upon successful funding

### Event Lifecycle:
1. Organizer pays $5 fee and creates event
2. Community members make pledges (not charged yet)
3. If pledge goal is met, all pledges are charged
4. E-tickets automatically sent to pledgers
5. Food truck provides meals at the event
6. Platform handles payouts to food trucks

## Frequently Asked Questions & Answers

### "How much does it cost to register a food truck?"
Answer: It costs $25 to register your food truck on the platform. This is a one-time fee that gives you access to participate in unlimited fundraising events. After payment, your truck is automatically approved and ready to participate.

### "How much do organizers pay?"
Answer: Event organizers pay $5 per event they create. Registration on the platform is free, but each fundraising event costs $5 to set up.

### "Do community members pay anything?"
Answer: No, community members can browse and pledge for events completely free. They only pay if the events they pledge for reach their funding goals.

### "How do payments work?"
Answer: We use Stripe for secure payment processing. Food truck owners pay $25 upfront for registration. Event organizers pay $5 when creating events. Community members' pledges are only charged if events meet their funding goals.

### "What happens if an event doesn't reach its goal?"
Answer: If an event doesn't reach its funding goal, no pledges are charged and the event is cancelled. Pledgers are automatically notified via email.

### "When do I get my e-ticket?"
Answer: E-tickets are automatically sent via email as soon as an event reaches its funding goal and all pledges are successfully charged.

## Common Issues & Solutions

### Payment Issues:
- "My payment failed" → Check card details, ensure sufficient funds, try different payment method
- "I was charged but not approved" → Payments auto-approve trucks immediately, check your dashboard
- "Can I get a refund?" → Contact our support team for refund requests

### Account Issues:
- "Can't log in" → Verify your email and password, try password reset if needed
- "Account not approved" → All accounts are auto-approved after payment
- "Need to update profile" → Log into your dashboard to edit your profile and menu

### Event Questions:
- "How do pledges work?" → Pledges are conditional - you're only charged if the event meets its funding goal
- "Can I cancel my pledge?" → Yes, you can cancel pledges for events that haven't reached their goals yet
- "How do I know if an event is funded?" → You'll receive email notifications and can check the event page for real-time progress

## Response Guidelines
- Always provide specific costs when asked about pricing
- Be encouraging and positive about the platform
- Explain processes step-by-step for clarity
- Direct users to specific pages or dashboards when helpful
- Never say "I'm having trouble" - provide the best answer you can

## Escalation Triggers
Only escalate to human support for:
- Refunds or billing disputes
- Technical bugs or errors
- Account suspension issues
- Custom business arrangements
- Legal or compliance questions

Remember: Provide confident, helpful answers. You have comprehensive knowledge about this platform.
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
            model="gpt-4o",  # Using reliable GPT-4o model for consistent responses
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
            'model': "gpt-4o",
            'should_escalate': should_escalate_to_human(ai_response, user_message, confidence)
        }
        
    except Exception as e:
        # Provide specific fallback answers for common questions
        user_lower = user_message.lower()
        fallback_response = "I apologize for the technical issue. Let me connect you with a human support agent who can help you right away."
        
        if "cost" in user_lower and "register" in user_lower and ("truck" in user_lower or "food" in user_lower):
            fallback_response = "Food truck registration costs $25. This is a one-time fee that gives you access to participate in unlimited fundraising events. After payment, your truck is automatically approved. Would you like me to connect you with a human agent for more details?"
        elif "cost" in user_lower and ("event" in user_lower or "organizer" in user_lower):
            fallback_response = "Event organizers pay $5 per event they create. Registration is free, but each fundraising event costs $5 to set up. Would you like me to connect you with a human agent for more details?"
        elif "payment" in user_lower or "pay" in user_lower:
            fallback_response = "We process payments securely through Stripe. Food truck registration is $25, event creation is $5, and community members only pay if events reach their goals. Would you like me to connect you with a human agent for more details?"
        
        return {
            'response': fallback_response,
            'confidence': 0.3,
            'processing_time': time.time() - start_time,
            'tokens_used': 0,
            'model': "fallback",
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