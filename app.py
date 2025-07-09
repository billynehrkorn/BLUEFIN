# CHANGES MADE:
# 1. Fixed migration logic to handle missing columns gracefully
# 2. Added proper column existence checking before migration
# 3. Enhanced schema detection and migration process
# 4. Added fallback values for missing columns

from flask import Flask, render_template, send_from_directory, request, redirect, url_for, flash, session, jsonify
import os
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
import sqlite3
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Configure template and static folders
app.template_folder = 'templates'
app.static_folder = 'static'

# Create directories if they don't exist
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

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
        db.execute('''CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            firm TEXT,
            address TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')

        # Check if opportunities table exists and get its schema
        cursor = db.execute("PRAGMA table_info(opportunities)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}  # column_name: data_type

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
                     '200 West St, New York, NY'),
                    (1, 'Sarah Johnson', 'sarah.j@goldmansachs.com', '555-0102', 'Goldman Sachs',
                     '200 West St, New York, NY'),
                    (1, 'Michael Brown', 'mbrown@jpmorgan.com', '555-0103', 'JPMorgan Chase',
                     '383 Madison Ave, New York, NY'),
                    (1, 'Emily Davis', 'emily.davis@bofa.com', '555-0104', 'Bank of America',
                     '100 N Tryon St, Charlotte, NC'),
                    (1, 'Robert Wilson', 'rwilson@wellsfargo.com', '555-0105', 'Wells Fargo',
                     '420 Montgomery St, San Francisco, CA'),
                    (1, 'Jennifer Lee', 'jlee@citi.com', '555-0106', 'Citigroup', '388 Greenwich St, New York, NY'),
                    (1, 'David Martinez', 'dmartinez@db.com', '555-0107', 'Deutsche Bank', '60 Wall St, New York, NY'),
                    (1, 'Lisa Anderson', 'landerson@ubs.com', '555-0108', 'UBS',
                     '1285 Avenue of the Americas, New York, NY')
                ]

                for contact in sample_contacts:
                    db.execute('''INSERT INTO contacts 
                                 (user_id, name, email, phone, firm, address) 
                                 VALUES (?, ?, ?, ?, ?, ?)''', contact)

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


@app.route('/contacts')
@login_required
def contacts():
    db = get_db()
    contacts = db.execute('SELECT * FROM contacts WHERE user_id = ?', (current_user.id,)).fetchall()
    return render_template('card.html', contacts=contacts)


@app.route('/spreadsheet')
@login_required
def spreadsheet():
    db = get_db()
    contacts = db.execute('SELECT * FROM contacts WHERE user_id = ?', (current_user.id,)).fetchall()
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
    return render_template('contact_card.html')


@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    firm = request.form.get('firm')
    address = request.form.get('address')
    if not name:
        flash('Name is required', 'error')
        return redirect(url_for('contacts'))
    db = get_db()
    db.execute('INSERT INTO contacts (user_id, name, email, phone, firm, address) VALUES (?, ?, ?, ?, ?, ?)',
               (current_user.id, name, email, phone, firm, address))
    db.commit()
    flash('Contact added successfully!', 'success')
    return redirect(url_for('contacts'))


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
    contacts = db.execute('SELECT name FROM contacts WHERE user_id = ?', (current_user.id,)).fetchall()
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