"""
tools/gmail_tool.py
───────────────────
Gmail operations via Google API.
  - send_email        → compose and send
  - search_emails     → query inbox, return summaries
  - recall_email      → delete from sent (undo shield target)
  - reply_to_thread   → reply in an existing thread
"""

import base64
import os
from email.mime.text import MIMEText
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from groq import Groq

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))


def _get_service():
    """Build and return an authenticated Gmail service."""
    creds = None
    token_path = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _draft_email_body(recipient: str, topic: str, tone: str, persona: dict) -> str:
    """Use Groq to write an email body matching the detected tone."""
    tone_instructions = {
        "casual": "Write in a warm, friendly, conversational tone. Short sentences. Natural.",
        "formal": "Write in professional formal language. No contractions. Structured.",
        "assertive": "Write firmly and directly. Clear deadlines or points. Confident.",
        "apologetic": "Write with genuine accountability. Acknowledge the issue. Offer a solution.",
        "urgent": "Write concisely and urgently. Lead with the key point immediately.",
    }
    instruction = tone_instructions.get(tone, tone_instructions["casual"])

    user_name = persona.get("name", "the sender")
    extra_context = f"Sender's name: {user_name}" if user_name else ""

    prompt = f"""Write a complete email body (no subject line, no greeting/sign-off headers — just the body).
Recipient: {recipient}
Topic/request: {topic}
Tone instruction: {instruction}
{extra_context}

Output only the email body text."""

    response = _groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()


def send_email(
    recipient: str,
    subject: str,
    topic: str,
    tone: str = "casual",
    persona: dict | None = None,
) -> dict[str, Any]:
    """
    Compose and send an email. Returns message_id for undo registration.
    """
    persona = persona or {}
    body = _draft_email_body(recipient, topic, tone, persona)

    message = MIMEText(body)
    message["to"] = recipient
    message["subject"] = subject
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service = _get_service()
    sent = service.users().messages().send(
        userId="me", body={"raw": encoded}
    ).execute()

    return {
        "status": "sent",
        "message_id": sent["id"],
        "to": recipient,
        "subject": subject,
        "body_preview": body[:120] + "...",
    }


def recall_email(message_id: str) -> dict[str, Any]:
    """
    Undo: move sent email to trash before recipient reads it.
    Gmail doesn't have true recall — trash is the closest we get.
    """
    service = _get_service()
    service.users().messages().trash(userId="me", id=message_id).execute()
    return {"status": "recalled", "message_id": message_id}


def search_emails(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search inbox and return summarized results."""
    service = _get_service()
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    summaries = []
    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        summaries.append({
            "id": m["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
        })

    return {"status": "found", "count": len(summaries), "emails": summaries}


def reply_to_thread(thread_id: str, message_id: str, body: str, to: str) -> dict[str, Any]:
    """Reply within an existing Gmail thread."""
    message = MIMEText(body)
    message["to"] = to
    message["In-Reply-To"] = message_id
    message["References"] = message_id
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service = _get_service()
    sent = service.users().messages().send(
        userId="me", body={"raw": encoded, "threadId": thread_id}
    ).execute()

    return {"status": "replied", "message_id": sent["id"], "thread_id": thread_id}