import sqlite3

def migrate():
    try:
        conn = sqlite3.connect('banking.db')
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("PRAGMA table_info(customers)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'password' not in columns:
            print("Adding password column to customers table...")
            cursor.execute("ALTER TABLE customers ADD COLUMN password TEXT")
            conn.commit()
            print("Migration successful.")
        else:
            print("Password column already exists.")
            
        conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
