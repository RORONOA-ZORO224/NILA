"""
intent_classifier.py
────────────────────
ARIA's brain — every user command flows through here first.

Uses Groq (llama-3.3-70b-versatile) with structured JSON output to produce:
  - action type
  - mode: ACT / ASK / PAUSE
  - extracted entities
  - ambiguity + risk scores
  - tone detection
  - chain steps (for multi-step workflows)
"""

import json
import os
from typing import Any

from groq import Groq
from pydantic import BaseModel


# ── Pydantic models ────────────────────────────────────────────────────────────

class Entities(BaseModel):
    recipient:  str = ""   # Email address or person name
    time:       str = ""   # Natural language time expression
    topic:      str = ""   # Subject matter / what it's about
    platform:   str = ""   # Slack channel, Notion workspace, etc.
    company:    str = ""   # For LinkedIn searches
    location:   str = ""   # City / region
    subject:    str = ""   # Email subject line if distinct from topic


class IntentResult(BaseModel):
    action:              str                    # send_email | create_event | search_linkedin | slack_message | notion_create | chain | other
    mode:                str                    # ACT | ASK | PAUSE
    entities:            Entities
    ambiguity_score:     float                  # 0.0 → 1.0
    missing_entity:      str                    # Which field is missing (ASK mode)
    clarifying_question: str                    # Exactly one question (ASK mode)
    tone:                str                    # formal | casual | assertive | apologetic | urgent
    risk_level:          str                    # low | medium | high
    chain_steps:         list[dict[str, Any]]   # List of sub-actions for chain mode
    reasoning:           str                    # Why this mode was chosen (shown in dashboard)


# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are ARIA's intent classifier. Analyze the user's command and return ONLY a valid JSON \
object. No markdown fences, no explanation, no preamble — raw JSON only.

Return this exact structure:
{
  "action": "send_email | create_event | search_linkedin | slack_message | notion_create | chain | other",
  "mode": "ACT | ASK | PAUSE",
  "entities": {
    "recipient": "",
    "time": "",
    "topic": "",
    "platform": "",
    "company": "",
    "location": "",
    "subject": ""
  },
  "ambiguity_score": 0.0,
  "missing_entity": "",
  "clarifying_question": "",
  "tone": "formal | casual | assertive | apologetic | urgent",
  "risk_level": "low | medium | high",
  "chain_steps": [],
  "reasoning": ""
}

━━━ MODE DECISION RULES (apply strictly in order) ━━━

ACT   → ambiguity_score < 0.3 AND all required entities present AND risk_level = low
        Execute immediately. No questions.

ASK   → exactly ONE required entity missing OR ambiguity_score between 0.3 and 0.7
        Set clarifying_question to ONE precise question. Fill missing_entity field.

PAUSE → risk_level = high OR ambiguity_score > 0.7
        Show action preview for human confirmation before executing.

━━━ ACTION TYPES ━━━

send_email      → Write and send an email. Required entities: recipient, topic.
                  Subject auto-generated if missing.

create_event    → Create a Google Calendar event. Required entities: topic, time.
                  Attendees from recipient field (optional).

search_linkedin → Search LinkedIn for HR/recruiter contacts at a company.
                  Required entities: company.
                  Location defaults to user preference if missing.

slack_message   → Post a message to a Slack channel or DM.
                  Required entities: platform (channel name), topic.

notion_create   → Create a Notion page or database entry.
                  Required entities: topic.

chain           → 3 or more sequential actions across different apps.
                  Populate chain_steps with each sub-action object.
                  Each step: { "action": "...", "entities": { ... } }

other           → Command understood but no matching action type.

━━━ RISK LEVELS ━━━

low    → send a message, create an event, search, read, summarize, create a page
medium → edit/update existing records, reply to threads, reschedule events
high   → delete anything, cancel multiple events, bulk-send to many external people,
         financial actions, sending to unknown external contacts

━━━ TONE DETECTION ━━━

casual     → "hey", "drop a note", emoji hints, informal phrasing
formal     → "draft a proposal", "meeting with board", structured language
assertive  → "tell them again", "make sure they know", firm language
apologetic → "I messed up", "my fault", "sorry about", accountability language
urgent     → "ASAP", "right now", "immediately", "running late", time pressure

━━━ CHAIN STEPS FORMAT ━━━

For chain commands, list every step:
"chain_steps": [
  { "action": "send_email",   "entities": { "recipient": "ravi@co.com", "topic": "welcome" } },
  { "action": "create_event", "entities": { "topic": "Day 1 onboarding", "time": "Monday 9am" } },
  { "action": "slack_message","entities": { "platform": "general", "topic": "intern joined" } }
]

━━━ USER PREFERENCES ━━━

If user preferences are provided below, use them to auto-fill missing entities before
deciding whether to go ASK mode. E.g. if location is in preferences and company is
provided, do NOT ask for location — fill it from preferences and go ACT.
"""


# ── Classifier ─────────────────────────────────────────────────────────────────

class IntentClassifier:
    def __init__(self):
        self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self._model  = "llama-3.3-70b-versatile"

    def classify(self, user_command: str, persona_context: dict | None = None) -> IntentResult:
        """
        Classify a user command into a structured IntentResult.

        Args:
            user_command:    Raw text or voice transcript from the user.
            persona_context: Dict of learned preferences injected as context.
                             Allows auto-filling entities without asking the user again.

        Returns:
            IntentResult with action, mode, entities, scores, and reasoning.

        Raises:
            ValueError: If Groq returns malformed JSON after strip attempts.
        """
        system = _SYSTEM_PROMPT
        if persona_context:
            system += f"\n\nUSER PREFERENCES (use these to fill missing entities):\n{json.dumps(persona_context, indent=2)}"

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system",  "content": system},
                {"role": "user",    "content": user_command},
            ],
            temperature=0.1,    # Low = deterministic, consistent JSON structure
            max_tokens=900,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if the model wraps output anyway
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"IntentClassifier: Groq returned invalid JSON — {e}\nRaw: {raw[:300]}")

        # Normalize: chain_steps must always be a list
        if not isinstance(parsed.get("chain_steps"), list):
            parsed["chain_steps"] = []

        # Normalize: clamp ambiguity_score to [0.0, 1.0]
        score = parsed.get("ambiguity_score", 0.0)
        parsed["ambiguity_score"] = max(0.0, min(1.0, float(score)))

        # Normalize: ensure mode is valid
        if parsed.get("mode") not in ("ACT", "ASK", "PAUSE"):
            parsed["mode"] = "ASK"

        return IntentResult(**parsed)