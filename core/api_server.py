import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import sys
import sqlite3
import socket
import subprocess

from agent import RegistryAgent
import config

app = FastAPI()

# Global variable to track the background update process
update_process = None

# Mount static folder
# In packaged mode (PyInstaller), static files will be relative to MEIPASS
bundle_dir = os.environ.get("APP_EXE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
static_dir = os.path.join(bundle_dir, "static")

if not os.path.exists(static_dir):
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/api/status")
async def get_status():
    global update_process
    status = {
        "db_connected": False,
        "db_last_update": None,
        "vpn_status": "Отключен",
        "is_updating": False
    }

    if update_process and update_process.poll() is None:
        status["is_updating"] = True
    
    # Check DB
    db_path = os.getenv('SQLITE_DB_PATH', 'reestr.db')
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT MAX(imported_at) FROM agrokhimikaty;")
            row = cur.fetchone()
            if row and row[0]:
                status["db_connected"] = True
                status["db_last_update"] = row[0]
            conn.close()
    except Exception as e:
        print(f"DB status error: {e}")

    # Check VPN proxy port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(('127.0.0.1', 20171))
            status["vpn_status"] = "Подключен"
    except Exception:
        pass

    return status

@app.post("/api/update_db")
async def update_db():
    global update_process
    
    if update_process and update_process.poll() is None:
        return {"status": "already_running"}
        
    updater_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "updater", "import_reestr.py")
    if not os.path.exists(updater_script):
        updater_script = os.path.join(os.getcwd(), "updater", "import_reestr.py")
    
    update_process = subprocess.Popen([sys.executable, updater_script, "--once"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "started"}

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]]
    session_id: Optional[str] = "default"

@app.post("/api/chat")
async def chat(request: ChatRequest):
    # Ensure config prompts are loaded
    config.load_prompts()
    
    # Initialize the agent
    agent = RegistryAgent(session_id=request.session_id)
    
    # Process message
    answer = await agent.process_message(request.message, request.history)
    return {"answer": answer}

def main():
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, log_level="info")

if __name__ == "__main__":
    main()
