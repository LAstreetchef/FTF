# Food Truck Fundraiser

## Overview

A Flask-based web application that enables community crowdfunding for food truck events. Event organizers can create fundraising campaigns by selecting food trucks, setting menu items with markup pricing, and establishing pledge goals. Community members can pledge for meal tickets, with payments only processed if the event reaches its funding goal. The platform features admin management for food trucks, real-time progress tracking, and integrated payment processing through Stripe.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask web framework with SQLAlchemy ORM for database operations
- **Database**: SQLite for local development with support for PostgreSQL via DATABASE_URL environment variable
- **Session Management**: Flask's built-in session handling with secure secret key configuration
- **Middleware**: ProxyFix middleware for proper header handling in production environments

### Frontend Architecture
- **Template Engine**: Jinja2 templating with a base template structure for consistent layout
- **CSS Framework**: Bootstrap with custom dark theme for responsive design
- **JavaScript**: Vanilla JavaScript with Feather icons for UI enhancements
- **Progressive Enhancement**: Auto-refresh functionality for real-time progress updates and form validation

### Authentication System
- **Multi-role Authentication**: Separate login systems for admins and event organizers
- **Password Security**: Werkzeug password hashing for secure credential storage
- **Session-based Access Control**: Role-based permissions using Flask sessions

### Payment Processing Architecture
- **Stripe Integration**: Payment intent creation with manual capture for conditional charging
- **Tokenization**: Secure card token storage without storing sensitive payment data
- **Conditional Charging**: Payments only processed when events meet funding goals

### Data Model Structure
- **Admin Management**: Simple admin accounts for platform management
- **Organizer System**: User registration for event creators with email-based authentication
- **Food Truck Catalog**: Truck profiles with JSON-stored menu items and sales goals
- **Event Management**: Event entities linking organizers, trucks, and pledge tracking
- **Pledge System**: Payment pledges with Stripe tokens for deferred charging

### Email Communication System
- **SMTP Integration**: Gmail SMTP configuration for transactional emails
- **Event Notifications**: Automated emails for goal achievements and payment confirmations
- **E-ticket Distribution**: Email-based ticket delivery upon successful payment processing

## External Dependencies

### Payment Processing
- **Stripe API**: Test mode integration for payment tokenization and charging
- Requires `STRIPE_SECRET_KEY` environment variable
- Handles payment intents with manual capture for conditional processing

### Email Services
- **Gmail SMTP**: Direct Gmail integration for email notifications
- Requires `GMAIL_USERNAME` and `GMAIL_PASSWORD` environment variables
- Handles transactional emails including pledges, confirmations, and e-tickets

### Frontend Libraries
- **Bootstrap CSS**: CDN-delivered responsive framework with dark theme
- **Feather Icons**: Lightweight icon library for consistent UI elements
- **Stripe.js**: Client-side payment form handling and tokenization

### Database Configuration
- **SQLite**: Default local development database
- **PostgreSQL**: Production database support via `DATABASE_URL` environment variable
- Connection pooling and health checks configured for production reliability