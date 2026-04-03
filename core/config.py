import os
from pathlib import Path
from dotenv import load_dotenv

# Пытаемся загрузить .env, если он есть
load_dotenv(override=True)

# ================== НАСТРОЙКИ ==================
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.1-pro-customtools")

# Определение базовой директории конфигурации
if os.path.exists("/app/config"):
    CONFIG_DIR = Path("/app/config")
elif os.environ.get('APP_EXE_DIR'):
    CONFIG_DIR = Path(os.environ['APP_EXE_DIR']) / "config"
else:
    CONFIG_DIR = Path(__file__).parent / "config"

USER_PROMPT_FILE = CONFIG_DIR / "user_promt.txt"
SYSTEM_PROMPT_FILE = CONFIG_DIR / "system_promt.txt"

current_user_prompt = ""
current_system_prompt = ""

def load_prompts():
    global current_user_prompt, current_system_prompt
    
    if USER_PROMPT_FILE.exists():
        current_user_prompt = USER_PROMPT_FILE.read_text(encoding="utf-8").strip()
        print(f"[SUCCESS] User Prompt загружен из файла", flush=True)
    else:
        current_user_prompt = "Ты полезный помощник по реестру пестицидов."
        print("[WARNING] user_promt.txt НЕ НАЙДЕН!", flush=True)

    if SYSTEM_PROMPT_FILE.exists():
        current_system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
        print(f"[SUCCESS] System Prompt загружен из файла", flush=True)
    else:
        current_system_prompt = "You are an AI Agent with tools."
        print("[WARNING] system_promt.txt НЕ НАЙДЕН!", flush=True)
