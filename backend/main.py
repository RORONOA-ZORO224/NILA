"""
main.py
───────
ARIA FastAPI server.
All routes, startup, CORS, and WebSocket for real-time dashboard.
"""

import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from intent_classifier import IntentClassifier
from memory import ActionHistory, PersonaMemory
from tool_router import ToolRouter
from undo_shield import undo_shield

# ── Singletons ────────────────────────────────────────────────────────────────
classifier = IntentClassifier()
persona = PersonaMemory()
history = ActionHistory()
router = ToolRouter(persona=persona, history=history)

# ── Connected WebSocket clients for live dashboard push ───────────────────────
_ws_clients: list[WebSocket] = []


async def broadcast(event: dict) -> None:
    """Push an event to all connected dashboard WebSocket clients."""
    disconnected = []
    for ws in _ws_clients:
        try:
            await ws.send_json(event)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _ws_clients.remove(ws)


# ── App setup ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 ARIA backend starting up...")
    yield
    print("🛑 ARIA backend shutting down.")


app = FastAPI(
    title="ARIA — Autonomous Real-world Intent Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000"), "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    confirm: bool = False   # Set True when user confirms a PAUSE-mode action


class ChatResponse(BaseModel):
    mode: str                       # ACT | ASK | PAUSE
    response: str                   # Human-readable ARIA reply
    action: str
    result: dict[str, Any] | None
    intent: dict[str, Any]          # Full intent JSON for dashboard transparency
    undo_available: bool
    action_id: int | None


class UndoRequest(BaseModel):
    action_id: int


# ── Session store for pending PAUSE confirmations ─────────────────────────────
# In production this would be Redis; for hackathon, in-memory is fine.
_pending_confirmations: dict[str, Any] = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main ARIA endpoint.
    Classifies the message, routes to the correct tool, returns structured response.
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # ── Handle confirmation of a pending PAUSE action ──────────────────────
    if req.confirm and "pending" in _pending_confirmations:
        pending = _pending_confirmations.pop("pending")
        intent = pending["intent"]
        result = await router.execute(intent, pending["raw_command"])
        await broadcast({"type": "action_executed", "data": result})

        return ChatResponse(
            mode="ACT",
            response=_friendly_response(intent.action, result),
            action=intent.action,
            result=result,
            intent=intent.model_dump(),
            undo_available=bool(undo_shield.get_active()),
            action_id=result.get("action_id"),
        )

    # ── Classify intent ────────────────────────────────────────────────────
    persona_context = persona.get_all()
    intent = classifier.classify(message, persona_context)

    await broadcast({"type": "intent_classified", "data": intent.model_dump()})

    # ── ASK mode: return clarifying question, no action ───────────────────
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

    # ── PAUSE mode: store pending, return preview card ─────────────────────
    if intent.mode == "PAUSE":
        _pending_confirmations["pending"] = {"intent": intent, "raw_command": message}
        preview = _build_pause_preview(intent)
        return ChatResponse(
            mode="PAUSE",
            response=preview,
            action=intent.action,
            result=None,
            intent=intent.model_dump(),
            undo_available=False,
            action_id=None,
        )

    # ── ACT mode: execute immediately ─────────────────────────────────────
    result = await router.execute(intent, message)
    await broadcast({"type": "action_executed", "data": result})

    # Update undo entries with the real action_id
    active = undo_shield.get_active()
    if active:
        # The most recently registered entry has action_id=0; patch it
        for entry in undo_shield._store.values():
            if entry.action_id == 0:
                entry.action_id = result["action_id"]
                undo_shield._store[result["action_id"]] = undo_shield._store.pop(0, entry)
                break

    return ChatResponse(
        mode="ACT",
        response=_friendly_response(intent.action, result),
        action=intent.action,
        result=result,
        intent=intent.model_dump(),
        undo_available=bool(undo_shield.get_active()),
        action_id=result.get("action_id"),
    )


@app.post("/undo")
async def undo(req: UndoRequest):
    """Trigger undo for a specific action within the 30-second window."""
    try:
        result = await undo_shield.execute_undo(req.action_id)
        history.mark_undone(req.action_id)
        await broadcast({"type": "action_undone", "action_id": req.action_id})
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/undo/active")
async def get_active_undos():
    """Return all currently undoable actions with countdown timers."""
    return {"active": undo_shield.get_active()}


@app.get("/memory")
async def get_memory():
    """Return ARIA's persona memory — shown in the 'What ARIA knows' panel."""
    return {"preferences": persona.get_all()}


@app.delete("/memory/{key}")
async def delete_memory_key(key: str):
    """Allow users to delete a specific learned preference."""
    persona.set(key, None)
    return {"status": "deleted", "key": key}


@app.get("/actions")
async def get_action_log(limit: int = 20):
    """Return recent action history for the dashboard."""
    return {"actions": history.get_recent(limit=limit)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ARIA"}


@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    """WebSocket endpoint — frontend subscribes for real-time action events."""
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()   # Keep connection alive
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)


# ── Response helpers ──────────────────────────────────────────────────────────

def _friendly_response(action: str, result: dict) -> str:
    """Generate a natural language confirmation from the tool result."""
    if result.get("status") in ("error", "missing_entity", "unknown_action", "channel_not_found"):
        return result.get("message", "Something went wrong. Try again.")

    messages = {
        "send_email":     lambda r: f"Done! Email sent to {r.get('to', '?')}.",
        "create_event":   lambda r: f"Done! '{r.get('title', 'Event')}' added to your calendar.",
        "search_linkedin":lambda r: f"Found {r.get('count', 0)} HR contacts at {r.get('company', '?')}.",
        "slack_message":  lambda r: f"Message posted to {r.get('channel', 'Slack')}.",
        "notion_create":  lambda r: f"Notion page created.",
        "chain":          lambda r: f"Done! Completed {r.get('steps_completed', 0)} actions.",
    }
    handler = messages.get(action, lambda r: "Done!")
    return handler(result)


def _build_pause_preview(intent) -> str:
    """Build a human-readable action preview for PAUSE mode."""
    e = intent.entities
    previews = {
        "send_email":   f"I'm about to send an email to {e.recipient} about '{e.topic}'. Confirm?",
        "search_linkedin": f"I'm about to search LinkedIn for HR contacts at {e.company} and send emails. Confirm?",
        "chain":        f"I'm about to run a {len(intent.chain_steps)}-step workflow. Confirm?",
    }
    return previews.get(
        intent.action,
        f"This action looks risky: {intent.reasoning}. Should I proceed?",
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("BACKEND_PORT", 8000)), reload=True)