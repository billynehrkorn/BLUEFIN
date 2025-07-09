# Bluefin CRM

A simple Customer Relationship Management (CRM) system built with Flask.

## Features

- User authentication (login/signup) with Flask-Login
- Each user has their own contacts (per-user contact management)
- Data is stored in a SQLite database (bluefin.db)
- CSV import/export functionality
- Contact details with notes
- Responsive design

## Installation

1. Install Python 3.7 or higher
2. Install dependencies:
   \`\`\`
   pip install -r requirements.txt
   \`\`\`

3. Run the application:
   \`\`\`
   python app.py
   \`\`\`

4. Open your browser and go to: http://localhost:5000

## Demo Account

- Email: demo@bluefin.com
- Password: demo123

## File Structure

\`\`\`
bluefin-crm/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates
│   ├── index.html     # Home page
│   ├── login.html     # Login page
│   ├── signup.html    # Registration page
│   └── card.html      # Contacts page
└── static/            # Static files (CSS, JS, images)
\`\`\`

## Usage

1. Start the application with `python app.py`
2. Visit the home page to see the CRM overview
3. Register a new account or use the demo account
4. Manage your contacts with the card or spreadsheet view
5. Import contacts from CSV files
6. Export your contact data

## Development

This is a demo application. For production use, consider:
- Using a proper database (PostgreSQL, MySQL)
- Implementing proper password hashing
- Adding session security
- Adding input validation and sanitization
- Implementing proper error handling
