# Food Truck Fundraiser

## Overview

A Flask-based web application that enables community crowdfunding for food truck events. Event organizers can create fundraising campaigns by selecting food trucks, setting menu items with markup pricing, and establishing pledge goals. Community members can pledge for meal tickets, with payments only processed if the event reaches its funding goal. The platform features admin management for food trucks, real-time progress tracking, and integrated payment processing through Stripe.

## User Preferences

Preferred communication style: Simple, everyday language.

## Recent Changes

- **2025-08-19**: Modern foodie theme transformation and event deletion system
  - Transformed app with vibrant, appetite-stimulating orange/yellow color scheme
  - Added Google Fonts (Poppins + Dancing Script) for enhanced typography
  - Created animated hero sections with floating patterns and food emojis
  - Enhanced cards with hover animations, gradients, and food-themed visual elements
  - Implemented shimmer effects on progress bars and smooth transitions
  - Updated navigation with gradient backgrounds and interactive hover states
  - Added foodie-themed buttons with warm gradients and enhanced hover effects
  - Replaced hero background with authentic food truck scene image for better engagement
  - Removed base price display from public event pages for cleaner pricing presentation
  - Created comprehensive event deletion functionality with safety checks
  - Added admin route `/admin/events/<id>/delete` with proper pledge handling
  - Fixed critical Flask startup error and improved overall code quality

- **2025-08-16**: Universal menu synchronization system implemented
  - Created comprehensive fix for menu display issues affecting all food trucks
  - Built `/auto-fix-all-menus-xyz123` route for complete truck/event menu synchronization  
  - Added automatic menu fallback protection to event creation process
  - Fixed Ho-Lee Chow menu display issues and extended solution to all trucks
  - Enhanced Green Truck menu with 8 items and proper pricing markup system
  - Implemented future-proof solution preventing menu sync issues for new events

- **2025-08-15**: Database integrity verification and admin system fixes
  - Fixed admin login credentials for deployed environment with debug routes
  - Updated pledge system to show menu-specific amounts instead of generic buttons
  - Verified and corrected database integrity (pledge totals, status consistency)
  - Fixed event status workflow to properly show "funded" events awaiting approval
  - Generated missing ticket codes for all charged pledges

- **2025-08-14**: Complete fundraising workflow implemented and tested
  - Fixed email confirmation system for pledges with Gmail SMTP
  - Successfully processed funded event with automatic payment charging
  - Generated and delivered e-tickets to all pledgers
  - Resolved event creation form UI issue (white block display problem)
  - Enhanced JavaScript for proper truck selection and menu display

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