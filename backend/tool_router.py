"""
tool_router.py
──────────────
Routes classified intents to the appropriate tool.
Registers undo handlers ONCE per action, keyed by the real action_id from history.log().
"""

import asyncio
from typing import Any

from intent_classifier import IntentResult
from memory import ActionHistory, PersonaMemory
from undo_shield import undo_shield
from tools import calendar_tool, gmail_tool, linkedin_tool, notion_tool, slack_tool


class ToolRouter:
    def __init__(self, persona: PersonaMemory, history: ActionHistory):
        self.persona = persona
        self.history = history

    async def execute(self, intent: IntentResult, raw_command: str) -> dict[str, Any]:
        """
        Route the classified intent to the appropriate tool.
        Undo is registered AFTER history.log() so we have the real action_id.
        """
        action = intent.action
        prefs = self.persona.get_all()

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
                "status": "unknown_action",
                "message": f"Don't know how to handle action '{action}' yet.",
            }

        # Log to history — this gives us the real action_id
        action_id = self.history.log(
            action=action,
            mode=intent.mode,
            summary=result.get("summary", str(result)),
            reasoning=intent.reasoning,
            payload=result,
        )
        result["action_id"] = action_id

        # Register undo ONCE using the real action_id
        self._register_undo(action, action_id, result)

        # Background preference extraction — non-blocking
        asyncio.create_task(
            asyncio.to_thread(self.persona.extract_and_store, raw_command, action)
        )

        return result

    def _register_undo(self, action: str, action_id: int, result: dict) -> None:
        """Register a single undo entry for reversible actions."""
        if action == "send_email" and result.get("status") == "sent":
            msg_id = result["message_id"]
            undo_shield.register(
                action_id=action_id,
                summary=f"Email to {result.get('to')}: '{result.get('subject')}'",
                undo_fn=lambda: asyncio.to_thread(gmail_tool.recall_email, msg_id),
            )
        elif action == "create_event" and result.get("status") == "created":
            event_id = result["event_id"]
            undo_shield.register(
                action_id=action_id,
                summary=f"Calendar event: '{result.get('title')}'",
                undo_fn=lambda: asyncio.to_thread(calendar_tool.delete_event, event_id),
            )
        elif action == "slack_message" and result.get("status") == "sent":
            ch, ts = result["channel"], result["ts"]
            undo_shield.register(
                action_id=action_id,
                summary=f"Slack message in {result.get('channel')}",
                undo_fn=lambda: asyncio.to_thread(slack_tool.delete_message, ch, ts),
            )
        elif action == "notion_create" and result.get("status") == "created":
            page_id = result["page_id"]
            undo_shield.register(
                action_id=action_id,
                summary=f"Notion page: '{result.get('title')}'",
                undo_fn=lambda: asyncio.to_thread(notion_tool.archive_page, page_id),
            )

    # ── Action handlers ───────────────────────────────────────────────────────

    async def _handle_send_email(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities
        recipient = e.recipient or prefs.get("default_email_contact", "")
        subject = e.subject or e.topic or "Following up"
        topic = e.topic or "the matter we discussed"

        if not recipient:
            return {"status": "missing_entity", "message": "Who should I send the email to?"}

        result = await asyncio.to_thread(
            gmail_tool.send_email,
            recipient=recipient,
            subject=subject,
            topic=topic,
            tone=intent.tone,
            persona=prefs,
        )

        if result.get("status") == "sent":
            result["summary"] = f"✉️ Email sent to {recipient} — '{subject}'"

        return result

    async def _handle_create_event(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities
        title = e.topic or e.subject or "Meeting"
        time_str = e.time or "tomorrow at 10am"
        attendees = [e.recipient] if e.recipient else []

        result = await asyncio.to_thread(
            calendar_tool.create_event,
            title=title,
            time_str=time_str,
            attendees=attendees,
            duration_minutes=int(prefs.get("default_meeting_duration_minutes", 60)),
        )

        if result.get("status") == "created":
            result["summary"] = f"📅 Event '{title}' created at {result['start']}"

        return result

    async def _handle_linkedin(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities
        company = e.company or "TCS"
        location = e.location or prefs.get("location", "Chennai")

        result = await asyncio.to_thread(
            linkedin_tool.search_hr_contacts,
            company=company,
            location=location,
            role_filter="HR",
        )
        result["summary"] = f"🔍 Found {result['count']} HR contacts at {company}"
        return result

    async def _handle_slack(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities
        channel = e.platform or e.recipient or "general"
        text = e.topic or e.subject or "Message from ARIA"

        result = await asyncio.to_thread(slack_tool.send_message, channel=channel, text=text)

        if result.get("status") == "sent":
            result["summary"] = f"💬 Slack message sent to {channel}"

        return result

    async def _handle_notion(self, intent: IntentResult, prefs: dict) -> dict:
        e = intent.entities
        title = e.topic or e.subject or "New Note"
        content = f"Created by ARIA from voice command.\nTopic: {e.topic}"

        result = await asyncio.to_thread(
            notion_tool.create_page, title=title, content=content
        )

        if result.get("status") == "created":
            result["summary"] = f"📝 Notion page '{title}' created"

        return result

    async def _handle_chain(self, intent: IntentResult, prefs: dict, raw_command: str) -> dict:
        """Execute a multi-step workflow sequentially."""
        results = []
        for step in intent.chain_steps:
            step_action = step.get("action", "other")
            from intent_classifier import Entities
            step_intent = IntentResult(
                action=step_action,
                mode="ACT",
                entities=Entities(**step.get("entities", {})),
                ambiguity_score=0.0,
                missing_entity="",
                clarifying_question="",
                tone=intent.tone,
                risk_level="low",
                chain_steps=[],
                reasoning=f"Chain step from: {raw_command}",
            )
            step_result = await self.execute(step_intent, raw_command)
            results.append({
                "step": step_action,
                "status": step_result.get("status"),
                "summary": step_result.get("summary", ""),
            })

        return {
            "status": "chain_complete",
            "steps_completed": len(results),
            "steps": results,
            "summary": f"⛓️ Chain completed: {len(results)} actions executed",
        }