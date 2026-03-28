"""
tools/slack_tool.py
───────────────────
Slack operations via slack-sdk.
  - send_message      → DM or channel post
  - delete_message    → undo target
  - set_reminder      → /remind equivalent
  - search_channel    → find a channel by name
  - list_channels     → for routing unknown channel names
"""

import os
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def _get_client() -> WebClient:
    return WebClient(token=os.getenv("SLACK_BOT_TOKEN"))


def send_message(channel: str, text: str) -> dict[str, Any]:
    """
    Send a message to a channel or DM.
    channel: channel name (e.g. '#general'), channel ID, or user ID.
    """
    client = _get_client()

    # Normalize channel name — add # if missing for named channels
    if not channel.startswith("#") and not channel.startswith("C") and not channel.startswith("U"):
        channel = f"#{channel}"

    response = client.chat_postMessage(channel=channel, text=text)

    return {
        "status": "sent",
        "channel": response["channel"],
        "ts": response["ts"],  # Slack message timestamp — used for deletion
        "text": text,
    }


def delete_message(channel: str, ts: str) -> dict[str, Any]:
    """Delete a Slack message by channel + timestamp (undo target)."""
    client = _get_client()
    client.chat_delete(channel=channel, ts=ts)
    return {"status": "deleted", "channel": channel, "ts": ts}


def set_reminder(text: str, when: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Set a Slack reminder via API.
    when: natural language time string or Unix timestamp string.
    """
    client = _get_client()
    # Use authenticated user if no target specified
    response = client.reminders_add(text=text, time=when, user=user_id)
    return {
        "status": "reminder_set",
        "reminder_id": response["reminder"]["id"],
        "text": text,
        "time": when,
    }


def list_channels(limit: int = 50) -> dict[str, Any]:
    """List public channels — used for routing by channel name."""
    client = _get_client()
    response = client.conversations_list(limit=limit, types="public_channel,private_channel")
    channels = [
        {"id": c["id"], "name": c["name"]}
        for c in response.get("channels", [])
    ]
    return {"status": "ok", "channels": channels}


def search_and_send(channel_name: str, text: str) -> dict[str, Any]:
    """
    Find a channel by name then send a message.
    Handles the common case where user says 'post in dev-team'.
    """
    channels_data = list_channels()
    match = next(
        (c for c in channels_data["channels"] if c["name"].lower() == channel_name.lower()),
        None,
    )
    if not match:
        return {
            "status": "channel_not_found",
            "message": f"Channel '{channel_name}' not found. Available: {[c['name'] for c in channels_data['channels'][:5]]}",
        }
    return send_message(match["id"], text)