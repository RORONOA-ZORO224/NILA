"""
scheduler.py
────────────
Background job queue for scheduled emails and future actions.
Uses APScheduler (AsyncIOScheduler) so jobs run in the same event loop as FastAPI.

Jobs survive server restarts via SQLite job store — same DB as the rest of ARIA.
"""

import asyncio
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from groq import Groq

DB_PATH = Path(__file__).parent / "aria_memory.db"

_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Scheduler singleton ───────────────────────────────────────────────────────

def _make_scheduler() -> AsyncIOScheduler:
    jobstores  = {"default": SQLAlchemyJobStore(url=f"sqlite:///{DB_PATH}")}
    executors  = {"default": AsyncIOExecutor()}
    job_defaults = {"coalesce": True, "max_instances": 1}

    return AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone="Asia/Kolkata",
    )


scheduler = _make_scheduler()


# ── Scheduled job table (for dashboard visibility) ────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_scheduler_table() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id           TEXT PRIMARY KEY,
                description  TEXT NOT NULL,
                run_at       TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'pending',
                payload      TEXT,
                created_at   TEXT NOT NULL
            );
        """)


def _log_scheduled_job(job_id: str, description: str, run_at: str, payload: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO scheduled_jobs (id, description, run_at, status, payload, created_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (job_id, description, run_at, json.dumps(payload), datetime.utcnow().isoformat()),
        )


def _mark_job_done(job_id: str, status: str = "done") -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE scheduled_jobs SET status = ? WHERE id = ?",
            (status, job_id),
        )


def get_scheduled_jobs(limit: int = 20) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_jobs ORDER BY run_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


# ── Natural language time → datetime ─────────────────────────────────────────

def parse_schedule_time(time_str: str) -> datetime:
    """
    Use Groq to convert a natural language time expression to a datetime object.
    Returns a timezone-aware datetime in IST.
    """
    now = datetime.now(timezone.utc).isoformat()
    prompt = f"""Convert this natural language time to an ISO 8601 datetime string.
Current UTC time: {now}
Time expression: "{time_str}"

Rules:
- Assume IST (UTC+5:30) unless another timezone is specified
- Return ONLY the ISO 8601 string, nothing else
- Example output: 2025-01-15T14:30:00+05:30

Output:"""

    response = _groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=50,
    )
    raw = response.choices[0].message.content.strip().strip('"')
    return datetime.fromisoformat(raw)


# ── Schedule an email ─────────────────────────────────────────────────────────

async def schedule_email(
    recipient: str,
    subject: str,
    topic: str,
    tone: str,
    persona: dict,
    send_at_str: str,
) -> dict[str, Any]:
    """
    Schedule an email to be sent at a future time.
    Returns job metadata for display in the dashboard.
    """
    from tools import gmail_tool  # avoid circular import at module level

    send_at = parse_schedule_time(send_at_str)
    job_id  = f"email_{recipient.replace('@','_')}_{int(send_at.timestamp())}"

    async def _send():
        result = await asyncio.to_thread(
            gmail_tool.send_email,
            recipient=recipient,
            subject=subject,
            topic=topic,
            tone=tone,
            persona=persona,
        )
        _mark_job_done(job_id, "sent" if result.get("status") == "sent" else "failed")
        return result

    scheduler.add_job(
        _send,
        trigger="date",
        run_date=send_at,
        id=job_id,
        replace_existing=True,
    )

    payload = {
        "recipient": recipient,
        "subject":   subject,
        "topic":     topic,
        "send_at":   send_at.isoformat(),
    }
    _log_scheduled_job(job_id, f"Email to {recipient} — '{subject}'", send_at.isoformat(), payload)

    return {
        "status":      "scheduled",
        "job_id":      job_id,
        "recipient":   recipient,
        "subject":     subject,
        "send_at":     send_at.isoformat(),
        "summary":     f"📅 Email to {recipient} scheduled for {send_at.strftime('%b %d at %I:%M %p')}",
    }


def cancel_scheduled_job(job_id: str) -> dict[str, Any]:
    """Cancel a pending scheduled job."""
    try:
        scheduler.remove_job(job_id)
        _mark_job_done(job_id, "cancelled")
        return {"status": "cancelled", "job_id": job_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}