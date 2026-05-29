"""Immutable audit log.

Every operation (fetch, archive, analyze, confirm, ignore, calendar write)
is recorded. The log is append-only — entries cannot be modified or deleted.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.models.schemas import AuditAction, AuditEntry

logger = logging.getLogger(__name__)


class AuditLog:
    """Append-only audit log stored as JSONL."""

    def __init__(self, storage_path: str | Path = "data/audit.jsonl"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        action: AuditAction,
        target_id: str = "",
        details: dict | None = None,
        user: str = "system",
    ) -> AuditEntry:
        """Append an audit entry. Returns the created entry."""
        entry = AuditEntry(
            action=action,
            target_id=target_id,
            details=details or {},
            user=user,
        )

        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

        logger.info(
            "AUDIT [%s] target=%s user=%s",
            action.value,
            target_id,
            user,
        )
        return entry

    def query(
        self,
        action: AuditAction | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries. Read-only."""
        if not self.storage_path.exists():
            return []

        entries = []
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entry = AuditEntry(**data)

                if action and entry.action != action:
                    continue
                if target_id and entry.target_id != target_id:
                    continue

                entries.append(entry)

        # Return most recent first
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]
