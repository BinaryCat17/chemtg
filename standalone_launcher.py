import os
import sys
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

# ОПРЕДЕЛЕНИЕ ПУТЕЙ
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    exe_dir = os.path.dirname(sys.executable)
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    exe_dir = bundle_dir

DB_PATH = os.path.join(exe_dir, "data", "reestr.db")
os.environ['SQLITE_DB_PATH'] = DB_PATH
os.environ['CONFIG_YAML_PATH'] = os.path.join(exe_dir, "config.yaml")
os.environ['DATA_DIR'] = os.path.join(exe_dir, "data")
os.environ['APP_EXE_DIR'] = exe_dir

for folder in [os.path.join(exe_dir, "data", "vpn"), os.path.join(exe_dir, "bin")]:
    os.makedirs(folder, exist_ok=True)

sys.path.append(os.path.join(bundle_dir, "core"))
sys.path.append(os.path.join(bundle_dir, "updater"))

import api_server
import import_reestr

env_path = os.path.join(exe_dir, ".env")
load_dotenv(env_path if os.path.exists(env_path) else None, override=True)

def log_startup(msg):
    timestamp = time.strftime("%H:%M:%S")
    api_server.startup_logs.append(f"[{timestamp}] {msg}")
    print(f"🚀 {msg}")

def parse_vless(link):
    if not link or not link.startswith("vless://"): return None
    try:
        url = urlparse(link)
        params = parse_qs(url.query)
        return {
            "uuid": url.username, "address": url.hostname, "port": url.port,
            "sni": params.get("sni", [""])[0], "pbk": params.get("pbk", [""])[0],
            "sid": params.get("sid", [""])[0], "flow": params.get("flow", [""])[0],
            "security": params.get("security", ["none"])[0], "type": params.get("type", ["tcp"])[0],
            "headerType": params.get("headerType", ["none"])[0] or "none", "fp": params.get("fp", ["chrome"])[0]
        }
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return None

def generate_xray_config(p):
    vpn_dir = os.path.join(exe_dir, "data", "vpn")
    config = {
        "log": {"loglevel": "debug"},
        "inbounds": [{"port": 20171, "listen": "127.0.0.1", "protocol": "http", "settings": {"auth": "noauth", "udp": True}}],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {"vnext": [{"address": p["address"], "port": p["port"], "users": [{"id": p["uuid"], "encryption": "none", "flow": p["flow"]}]}]},
                "streamSettings": {
                    "network": p["type"], "security": p["security"],
                    "realitySettings": {"show": False, "fingerprint": p["fp"], "serverName": p["sni"], "publicKey": p["pbk"], "shortId": p["sid"]} if p["security"] == "reality" else {},
                    "tlsSettings": {"serverName": p["sni"], "fingerprint": p["fp"]} if p["security"] == "tls" else {},
                    "tcpSettings": {"header": {"type": p["headerType"]}} if p["type"] == "tcp" else {}
                }
            },
            {"protocol": "freedom", "tag": "direct"}
        ]
    }
    with open(os.path.join(vpn_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)
    return True

def fetch_subscription():
    sub_url = os.getenv("VPN_SUBSCRIPTION_URL")
    if not sub_url: return []
    try:
        # ВОССТАНОВЛЕНО: x-hwid и полная логика декодирования
        headers = {
            'User-Agent': 'v2rayN/6.33',
            'x-hwid': 'a1b2c3d4e5f6'
        }
        r = requests.get(sub_url, headers=headers, timeout=15)
        r.encoding = 'utf-8'
        if r.status_code != 200: return []
        
        content = r.text.strip()
        try:
            padded = content + "=" * ((4 - len(content) % 4) % 4)
            decoded_body = base64.b64decode(padded).decode('utf-8')
        except:
            decoded_body = content
            
        links = []
        for line in decoded_body.splitlines():
            line = line.strip()
            if not line: continue
            if line.startswith("vless://"):
                links.append(line)
            else:
                try:
                    padded_line = line + "=" * ((4 - len(line) % 4) % 4)
                    dec = base64.b64decode(padded_line).decode('utf-8').strip()
                    if dec.startswith("vless://"):
                        links.append(dec)
                except:
                    pass
        
        if not links: return []
            
        # Сортировка (как было раньше)
        nl_links, de_links, other_links = [], [], []
        for line in links:
            dec_line = unquote(line).lower()
            if "нидерланды" in dec_line or "nl." in dec_line: nl_links.append(line)
            elif "германия" in dec_line or "de." in dec_line: de_links.append(line)
            else: other_links.append(line)
                
        return nl_links + de_links + other_links
    except Exception as e:
        print(f"❌ Ошибка подписки: {e}")
        return []

def test_proxy():
    try:
        # Проверяем доступность Gemini API через прокси
        r = requests.get("https://generativelanguage.googleapis.com", proxies={"https": "http://127.0.0.1:20171"}, timeout=5)
        return r.status_code in [200, 404, 403]
    except: return False

def start_vpn():
    xray_exe = os.path.join(exe_dir, "bin", "xray.exe" if os.name == 'nt' else "xray")
    if not os.path.exists(xray_exe):
        log_startup("VPN (Xray) не найден.")
        return False

    log_startup("Получение списка VPN серверов...")
    links = fetch_subscription()
    if not links:
        log_startup("Подписка VPN пуста или HWID отклонен.")
        return False
        
    for link in links:
        p = parse_vless(link)
        if not p or not p.get("address") or p["address"] == "0.0.0.0": continue
        
        server_name = unquote(link.split('#')[-1]) if '#' in link else p["address"]
        log_startup(f"Проверка сервера: {server_name}")
        
        if generate_xray_config(p):
            flags = 0x08000000 if os.name == 'nt' else 0
            proc = subprocess.Popen(
                [xray_exe, "-c", os.path.join(exe_dir, "data", "vpn", "config.json")], 
                creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 
                cwd=os.path.join(exe_dir, "bin")
            )
            
            time.sleep(3)
            if test_proxy():
                log_startup(f"VPN успешно подключен: {server_name}")
                os.environ['HTTP_PROXY'] = "http://127.0.0.1:20171"
                os.environ['HTTPS_PROXY'] = "http://127.0.0.1:20171"
                os.environ['ALL_PROXY'] = "http://127.0.0.1:20171"
                return True
            else:
                proc.terminate()
                time.sleep(1)
                
    log_startup("❌ Все серверы недоступны.")
    return False

def init_system():
    log_startup("Инициализация системы...")
    if not os.path.exists(DB_PATH):
        log_startup("База данных не найдена. Начинаю первый импорт...")
        import_reestr.run_import()
        log_startup("Первичный импорт завершен.")
    else:
        log_startup("База данных обнаружена.")
    
    vpn_ok = start_vpn()
    if vpn_ok:
        log_startup("VPN активен. Связь с ИИ установлена.")
    else:
        log_startup("⚠️ ВНИМАНИЕ: VPN не запущен. Работа с ИИ может быть ограничена.")
    
    log_startup("Система готова к работе!")
    api_server.is_system_ready = True

def scheduler_worker():
    schedule.every().day.at("00:00").do(import_reestr.run_import)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    # 1. Запускаем сервер в отдельном потоке (МГНОВЕННО)
    threading.Thread(target=api_server.main, daemon=True).start()
    
    # 2. Открываем браузер
    def open_browser():
        time.sleep(1)
        import webbrowser
        webbrowser.open("http://127.0.0.1:8000")
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 3. Планировщик
    threading.Thread(target=scheduler_worker, daemon=True).start()
    
    # 4. Инициализация в основном потоке
    try:
        init_system()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
