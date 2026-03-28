"""
undo_shield.py
──────────────
30-second reversible action window.
Every executed action registers an undo handler here.
The frontend polls for active undo tokens and shows a countdown toast.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

UNDO_WINDOW = int(__import__("os").getenv("UNDO_WINDOW_SECONDS", "30"))


@dataclass
class UndoEntry:
    action_id: int
    summary: str
    executed_at: float
    undo_fn: Callable[[], Coroutine]  # async callable that reverses the action
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def expires_at(self) -> float:
        return self.executed_at + UNDO_WINDOW

    @property
    def seconds_remaining(self) -> int:
        remaining = self.expires_at - time.time()
        return max(0, int(remaining))

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class UndoShield:
    """
    In-memory store of pending undo entries.
    Keyed by action_id for O(1) lookup.
    """

    def __init__(self):
        self._store: dict[int, UndoEntry] = {}

    def register(
        self,
        action_id: int,
        summary: str,
        undo_fn: Callable[[], Coroutine],
        metadata: dict | None = None,
    ) -> None:
        self._store[action_id] = UndoEntry(
            action_id=action_id,
            summary=summary,
            executed_at=time.time(),
            undo_fn=undo_fn,
            metadata=metadata or {},
        )

    async def execute_undo(self, action_id: int) -> dict[str, Any]:
        """
        Attempt to undo the action. Returns status dict.
        Raises ValueError if expired or not found.
        """
        entry = self._store.get(action_id)
        if not entry:
            raise ValueError(f"No undo entry found for action {action_id}")
        if entry.is_expired:
            self._store.pop(action_id, None)
            raise ValueError("Undo window expired (30 seconds have passed)")

        await entry.undo_fn()
        self._store.pop(action_id, None)
        return {"status": "undone", "action_id": action_id, "summary": entry.summary}

    def get_active(self) -> list[dict]:
        """Return all non-expired undo entries for the frontend countdown."""
        now = time.time()
        expired = [aid for aid, e in self._store.items() if e.is_expired]
        for aid in expired:
            self._store.pop(aid, None)

        return [
            {
                "action_id": e.action_id,
                "summary": e.summary,
                "seconds_remaining": e.seconds_remaining,
            }
            for e in self._store.values()
        ]

    def purge_expired(self) -> None:
        expired = [aid for aid, e in self._store.items() if e.is_expired]
        for aid in expired:
            self._store.pop(aid, None)


# Global singleton — shared across the FastAPI app
undo_shield = UndoShield()