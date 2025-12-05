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

@app.route('/')
def index():
    return render_template('index.html')

# --- API Endpoints ---

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.get_json()
    username = data.get('username')

    if not username:
        return jsonify({'error': 'Username is required'}), 400

    db = get_db()
    try:
        # Check if user exists
        user = query_db('SELECT * FROM customers WHERE name = ?', [username], one=True)
        
        if not user:
            # Create new user
            cur = db.cursor()
            # We use username as email for simplicity in this schema, or just leave email empty/dummy if schema requires it.
            # The schema has email NOT NULL. Let's use username as email or adjust schema.
            # Given the previous schema had email UNIQUE, let's assume username is unique enough for this request.
            # We'll just store username in 'name' and 'email' to satisfy constraints, or modify schema.
            # Let's just use username for both for now to be safe with existing schema.
            cur.execute('INSERT INTO customers (name, email) VALUES (?, ?)', (username, username))
            user_id = cur.lastrowid
            
            # Create default accounts
            cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)', (user_id, 'Checking', 0.0))
            cur.execute('INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)', (user_id, 'Savings', 0.0))
            db.commit()
            
            # Fetch the newly created user
            user = query_db('SELECT * FROM customers WHERE id = ?', [user_id], one=True)

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        return jsonify({'message': 'Authenticated successfully', 'user': {'id': user['id'], 'name': user['name']}}), 200

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
