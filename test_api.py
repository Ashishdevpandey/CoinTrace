import unittest
import json
import os
from app import app, get_db

class CoinTraceApiTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, app.config['DATABASE'] = '/tmp/test_banking.db', '/tmp/test_banking.db'
        app.config['TESTING'] = True
        self.app = app.test_client()
        
        # Initialize DB
        with app.app_context():
            db = get_db()
            # Create tables manually for test
            db.execute('CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, type TEXT, balance REAL DEFAULT 0.0)')
            db.execute('CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, date TEXT, amount REAL, type TEXT, category TEXT, description TEXT)')
            db.commit()

    def tearDown(self):
        try:
            os.unlink(app.config['DATABASE'])
        except OSError:
            pass

    def auth(self, username):
        return self.app.post('/api/auth', data=json.dumps(dict(
            username=username
        )), content_type='application/json')

    def test_auth_flow(self):
        # Test new user creation
        rv = self.auth('testuser')
        self.assertEqual(rv.status_code, 200)
        data = json.loads(rv.data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['name'], 'testuser')
        user_id = data['user']['id']
        
        # Test existing user login
        rv = self.auth('testuser')
        self.assertEqual(rv.status_code, 200)
        data = json.loads(rv.data)
        self.assertEqual(data['user']['id'], user_id)

    def test_dashboard_access(self):
        # Try without login
        rv = self.app.get('/api/dashboard')
        self.assertEqual(rv.status_code, 401)
        
        # Login first
        self.auth('testuser')
        
        rv = self.app.get('/api/dashboard')
        self.assertEqual(rv.status_code, 200)

if __name__ == '__main__':
    unittest.main()
