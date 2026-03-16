import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Пытаемся загрузить .env, если он есть (для локальной разработки без Docker)
load_dotenv()

# ================== НАСТРОЙКИ ==================
# Читаем из окружения. Если переменной нет — будет None, что лучше, чем скрытый дефолт.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")

# Читаем ADMIN_ID как число
admin_id_raw = os.getenv("ADMIN_ID", "0")
try:
    ADMIN_ID = int(admin_id_raw)
except ValueError:
    ADMIN_ID = 0
    print(f"[ERROR] Некорректный ADMIN_ID в .env: {admin_id_raw}", flush=True)

# Определение базовой директории конфигурации
if os.path.exists("/app/config"):
    CONFIG_DIR = Path("/app/config")
else:
    # Если мы не в докере, ищем папку config рядом с кодом
    CONFIG_DIR = Path(os.getcwd()) / "config"

WHITELIST_FILE = CONFIG_DIR / "whitelist.json"
USER_PROMPT_FILE = CONFIG_DIR / "user_promt.txt"
SYSTEM_PROMPT_FILE = CONFIG_DIR / "system_promt.txt"

whitelist_set = set() # Здесь будем хранить ID как строки
last_mtime = 0.0
current_user_prompt = ""
current_system_prompt = ""


def log_prompt(title: str, content: str):
    """Красивый вывод промпта в консоль"""
    separator = "=" * 95
    print(f"\n{separator}", flush=True)
    print(f"🔍 {title} (длина = {len(content)} символов)", flush=True)
    print(separator, flush=True)
    print(content.strip(), flush=True)
    print(separator + "\n", flush=True)


def load_whitelist():
    global whitelist_set, last_mtime
    if not WHITELIST_FILE.exists():
        print(f"[WARNING] whitelist.json не найден: {WHITELIST_FILE}", flush=True)
        return
    mtime = WHITELIST_FILE.stat().st_mtime
    if mtime == last_mtime:
        return
    try:
        data = json.loads(WHITELIST_FILE.read_text(encoding="utf-8-sig"))
        whitelist_set.clear()
        # Храним ID как строки для консистентности с JSON
        whitelist_set.update({str(item) for item in data})
        last_mtime = mtime
        print(f"[INFO] Whitelist загружен: {len(whitelist_set)} пользователей", flush=True)
    except Exception as e:
        print(f"[ERROR] Whitelist: {e}", flush=True)


def load_prompts():
    global current_user_prompt, current_system_prompt
    
    # Загружаем пользовательский промпт
    if USER_PROMPT_FILE.exists():
        current_user_prompt = USER_PROMPT_FILE.read_text(encoding="utf-8").strip()
        print(f"[SUCCESS] User Prompt загружен из файла", flush=True)
    else:
        current_user_prompt = "Ты полезный помощник по реестру пестицидов."
        print("[WARNING] user_promt.txt НЕ НАЙДЕН!", flush=True)

    # Загружаем системный промпт
    if SYSTEM_PROMPT_FILE.exists():
        current_system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
        print(f"[SUCCESS] System Prompt загружен из файла", flush=True)
    else:
        current_system_prompt = "You are an AI Agent with tools."
        print("[WARNING] system_promt.txt НЕ НАЙДЕН!", flush=True)
