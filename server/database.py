import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'entertainment.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS cache (
            key   TEXT PRIMARY KEY,
            data  TEXT NOT NULL,
            ts    INTEGER NOT NULL
        );
    ''')
    conn.commit()
    conn.close()
