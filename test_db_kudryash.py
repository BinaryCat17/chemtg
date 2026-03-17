import sqlite3

db_path = 'data/reestr.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cur = conn.cursor()
# Посмотрим, как в базе записан лен-кудряш и масличный
cur.execute("SELECT DISTINCT kultura FROM pestitsidy_primeneniya WHERE kultura LIKE '%кудряш%' OR kultura LIKE '%масличн%'")
rows = cur.fetchall()

print("Культуры со словами 'кудряш' или 'масличн':")
for r in rows:
    print(r['kultura'])
