# University project: Bristol Community Events (BCE)

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from db import get_connection
from datetime import date, datetime
import mysql.connector
from mysql.connector import Error
from functools import wraps
import re
import os

def load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("Set SECRET_KEY in your environment before running the application.")

UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in first.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or session.get('role_name') != 'Admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('nl2br')
def nl2br_filter(text):
    if not text:
        return ''
    return text.replace('\n', '<br>\n')

@app.template_filter('format_datetime')
def format_datetime(value):
    if isinstance(value, datetime):
        return value.strftime('%d %b %Y, %H:%M')
    return value

def calculate_cancellation_fee(final_price, event_start_date):
    """
    Calculates cancellation fee based on days until event:
    - 40+ days before event: no fee (full refund)
    - 25-39 days before event: 40% cancellation fee
    - Less than 25 days before event: 100% cancellation fee (no refund)
    """
    today = date.today()
    if isinstance(event_start_date, datetime):
        event_start_date = event_start_date.date()

    days_until_event = (event_start_date - today).days

    if days_until_event >= 40:
        cancellation_fee = 0.00
        refund_amount = float(final_price)
        reason = "Cancelled more than 40 days before event – full refund"
    elif 25 <= days_until_event < 40:
        cancellation_fee = round(float(final_price) * 0.40, 2)
        refund_amount = round(float(final_price) - cancellation_fee, 2)
        reason = f"Cancelled {days_until_event} days before event – 40% cancellation fee applied"
    else:
        cancellation_fee = float(final_price)
        refund_amount = 0.00
        reason = f"Cancelled less than 25 days before event – no refund"

    return cancellation_fee, refund_amount, reason

def calculate_discount(base_total, days_in_advance, is_student):
    """
    Returns (final_price, list_of_discount_ids_applied)
    Advance booking discount IDs (from DISCOUNTS table):
      1 = 20% (50-60 days)
      2 = 15% (35-50 days)
      3 = 10% (25-35 days)
      4 = 5%  (15-25 days)
      5 = 10% student
    Discounts are multiplicative (student on top of advance).
    """
    final_price = base_total
    applied_discount_ids = []

    if 50 <= days_in_advance <= 60:
        final_price *= 0.80
        applied_discount_ids.append(1)
    elif 35 <= days_in_advance < 50:
        final_price *= 0.85
        applied_discount_ids.append(2)
    elif 25 <= days_in_advance < 35:
        final_price *= 0.90
        applied_discount_ids.append(3)
    elif 15 <= days_in_advance < 25:
        final_price *= 0.95
        applied_discount_ids.append(4)

    if is_student:
        final_price *= 0.90
        applied_discount_ids.append(5)

    return round(final_price, 2), applied_discount_ids

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not all([name, email, message]):
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('contact'))

        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('contact'))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO CONTACT_MESSAGES (FullName, Email, Subject, Message, CreatedAt, IsRead)
            VALUES (%s, %s, %s, %s, NOW(), 0)
        ''', (name, email, subject, message))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))

    return render_template('contact.html')

@app.route('/admin/messages')
@admin_required
def admin_messages():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM CONTACT_MESSAGES ORDER BY IsRead ASC, CreatedAt DESC')
    messages = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) as count FROM CONTACT_MESSAGES WHERE IsRead = 0')
    unread_count = cursor.fetchone()['count']
    cursor.execute('SELECT COUNT(*) as count FROM CONTACT_MESSAGES')
    total_messages = cursor.fetchone()['count']
    cursor.execute('SELECT COUNT(*) as count FROM CONTACT_MESSAGES WHERE IsReplied = 1')
    replied_count = cursor.fetchone()['count']
    cursor.close()
    conn.close()
    return render_template('admin_messages.html',
                           messages=messages,
                           unread_count=unread_count,
                           total_messages=total_messages,
                           replied_count=replied_count)

@app.route('/admin/messages/<int:message_id>/read', methods=['POST'])
@admin_required
def mark_message_read(message_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE CONTACT_MESSAGES SET IsRead = 1 WHERE MessageID = %s', (message_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/messages/<int:message_id>/reply', methods=['POST'])
@admin_required
def reply_to_message(message_id):
    data = request.get_json()
    reply_text = data.get('reply', '').strip()
    if not reply_text:
        return jsonify({'success': False, 'error': 'Reply text is required'}), 400
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM CONTACT_MESSAGES WHERE MessageID = %s', (message_id,))
    message = cursor.fetchone()
    if not message:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': 'Message not found'}), 404
    cursor.execute(
        'UPDATE CONTACT_MESSAGES SET IsReplied = 1, AdminReply = %s, RepliedAt = NOW(), IsRead = 1 WHERE MessageID = %s',
        (reply_text, message_id)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/admin/messages/<int:message_id>/delete', methods=['DELETE'])
@admin_required
def delete_message(message_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM CONTACT_MESSAGES WHERE MessageID = %s', (message_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

@app.route("/events")
def events():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    category = request.args.get('category', '')
    venue = request.args.get('venue', '')
    free_only = request.args.get('free_only', '')
    month = request.args.get('month', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = """
        SELECT
            e.EventID,
            e.EventName,
            e.Description,
            e.StartDate,
            e.EndDate,
            e.BasePrice,
            e.IsFree,
            e.ImageURL,
            e.MaxTickets,
            v.VenueName,
            c.CategoryName,
            COALESCE((SELECT SUM(b.NumberOfTickets)
                      FROM BOOKINGS b WHERE b.EventID = e.EventID), 0) AS tickets_booked
        FROM EVENTS e
        JOIN VENUES_EVENT_CATEGORIES vec ON e.VenuesEventCategoriesID = vec.VenuesEventCategoriesID
        JOIN VENUES v ON vec.VenueID = v.VenueID
        JOIN EVENT_CATEGORIES c ON vec.CategoryID = c.CategoryID
        WHERE 1=1
    """
    params = []

    if category:
        query += " AND c.CategoryName = %s"
        params.append(category)
    if venue:
        query += " AND v.VenueName = %s"
        params.append(venue)
    if free_only == '1':
        query += " AND e.IsFree = 1"
    if month:
        query += " AND MONTH(e.StartDate) = %s"
        params.append(month)
    if date_from:
        query += " AND e.StartDate >= %s"
        params.append(date_from)
    if date_to:
        query += " AND e.StartDate <= %s"
        params.append(date_to)

    query += " ORDER BY e.StartDate ASC"

    cursor.execute(query, tuple(params))
    events_list = cursor.fetchall()

    for ev in events_list:
        ev['remaining_tickets'] = ev['MaxTickets'] - int(ev['tickets_booked'])

    cursor.execute("SELECT CategoryName FROM EVENT_CATEGORIES ORDER BY CategoryName ASC")
    categories = cursor.fetchall()
    cursor.execute("SELECT VenueName FROM VENUES ORDER BY VenueName ASC")
    venues = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "events.html",
        events=events_list,
        categories=categories,
        venues=venues,
        selected_category=category,
        selected_venue=venue,
        selected_free_only=free_only,
        selected_month=month,
        selected_date_from=date_from,
        selected_date_to=date_to
    )

@app.route("/event/<int:id>")
def event_detail(id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT
        e.EventID, e.EventName, e.Description,
        e.StartDate, e.EndDate, e.BasePrice, e.IsFree,
        e.MaxTickets, e.BookingDeadline, e.ImageURL,
        v.VenueName, c.CategoryName
    FROM EVENTS e
    JOIN VENUES_EVENT_CATEGORIES vec ON e.VenuesEventCategoriesID = vec.VenuesEventCategoriesID
    JOIN VENUES v ON vec.VenueID = v.VenueID
    JOIN EVENT_CATEGORIES c ON vec.CategoryID = c.CategoryID
    WHERE e.EventID = %s
    """
    cursor.execute(query, (id,))
    event = cursor.fetchone()

    if not event:
        cursor.close()
        conn.close()
        flash("Event not found.", 'error')
        return redirect(url_for("events"))

    cursor.execute(
        "SELECT COALESCE(SUM(NumberOfTickets), 0) AS tickets_booked FROM BOOKINGS WHERE EventID = %s",
        (id,)
    )
    tickets_booked = cursor.fetchone()['tickets_booked']
    remaining_tickets = event['MaxTickets'] - int(tickets_booked)

    cursor.execute(
        "SELECT EventDate, DayPrice FROM EVENT_DAYS WHERE EventID = %s ORDER BY EventDate ASC",
        (id,)
    )
    event_days = cursor.fetchall()

    on_waiting_list = False
    if session.get('user_id'):
        cursor.execute(
            "SELECT WaitlistID FROM WAITING_LIST WHERE EventID = %s AND UserID = %s AND IsNotified = 0",
            (id, session['user_id'])
        )
        on_waiting_list = cursor.fetchone() is not None

    cursor.close()
    conn.close()

    today = date.today()
    days_in_advance = (event['StartDate'] - today).days if isinstance(event['StartDate'], date) else 0
    discount_preview = None
    if days_in_advance >= 50:
        discount_preview = "20% advance booking discount applies!"
    elif days_in_advance >= 35:
        discount_preview = "15% advance booking discount applies!"
    elif days_in_advance >= 25:
        discount_preview = "10% advance booking discount applies!"
    elif days_in_advance >= 15:
        discount_preview = "5% advance booking discount applies!"

    return render_template(
        "event_detail.html",
        event=event,
        remaining_tickets=remaining_tickets,
        event_days=event_days,
        on_waiting_list=on_waiting_list,
        discount_preview=discount_preview,
        days_in_advance=days_in_advance
    )

@app.route('/book/<int:event_id>', methods=['POST'])
@login_required
def book_event(event_id):
    try:
        number_of_tickets = int(request.form.get('number_of_tickets', 1))
        if number_of_tickets < 1:
            flash('Please select at least 1 ticket.', 'error')
            return redirect(url_for('event_detail', id=event_id))
    except (ValueError, TypeError):
        flash('Invalid number of tickets.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT EventID, EventName, BasePrice, IsFree, MaxTickets, BookingDeadline, StartDate
        FROM EVENTS WHERE EventID = %s
    """, (event_id,))
    event = cursor.fetchone()

    if not event:
        cursor.close()
        conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events'))

    today = date.today()

    deadline = event['BookingDeadline']
    if isinstance(deadline, datetime):
        deadline = deadline.date()
    if today > deadline:
        cursor.close()
        conn.close()
        flash('Booking deadline has passed for this event.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    start = event['StartDate']
    if isinstance(start, datetime):
        start = start.date()
    days_in_advance = (start - today).days
    if days_in_advance > 60:
        cursor.close()
        conn.close()
        flash('Bookings can only be made up to 2 months (60 days) in advance.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    cursor.execute(
        "SELECT COALESCE(SUM(NumberOfTickets), 0) AS tickets_booked FROM BOOKINGS WHERE EventID = %s",
        (event_id,)
    )
    tickets_booked = int(cursor.fetchone()['tickets_booked'])
    remaining_tickets = event['MaxTickets'] - tickets_booked

    if remaining_tickets <= 0:
        cursor.close()
        conn.close()
        flash('Sorry, this event is fully booked. Please join the waiting list.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    if number_of_tickets > remaining_tickets:
        cursor.close()
        conn.close()
        flash(f'Only {remaining_tickets} ticket(s) remaining. Please reduce your quantity.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    cursor.execute("SELECT IsStudent FROM USERS WHERE UserID = %s", (user_id,))
    user = cursor.fetchone()
    is_student = bool(user['IsStudent']) if user else False

    base_price = 0.0 if event['IsFree'] else float(event['BasePrice'])
    base_total = base_price * number_of_tickets
    final_price, applied_discount_ids = calculate_discount(base_total, days_in_advance, is_student)

    cursor.execute("""
        INSERT INTO BOOKINGS (BookingDate, NumberOfTickets, BasePricePerTicket, FinalPrice, UserID, EventID)
        VALUES (NOW(), %s, %s, %s, %s, %s)
    """, (number_of_tickets, base_price, final_price, user_id, event_id))
    conn.commit()
    booking_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO BOOKING_STATUS_HISTORY (ChangedAt, BookingID, StatusID)
        VALUES (NOW(), %s, 2)
    """, (booking_id,))

    for discount_id in applied_discount_ids:
        cursor.execute("""
            INSERT IGNORE INTO BOOKING_DISCOUNTS (DiscountID, BookingID) VALUES (%s, %s)
        """, (discount_id, booking_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash('Booking confirmed successfully!', 'success')
    return redirect(url_for('booking_receipt', booking_id=booking_id))

@app.route('/receipt/<int:booking_id>')
@login_required
def booking_receipt(booking_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            b.BookingID, b.BookingDate, b.NumberOfTickets,
            b.BasePricePerTicket, b.FinalPrice,
            e.EventName, e.StartDate, e.VenuesEventCategoriesID,
            u.FullName, u.Email,
            v.VenueName
        FROM BOOKINGS b
        JOIN EVENTS e ON b.EventID = e.EventID
        JOIN USERS u ON b.UserID = u.UserID
        JOIN VENUES_EVENT_CATEGORIES vec ON e.VenuesEventCategoriesID = vec.VenuesEventCategoriesID
        JOIN VENUES v ON vec.VenueID = v.VenueID
        WHERE b.BookingID = %s AND b.UserID = %s
    """, (booking_id, session['user_id']))
    booking = cursor.fetchone()

    if not booking:
        cursor.close()
        conn.close()
        flash('Receipt not found.', 'error')
        return redirect(url_for('home'))

    cursor.execute("""
        SELECT d.DiscountName, d.DiscountValue
        FROM BOOKING_DISCOUNTS bd
        JOIN DISCOUNTS d ON bd.DiscountID = d.DiscountID
        WHERE bd.BookingID = %s
    """, (booking_id,))
    discounts = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('receipt.html', booking=booking, discounts=discounts)

@app.route('/my-bookings')
@login_required
def my_bookings():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            b.BookingID, b.BookingDate, b.NumberOfTickets, b.FinalPrice,
            e.EventID, e.EventName, e.StartDate,
            bs.StatusName
        FROM BOOKINGS b
        JOIN EVENTS e ON b.EventID = e.EventID
        LEFT JOIN (
            SELECT bsh.BookingID, bsh.StatusID
            FROM BOOKING_STATUS_HISTORY bsh
            INNER JOIN (
                SELECT BookingID, MAX(ChangedAt) AS latest_change
                FROM BOOKING_STATUS_HISTORY GROUP BY BookingID
            ) latest ON bsh.BookingID = latest.BookingID AND bsh.ChangedAt = latest.latest_change
        ) latest_status ON b.BookingID = latest_status.BookingID
        LEFT JOIN BOOKING_STATUS bs ON latest_status.StatusID = bs.StatusID
        WHERE b.UserID = %s
        ORDER BY b.BookingDate DESC
    """, (session['user_id'],))
    bookings = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/cancel-booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT b.BookingID, b.UserID, b.FinalPrice, e.StartDate
        FROM BOOKINGS b
        JOIN EVENTS e ON b.EventID = e.EventID
        WHERE b.BookingID = %s AND b.UserID = %s
    """, (booking_id, user_id))
    booking = cursor.fetchone()

    if not booking:
        cursor.close()
        conn.close()
        flash('Booking not found.', 'error')
        return redirect(url_for('my_bookings'))

    cursor.execute("""
        SELECT bs.StatusName FROM BOOKING_STATUS_HISTORY bsh
        JOIN BOOKING_STATUS bs ON bsh.StatusID = bs.StatusID
        WHERE bsh.BookingID = %s ORDER BY bsh.ChangedAt DESC LIMIT 1
    """, (booking_id,))
    current_status = cursor.fetchone()

    if current_status and current_status['StatusName'] in ['Cancelled', 'Refunded']:
        cursor.close()
        conn.close()
        flash('This booking has already been cancelled.', 'error')
        return redirect(url_for('my_bookings'))

    event_start = booking['StartDate']
    if isinstance(event_start, datetime):
        event_start = event_start.date()

    today = date.today()
    if event_start < today:
        cursor.close()
        conn.close()
        flash('Past event bookings cannot be cancelled.', 'error')
        return redirect(url_for('my_bookings'))

    cancellation_fee, refund_amount, reason = calculate_cancellation_fee(booking['FinalPrice'], event_start)

    cursor.execute("""
        INSERT INTO BOOKING_STATUS_HISTORY (ChangedAt, BookingID, StatusID) VALUES (NOW(), %s, 3)
    """, (booking_id,))

    cursor.execute("""
        INSERT INTO REFUNDS (RefundDate, RefundAmount, CancellationFee, Reason, BookingID)
        VALUES (NOW(), %s, %s, %s, %s)
    """, (refund_amount, cancellation_fee, reason, booking_id))

    cursor.execute("""
        INSERT INTO BOOKING_STATUS_HISTORY (ChangedAt, BookingID, StatusID) VALUES (NOW(), %s, 4)
    """, (booking_id,))

    conn.commit()

    cursor.execute("""
        SELECT w.WaitlistID, w.UserID, u.Email, u.FullName
        FROM WAITING_LIST w
        JOIN USERS u ON w.UserID = u.UserID
        WHERE w.EventID = (SELECT EventID FROM BOOKINGS WHERE BookingID = %s)
          AND w.IsNotified = 0
        ORDER BY w.JoinedAt ASC
        LIMIT 1
    """, (booking_id,))
    next_in_line = cursor.fetchone()

    if next_in_line:
        cursor.execute(
            "UPDATE WAITING_LIST SET IsNotified = 1 WHERE WaitlistID = %s",
            (next_in_line['WaitlistID'],)
        )
        conn.commit()
        flash(f'Booking cancelled. {next_in_line["FullName"]} from the waiting list has been notified.', 'info')

    cursor.close()
    conn.close()

    if cancellation_fee == 0:
        flash('Booking cancelled. Full refund will be processed.', 'success')
    elif refund_amount == 0:
        flash('Booking cancelled. No refund applies (less than 25 days before event).', 'warning')
    else:
        flash(f'Booking cancelled. Refund: £{refund_amount:.2f} (40% cancellation fee of £{cancellation_fee:.2f} applied).', 'warning')

    return redirect(url_for('my_bookings'))

@app.route('/join-waiting-list/<int:event_id>', methods=['POST'])
@login_required
def join_waiting_list(event_id):
    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT EventID, EventName FROM EVENTS WHERE EventID = %s", (event_id,))
    event = cursor.fetchone()
    if not event:
        cursor.close()
        conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events'))

    cursor.execute(
        "SELECT WaitlistID FROM WAITING_LIST WHERE EventID = %s AND UserID = %s AND IsNotified = 0",
        (event_id, user_id)
    )
    existing = cursor.fetchone()
    if existing:
        cursor.close()
        conn.close()
        flash('You are already on the waiting list for this event.', 'info')
        return redirect(url_for('event_detail', id=event_id))

    cursor.execute(
        "INSERT INTO WAITING_LIST (EventID, UserID, JoinedAt, IsNotified) VALUES (%s, %s, NOW(), 0)",
        (event_id, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash(f'You have been added to the waiting list for "{event["EventName"]}".', 'success')
    return redirect(url_for('event_detail', id=event_id))

@app.route('/book-days/<int:event_id>', methods=['POST'])
@login_required
def book_event_days(event_id):
    """Multi-day booking: user selects specific EVENT_DAYS dates."""
    selected_days = request.form.getlist('selected_days')

    if not selected_days:
        flash('Please select at least one day.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT EventID, EventName, IsFree, MaxTickets, BookingDeadline, StartDate FROM EVENTS WHERE EventID = %s",
        (event_id,)
    )
    event = cursor.fetchone()
    if not event:
        cursor.close(); conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('events'))

    today = date.today()
    deadline = event['BookingDeadline']
    if isinstance(deadline, datetime):
        deadline = deadline.date()
    if today > deadline:
        cursor.close(); conn.close()
        flash('Booking deadline has passed.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    start = event['StartDate']
    if isinstance(start, datetime):
        start = start.date()
    days_in_advance = (start - today).days
    if days_in_advance > 60:
        cursor.close(); conn.close()
        flash('Bookings open up to 60 days in advance.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    cursor.execute(
        "SELECT COALESCE(SUM(NumberOfTickets),0) AS booked FROM BOOKINGS WHERE EventID=%s",
        (event_id,)
    )
    booked = int(cursor.fetchone()['booked'])
    remaining = event['MaxTickets'] - booked
    num_days = len(selected_days)
    if num_days > remaining:
        cursor.close(); conn.close()
        flash(f'Only {remaining} slot(s) available. Reduce your day selection.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    placeholders = ','.join(['%s'] * len(selected_days))
    cursor.execute(
        "SELECT EventDate, DayPrice FROM EVENT_DAYS WHERE EventID=%s AND EventDate IN (" + placeholders + ")",
        [event_id] + selected_days
    )
    day_rows = cursor.fetchall()
    if len(day_rows) != num_days:
        cursor.close(); conn.close()
        flash('Some selected dates are invalid.', 'error')
        return redirect(url_for('event_detail', id=event_id))

    base_total = sum(float(d['DayPrice']) for d in day_rows)
    cursor.execute("SELECT IsStudent FROM USERS WHERE UserID=%s", (user_id,))
    user_row = cursor.fetchone()
    is_student = bool(user_row['IsStudent']) if user_row else False

    final_price, applied_discount_ids = calculate_discount(base_total, days_in_advance, is_student)
    base_per_ticket = round(base_total / num_days, 2) if num_days > 0 else 0

    cursor.execute(
        "INSERT INTO BOOKINGS (BookingDate,NumberOfTickets,BasePricePerTicket,FinalPrice,UserID,EventID) VALUES (NOW(),%s,%s,%s,%s,%s)",
        (num_days, base_per_ticket, final_price, user_id, event_id)
    )
    conn.commit()
    booking_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO BOOKING_STATUS_HISTORY (ChangedAt,BookingID,StatusID) VALUES (NOW(),%s,2)",
        (booking_id,)
    )
    for did in applied_discount_ids:
        cursor.execute(
            "INSERT IGNORE INTO BOOKING_DISCOUNTS (DiscountID,BookingID) VALUES (%s,%s)",
            (did, booking_id)
        )
    conn.commit()
    cursor.close(); conn.close()

    flash('Multi-day booking confirmed!', 'success')
    return redirect(url_for('booking_receipt', booking_id=booking_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        is_student = 1 if request.form.get('is_student') == 'on' else 0

        if not full_name or not email or not password:
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('register'))

        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('register'))

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT UserID FROM USERS WHERE Email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO USERS (FullName, Email, Phone, PasswordHash, IsStudent, RoleID)
            VALUES (%s, %s, %s, %s, %s, 2)
        """, (full_name, email, phone, password_hash, is_student))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.UserID, u.FullName, u.Email, u.PasswordHash, u.RoleID, r.RoleName
            FROM USERS u
            JOIN ROLES r ON u.RoleID = r.RoleID
            WHERE u.Email = %s
        """, (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user['PasswordHash'], password):
            session['user_id'] = user['UserID']
            session['full_name'] = user['FullName']
            session['email'] = user['Email']
            session['role_id'] = user['RoleID']
            session['role_name'] = user['RoleName']
            flash(f'Welcome back, {user["FullName"]}!', 'success')
            return redirect(url_for('home'))

        flash('Invalid email or password. Please try again.', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_new_password = request.form.get('confirm_new_password', '')

        if new_password != confirm_new_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('change_password'))

        if len(new_password) < 6:
            flash('New password must be at least 6 characters.', 'error')
            return redirect(url_for('change_password'))

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT PasswordHash FROM USERS WHERE UserID = %s", (session['user_id'],))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['PasswordHash'], old_password):
            cursor.close()
            conn.close()
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('change_password'))

        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE USERS SET PasswordHash = %s WHERE UserID = %s", (new_hash, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Password updated successfully!', 'success')
        return redirect(url_for('home'))

    return render_template('change_password.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT COUNT(*) as count FROM CONTACT_MESSAGES WHERE IsRead = 0')
    unread_count = cursor.fetchone()['count']
    cursor.execute('SELECT COUNT(*) as count FROM EVENTS')
    total_events = cursor.fetchone()['count']
    cursor.execute('SELECT COUNT(*) as count FROM BOOKINGS')
    total_bookings = cursor.fetchone()['count']
    cursor.execute('SELECT COUNT(*) as count FROM USERS WHERE RoleID = 2')
    total_users = cursor.fetchone()['count']
    cursor.execute('SELECT COALESCE(SUM(FinalPrice),0) as total FROM BOOKINGS')
    total_revenue = cursor.fetchone()['total']
    cursor.close()
    conn.close()
    return render_template('admin_dashboard.html',
                           unread_messages_count=unread_count,
                           total_events=total_events,
                           total_bookings=total_bookings,
                           total_users=total_users,
                           total_revenue=total_revenue)

@app.route('/admin/events')
@admin_required
def admin_events():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            e.EventID, e.EventName, e.StartDate, e.EndDate,
            e.BasePrice, e.IsFree, e.MaxTickets, e.BookingDeadline, e.ImageURL,
            v.VenueName, c.CategoryName,
            COALESCE((SELECT SUM(b.NumberOfTickets) FROM BOOKINGS b WHERE b.EventID = e.EventID), 0) AS tickets_sold
        FROM EVENTS e
        JOIN VENUES_EVENT_CATEGORIES vec ON e.VenuesEventCategoriesID = vec.VenuesEventCategoriesID
        JOIN VENUES v ON vec.VenueID = v.VenueID
        JOIN EVENT_CATEGORIES c ON vec.CategoryID = c.CategoryID
        ORDER BY e.StartDate ASC
    """)
    events_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_events.html', events=events_list)

@app.route('/admin/events/add', methods=['GET', 'POST'])
@admin_required
def admin_add_event():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT vec.VenuesEventCategoriesID, v.VenueName, c.CategoryName
        FROM VENUES_EVENT_CATEGORIES vec
        JOIN VENUES v ON vec.VenueID = v.VenueID
        JOIN EVENT_CATEGORIES c ON vec.CategoryID = c.CategoryID
        ORDER BY v.VenueName, c.CategoryName
    """)
    venue_category_options = cursor.fetchall()

    if request.method == 'POST':
        event_name = request.form.get('event_name', '').strip()
        description = request.form.get('description', '').strip()
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        base_price = request.form.get('base_price', 0)
        is_free = 1 if request.form.get('is_free') == 'on' else 0
        max_tickets = request.form.get('max_tickets')
        booking_deadline = request.form.get('booking_deadline')
        vec_id = request.form.get('vec_id')

        if is_free:
            base_price = 0

        if end_date < start_date:
            flash('End date cannot be earlier than start date.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_add_event'))

        if booking_deadline > start_date:
            flash('Booking deadline cannot be later than start date.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_add_event'))

        image_filename = None
        if 'event_image' in request.files:
            file = request.files['event_image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                image_filename = f"{name}_{timestamp}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        cursor.execute("""
            INSERT INTO EVENTS
            (EventName, Description, StartDate, EndDate, BasePrice, IsFree, MaxTickets, BookingDeadline, VenuesEventCategoriesID, ImageURL)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (event_name, description, start_date, end_date, base_price, is_free, max_tickets, booking_deadline, vec_id, image_filename))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Event added successfully!', 'success')
        return redirect(url_for('admin_events'))

    cursor.close()
    conn.close()
    return render_template('admin_add_event.html', venue_category_options=venue_category_options)

@app.route('/admin/events/edit/<int:event_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_event(event_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM EVENTS WHERE EventID = %s", (event_id,))
    event = cursor.fetchone()
    if not event:
        cursor.close()
        conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('admin_events'))

    cursor.execute("""
        SELECT vec.VenuesEventCategoriesID, v.VenueName, c.CategoryName
        FROM VENUES_EVENT_CATEGORIES vec
        JOIN VENUES v ON vec.VenueID = v.VenueID
        JOIN EVENT_CATEGORIES c ON vec.CategoryID = c.CategoryID
        ORDER BY v.VenueName, c.CategoryName
    """)
    venue_category_options = cursor.fetchall()

    if request.method == 'POST':
        event_name = request.form.get('event_name', '').strip()
        description = request.form.get('description', '').strip()
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        base_price = request.form.get('base_price', 0)
        is_free = 1 if request.form.get('is_free') == 'on' else 0
        max_tickets = request.form.get('max_tickets')
        booking_deadline = request.form.get('booking_deadline')
        vec_id = request.form.get('vec_id')

        if is_free:
            base_price = 0

        if end_date < start_date:
            flash('End date cannot be earlier than start date.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_edit_event', event_id=event_id))

        if booking_deadline > start_date:
            flash('Booking deadline cannot be later than start date.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('admin_edit_event', event_id=event_id))

        image_filename = event['ImageURL']
        remove_image = request.form.get('remove_image') == 'on'

        if 'event_image' in request.files:
            file = request.files['event_image']
            if file and file.filename and allowed_file(file.filename):
                if image_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(file.filename)
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                image_filename = f"{name}_{timestamp}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        if remove_image and image_filename:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            if os.path.exists(old_path):
                os.remove(old_path)
            image_filename = None

        cursor.execute("""
            UPDATE EVENTS SET
                EventName = %s, Description = %s, StartDate = %s, EndDate = %s,
                BasePrice = %s, IsFree = %s, MaxTickets = %s, BookingDeadline = %s,
                VenuesEventCategoriesID = %s, ImageURL = %s
            WHERE EventID = %s
        """, (event_name, description, start_date, end_date, base_price, is_free,
              max_tickets, booking_deadline, vec_id, image_filename, event_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Event updated successfully!', 'success')
        return redirect(url_for('admin_events'))

    cursor.close()
    conn.close()
    return render_template('admin_edit_event.html', event=event, venue_category_options=venue_category_options)

@app.route('/admin/events/delete/<int:event_id>', methods=['POST'])
@admin_required
def admin_delete_event(event_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT ImageURL FROM EVENTS WHERE EventID = %s", (event_id,))
    event = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS total FROM BOOKINGS WHERE EventID = %s", (event_id,))
    if cursor.fetchone()['total'] > 0:
        cursor.close()
        conn.close()
        flash("Cannot delete: this event has existing bookings.", 'error')
        return redirect(url_for('admin_events'))

    if event and event['ImageURL']:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], event['ImageURL'])
        if os.path.exists(image_path):
            os.remove(image_path)

    cursor.execute("DELETE FROM EVENTS WHERE EventID = %s", (event_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Event deleted successfully.", 'success')
    return redirect(url_for('admin_events'))

@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            b.BookingID, b.BookingDate, b.NumberOfTickets, b.FinalPrice,
            u.FullName, u.Email, e.EventName, e.StartDate,
            bs.StatusName
        FROM BOOKINGS b
        JOIN USERS u ON b.UserID = u.UserID
        JOIN EVENTS e ON b.EventID = e.EventID
        LEFT JOIN (
            SELECT bsh.BookingID, bsh.StatusID
            FROM BOOKING_STATUS_HISTORY bsh
            INNER JOIN (
                SELECT BookingID, MAX(ChangedAt) AS latest_change
                FROM BOOKING_STATUS_HISTORY GROUP BY BookingID
            ) latest ON bsh.BookingID = latest.BookingID AND bsh.ChangedAt = latest.latest_change
        ) latest_status ON b.BookingID = latest_status.BookingID
        LEFT JOIN BOOKING_STATUS bs ON latest_status.StatusID = bs.StatusID
        ORDER BY b.BookingDate DESC
    """)
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_bookings.html', bookings=bookings)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT e.EventName, COUNT(b.BookingID) AS total_bookings,
               COALESCE(SUM(b.NumberOfTickets), 0) AS total_tickets_sold
        FROM EVENTS e LEFT JOIN BOOKINGS b ON e.EventID = b.EventID
        GROUP BY e.EventID, e.EventName ORDER BY total_bookings DESC
    """)
    bookings_per_event = cursor.fetchall()

    cursor.execute("""
        SELECT e.EventName, e.MaxTickets,
               COALESCE(SUM(b.NumberOfTickets), 0) AS tickets_booked,
               (e.MaxTickets - COALESCE(SUM(b.NumberOfTickets), 0)) AS tickets_left
        FROM EVENTS e LEFT JOIN BOOKINGS b ON e.EventID = b.EventID
        GROUP BY e.EventID, e.EventName, e.MaxTickets ORDER BY e.StartDate ASC
    """)
    tickets_left_report = cursor.fetchall()

    cursor.execute("""
        SELECT e.EventName, COALESCE(SUM(b.FinalPrice), 0) AS total_revenue
        FROM EVENTS e LEFT JOIN BOOKINGS b ON e.EventID = b.EventID
        GROUP BY e.EventID, e.EventName ORDER BY total_revenue DESC
    """)
    revenue_report = cursor.fetchall()

    cursor.execute("""
        SELECT e.EventID, e.EventName, e.StartDate, e.MaxTickets, e.BasePrice,
               COALESCE(SUM(b.NumberOfTickets), 0) AS tickets_booked,
               ROUND(COALESCE(SUM(b.NumberOfTickets), 0) / e.MaxTickets * 100, 1) AS booking_pct,
               DATEDIFF(e.StartDate, CURDATE()) AS days_until_event
        FROM EVENTS e LEFT JOIN BOOKINGS b ON e.EventID = b.EventID
        WHERE DATEDIFF(e.StartDate, CURDATE()) BETWEEN 0 AND 10
        GROUP BY e.EventID, e.EventName, e.StartDate, e.MaxTickets, e.BasePrice
        HAVING booking_pct < 50
        ORDER BY e.StartDate ASC
    """)
    low_booking_events = cursor.fetchall()

    cursor.execute("""
        SELECT v.VenueName, COUNT(e.EventID) AS upcoming_events
        FROM VENUES v
        LEFT JOIN VENUES_EVENT_CATEGORIES vec ON v.VenueID = vec.VenueID
        LEFT JOIN EVENTS e ON vec.VenuesEventCategoriesID = e.VenuesEventCategoriesID
            AND e.StartDate >= CURDATE()
        GROUP BY v.VenueID, v.VenueName ORDER BY upcoming_events DESC
    """)
    venue_upcoming = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin_reports.html',
                           bookings_per_event=bookings_per_event,
                           tickets_left_report=tickets_left_report,
                           revenue_report=revenue_report,
                           low_booking_events=low_booking_events,
                           venue_upcoming=venue_upcoming)

@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.UserID, u.FullName, u.Email, u.Phone, u.IsStudent, r.RoleName
        FROM USERS u JOIN ROLES r ON u.RoleID = r.RoleID
        ORDER BY u.UserID ASC
    """)
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/reset-password/<int:user_id>', methods=['POST'])
@admin_required
def admin_reset_password(user_id):
    new_password = request.form.get('new_password', '').strip()
    if len(new_password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('admin_users'))
    conn = get_connection()
    cursor = conn.cursor()
    new_hash = generate_password_hash(new_password)
    cursor.execute("UPDATE USERS SET PasswordHash = %s WHERE UserID = %s", (new_hash, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash('User password updated successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_user(user_id):
    import re as _re
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT RoleID, RoleName FROM ROLES ORDER BY RoleID ASC")
    roles = cursor.fetchall()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        role_id = request.form.get('role_id', '').strip()
        is_student = 1 if request.form.get('is_student') == 'on' else 0

        if not full_name or not email or not role_id:
            flash('Name, email and role are required.', 'error')
            cursor.execute("SELECT * FROM USERS WHERE UserID = %s", (user_id,))
            user = cursor.fetchone()
            cursor.close(); conn.close()
            return render_template('admin_edit_user.html', user=user, roles=roles)

        if not _re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash('Invalid email address.', 'error')
            cursor.execute("SELECT * FROM USERS WHERE UserID = %s", (user_id,))
            user = cursor.fetchone()
            cursor.close(); conn.close()
            return render_template('admin_edit_user.html', user=user, roles=roles)

        cursor.execute("SELECT UserID FROM USERS WHERE Email = %s AND UserID != %s", (email, user_id))
        if cursor.fetchone():
            flash('This email is already used by another account.', 'error')
            cursor.execute("SELECT * FROM USERS WHERE UserID = %s", (user_id,))
            user = cursor.fetchone()
            cursor.close(); conn.close()
            return render_template('admin_edit_user.html', user=user, roles=roles)

        cursor.execute(
            "UPDATE USERS SET FullName=%s, Email=%s, Phone=%s, RoleID=%s, IsStudent=%s WHERE UserID=%s",
            (full_name, email, phone, role_id, is_student, user_id)
        )
        conn.commit()
        cursor.close(); conn.close()
        flash(f'User updated successfully.', 'success')
        return redirect(url_for('admin_users'))

    cursor.execute("SELECT * FROM USERS WHERE UserID = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close(); conn.close()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin_users'))
    return render_template('admin_edit_user.html', user=user, roles=roles)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_users'))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as total FROM BOOKINGS WHERE UserID = %s", (user_id,))
    if cursor.fetchone()['total'] > 0:
        cursor.close(); conn.close()
        flash('Cannot delete: this user has existing bookings.', 'error')
        return redirect(url_for('admin_users'))
    cursor.execute("DELETE FROM USERS WHERE UserID = %s", (user_id,))
    conn.commit()
    cursor.close(); conn.close()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/venues')
@admin_required
def admin_venues():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM VENUES ORDER BY VenueName ASC")
    venues = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_venues.html', venues=venues)

@app.route('/admin/venues/add', methods=['POST'])
@admin_required
def admin_add_venue():
    venue_name = request.form.get('venue_name', '').strip()
    address = request.form.get('address', '').strip()
    capacity = request.form.get('capacity', '').strip()
    description = request.form.get('description', '').strip()

    if not venue_name or not address or not capacity:
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('admin_venues'))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO VENUES (VenueName, Address, Capacity, Description)
        VALUES (%s, %s, %s, %s)
    """, (venue_name, address, capacity, description))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Venue added successfully!', 'success')
    return redirect(url_for('admin_venues'))

@app.route('/admin/venues/delete/<int:venue_id>', methods=['POST'])
@admin_required
def admin_delete_venue(venue_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as total FROM VENUES_EVENT_CATEGORIES WHERE VenueID = %s", (venue_id,))
    result = cursor.fetchone()
    if result['total'] > 0:
        cursor.close()
        conn.close()
        flash('Cannot delete: this venue has events linked to it.', 'error')
        return redirect(url_for('admin_venues'))
    cursor.execute("DELETE FROM VENUES WHERE VenueID = %s", (venue_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Venue deleted successfully.', 'success')
    return redirect(url_for('admin_venues'))

@app.route('/admin/events/reduce-price/<int:event_id>', methods=['POST'])
@admin_required
def admin_reduce_price(event_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT BasePrice FROM EVENTS WHERE EventID = %s", (event_id,))
    event = cursor.fetchone()
    if not event:
        cursor.close()
        conn.close()
        flash('Event not found.', 'error')
        return redirect(url_for('admin_reports'))
    new_price = round(float(event['BasePrice']) * 0.75, 2)
    cursor.execute("UPDATE EVENTS SET BasePrice = %s WHERE EventID = %s", (new_price, event_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash(f'Price reduced by 25% to £{new_price}.', 'success')
    return redirect(url_for('admin_reports'))

if __name__ == '__main__':
    app.run(debug=True)
