"""Outlook calendar integration via local COM automation.

Creates calendar events from confirmed task proposals.
No OAuth needed — uses the already-logged-in Outlook client.

Reminder strategy (from user preference):
    时限长度 → 提前提醒
    4个月   → 2个月
    2个月   → 1个月
    1个月   → 1周
    15天    → 5天
    10天    → 3天
    7天     → 2天
    3天     → 1天
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.models.schemas import TaskProposal

logger = logging.getLogger(__name__)

# Reminder lookup table: (max days, reminder timedelta)
REMINDER_TABLE: list[tuple[int, timedelta]] = [
    (120, timedelta(days=60)),   # 4个月 → 2个月
    (60,  timedelta(days=30)),   # 2个月 → 1个月
    (30,  timedelta(days=7)),    # 1个月 → 1周
    (15,  timedelta(days=5)),    # 15天 → 5天
    (10,  timedelta(days=3)),    # 10天 → 3天
    (7,   timedelta(days=2)),    # 7天 → 2天
    (3,   timedelta(days=1)),    # 3天 → 1天
]


def compute_reminder_minutes(deadline: datetime) -> int:
    """Compute reminder minutes based on how far the deadline is."""
    now = datetime.now()
    days_until = (deadline - now).days

    for max_days, reminder_delta in REMINDER_TABLE:
        if days_until >= max_days:
            # Deadline is far away, remind by the table
            return int(reminder_delta.total_seconds() / 60)

    # Default: remind 1 hour before
    return 60


class ComCalendarService:
    """Manages Outlook calendar events via local COM automation."""

    def __init__(self, calendar_name: str = ""):
        self.calendar_name = calendar_name

    def create_event(self, task: TaskProposal) -> str:
        """Create an Outlook calendar event from a confirmed task.

        Returns the created event EntryID.
        """
        if not task.deadline:
            raise ValueError("Cannot create calendar event without a deadline")

        return self._create_event_sync(task)

    def _create_event_sync(self, task: TaskProposal) -> str:
        """Synchronous COM call — runs in thread pool."""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            return self._create_event_inner(task, win32com.client)
        finally:
            pythoncom.CoUninitialize()

    def _create_event_inner(self, task: TaskProposal, win32com_client) -> str:
        """Inner create logic — COM must be initialized before calling."""
        outlook = win32com_client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")

        # Get calendar folder
        calendar = self._get_calendar(ns)
        if calendar is None:
            raise RuntimeError("Cannot access Outlook calendar")

        # Create appointment
        appt = calendar.Items.Add()

        # Priority prefix
        prefix = {"urgent": "[紧急]", "high": "[重要]"}.get(task.priority, "")
        appt.Subject = f"{prefix} {task.title}".strip()

        # Body with context
        appt.Body = (
            f"{task.description}\n\n"
            f"---\n"
            f"来源: {task.source.value}\n"
            f"发送者: {task.sender}\n"
            f"分类: {task.category}\n"
            f"优先级: {task.priority}\n"
            f"任务ID: {task.id}"
        )

        # Time
        deadline = task.deadline
        appt.Start = deadline

        # Duration: urgent/high = 1 hour, others = 30 min
        duration_minutes = 60 if task.priority in ("urgent", "high") else 30
        appt.End = deadline + timedelta(minutes=duration_minutes)

        # Reminder
        reminder_minutes = compute_reminder_minutes(deadline)
        appt.ReminderSet = True
        appt.ReminderMinutesBeforeStart = reminder_minutes

        # Importance
        importance_map = {"urgent": 2, "high": 2, "normal": 1, "low": 0}
        appt.Importance = importance_map.get(task.priority, 1)

        # Category
        category = task.category or "task-pilot"
        appt.Categories = category

        # Save
        appt.Save()

        event_id = appt.EntryID
        logger.info(
            "Created Outlook event for task %s (deadline: %s, reminder: %d min before)",
            task.id, deadline, reminder_minutes,
        )
        return event_id

    def _get_calendar(self, ns):
        """Get the target calendar folder."""
        if self.calendar_name:
            # Search by name
            for store in ns.Stores:
                try:
                    root = store.GetRootFolder()
                    cal = _find_subfolder(root, self.calendar_name, depth=3)
                    if cal:
                        return cal
                except Exception:
                    continue

        # Default: primary calendar
        return ns.GetDefaultFolder(9)  # olFolderCalendar


def _find_subfolder(folder, name: str, depth: int = 0):
    """Recursively search for a subfolder by name."""
    if depth > 3:
        return None
    try:
        for sub in folder.Folders:
            if sub.Name == name:
                return sub
            found = _find_subfolder(sub, name, depth + 1)
            if found:
                return found
    except Exception:
        pass
    return None
