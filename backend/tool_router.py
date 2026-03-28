"""
tool_router.py
──────────────
Maps a classified IntentResult to the correct tool and executes it.

Key design decisions:
  1. asyncio imported at the TOP — not at the bottom (that was the original bug).
  2. Undo registration happens AFTER history.log() so we always have a real action_id.
     The original code registered with action_id=0 then tried to patch it — that's broken.
  3. Each handler is a clean private method. No business logic in execute().
  4. All undo lambdas capture variables explicitly to avoid late-binding closure bugs.
"""

import asyncio
from typing import Any

from intent_classifier import Entities, IntentResult
from memory import ActionHistory, PersonaMemory
from undo_shield import undo_shield
from tools import calendar_tool, gmail_tool, linkedin_tool, notion_tool, slack_tool


class ToolRouter:
    def __init__(self, persona: PersonaMemory, history: ActionHistory):
        self.persona = persona
        self.history = history

    # ── Public entry point ─────────────────────────────────────────────────────

    async def execute(self, intent: IntentResult, raw_command: str) -> dict[str, Any]:
        """
        Route the classified intent to the correct tool and execute it.

        Flow:
          1. Call the appropriate handler based on intent.action
          2. Log the action to history → get real action_id
          3. Register undo handler using the real action_id
          4. Fire-and-forget persona learning in background
          5. Return result dict with action_id attached

        Returns a result dict. Always includes:
            - status  (str)
            - summary (str) — shown in the dashboard
            - action_id (int)
        """
        action  = intent.action
        prefs   = self.persona.get_all()
        result: dict[str, Any]

        # ── Dispatch ────────────────────────────────────────────────────────────
        if action == "send_email":
            result = await self._handle_send_email(intent, prefs)

        elif action == "create_event":
            result = await self._handle_create_event(intent, prefs)

        elif action == "search_linkedin":
            result = await self._handle_linkedin(intent, prefs)

        elif action == "slack_message":
            result = await self._handle_slack(intent, prefs)

        elif action == "notion_create":
            result = await self._handle_notion(intent, prefs)

        elif action == "chain":
            result = await self._handle_chain(intent, prefs, raw_command)

        else:
            result = {
                "status":  "unknown_action",
                "message": f"I understood your command but don't have a handler for '{action}' yet.",
                "summary": f"⚠️ Unknown action: {action}",
            }

        # ── Log to history — gives us the real action_id ────────────────────────
        action_id = self.history.log(
            action    = action,
            mode      = intent.mode,
            summary   = result.get("summary", str(result)[:120]),
            reasoning = intent.reasoning,
            payload   = result,
        )

        # ── Register undo with the REAL action_id ──────────────────────────────
        # Each branch captures its rollback variable explicitly in the lambda
        # to avoid Python late-binding closure bugs (all lambdas sharing last value).
        self._register_undo(action, action_id, result)

        # ── Attach action_id to result before returning ─────────────────────────
        result["action_id"] = action_id

        # ── Background persona learning — never blocks the response ─────────────
        asyncio.create_task(
            asyncio.to_thread(self.persona.extract_and_store, raw_command, action)
        )

        return result

    # ── Undo registration ──────────────────────────────────────────────────────

    def _register_undo(self, action: str, action_id: int, result: dict) -> None:
        """
        Register an undo handler only for actions that succeeded and are reversible.
        Uses explicit variable capture in each lambda to avoid closure bugs.
        """
        if action == "send_email" and result.get("status") == "sent":
            msg_id = result["message_id"]
            undo_shield.register(
                action_id = action_id,
                summary   = f"Email to {result.get('to')}: '{result.get('subject')}'",
                undo_fn   = lambda _id=msg_id: asyncio.to_thread(gmail_tool.recall_email, _id),
            )

        elif action == "create_event" and result.get("status") == "created":
            event_id = result["event_id"]
            undo_shield.register(
                action_id = action_id,
                summary   = f"Calendar event: '{result.get('title')}'",
                undo_fn   = lambda _id=event_id: asyncio.to_thread(calendar_tool.delete_event, _id),
            )

        elif action == "slack_message" and result.get("status") == "sent":
            ch = result["channel"]
            ts = result["ts"]
            undo_shield.register(
                action_id = action_id,
                summary   = f"Slack message in {result.get('channel')}",
                undo_fn   = lambda _ch=ch, _ts=ts: asyncio.to_thread(slack_tool.delete_message, _ch, _ts),
            )

        elif action == "notion_create" and result.get("status") == "created":
            page_id = result["page_id"]
            undo_shield.register(
                action_id = action_id,
                summary   = f"Notion page: '{result.get('title')}'",
                undo_fn   = lambda _id=page_id: asyncio.to_thread(notion_tool.archive_page, _id),
            )
        # linkedin, chain, other — no undo available (read-only or multi-step)

    # ── Action handlers ────────────────────────────────────────────────────────

    async def _handle_send_email(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities

        recipient = e.recipient or prefs.get("default_email_contact", "")
        subject   = e.subject or e.topic or "Following up"
        topic     = e.topic or "the matter we discussed"

        if not recipient:
            return {
                "status":  "missing_entity",
                "message": "Who should I send the email to?",
                "summary": "⚠️ Missing recipient for email",
            }

        result = await asyncio.to_thread(
            gmail_tool.send_email,
            recipient = recipient,
            subject   = subject,
            topic     = topic,
            tone      = intent.tone,
            persona   = prefs,
        )

        if result.get("status") == "sent":
            result["summary"] = f"✉️ Email sent to {recipient} — '{subject}'"

        return result

    async def _handle_create_event(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities

        title     = e.topic or e.subject or "Meeting"
        time_str  = e.time or "tomorrow at 10am"
        attendees = [e.recipient] if e.recipient else []
        duration  = int(prefs.get("default_meeting_duration_minutes", 60))

        result = await asyncio.to_thread(
            calendar_tool.create_event,
            title            = title,
            time_str         = time_str,
            attendees        = attendees,
            duration_minutes = duration,
        )

        if result.get("status") == "created":
            result["summary"] = f"📅 Event '{title}' created at {result['start']}"

        return result

    async def _handle_linkedin(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities

        company     = e.company or prefs.get("target_company", "TCS")
        location    = e.location or prefs.get("location", "Chennai")
        role_filter = "HR"

        result = await asyncio.to_thread(
            linkedin_tool.search_hr_contacts,
            company     = company,
            location    = location,
            role_filter = role_filter,
        )

        result["summary"] = f"🔍 Found {result.get('count', 0)} HR contacts at {company}"
        return result

    async def _handle_slack(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities

        channel = e.platform or e.recipient or prefs.get("default_slack_channel", "general")
        text    = e.topic or e.subject or "Message from ARIA"

        result = await asyncio.to_thread(
            slack_tool.send_message,
            channel = channel,
            text    = text,
        )

        if result.get("status") == "sent":
            result["summary"] = f"💬 Slack message sent to {channel}"
        elif result.get("status") == "channel_not_found":
            result["summary"] = f"⚠️ Slack channel '{channel}' not found"

        return result

    async def _handle_notion(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities

        title   = e.topic or e.subject or "New Note"
        content = (
            f"Created by ARIA from voice command.\n\n"
            f"Topic: {e.topic}\n"
            f"Time: {e.time or 'not specified'}\n"
        )

        result = await asyncio.to_thread(
            notion_tool.create_page,
            title   = title,
            content = content,
        )

        if result.get("status") == "created":
            result["summary"] = f"📝 Notion page '{title}' created"

        return result

    async def _handle_chain(self, intent: IntentResult, prefs: dict, raw_command: str) -> dict:
        """
        Execute a multi-step workflow sequentially.
        Each step is processed as an independent IntentResult.
        Steps run in order — failure of one step does not abort the rest (best-effort).
        """
        if not intent.chain_steps:
            return {
                "status":  "error",
                "message": "Chain command detected but no steps were provided.",
                "summary": "⚠️ Empty chain",
            }

        results      = []
        completed    = 0
        failed_steps = []

        for i, step in enumerate(intent.chain_steps):
            step_action = step.get("action", "other")
            step_entities_raw = step.get("entities", {})

            # Build a minimal IntentResult for this sub-step
            step_intent = IntentResult(
                action              = step_action,
                mode                = "ACT",
                entities            = Entities(**{
                    k: v for k, v in step_entities_raw.items()
                    if k in Entities.model_fields
                }),
                ambiguity_score     = 0.0,
                missing_entity      = "",
                clarifying_question = "",
                tone                = intent.tone,
                risk_level          = "low",
                chain_steps         = [],
                reasoning           = f"Chain step {i+1} from: {raw_command[:80]}",
            )

            step_result = await self.execute(step_intent, raw_command)
            status = step_result.get("status", "unknown")

            results.append({
                "step":    i + 1,
                "action":  step_action,
                "status":  status,
                "summary": step_result.get("summary", ""),
            })

            if status not in ("error", "missing_entity", "unknown_action", "channel_not_found"):
                completed += 1
            else:
                failed_steps.append(f"Step {i+1} ({step_action}): {step_result.get('message', status)}")

        return {
            "status":          "chain_complete",
            "steps_completed": completed,
            "steps_total":     len(intent.chain_steps),
            "steps":           results,
            "failed":          failed_steps,
            "summary": (
                f"⛓️ Chain: {completed}/{len(intent.chain_steps)} steps completed"
                + (f" — {len(failed_steps)} failed" if failed_steps else "")
            ),
        }