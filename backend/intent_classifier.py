"""
intent_classifier.py
────────────────────
ARIA's brain — every user command flows through here first.

Uses Groq (llama-3.3-70b-versatile) with structured JSON output.

Fixes applied:
  - Exponential backoff retry (3 attempts) on Groq API failures
  - Explicit timeout on API calls
"""

import json
import os
import time
from typing import Any

from groq import Groq
from pydantic import BaseModel


# ── Pydantic models ────────────────────────────────────────────────────────────

class Entities(BaseModel):
    recipient:  str = ""
    time:       str = ""
    topic:      str = ""
    platform:   str = ""
    company:    str = ""
    location:   str = ""
    subject:    str = ""


class IntentResult(BaseModel):
    action:              str
    mode:                str
    entities:            Entities
    ambiguity_score:     float
    missing_entity:      str
    clarifying_question: str
    tone:                str
    risk_level:          str
    chain_steps:         list[dict[str, Any]]
    reasoning:           str


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
ASK   → exactly ONE required entity missing OR ambiguity_score between 0.3 and 0.7
PAUSE → risk_level = high OR ambiguity_score > 0.7

━━━ ACTION TYPES ━━━

send_email      → Required entities: recipient, topic.
create_event    → Required entities: topic, time.
search_linkedin → Required entities: company.
slack_message   → Required entities: platform, topic.
notion_create   → Required entities: topic.
chain           → 3+ sequential actions. Populate chain_steps.
other           → Command understood but no matching action.

━━━ RISK LEVELS ━━━

low    → send message, create event, search, read, summarize, create page
medium → edit/update existing records, reply to threads, reschedule events
high   → delete anything, cancel multiple events, bulk-send to external people,
         financial actions, sending to unknown external contacts

━━━ TONE DETECTION ━━━

casual     → "hey", "drop a note", emoji hints, informal phrasing
formal     → "draft a proposal", "meeting with board", structured language
assertive  → "tell them again", "make sure they know", firm language
apologetic → "I messed up", "my fault", accountability language
urgent     → "ASAP", "right now", "immediately", time pressure

━━━ USER PREFERENCES ━━━

If user preferences are provided, use them to auto-fill missing entities before
deciding ASK mode. E.g. if location is in preferences and company is provided,
fill location from preferences and go ACT.
"""


# ── Classifier ─────────────────────────────────────────────────────────────────

class IntentClassifier:
    MAX_RETRIES = 3

    def __init__(self):
        self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self._model  = "llama-3.3-70b-versatile"

    def classify(self, user_command: str, persona_context: dict | None = None) -> IntentResult:
        """
        Classify a user command into a structured IntentResult.
        Retries up to 3 times with exponential backoff on API or JSON errors.
        """
        system = _SYSTEM_PROMPT
        if persona_context:
            system += f"\n\nUSER PREFERENCES:\n{json.dumps(persona_context, indent=2)}"

        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user_command},
                    ],
                    temperature=0.1,
                    max_tokens=900,
                    timeout=15.0,
                )

                raw = response.choices[0].message.content.strip()

                # Strip markdown fences
                if raw.startswith("```"):
                    parts = raw.split("```")
                    raw = parts[1] if len(parts) > 1 else parts[0]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                parsed = json.loads(raw)

                # Normalize
                if not isinstance(parsed.get("chain_steps"), list):
                    parsed["chain_steps"] = []
                score = parsed.get("ambiguity_score", 0.0)
                parsed["ambiguity_score"] = max(0.0, min(1.0, float(score)))
                if parsed.get("mode") not in ("ACT", "ASK", "PAUSE"):
                    parsed["mode"] = "ASK"

                return IntentResult(**parsed)

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                last_error = e
                wait = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait)
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                time.sleep(wait)

        # All retries exhausted — return a safe fallback
        return IntentResult(
            action="other",
            mode="ASK",
            entities=Entities(),
            ambiguity_score=1.0,
            missing_entity="command",
            clarifying_question="I had trouble understanding that. Could you rephrase your request?",
            tone="casual",
            risk_level="low",
            chain_steps=[],
            reasoning=f"Classifier failed after {self.MAX_RETRIES} attempts: {last_error}",
        )