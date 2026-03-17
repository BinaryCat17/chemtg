import sqlite3

db_path = 'data/reestr.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cur = conn.cursor()
cur.execute("SELECT 'Протравливание семян' LIKE '%протравливание%' as is_match")
print("Capital П vs lower п:", cur.fetchone()['is_match'])

cur.execute("SELECT 'Обработка семян' LIKE '%обработка семян%' as is_match")
print("Capital О vs lower о:", cur.fetchone()['is_match'])

cur.execute("SELECT 'Лен масличный' LIKE '%масличн%' as is_match")
print("масличн:", cur.fetchone()['is_match'])

cur.execute("SELECT 'Лен масличный' LIKE '%лен масличн%' as is_match")
print("лен масличн:", cur.fetchone()['is_match'])
