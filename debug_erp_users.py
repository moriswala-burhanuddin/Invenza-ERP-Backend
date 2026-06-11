import sqlite3
import json
import os

db_path = 'd:/paid-erp/invenza-erp/invenza-website/backend/db.sqlite3'
if not os.path.exists(db_path):
    print(f"Error: DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
try:
    cur.execute("SELECT * FROM erp_core_erpuser")
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    data = [dict(zip(columns, row)) for row in rows]
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
