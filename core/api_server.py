import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import os

from agent import RegistryAgent
import config

app = FastAPI()

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
