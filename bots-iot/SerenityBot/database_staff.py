# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime

DB_NAME = "staff_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Tabla consolidada para staff
    c.execute('''CREATE TABLE IF NOT EXISTS staff 
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  last_active TEXT, 
                  absence_until TEXT,
                  apodo TEXT)''')
    conn.commit()
    conn.close()
    print("✅ DB Staff inicializada.")

def update_activity(user_id, username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""
        INSERT INTO staff (user_id, username, last_active) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_active = excluded.last_active, username = excluded.username
    """, (user_id, username, now))
    conn.commit()
    conn.close()

def set_absence(user_id, date_iso):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE staff SET absence_until = ? WHERE user_id = ?", (date_iso, user_id))
    conn.commit()
    conn.close()

def get_absence(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT absence_until FROM staff WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def set_apodo(user_id, apodo):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE staff SET apodo = ? WHERE user_id = ?", (apodo, user_id))
    conn.commit()
    conn.close()

def get_apodo(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT apodo FROM staff WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None
