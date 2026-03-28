"""
memory.py
─────────
Persona memory and action history using SQLite.
Two responsibilities:
  1. PersonaMemory  — learns user preferences from interactions
  2. ActionHistory  — append-only log of all executed actions (for dashboard)
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from groq import Groq

DB_PATH = Path(__file__).parent / "aria_memory.db"

# ── Schema setup ──────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS persona (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS action_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                action     TEXT NOT NULL,
                mode       TEXT NOT NULL,
                summary    TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'executed',
                reasoning  TEXT,
                payload    TEXT,
                executed_at TEXT NOT NULL
            );
        """)

# ── PersonaMemory ─────────────────────────────────────────────────────────────

class PersonaMemory:
    """
    Stores and retrieves learned user preferences.
    After every successful action, we run a lightweight Groq call to extract
    any new preference signals from the command.
    """

    def __init__(self):
        self._groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
        init_db()

    def get_all(self) -> dict[str, Any]:
        with _get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM persona").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def set(self, key: str, value: Any) -> None:
        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO persona (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, json.dumps(value), datetime.utcnow().isoformat()),
            )

    def extract_and_store(self, user_command: str, action_taken: str) -> None:
        """
        Run a Groq call to detect preference signals in the command.
        E.g. 'Order lunch from Anjappar for 12' → { lunch_restaurant: 'Anjappar', team_size: 12 }
        Fire-and-forget — never blocks the main response.
        """
        prompt = f"""Extract any personal preference signals from this command and the action taken.
Return ONLY a JSON object of key-value pairs representing learned preferences.
If nothing to learn, return {{}}.

Examples of what to extract:
- preferred restaurant name
- team size / headcount
- default meeting duration
- preferred tone style
- frequently mentioned people
- usual work hours

Command: "{user_command}"
Action: "{action_taken}"

Return raw JSON only, no markdown."""

        try:
            response = self._groq.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            learned = json.loads(raw)
            for key, value in learned.items():
                if value:
                    self.set(key, value)
        except Exception:
            pass  # Non-critical — never crash the main flow


# ── ActionHistory ─────────────────────────────────────────────────────────────

class ActionHistory:
    """Append-only log of all actions taken by ARIA — powers the dashboard."""

    def __init__(self):
        init_db()

    def log(
        self,
        action: str,
        mode: str,
        summary: str,
        reasoning: str = "",
        payload: dict | None = None,
    ) -> int:
        """Log an action and return its ID (used by undo shield)."""
        with _get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO action_log (action, mode, summary, status, reasoning, payload, executed_at)
                   VALUES (?, ?, ?, 'executed', ?, ?, ?)""",
                (
                    action,
                    mode,
                    summary,
                    reasoning,
                    json.dumps(payload or {}),
                    datetime.utcnow().isoformat(),
                ),
            )
            return cur.lastrowid

    def mark_undone(self, action_id: int) -> None:
        with _get_conn() as conn:
            conn.execute(
                "UPDATE action_log SET status = 'undone' WHERE id = ?",
                (action_id,),
            )

    def get_recent(self, limit: int = 20) -> list[dict]:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]