"""Task management service.

Manages the lifecycle of task proposals: pending → confirmed/modified/ignored.
All state changes are recorded in the audit log.

CRITICAL: This service does NOT touch source data or snapshots.
          It only manages derived task proposals.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.models.schemas import (
    AuditAction,
    ExtractionResult,
    Snapshot,
    TaskProposal,
    TaskStatus,
)
from src.services.archive import SnapshotArchive
from src.services.audit import AuditLog
from src.services.calendar import CalendarService

logger = logging.getLogger(__name__)


class TaskManager:
    """Manages task proposals and their confirmation lifecycle."""

    def __init__(
        self,
        archive: SnapshotArchive,
        calendar: CalendarService,
        audit: AuditLog,
    ):
        self.archive = archive
        self.calendar = calendar
        self.audit = audit
        self._tasks: dict[str, TaskProposal] = {}

    def create_proposals(
        self,
        extraction: ExtractionResult,
    ) -> list[TaskProposal]:
        """Create task proposals from an extraction result.

        Returns created proposals. Tasks are in PENDING status,
        awaiting user confirmation.
        """
        snapshot = self.archive.get(extraction.snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot {extraction.snapshot_id} not found")

        proposals = []
        for item in extraction.action_items:
            task = TaskProposal(
                snapshot_id=extraction.snapshot_id,
                title=item.task,
                description=extraction.summary,
                deadline=item.deadline,
                priority=item.priority,
                category=item.category,
                source=snapshot.source,
                sender=snapshot.metadata.get("sender", ""),
                sender_type=extraction.sender_type,
                status=TaskStatus.PENDING,
            )
            self._tasks[task.id] = task
            proposals.append(task)

        self.audit.log(
            AuditAction.ANALYZE,
            target_id=extraction.snapshot_id,
            details={
                "tasks_created": len(proposals),
                "sender_type": extraction.sender_type.value,
                "summary": extraction.summary,
            },
        )

        logger.info(
            "Created %d task proposal(s) from snapshot %s",
            len(proposals),
            extraction.snapshot_id,
        )
        return proposals

    def confirm(self, task_id: str, user: str = "user") -> TaskProposal:
        """User confirms a task proposal. Writes to calendar."""
        task = self._get_pending(task_id)

        # Write to calendar
        event_id = self.calendar.create_event(task)

        task.status = TaskStatus.CONFIRMED
        task.confirmed_at = datetime.utcnow()
        task.calendar_event_id = event_id

        self.audit.log(
            AuditAction.CONFIRM,
            target_id=task_id,
            details={"calendar_event_id": event_id},
            user=user,
        )

        logger.info("Task %s confirmed, calendar event %s", task_id, event_id)
        return task

    def modify_and_confirm(
        self,
        task_id: str,
        title: str | None = None,
        deadline: datetime | None = None,
        priority: str | None = None,
        user: str = "user",
    ) -> TaskProposal:
        """User modifies a task before confirming."""
        task = self._get_pending(task_id)

        changes = {}
        if title is not None:
            changes["title"] = (task.title, title)
            task.title = title
        if deadline is not None:
            changes["deadline"] = (
                task.deadline.isoformat() if task.deadline else None,
                deadline.isoformat(),
            )
            task.deadline = deadline
        if priority is not None:
            changes["priority"] = (task.priority, priority)
            task.priority = priority

        # Write modified task to calendar
        event_id = self.calendar.create_event(task)

        task.status = TaskStatus.MODIFIED
        task.confirmed_at = datetime.utcnow()
        task.calendar_event_id = event_id

        self.audit.log(
            AuditAction.MODIFY,
            target_id=task_id,
            details={"changes": changes, "calendar_event_id": event_id},
            user=user,
        )

        logger.info("Task %s modified and confirmed", task_id)
        return task

    def ignore(self, task_id: str, user: str = "user") -> TaskProposal:
        """User ignores a task proposal."""
        task = self._get_pending(task_id)
        task.status = TaskStatus.IGNORED

        self.audit.log(AuditAction.IGNORE, target_id=task_id, user=user)

        logger.info("Task %s ignored", task_id)
        return task

    def get_pending(self) -> list[TaskProposal]:
        """Get all tasks awaiting confirmation."""
        return [
            t for t in self._tasks.values()
            if t.status == TaskStatus.PENDING
        ]

    def get_all(
        self,
        status: TaskStatus | None = None,
        limit: int = 50,
    ) -> list[TaskProposal]:
        """Get tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    def _get_pending(self, task_id: str) -> TaskProposal:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task.status != TaskStatus.PENDING:
            raise ValueError(
                f"Task {task_id} is already {task.status.value}, "
                "only pending tasks can be confirmed/modified/ignored"
            )
        return task
