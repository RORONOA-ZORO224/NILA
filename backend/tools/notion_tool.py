"""
tools/notion_tool.py
────────────────────
Notion operations via notion-client SDK.
  - create_page        → new page in workspace
  - add_database_entry → add row to a tracked database (e.g. job applications)
  - search_pages       → full-text search across workspace
  - archive_page       → soft-delete (always recoverable) — undo target
"""

import os
from typing import Any

from notion_client import Client


def _get_client() -> Client:
    return Client(auth=os.getenv("NOTION_API_KEY"))


def create_page(title: str, content: str, parent_page_id: str | None = None) -> dict[str, Any]:
    """Create a new Notion page with markdown-style content."""
    client = _get_client()

    # Determine parent — use env var default if no parent specified
    parent: dict[str, Any]
    if parent_page_id:
        parent = {"type": "page_id", "page_id": parent_page_id}
    else:
        # Fall back to database if configured, else workspace root
        db_id = os.getenv("NOTION_DATABASE_ID")
        if db_id:
            parent = {"type": "database_id", "database_id": db_id}
        else:
            return {"status": "error", "message": "No parent page or database configured"}

    # Split content into paragraph blocks (max 2000 chars per block per Notion limits)
    blocks = [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            },
        }
        for chunk in [content[i:i+1900] for i in range(0, len(content), 1900)]
    ]

    page = client.pages.create(
        parent=parent,
        properties={"title": {"title": [{"text": {"content": title}}]}},
        children=blocks,
    )

    return {
        "status": "created",
        "page_id": page["id"],
        "title": title,
        "url": page.get("url", ""),
    }


def add_database_entry(database_id: str, properties: dict[str, Any]) -> dict[str, Any]:
    """
    Add a row to a Notion database.
    properties: dict mapping column names to values.
    Example: { "Name": "Ravi Kumar", "Company": "TCS", "Status": "Sent" }
    """
    client = _get_client()

    # Build Notion property objects from plain values
    notion_props: dict[str, Any] = {}
    for key, value in properties.items():
        if key.lower() == "name" or key.lower() == "title":
            notion_props[key] = {"title": [{"text": {"content": str(value)}}]}
        else:
            notion_props[key] = {"rich_text": [{"text": {"content": str(value)}}]}

    page = client.pages.create(
        parent={"type": "database_id", "database_id": database_id},
        properties=notion_props,
    )

    return {
        "status": "entry_added",
        "page_id": page["id"],
        "database_id": database_id,
    }


def search_pages(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search Notion workspace for pages matching query."""
    client = _get_client()
    results = client.search(query=query, page_size=max_results)
    pages = []
    for obj in results.get("results", []):
        title = ""
        props = obj.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                title_arr = prop.get("title", [])
                if title_arr:
                    title = title_arr[0].get("plain_text", "")
                    break
        pages.append({
            "id": obj["id"],
            "title": title,
            "url": obj.get("url", ""),
            "type": obj.get("object", ""),
        })
    return {"status": "ok", "count": len(pages), "pages": pages}


def archive_page(page_id: str) -> dict[str, Any]:
    """Archive (soft-delete) a page — used as undo target for create_page."""
    client = _get_client()
    client.pages.update(page_id=page_id, archived=True)
    return {"status": "archived", "page_id": page_id}


def log_job_application(
    name: str, company: str, role: str, email: str, linkedin_url: str = ""
) -> dict[str, Any]:
    """Convenience: log a LinkedIn outreach in the job applications Notion database."""
    db_id = os.getenv("NOTION_DATABASE_ID")
    if not db_id:
        return {"status": "error", "message": "NOTION_DATABASE_ID not set"}

    return add_database_entry(
        database_id=db_id,
        properties={
            "Name": name,
            "Company": company,
            "Role": role,
            "Email": email,
            "LinkedIn": linkedin_url,
            "Status": "Sent",
        },
    )