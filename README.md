# Bristol Community Events (BCE)

A web-based community events booking system developed with **Python, Flask and MySQL** as a university project for the Web Development and Databases module.

## Features

### User features
- User registration, login, logout and password changes
- Browse and filter events by category, venue, free events, month and date range
- Event detail pages with availability and discount previews
- Standard and multi-day event bookings
- Advance-booking and student discounts
- Booking receipts and booking history
- Booking cancellation with cancellation-fee calculations
- Waiting list for fully booked events
- Contact form for submitting messages

### Admin features
- Admin dashboard with booking and event statistics
- Create, edit and delete events
- Upload event images
- View bookings and manage user details
- Manage venues
- View reports, including revenue and ticket availability
- Read, reply to and delete contact messages

## Tech stack

- Python
- Flask
- MySQL
- HTML, CSS and Jinja2
- `mysql-connector-python`

## Project structure

```text
.
├── app.py
├── db.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── static/
│   ├── css/
│   └── images/
└── templates/
```

## Setup

1. Install Python 3.10+ and MySQL Server 8+.
2. Create a MySQL database named `bce_db`.
3. **Import the database schema and sample data.** The SQL dump referenced in the original project notes (`The_most_final.sql`) was not included in the uploaded archive. Add your own exported SQL file before treating this repository as independently runnable.
4. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

5. Activate it and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

6. Copy `.env.example` to `.env` and enter your own local configuration:

   ```text
   SECRET_KEY=your-long-random-secret
   DB_HOST=localhost
   DB_USER=your_mysql_username
   DB_PASSWORD=your_mysql_password
   DB_NAME=bce_db
   ```

7. Run the application:

   ```bash
   python app.py
   ```

8. Open `http://127.0.0.1:5000` in your browser.

**Do not commit `.env` or real database credentials to GitHub.** The `.env.example` file contains placeholders only.

## Security notes

- Passwords are hashed using Werkzeug.
- SQL statements use parameterised queries in the application code.
- Login and admin routes use access-control decorators.
- Uploaded images are restricted by file extension and size.
- CSRF protection is not implemented yet; add CSRF tokens before any production deployment.
- Waiting-list notifications currently update a database flag; they do not send email.

## Notes

This repository contains the application source, templates, CSS and image assets from the supplied project archive. The database SQL export was not present in that archive, so the database setup step is not yet reproducible from this repository alone.
