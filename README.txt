================================================================
Student Name:  Ekaterina Inchakova
Student ID:    25028334
Module:        Web Development and Databases (UFCFES-30-1)
Project Title: Bristol Community Events (BCE)
================================================================

HOW TO RUN
----------
1. Install Python 3.10+ and MySQL Server 8+.

2. Create database and import the SQL dump:
      mysql -u root -p -e "CREATE DATABASE bce_db;"
      mysql -u root -p bce_db < The_most_final.sql

3. Open db.py and update your MySQL password on line 9:
      password=os.environ.get("DB_PASSWORD", "YOUR_PASSWORD_HERE")

4. Install Python dependencies:
      pip install flask mysql-connector-python werkzeug

5. Run the application:
      python app.py   (or python3 app.py on Mac)

6. Open in your browser:
      http://127.0.0.1:5000

================================================================
DEMO CREDENTIALS
================================================================
Admin:   admin@bce.com      / Admin2026!
User 1:  anna@bce.com       / User2026!
User 2:  daniel@bce.com     / User2026!
User 3:  maria@bce.com      / User2026!
User 4:  natasha@bce.com    / Natasha2026!

================================================================
FEATURES IMPLEMENTED
================================================================

END USER:
  [x] Register / Login / Logout / Change password
  [x] Browse and filter events (by category, venue, free-only,
      month, and custom date range)
  [x] Event detail page showing remaining tickets, booking
      deadline, and live discount preview
  [x] Standard ticket booking (1 or more tickets)
  [x] Multi-day event booking (select individual days; prices
      summed per selected day)
  [x] Advance booking discounts as per brief Table 2:
        50-60 days: 20% off
        35-50 days: 15% off
        25-35 days: 10% off
        15-25 days: 5% off
  [x] Student 10% discount (disclaimer: bring student ID)
  [x] Booking receipt with full price breakdown
      (base price, discounts applied, final price)
  [x] View all past and upcoming bookings (My Bookings)
  [x] Cancel booking with 3-tier cancellation fee logic:
        40+ days before event: full refund, no fee
        25-39 days: 40% cancellation fee
        Less than 25 days: no refund (100% fee)
  [x] Join waiting list for fully booked events
  [x] Contact form with message submission

ADMIN:
  [x] Dashboard with live statistics
  [x] Add, edit, and delete events (with image upload)
  [x] View all bookings with current status
  [x] Edit user details (name, email, phone, role, student flag)
  [x] Reset user passwords
  [x] Delete users (protected: cannot delete self or user with
      existing bookings)
  [x] Add and delete venues
  [x] Reports section:
        Revenue earned per event
        Number of bookings per event
        Tickets remaining per event
        Low booking alert (less than 50% sold within 10 days)
        with one-click 25% price reduction
        Upcoming events per venue
  [x] Contact message inbox with read / reply / delete actions

ADVANCED FEATURES:
  [x] Multi-day event booking (users select specific days)
  [x] Waiting list with automatic notification flag on
      cancellation (top of queue is marked IsNotified = 1)
  [x] Full cancellation fee logic with REFUNDS table entry
  [x] Low booking alert with direct price reduction button

SECURITY:
  [x] Password hashing using werkzeug (scrypt algorithm)
  [x] All SQL queries fully parameterised (SQL injection
      prevention)
  [x] Route protection via @login_required and @admin_required
      decorators
  [x] Jinja2 auto-escaping active (XSS prevention)
  [x] Server-side input validation on all forms
  [x] File upload restricted by extension and size (max 5 MB)
  [x] Admin cannot delete their own account

RESPONSIVE DESIGN (4 breakpoints):
  [x] max-width: 480px   — small mobile
  [x] max-width: 768px   — mobile / tablet
  [x] 769px to 1024px   — tablet / laptop
  [x] min-width: 1280px  — large desktop

DATABASE:
  [x] Normalised to 3NF
  [x] Foreign key constraints with ON DELETE / ON UPDATE rules
  [x] CHECK constraints on numeric fields
  [x] 12 tables including: USERS, ROLES, EVENTS, VENUES,
      EVENT_CATEGORIES, VENUES_EVENT_CATEGORIES, BOOKINGS,
      BOOKING_STATUS, BOOKING_STATUS_HISTORY, BOOKING_DISCOUNTS,
      DISCOUNTS, REFUNDS, WAITING_LIST, CONTACT_MESSAGES,
      EVENT_DAYS

================================================================
KNOWN LIMITATIONS
================================================================
- No CSRF token protection implemented. In a production
  environment Flask-WTF would be used to add CSRF tokens to
  all state-changing forms.
- Waiting list notification sets a database flag only; no
  real email is sent to the user.
- Database credentials should be managed as server environment
  variables in a production deployment.
================================================================
