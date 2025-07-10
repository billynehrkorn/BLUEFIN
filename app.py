# CHANGES MADE:
# 1. Added calendar_notes table for daily custom notes
# 2. Added calendar route with month navigation
# 3. Added CRUD endpoints for calendar notes
# 4. Added endpoint to delete opportunity reminders
# 5. Enhanced opportunity queries to support calendar display
# 6. Added date filtering and formatting utilities

from flask import Flask, render_template, send_from_directory, request, redirect, url_for, flash, session, jsonify
import os
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
import sqlite3
import json
from datetime import datetime, timedelta
import calendar
from werkzeug.utils import secure_filename
import uuid
from PIL import Image

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Configure template and static folders
app.template_folder = 'templates'
app.static_folder = 'static'

# Create directories if they don't exist
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)
os.makedirs('static/uploads', exist_ok=True)
os.makedirs('static/uploads/profile_pictures', exist_ok=True)

# File upload configuration
UPLOAD_FOLDER = 'static/uploads/profile_pictures'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_image(image_path, max_size=(300, 300)):
    """Resize image to maximum dimensions while maintaining aspect ratio"""
    try:
        with Image.open(image_path) as img:
            # Convert RGBA to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background

            # Resize image
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(image_path, 'JPEG', quality=85, optimize=True)
            return True
    except Exception as e:
        print(f"Error resizing image: {e}")
        return False


# --- Database Setup ---
DATABASE = 'bluefin.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL
        )''')

        # Check if contacts table exists and get its schema
        cursor = db.execute("PRAGMA table_info(contacts)")
        contact_columns = {row[1]: row[2] for row in cursor.fetchall()}

        if not contact_columns:
            # Create new contacts table with all required columns including created_at
            print("Creating new contacts table...")
            db.execute('''CREATE TABLE contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                firm TEXT,
                address TEXT,
                crd_number TEXT,
                title TEXT,
                profile_picture TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )''')
            print("New contacts table created successfully.")
        else:
            # Check if we need to add new columns
            if 'crd_number' not in contact_columns:
                print("Adding crd_number column to contacts table...")
                db.execute('ALTER TABLE contacts ADD COLUMN crd_number TEXT')
            if 'title' not in contact_columns:
                print("Adding title column to contacts table...")
                db.execute('ALTER TABLE contacts ADD COLUMN title TEXT')
            if 'profile_picture' not in contact_columns:
                print("Adding profile_picture column to contacts table...")
                db.execute('ALTER TABLE contacts ADD COLUMN profile_picture TEXT')
            if 'created_at' not in contact_columns:
                print("Adding created_at column to contacts table...")
                db.execute('ALTER TABLE contacts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                # Update existing records with current timestamp
                db.execute('UPDATE contacts SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL')
            if 'updated_at' not in contact_columns:
                print("Adding updated_at column to contacts table...")
                db.execute('ALTER TABLE contacts ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                # Update existing records with current timestamp
                db.execute('UPDATE contacts SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL')

        # Create contact_notes table
        db.execute('''CREATE TABLE IF NOT EXISTS contact_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')

        # Create calendar_notes table for daily custom notes
        db.execute('''CREATE TABLE IF NOT EXISTS calendar_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            note_date DATE NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')

        # Create registered_accounts table
        db.execute('''CREATE TABLE IF NOT EXISTS registered_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            account_number TEXT,
            client_name TEXT,
            strategy TEXT,
            inception_value REAL,
            fee_percent REAL,
            open_date DATE,
            status TEXT NOT NULL DEFAULT 'New',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')

        # Check if opportunities table exists and get its schema
        cursor = db.execute("PRAGMA table_info(opportunities)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        if not columns:
            # Create new opportunities table with correct schema
            print("Creating new opportunities table...")
            db.execute('''CREATE TABLE opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                contact TEXT NOT NULL,
                salesperson TEXT,
                amount REAL DEFAULT 0,
                probability INTEGER DEFAULT 50,
                stage TEXT NOT NULL DEFAULT 'prospecting',
                close_date DATE,
                notes TEXT,
                reminder DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )''')
            print("New opportunities table created successfully.")
        else:
            # Check if we need to migrate the schema
            needs_migration = False
            migration_reason = ""

            if 'contact' not in columns:
                needs_migration = True
                migration_reason = "Missing 'contact' column"
            elif 'salesperson' not in columns:
                needs_migration = True
                migration_reason = "Missing 'salesperson' column"
            elif 'probability' not in columns:
                needs_migration = True
                migration_reason = "Missing 'probability' column"

            if needs_migration:
                print(f"Migrating opportunities table: {migration_reason}")

                # Create new table with correct schema
                db.execute('''CREATE TABLE opportunities_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    salesperson TEXT,
                    amount REAL DEFAULT 0,
                    probability INTEGER DEFAULT 50,
                    stage TEXT NOT NULL DEFAULT 'prospecting',
                    close_date DATE,
                    notes TEXT,
                    reminder DATETIME,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )''')

                # Build dynamic migration query based on existing columns
                select_parts = []
                select_parts.append('o.id')
                select_parts.append('o.user_id')
                select_parts.append('o.title' if 'title' in columns else "'Untitled' as title")

                # Handle contact field - could be contact_id or contact
                if 'contact' in columns:
                    select_parts.append('o.contact')
                elif 'contact_id' in columns:
                    select_parts.append("COALESCE(c.name, 'Unknown Contact') as contact")
                else:
                    select_parts.append("'Unknown Contact' as contact")

                # Handle other optional fields
                select_parts.append('o.salesperson' if 'salesperson' in columns else 'NULL as salesperson')
                select_parts.append('o.amount' if 'amount' in columns else '0 as amount')
                select_parts.append('o.probability' if 'probability' in columns else '50 as probability')
                select_parts.append('o.stage' if 'stage' in columns else "'prospecting' as stage")
                select_parts.append('o.close_date' if 'close_date' in columns else 'NULL as close_date')
                select_parts.append('o.notes' if 'notes' in columns else 'NULL as notes')
                select_parts.append('o.reminder' if 'reminder' in columns else 'NULL as reminder')
                select_parts.append('o.created_at' if 'created_at' in columns else 'CURRENT_TIMESTAMP as created_at')
                select_parts.append('o.updated_at' if 'updated_at' in columns else 'CURRENT_TIMESTAMP as updated_at')

                # Build the migration query
                select_clause = ', '.join(select_parts)

                if 'contact_id' in columns and 'contact' not in columns:
                    # Need to join with contacts table
                    migration_query = f'''INSERT INTO opportunities_new
                                          (id, user_id, title, contact, salesperson, amount, probability, stage, close_date, notes, reminder, created_at, updated_at)
                                         SELECT {select_clause}
                                         FROM opportunities o
                                         LEFT JOIN contacts c ON o.contact_id = c.id'''
                else:
                    # Simple migration without joins
                    migration_query = f'''INSERT INTO opportunities_new
                                          (id, user_id, title, contact, salesperson, amount, probability, stage, close_date, notes, reminder, created_at, updated_at)
                                         SELECT {select_clause}
                                         FROM opportunities o'''

                try:
                    db.execute(migration_query)
                    # Drop old table and rename new one
                    db.execute('DROP TABLE opportunities')
                    db.execute('ALTER TABLE opportunities_new RENAME TO opportunities')
                    print("Schema migration completed successfully.")
                except Exception as e:
                    print(f"Migration error: {e}")
                    # Clean up failed migration
                    db.execute('DROP TABLE IF EXISTS opportunities_new')
                    raise e


init_db()


# Add this after init_db()
def init_notes_table():
    with get_db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )''')


def seed_sample_data():
    """Add sample data for analytics if tables are empty"""
    with get_db() as db:
        # Check if we already have data
        opp_count = db.execute('SELECT COUNT(*) as count FROM opportunities').fetchone()['count']
        if opp_count == 0:
            print("Seeding sample opportunities data...")
            # Add sample opportunities with contact names (not IDs)
            sample_opportunities = [
                (1, 'Morgan Stanley Portfolio Review', 'John Smith', 'Alex Rodriguez', 75000, 80, 'negotiation',
                 '2024-02-15', 'Follow up on portfolio diversification strategy. Client interested in ESG investments.',
                 '2024-01-20 10:00:00'),
                (1, 'Goldman Sachs Retirement Planning', 'Sarah Johnson', 'Maria Garcia', 120000, 60, 'proposal',
                 '2024-02-28', 'Comprehensive retirement planning for executive. Needs tax optimization strategies.',
                 '2024-01-25 14:00:00'),
                (1, 'JPMorgan Investment Advisory', 'Michael Brown', 'David Chen', 45000, 100, 'closed-won',
                 '2024-01-15', 'Successfully closed investment advisory agreement. Client very satisfied.', None),
                (1, 'Bank of America Wealth Management', 'Emily Davis', 'Jennifer Kim', 85000, 25, 'qualifying',
                 '2024-03-10', 'Initial consultation completed. Need to assess risk tolerance and investment goals.',
                 '2024-01-30 09:00:00'),
                (1, 'Wells Fargo Estate Planning', 'Robert Wilson', 'Alex Rodriguez', 95000, 70, 'proposal',
                 '2024-02-20', 'Complex estate planning case. Multiple beneficiaries and trust structures involved.',
                 '2024-01-28 11:00:00'),
                (1, 'Citigroup Corporate Benefits', 'Jennifer Lee', 'Maria Garcia', 65000, 40, 'prospecting',
                 '2024-03-15', 'Corporate benefits consultation. Need to prepare comprehensive proposal.',
                 '2024-02-01 15:00:00'),
                (1, 'Deutsche Bank Private Wealth', 'David Martinez', 'David Chen', 150000, 0, 'closed-lost',
                 '2024-01-30', 'Lost to competitor due to pricing concerns.', None),
                (1, 'UBS Investment Management', 'Lisa Anderson', 'Jennifer Kim', 200000, 85, 'negotiation',
                 '2024-02-25', 'Large investment management deal in final stages.', '2024-02-05 16:00:00')
            ]

            for opp in sample_opportunities:
                db.execute('''INSERT INTO opportunities
                              (user_id, title, contact, salesperson, amount, probability, stage, close_date, notes, reminder)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', opp)

            # Add sample contacts with firms if contacts table is empty
            contact_count = db.execute('SELECT COUNT(*) as count FROM contacts').fetchone()['count']
            if contact_count == 0:
                print("Seeding sample contacts data...")
                sample_contacts = [
                    (1, 'John Smith', 'john.smith@morganstanley.com', '555-0101', 'Morgan Stanley',
                     '200 West St, New York, NY', '12345678', 'Senior Financial Advisor'),
                    (1, 'Sarah Johnson', 'sarah.j@goldmansachs.com', '555-0102', 'Goldman Sachs',
                     '200 West St, New York, NY', '23456789', 'Vice President'),
                    (1, 'Michael Brown', 'mbrown@jpmorgan.com', '555-0103', 'JPMorgan Chase',
                     '383 Madison Ave, New York, NY', '34567890', 'Managing Director'),
                    (1, 'Emily Davis', 'emily.davis@bofa.com', '555-0104', 'Bank of America',
                     '100 N Tryon St, Charlotte, NC', '45678901', 'Financial Advisor'),
                    (1, 'Robert Wilson', 'rwilson@wellsfargo.com', '555-0105', 'Wells Fargo',
                     '420 Montgomery St, San Francisco, CA', '56789012', 'Senior Advisor'),
                    (1, 'Jennifer Lee', 'jlee@citi.com', '555-0106', 'Citigroup', '388 Greenwich St, New York, NY',
                     '67890123', 'Investment Advisor'),
                    (1, 'David Martinez', 'dmartinez@db.com', '555-0107', 'Deutsche Bank', '60 Wall St, New York, NY',
                     '78901234', 'Private Wealth Manager'),
                    (1, 'Lisa Anderson', 'landerson@ubs.com', '555-0108', 'UBS',
                     '1285 Avenue of the Americas, New York, NY', '89012345', 'Senior Portfolio Manager')
                ]

                for contact in sample_contacts:
                    db.execute('''INSERT INTO contacts
                                  (user_id, name, email, phone, firm, address, crd_number, title)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', contact)

            db.commit()
            print("Sample data seeding completed.")


init_notes_table()
seed_sample_data()

# --- Flask-Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin):
    def __init__(self, id, email, name, password):
        self.id = id
        self.email = email
        self.name = name
        self.password = password

    @staticmethod
    def get(user_id):
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if user:
            return User(user['id'], user['email'], user['name'], user['password'])
        return None

    @staticmethod
    def get_by_email(email):
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user:
            return User(user['id'], user['email'], user['name'], user['password'])
        return None


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


# Sample user data (in production, use a proper database)
users = {
    'demo@bluefin.com': {
        'password': 'demo123',
        'name': 'Demo User'
    }
}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.get_by_email(email)
        if user and user.password == password:
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('contacts'))
        else:
            flash('Invalid email or password', 'error')

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if User.get_by_email(email):
            flash('Email already exists', 'error')
        elif password != confirm_password:
            flash('Passwords do not match', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
        else:
            db = get_db()
            db.execute('INSERT INTO users (email, password, name) VALUES (?, ?, ?)', (email, password, name))
            db.commit()

            user = User.get_by_email(email)
            login_user(user)
            flash('Account created successfully!', 'success')
            return redirect(url_for('contacts'))

    return render_template('signup.html')


@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))


@app.route('/calendar')
@login_required
def calendar_view():
    # Get year and month from query parameters, default to current
    now = datetime.now()
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))

    # Ensure valid month/year
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    # Create calendar data
    cal = calendar.Calendar(firstweekday=6)  # Start with Sunday
    month_days = cal.monthdayscalendar(year, month)

    # Get month name
    month_name = calendar.month_name[month]

    # Calculate previous and next month/year
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    # Get calendar notes for this month
    db = get_db()
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    calendar_notes = db.execute('''
        SELECT * FROM calendar_notes 
        WHERE user_id = ? AND note_date >= ? AND note_date < ?
        ORDER BY note_date, created_at
    ''', (current_user.id, start_date, end_date)).fetchall()

    # Get opportunity reminders for this month
    opportunity_reminders = db.execute('''
        SELECT id, title, reminder 
        FROM opportunities 
        WHERE user_id = ? AND reminder IS NOT NULL 
        AND DATE(reminder) >= ? AND DATE(reminder) < ?
        ORDER BY reminder
    ''', (current_user.id, start_date, end_date)).fetchall()

    # Organize notes and reminders by date
    notes_by_date = {}
    for note in calendar_notes:
        date_key = note['note_date']
        if date_key not in notes_by_date:
            notes_by_date[date_key] = []
        notes_by_date[date_key].append(note)

    reminders_by_date = {}
    for reminder in opportunity_reminders:
        date_key = reminder['reminder'][:10]  # Extract date part
        if date_key not in reminders_by_date:
            reminders_by_date[date_key] = []
        reminders_by_date[date_key].append(reminder)

    return render_template('calendar.html',
                           year=year,
                           month=month,
                           month_name=month_name,
                           month_days=month_days,
                           prev_month=prev_month,
                           prev_year=prev_year,
                           next_month=next_month,
                           next_year=next_year,
                           notes_by_date=notes_by_date,
                           reminders_by_date=reminders_by_date,
                           today=now.date())


@app.route('/contacts')
@login_required
def contacts():
    db = get_db()

    # Get filter parameters from query string
    firm_filter = request.args.get('firm', '').strip()
    accounts_filter = request.args.get('accounts', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    # Base query with LEFT JOIN to count registered accounts
    base_query = '''
        SELECT c.*, 
               COUNT(ra.id) as account_count
        FROM contacts c
        LEFT JOIN registered_accounts ra ON c.id = ra.contact_id AND ra.user_id = c.user_id
        WHERE c.user_id = ?
    '''

    query_params = [current_user.id]

    # Add firm filter
    if firm_filter:
        base_query += ' AND c.firm = ?'
        query_params.append(firm_filter)

    # Add date range filters
    if start_date:
        base_query += ' AND DATE(c.created_at) >= ?'
        query_params.append(start_date)

    if end_date:
        base_query += ' AND DATE(c.created_at) <= ?'
        query_params.append(end_date)

    # Group by contact to get proper count
    base_query += ' GROUP BY c.id'

    # Add account count filter (applied after grouping)
    if accounts_filter:
        if accounts_filter == '0':
            base_query += ' HAVING account_count = 0'
        elif accounts_filter == '1-5':
            base_query += ' HAVING account_count BETWEEN 1 AND 5'
        elif accounts_filter == '6-10':
            base_query += ' HAVING account_count BETWEEN 6 AND 10'
        elif accounts_filter == '10+':
            base_query += ' HAVING account_count > 10'

    # Add final ordering
    base_query += ' ORDER BY c.name'

    # Execute the main query
    contacts = db.execute(base_query, query_params).fetchall()

    # Get distinct firms for the dropdown (only firms that have contacts)
    firms_query = '''
        SELECT DISTINCT firm 
        FROM contacts 
        WHERE user_id = ? AND firm IS NOT NULL AND firm != '' 
        ORDER BY firm
    '''
    firms_result = db.execute(firms_query, (current_user.id,)).fetchall()
    firms = [row['firm'] for row in firms_result]

    # Convert contacts to list of dicts to make them easier to work with in template
    contacts_list = []
    for contact in contacts:
        contact_dict = dict(contact)
        contacts_list.append(contact_dict)

    return render_template('card.html',
                           contacts=contacts_list,
                           firms=firms,
                           request=request)  # Pass request object for template access to args


@app.route('/spreadsheet')
@login_required
def spreadsheet():
    db = get_db()
    contacts = db.execute('SELECT * FROM contacts WHERE user_id = ? ORDER BY name', (current_user.id,)).fetchall()
    return render_template('spreadsheet.html', contacts=contacts)


@app.route('/analytics&reports')
@login_required
def analytics_reports():
    db = get_db()

    # Get optional date filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Base query for opportunities by stage
    opp_stage_query = '''
        SELECT stage, COUNT(*) AS count 
        FROM opportunities 
        WHERE user_id = ?
    '''
    opp_stage_params = [current_user.id]

    # Add date filtering if provided
    if start_date and end_date:
        opp_stage_query += ' AND close_date BETWEEN ? AND ?'
        opp_stage_params.extend([start_date, end_date])
    elif start_date:
        opp_stage_query += ' AND close_date >= ?'
        opp_stage_params.append(start_date)
    elif end_date:
        opp_stage_query += ' AND close_date <= ?'
        opp_stage_params.append(end_date)

    opp_stage_query += ' GROUP BY stage'

    # Execute queries
    opp_by_stage = db.execute(opp_stage_query, opp_stage_params).fetchall()

    # Contacts by firm query
    contacts_by_firm = db.execute('''
        SELECT firm, COUNT(*) AS count 
        FROM contacts 
        WHERE user_id = ? AND firm IS NOT NULL AND firm != ''
        GROUP BY firm
    ''', (current_user.id,)).fetchall()

    # Get total counts
    total_opportunities_query = '''
        SELECT COUNT(*) AS count 
        FROM opportunities 
        WHERE user_id = ?
    '''
    total_opp_params = [current_user.id]

    if start_date and end_date:
        total_opportunities_query += ' AND close_date BETWEEN ? AND ?'
        total_opp_params.extend([start_date, end_date])
    elif start_date:
        total_opportunities_query += ' AND close_date >= ?'
        total_opp_params.append(start_date)
    elif end_date:
        total_opportunities_query += ' AND close_date <= ?'
        total_opp_params.append(end_date)

    total_opportunities = db.execute(total_opportunities_query, total_opp_params).fetchone()['count']
    total_contacts = \
        db.execute('SELECT COUNT(*) AS count FROM contacts WHERE user_id = ?', (current_user.id,)).fetchone()['count']

    # Convert to list of dictionaries for JSON serialization
    opp_by_stage_data = [{'stage': row['stage'], 'count': row['count']} for row in opp_by_stage]
    contacts_by_firm_data = [{'firm': row['firm'], 'count': row['count']} for row in contacts_by_firm]

    return render_template('analytics&reports.html',
                           opp_by_stage=opp_by_stage_data,
                           contacts_by_firm=contacts_by_firm_data,
                           total_opportunities=total_opportunities,
                           total_contacts=total_contacts,
                           start_date=start_date,
                           end_date=end_date)


@app.route('/upload')
def upload():
    return render_template('upload.html')


@app.route('/contact_card')
def contact_card():
    contact_id = request.args.get('id')
    if not contact_id:
        flash('Contact ID is required', 'error')
        return redirect(url_for('contacts'))

    db = get_db()
    contact = db.execute('''
        SELECT * FROM contacts 
        WHERE id = ? AND user_id = ?
    ''', (contact_id, current_user.id)).fetchone()

    if not contact:
        flash('Contact not found', 'error')
        return redirect(url_for('contacts'))

    # Get contact notes
    notes = db.execute('''
        SELECT * FROM contact_notes 
        WHERE contact_id = ? AND user_id = ? 
        ORDER BY created_at DESC
    ''', (contact_id, current_user.id)).fetchall()

    # Get registered accounts
    accounts = db.execute('''
        SELECT * FROM registered_accounts 
        WHERE contact_id = ? AND user_id = ? 
        ORDER BY created_at DESC
    ''', (contact_id, current_user.id)).fetchall()

    return render_template('contact_card.html', contact=contact, notes=notes, accounts=accounts)


# --- Calendar Notes CRUD ---
@app.route('/api/calendar_notes', methods=['POST'])
@login_required
def add_calendar_note():
    """Add a calendar note for a specific date"""
    try:
        data = request.get_json()
        note_date = data.get('date')
        content = data.get('content', '').strip()

        if not note_date or not content:
            return jsonify({'error': 'Date and content are required'}), 400

        db = get_db()
        cursor = db.execute('''
            INSERT INTO calendar_notes (user_id, note_date, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (current_user.id, note_date, content,
              datetime.now().isoformat(), datetime.now().isoformat()))

        note_id = cursor.lastrowid
        db.commit()

        # Return the created note
        note = db.execute('SELECT * FROM calendar_notes WHERE id = ?', (note_id,)).fetchone()
        return jsonify(dict(note)), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/calendar_notes/<int:note_id>', methods=['DELETE'])
@login_required
def delete_calendar_note(note_id):
    """Delete a calendar note"""
    try:
        db = get_db()

        # Check if note exists and belongs to user
        existing = db.execute('''
            SELECT * FROM calendar_notes 
            WHERE id = ? AND user_id = ?
        ''', (note_id, current_user.id)).fetchone()

        if not existing:
            return jsonify({'error': 'Note not found'}), 404

        # Delete the note
        db.execute('DELETE FROM calendar_notes WHERE id = ? AND user_id = ?',
                   (note_id, current_user.id))
        db.commit()

        return jsonify({'message': 'Note deleted successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opportunities/<int:opportunity_id>/reminder', methods=['DELETE'])
@login_required
def delete_opportunity_reminder(opportunity_id):
    """Delete/clear an opportunity reminder"""
    try:
        db = get_db()

        # Check if opportunity exists and belongs to user
        existing = db.execute('''
            SELECT * FROM opportunities 
            WHERE id = ? AND user_id = ?
        ''', (opportunity_id, current_user.id)).fetchone()

        if not existing:
            return jsonify({'error': 'Opportunity not found'}), 404

        # Clear the reminder
        db.execute('''
            UPDATE opportunities 
            SET reminder = NULL, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (datetime.now().isoformat(), opportunity_id, current_user.id))
        db.commit()

        return jsonify({'message': 'Reminder deleted successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/upload_profile_picture', methods=['POST'])
@login_required
def upload_profile_picture():
    """Upload and save profile picture for a contact"""
    try:
        contact_id = request.form.get('contact_id')
        if not contact_id:
            flash('Contact ID is required', 'error')
            return redirect(url_for('contacts'))

        # Check if contact exists and belongs to user
        db = get_db()
        contact = db.execute('''
            SELECT * FROM contacts 
            WHERE id = ? AND user_id = ?
        ''', (contact_id, current_user.id)).fetchone()

        if not contact:
            flash('Contact not found', 'error')
            return redirect(url_for('contacts'))

        # Check if file was uploaded
        if 'profile_picture' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('contact_card', id=contact_id))

        file = request.files['profile_picture']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('contact_card', id=contact_id))

        if file and allowed_file(file.filename):
            # Generate unique filename
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

            # Save file
            file.save(file_path)

            # Resize image
            if resize_image(file_path):
                # Delete old profile picture if it exists
                if contact['profile_picture']:
                    old_file_path = os.path.join('static', contact['profile_picture'].lstrip('/'))
                    if os.path.exists(old_file_path):
                        try:
                            os.remove(old_file_path)
                        except OSError:
                            pass  # File might be in use or already deleted

                # Update database with new profile picture path
                profile_picture_url = f"/static/uploads/profile_pictures/{unique_filename}"
                db.execute('''
                    UPDATE contacts 
                    SET profile_picture = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                ''', (profile_picture_url, datetime.now().isoformat(), contact_id, current_user.id))
                db.commit()

                flash('Profile picture updated successfully!', 'success')
            else:
                # Remove file if resize failed
                if os.path.exists(file_path):
                    os.remove(file_path)
                flash('Error processing image. Please try a different file.', 'error')
        else:
            flash('Invalid file type. Please upload a PNG, JPG, JPEG, GIF, or WebP image.', 'error')

        return redirect(url_for('contact_card', id=contact_id))

    except Exception as e:
        flash(f'Error uploading profile picture: {str(e)}', 'error')
        return redirect(url_for('contacts'))


@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    firm = request.form.get('firm')
    address = request.form.get('address')
    crd_number = request.form.get('crd_number')
    title = request.form.get('title')

    if not name:
        flash('Name is required', 'error')
        return redirect(url_for('contacts'))

    db = get_db()
    # Explicitly set created_at and updated_at to current timestamp
    current_time = datetime.now().isoformat()
    db.execute('''INSERT INTO contacts
                  (user_id, name, email, phone, firm, address, crd_number, title, created_at, updated_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
               (current_user.id, name, email, phone, firm, address, crd_number, title,
                current_time, current_time))
    db.commit()

    flash('Contact added successfully!', 'success')
    return redirect(url_for('contacts'))


@app.route('/update_contact', methods=['POST'])
@login_required
def update_contact():
    """Update contact information"""
    try:
        contact_id = request.form.get('contact_id')
        if not contact_id:
            return jsonify({'error': 'Contact ID is required'}), 400

        db = get_db()
        # Check if contact exists and belongs to user
        existing = db.execute('''
            SELECT * FROM contacts 
            WHERE id = ? AND user_id = ?
        ''', (contact_id, current_user.id)).fetchone()

        if not existing:
            return jsonify({'error': 'Contact not found'}), 404

        # Update contact
        db.execute('''
            UPDATE contacts 
            SET name = ?, title = ?, email = ?, phone = ?, firm = ?, address = ?, crd_number = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (
            request.form.get('name', existing['name']),
            request.form.get('title', existing['title']),
            request.form.get('email', existing['email']),
            request.form.get('phone', existing['phone']),
            request.form.get('firm', existing['firm']),
            request.form.get('address', existing['address']),
            request.form.get('crd_number', existing['crd_number']),
            datetime.now().isoformat(),
            contact_id,
            current_user.id
        ))
        db.commit()

        flash('Contact updated successfully!', 'success')
        return redirect(url_for('contact_card', id=contact_id))

    except Exception as e:
        flash(f'Error updating contact: {str(e)}', 'error')
        return redirect(url_for('contacts'))


@app.route('/add_contact_note', methods=['POST'])
@login_required
def add_contact_note():
    """Add a note to a contact"""
    try:
        contact_id = request.form.get('contact_id')
        content = request.form.get('content')

        if not contact_id or not content:
            flash('Contact ID and note content are required', 'error')
            return redirect(url_for('contacts'))

        db = get_db()
        # Verify contact exists and belongs to user
        contact = db.execute('''
            SELECT * FROM contacts 
            WHERE id = ? AND user_id = ?
        ''', (contact_id, current_user.id)).fetchone()

        if not contact:
            flash('Contact not found', 'error')
            return redirect(url_for('contacts'))

        # Add note
        db.execute('''
            INSERT INTO contact_notes (contact_id, user_id, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (contact_id, current_user.id, content, datetime.now().isoformat(), datetime.now().isoformat()))
        db.commit()

        flash('Note added successfully!', 'success')
        return redirect(url_for('contact_card', id=contact_id))

    except Exception as e:
        flash(f'Error adding note: {str(e)}', 'error')
        return redirect(url_for('contacts'))


@app.route('/add_registered_account', methods=['POST'])
@login_required
def add_registered_account():
    """Add a registered account to a contact"""
    try:
        contact_id = request.form.get('contact_id')
        if not contact_id:
            flash('Contact ID is required', 'error')
            return redirect(url_for('contacts'))

        db = get_db()
        # Verify contact exists and belongs to user
        contact = db.execute('''
            SELECT * FROM contacts 
            WHERE id = ? AND user_id = ?
        ''', (contact_id, current_user.id)).fetchone()

        if not contact:
            flash('Contact not found', 'error')
            return redirect(url_for('contacts'))

        # Get form data
        account_number = request.form.get('account_number')
        client_name = request.form.get('client_name')
        strategy = request.form.get('strategy')
        inception_value = request.form.get('inception_value')
        fee_percent = request.form.get('fee_percent')
        open_date = request.form.get('open_date')
        status = request.form.get('status', 'New')

        # Convert numeric fields
        inception_value = float(inception_value) if inception_value else None
        fee_percent = float(fee_percent) if fee_percent else None

        # Add account
        db.execute('''
            INSERT INTO registered_accounts 
            (contact_id, user_id, account_number, client_name, strategy, inception_value, 
             fee_percent, open_date, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (contact_id, current_user.id, account_number, client_name, strategy,
              inception_value, fee_percent, open_date, status,
              datetime.now().isoformat(), datetime.now().isoformat()))
        db.commit()

        flash('Registered account added successfully!', 'success')
        return redirect(url_for('contact_card', id=contact_id))

    except Exception as e:
        flash(f'Error adding account: {str(e)}', 'error')
        return redirect(url_for('contacts'))


@app.route('/get_registered_account/<int:account_id>', methods=['GET'])
@login_required
def get_registered_account(account_id):
    """Get account data for editing"""
    try:
        db = get_db()
        # Get account and verify ownership
        account = db.execute('''
            SELECT ra.*, c.user_id as contact_user_id 
            FROM registered_accounts ra
            JOIN contacts c ON ra.contact_id = c.id
            WHERE ra.id = ? AND ra.user_id = ? AND c.user_id = ?
        ''', (account_id, current_user.id, current_user.id)).fetchone()

        if not account:
            return jsonify({'error': 'Account not found'}), 404

        return jsonify(dict(account))

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/update_registered_account/<int:account_id>', methods=['POST'])
@login_required
def update_registered_account(account_id):
    """Update a registered account"""
    try:
        db = get_db()
        # Get account and verify ownership
        existing = db.execute('''
            SELECT ra.*, c.user_id as contact_user_id 
            FROM registered_accounts ra
            JOIN contacts c ON ra.contact_id = c.id
            WHERE ra.id = ? AND ra.user_id = ? AND c.user_id = ?
        ''', (account_id, current_user.id, current_user.id)).fetchone()

        if not existing:
            flash('Account not found', 'error')
            return redirect(url_for('contacts'))

        contact_id = existing['contact_id']

        # Get form data
        account_number = request.form.get('account_number')
        client_name = request.form.get('client_name')
        strategy = request.form.get('strategy')
        inception_value = request.form.get('inception_value')
        fee_percent = request.form.get('fee_percent')
        open_date = request.form.get('open_date')
        status = request.form.get('status', existing['status'])

        # Convert numeric fields
        inception_value = float(inception_value) if inception_value else None
        fee_percent = float(fee_percent) if fee_percent else None

        # Update account
        db.execute('''
            UPDATE registered_accounts 
            SET account_number = ?, client_name = ?, strategy = ?, inception_value = ?, 
                fee_percent = ?, open_date = ?, status = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (account_number, client_name, strategy, inception_value, fee_percent,
              open_date, status, datetime.now().isoformat(), account_id, current_user.id))
        db.commit()

        flash('Account updated successfully!', 'success')
        return redirect(url_for('contact_card', id=contact_id))

    except Exception as e:
        flash(f'Error updating account: {str(e)}', 'error')
        return redirect(url_for('contacts'))


@app.route('/delete_contact_note/<int:note_id>', methods=['POST'])
@login_required
def delete_contact_note(note_id):
    """Delete a contact note"""
    try:
        db = get_db()
        # Get note and verify ownership
        note = db.execute('''
            SELECT cn.*, c.user_id as contact_user_id 
            FROM contact_notes cn
            JOIN contacts c ON cn.contact_id = c.id
            WHERE cn.id = ? AND cn.user_id = ? AND c.user_id = ?
        ''', (note_id, current_user.id, current_user.id)).fetchone()

        if not note:
            return jsonify({'error': 'Note not found'}), 404

        contact_id = note['contact_id']

        # Delete note
        db.execute('DELETE FROM contact_notes WHERE id = ? AND user_id = ?',
                   (note_id, current_user.id))
        db.commit()

        return jsonify({'message': 'Note deleted successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/delete_registered_account/<int:account_id>', methods=['POST'])
@login_required
def delete_registered_account(account_id):
    """Delete a registered account"""
    try:
        db = get_db()
        # Get account and verify ownership
        account = db.execute('''
            SELECT ra.*, c.user_id as contact_user_id 
            FROM registered_accounts ra
            JOIN contacts c ON ra.contact_id = c.id
            WHERE ra.id = ? AND ra.user_id = ? AND c.user_id = ?
        ''', (account_id, current_user.id, current_user.id)).fetchone()

        if not account:
            return jsonify({'error': 'Account not found'}), 404

        # Delete account
        db.execute('DELETE FROM registered_accounts WHERE id = ? AND user_id = ?',
                   (account_id, current_user.id))
        db.commit()

        return jsonify({'message': 'Account deleted successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/seminars')
@login_required
def seminars():
    return render_template('seminars.html')


@app.route('/opportunities', methods=['GET', 'POST'])
@login_required
def opportunities():
    db = get_db()

    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            from datetime import datetime
            db.execute('INSERT INTO notes (user, content, timestamp) VALUES (?, ?, ?)',
                       (current_user.name, content, datetime.now().strftime('%Y-%m-%d %H:%M')))
            db.commit()
        return redirect(url_for('opportunities'))

    # Get opportunities from database
    opportunities = db.execute('''
        SELECT * FROM opportunities 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (current_user.id,)).fetchall()

    # Get contacts for dropdown
    contacts = db.execute('SELECT name FROM contacts WHERE user_id = ? ORDER BY name', (current_user.id,)).fetchall()
    contact_names = [contact['name'] for contact in contacts]

    notes = db.execute('SELECT * FROM notes ORDER BY id DESC').fetchall()

    return render_template('opportunities.html',
                           opportunities=opportunities,
                           contacts=contact_names,
                           notes=notes)


# --- API Endpoints for Opportunities CRUD ---
@app.route('/api/opportunities', methods=['GET'])
@login_required
def api_get_opportunities():
    """Get all opportunities for the current user"""
    db = get_db()
    opportunities = db.execute('''
        SELECT * FROM opportunities 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (current_user.id,)).fetchall()

    return jsonify([dict(opp) for opp in opportunities])


@app.route('/api/opportunities', methods=['POST'])
@login_required
def api_create_opportunity():
    """Create a new opportunity"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('title') or not data.get('contact'):
            return jsonify({'error': 'Title and contact are required'}), 400

        db = get_db()
        cursor = db.execute('''
            INSERT INTO opportunities 
            (user_id, title, contact, salesperson, amount, probability, stage, close_date, notes, reminder, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            current_user.id,
            data.get('title'),
            data.get('contact'),
            data.get('salesperson'),
            float(data.get('amount', 0)),
            int(data.get('probability', 50)),
            data.get('stage', 'prospecting'),
            data.get('close_date'),
            data.get('notes'),
            data.get('reminder'),
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))

        opportunity_id = cursor.lastrowid
        db.commit()

        # Return the created opportunity
        opportunity = db.execute('SELECT * FROM opportunities WHERE id = ?', (opportunity_id,)).fetchone()
        return jsonify(dict(opportunity)), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opportunities/<int:opportunity_id>', methods=['PUT'])
@login_required
def api_update_opportunity(opportunity_id):
    """Update an existing opportunity"""
    try:
        data = request.get_json()
        db = get_db()

        # Check if opportunity exists and belongs to user
        existing = db.execute('''
            SELECT * FROM opportunities 
            WHERE id = ? AND user_id = ?
        ''', (opportunity_id, current_user.id)).fetchone()

        if not existing:
            return jsonify({'error': 'Opportunity not found'}), 404

        # Update the opportunity
        db.execute('''
            UPDATE opportunities 
            SET title = ?, contact = ?, salesperson = ?, amount = ?, probability = ?, 
                stage = ?, close_date = ?, notes = ?, reminder = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (
            data.get('title', existing['title']),
            data.get('contact', existing['contact']),
            data.get('salesperson', existing['salesperson']),
            float(data.get('amount', existing['amount'])),
            int(data.get('probability', existing['probability'])),
            data.get('stage', existing['stage']),
            data.get('close_date', existing['close_date']),
            data.get('notes', existing['notes']),
            data.get('reminder', existing['reminder']),
            datetime.now().isoformat(),
            opportunity_id,
            current_user.id
        ))
        db.commit()

        # Return the updated opportunity
        opportunity = db.execute('SELECT * FROM opportunities WHERE id = ?', (opportunity_id,)).fetchone()
        return jsonify(dict(opportunity))

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opportunities/<int:opportunity_id>', methods=['DELETE'])
@login_required
def api_delete_opportunity(opportunity_id):
    """Delete an opportunity"""
    try:
        db = get_db()

        # Check if opportunity exists and belongs to user
        existing = db.execute('''
            SELECT * FROM opportunities 
            WHERE id = ? AND user_id = ?
        ''', (opportunity_id, current_user.id)).fetchone()

        if not existing:
            return jsonify({'error': 'Opportunity not found'}), 404

        # Delete the opportunity
        db.execute('DELETE FROM opportunities WHERE id = ? AND user_id = ?',
                   (opportunity_id, current_user.id))
        db.commit()

        return jsonify({'message': 'Opportunity deleted successfully'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/opportunities/<int:opportunity_id>/stage', methods=['PUT'])
@login_required
def api_update_opportunity_stage(opportunity_id):
    """Update only the stage of an opportunity (for drag and drop)"""
    try:
        data = request.get_json()
        new_stage = data.get('stage')

        if not new_stage:
            return jsonify({'error': 'Stage is required'}), 400

        db = get_db()

        # Check if opportunity exists and belongs to user
        existing = db.execute('''
            SELECT * FROM opportunities 
            WHERE id = ? AND user_id = ?
        ''', (opportunity_id, current_user.id)).fetchone()

        if not existing:
            return jsonify({'error': 'Opportunity not found'}), 404

        # Update only the stage
        db.execute('''
            UPDATE opportunities 
            SET stage = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        ''', (new_stage, datetime.now().isoformat(), opportunity_id, current_user.id))
        db.commit()

        return jsonify({'message': 'Stage updated successfully', 'stage': new_stage})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Serve static files
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


if __name__ == '__main__':
    print("Starting Bluefin CRM...")
    print("Open your browser and go to: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)