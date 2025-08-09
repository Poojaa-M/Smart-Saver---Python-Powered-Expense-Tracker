import sqlite3

DB_NAME = "expense_tracker.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Create users table (no password for now)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        )
    ''')

    # Create expenses table
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT NOT NULL, -- income or expense
            category TEXT,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()

def create_user(username, name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, name) VALUES (?, ?)", (username, name))
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Username already exists
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user_id = c.fetchone()[0]
    conn.close()
    return user_id

def add_transaction(user_id, type_, category, amount, date):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO expenses (user_id, type, category, amount, date) VALUES (?, ?, ?, ?, ?)",
              (user_id, type_, category, amount, date))
    conn.commit()
    conn.close()

def get_transactions(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT type, category, amount, date FROM expenses WHERE user_id = ?", (user_id,))
    data = c.fetchall()
    conn.close()
    return data

def get_family_totals():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT type, SUM(amount) 
        FROM expenses
        GROUP BY type
    """)
    totals = dict(c.fetchall())
    conn.close()
    return totals
