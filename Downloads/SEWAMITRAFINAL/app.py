import os
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = secrets.token_hex(24)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bridge.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'previous-work')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def normalize_photo_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
        except json.JSONDecodeError:
            pass
        return [cleaned]
    return []


def normalize_worker_profile(row):
    if row is None:
        return None
    profile = dict(row)
    if 'previous_work_photos' in profile:
        profile['previous_work_photos'] = normalize_photo_list(profile.get('previous_work_photos'))
    return profile


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        phone TEXT,
        role TEXT NOT NULL CHECK(role IN ('customer','worker','business','service-team','admin')),
        id_verified INTEGER DEFAULT 0,
        id_number TEXT,
        on_behalf_of TEXT,
        behalf_details TEXT,
        latitude REAL,
        longitude REAL,
        address TEXT,
        bio TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS worker_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        skills TEXT,
        hourly_rate REAL,
        daily_rate REAL,
        portfolio TEXT,
        previous_work_photos TEXT DEFAULT '[]',
        availability INTEGER DEFAULT 1,
        group_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS worker_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        leader_id INTEGER NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (leader_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS worker_group_members (
        group_id INTEGER NOT NULL,
        worker_id INTEGER NOT NULL,
        PRIMARY KEY (group_id, worker_id),
        FOREIGN KEY (group_id) REFERENCES worker_groups(id),
        FOREIGN KEY (worker_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS job_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        icon TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS help_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT,
        category TEXT,
        tags TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        category TEXT,
        budget REAL,
        num_workers INTEGER DEFAULT 1,
        status TEXT DEFAULT 'open',
        latitude REAL,
        longitude REAL,
        location TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (customer_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS job_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        worker_id INTEGER,
        group_id INTEGER,
        proposed_price REAL,
        price_type TEXT DEFAULT 'total',
        status TEXT DEFAULT 'pending',
        message TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (job_id) REFERENCES jobs(id),
        FOREIGN KEY (worker_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS negotiations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        price REAL,
        price_type TEXT,
        proposed_by TEXT NOT NULL,
        message TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (application_id) REFERENCES job_applications(id)
    );

    CREATE TABLE IF NOT EXISTS job_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        worker_id INTEGER,
        group_id INTEGER,
        agreed_price REAL,
        price_type TEXT DEFAULT 'total',
        status TEXT DEFAULT 'in_progress',
        started_at TEXT DEFAULT (datetime('now')),
        completed_at TEXT,
        FOREIGN KEY (job_id) REFERENCES jobs(id)
    );

    CREATE TABLE IF NOT EXISTS job_cancellations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        assignment_id INTEGER,
        cancelled_by TEXT NOT NULL,
        reason TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (job_id) REFERENCES jobs(id),
        FOREIGN KEY (assignment_id) REFERENCES job_assignments(id)
    );

    CREATE TABLE IF NOT EXISTS wallets (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0,
        held_balance REAL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'completed',
        related_job_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        rater_id INTEGER NOT NULL,
        ratee_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        review TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (rater_id) REFERENCES users(id),
        FOREIGN KEY (ratee_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS sos_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        latitude REAL,
        longitude REAL,
        description TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complainant_id INTEGER NOT NULL,
        respondent_id INTEGER,
        job_id INTEGER,
        subject TEXT,
        description TEXT,
        status TEXT DEFAULT 'submitted',
        resolution TEXT,
        complaint_uuid TEXT UNIQUE,
        evidence TEXT DEFAULT '[]',
        preferred_resolution TEXT,
        priority TEXT DEFAULT 'LOW',
        assigned_to INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (complainant_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS complaint_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        author_id INTEGER NOT NULL,
        note TEXT,
        internal INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (complaint_id) REFERENCES complaints(id),
        FOREIGN KEY (author_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS committee_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER NOT NULL,
        reported_id INTEGER,
        description TEXT,
        status TEXT DEFAULT 'open',
        response TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (reporter_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        content TEXT,
        read_flag INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (sender_id) REFERENCES users(id),
        FOREIGN KEY (receiver_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        category TEXT,
        image_url TEXT,
        stock INTEGER DEFAULT 100,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (business_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL,
        quantity INTEGER DEFAULT 1,
        total_price REAL,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (customer_id) REFERENCES users(id)
    );
    ''')

    # Seed job categories
    categories = [
        ('Plumbing', '🔧'), ('Electrical', '💡'), ('Carpentry', '🪚'),
        ('Painting', '🎨'), ('Cleaning', '🧹'), ('Moving/Relocation', '📦'),
        ('Gardening', '🌱'), ('Cooking/Catering', '🍳'), ('Tutoring', '📚'),
        ('Repair/Maintenance', '🛠️'), ('Delivery', '🚚'), ('Construction', '🏗️'),
        ('Driving', '🚗'), ('Beauty/Salon', '💇'), ('Photography', '📷'),
        ('Other', '➕')
    ]
    for name, icon in categories:
        c.execute('INSERT OR IGNORE INTO job_categories (name, icon) VALUES (?,?)', (name, icon))

    # Seed admin user
    admin_email = 'admin@bridge.local'
    c.execute('SELECT id FROM users WHERE email = ?', (admin_email,))
    if not c.fetchone():
        admin_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute(
            'INSERT INTO users (name, email, password_hash, role, id_verified, phone) VALUES (?,?,?,?,?,?)',
            ('Admin', admin_email, admin_hash, 'admin', 1, '0000000000')
        )

    # Seed a small, repeatable demo dataset for local development.
    demo_hash = hashlib.sha256('demo123'.encode()).hexdigest()
    demo_users = [
        ('Demo Customer', 'customer@bridge.local', 'customer', '9876500001', 12.9716, 77.5946, 'Indiranagar, Bengaluru', 'Looking for reliable local help.'),
        ('Kaushal', 'kaushal@bridge.local', 'worker', '9876500002', 12.9728, 77.5985, 'Indiranagar, Bengaluru', 'Professional home chef and caterer offering tasty, hygienic meals and event cooking for families and small gatherings.'),
        ('Arjun Electrician', 'worker1@bridge.local', 'worker', '9876500003', 12.9750, 77.6030, 'Ulsoor, Bengaluru', 'Certified electrician with 8 years of experience.'),
        ('Meera Plumber', 'worker2@bridge.local', 'worker', '9876500004', 12.9650, 77.5900, 'Domlur, Bengaluru', 'Fast plumbing repairs and installations.'),
        ('Ravi Home Care', 'worker3@bridge.local', 'worker', '9876500005', 12.9850, 77.5800, 'Malleshwaram, Bengaluru', 'Cleaning and home maintenance specialist.'),
        ('CraftHub Supplies', 'business', 'business', '9876500006', 12.9680, 77.6050, 'Koramangala, Bengaluru', 'Tools and supplies for local professionals.')
    ]
    demo_ids = {}
    for name, email, role, phone, latitude, longitude, address, bio in demo_users:
        c.execute(
            '''INSERT OR IGNORE INTO users
               (name, email, password_hash, phone, role, id_verified, latitude, longitude, address, bio)
               VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (name, email, demo_hash, phone, role, 1, latitude, longitude, address, bio)
        )
        if email == 'kaushal@bridge.local':
            c.execute(
                '''UPDATE users
                         SET name = ?, phone = ?, latitude = ?, longitude = ?, address = ?, bio = ?
                   WHERE email = ?''',
                     ('Kaushal', '9876500002', 12.9728, 77.5985, 'Indiranagar, Bengaluru', 'Professional home chef and caterer offering tasty, hygienic meals and event cooking for families and small gatherings.', email)
            )
        demo_ids[email] = c.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()['id']

    worker_profiles = [
        ('kaushal@bridge.local', 'Cooking,Catering,Meal Prep,Event Cooking', 500, 3500, 'Specializes in home-style vegetarian and non-vegetarian meals, party catering, and daily tiffin service for busy families and small events.', '/static/uploads/previous-work/kaushal-cooking-sample.svg'),
        ('worker1@bridge.local', 'Electrical,Repair/Maintenance', 450, 2800, 'Residential wiring, fans, lights and safety checks.', '[]'),
        ('worker2@bridge.local', 'Plumbing,Repair/Maintenance', 400, 2500, 'Leak repair, bathroom fittings and water lines.', '[]'),
        ('worker3@bridge.local', 'Cleaning,Painting,Gardening', 300, 1900, 'Home care, painting touch-ups and garden maintenance.', '[]')
    ]
    for email, skills, hourly_rate, daily_rate, portfolio, previous_work in worker_profiles:
        user_id = demo_ids[email]
        c.execute(
            '''INSERT INTO worker_profiles
               (user_id, skills, hourly_rate, daily_rate, portfolio, previous_work_photos, availability)
               VALUES (?,?,?,?,?,?,1)
               ON CONFLICT(user_id) DO UPDATE SET
                 skills = excluded.skills,
                 hourly_rate = excluded.hourly_rate,
                 daily_rate = excluded.daily_rate,
                 portfolio = excluded.portfolio,
                 previous_work_photos = excluded.previous_work_photos,
                 availability = 1''',
            (user_id, skills, hourly_rate, daily_rate, portfolio, previous_work)
        )

    c.execute('INSERT OR IGNORE INTO wallets (user_id, balance, held_balance) VALUES (?,?,0)', (demo_ids['customer@bridge.local'], 5000))
    c.execute('INSERT OR IGNORE INTO wallets (user_id, balance, held_balance) VALUES (?,?,0)', (demo_ids['business'], 3200))
    for email in ('worker1@bridge.local', 'worker2@bridge.local', 'worker3@bridge.local'):
        c.execute('INSERT OR IGNORE INTO wallets (user_id, balance, held_balance) VALUES (?,?,0)', (demo_ids[email], 1000))

    demo_jobs = [
        ('Need electrician for kitchen rewiring', 'Replace old wiring and install three new light points.', 'Electrical', 2200, 1, 12.9732, 77.6008, 'Indiranagar 12th Main'),
        ('Fix leaking bathroom tap', 'Repair the leaking tap and check the water pressure.', 'Plumbing', 900, 1, 12.9684, 77.5887, 'Domlur near Inner Ring Road'),
        ('Deep clean and paint living room', 'One-day deep clean followed by two accent walls.', 'Cleaning', 3500, 2, 12.9802, 77.5921, 'Ulsoor Lake area')
    ]
    demo_job_ids = []
    for title, description, category, budget, num_workers, latitude, longitude, location in demo_jobs:
        c.execute('SELECT id FROM jobs WHERE title = ? AND customer_id = ?', (title, demo_ids['customer@bridge.local']))
        existing_job = c.fetchone()
        if existing_job:
            demo_job_ids.append(existing_job['id'])
        else:
            c.execute(
                '''INSERT INTO jobs
                   (customer_id, title, description, category, budget, num_workers, status, latitude, longitude, location)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (demo_ids['customer@bridge.local'], title, description, category, budget, num_workers, 'open', latitude, longitude, location)
            )
            demo_job_ids.append(c.lastrowid)

    c.execute('SELECT id FROM worker_groups WHERE name = ?', ('Bridge Home Pros',))
    demo_group = c.fetchone()
    if not demo_group:
        c.execute(
            'INSERT INTO worker_groups (name, leader_id, description) VALUES (?,?,?)',
            ('Bridge Home Pros', demo_ids['worker1@bridge.local'], 'A trusted local team for electrical, plumbing and home repairs.')
        )
        demo_group_id = c.lastrowid
    else:
        demo_group_id = demo_group['id']
    for email in ('worker1@bridge.local', 'worker2@bridge.local', 'worker3@bridge.local'):
        c.execute('INSERT OR IGNORE INTO worker_group_members (group_id, worker_id) VALUES (?,?)', (demo_group_id, demo_ids[email]))

    demo_products = [
        ('LED Emergency Light', 'Rechargeable light for home repairs and power cuts.', 799, 'Electrical', '💡', 24),
        ('Professional Plumbing Kit', 'Compact toolkit with wrench, tape and fittings.', 1499, 'Tools', '🧰', 12),
        ('Eco Home Cleaning Pack', 'Plant-based cleaners for kitchens and bathrooms.', 599, 'Cleaning', '🧼', 30),
        ('Smart Water Filter', 'Compact filtration unit for kitchen water safety.', 2499, 'Home', '💧', 18),
        ('Portable Drill Set', 'Cordless drill with bits for fast home fixes.', 1899, 'Tools', '🔧', 16),
        ('Safety Helmet Kit', 'Protective headgear and gloves for renovation work.', 999, 'Safety', '🦺', 20),
        ('Kitchen Cleaning Bundle', 'Deep-clean essentials for counters, sinks and tiles.', 699, 'Cleaning', '🫧', 25),
        ('Garden Starter Pack', 'Seed mix, gloves and basic outdoor maintenance tools.', 1299, 'Gardening', '🌿', 14)
    ]
    for name, description, price, category, image_url, stock in demo_products:
        c.execute(
            '''INSERT OR IGNORE INTO products
               (business_id, name, description, price, category, image_url, stock)
               VALUES (?,?,?,?,?,?,?)''',
            (demo_ids['business'], name, description, price, category, image_url, stock)
        )

    demo_product = c.execute('SELECT id, price FROM products WHERE name = ?', ('LED Emergency Light',)).fetchone()
    if c.execute('SELECT COUNT(*) FROM job_assignments WHERE job_id = ? AND worker_id = ?', (demo_job_ids[0], demo_ids['worker1@bridge.local'])).fetchone()[0] == 0:
        c.execute(
            '''INSERT INTO job_assignments (job_id, worker_id, agreed_price, price_type, status)
               VALUES (?,?,?,?,?)''',
            (demo_job_ids[0], demo_ids['worker1@bridge.local'], 2200, 'total', 'in_progress')
        )
    if c.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ? AND description = ?', (demo_ids['customer@bridge.local'], 'Demo wallet top-up')).fetchone()[0] == 0:
        c.execute(
            'INSERT INTO transactions (user_id, amount, type, description) VALUES (?,?,?,?)',
            (demo_ids['customer@bridge.local'], 5000, 'deposit', 'Demo wallet top-up')
        )
    if c.execute('SELECT COUNT(*) FROM orders WHERE customer_id = ? AND product_id = ?', (demo_ids['customer@bridge.local'], demo_product['id'])).fetchone()[0] == 0:
        c.execute(
            'INSERT INTO orders (product_id, customer_id, quantity, total_price, status) VALUES (?,?,?,?,?)',
            (demo_product['id'], demo_ids['customer@bridge.local'], 1, demo_product['price'], 'pending')
        )
    if c.execute('SELECT COUNT(*) FROM sos_alerts WHERE user_id = ? AND description = ?', (demo_ids['worker2@bridge.local'], 'Demo safety check')).fetchone()[0] == 0:
        c.execute(
            'INSERT INTO sos_alerts (user_id, latitude, longitude, description) VALUES (?,?,?,?)',
            (demo_ids['worker2@bridge.local'], 12.9650, 77.5900, 'Demo safety check')
        )
    if c.execute('SELECT COUNT(*) FROM complaints WHERE complainant_id = ? AND subject = ?', (demo_ids['customer@bridge.local'], 'Demo service review')).fetchone()[0] == 0:
        c.execute(
            'INSERT INTO complaints (complainant_id, respondent_id, job_id, subject, description) VALUES (?,?,?,?,?)',
            (demo_ids['customer@bridge.local'], demo_ids['worker1@bridge.local'], demo_job_ids[0], 'Demo service review', 'Sample complaint for the admin workflow.')
        )
    if c.execute('SELECT COUNT(*) FROM committee_reports WHERE reporter_id = ? AND description = ?', (demo_ids['customer@bridge.local'], 'Demo committee report')).fetchone()[0] == 0:
        c.execute(
            'INSERT INTO committee_reports (reporter_id, reported_id, description) VALUES (?,?,?)',
            (demo_ids['customer@bridge.local'], demo_ids['worker1@bridge.local'], 'Demo committee report')
        )

    if c.execute('SELECT COUNT(*) FROM messages WHERE sender_id = ? AND receiver_id = ?', (demo_ids['customer@bridge.local'], demo_ids['worker1@bridge.local'])).fetchone()[0] == 0:
        c.execute(
            'INSERT INTO messages (sender_id, receiver_id, content) VALUES (?,?,?)',
            (demo_ids['customer@bridge.local'], demo_ids['worker1@bridge.local'], 'Hi Arjun, are you available for the kitchen rewiring job?')
        )
    if c.execute('SELECT COUNT(*) FROM ratings WHERE rater_id = ? AND ratee_id = ?', (demo_ids['customer@bridge.local'], demo_ids['worker2@bridge.local'])).fetchone()[0] == 0:
        c.execute(
            'INSERT INTO ratings (job_id, rater_id, ratee_id, score, review) VALUES (?,?,?,?,?)',
            (demo_job_ids[1], demo_ids['customer@bridge.local'], demo_ids['worker2@bridge.local'], 5, 'Quick, professional and tidy.')
        )

    # Seed help articles
    articles = [
        ('Booking a Service', 'If your service was not accepted, try checking your job details and re-posting or contacting support.', 'Booking', 'booking,service'),
        ('Payment failed but money deducted', 'If your payment failed but money was deducted, check your wallet transactions. If unresolved, raise a complaint from Help & Support.', 'Payment', 'payment,refund'),
        ('Provider didn\'t arrive', 'First contact the assigned provider via Messages. If the provider does not respond, raise a complaint and request a re-assignment.', 'Provider', 'provider,late')
    ]
    for title, body, category, tags in articles:
        c.execute('INSERT OR IGNORE INTO help_articles (title, body, category, tags) VALUES (?,?,?,?)', (title, body, category, tags))

    columns = [col[1] for col in conn.execute('PRAGMA table_info(worker_profiles)').fetchall()]
    if 'previous_work_photos' not in columns:
        conn.execute("ALTER TABLE worker_profiles ADD COLUMN previous_work_photos TEXT DEFAULT '[]'")

    # Ensure complaints table has new columns when upgrading existing DB
    comp_cols = [col[1] for col in conn.execute('PRAGMA table_info(complaints)').fetchall()]
    if 'complaint_uuid' not in comp_cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN complaint_uuid TEXT")
    if 'evidence' not in comp_cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN evidence TEXT DEFAULT '[]'")
    if 'preferred_resolution' not in comp_cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN preferred_resolution TEXT")
    if 'priority' not in comp_cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN priority TEXT DEFAULT 'LOW'")
    if 'assigned_to' not in comp_cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN assigned_to INTEGER")

    conn.commit()
    conn.close()


def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = session.get('user_id')
        if not uid:
            return jsonify({'error': 'Not logged in'}), 401
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            uid = session.get('user_id')
            if not uid:
                return jsonify({'error': 'Not logged in'}), 401
            conn = get_db()
            user = conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
            conn.close()
            user_role = user['role'] if user else None
            allowed = user_role in roles
            if user_role == 'service-team' and 'worker' in roles:
                allowed = True
            if not user or not allowed:
                return jsonify({'error': 'Unauthorized'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()
    conn.close()
    return user


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


@app.route('/<page>.html')
def serve_page(page):
    try:
        return send_from_directory('templates', page + '.html')
    except FileNotFoundError:
        return 'Page not found', 404


# ---------------------------------------------------------------------------
# AUTH API
# ---------------------------------------------------------------------------

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    required = ['name', 'email', 'password', 'role']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    role = data['role']
    if role not in ('customer', 'worker', 'business', 'service-team'):
        return jsonify({'error': 'Invalid role'}), 400

    conn = get_db()
    try:
        c = conn.cursor()

        def add_user_for_role(user_name, user_email, user_password, user_phone, user_role, **extra):
            pw_hash = hash_password(user_password)
            c.execute(
                '''INSERT INTO users (name, email, password_hash, phone, role, id_number,
                   on_behalf_of, behalf_details, latitude, longitude, address, bio)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    user_name, user_email, pw_hash, user_phone or '',
                    user_role, extra.get('id_number', ''),
                    extra.get('on_behalf_of', ''), extra.get('behalf_details', ''),
                    extra.get('latitude'), extra.get('longitude'),
                    extra.get('address', ''), extra.get('bio', '')
                )
            )
            user_id = c.lastrowid
            c.execute('INSERT INTO wallets (user_id, balance, held_balance) VALUES (?,?,0)', (user_id, 1000))
            return user_id

        if role == 'service-team':
            team_name = (data.get('team_name') or '').strip()
            if not team_name:
                return jsonify({'error': 'Team name is required'}), 400

            team_members = data.get('team_members') or []
            if not isinstance(team_members, list):
                return jsonify({'error': 'Team members must be a list'}), 400

            if len(team_members) == 0:
                return jsonify({'error': 'Add at least one team member'}), 400

            user_id = add_user_for_role(
                data['name'], data['email'], data['password'], data.get('phone', ''), role,
                id_number=data.get('id_number', ''),
                on_behalf_of=data.get('on_behalf_of', ''),
                behalf_details=data.get('behalf_details', ''),
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                address=data.get('address', ''),
                bio=data.get('team_description', '')
            )

            c.execute(
                'INSERT INTO worker_groups (name, leader_id, description) VALUES (?,?,?)',
                (team_name, user_id, data.get('team_description', ''))
            )
            group_id = c.lastrowid
            c.execute('INSERT INTO worker_group_members (group_id, worker_id) VALUES (?,?)', (group_id, user_id))

            for member in team_members:
                member_name = (member or {}).get('name', '').strip()
                member_email = (member or {}).get('email', '').strip()
                member_password = (member or {}).get('password', '')
                if not member_name or not member_email or not member_password:
                    return jsonify({'error': 'Each team member needs a name, email, and password'}), 400

                member_id = add_user_for_role(
                    member_name, member_email, member_password, (member or {}).get('phone', ''), 'worker',
                    address=(member or {}).get('address', ''),
                    bio=(member or {}).get('skills', '')
                )
                c.execute(
                    '''INSERT INTO worker_profiles (user_id, skills, hourly_rate, daily_rate, portfolio, availability, group_id)
                       VALUES (?,?,?,?,?,?,?)''',
                    (
                        member_id,
                        (member or {}).get('skills', ''),
                        (member or {}).get('hourly_rate'),
                        (member or {}).get('daily_rate'),
                        (member or {}).get('portfolio', ''),
                        1,
                        group_id
                    )
                )
                c.execute('INSERT INTO worker_group_members (group_id, worker_id) VALUES (?,?)', (group_id, member_id))

            conn.commit()
            conn.close()
            return jsonify({'message': 'Service team registered successfully', 'user_id': user_id}), 201

        pw_hash = hash_password(data['password'])
        c.execute(
            '''INSERT INTO users (name, email, password_hash, phone, role, id_number,
               on_behalf_of, behalf_details, latitude, longitude, address, bio)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                data['name'], data['email'], pw_hash, data.get('phone', ''),
                role, data.get('id_number', ''),
                data.get('on_behalf_of', ''), data.get('behalf_details', ''),
                data.get('latitude'), data.get('longitude'),
                data.get('address', ''), data.get('bio', '')
            )
        )
        user_id = c.lastrowid

        c.execute('INSERT INTO wallets (user_id, balance, held_balance) VALUES (?,?,0)', (user_id, 1000))

        if role == 'worker':
            skills = data.get('skills', '')
            c.execute(
                '''INSERT INTO worker_profiles (user_id, skills, hourly_rate, daily_rate, portfolio, availability)
                   VALUES (?,?,?,?,?,1)''',
                (user_id, skills, data.get('hourly_rate'), data.get('daily_rate'), data.get('portfolio', ''))
            )

        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Email already registered'}), 409
    conn.close()
    return jsonify({'message': 'Registered successfully', 'user_id': user_id}), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '')
    password = data.get('password', '')
    pw_hash = hash_password(password)
    conn = get_db()
    user = conn.execute(
        'SELECT * FROM users WHERE email = ? AND password_hash = ?', (email, pw_hash)
    ).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    session['user_id'] = user['id']
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user['id'], 'name': user['name'], 'email': user['email'],
            'role': user['role'], 'id_verified': bool(user['id_verified'])
        }
    })


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})


@app.route('/api/auth/me', methods=['GET'])
def me():
    user = current_user()
    if not user:
        return jsonify({'user': None})
    profile = None
    conn = get_db()
    if user['role'] == 'worker':
        profile = conn.execute('SELECT * FROM worker_profiles WHERE user_id = ?', (user['id'],)).fetchone()
    wallet = conn.execute('SELECT balance, held_balance FROM wallets WHERE user_id = ?', (user['id'],)).fetchone()
    conn.close()
    return jsonify({
        'user': {
            'id': user['id'], 'name': user['name'], 'email': user['email'],
            'role': user['role'], 'phone': user['phone'],
            'id_verified': bool(user['id_verified']),
            'address': user['address'], 'bio': user['bio'],
            'latitude': user['latitude'], 'longitude': user['longitude'],
        },
        'worker_profile': normalize_worker_profile(profile),
        'wallet': dict(wallet) if wallet else None
    })


@app.route('/api/auth/verify-id', methods=['POST'])
@login_required
def verify_id():
    data = request.json
    id_number = data.get('id_number', '')
    conn = get_db()
    conn.execute('UPDATE users SET id_verified = 1, id_number = ? WHERE id = ?', (id_number, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'ID verified successfully'})


# ---------------------------------------------------------------------------
# JOB CATEGORIES
# ---------------------------------------------------------------------------

@app.route('/api/job-categories', methods=['GET'])
def get_categories():
    conn = get_db()
    rows = conn.execute('''
        SELECT id, name, icon
        FROM job_categories
        GROUP BY name
        ORDER BY name
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/help/articles', methods=['GET'])
def list_help_articles():
    conn = get_db()
    rows = conn.execute('SELECT id, title, category, tags FROM help_articles ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/help/search', methods=['GET'])
def search_help_articles():
    q = (request.args.get('q') or '').strip()
    conn = get_db()
    if not q:
        rows = conn.execute('SELECT id, title, category, tags FROM help_articles ORDER BY created_at DESC LIMIT 10').fetchall()
    else:
        pattern = f'%{q}%'
        rows = conn.execute('''SELECT id, title, category, tags FROM help_articles
                               WHERE title LIKE ? OR body LIKE ? OR tags LIKE ? ORDER BY created_at DESC LIMIT 20''', (pattern, pattern, pattern)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/config/maps', methods=['GET'])
@login_required
def maps_config():
    return jsonify({'google_maps_api_key': os.getenv('GOOGLE_MAPS_API_KEY', '')})


# ---------------------------------------------------------------------------
# JOBS API
# ---------------------------------------------------------------------------

@app.route('/api/jobs', methods=['GET'])
@login_required
def list_jobs():
    user = current_user()
    conn = get_db()
    if user['role'] == 'customer':
        rows = conn.execute(
            '''SELECT j.*, u.name as customer_name FROM jobs j
               JOIN users u ON j.customer_id = u.id
               WHERE j.customer_id = ? ORDER BY j.created_at DESC''',
            (user['id'],)
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT j.*, u.name as customer_name FROM jobs j
               JOIN users u ON j.customer_id = u.id
               WHERE j.status = 'open' ORDER BY j.created_at DESC'''
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/jobs', methods=['POST'])
@login_required
@role_required('customer')
def create_job():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO jobs (customer_id, title, description, category, budget, num_workers,
           latitude, longitude, location)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        (
            session['user_id'], data['title'], data.get('description', ''),
            data.get('category', 'Other'), data.get('budget'), data.get('num_workers', 1),
            data.get('latitude'), data.get('longitude'), data.get('location', '')
        )
    )
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Job created', 'job_id': job_id}), 201


@app.route('/api/jobs/<int:job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    conn = get_db()
    job = conn.execute(
        '''SELECT j.*, u.name as customer_name, u.phone as customer_phone
           FROM jobs j JOIN users u ON j.customer_id = u.id WHERE j.id = ?''',
        (job_id,)
    ).fetchone()
    if not job:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404
    apps = conn.execute(
        '''SELECT a.*, u.name as worker_name FROM job_applications a
           JOIN users u ON a.worker_id = u.id WHERE a.job_id = ?''',
        (job_id,)
    ).fetchall()
    conn.close()
    return jsonify({'job': dict(job), 'applications': [dict(a) for a in apps]})


@app.route('/api/jobs/nearby', methods=['GET'])
@login_required
def nearby_jobs():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius_km = request.args.get('radius', default=25, type=float)
    conn = get_db()
    rows = conn.execute(
        '''SELECT j.id, j.title, j.description, j.category, j.budget, j.num_workers,
                  j.latitude, j.longitude, j.location, j.status, u.name AS customer_name
           FROM jobs j JOIN users u ON j.customer_id = u.id
           WHERE j.status = 'open' AND j.latitude IS NOT NULL AND j.longitude IS NOT NULL
           ORDER BY j.created_at DESC'''
    ).fetchall()
    jobs = []
    for row in rows:
        job = dict(row)
        if lat is not None and lng is not None:
            distance = ((job['latitude'] - lat) ** 2 + (job['longitude'] - lng) ** 2) ** 0.5 * 111
            if distance > radius_km:
                continue
            job['distance_km'] = round(distance, 1)
        else:
            job['distance_km'] = None
        jobs.append(job)
    conn.close()
    return jsonify({'jobs': jobs[:20], 'count': len(jobs)})


@app.route('/api/jobs/<int:job_id>/status', methods=['PUT'])
@login_required
def update_job_status(job_id):
    data = request.json
    status = data.get('status')
    conn = get_db()
    conn.execute('UPDATE jobs SET status = ? WHERE id = ?', (status, job_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Status updated'})


@app.route('/api/jobs/<int:job_id>/cancel', methods=['POST'])
@login_required
def cancel_job(job_id):
    data = request.json or {}
    reason = data.get('reason', '')
    user = current_user()
    conn = get_db()
    c = conn.cursor()
    job = c.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404
    if user['role'] != 'customer' or job['customer_id'] != user['id']:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
    if job['status'] in ('cancelled', 'completed'):
        conn.close()
        return jsonify({'error': 'Job cannot be cancelled'}), 400

    # If there's an active assignment, cancel it and refund the held payment
    assignment = c.execute('SELECT * FROM job_assignments WHERE job_id = ? AND status IN ("in_progress","pending_completion","assigned")', (job_id,)).fetchone()
    if assignment:
        c.execute("UPDATE job_assignments SET status = 'cancelled_by_customer' WHERE id = ?", (assignment['id'],))
        # Refund held payment back to customer's balance
        try:
            c.execute('UPDATE wallets SET balance = balance + ?, held_balance = held_balance - ? WHERE user_id = ?', (assignment['agreed_price'], assignment['agreed_price'], user['id']))
            c.execute('''INSERT INTO transactions (user_id, amount, type, description, status, related_job_id)
                         VALUES (?,?, 'refund', 'Refund due to job cancellation', 'completed', ?)''',
                      (user['id'], assignment['agreed_price'], job_id))
        except Exception:
            pass

    c.execute("UPDATE jobs SET status = 'cancelled' WHERE id = ?", (job_id,))
    c.execute('INSERT INTO job_cancellations (job_id, assignment_id, cancelled_by, reason) VALUES (?,?,?,?)',
              (job_id, assignment['id'] if assignment else None, 'customer', reason))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Job cancelled'})


# ---------------------------------------------------------------------------
# JOB APPLICATIONS & NEGOTIATIONS
# ---------------------------------------------------------------------------

@app.route('/api/jobs/<int:job_id>/apply', methods=['POST'])
@login_required
@role_required('worker')
def apply_job(job_id):
    data = request.json
    user = current_user()
    conn = get_db()
    # Check if already applied
    existing = conn.execute(
        'SELECT id FROM job_applications WHERE job_id = ? AND worker_id = ?',
        (job_id, user['id'])
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Already applied'}), 409
    c = conn.cursor()
    c.execute(
        '''INSERT INTO job_applications (job_id, worker_id, proposed_price, price_type, message)
           VALUES (?,?,?,?,?)''',
        (job_id, user['id'], data.get('proposed_price'), data.get('price_type', 'total'), data.get('message', ''))
    )
    app_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Applied successfully', 'application_id': app_id}), 201


@app.route('/api/jobs/<int:job_id>/apply-group', methods=['POST'])
@login_required
@role_required('worker')
def apply_job_group(job_id):
    data = request.json
    group_id = data.get('group_id')
    conn = get_db()
    # Check group membership
    member = conn.execute(
        'SELECT 1 FROM worker_group_members WHERE group_id = ? AND worker_id = ?',
        (group_id, session['user_id'])
    ).fetchone()
    if not member:
        conn.close()
        return jsonify({'error': 'Not a member of this group'}), 403
    c = conn.cursor()
    c.execute(
        '''INSERT INTO job_applications (job_id, group_id, proposed_price, price_type, message)
           VALUES (?,?,?,?,?)''',
        (job_id, group_id, data.get('proposed_price'), data.get('price_type', 'total'), data.get('message', ''))
    )
    app_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Group applied successfully', 'application_id': app_id}), 201


@app.route('/api/applications/<int:app_id>/negotiate', methods=['POST'])
@login_required
def negotiate(app_id):
    data = request.json
    user = current_user()
    conn = get_db()
    app_row = conn.execute('SELECT * FROM job_applications WHERE id = ?', (app_id,)).fetchone()
    if not app_row:
        conn.close()
        return jsonify({'error': 'Application not found'}), 404

    job = conn.execute('SELECT customer_id FROM jobs WHERE id = ?', (app_row['job_id'],)).fetchone()
    worker_id = app_row['worker_id']

    # Determine who is proposing
    if user['role'] == 'customer' and job['customer_id'] == user['id']:
        proposed_by = 'customer'
    elif user['id'] == worker_id:
        proposed_by = 'worker'
    else:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403

    c = conn.cursor()
    c.execute(
        '''INSERT INTO negotiations (application_id, price, price_type, proposed_by, message, status)
           VALUES (?,?,?,?,?, 'pending')''',
        (app_id, data.get('price'), data.get('price_type', 'total'), proposed_by, data.get('message', ''))
    )
    # Update application proposed_price
    c.execute('UPDATE job_applications SET proposed_price = ? WHERE id = ?', (data.get('price'), app_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Negotiation sent'}), 201


@app.route('/api/applications/<int:app_id>/negotiations', methods=['GET'])
@login_required
def get_negotiations(app_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM negotiations WHERE application_id = ? ORDER BY created_at ASC',
        (app_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/applications/<int:app_id>/accept', methods=['POST'])
@login_required
@role_required('customer')
def accept_application(app_id):
    data = request.json
    conn = get_db()
    c = conn.cursor()
    app_row = c.execute('SELECT * FROM job_applications WHERE id = ?', (app_id,)).fetchone()
    if not app_row:
        conn.close()
        return jsonify({'error': 'Application not found'}), 404

    job = c.execute('SELECT * FROM jobs WHERE id = ?', (app_row['job_id'],)).fetchone()
    if job['customer_id'] != session['user_id']:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403

    agreed_price = data.get('agreed_price', app_row['proposed_price'])
    price_type = data.get('price_type', app_row['price_type'])

    try:
        agreed_price = float(agreed_price)
    except (TypeError, ValueError):
        conn.close()
        return jsonify({'error': 'A valid agreed payment amount is required'}), 400
    if agreed_price <= 0:
        conn.close()
        return jsonify({'error': 'The agreed payment amount must be greater than zero'}), 400

    wallet = c.execute('SELECT balance FROM wallets WHERE user_id = ?', (session['user_id'],)).fetchone()
    if not wallet or wallet['balance'] < agreed_price:
        conn.close()
        return jsonify({'error': 'Insufficient job payment wallet balance. Deposit funds before accepting this application.'}), 400

    # Create assignment
    c.execute(
        '''INSERT INTO job_assignments (job_id, worker_id, group_id, agreed_price, price_type, status)
           VALUES (?,?,?,?,?, 'in_progress')''',
        (job['id'], app_row['worker_id'], app_row['group_id'], agreed_price, price_type)
    )

    # Update job status
    c.execute('UPDATE jobs SET status = ? WHERE id = ?', ('assigned', job['id']))
    # Update application status
    c.execute('UPDATE job_applications SET status = ? WHERE id = ?', ('accepted', app_id))

    # Hold payment from customer wallet
    c.execute(
        'UPDATE wallets SET balance = balance - ?, held_balance = held_balance + ? WHERE user_id = ?',
        (agreed_price, agreed_price, session['user_id'])
    )
    c.execute(
        '''INSERT INTO transactions (user_id, amount, type, description, status, related_job_id)
           VALUES (?,?, 'hold', 'Payment held for job', 'completed', ?)''',
        (session['user_id'], agreed_price, job['id'])
    )

    conn.commit()
    conn.close()
    return jsonify({'message': 'Application accepted, job assigned'})


@app.route('/api/applications/<int:app_id>/reject', methods=['POST'])
@login_required
@role_required('customer')
def reject_application(app_id):
    conn = get_db()
    conn.execute('UPDATE job_applications SET status = ? WHERE id = ?', ('rejected', app_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Application rejected'})


@app.route('/api/applications/my', methods=['GET'])
@login_required
@role_required('worker')
def my_applications():
    user = current_user()
    conn = get_db()
    rows = conn.execute(
        '''SELECT a.*, j.title as job_title, j.category, j.budget, j.status as job_status,
           u.name as customer_name
           FROM job_applications a
           JOIN jobs j ON a.job_id = j.id
           JOIN users u ON j.customer_id = u.id
           WHERE a.worker_id = ? ORDER BY a.created_at DESC''',
        (user['id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# JOB ASSIGNMENTS - complete & release payment
# ---------------------------------------------------------------------------

@app.route('/api/assignments', methods=['GET'])
@login_required
def my_assignments():
    user = current_user()
    conn = get_db()
    if user['role'] == 'customer':
        rows = conn.execute(
            '''SELECT ja.*, j.title as job_title, j.category, u.name as worker_name
               FROM job_assignments ja
               JOIN jobs j ON ja.job_id = j.id
               JOIN users u ON ja.worker_id = u.id
               WHERE j.customer_id = ? ORDER BY ja.started_at DESC''',
            (user['id'],)
        ).fetchall()
    elif user['role'] == 'worker':
        rows = conn.execute(
            '''SELECT ja.*, j.title as job_title, j.category, u.name as customer_name,
               j.customer_id
               FROM job_assignments ja
               JOIN jobs j ON ja.job_id = j.id
               JOIN users u ON j.customer_id = u.id
               WHERE ja.worker_id = ? ORDER BY ja.started_at DESC''',
            (user['id'],)
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT ja.*, j.title as job_title, u.name as worker_name, cu.name as customer_name
               FROM job_assignments ja
               JOIN jobs j ON ja.job_id = j.id
               JOIN users u ON ja.worker_id = u.id
               JOIN users cu ON j.customer_id = cu.id
               ORDER BY ja.started_at DESC'''
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/assignments/<int:assignment_id>/complete', methods=['POST'])
@login_required
def complete_assignment(assignment_id):
    user = current_user()
    conn = get_db()
    c = conn.cursor()
    assignment = c.execute('SELECT * FROM job_assignments WHERE id = ?', (assignment_id,)).fetchone()
    if not assignment:
        conn.close()
        return jsonify({'error': 'Assignment not found'}), 404

    job = c.execute('SELECT * FROM jobs WHERE id = ?', (assignment['job_id'],)).fetchone()

    # Customer confirms completion -> release payment
    if user['role'] == 'customer' and job['customer_id'] == user['id']:
        if assignment['status'] != 'pending_completion':
            conn.close()
            return jsonify({'error': 'The worker must mark the job as completed before approval'}), 400
        c.execute(
            "UPDATE job_assignments SET status = 'completed', completed_at = datetime('now') WHERE id = ?",
            (assignment_id,)
        )
        c.execute("UPDATE jobs SET status = 'completed' WHERE id = ?", (job['id'],))

        # Release held payment to worker
        worker_id = assignment['worker_id']
        if worker_id:
            c.execute(
                'UPDATE wallets SET held_balance = held_balance - ? WHERE user_id = ?',
                (assignment['agreed_price'], user['id'])
            )
            c.execute(
                'UPDATE wallets SET balance = balance + ? WHERE user_id = ?',
                (assignment['agreed_price'], worker_id)
            )
            c.execute(
                '''INSERT INTO transactions (user_id, amount, type, description, status, related_job_id)
                   VALUES (?,?, 'release', 'Payment received for completed job', 'completed', ?)''',
                (worker_id, assignment['agreed_price'], job['id'])
            )
        conn.commit()
        conn.close()
        return jsonify({'message': 'Job completed, payment released to worker'})

    # Worker marks as done -> pending customer confirmation
    if user['id'] == assignment['worker_id']:
        if assignment['status'] != 'in_progress':
            conn.close()
            return jsonify({'error': 'This assignment is no longer in progress'}), 400
        c.execute("UPDATE job_assignments SET status = 'pending_completion' WHERE id = ?", (assignment_id,))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Marked as done, waiting for customer confirmation'})

    conn.close()
    return jsonify({'error': 'Unauthorized'}), 403


@app.route('/api/assignments/<int:assignment_id>/cancel', methods=['POST'])
@login_required
@role_required('worker')
def cancel_assignment(assignment_id):
    data = request.json or {}
    reason = data.get('reason', '')
    user = current_user()
    conn = get_db()
    c = conn.cursor()
    assignment = c.execute('SELECT * FROM job_assignments WHERE id = ?', (assignment_id,)).fetchone()
    if not assignment:
        conn.close()
        return jsonify({'error': 'Assignment not found'}), 404
    if assignment['worker_id'] != user['id']:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
    if assignment['status'] not in ('in_progress', 'assigned'):
        conn.close()
        return jsonify({'error': 'This assignment cannot be cancelled at this stage'}), 400

    # Mark assignment cancelled by worker
    c.execute("UPDATE job_assignments SET status = 'cancelled_by_worker' WHERE id = ?", (assignment_id,))
    # Re-open the job so others can apply
    c.execute('UPDATE jobs SET status = ? WHERE id = ?', ('open', assignment['job_id']))

    # Refund held payment to customer (move held_balance back to balance)
    job = c.execute('SELECT * FROM jobs WHERE id = ?', (assignment['job_id'],)).fetchone()
    if job:
        customer_id = job['customer_id']
        try:
            c.execute('UPDATE wallets SET balance = balance + ?, held_balance = held_balance - ? WHERE user_id = ?', (assignment['agreed_price'], assignment['agreed_price'], customer_id))
            c.execute('''INSERT INTO transactions (user_id, amount, type, description, status, related_job_id)
                         VALUES (?,?, 'refund', 'Refund due to worker cancellation', 'completed', ?)''',
                      (customer_id, assignment['agreed_price'], assignment['job_id']))
        except Exception:
            pass

    c.execute('INSERT INTO job_cancellations (job_id, assignment_id, cancelled_by, reason) VALUES (?,?,?,?)',
              (assignment['job_id'], assignment_id, 'worker', reason))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Assignment cancelled by worker'})


# ---------------------------------------------------------------------------
# WALLET API
# ---------------------------------------------------------------------------

@app.route('/api/wallet', methods=['GET'])
@login_required
def get_wallet():
    conn = get_db()
    wallet = conn.execute('SELECT * FROM wallets WHERE user_id = ?', (session['user_id'],)).fetchone()
    txns = conn.execute(
        'SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return jsonify({
        'wallet': dict(wallet) if wallet else {'balance': 0, 'held_balance': 0},
        'transactions': [dict(t) for t in txns]
    })


@app.route('/api/wallet/deposit', methods=['POST'])
@login_required
def deposit():
    data = request.json
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE wallets SET balance = balance + ? WHERE user_id = ?', (amount, session['user_id']))
    c.execute(
        '''INSERT INTO transactions (user_id, amount, type, description, status)
           VALUES (?,?, 'deposit', 'Demo deposit (simulated payment)', 'completed')''',
        (session['user_id'], amount)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deposit successful (simulated)'})


@app.route('/api/wallet/demo-deposit/remove', methods=['POST'])
@login_required
@role_required('customer')
def remove_demo_deposit():
    conn = get_db()
    c = conn.cursor()
    deposit_txn = c.execute(
        '''SELECT id, amount FROM transactions
           WHERE user_id = ? AND type = 'deposit'
             AND description = 'Demo deposit (simulated payment)'
           ORDER BY id DESC LIMIT 1''',
        (session['user_id'],)
    ).fetchone()
    if not deposit_txn:
        conn.close()
        return jsonify({'error': 'No removable demo deposit found'}), 404

    wallet = c.execute('SELECT balance FROM wallets WHERE user_id = ?', (session['user_id'],)).fetchone()
    if not wallet or wallet['balance'] < deposit_txn['amount']:
        conn.close()
        return jsonify({'error': 'This deposit is reserved for a job and cannot be removed'}), 400

    c.execute('UPDATE wallets SET balance = balance - ? WHERE user_id = ?', (deposit_txn['amount'], session['user_id']))
    c.execute('DELETE FROM transactions WHERE id = ?', (deposit_txn['id'],))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Demo deposit removed'})


@app.route('/api/wallet/withdraw', methods=['POST'])
@login_required
def withdraw():
    data = request.json
    amount = float(data.get('amount', 0))
    conn = get_db()
    wallet = conn.execute('SELECT balance FROM wallets WHERE user_id = ?', (session['user_id'],)).fetchone()
    if not wallet or wallet['balance'] < amount:
        conn.close()
        return jsonify({'error': 'Insufficient balance'}), 400
    c = conn.cursor()
    c.execute('UPDATE wallets SET balance = balance - ? WHERE user_id = ?', (amount, session['user_id']))
    c.execute(
        '''INSERT INTO transactions (user_id, amount, type, description, status)
           VALUES (?,?, 'withdraw', 'Withdrawal (simulated)', 'completed')''',
        (session['user_id'], amount)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Withdrawal successful (simulated)'})


# ---------------------------------------------------------------------------
# RATINGS API
# ---------------------------------------------------------------------------

@app.route('/api/ratings', methods=['POST'])
@login_required
def create_rating():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    # Check if already rated
    existing = c.execute(
        'SELECT id FROM ratings WHERE job_id = ? AND rater_id = ? AND ratee_id = ?',
        (data.get('job_id'), session['user_id'], data.get('ratee_id'))
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Already rated'}), 409
    c.execute(
        'INSERT INTO ratings (job_id, rater_id, ratee_id, score, review) VALUES (?,?,?,?,?)',
        (data.get('job_id'), session['user_id'], data.get('ratee_id'), data.get('score'), data.get('review', ''))
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Rating submitted'}), 201


@app.route('/api/ratings/<int:user_id>', methods=['GET'])
def get_ratings(user_id):
    conn = get_db()
    rows = conn.execute(
        '''SELECT r.*, u.name as rater_name FROM ratings r
           JOIN users u ON r.rater_id = u.id WHERE r.ratee_id = ? ORDER BY r.created_at DESC''',
        (user_id,)
    ).fetchall()
    avg = conn.execute('SELECT AVG(score) as avg, COUNT(*) as count FROM ratings WHERE ratee_id = ?', (user_id,)).fetchone()
    conn.close()
    return jsonify({
        'ratings': [dict(r) for r in rows],
        'average': round(avg['avg'], 1) if avg['avg'] else 0,
        'count': avg['count']
    })


# ---------------------------------------------------------------------------
# SOS API
# ---------------------------------------------------------------------------

@app.route('/api/sos', methods=['POST'])
@login_required
def create_sos():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO sos_alerts (user_id, latitude, longitude, description) VALUES (?,?,?,?)',
        (session['user_id'], data.get('latitude'), data.get('longitude'), data.get('description', 'Emergency alert'))
    )
    sos_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'SOS alert sent', 'sos_id': sos_id}), 201


@app.route('/api/sos', methods=['GET'])
@login_required
def list_sos():
    user = current_user()
    conn = get_db()
    if user['role'] == 'admin':
        rows = conn.execute(
            '''SELECT s.*, u.name as user_name, u.role as user_role FROM sos_alerts s
               JOIN users u ON s.user_id = u.id ORDER BY s.created_at DESC'''
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM sos_alerts WHERE user_id = ? ORDER BY created_at DESC',
            (user['id'],)
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/sos/<int:sos_id>/resolve', methods=['POST'])
@login_required
@role_required('admin')
def resolve_sos(sos_id):
    conn = get_db()
    conn.execute("UPDATE sos_alerts SET status = 'resolved' WHERE id = ?", (sos_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'SOS resolved'})


# ---------------------------------------------------------------------------
# COMPLAINTS API
# ---------------------------------------------------------------------------

@app.route('/api/complaints', methods=['POST'])
@login_required
def create_complaint():
    # Accept JSON or multipart/form-data (for uploads)
    is_multipart = request.mimetype == 'multipart/form-data'
    payload = request.form.to_dict() if is_multipart else (request.json or {})
    files = request.files.getlist('evidence') if is_multipart else []

    evidence_paths = []
    for f in files:
        if not f or not f.filename:
            continue
        filename = f"complaint_{secrets.token_hex(8)}_{os.path.basename(f.filename)}"
        dest = os.path.join(UPLOAD_FOLDER, filename)
        f.save(dest)
        evidence_paths.append(f'/static/uploads/previous-work/{filename}')

    conn = get_db()
    c = conn.cursor()
    uuid = secrets.token_hex(8)
    preferred_resolution = payload.get('preferred_resolution')
    priority = payload.get('priority') or 'LOW'
    c.execute(
        '''INSERT INTO complaints (complainant_id, respondent_id, job_id, subject, description,
           complaint_uuid, evidence, preferred_resolution, priority, status)
           VALUES (?,?,?,?,?,?,?,?,?, 'submitted')''',
        (
            session['user_id'], payload.get('respondent_id'), payload.get('job_id'),
            payload.get('subject', ''), payload.get('description', ''), uuid,
            json.dumps(evidence_paths), preferred_resolution, priority
        )
    )
    cid = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Complaint filed', 'complaint_id': cid, 'complaint_uuid': uuid}), 201


@app.route('/api/complaints', methods=['GET'])
@login_required
def list_complaints():
    user = current_user()
    conn = get_db()
    if user['role'] == 'admin':
        rows = conn.execute(
            '''SELECT c.*, u.name as complainant_name, r.name as respondent_name
               FROM complaints c
               JOIN users u ON c.complainant_id = u.id
               LEFT JOIN users r ON c.respondent_id = r.id
               ORDER BY c.created_at DESC'''
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT c.*, u.name as complainant_name, r.name as respondent_name
               FROM complaints c
               JOIN users u ON c.complainant_id = u.id
               LEFT JOIN users r ON c.respondent_id = r.id
               WHERE c.complainant_id = ? ORDER BY c.created_at DESC''',
            (user['id'],)
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/complaints/<int:cid>/resolve', methods=['POST'])
@login_required
@role_required('admin')
def resolve_complaint(cid):
    data = request.json
    conn = get_db()
    conn.execute(
        "UPDATE complaints SET status = 'resolved', resolution = ? WHERE id = ?",
        (data.get('resolution', ''), cid)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Complaint resolved'})


@app.route('/api/complaints/<int:cid>', methods=['GET'])
@login_required
def get_complaint(cid):
    conn = get_db()
    row = conn.execute(
        '''SELECT c.*, u.name as complainant_name, r.name as respondent_name
           FROM complaints c
           JOIN users u ON c.complainant_id = u.id
           LEFT JOIN users r ON c.respondent_id = r.id WHERE c.id = ?''',
        (cid,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Complaint not found'}), 404
    notes = conn.execute('SELECT * FROM complaint_notes WHERE complaint_id = ? ORDER BY created_at ASC', (cid,)).fetchall()
    conn.close()
    out = dict(row)
    try:
        out['evidence'] = json.loads(out.get('evidence') or '[]')
    except Exception:
        out['evidence'] = []
    out['notes'] = [dict(n) for n in notes]
    return jsonify(out)


@app.route('/api/complaints/<int:cid>/status', methods=['PUT'])
@login_required
@role_required('admin', 'service-team')
def update_complaint_status(cid):
    data = request.json or {}
    status = data.get('status')
    assigned_to = data.get('assigned_to')
    priority = data.get('priority')
    conn = get_db()
    if assigned_to:
        conn.execute('UPDATE complaints SET assigned_to = ? WHERE id = ?', (assigned_to, cid))
    if priority:
        conn.execute('UPDATE complaints SET priority = ? WHERE id = ?', (priority, cid))
    if status:
        conn.execute('UPDATE complaints SET status = ? WHERE id = ?', (status, cid))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Complaint updated'})


@app.route('/api/complaints/<int:cid>/note', methods=['POST'])
@login_required
def add_complaint_note(cid):
    data = request.json or {}
    note = data.get('note', '')
    internal = 1 if data.get('internal', True) else 0
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO complaint_notes (complaint_id, author_id, note, internal) VALUES (?,?,?,?)',
              (cid, session['user_id'], note, internal))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Note added'})


@app.route('/api/complaints/<int:cid>/reopen', methods=['POST'])
@login_required
def reopen_complaint(cid):
    conn = get_db()
    conn.execute("UPDATE complaints SET status = 'reopened' WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Complaint reopened'})


# ---------------------------------------------------------------------------
# COMMITTEE API
# ---------------------------------------------------------------------------

@app.route('/api/committee', methods=['POST'])
@login_required
@role_required('worker')
def create_committee_report():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO committee_reports (reporter_id, reported_id, description) VALUES (?,?,?)',
        (session['user_id'], data.get('reported_id'), data.get('description', ''))
    )
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Report submitted', 'report_id': rid}), 201


@app.route('/api/committee', methods=['GET'])
@login_required
@role_required('worker', 'admin')
def list_committee():
    user = current_user()
    conn = get_db()
    if user['role'] == 'admin':
        rows = conn.execute(
            '''SELECT cr.*, u.name as reporter_name, r.name as reported_name
               FROM committee_reports cr
               JOIN users u ON cr.reporter_id = u.id
               LEFT JOIN users r ON cr.reported_id = r.id
               ORDER BY cr.created_at DESC'''
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT cr.*, u.name as reporter_name, r.name as reported_name
               FROM committee_reports cr
               JOIN users u ON cr.reporter_id = u.id
               LEFT JOIN users r ON cr.reported_id = r.id
               ORDER BY cr.created_at DESC'''
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/committee/<int:rid>/respond', methods=['POST'])
@login_required
@role_required('worker', 'admin')
def respond_committee(rid):
    data = request.json
    conn = get_db()
    conn.execute(
        "UPDATE committee_reports SET status = 'addressed', response = ? WHERE id = ?",
        (data.get('response', ''), rid)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Response recorded'})


# ---------------------------------------------------------------------------
# MESSAGES API
# ---------------------------------------------------------------------------

@app.route('/api/messages', methods=['POST'])
@login_required
def send_message():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO messages (sender_id, receiver_id, content) VALUES (?,?,?)',
        (session['user_id'], data.get('receiver_id'), data.get('content', ''))
    )
    mid = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Sent', 'msg_id': mid}), 201


@app.route('/api/messages/<int:other_id>', methods=['GET'])
@login_required
def get_messages(other_id):
    conn = get_db()
    rows = conn.execute(
        '''SELECT * FROM messages WHERE
           (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
           ORDER BY created_at ASC''',
        (session['user_id'], other_id, other_id, session['user_id'])
    ).fetchall()
    # Mark as read
    conn.execute(
        'UPDATE messages SET read_flag = 1 WHERE sender_id = ? AND receiver_id = ?',
        (other_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/messages/contacts', methods=['GET'])
@login_required
def get_contacts():
    user = current_user()
    conn = get_db()
    rows = conn.execute(
        '''SELECT DISTINCT
           CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END as other_id,
           u.name as other_name, u.role as other_role
           FROM messages m
           JOIN users u ON u.id = CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END
           WHERE sender_id = ? OR receiver_id = ?''',
        (user['id'], user['id'], user['id'], user['id'])
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# WORKER GROUPS API
# ---------------------------------------------------------------------------

@app.route('/api/groups', methods=['POST'])
@login_required
@role_required('worker')
def create_group():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO worker_groups (name, leader_id, description) VALUES (?,?,?)',
        (data['name'], session['user_id'], data.get('description', ''))
    )
    gid = c.lastrowid
    c.execute('INSERT INTO worker_group_members (group_id, worker_id) VALUES (?,?)', (gid, session['user_id']))
    c.execute('UPDATE worker_profiles SET group_id = ? WHERE user_id = ?', (gid, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Group created', 'group_id': gid}), 201


@app.route('/api/groups', methods=['GET'])
@login_required
def list_groups():
    conn = get_db()
    rows = conn.execute(
        '''SELECT g.*, u.name as leader_name,
           (SELECT COUNT(*) FROM worker_group_members WHERE group_id = g.id) as member_count
           FROM worker_groups g JOIN users u ON g.leader_id = u.id ORDER BY g.created_at DESC'''
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/groups/<int:gid>/members', methods=['GET'])
@login_required
def group_members(gid):
    conn = get_db()
    rows = conn.execute(
        '''SELECT u.id, u.name, u.phone, wp.skills FROM worker_group_members m
           JOIN users u ON m.worker_id = u.id
           LEFT JOIN worker_profiles wp ON wp.user_id = u.id
           WHERE m.group_id = ?''',
        (gid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/groups/<int:gid>/join', methods=['POST'])
@login_required
@role_required('worker')
def join_group(gid):
    conn = get_db()
    try:
        conn.execute('INSERT INTO worker_group_members (group_id, worker_id) VALUES (?,?)', (gid, session['user_id']))
        conn.execute('UPDATE worker_profiles SET group_id = ? WHERE user_id = ?', (gid, session['user_id']))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Already a member'}), 409
    conn.close()
    return jsonify({'message': 'Joined group'})


@app.route('/api/groups/my', methods=['GET'])
@login_required
@role_required('worker')
def my_group():
    conn = get_db()
    row = conn.execute(
        '''SELECT g.*, (SELECT COUNT(*) FROM worker_group_members WHERE group_id = g.id) as member_count
           FROM worker_groups g
           JOIN worker_group_members m ON m.group_id = g.id
           WHERE m.worker_id = ?''',
        (session['user_id'],)
    ).fetchone()
    conn.close()
    return jsonify(dict(row) if row else None)


# ---------------------------------------------------------------------------
# PRODUCTS API (Business)
# ---------------------------------------------------------------------------

@app.route('/api/products', methods=['POST'])
@login_required
@role_required('business')
def create_product():
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO products (business_id, name, description, price, category, image_url, stock)
           VALUES (?,?,?,?,?,?,?)''',
        (session['user_id'], data['name'], data.get('description', ''), data['price'],
         data.get('category', ''), data.get('image_url', ''), data.get('stock', 100))
    )
    pid = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Product created', 'product_id': pid}), 201


@app.route('/api/products', methods=['GET'])
@login_required
def list_products():
    conn = get_db()
    rows = conn.execute(
        '''SELECT p.*, u.name as business_name FROM products p
           JOIN users u ON p.business_id = u.id ORDER BY RANDOM()'''
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/products/my', methods=['GET'])
@login_required
@role_required('business')
def my_products():
    conn = get_db()
    rows = conn.execute('SELECT * FROM products WHERE business_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/products/<int:pid>/order', methods=['POST'])
@login_required
def place_order(pid):
    data = request.json
    quantity = int(data.get('quantity', 1))
    conn = get_db()
    c = conn.cursor()
    product = c.execute('SELECT * FROM products WHERE id = ?', (pid,)).fetchone()
    if not product:
        conn.close()
        return jsonify({'error': 'Product not found'}), 404
    total = product['price'] * quantity
    c.execute(
        'INSERT INTO orders (product_id, customer_id, quantity, total_price, status) VALUES (?,?,?,?, "pending")',
        (pid, session['user_id'], quantity, total)
    )
    oid = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'message': 'Order placed', 'order_id': oid, 'total': total}), 201


@app.route('/api/orders', methods=['GET'])
@login_required
def list_orders():
    user = current_user()
    conn = get_db()
    if user['role'] == 'business':
        rows = conn.execute(
            '''SELECT o.*, p.name as product_name, u.name as customer_name
               FROM orders o JOIN products p ON o.product_id = p.id
               JOIN users u ON o.customer_id = u.id
               WHERE p.business_id = ? ORDER BY o.created_at DESC''',
            (user['id'],)
        ).fetchall()
    elif user['role'] == 'admin':
        rows = conn.execute(
            '''SELECT o.*, p.name as product_name, u.name as customer_name, b.name as business_name
               FROM orders o JOIN products p ON o.product_id = p.id
               JOIN users u ON o.customer_id = u.id
               JOIN users b ON p.business_id = b.id
               ORDER BY o.created_at DESC'''
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT o.*, p.name as product_name FROM orders o
               JOIN products p ON o.product_id = p.id
               WHERE o.customer_id = ? ORDER BY o.created_at DESC''',
            (user['id'],)
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/orders/<int:oid>/status', methods=['PUT'])
@login_required
def update_order_status(oid):
    data = request.json
    status = data.get('status')
    conn = get_db()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, oid))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Order status updated'})


# ---------------------------------------------------------------------------
# PROFILE API
# ---------------------------------------------------------------------------

@app.route('/api/profile', methods=['PUT'])
@login_required
def update_profile():
    is_multipart = request.mimetype == 'multipart/form-data'
    payload = request.form.to_dict() if is_multipart else (request.json or {})
    uploaded_files = request.files.getlist('previous_work_photos') if is_multipart else []

    existing_photos = []
    if is_multipart:
        if 'previous_work_photos' in payload:
            existing_photos = normalize_photo_list(payload.get('previous_work_photos'))
        elif 'existing_previous_work_photos' in payload:
            existing_photos = normalize_photo_list(payload.get('existing_previous_work_photos'))
    else:
        existing_photos = normalize_photo_list((request.json or {}).get('previous_work_photos'))

    new_photos = []
    for upload in uploaded_files:
        if not upload or not upload.filename:
            continue
        filename = f"{secrets.token_hex(8)}_{os.path.basename(upload.filename)}"
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        upload.save(upload_path)
        new_photos.append(f'/static/uploads/previous-work/{filename}')

    final_photos = existing_photos + new_photos
    if is_multipart and 'clear_previous_work_photos' in payload and payload.get('clear_previous_work_photos') == 'true':
        final_photos = []

    data = payload.copy()
    data['previous_work_photos'] = final_photos
    data['name'] = data.get('name')
    data['phone'] = data.get('phone')
    data['address'] = data.get('address')
    data['bio'] = data.get('bio')
    data['latitude'] = data.get('latitude')
    data['longitude'] = data.get('longitude')

    conn = get_db()
    c = conn.cursor()
    c.execute(
        '''UPDATE users SET name = ?, phone = ?, address = ?, bio = ?, latitude = ?, longitude = ?
           WHERE id = ?''',
        (data.get('name'), data.get('phone'), data.get('address'),
         data.get('bio'), data.get('latitude'), data.get('longitude'), session['user_id'])
    )
    user = c.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user['role'] == 'worker':
        c.execute(
            '''INSERT INTO worker_profiles (user_id, skills, hourly_rate, daily_rate, portfolio, previous_work_photos, availability)
               VALUES (?, ?, ?, ?, ?, ?, 1)
               ON CONFLICT(user_id) DO UPDATE SET
                   skills = excluded.skills,
                   hourly_rate = excluded.hourly_rate,
                   daily_rate = excluded.daily_rate,
                   portfolio = excluded.portfolio,
                   previous_work_photos = excluded.previous_work_photos''',
            (
                session['user_id'],
                data.get('skills', ''),
                data.get('hourly_rate'),
                data.get('daily_rate'),
                data.get('portfolio', ''),
                json.dumps(final_photos)
            )
        )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Profile updated'})


@app.route('/api/profile/<int:user_id>', methods=['GET'])
def get_profile(user_id):
    conn = get_db()
    user = conn.execute(
        'SELECT id, name, email, role, phone, address, bio, id_verified, created_at FROM users WHERE id = ?',
        (user_id,)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    profile = None
    if user['role'] == 'worker':
        profile = conn.execute('SELECT * FROM worker_profiles WHERE user_id = ?', (user_id,)).fetchone()
    ratings = conn.execute(
        '''SELECT r.*, u.name as rater_name FROM ratings r
           JOIN users u ON r.rater_id = u.id WHERE r.ratee_id = ? ORDER BY r.created_at DESC''',
        (user_id,)
    ).fetchall()
    avg = conn.execute('SELECT AVG(score) as avg, COUNT(*) as count FROM ratings WHERE ratee_id = ?', (user_id,)).fetchone()
    conn.close()
    return jsonify({
        'user': dict(user),
        'worker_profile': normalize_worker_profile(profile),
        'ratings': [dict(r) for r in ratings],
        'avg_rating': round(avg['avg'], 1) if avg['avg'] else 0,
        'rating_count': avg['count']
    })


# ---------------------------------------------------------------------------
# MAP / NEARBY WORKERS API
# ---------------------------------------------------------------------------

@app.route('/api/workers/nearby', methods=['GET'])
@login_required
def nearby_workers():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    category = request.args.get('category', '')
    radius_km = request.args.get('radius', default=50, type=float)

    conn = get_db()
    query = '''
         SELECT u.id, u.name, wp.skills, wp.hourly_rate, wp.daily_rate, wp.availability,
             u.latitude AS worker_latitude, u.longitude AS worker_longitude
        FROM users u
        LEFT JOIN worker_profiles wp ON wp.user_id = u.id
        WHERE u.role = 'worker' AND wp.availability = 1
    '''
    params = []
    if category:
        query += ' AND wp.skills LIKE ?'
        params.append(f'%{category}%')

    rows = conn.execute(query, params).fetchall()
    workers = []
    for r in rows:
        w = dict(r)
        worker_latitude = w.pop('worker_latitude')
        worker_longitude = w.pop('worker_longitude')
        w['skills'] = w['skills'].split(',') if w['skills'] else []
        if lat is not None and lng is not None and worker_latitude and worker_longitude:
            dist = ((worker_latitude - lat) ** 2 + (worker_longitude - lng) ** 2) ** 0.5 * 111
            w['distance_km'] = round(dist, 1)
            if dist <= radius_km:
                workers.append(w)
        else:
            w['distance_km'] = None
            workers.append(w)

    workers.sort(key=lambda x: x['distance_km'] if x['distance_km'] is not None else 9999)
    conn.close()
    return jsonify({'workers': workers, 'available_count': len(workers)})


# ---------------------------------------------------------------------------
# ADMIN API
# ---------------------------------------------------------------------------

@app.route('/api/admin/users', methods=['GET'])
@login_required
@role_required('admin')
def admin_list_users():
    conn = get_db()
    rows = conn.execute('SELECT id, name, email, role, phone, id_verified, created_at FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/admin/users/<int:uid>/verify', methods=['POST'])
@login_required
@role_required('admin')
def admin_verify_user(uid):
    conn = get_db()
    conn.execute('UPDATE users SET id_verified = 1 WHERE id = ?', (uid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'User verified'})


@app.route('/api/admin/stats', methods=['GET'])
@login_required
@role_required('admin')
def admin_stats():
    conn = get_db()
    stats = {
        'users': conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c'],
        'jobs': conn.execute('SELECT COUNT(*) as c FROM jobs').fetchone()['c'],
        'completed_jobs': conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status = 'completed'").fetchone()['c'],
        'open_jobs': conn.execute("SELECT COUNT(*) as c FROM jobs WHERE status = 'open'").fetchone()['c'],
        'workers': conn.execute("SELECT COUNT(*) as c FROM users WHERE role = 'worker'").fetchone()['c'],
        'customers': conn.execute("SELECT COUNT(*) as c FROM users WHERE role = 'customer'").fetchone()['c'],
        'businesses': conn.execute("SELECT COUNT(*) as c FROM users WHERE role = 'business'").fetchone()['c'],
        'sos_active': conn.execute("SELECT COUNT(*) as c FROM sos_alerts WHERE status = 'active'").fetchone()['c'],
        'complaints_open': conn.execute("SELECT COUNT(*) as c FROM complaints WHERE status = 'open'").fetchone()['c'],
        'products': conn.execute('SELECT COUNT(*) as c FROM products').fetchone()['c'],
        'orders': conn.execute('SELECT COUNT(*) as c FROM orders').fetchone()['c'],
    }
    conn.close()
    return jsonify(stats)


@app.route('/api/admin/jobs', methods=['GET'])
@login_required
@role_required('admin')
def admin_list_jobs():
    conn = get_db()
    rows = conn.execute(
        '''SELECT j.*, u.name as customer_name FROM jobs j
           JOIN users u ON j.customer_id = u.id ORDER BY j.created_at DESC'''
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# LANGUAGE ASSISTANT (simple translation helper)
# ---------------------------------------------------------------------------

@app.route('/api/translate', methods=['POST'])
def translate():
    data = request.json
    text = data.get('text', '')
    target_lang = data.get('lang', 'en')

    translations = {
        'hi': {
            'hello': 'नमस्ते', 'job': 'काम', 'worker': 'मजदूर', 'customer': 'ग्राहक',
            'payment': 'भुगतान', 'register': 'रजिस्टर करें', 'login': 'लॉगिन',
            'profile': 'प्रोफ़ाइल', 'wallet': 'वॉलेट', 'help': 'मदद',
            'emergency': 'आपातकाल', 'search': 'खोज', 'apply': 'आवेदन करें'
        },
        'ta': {
            'hello': 'வணக்கம்', 'job': 'வேலை', 'worker': 'தொழிலாளி', 'customer': 'வாடிக்கையாளர்',
            'payment': 'கட்டணம்', 'register': 'பதிவு செய்', 'login': 'உள்நுழை',
            'profile': 'சுயவிவரம்', 'wallet': 'பணப்பை', 'help': 'உதவி',
            'emergency': 'அவசரம்', 'search': 'தேடல்', 'apply': 'விண்ணப்பிக்க'
        },
        'te': {
            'hello': 'నమస్కారం', 'job': 'పని', 'worker': 'కార్మికుడు', 'customer': 'కస్టమర్',
            'payment': 'చెల్లింపు', 'register': 'నమోదు చేయండి', 'login': 'లాగిన్',
            'profile': 'ప్రొఫైల్', 'wallet': 'వాలెట్', 'help': 'సహాయం',
            'emergency': 'అత్యవసరం', 'search': 'శోధన', 'apply': 'దరఖాస్తు'
        },
        'bn': {
            'hello': 'নমস্কার', 'job': 'কাজ', 'worker': 'শ্রমিক', 'customer': 'গ্রাহক',
            'payment': 'পেমেন্ট', 'register': 'নিবন্ধন', 'login': 'লগইন',
            'profile': 'প্রোফাইল', 'wallet': 'ওয়ালেট', 'help': 'সাহায্য',
            'emergency': 'জরুরী', 'search': 'অনুসন্ধান', 'apply': 'আবেদন'
        },
        'mr': {
            'hello': 'नमस्कार', 'job': 'काम', 'worker': 'कामगार', 'customer': 'ग्राहक',
            'payment': 'पेमेंट', 'register': 'नोंदणी', 'login': 'लॉगिन',
            'profile': 'प्रोफाइल', 'wallet': 'वॉलेट', 'help': 'मदत',
            'emergency': 'आपत्कालीन', 'search': 'शोध', 'apply': 'अर्ज'
        },
        'kn': {
            'hello': 'ನಮಸ್ಕಾರ', 'job': 'ಕೆಲಸ', 'worker': 'ಕೆಲಸಗಾರ', 'customer': 'ಗ್ರಾಹಕ',
            'payment': 'ಪಾವತಿ', 'register': 'ನೋಂದಣಿ', 'login': 'ಲಾಗಿನ್',
            'profile': 'ಪ್ರೊಫೈಲ್', 'wallet': 'ವಾಲೆಟ್', 'help': 'ಸಹಾಯ',
            'emergency': 'ತುರ್ತು', 'search': 'ಹುಡುಕಾಟ', 'apply': 'ಅರ್ಜಿ'
        }
    }

    lang_map = translations.get(target_lang, {})
    words = text.lower().split()
    translated = ' '.join(lang_map.get(w, w) for w in words)
    conn = None
    return jsonify({'translated': translated, 'lang': target_lang})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
