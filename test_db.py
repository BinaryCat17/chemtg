import sqlite3

db_path = 'data/reestr.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

import re
def regexp(expr, item):
    if item is None: return False
    reg = re.compile(expr, re.IGNORECASE)
    return reg.search(str(item)) is not None

conn.create_function("REGEXP", 2, regexp)
cur = conn.cursor()

# Query with just "протравливание"
cur.execute("""
    SELECT COUNT(*) as cnt 
    FROM pestitsidy_primeneniya pp 
    WHERE (pp.kultura LIKE '%лен масличн%' OR pp.kultura LIKE '%лен-кудряш%') 
    AND pp.sposob LIKE '%протравливание%'
""")
print("Count with LIKE '%протравливание%':", cur.fetchone()['cnt'])

# Query with "обработка семян"
cur.execute("""
    SELECT COUNT(*) as cnt 
    FROM pestitsidy_primeneniya pp 
    WHERE (pp.kultura LIKE '%лен масличн%' OR pp.kultura LIKE '%лен-кудряш%') 
    AND pp.sposob LIKE '%обработка семян%'
""")
print("Count with LIKE '%обработка семян%':", cur.fetchone()['cnt'])

# Check combinations for "лен" general
cur.execute("""
    SELECT pp.sposob, pp.kultura, p.naimenovanie 
    FROM pestitsidy_primeneniya pp 
    JOIN pestitsidy p ON p.nomer_reg = pp.nomer_reg
    WHERE pp.kultura REGEXP 'лен'
    AND pp.sposob REGEXP 'протравливан|обработка семян'
""")
rows = cur.fetchall()
print("\nAll seed treatments for лен:")
for r in rows:
    print(f"{r['naimenovanie']} | {r['kultura']} | {r['sposob']}")
