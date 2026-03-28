"""
intent_classifier.py
────────────────────
ARIA's brain. Every user command flows through here.
Uses Groq (llama-3.3-70b-versatile) to produce a structured JSON decision:
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

# ── Pydantic models for type-safe classifier output ──────────────────────────

class Entities(BaseModel):
    recipient: str = ""
    time: str = ""
    topic: str = ""
    platform: str = ""
    company: str = ""
    location: str = ""
    subject: str = ""

class IntentResult(BaseModel):
    action: str           # send_email | create_event | search_linkedin | slack_message | notion_create | chain | other
    mode: str             # ACT | ASK | PAUSE
    entities: Entities
    ambiguity_score: float
    missing_entity: str
    clarifying_question: str
    tone: str             # formal | casual | assertive | apologetic | urgent
    risk_level: str       # low | medium | high
    chain_steps: list[dict[str, Any]]
    reasoning: str

# ── System prompt ─────────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM_PROMPT = """You are ARIA's intent classifier. Analyze the user's command and return ONLY a valid JSON object. No markdown, no explanation — raw JSON only.

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

DECISION RULES — apply strictly:

ACT   → ambiguity_score < 0.3  AND  all required entities present  AND  risk_level = low
        Execute immediately. No questions.

ASK   → exactly ONE entity missing  OR  ambiguity_score 0.3–0.7
        Ask exactly ONE clarifying question. Fill clarifying_question field.

PAUSE → risk_level = high  OR  ambiguity_score > 0.7
        Show preview for human confirmation before executing.

RISK LEVELS:
  low    → send message, create event, search, read, summarize
  medium → update/edit existing records, send to external unknown contacts
  high   → delete, cancel multiple events, bulk send to many people, financial actions

CHAIN  → command involves 3+ sequential actions across different apps
         List each step as { "action": "...", "entities": {...} } in chain_steps.

TONE DETECTION:
  casual    → informal language, emoji hints, "hey", "drop a note"
  formal    → "draft a proposal", "meeting with board"
  assertive → "tell them again", "make sure they know"
  apologetic → "I messed up", "my fault", "sorry about"
  urgent    → "ASAP", "right now", "immediately", "running late"

Use user preferences from context (if provided) to auto-fill known entities.
"""

# ── Classifier class ──────────────────────────────────────────────────────────

class IntentClassifier:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.3-70b-versatile"

    def classify(self, user_command: str, persona_context: dict | None = None) -> IntentResult:
        """
        Classify a user command into a structured IntentResult.
        persona_context: dict of learned preferences injected as few-shot context.
        """
        context_block = ""
        if persona_context:
            context_block = f"\n\nUSER PREFERENCES (use to fill missing entities):\n{json.dumps(persona_context, indent=2)}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT + context_block},
                {"role": "user", "content": user_command},
            ],
            temperature=0.1,   # Low temperature = deterministic, consistent JSON
            max_tokens=800,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if model wraps output anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        parsed = json.loads(raw)

        # Normalize: ensure chain_steps is always a list
        if not isinstance(parsed.get("chain_steps"), list):
            parsed["chain_steps"] = []

        return IntentResult(**parsed)