import sqlite3
import os
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import random

app = Flask(__name__)
CORS(app) # Enable CORS for all routes
DB_NAME = "banking.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            type TEXT NOT NULL,
            balance REAL DEFAULT 0.0,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL, -- 'credit' or 'debit'
            category TEXT,
            description TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    ''')
    
    # Seed Data if empty
    cursor.execute('SELECT count(*) FROM customers')
    if cursor.fetchone()[0] == 0:
        print("Seeding database...")
        cursor.execute("INSERT INTO customers (name, email) VALUES (?, ?)", ("ASHISH PANDEY", "ashisdvpandey@gmail.com"))
        customer_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)", (customer_id, "Checking", 5000.00))
        account_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO accounts (customer_id, type, balance) VALUES (?, ?, ?)", (customer_id, "Savings", 12000.00))
        
        # Seed Transactions
        categories = ['Food', 'Transport', 'Utilities', 'Entertainment', 'Salary', 'Shopping']
        for _ in range(50):
            t_type = 'debit' if random.random() > 0.3 else 'credit'
            amount = round(random.uniform(10.0, 500.0), 2)
            if t_type == 'credit':
                amount = round(random.uniform(1000.0, 3000.0), 2)
                category = 'Salary'
            else:
                category = random.choice([c for c in categories if c != 'Salary'])
                
            # Random date within last 6 months
            days_ago = random.randint(0, 180)
            date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute('''
                INSERT INTO transactions (account_id, date, amount, type, category, description)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (account_id, date, amount, t_type, category, f"{t_type} transaction for {category}"))
            
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/summary')
def get_summary():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total Balance
    cursor.execute("SELECT SUM(balance) FROM accounts")
    total_balance = cursor.fetchone()[0] or 0
    
    # Spending by Category (Last 30 days usually, but here all time for simplicity)
    cursor.execute('''
        SELECT category, SUM(amount) as total 
        FROM transactions 
        WHERE type = 'debit' 
        GROUP BY category
    ''')
    spending_by_category = [dict(row) for row in cursor.fetchall()]
    
    # Monthly Income vs Expense
    cursor.execute('''
        SELECT 
            strftime('%Y-%m', date) as month,
            SUM(CASE WHEN type='credit' THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN type='debit' THEN amount ELSE 0 END) as expense
        FROM transactions
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6
    ''')
    monthly_stats = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({
        'total_balance': total_balance,
        'spending_by_category': spending_by_category,
        'monthly_stats': monthly_stats
    })

@app.route('/api/transactions')
def get_transactions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM transactions ORDER BY date DESC LIMIT 50')
    transactions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(transactions)

@app.route('/api/transaction', methods=['POST'])
def add_transaction():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Simplified: Assuming single user/account for demo
    cursor.execute("SELECT id FROM accounts LIMIT 1")
    account_id = cursor.fetchone()[0]
    
    cursor.execute('''
        INSERT INTO transactions (account_id, date, amount, type, category, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (account_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data['amount'], data['type'], data['category'], data['description']))
    
    # Update Account Balance
    if data['type'] == 'credit':
        cursor.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (data['amount'], account_id))
    else:
        cursor.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (data['amount'], account_id))
        
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
