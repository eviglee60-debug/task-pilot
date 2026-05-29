"""Outlook calendar integration via Microsoft Graph API.

Creates calendar events from confirmed task proposals.
Uses the same OAuth token as the email connector.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from src.models.schemas import TaskProposal

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class CalendarService:
    """Manages Outlook calendar events via Microsoft Graph API."""

    def __init__(self, access_token: str, calendar_id: str = "calendar"):
        self.access_token = access_token
        self.calendar_id = calendar_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def create_event(self, task: TaskProposal) -> str:
        """Create an Outlook calendar event from a confirmed task.

        Returns the created event ID.
        """
        if not task.deadline:
            raise ValueError("Cannot create calendar event without a deadline")

        # Set reminder based on priority
        reminder_minutes = {
            "urgent": 1440,   # 1 day before
            "high": 720,      # 12 hours before
            "normal": 60,     # 1 hour before
            "low": 15,        # 15 minutes before
        }.get(task.priority, 60)

        # Event duration: 30 min for normal, 1 hour for urgent/high
        duration_minutes = 60 if task.priority in ("urgent", "high") else 30

        event_body = self._build_event_body(task, duration_minutes)

        import httpx

        resp = httpx.post(
            f"{GRAPH_BASE}/me/calendars/{self.calendar_id}/events",
            headers=self._headers(),
            json=event_body,
            timeout=30,
        )
        resp.raise_for_status()
        event_data = resp.json()
        event_id = event_data["id"]

        logger.info(
            "Created Outlook event %s for task %s (deadline: %s)",
            event_id,
            task.id,
            task.deadline,
        )
        return event_id

    def _build_event_body(
        self, task: TaskProposal, duration_minutes: int
    ) -> dict:
        """Build the Graph API event request body."""
        # Priority mapping
        importance = {
            "urgent": "high",
            "high": "high",
            "normal": "normal",
            "low": "low",
        }.get(task.priority, "normal")

        # Category tag
        category = task.category or "task-pilot"

        # Subject with priority prefix
        prefix = {"urgent": "[紧急]", "high": "[重要]"}.get(task.priority, "")
        subject = f"{prefix} {task.title}".strip()

        # Body with context
        body_text = (
            f"{task.description}\n\n"
            f"---\n"
            f"来源: {task.source.value}\n"
            f"发送者: {task.sender}\n"
            f"分类: {task.category}\n"
            f"优先级: {task.priority}\n"
            f"任务ID: {task.id}"
        )

        deadline = task.deadline

        return {
            "subject": subject,
            "body": {
                "contentType": "text",
                "content": body_text,
            },
            "start": {
                "dateTime": deadline.isoformat(),
                "timeZone": "Asia/Shanghai",
            },
            "end": {
                "dateTime": (deadline + timedelta(minutes=duration_minutes)).isoformat(),
                "timeZone": "Asia/Shanghai",
            },
            "importance": importance,
            "reminderMinutesBeforeStart": 60,
            "isReminderOn": True,
            "categories": [category],
        }
