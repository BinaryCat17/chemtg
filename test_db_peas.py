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
# Ищем все протравители для гороха, где упомянут пероноспороз или ЛМР
query = """
    SELECT p.naimenovanie, pp.vrednyy_obekt, pp.sposob, pp.norma
    FROM pestitsidy p
    JOIN pestitsidy_primeneniya pp ON p.nomer_reg = pp.nomer_reg
    WHERE pp.kultura REGEXP 'горох'
      AND pp.sposob REGEXP 'протравливан|обработк.*семян'
      AND pp.vrednyy_obekt REGEXP 'пероноспор|ложная мучнистая роса'
      AND p.status = 'Действует'
"""
cur.execute(query)
rows = cur.fetchall()

print(f"Найдено препаратов: {len(rows)}")
for r in rows:
    print(f"Препарат: {r['naimenovanie']}, Объект: {r['vrednyy_obekt']}")

# Теперь посмотрим вообще все болезни, от которых протравливают горох (какие там есть)
print("\n--- ВСЕ болезни для протравливания гороха ---")
query_all = """
    SELECT DISTINCT pp.vrednyy_obekt
    FROM pestitsidy p
    JOIN pestitsidy_primeneniya pp ON p.nomer_reg = pp.nomer_reg
    WHERE pp.kultura REGEXP 'горох'
      AND pp.sposob REGEXP 'протравливан|обработк.*семян'
      AND p.status = 'Действует'
"""
cur.execute(query_all)
rows_all = cur.fetchall()
for r in rows_all:
    print(r['vrednyy_obekt'])
