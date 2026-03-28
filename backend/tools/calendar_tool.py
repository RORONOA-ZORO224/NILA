"""
tools/calendar_tool.py
──────────────────────
Google Calendar operations.
  - create_event       → parse natural language time, invite attendees
  - list_events        → upcoming events with conflict detection
  - delete_event       → undo target
  - reschedule_event   → find and update a matching event
  - find_conflicts     → check if a time slot is free
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from groq import Groq

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))


def _get_service():
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

    return build("calendar", "v3", credentials=creds)


def _parse_natural_time(time_str: str) -> dict[str, str]:
    """
    Use Groq to convert natural language time to ISO 8601.
    Returns { start: ISO, end: ISO } assuming 1-hour default duration.
    """
    now = datetime.now(timezone.utc).isoformat()
    prompt = f"""Convert this natural language time expression to ISO 8601 datetime.
Current UTC time: {now}
Time expression: "{time_str}"

Return ONLY a JSON object:
{{"start": "YYYY-MM-DDTHH:MM:SS+05:30", "end": "YYYY-MM-DDTHH:MM:SS+05:30"}}
Assume IST (UTC+5:30). Default event duration: 1 hour. Raw JSON only."""

    response = _groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=100,
    )
    import json
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)


def create_event(
    title: str,
    time_str: str,
    attendees: list[str] | None = None,
    description: str = "",
    duration_minutes: int = 60,
) -> dict[str, Any]:
    """Create a calendar event with natural language time parsing."""
    time_range = _parse_natural_time(time_str)

    event_body: dict[str, Any] = {
        "summary": title,
        "description": description,
        "start": {"dateTime": time_range["start"], "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": time_range["end"], "timeZone": "Asia/Kolkata"},
    }

    if attendees:
        event_body["attendees"] = [{"email": a} for a in attendees]
        event_body["guestsCanInviteOthers"] = False

    service = _get_service()

    # Conflict check before creating
    conflicts = _check_conflicts(time_range["start"], time_range["end"])
    if conflicts:
        conflict_titles = [c["summary"] for c in conflicts]
        return {
            "status": "conflict_detected",
            "conflicts": conflict_titles,
            "message": f"Time conflicts with: {', '.join(conflict_titles)}. Please confirm or choose a different time.",
        }

    created = service.events().insert(calendarId="primary", body=event_body).execute()

    return {
        "status": "created",
        "event_id": created["id"],
        "title": title,
        "start": time_range["start"],
        "end": time_range["end"],
        "attendees": attendees or [],
        "html_link": created.get("htmlLink", ""),
    }


def _check_conflicts(start_iso: str, end_iso: str) -> list[dict]:
    """Return any events that overlap with the given time range."""
    service = _get_service()
    result = service.events().list(
        calendarId="primary",
        timeMin=start_iso,
        timeMax=end_iso,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])


def list_events(days_ahead: int = 3) -> dict[str, Any]:
    """List upcoming events in the next N days."""
    service = _get_service()
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    formatted = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        formatted.append({
            "id": e["id"],
            "title": e.get("summary", "(no title)"),
            "start": start,
            "attendees": [a["email"] for a in e.get("attendees", [])],
        })

    return {"status": "ok", "events": formatted, "count": len(formatted)}


def delete_event(event_id: str) -> dict[str, Any]:
    """Delete a calendar event — used as undo target for create_event."""
    service = _get_service()
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return {"status": "deleted", "event_id": event_id}


def reschedule_event(title_keyword: str, new_time_str: str) -> dict[str, Any]:
    """Find an event by keyword in title and move it to a new time."""
    events_data = list_events(days_ahead=7)
    matching = [
        e for e in events_data["events"]
        if title_keyword.lower() in e["title"].lower()
    ]

    if not matching:
        return {"status": "not_found", "message": f"No event found matching '{title_keyword}'"}
    if len(matching) > 1:
        titles = [e["title"] for e in matching]
        return {
            "status": "ambiguous",
            "matches": titles,
            "message": f"Multiple matches: {', '.join(titles)}. Which one?",
        }

    event_id = matching[0]["id"]
    time_range = _parse_natural_time(new_time_str)
    service = _get_service()

    updated = service.events().patch(
        calendarId="primary",
        eventId=event_id,
        body={
            "start": {"dateTime": time_range["start"], "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": time_range["end"], "timeZone": "Asia/Kolkata"},
        },
    ).execute()

    return {
        "status": "rescheduled",
        "event_id": event_id,
        "title": matching[0]["title"],
        "new_start": time_range["start"],
    }