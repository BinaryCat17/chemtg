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

# =========================================================
# ФИКС ДЛЯ TIKTOKEN В EXE (ПРАВИЛЬНЫЙ)
# =========================================================
if getattr(sys, 'frozen', False):
    os.environ["TIKTOKEN_CACHE_DIR"] = sys._MEIPASS
# =========================================================

# ОПРЕДЕЛЕНИЕ ПУТЕЙ
if getattr(sys, 'frozen', False):
    # Если запущен EXE: bundle_dir - это Temp, а exe_dir - папка с EXE
    bundle_dir = sys._MEIPASS
    exe_dir = os.path.dirname(sys.executable)
else:
    # Если запущен скрипт .py
    bundle_dir = os.path.dirname(os.path.abspath(__file__))
    exe_dir = bundle_dir

# АБСОЛЮТНЫЕ ПУТИ (все данные ищем СНАРУЖИ EXE в папке дистрибутива)
DB_PATH = os.path.join(exe_dir, "data", "reestr.db")
os.environ['SQLITE_DB_PATH'] = DB_PATH
os.environ['CONFIG_YAML_PATH'] = os.path.join(exe_dir, "config.yaml")
os.environ['DATA_DIR'] = os.path.join(exe_dir, "data")
# Пробрасываем путь к конфигам для других модулей
os.environ['APP_EXE_DIR'] = exe_dir

# ГАРАНТИРУЕМ НАЛИЧИЕ ПАПОК ПРИ ЗАПУСКЕ
for folder in [os.path.join(exe_dir, "data", "vpn"), os.path.join(exe_dir, "bin")]:
    os.makedirs(folder, exist_ok=True)

sys.path.append(os.path.join(bundle_dir, "core"))
sys.path.append(os.path.join(bundle_dir, "updater"))

try:
    import api_server
    import import_reestr
except ImportError:
    sys.path.append(os.path.join(os.getcwd(), "core"))
    sys.path.append(os.path.join(os.getcwd(), "updater"))
    import api_server
    import import_reestr

env_path = os.path.join(exe_dir, ".env")
load_dotenv(env_path if os.path.exists(env_path) else None, override=True)

def parse_vless(link):
    if not link or not link.startswith("vless://"): return None
    try:
        url = urlparse(link)
        params = parse_qs(url.query)
        return {
            "uuid": url.username,
            "address": url.hostname,
            "port": url.port,
            "sni": params.get("sni", [""])[0],
            "pbk": params.get("pbk", [""])[0],
            "sid": params.get("sid", [""])[0],
            "flow": params.get("flow", [""])[0],
            "security": params.get("security", ["none"])[0],
            "type": params.get("type", ["tcp"])[0],
            "headerType": params.get("headerType", ["none"])[0] or "none",
            "fp": params.get("fp", ["chrome"])[0]
        }
    except Exception as e:
        print(f"❌ Ошибка парсинга: {e}")
        return None

def generate_xray_config(p):
    if not p: return False
    # Гарантируем наличие папок
    vpn_dir = os.path.join(exe_dir, "data", "vpn")
    os.makedirs(vpn_dir, exist_ok=True)

    config = {
        "log": {
            "loglevel": "debug",
            "access": os.path.join(vpn_dir, "access.log"),
            "error": os.path.join(vpn_dir, "error.log")
        },
        "inbounds": [{
            "port": 20171,
            "listen": "127.0.0.1",
            "protocol": "http",
            "settings": {"auth": "noauth", "udp": True}
        }],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": p["address"],
                        "port": p["port"],
                        "users": [{
                            "id": p["uuid"],
                            "encryption": "none",
                            "flow": p["flow"]
                        }]
                    }]
                },
                "streamSettings": {
                    "network": p["type"],
                    "security": p["security"],
                    "realitySettings": {
                        "show": False,
                        "fingerprint": p["fp"],
                        "serverName": p["sni"],
                        "publicKey": p["pbk"],
                        "shortId": p["sid"]
                    } if p["security"] == "reality" else {},
                    "tlsSettings": {
                        "serverName": p["sni"],
                        "fingerprint": p["fp"]
                    } if p["security"] == "tls" else {},
                    "tcpSettings": {
                        "header": {"type": p["headerType"]}
                    } if p["type"] == "tcp" else {}
                }
            },
            {"protocol": "freedom", "tag": "direct"}
        ]
    }
    
    # Удаляем пустые секции
    outbound_stream = config["outbounds"][0]["streamSettings"]
    if not outbound_stream.get("realitySettings"):
        del outbound_stream["realitySettings"]
    if not outbound_stream.get("tlsSettings"):
        del outbound_stream["tlsSettings"]

    # Гарантируем наличие папок
    vpn_dir = os.path.join(exe_dir, "data", "vpn")
    os.makedirs(vpn_dir, exist_ok=True)

    with open(os.path.join(vpn_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)
    return True

def fetch_subscription():
    sub_url = os.getenv("VPN_SUBSCRIPTION_URL")
    if not sub_url: return []
    try:
        # Используем проверенную заглушку
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
        
        if not links:
            return []
            
        # Сортируем: Нидерланды -> Германия -> Остальные
        nl_links = []
        de_links = []
        other_links = []
        
        for line in links:
            decoded_line = unquote(line).lower()
            if "нидерланды" in decoded_line or "nl." in decoded_line:
                nl_links.append(line)
            elif "германия" in decoded_line or "de." in decoded_line:
                de_links.append(line)
            else:
                other_links.append(line)
                
        return nl_links + de_links + other_links
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Ошибка подписки: {e}")
    return []

def test_proxy():
    print("⏳ Проверка VPN соединения (Gemini API)...")
    proxies = {"http": "http://127.0.0.1:20171", "https": "http://127.0.0.1:20171"}
    try:
        r = requests.get("https://generativelanguage.googleapis.com", proxies=proxies, timeout=15)
        if r.status_code in [200, 404, 403]:
            print("✅ VPN работает!")
            return True
    except Exception as e:
        print(f"❌ VPN не пропускает трафик: {e}")
    return False

def start_vpn():
    xray_exe = os.path.join(exe_dir, "bin", "xray.exe" if os.name == 'nt' else "xray")
    if not os.path.exists(xray_exe):
        print(f"⚠️ {xray_exe} не найден.")
        return False

    # Проверка дата-файлов Xray
    for f in ["geoip.dat", "geosite.dat"]:
        if not os.path.exists(os.path.join(exe_dir, "bin", f)):
            print(f"⚠️ Файл {f} не найден в папке bin. Xray может не работать.")

    links = fetch_subscription()
    if not links:
        print("❌ Не удалось получить ссылку из подписки.")
        return False
        
    for link in links:
        p = parse_vless(link)
        if not p or not p.get("address") or p["address"] == "0.0.0.0": continue
        
        server_name = unquote(link.split('#')[-1]) if '#' in link else p["address"]
        print(f"🔄 Пробуем подключиться к VPN серверу: {server_name}")
        
        if generate_xray_config(p):
            flags = 0x08000000 if os.name == 'nt' else 0
            xray_proc = subprocess.Popen(
                [xray_exe, "-c", os.path.join(exe_dir, "data", "vpn", "config.json")], 
                creationflags=flags, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                cwd=os.path.join(exe_dir, "bin")
            )
            
            time.sleep(3)
            if test_proxy():
                os.environ['HTTP_PROXY'] = "http://127.0.0.1:20171"
                os.environ['HTTPS_PROXY'] = "http://127.0.0.1:20171"
                os.environ['ALL_PROXY'] = "http://127.0.0.1:20171"
                return True
            else:
                print(f"❌ Сервер {server_name} недоступен. Пробуем следующий...")
                xray_proc.terminate()
                time.sleep(1)
                
    print("❌ Ни один из серверов подписки не заработал.")
    return False

def check_database():
    if not os.path.exists(DB_PATH):
        print(f"📦 База данных не обнаружена. Импорт...")
        import_reestr.run_import()

def scheduler_worker():
    schedule.every().day.at("00:00").do(import_reestr.run_import)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    print("=== Standalone ChemTG Bot (v2.0.0 - Web UI) ===")
    check_database()
    threading.Thread(target=scheduler_worker, daemon=True).start()
    
    vpn_ok = start_vpn()
    if not vpn_ok:
        print("⚠️ ВНИМАНИЕ: Бот запущен БЕЗ работающего VPN.")
    
    def open_browser():
        time.sleep(2)
        import webbrowser
        try:
            print("🌐 Открываю браузер: http://127.0.0.1:8000")
            # Перенаправляем stdout/stderr, чтобы подавить ошибку gio в WSL
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = open(os.devnull, 'w')
            sys.stderr = open(os.devnull, 'w')
            try:
                webbrowser.open("http://127.0.0.1:8000")
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
        except Exception as e:
            print(f"⚠️ Не удалось открыть браузер: {e}. Откройте вручную http://127.0.0.1:8000")

    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        api_server.main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        input("Нажмите Enter...")


    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        api_server.main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        input("Нажмите Enter...")
