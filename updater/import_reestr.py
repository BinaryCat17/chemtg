import requests, psycopg2, json, os, zipfile
from datetime import datetime
from lxml import etree

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

AGRO_URL = "http://opendata.mcx.ru/opendata/7708075454-agrokhimikaty/data-20260303-0-structure-20250926.xml"
PEST_URL = "http://opendata.mcx.ru/opendata/7708075454-pestitsidy/data-20260303-0-structure-20250925.xml"

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'postgres'),
    'port': '5432',
    'dbname': 'reestr',
    'user': 'postgres',
    'password': os.getenv('POSTGRES_PASSWORD', 'ChangeMe2026!!')
}

def download_and_extract(url, target_name):
    zip_path = target_name + '.zip'
    xml_path = target_name + '.xml'
    print(f"📥 Скачиваю {target_name}...")
    r = requests.get(url, headers=headers, stream=True, timeout=180)
    r.raise_for_status()
    with open(zip_path, 'wb') as f:
        for chunk in r.iter_content(8192): f.write(chunk)
    with zipfile.ZipFile(zip_path) as z:
        xml_inside = [f for f in z.namelist() if f.lower().endswith('.xml')][0]
        z.extract(xml_inside)
        os.rename(xml_inside, xml_path)
    os.remove(zip_path)
    print(f"✅ Распаковано → {xml_path}")
    return xml_path

def parse_xml_safe(filename):
    with open(filename, 'rb') as f: data = f.read()
    if data.startswith(b'\xef\xbb\xbf'): data = data[3:]
    start = data.find(b'<')
    if start > 0: data = data[start:]
    return etree.fromstring(data, parser=etree.XMLParser(recover=True, huge_tree=True))

def import_agro(xml_path):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS reestr;")

    cur.execute("DROP TABLE IF EXISTS reestr.agrokhimikaty CASCADE;")
    cur.execute("""CREATE TABLE reestr.agrokhimikaty (
        rn TEXT PRIMARY KEY, preparat TEXT, registrant TEXT, data_reg TEXT,
        srok_reg TEXT, status TEXT, group_name TEXT, imported_at TIMESTAMP DEFAULT NOW()
    );""")

    cur.execute("DROP TABLE IF EXISTS reestr.agrokhimikaty_primeneniya;")
    cur.execute("""CREATE TABLE reestr.agrokhimikaty_primeneniya (
        id SERIAL PRIMARY KEY, rn TEXT REFERENCES reestr.agrokhimikaty(rn),
        marka TEXT, oblast TEXT, doza TEXT, kultura TEXT, vremya TEXT, osobennosti TEXT
    );""")

    root = parse_xml_safe(xml_path)
    for item in root.findall('.//agrokhimikaty'):
        rn = item.findtext('rn')
        if not rn: continue
        cur.execute("""INSERT INTO reestr.agrokhimikaty (rn, preparat, registrant, data_reg, srok_reg, status, group_name)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (rn) DO NOTHING;""",
            (rn, item.findtext('preparat'), item.findtext('registrant'),
             item.findtext('Data_gosudarstvennoy_registracii'),
             item.findtext('srok_registratsii_po'), item.findtext('Status_gosudarstvennoy_registracii'),
             item.findtext('.//fulldataset1//Group')))

        for app in item.findall('.//fulldataset2/item'):
            cur.execute("""INSERT INTO reestr.agrokhimikaty_primeneniya 
                (rn, marka, oblast, doza, kultura, vremya, osobennosti)
                VALUES (%s,%s,%s,%s,%s,%s,%s);""",
                (rn, app.findtext('marka'), app.findtext('oblast'),
                 app.findtext('Doza_primeneniya'), app.findtext('Kultura_obrabatyvaemyy_obekt'),
                 app.findtext('Vremya_primeneniya'), app.findtext('Osobennosti_primeneniya')))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Агрохимикаты + применения загружены")

def import_pest(xml_path):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS reestr;")

    cur.execute("DROP TABLE IF EXISTS reestr.pestitsidy CASCADE;")
    cur.execute("""CREATE TABLE reestr.pestitsidy (
        nomer_reg TEXT PRIMARY KEY, naimenovanie TEXT, preparativnaya_forma TEXT,
        deystvuyushchee_veshchestvo JSONB, registrant TEXT, klass_opasnosti TEXT,
        data_reg TEXT, srok_reg TEXT, status TEXT, imported_at TIMESTAMP DEFAULT NOW()
    );""")

    cur.execute("DROP TABLE IF EXISTS reestr.pestitsidy_primeneniya;")
    cur.execute("""CREATE TABLE reestr.pestitsidy_primeneniya (
        id SERIAL PRIMARY KEY, nomer_reg TEXT REFERENCES reestr.pestitsidy(nomer_reg),
        vrednyy_obekt TEXT, kultura TEXT, sposob TEXT, srok_ozhidaniya TEXT,
        vyhod TEXT, norma TEXT, avia TEXT, osobennosti TEXT
    );""")

    root = parse_xml_safe(xml_path)
    for item in root.findall('.//items'):
        nomer_elem = item.find('Nomer_gosudarstvennoy_registracii/item')
        nomer = nomer_elem.text.strip() if nomer_elem is not None and nomer_elem.text else ''
        if not nomer: continue

        dv = [{"veshchestvo": ds.findtext('Deystvuyushee_veshestvo'), "koncentraciya": ds.findtext('Koncentraciya')} 
              for ds in item.findall('.//fulldataset1/item')]

        cur.execute("""INSERT INTO reestr.pestitsidy 
            (nomer_reg, naimenovanie, preparativnaya_forma, deystvuyushchee_veshchestvo, registrant, klass_opasnosti, data_reg, srok_reg, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (nomer_reg) DO NOTHING;""",
            (nomer, item.findtext('Naimenovanie/item'), item.findtext('Preparativnaya_forma/item'),
             json.dumps(dv), item.findtext('Registrant/item'), item.findtext('Klass_opasnosti/item'),
             item.findtext('Data_gosudarstvennoy_registracii/item'), item.findtext('Srok_registracii_Po/item'),
             item.findtext('Status_gosudarstvennoy_registracii/item')))

        for app in item.findall('.//fulldataset2/item'):
            cur.execute("""INSERT INTO reestr.pestitsidy_primeneniya 
                (nomer_reg, vrednyy_obekt, kultura, sposob, srok_ozhidaniya, vyhod, norma, avia, osobennosti)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);""",
                (nomer, app.findtext('Vrednyy_obekt_naznachenie'), app.findtext('Kultura_obrabatyvaemyy_obekt'),
                 app.findtext('Sposob_i_vremya_obrabotki'), app.findtext('Srok_ozhidaniya_kratnost_obrabotok'),
                 app.findtext('Sroki_vyhoda_dlya_ruchnyh_mehanizirovannyh_rabot'),
                 app.findtext('Norma_primeneniya'), app.findtext('Razreshenie_avia_obrabotok'),
                 app.findtext('Osobennosti_primeneniya')))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Пестициды + применения загружены")

if __name__ == "__main__":
    print(f"🚀 Обновление реестра {datetime.now()}")
    agro_xml = download_and_extract(AGRO_URL, "agrokhimikaty")
    pest_xml = download_and_extract(PEST_URL, "pestitsidy")
    import_agro(agro_xml)
    import_pest(pest_xml)
    print("🎉 Реестр полностью нормализован и готов к удобному просмотру!")
