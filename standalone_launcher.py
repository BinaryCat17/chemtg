import os
import sys

# =========================================================
# ФИКС ДЛЯ TIKTOKEN В EXE (ПРАВИЛЬНЫЙ)
# =========================================================
if getattr(sys, 'frozen', False):
    # При сборке в EXE, tiktoken должен искать кодировки в папке внутри EXE
    os.environ["TIKTOKEN_CACHE_DIR"] = sys._MEIPASS
# =========================================================

import time
import subprocess
import requests
import base64
import json
import re
import asyncio
import threading
import schedule
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

# КОРРЕКТНОЕ ОПРЕДЕЛЕНИЕ ПУТЕЙ ДЛЯ EXE
if getattr(sys, 'frozen', False):
    # Если запущено как EXE
    bundle_dir = sys._MEIPASS
    exe_dir = os.path.dirname(sys.executable)
else:
    # Если запущено как обычный скрипт
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    exe_dir = bundle_dir

# Устанавливаем абсолютные пути для стабильной работы EXE
DB_PATH = os.path.join(exe_dir, "reestr.db")
os.environ['SQLITE_DB_PATH'] = DB_PATH
os.environ['CONFIG_YAML_PATH'] = os.path.join(exe_dir, "config.yaml")
os.environ['DATA_DIR'] = os.path.join(exe_dir, "data")

# Добавляем пути к модулям внутри EXE
sys.path.append(os.path.join(bundle_dir, "telegram-bot"))
sys.path.append(os.path.join(bundle_dir, "updater"))

# Теперь импорты не упадут
try:
    import main
    import handlers  # Явно импортируем для PyInstaller
    import import_reestr
except ImportError as e:
    print(f"❌ Ошибка импорта модулей: {e}")
    # Попробуем альтернативный путь если папки лежат рядом с EXE
    sys.path.append(os.path.join(os.getcwd(), "telegram-bot"))
    sys.path.append(os.path.join(os.getcwd(), "updater"))
    import main
    import handlers
    import import_reestr

# Загружаем .env из папки с EXE
env_path = os.path.join(exe_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv() # Фолбэк на текущую директорию

def parse_vless(link):
    if not link or not link.startswith("vless://"): return None
    try:
        parts = link[8:].split("@")
        uuid = parts[0]
        address_parts = parts[1].split("?")
        host_port = address_parts[0].split(":")
        address = host_port[0]
        port = int(host_port[1])
        params = parse_qs(address_parts[1])
        return {
            "uuid": uuid, "address": address, "port": port,
            "sni": params.get("sni", [""])[0], "pbk": params.get("pbk", [""])[0],
            "sid": params.get("sid", [""])[0], "flow": params.get("flow", [""])[0],
            "security": params.get("security", [""])[0], "type": params.get("type", ["tcp"])[0]
        }
    except: return None

def generate_xray_config(vless_link):
    p = parse_vless(vless_link)
    if not p: return False
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "port": 20171, "listen": "127.0.0.1", "protocol": "http",
            "settings": {"auth": "noauth", "udp": True}
        }],
        "outbounds": [{
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": p["address"], "port": p["port"],
                    "users": [{"id": p["uuid"], "encryption": "none", "flow": p["flow"]}]
                }]
            },
            "streamSettings": {
                "network": p["type"], "security": p["security"],
                "realitySettings": {
                    "show": False, "fingerprint": "chrome",
                    "serverName": p["sni"], "publicKey": p["pbk"], "shortId": p["sid"]
                }
            }
        }, {"protocol": "freedom", "tag": "direct"}]
    }
    with open("config.json", "w") as f: json.dump(config, f, indent=2)
    return True

def fetch_subscription():
    sub_url = os.getenv("VPN_SUBSCRIPTION_URL")
    if not sub_url: return None
    try:
        headers = {'x-hwid': 'standalone-bot-v3'}
        r = requests.get(sub_url, headers=headers, timeout=10)
        if r.status_code == 200:
            decoded = base64.b64decode(r.text).decode('utf-8')
            for link in decoded.splitlines():
                if "vless://" in link and "reality" in link: return link
    except: pass
    return None

def start_vpn():
    # Ищем xray.exe сначала в папке с EXE, потом в текущей папке
    xray_exe = "xray.exe" if os.name == 'nt' else "./xray"
    if not os.path.exists(xray_exe):
        # Если запущено из EXE, ищем рядом с ним
        xray_exe = os.path.join(exe_dir, "xray.exe")
        if not os.path.exists(xray_exe): return

    vless_link = fetch_subscription()
    if vless_link and generate_xray_config(vless_link):
        print("🌐 Запуск встроенного VPN...")
        os.environ['HTTP_PROXY'] = "http://127.0.0.1:20171"
        os.environ['HTTPS_PROXY'] = "http://127.0.0.1:20171"
        os.environ['ALL_PROXY'] = "http://127.0.0.1:20171"
        os.environ['NO_PROXY'] = "localhost,127.0.0.1"
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        subprocess.Popen([xray_exe, "-c", "config.json"], creationflags=creation_flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)

def check_database():
    if not os.path.exists(DB_PATH):
        print(f"📦 База данных {DB_PATH} не обнаружена. Запуск импорта...")
        import_reestr.run_import()
    else:
        print(f"✅ База данных обнаружена: {DB_PATH}")

def scheduler_worker():
    print("🕒 Планировщик обновлений запущен (ежедневно в 00:00).")
    schedule.every().day.at("00:00").do(import_reestr.run_import)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    print("=== Standalone ChemTG Bot (EXE Mode) ===")
    check_database()
    
    # Запуск планировщика в фоновом потоке
    scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
    scheduler_thread.start()
    
    start_vpn()
    try:
        asyncio.run(main.main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"💥 Ошибка: {e}")
        input("Нажмите Enter для выхода...")
