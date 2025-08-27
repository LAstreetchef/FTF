#!/usr/bin/env python3
"""
Data Migration Script: Development to Production
================================================

This script migrates test data from your development database to production.
Run this script in your production environment (deployed app) to sync data.

IMPORTANT: This will overwrite existing data in production!
"""

import os
import sys
import psycopg2
from datetime import datetime
import json

# Production database URL (should be set in deployed environment)
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not found!")
    print("This script should be run in the production environment.")
    sys.exit(1)

# Data to migrate (exported from development)
ORGANIZERS_DATA = [
    (2, 'organizer@test.com', 'John Smith', 'scrypt:32768:8:1$yRpBhZ0bfnjkHI8k$382d065f8bc4b4d8043e0c578f86d7768315ebda9af69dbc2d794767e10aa43e99551fd8185ba961c71b7ff347eaad60e5a7ee419251a76615538284e9c52293', '2025-08-14 09:58:45.830691'),
    (1, 'kammiceli@gmail.com', 'keith miceli', 'scrypt:32768:8:1$yRpBhZ0bfnjkHI8k$382d065f8bc4b4d8043e0c578f86d7768315ebda9af69dbc2d794767e10aa43e99551fd8185ba961c71b7ff347eaad60e5a7ee419251a76615538284e9c52293', '2025-08-14 09:51:01.601366'),
    (3, 'ripplingbrook1920@gmail.com', 'Rippling Brook Clean Water Fund', 'scrypt:32768:8:1$m7wAm9EeIEjx1dxw$6a6d246be0bb251e341993a306d41b55a9beb83004495170b87ec562edea32c22c3598783dffd61d7f1f81730659535f9d4a87dd52dc4ce248afcaa44f3ac088', '2025-08-22 10:13:06.361016'),
    (4, 'debugtest@example.com', 'Debug Test User', 'scrypt:32768:8:1$aW1RzP5wQbJDrfOW$0bb193be91647bf7d546fed6befdf5bfc1e35486a50668fc5c0efa7b72a7b6d405f38f70f53d5c2f5eca4587f74441277a2a94b594866b9fbf25c4491263b75e', '2025-08-22 10:20:47.612492'),
    (5, 'holeechowtruck@gmail.com', 'HoLeeChow', 'scrypt:32768:8:1$TRRqrf6S9uBm3ewX$b103845cc863db312c93bbbfc3a758ab6a6eb304e672cec8d7c21b00909718767d4efd2edee0a17c8a82517f89c57c8b48b5f2ef48c62019a9ff5db3b5aa5d69', '2025-08-26 11:15:55.36559'),
    (6, 'marcsonson@gmail.com', 'Marc Sonson', 'scrypt:32768:8:1$LMD8zTfHbmaHUfOV$8c7c8f75ee228b1ff5be9b2b6614851022ad82a7137992263fae9c55d38278033d778cbead3a7e0af2c629687d90ce9bdfc84d26f0d89d891a39eaf4e17b917b', '2025-08-26 21:18:49.654951')
]

FOOD_TRUCKS_DATA = [
    (2, 'Tasty Tacos Truck', 'Authentic Mexican street tacos with fresh ingredients', '[{"name": "Carnitas Taco", "price": 4.5}, {"name": "Chicken Taco", "price": 4.0}, {"name": "Veggie Taco", "price": 3.75}, {"name": "Combo Meal", "price": 12.0}]', 500, None, None, None, 'pending', None, None, None, None, None, None, '2025-08-14 09:58:38.72585', False, None),
    (1, 'Tasty Tacos', 'LA\'s premiere healthy food truck', '[{"name": "Carnitas Taco", "price": 4.5}, {"name": "Chicken Taco", "price": 4.0}, {"name": "Veggie Taco", "price": 3.75}, {"name": "Combo Meal", "price": 12.0}]', 1500, None, None, None, 'pending', None, None, None, None, None, None, '2025-08-14 09:50:06.643711', False, None),
    (3, 'Acai Truck', 'Fresh and healthy acai bowls made with organic ingredients', '[{"name": "Classic Acai Bowl", "price": 12.5}, {"name": "Berry Blast Bowl", "price": 14.0}, {"name": "Green Goddess Bowl", "price": 13.25}, {"name": "Protein Power Bowl", "price": 15.5}, {"name": "Mini Acai Bowl", "price": 8.75}, {"name": "Acai Smoothie", "price": 7.5}]', 1750, None, None, None, 'pending', None, None, None, None, None, None, '2025-08-16 08:51:14.309754', False, None),
    (7, 'All In Cafe Truck', 'LA\'s original Cafe Truck', '', 1200, 4, 'Coffee + Smoothies', None, 'approved', '2025-08-26 14:16:18.348623', None, 'greentruck.sales@gmail.com', '3102040477', 'https://thefoodtruckstop.com', 'thetruckstop_la', '2025-08-26 14:11:38.978663', True, 'pi_3S0NbPEQF4GGt7S91sSUZvlx'),
    (8, 'Bad Ass Food Truck', 'Classic American Cuisine', '[{"name": "Grass-Fed Burger", "price": 17.5, "description": "1/3 lbs Grass-Fed Beef Patty, Aged Cheddar, Grilled Onions, Tomato"}]', 1000, 5, None, None, 'approved', '2025-08-27 18:26:22.530354', None, 'marcsonson@gmail.com', '7025968599', None, None, '2025-08-27 18:26:09.750925', True, 'pi_3S0o37Bgt3ltA59n0CJrM57S')
]

# Key events to migrate (the "Seeking Support" events from development)
EVENTS_DATA = [
    (5, 'Acai Bowl Fundraiser', 'Fresh and healthy acai bowls for a great cause', '2025-09-02 04:30:00', 'Community Center', 1, 3, '[{"name": "Classic Acai Bowl", "price": 12.50, "original_price": 12.50, "marked_up_price": 15.00}, {"name": "Berry Blast Bowl", "price": 14.00, "original_price": 14.00, "marked_up_price": 16.80}, {"name": "Green Goddess Bowl", "price": 13.25, "original_price": 13.25, "marked_up_price": 15.90}, {"name": "Protein Power Bowl", "price": 15.50, "original_price": 15.50, "marked_up_price": 18.60}, {"name": "Mini Acai Bowl", "price": 8.75, "original_price": 8.75, "marked_up_price": 10.50}, {"name": "Acai Smoothie", "price": 7.50, "original_price": 7.50, "marked_up_price": 9.00}]', 20, 1750, 'pending', 15, None, '2025-08-27 19:00:00', False, None, False),
    (21, 'USTA Junior Tournament Fundraiser', 'Fundraiser for USTA Juniors', '2025-08-30 11:30:00', '4212 CLUBHOUSE DR, LAKEWOOD, CA, 90712', 6, 8, '[{"name": "Grass-Fed Burger", "price": 17.5, "description": "1/3 lbs Grass-Fed Beef Patty, Aged Cheddar, Grilled Onions, Tomato", "original_price": 17.5, "marked_up_price": 20.12}]', 15, 1000, 'pending', 0, None, '2025-08-27 18:31:50.511637', True, 'pi_3S0o8mBgt3ltA59n0gsFvLwO', False),
    (20, 'Lakewood Tennis Center - Level 3 Open', 'USTA Junior Tournament', '2025-09-06 11:00:00', '4212 CLUBHOUSE DR, LAKEWOOD, CA, 90712', 6, 7, '[]', 15, 1200, 'pending', 45.12, None, '2025-08-27 17:58:01.385776', True, 'pi_3S0nbpBgt3ltA59n1f2poj1U', False)
]

def migrate_data():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        print("🚀 Starting data migration to production...")
        
        # Clear existing test data
        print("🗑️  Clearing existing events and pledges...")
        cur.execute("DELETE FROM pledge WHERE event_id IN (SELECT id FROM event)")
        cur.execute("DELETE FROM event")
        cur.execute("DELETE FROM food_truck WHERE id NOT IN (1, 2, 3, 7, 8)")  # Keep essential trucks
        cur.execute("DELETE FROM organizer WHERE id NOT IN (1, 2, 3, 4, 5, 6)")  # Keep our organizers
        
        # Reset sequences
        cur.execute("SELECT setval('event_id_seq', 1, false)")
        cur.execute("SELECT setval('pledge_id_seq', 1, false)")
        
        # Insert organizers (if not exist)
        print("👥 Migrating organizers...")
        for organizer in ORGANIZERS_DATA:
            cur.execute("""
                INSERT INTO organizer (id, email, name, password_hash, created_at) 
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                password_hash = EXCLUDED.password_hash,
                created_at = EXCLUDED.created_at
            """, organizer)
        
        # Insert food trucks
        print("🚚 Migrating food trucks...")
        for truck in FOOD_TRUCKS_DATA:
            cur.execute("""
                INSERT INTO food_truck (id, name, description, menu_items, sales_goal, owner_id, cuisine_type, logo_url, status, approved_at, approved_by, contact_email, contact_phone, website, instagram, created_at, registration_fee_charged, registration_fee_payment_intent) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                menu_items = EXCLUDED.menu_items,
                sales_goal = EXCLUDED.sales_goal,
                status = EXCLUDED.status
            """, truck)
        
        # Insert key events
        print("📅 Migrating events...")
        for event in EVENTS_DATA:
            cur.execute("""
                INSERT INTO event (id, name, description, date, location, organizer_id, food_truck_id, selected_menu_items, markup_percentage, pledge_goal, status, current_pledges, approved_at, created_at, organizer_fee_charged, organizer_fee_payment_intent, organizer_entree_claimed) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, event)
        
        # Update sequences to prevent conflicts
        cur.execute("SELECT setval('organizer_id_seq', (SELECT MAX(id) FROM organizer), true)")
        cur.execute("SELECT setval('food_truck_id_seq', (SELECT MAX(id) FROM food_truck), true)")
        cur.execute("SELECT setval('event_id_seq', (SELECT MAX(id) FROM event), true)")
        
        conn.commit()
        print("✅ Data migration completed successfully!")
        print("🎯 Key events migrated:")
        print("   - Acai Bowl Fundraiser")  
        print("   - USTA Junior Tournament Fundraiser")
        print("   - Lakewood Tennis Center - Level 3 Open")
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Migration failed: {str(e)}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    migrate_data()