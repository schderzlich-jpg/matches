from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import asyncio
import subprocess

from fastapi.staticfiles import StaticFiles

# Backend constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGOS_DIR = os.path.join(BASE_DIR, "logos")
OUTPUT_DIR = os.path.join(BASE_DIR, "Mac")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads") # Adding uploads as per rules
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = FastAPI(title="Match Automation API")

# Serve static files for previews
app.mount("/static/previews", StaticFiles(directory=OUTPUT_DIR), name="previews")
app.mount("/static/logos", StaticFiles(directory=LOGOS_DIR), name="logos")
app.mount("/static/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MatchInput(BaseModel):
    home_team: str
    away_team: str
    odds_1: Optional[str] = ""
    odds_x: Optional[str] = ""
    odds_2: Optional[str] = ""
    manual_datetime: Optional[str] = None

class AutomationTask(BaseModel):
    matches: List[MatchInput]
    boost_odds: bool = False
    subtract_day_for_night: bool = False

@app.get("/")
async def root():
    return {"status": "ok", "message": "Match Automation API is running"}

from automation_engine import run_automation_flow, get_upcoming_fixtures, render_match_psd

@app.post("/api/v1/automation/render")
async def render_match(data: dict):
    try:
        match = data.get("match")
        template = data.get("template", "Maclar.psd")
        
        # Run in thread pool since Photoshop trigger is blocking
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, render_match_psd, match, template)
        
        if success:
            return {"status": "success", "message": "Render triggered in Photoshop"}
        else:
            return {"status": "error", "message": "Failed to trigger Photoshop"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/automation/fixtures")
async def list_fixtures():
    try:
        fixtures = await get_upcoming_fixtures()
        return {"status": "success", "fixtures": fixtures}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/automation/execute")
async def execute_automation(task: AutomationTask):
    try:
        results = await run_automation_flow(
            [m.dict() for m in task.matches], 
            task.boost_odds, 
            task.subtract_day_for_night
        )
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/automation/previews/{filename}")
async def delete_preview(filename: str):
    try:
        file_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "success", "message": f"File {filename} deleted"}
        else:
            raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/automation/previews")
async def list_previews():
    try:
        import unicodedata
        files = [unicodedata.normalize('NFC', f) for f in os.listdir(OUTPUT_DIR) if f.endswith(('.png', '.jpg', '.jpeg'))]
        # Return sorted by modification time (newest first)
        files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
        return {"status": "success", "previews": files}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
