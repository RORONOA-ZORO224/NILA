"""
main.py  —  ARIA FastAPI server (Phase 2)
─────────────────────────────────────────
New endpoints:
  GET  /analytics          → hourly action counts + breakdown for chart
  GET  /scheduled          → pending scheduled jobs
  DELETE /scheduled/{id}   → cancel a scheduled job

New behaviour:
  send_email + future time → routed to scheduler, not sent immediately
  Scheduler starts/stops cleanly in FastAPI lifespan
"""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from intent_classifier import IntentClassifier
from memory import ActionHistory, PersonaMemory
from scheduler import (
    scheduler,
    init_scheduler_table,
    get_scheduled_jobs,
    cancel_scheduled_job,
    schedule_email,
)
from tool_router import ToolRouter
from undo_shield import undo_shield

classifier = IntentClassifier()
persona    = PersonaMemory()
history    = ActionHistory()
router     = ToolRouter(persona=persona, history=history)

_ws_clients: list[WebSocket] = []


async def broadcast(event: dict) -> None:
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 ARIA v2 starting up...")
    init_scheduler_table()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)
    print("🛑 ARIA shutting down.")


app = FastAPI(title="ARIA", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ✅ allow all (dev mode)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:    str
    confirm:    bool = False
    session_id: str | None = None


class ChatResponse(BaseModel):
    mode:           str
    response:       str
    action:         str
    result:         dict[str, Any] | None
    intent:         dict[str, Any]
    undo_available: bool
    action_id:      int | None
    session_id:     str | None = None


class UndoRequest(BaseModel):
    action_id: int


_pending: dict[str, Any] = {}


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty")

    if req.confirm and req.session_id:
        pending = _pending.pop(req.session_id, None)
        if not pending:
            raise HTTPException(400, "No pending action found for this session.")
        intent = pending["intent"]
        result = await router.execute(intent, pending["raw_command"])
        await broadcast({"type": "action_executed", "data": result})
        return ChatResponse(
            mode="ACT",
            response=_friendly(intent.action, result),
            action=intent.action,
            result=result,
            intent=intent.model_dump(),
            undo_available=bool(undo_shield.get_active()),
            action_id=result.get("action_id"),
        )

    ctx    = persona.get_all()
    intent = classifier.classify(message, ctx)
    await broadcast({"type": "intent_classified", "data": intent.model_dump()})

    # Route scheduled emails
    if (
        intent.action == "send_email"
        and intent.mode == "ACT"
        and intent.entities.time
        and _looks_future(intent.entities.time)
    ):
        result = await schedule_email(
            recipient=intent.entities.recipient,
            subject=intent.entities.subject or intent.entities.topic or "Following up",
            topic=intent.entities.topic or "the matter we discussed",
            tone=intent.tone,
            persona=ctx,
            send_at_str=intent.entities.time,
        )
        action_id = history.log("schedule_email", "ACT", result.get("summary", ""), intent.reasoning, result)
        result["action_id"] = action_id
        await broadcast({"type": "action_executed", "data": result})
        return ChatResponse(
            mode="ACT",
            response=result["summary"],
            action="schedule_email",
            result=result,
            intent=intent.model_dump(),
            undo_available=False,
            action_id=action_id,
        )

    if intent.mode == "ASK":
        return ChatResponse(
            mode="ASK",
            response=intent.clarifying_question,
            action=intent.action,
            result=None,
            intent=intent.model_dump(),
            undo_available=False,
            action_id=None,
        )

    if intent.mode == "PAUSE":
        sid = str(uuid.uuid4())
        _pending[sid] = {"intent": intent, "raw_command": message}
        return ChatResponse(
            mode="PAUSE",
            response=_pause_preview(intent),
            action=intent.action,
            result=None,
            intent=intent.model_dump(),
            undo_available=False,
            action_id=None,
            session_id=sid,
        )

    result = await router.execute(intent, message)
    await broadcast({"type": "action_executed", "data": result})
    return ChatResponse(
        mode="ACT",
        response=_friendly(intent.action, result),
        action=intent.action,
        result=result,
        intent=intent.model_dump(),
        undo_available=bool(undo_shield.get_active()),
        action_id=result.get("action_id"),
    )


# ── Undo ──────────────────────────────────────────────────────────────────────

@app.post("/undo")
async def undo(req: UndoRequest):
    try:
        result = await undo_shield.execute_undo(req.action_id)
        history.mark_undone(req.action_id)
        await broadcast({"type": "action_undone", "action_id": req.action_id})
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/undo/active")
async def get_active_undos():
    return {"active": undo_shield.get_active(), "window_seconds": int(os.getenv("UNDO_WINDOW_SECONDS", "30"))}


# ── Memory ────────────────────────────────────────────────────────────────────

@app.get("/memory")
async def get_memory():
    return {"preferences": persona.get_all()}


@app.delete("/memory/{key}")
async def delete_memory_key(key: str):
    persona.delete(key)
    return {"status": "deleted", "key": key}


# ── Actions ───────────────────────────────────────────────────────────────────

@app.get("/actions")
async def get_actions(limit: int = 20):
    return {"actions": history.get_recent(limit=limit)}


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics")
async def get_analytics():
    from memory import _get_conn
    with _get_conn() as conn:
        hourly_rows = conn.execute("""
            SELECT strftime('%H:00', executed_at) AS hour, COUNT(*) AS count
            FROM action_log
            WHERE executed_at >= datetime('now', '-24 hours')
            GROUP BY hour ORDER BY hour
        """).fetchall()
        hourly_map = {r["hour"]: r["count"] for r in hourly_rows}

        now = datetime.utcnow()
        hourly = []
        for i in range(24):
            label = (now - timedelta(hours=23 - i)).strftime("%H:00")
            hourly.append({"hour": label, "count": hourly_map.get(label, 0)})

        type_rows = conn.execute("""
            SELECT action, COUNT(*) AS count FROM action_log
            GROUP BY action ORDER BY count DESC
        """).fetchall()

        mode_rows = conn.execute("""
            SELECT mode, COUNT(*) AS count FROM action_log GROUP BY mode
        """).fetchall()

        stats = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status='undone' THEN 1 ELSE 0 END) AS undone,
                   SUM(CASE WHEN mode='ACT' THEN 1 ELSE 0 END) AS act_count
            FROM action_log
        """).fetchone()

    total = stats["total"] or 0
    return {
        "hourly":  hourly,
        "by_type": [{"action": r["action"], "count": r["count"]} for r in type_rows],
        "by_mode": [{"mode": r["mode"], "count": r["count"]} for r in mode_rows],
        "totals":  {
            "total":    total,
            "undone":   stats["undone"] or 0,
            "act_rate": round((stats["act_count"] or 0) / max(total, 1) * 100, 1),
        },
    }


# ── Scheduler ─────────────────────────────────────────────────────────────────

@app.get("/scheduled")
async def list_scheduled():
    return {"jobs": get_scheduled_jobs()}


@app.delete("/scheduled/{job_id}")
async def cancel_job(job_id: str):
    result = cancel_scheduled_job(job_id)
    if result.get("status") == "error":
        raise HTTPException(400, result["message"])
    return result


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":  "ok",
        "service": "ARIA",
        "scheduler_running": scheduler.running,
        "pending_jobs":      len(scheduler.get_jobs()),
    }


@app.websocket("/ws/dashboard")
async def dashboard_ws(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _looks_future(time_str: str) -> bool:
    signals = ["tomorrow", "next ", "tonight", "at ", "in ", "am", "pm",
               "morning", "afternoon", "evening", "monday", "tuesday",
               "wednesday", "thursday", "friday", "saturday", "sunday"]
    return any(s in time_str.lower() for s in signals)


def _friendly(action: str, result: dict) -> str:
    if result.get("status") in ("error", "missing_entity", "unknown_action", "channel_not_found"):
        return result.get("message", "Something went wrong.")
    return {
        "send_email":      lambda r: f"Done! Email sent to {r.get('to', '?')}.",
        "schedule_email":  lambda r: r.get("summary", "Email scheduled."),
        "create_event":    lambda r: f"Done! '{r.get('title', 'Event')}' added to your calendar.",
        "search_linkedin": lambda r: f"Found {r.get('count', 0)} HR contacts at {r.get('company', '?')}.",
        "slack_message":   lambda r: f"Message posted to {r.get('channel', 'Slack')}.",
        "notion_create":   lambda r: "Notion page created.",
        "chain":           lambda r: f"Done! Completed {r.get('steps_completed', 0)} actions.",
    }.get(action, lambda r: "Done!")(result)


def _pause_preview(intent) -> str:
    e = intent.entities
    return {
        "send_email":      f"About to email {e.recipient} about '{e.topic}'. Confirm?",
        "search_linkedin": f"About to search LinkedIn at {e.company} and send emails. Confirm?",
        "chain":           f"About to run a {len(intent.chain_steps)}-step workflow. Confirm?",
    }.get(intent.action, f"Risky action: {intent.reasoning}. Proceed?")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("BACKEND_PORT", 8000)), reload=True)