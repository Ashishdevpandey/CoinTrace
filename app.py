import os
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
import shutil
import random
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, g, session
from flask_cors import CORS
from dotenv import load_dotenv
import threading

# Load environment variables from .env file for local development
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key') # Change this in production
CORS(app)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db_url = os.environ.get('POSTGRES_URL')
        
        if db_url:
            # Postgres connection (Production/Vercel)
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
            db = g._database = psycopg2.connect(db_url)
            g.db_type = 'postgres'
        else:
            # SQLite connection (Local Development)
            db_path = os.path.join(os.path.dirname(__file__), 'banking.db')
            db = g._database = sqlite3.connect(db_path)
            db.row_factory = sqlite3.Row
            g.db_type = 'sqlite'
            
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    
    # Handle placeholder differences between Postgres (%s) and SQLite (?)
    if db_type == 'sqlite':
        query = query.replace('%s', '?')
        # SQLite Row object needs to be converted to dict for compatibility with RealDictCursor
        cur = db.execute(query, args)
        rv = [dict(row) for row in cur.fetchall()]
    else:
        cur = db.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, args)
        rv = cur.fetchall()
        
    cur.close()
    return (rv[0] if rv else None) if one else rv

def init_db():
    with app.app_context():
        try:
            db = get_db()
            db_type = getattr(g, 'db_type', 'sqlite')
            cur = db.cursor()
            
            # Syntax differences for primary keys and types
            if db_type == 'postgres':
                pk = "SERIAL PRIMARY KEY"
                double = "DOUBLE PRECISION"
            else:
                pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
                double = "REAL"

            cur.execute(f'CREATE TABLE IF NOT EXISTS customers (id {pk}, name TEXT NOT NULL, email TEXT NOT NULL, password TEXT)')
            cur.execute(f'CREATE TABLE IF NOT EXISTS accounts (id {pk}, customer_id INTEGER, type TEXT, balance {double} DEFAULT 0.0)')
            cur.execute(f'CREATE TABLE IF NOT EXISTS transactions (id {pk}, account_id INTEGER, date TEXT, amount {double}, type TEXT, category TEXT, description TEXT)')
            
            # Friends / Udhar tables
            cur.execute(f'''CREATE TABLE IF NOT EXISTS friends (
                id {pk},
                customer_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )''')
            cur.execute(f'''CREATE TABLE IF NOT EXISTS friend_transactions (
                id {pk},
                customer_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                amount {double} NOT NULL,
                type TEXT NOT NULL,
                note TEXT,
                date TEXT NOT NULL,
                settled INTEGER DEFAULT 0,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (friend_id) REFERENCES friends(id)
            )''')
            
            # OTP Verification Table
            cur.execute(f'CREATE TABLE IF NOT EXISTS otp_verifications (id {pk}, email TEXT NOT NULL, otp TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
            
            db.commit()
            
            # Add email column to friends if it doesn't exist (for existing databases)
            try:
                cur.execute('ALTER TABLE friends ADD COLUMN email TEXT')
                db.commit()
            except:
                pass # Column already exists
            
            cur.close()
        except Exception as e:
            print(f"Error initializing DB: {e}")

@app.route('/')
def index():
    return render_template('index.html')

# --- API Endpoints ---

def send_transaction_notification(target_email, friend_name, sender_name, amount, type, net_balance, reason="No reason provided"):
    sender_email = os.environ.get('MAIL_USERNAME')
    sender_password = os.environ.get('MAIL_PASSWORD')
    
    if not sender_email or not sender_password or not target_email:
        return False

    # Capitalize names for a professional look
    friend_name = friend_name.title()
    sender_name = sender_name.title()

    message = MIMEMultipart("alternative")
    
    # Dynamic Subject and Body based on transaction type
    if type == 'lent':
        subject = f"Money Lent Alert from {sender_name}"
        action_text = f"{sender_name} lent you ₹{amount:,.2f}"
    elif type == 'borrowed':
        subject = f"Money Borrowed Alert from {sender_name}"
        action_text = f"You borrowed ₹{amount:,.2f} from {sender_name}"
    else:
        subject = f"Account Settlement Alert: {sender_name}"
        action_text = f"A transaction of ₹{amount:,.2f} was settled with {sender_name}"

    # IMPROVED: Explicit Balance Text
    if net_balance > 0:
        balance_text = f"Final Status: <strong>You owe {sender_name} ₹{net_balance:,.2f}</strong>"
    elif net_balance < 0:
        balance_text = f"Final Status: <strong>{sender_name} owes you ₹{abs(net_balance):,.2f}</strong>"
    else:
        balance_text = "Final Status: <strong>All settled! No balance remaining.</strong>"

    message["Subject"] = subject
    message["From"] = f"{sender_name} via CoinTrace <{sender_email}>"
    message["To"] = target_email

    html = f"""
    <html>
      <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 30px; color: #1a1a1a; line-height: 1.6; background-color: #f9f9f9;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h2 style="color: #38b000; margin: 0; font-size: 28px;">CoinTrace</h2>
                <p style="color: #666; margin-top: 5px;">Smart Finance Tracking</p>
            </div>
            
            <p style="font-size: 16px;">Hey <strong>{friend_name}</strong>,</p>
            <p style="font-size: 16px;">Greetings from <strong>CoinTrace</strong>!</p>
            
            <div style="margin: 30px 0; padding: 25px; background: #f0fdf4; border-radius: 8px; border-left: 4px solid #38b000;">
                <p style="margin: 0; font-size: 18px; color: #0b1a14;">
                    {action_text} for reason: <strong>{reason if reason else 'General Transaction'}</strong>.
                </p>
                <p style="margin-top: 15px; font-size: 18px; font-weight: bold; color: #1a1a1a;">
                    {balance_text}
                </p>
            </div>
            
            <p style="font-size: 14px; color: #666; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                Thank you,<br>
                <strong>Team CoinTrace</strong>
            </p>
        </div>
      </body>
    </html>
    """
    message.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, target_email, message.as_string())
        return True
    except Exception as e:
        print(f"Error sending notification: {e}")
        return False

@app.route('/api/auth', methods=['POST'])
def auth():
    from werkzeug.security import generate_password_hash, check_password_hash
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    try:
        # Check if user exists (Case Insensitive using LOWER)
        query = 'SELECT * FROM customers WHERE LOWER(name) = LOWER(%s)'
        if db_type == 'sqlite':
            query = query.replace('%s', '?')
            
        user = query_db(query, [username.strip()], one=True)
        
        if not user:
            return jsonify({'error': 'Account not found. Please register.'}), 404
            
        if not user['password'] or not check_password_hash(user['password'], password):
            return jsonify({'error': 'Invalid username or password'}), 401

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        return jsonify({'message': 'Authenticated successfully', 'user': {'id': user['id'], 'name': user['name']}}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/register', methods=['POST'])
def register():
    from werkzeug.security import generate_password_hash
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    try:
        query_check = 'SELECT * FROM customers WHERE LOWER(name) = LOWER(%s)'
        if db_type == 'sqlite':
            query_check = query_check.replace('%s', '?')
            
        user = query_db(query_check, [username.strip()], one=True)
        if user:
            return jsonify({'error': 'Username already exists'}), 400

        cur = db.cursor()
        hashed_password = generate_password_hash(password)
        
        if db_type == 'postgres':
            cur.execute('INSERT INTO customers (name, email, password) VALUES (%s, %s, %s) RETURNING id', (username.strip(), username.strip(), hashed_password))
            user_id = cur.fetchone()[0]
        else:
            cur.execute('INSERT INTO customers (name, email, password) VALUES (?, ?, ?)', (username.strip(), username.strip(), hashed_password))
            user_id = cur.lastrowid
        
        if db_type == 'postgres':
            cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (%s, %s, %s)', (user_id, 'Checking', 0.0))
            cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (%s, %s, %s)', (user_id, 'Savings', 0.0))
        else:
            cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)', (user_id, 'Checking', 0.0))
            cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)', (user_id, 'Savings', 0.0))
            
        db.commit()
        cur.close()
        
        # Re-query user for session
        user = query_db(query_check, [username.strip()], one=True)
        session['user_id'] = user['id']
        session['user_name'] = user['name']

        return jsonify({'message': 'Created successfully', 'user': {'id': user['id'], 'name': user['name']}}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out'}), 200

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    # Get Accounts
    accounts = query_db('SELECT * FROM accounts WHERE customer_id = %s', [user_id])
    accounts_data = [{'id': row['id'], 'type': row['type'], 'balance': row['balance']} for row in accounts]
    
    # Get Transactions (for all user accounts)
    account_ids = [acc['id'] for acc in accounts_data]
    if not account_ids:
        transactions_data = []
    else:
        placeholders = ','.join(['%s'] * len(account_ids))
        transactions = query_db(f'SELECT * FROM transactions WHERE account_id IN ({placeholders}) ORDER BY date DESC', account_ids)
        transactions_data = [{'id': row['id'], 'date': row['date'], 'amount': row['amount'], 'type': row['type'], 'category': row['category'], 'description': row['description']} for row in transactions]

    return jsonify({
        'accounts': accounts_data,
        'transactions': transactions_data
    })

@app.route('/api/transaction', methods=['POST'])
def add_transaction():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    
    # Basic validation
    amount = float(data.get('amount'))
    type = data.get('type') # 'credit' or 'debit'
    category = data.get('category')
    description = data.get('description')
    
    # For simplicity, just pick the first Checking account
    account = query_db('SELECT * FROM accounts WHERE customer_id = %s AND type = %s', [user_id, 'Checking'], one=True)
    if not account:
         # Fallback to any account if Checking doesn't exist
        account = query_db('SELECT * FROM accounts WHERE customer_id = %s', [user_id], one=True)
        
    if not account:
        return jsonify({'error': 'No account found'}), 400
        
    account_id = account['id']
    current_balance = account['balance']
    
    # Update balance
    if type == 'credit':
        new_balance = current_balance + amount
    else:
        new_balance = current_balance - amount
        
    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    try:
        cur = db.cursor()
        
        update_query = 'UPDATE accounts SET balance = %s WHERE id = %s'
        insert_query = 'INSERT INTO transactions (account_id, date, amount, type, category, description) VALUES (%s, %s, %s, %s, %s, %s)'
        if db_type == 'sqlite':
            update_query = update_query.replace('%s', '?')
            insert_query = insert_query.replace('%s', '?')

        cur.execute(update_query, (new_balance, account_id))
        
        # Insert transaction
        import datetime
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(insert_query, (account_id, date_str, amount, type, category, description))
        
        db.commit()
        cur.close()
        return jsonify({'message': 'Transaction added', 'new_balance': new_balance}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Friends / Udhar API ---

@app.route('/api/friends', methods=['GET'])
def get_friends():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    friends = query_db('SELECT * FROM friends WHERE customer_id = %s ORDER BY name', [user_id])
    result = []
    for f in friends:
        # Optimized: Use SQL SUM for balance
        net_row = query_db('''
            SELECT SUM(CASE WHEN type = 'lent' THEN amount ELSE -amount END) as net
            FROM friend_transactions 
            WHERE friend_id = %s AND customer_id = %s AND settled = 0
        ''', [f['id'], user_id], one=True)
        net = net_row['net'] if net_row and net_row['net'] is not None else 0.0
        
        result.append({'id': f['id'], 'name': f['name'], 'phone': f['phone'], 'email': f.get('email', ''), 'net': round(net, 2)})
    return jsonify(result)

@app.route('/api/friends', methods=['POST'])
def add_friend():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    data = request.get_json()
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    try:
        cur = db.cursor()
        if db_type == 'postgres':
            cur.execute('INSERT INTO friends (customer_id, name, phone, email) VALUES (%s, %s, %s, %s) RETURNING id', (user_id, name, phone, email))
            friend_id = cur.fetchone()[0]
        else:
            cur.execute('INSERT INTO friends (customer_id, name, phone, email) VALUES (?, ?, ?, ?)', (user_id, name, phone, email))
            friend_id = cur.lastrowid
        db.commit()
        cur.close()
        return jsonify({'id': friend_id, 'name': name, 'phone': phone, 'email': email, 'net': 0.0}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/friends/<int:friend_id>/transactions', methods=['GET'])
def get_friend_transactions(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    txns = query_db('SELECT * FROM friend_transactions WHERE friend_id = %s AND customer_id = %s ORDER BY date DESC', [friend_id, user_id])
    result = [{'id': t['id'], 'amount': t['amount'], 'type': t['type'], 'note': t['note'], 'date': t['date'], 'settled': bool(t['settled'])} for t in txns]
    return jsonify(result)

@app.route('/api/friends/<int:friend_id>/transactions', methods=['POST'])
def add_friend_transaction(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    data = request.get_json()
    amount = float(data.get('amount', 0))
    txn_type = data.get('type')  # 'lent' or 'borrowed'
    note = data.get('note', '')
    if amount <= 0 or txn_type not in ('lent', 'borrowed'):
        return jsonify({'error': 'Invalid amount or type'}), 400
    import datetime
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    try:
        # Get friend info first for email
        friend = query_db('SELECT * FROM friends WHERE id = %s', [friend_id], one=True)
        if not friend:
            return jsonify({'error': 'Friend not found'}), 404
            
        cur = db.cursor()
        insert_query = 'INSERT INTO friend_transactions (customer_id, friend_id, amount, type, note, date) VALUES (%s, %s, %s, %s, %s, %s)'
        if db_type == 'sqlite':
            insert_query = insert_query.replace('%s', '?')
            
        cur.execute(insert_query, (user_id, friend_id, amount, txn_type, note, date_str))
        db.commit()
        cur.close()
        
        # Calculate new net balance for notification (Optimized)
        net_row = query_db('''
            SELECT SUM(CASE WHEN type = 'lent' THEN amount ELSE -amount END) as net
            FROM friend_transactions 
            WHERE friend_id = %s AND customer_id = %s AND settled = 0
        ''', [friend_id, user_id], one=True)
        net = net_row['net'] if net_row and net_row['net'] is not None else 0.0
            
        # Send notification if email exists (Async)
        user_name = session.get('user_name', 'User')
        if friend['email']:
            threading.Thread(target=send_transaction_notification, 
                             args=(friend['email'], friend['name'], user_name, amount, txn_type, net, note)).start()
            
        return jsonify({'message': 'Transaction added'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/friends/transactions/<int:txn_id>/settle', methods=['POST'])
def settle_friend_transaction(txn_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    try:
        # Get transaction and friend info for notification
        txn = query_db('SELECT * FROM friend_transactions WHERE id = %s', [txn_id], one=True)
        if not txn:
            return jsonify({'error': 'Transaction not found'}), 404
        
        friend = query_db('SELECT * FROM friends WHERE id = %s', [txn['friend_id']], one=True)
        
        cur = db.cursor()
        query = 'UPDATE friend_transactions SET settled = 1 WHERE id = %s AND customer_id = %s'
        if db_type == 'sqlite':
            query = query.replace('%s', '?')
        cur.execute(query, (txn_id, user_id))
        db.commit()
        cur.close()
        
        # Calculate new net balance (Optimized)
        net_row = query_db('''
            SELECT SUM(CASE WHEN type = 'lent' THEN amount ELSE -amount END) as net
            FROM friend_transactions 
            WHERE friend_id = %s AND customer_id = %s AND settled = 0
        ''', [txn['friend_id'], user_id], one=True)
        net = net_row['net'] if net_row and net_row['net'] is not None else 0.0
            
        # Send settlement notification (Async)
        user_name = session.get('user_name', 'User')
        if friend and friend['email']:
            threading.Thread(target=send_transaction_notification, 
                             args=(friend['email'], friend['name'], user_name, txn['amount'], f"Settled ({txn['type']})", net, "Account Settlement")).start()
            
        return jsonify({'message': 'Settled'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/friends/<int:friend_id>', methods=['DELETE'])
def delete_friend(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    db = get_db()
    db_type = getattr(g, 'db_type', 'sqlite')
    try:
        cur = db.cursor()
        del_txns = 'DELETE FROM friend_transactions WHERE friend_id = %s AND customer_id = %s'
        del_friend = 'DELETE FROM friends WHERE id = %s AND customer_id = %s'
        if db_type == 'sqlite':
            del_txns = del_txns.replace('%s', '?')
            del_friend = del_friend.replace('%s', '?')
            
        # Delete related transactions first
        cur.execute(del_txns, (friend_id, user_id))
        # Delete the friend
        cur.execute(del_friend, (friend_id, user_id))
        db.commit()
        cur.close()
        return jsonify({'message': 'Friend removed'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Initialize database tables unconditionally so Vercel's serverless environment picks it up
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
