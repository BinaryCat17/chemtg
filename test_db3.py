import sqlite3
import json

db_path = 'data/reestr.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT deystvuyushchee_veshchestvo FROM pestitsidy WHERE deystvuyushchee_veshchestvo IS NOT NULL LIMIT 5")
rows = cur.fetchall()

for r in rows:
    print(r[0])
