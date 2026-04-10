import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional

import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import db
from backend.orchestrator import Orchestrator


# --- WebSocket manager ---

class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, message: dict):
        for ws in self.connections[:]:
            try:
                await ws.send_json(message)
            except Exception:
                self.connections.remove(ws)


ws_manager = ConnectionManager()


# --- App lifecycle ---

orchestrator = Orchestrator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    # Clean up stale "running" cycles from previous crashes
    stale = await db.list_cycles(status="running", limit=50)
    for c in stale:
        await db.complete_cycle(c["id"], "failed", rollback_reason="Stale from server restart")
    orchestrator._broadcast = ws_manager.broadcast
    loop_task = asyncio.create_task(orchestrator.run_loop())
    yield
    orchestrator.stop()
    loop_task.cancel()


app = FastAPI(title="Ollama Team", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Models ---

class FeedbackIn(BaseModel):
    rating: str  # "up" or "down"
    note: Optional[str] = None


class GuidanceIn(BaseModel):
    message: str


class SettingsUpdate(BaseModel):
    cycle_cooldown_seconds: Optional[int] = None
    max_retries_per_step: Optional[int] = None
    process_timeout_seconds: Optional[int] = None
    health_check_timeout_seconds: Optional[int] = None
    paused: Optional[bool] = None
    stopped: Optional[bool] = None


# --- Health ---

@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Cycles ---

@app.get("/api/cycles")
async def list_cycles(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    cycles = await db.list_cycles(status=status, limit=limit, offset=offset)
    # Parse JSON fields for the response
    for c in cycles:
        if c.get("proposal") and isinstance(c["proposal"], str):
            try:
                c["proposal"] = json.loads(c["proposal"])
            except json.JSONDecodeError:
                pass
    return {"cycles": cycles, "limit": limit, "offset": offset}


@app.get("/api/cycles/{cycle_id}")
async def get_cycle(cycle_id: str):
    cycle = await db.get_cycle(cycle_id)
    if not cycle:
        return {"error": "Cycle not found"}, 404
    if cycle.get("proposal") and isinstance(cycle["proposal"], str):
        try:
            cycle["proposal"] = json.loads(cycle["proposal"])
        except json.JSONDecodeError:
            pass
    feedback = await db.get_feedback(cycle_id=cycle_id)
    return {"cycle": cycle, "feedback": feedback}


# --- Feedback ---

@app.post("/api/cycles/{cycle_id}/feedback")
async def submit_feedback(cycle_id: str, body: FeedbackIn):
    result = await db.add_feedback(cycle_id, body.rating, body.note)
    await ws_manager.broadcast({
        "type": "feedback",
        "cycle_id": cycle_id,
        "rating": body.rating,
    })
    return result


# --- Agents ---

@app.get("/api/agents")
async def list_agents():
    stats = await db.get_agent_stats()
    agents = ["planner", "coder", "reviewer", "tester", "deployer"]
    stats_map = {s["agent_name"]: s for s in stats}
    result = []
    for name in agents:
        s = stats_map.get(name, {})
        result.append({
            "name": name,
            "total_invocations": s.get("total_invocations", 0),
            "total_successes": s.get("total_successes", 0),
            "total_failures": s.get("total_failures", 0),
            "avg_duration_seconds": s.get("avg_duration_seconds", 0.0),
            "last_invoked_at": s.get("last_invoked_at"),
        })
    return {"agents": result}


@app.get("/api/agents/{name}")
async def get_agent(name: str):
    stats = await db.get_agent_stats(name)
    stat = stats[0] if stats else {}

    # Read current prompt
    from pathlib import Path
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{name}.md"
    prompt_content = ""
    if prompt_path.exists():
        prompt_content = prompt_path.read_text(encoding="utf-8")

    return {
        "name": name,
        "prompt": prompt_content,
        "stats": stat,
    }


# --- System ---

@app.get("/api/system/health")
async def system_health():
    from backend.services.llm_service import llm

    # Check LLM backend
    llm_status = await llm.get_status()
    llm_models = await llm.list_models()

    # System resources
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()

    return {
        "llm": {"backend": llm_status.get("backend", "unknown"), "models": llm_models, "status": llm_status},
        "cpu_percent": cpu_percent,
        "memory": {
            "total_gb": round(memory.total / (1024**3), 1),
            "used_gb": round(memory.used / (1024**3), 1),
            "percent": memory.percent,
        },
    }


# --- Control ---

@app.post("/api/system/pause")
async def pause_loop():
    await db.update_settings({"paused": "true"})
    await ws_manager.broadcast({"type": "system", "action": "paused"})
    return {"status": "paused"}


@app.post("/api/system/resume")
async def resume_loop():
    await db.update_settings({"paused": "false"})
    await ws_manager.broadcast({"type": "system", "action": "resumed"})
    return {"status": "resumed"}


@app.post("/api/system/guidance")
async def set_guidance(body: GuidanceIn):
    """Set a guidance prompt that the Planner will see on its next cycle."""
    await db.update_settings({"guidance": body.message})
    await ws_manager.broadcast({"type": "system", "action": "guidance_set", "message": body.message})
    return {"status": "ok", "message": body.message}


@app.get("/api/system/guidance")
async def get_guidance():
    settings = await db.get_settings()
    return {"message": settings.get("guidance", "")}


@app.post("/api/system/stop")
async def stop_loop():
    await db.update_settings({"stopped": "true"})
    orchestrator.stop()
    await ws_manager.broadcast({"type": "system", "action": "stopped"})
    return {"status": "stopped"}


@app.get("/api/system/status")
async def orchestrator_status():
    return orchestrator.status


@app.post("/api/system/trigger")
async def trigger_cycle():
    """Manually trigger one improvement cycle."""
    cycle_id = await orchestrator.run_cycle()
    return {"cycle_id": cycle_id}


# --- Settings ---

@app.get("/api/settings")
async def get_settings():
    return await db.get_settings()


@app.put("/api/settings")
async def update_settings(body: SettingsUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        str_updates = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in updates.items()}
        await db.update_settings(str_updates)
    return await db.get_settings()


# --- WebSocket ---

@app.websocket("/api/ws/activity")
async def activity_ws(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep alive — client can send pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
