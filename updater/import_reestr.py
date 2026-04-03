import sqlite3
import json
import os
import zipfile
import requests
import sys
import schedule
import time
from datetime import datetime
from lxml import etree

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Ссылки на актуальные данные
AGRO_URL = "http://opendata.mcx.ru/opendata/7708075454-agrokhimikaty/data-20260303-0-structure-20250926.xml"
PEST_URL = "http://opendata.mcx.ru/opendata/7708075454-pestitsidy/data-20260303-0-structure-20250925.xml"

DB_PATH = os.getenv('SQLITE_DB_PATH', 'reestr.db')
DATA_DIR = os.getenv('DATA_DIR', 'data')

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def download_and_extract(url, target_name):
    ensure_data_dir()
    zip_path = os.path.join(DATA_DIR, target_name + '.zip')
    xml_path = os.path.join(DATA_DIR, target_name + '.xml')
    print(f"📥 Скачиваю {target_name}...")
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=180, proxies={"http": None, "https": None})
        r.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in r.iter_content(8192): f.write(chunk)
        with zipfile.ZipFile(zip_path) as z:
            xml_inside = [f for f in z.namelist() if f.lower().endswith('.xml')][0]
            z.extract(xml_inside, DATA_DIR)
            extracted_path = os.path.join(DATA_DIR, xml_inside)
            if os.path.exists(xml_path): os.remove(xml_path)
            os.rename(extracted_path, xml_path)
        os.remove(zip_path)
        print(f"✅ Распаковано → {xml_path}")
        return xml_path
    except Exception as e:
        print(f"❌ Ошибка при скачивании {target_name}: {e}")
        return None

def parse_xml_safe(filename):
    with open(filename, 'rb') as f: data = f.read()
    if data.startswith(b'\xef\xbb\xbf'): data = data[3:]
    start = data.find(b'<')
    if start > 0: data = data[start:]
    return etree.fromstring(data, parser=etree.XMLParser(recover=True, huge_tree=True))

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Таблицы агрохимикатов
    cur.execute("DROP TABLE IF EXISTS agrokhimikaty;")
    cur.execute("""CREATE TABLE agrokhimikaty (
        rn TEXT PRIMARY KEY, preparat TEXT, registrant TEXT, data_reg TEXT,
        srok_reg TEXT, status TEXT, group_name TEXT, imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );""")

    cur.execute("DROP TABLE IF EXISTS agrokhimikaty_primeneniya;")
    cur.execute("""CREATE TABLE agrokhimikaty_primeneniya (
        id INTEGER PRIMARY KEY AUTOINCREMENT, rn TEXT,
        marka TEXT, oblast TEXT, doza TEXT, kultura TEXT, vremya TEXT, osobennosti TEXT,
        FOREIGN KEY (rn) REFERENCES agrokhimikaty(rn)
    );""")

    # Таблицы пестицидов
    cur.execute("DROP TABLE IF EXISTS pestitsidy;")
    cur.execute("""CREATE TABLE pestitsidy (
        nomer_reg TEXT PRIMARY KEY, naimenovanie TEXT, preparativnaya_forma TEXT,
        deystvuyushchee_veshchestvo TEXT, registrant TEXT, klass_opasnosti TEXT,
        data_reg TEXT, srok_reg TEXT, status TEXT, imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );""")

    cur.execute("DROP TABLE IF EXISTS pestitsidy_primeneniya;")
    cur.execute("""CREATE TABLE pestitsidy_primeneniya (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nomer_reg TEXT,
        vrednyy_obekt TEXT, kultura TEXT, sposob TEXT, srok_ozhidaniya TEXT,
        vyhod TEXT, norma TEXT, avia TEXT, osobennosti TEXT,
        FOREIGN KEY (nomer_reg) REFERENCES pestitsidy(nomer_reg)
    );""")

    conn.commit()
    conn.close()

def import_agro(xml_path):
    if not xml_path: return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    root = parse_xml_safe(xml_path)
    
    for item in root.findall('.//agrokhimikaty'):
        rn = item.findtext('rn')
        if not rn: continue
        
        cur.execute("""INSERT OR IGNORE INTO agrokhimikaty 
            (rn, preparat, registrant, data_reg, srok_reg, status, group_name)
            VALUES (?,?,?,?,?,?,?);""",
            (rn, item.findtext('preparat'), item.findtext('registrant'),
             item.findtext('Data_gosudarstvennoy_registracii'),
             item.findtext('srok_registratsii_po'), item.findtext('Status_gosudarstvennoy_registracii'),
             item.findtext('.//fulldataset1//Group')))

        for app in item.findall('.//fulldataset2/item'):
            cur.execute("""INSERT INTO agrokhimikaty_primeneniya 
                (rn, marka, oblast, doza, kultura, vremya, osobennosti)
                VALUES (?,?,?,?,?,?,?);""",
                (rn, app.findtext('marka'), app.findtext('oblast'),
                 app.findtext('Doza_primeneniya'), app.findtext('Kultura_obrabatyvaemyy_obekt'),
                 app.findtext('Vremya_primeneniya'), app.findtext('Osobennosti_primeneniya')))
    
    conn.commit()
    conn.close()
    print("✅ Агрохимикаты загружены")

def import_pest(xml_path):
    if not xml_path: return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    root = parse_xml_safe(xml_path)
    
    for item in root.findall('.//items'):
        nomer_elem = item.find('Nomer_gosudarstvennoy_registracii/item')
        nomer = nomer_elem.text.strip() if nomer_elem is not None and nomer_elem.text else ''
        if not nomer: continue

        dv = [{"veshchestvo": ds.findtext('Deystvuyushee_veshestvo'), "koncentraciya": ds.findtext('Koncentraciya')} 
              for ds in item.findall('.//fulldataset1/item')]

        cur.execute("""INSERT OR IGNORE INTO pestitsidy 
            (nomer_reg, naimenovanie, preparativnaya_forma, deystvuyushchee_veshchestvo, registrant, klass_opasnosti, data_reg, srok_reg, status)
            VALUES (?,?,?,?,?,?,?,?,?);""",
            (nomer, item.findtext('Naimenovanie/item'), item.findtext('Preparativnaya_forma/item'),
             json.dumps(dv), item.findtext('Registrant/item'), item.findtext('Klass_opasnosti/item'),
             item.findtext('Data_gosudarstvennoy_registracii/item'), item.findtext('Srok_registracii_Po/item'),
             item.findtext('Status_gosudarstvennoy_registracii/item')))

        for app in item.findall('.//fulldataset2/item'):
            cur.execute("""INSERT INTO pestitsidy_primeneniya 
                (nomer_reg, vrednyy_obekt, kultura, sposob, srok_ozhidaniya, vyhod, norma, avia, osobennosti)
                VALUES (?,?,?,?,?,?,?,?,?);""",
                (nomer, app.findtext('Vrednyy_obekt_naznachenie'), app.findtext('Kultura_obrabatyvaemyy_obekt'),
                 app.findtext('Sposob_i_vremya_obrabotki'), app.findtext('Srok_ozhidaniya_kratnost_obrabotok'),
                 app.findtext('Sroki_vyhoda_dlya_ruchnyh_mehanizirovannyh_rabot'),
                 app.findtext('Norma_primeneniya'), app.findtext('Razreshenie_avia_obrabotok'),
                 app.findtext('Osobennosti_primeneniya')))
    
    conn.commit()
    conn.close()
    print("✅ Пестициды загружены")

def run_import():
    try:
        print(f"🚀 [START] Обновление реестра {datetime.now()}")
        init_db()
        agro_xml = download_and_extract(AGRO_URL, "agrokhimikaty")
        pest_xml = download_and_extract(PEST_URL, "pestitsidy")
        import_agro(agro_xml)
        import_pest(pest_xml)
        print(f"🎉 [SUCCESS] Реестр обновлен! {datetime.now()}")
    except Exception as e:
        print(f"❌ [ERROR] Ошибка при обновлении: {e}")

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_import()
    else:
        print("🕒 Планировщик запущен. Обновление ежедневно в 00:00.")
        schedule.every().day.at("00:00").do(run_import)
        while True:
            schedule.run_pending()
            time.sleep(60)
