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
from database import Database
import config

app = FastAPI()

# Global state
update_process = None
startup_logs = []
is_system_ready = False

# Mount static folder
bundle_dir = os.environ.get("APP_EXE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
static_dir = os.path.join(bundle_dir, "static")
if not os.path.exists(static_dir):
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/api/startup-status")
async def get_startup_status():
    return {"logs": startup_logs, "ready": is_system_ready}

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
    except Exception: pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(('127.0.0.1', 20171))
            status["vpn_status"] = "Подключен"
    except Exception: pass

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

@app.get("/api/products/pesticides")
async def get_pesticides(page: int = 1, limit: int = 50, q: str = "", field: str = "all"):
    db = Database()
    offset = (page - 1) * limit
    conditions = []
    join_clause = ""
    
    if q:
        if field == "name": conditions.append(f"p.naimenovanie REGEXP '{q}'")
        elif field == "dv": conditions.append(f"EXISTS (SELECT 1 FROM json_each(p.deystvuyushchee_veshchestvo) WHERE value->>'veshchestvo' REGEXP '{q}')")
        elif field == "reg_number": conditions.append(f"p.nomer_reg REGEXP '{q}'")
        elif field == "crop":
            join_clause = "JOIN pestitsidy_primeneniya pp ON p.nomer_reg = pp.nomer_reg"
            conditions.append(f"pp.kultura REGEXP '{q}'")
        else:
            join_clause = "LEFT JOIN pestitsidy_primeneniya pp ON p.nomer_reg = pp.nomer_reg"
            conditions.append(f"(p.naimenovanie REGEXP '{q}' OR p.nomer_reg REGEXP '{q}' OR pp.kultura REGEXP '{q}' OR EXISTS (SELECT 1 FROM json_each(p.deystvuyushchee_veshchestvo) WHERE value->>'veshchestvo' REGEXP '{q}'))")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT DISTINCT p.*, COALESCE(pop.score, 0) as popularity 
        FROM pestitsidy p {join_clause}
        LEFT JOIN product_popularity pop ON p.naimenovanie = pop.naimenovanie 
        {where} ORDER BY popularity DESC, p.naimenovanie ASC LIMIT {limit} OFFSET {offset}
    """
    count_query = f"SELECT COUNT(DISTINCT p.nomer_reg) as total FROM pestitsidy p {join_clause} {where}"
    items = db.execute_query(query)
    total_res = db.execute_query(count_query)
    return {"items": items, "total": total_res[0]['total'] if total_res else 0}

@app.get("/api/products/agrochemicals")
async def get_agrochemicals(page: int = 1, limit: int = 50, q: str = "", field: str = "all"):
    db = Database()
    offset = (page - 1) * limit
    conditions = []
    join_clause = ""
    if q:
        if field == "name": conditions.append(f"a.preparat REGEXP '{q}'")
        elif field == "reg_number": conditions.append(f"a.rn REGEXP '{q}'")
        elif field == "crop":
            join_clause = "JOIN agrokhimikaty_primeneniya ap ON a.rn = ap.rn"
            conditions.append(f"ap.kultura REGEXP '{q}'")
        else:
            join_clause = "LEFT JOIN agrokhimikaty_primeneniya ap ON a.rn = ap.rn"
            conditions.append(f"(a.preparat REGEXP '{q}' OR a.rn REGEXP '{q}' OR ap.kultura REGEXP '{q}')")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT DISTINCT a.*, COALESCE(pop.score, 0) as popularity 
        FROM agrokhimikaty a {join_clause}
        LEFT JOIN agrokhimikaty_popularity pop ON a.preparat = pop.preparat 
        {where} ORDER BY popularity DESC, a.preparat ASC LIMIT {limit} OFFSET {offset}
    """
    count_query = f"SELECT COUNT(DISTINCT a.rn) as total FROM agrokhimikaty a {join_clause} {where}"
    items = db.execute_query(query)
    total_res = db.execute_query(count_query)
    return {"items": items, "total": total_res[0]['total'] if total_res else 0}

@app.get("/api/product/pesticide/{id:path}")
async def get_pesticide_detail(id: str):
    db = Database()
    p_res = db.execute_query(f"SELECT * FROM pestitsidy WHERE nomer_reg = '{id}'")
    if not p_res: return {"error": "Not found"}
    apps = db.execute_query(f"SELECT * FROM pestitsidy_primeneniya WHERE nomer_reg = '{id}'")
    return {"info": p_res[0], "applications": apps}

@app.get("/api/product/agrochemical/{id:path}")
async def get_agrochemical_detail(id: str):
    db = Database()
    a_res = db.execute_query(f"SELECT * FROM agrokhimikaty WHERE rn = '{id}'")
    if not a_res: return {"error": "Not found"}
    apps = db.execute_query(f"SELECT * FROM agrokhimikaty_primeneniya WHERE rn = '{id}'")
    return {"info": a_res[0], "applications": apps}

class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]]
    session_id: Optional[str] = "default"

@app.post("/api/chat")
async def chat(request: ChatRequest):
    config.load_prompts()
    agent = RegistryAgent(session_id=request.session_id)
    answer = await agent.process_message(request.message, request.history)
    return {"answer": answer}

def main():
    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, log_level="info")

if __name__ == "__main__":
    main()
