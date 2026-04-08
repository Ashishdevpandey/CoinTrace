import os
import sqlite3
from flask import Flask, render_template, request, jsonify, g, session
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key') # Change this in production
CORS(app)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db_path = app.config.get('DATABASE', 'banking.db')
        db = g._database = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def init_db():
    with app.app_context():
        db = get_db()
        # Create tables if they don't exist
        db.execute('CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL, password TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, type TEXT, balance REAL DEFAULT 0.0)')
        db.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, date TEXT, amount REAL, type TEXT, category TEXT, description TEXT)')
        # Friends / Udhar tables
        db.execute('''CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS friend_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            note TEXT,
            date TEXT NOT NULL,
            settled INTEGER DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customers(id),
            FOREIGN KEY (friend_id) REFERENCES friends(id)
        )''')
        db.commit()

@app.route('/')
def index():
    return render_template('index.html')

# --- API Endpoints ---

@app.route('/api/auth', methods=['POST'])
def auth():
    from werkzeug.security import generate_password_hash, check_password_hash
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    db = get_db()
    try:
        # Check if user exists (Case Insensitive)
        user = query_db('SELECT * FROM customers WHERE name = ? COLLATE NOCASE', [username.strip()], one=True)
        
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
    try:
        user = query_db('SELECT * FROM customers WHERE name = ? COLLATE NOCASE', [username.strip()], one=True)
        if user:
            return jsonify({'error': 'Username already exists'}), 400

        cur = db.cursor()
        hashed_password = generate_password_hash(password)
        cur.execute('INSERT INTO customers (name, email, password) VALUES (?, ?, ?)', (username.strip(), username.strip(), hashed_password))
        user_id = cur.lastrowid
        
        cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)', (user_id, 'Checking', 0.0))
        cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)', (user_id, 'Savings', 0.0))
        db.commit()
        
        user = query_db('SELECT * FROM customers WHERE id = ?', [user_id], one=True)
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
    accounts = query_db('SELECT * FROM accounts WHERE customer_id = ?', [user_id])
    accounts_data = [{'id': row['id'], 'type': row['type'], 'balance': row['balance']} for row in accounts]
    
    # Get Transactions (for all user accounts)
    # This is a simplified query. Ideally we join tables.
    # First get account IDs
    account_ids = [acc['id'] for acc in accounts_data]
    if not account_ids:
        transactions_data = []
    else:
        placeholders = ','.join('?' * len(account_ids))
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
    account = query_db('SELECT * FROM accounts WHERE customer_id = ? AND type = ?', [user_id, 'Checking'], one=True)
    if not account:
         # Fallback to any account if Checking doesn't exist
        account = query_db('SELECT * FROM accounts WHERE customer_id = ?', [user_id], one=True)
        
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
    try:
        cur = db.cursor()
        cur.execute('UPDATE accounts SET balance = ? WHERE id = ?', (new_balance, account_id))
        
        # Insert transaction
        import datetime
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute('INSERT INTO transactions (account_id, date, amount, type, category, description) VALUES (?, ?, ?, ?, ?, ?)',
                    (account_id, date_str, amount, type, category, description))
        
        db.commit()
        return jsonify({'message': 'Transaction added', 'new_balance': new_balance}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Friends / Udhar API ---

@app.route('/api/friends', methods=['GET'])
def get_friends():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    friends = query_db('SELECT * FROM friends WHERE customer_id = ? ORDER BY name', [user_id])
    result = []
    for f in friends:
        # Calculate net balance for this friend
        txns = query_db('SELECT * FROM friend_transactions WHERE friend_id = ? AND customer_id = ? AND settled = 0', [f['id'], user_id])
        net = 0.0
        for t in txns:
            if t['type'] == 'lent':    # I gave money → they owe me (positive = they owe me)
                net += t['amount']
            else:                       # borrowed → I owe them (negative = I owe them)
                net -= t['amount']
        result.append({'id': f['id'], 'name': f['name'], 'phone': f['phone'], 'net': round(net, 2)})
    return jsonify(result)

@app.route('/api/friends', methods=['POST'])
def add_friend():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    data = request.get_json()
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute('INSERT INTO friends (customer_id, name, phone) VALUES (?, ?, ?)', (user_id, name, phone))
        db.commit()
        return jsonify({'id': cur.lastrowid, 'name': name, 'phone': phone, 'net': 0.0}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/friends/<int:friend_id>/transactions', methods=['GET'])
def get_friend_transactions(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    txns = query_db('SELECT * FROM friend_transactions WHERE friend_id = ? AND customer_id = ? ORDER BY date DESC', [friend_id, user_id])
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
    try:
        cur = db.cursor()
        cur.execute('INSERT INTO friend_transactions (customer_id, friend_id, amount, type, note, date) VALUES (?, ?, ?, ?, ?, ?)',
                    (user_id, friend_id, amount, txn_type, note, date_str))
        db.commit()
        return jsonify({'message': 'Transaction added'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/friends/transactions/<int:txn_id>/settle', methods=['POST'])
def settle_friend_transaction(txn_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    db = get_db()
    try:
        db.execute('UPDATE friend_transactions SET settled = 1 WHERE id = ? AND customer_id = ?', (txn_id, user_id))
        db.commit()
        return jsonify({'message': 'Settled'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/friends/<int:friend_id>', methods=['DELETE'])
def delete_friend(friend_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    db = get_db()
    try:
        cur = db.cursor()
        # Delete related transactions first
        cur.execute('DELETE FROM friend_transactions WHERE friend_id = ? AND customer_id = ?', (friend_id, user_id))
        # Delete the friend
        cur.execute('DELETE FROM friends WHERE id = ? AND customer_id = ?', (friend_id, user_id))
        db.commit()
        return jsonify({'message': 'Friend removed'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
