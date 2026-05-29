"""Append-only snapshot archive.

Design principles:
- Snapshots are NEVER deleted or modified once written.
- Each snapshot has a SHA-256 content hash for integrity verification.
- Storage uses append-only file or database — no UPDATE/DELETE operations.
- Snapshots reference source messages by (source, source_id) for traceability.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.models.schemas import MessageSource, RawMessage, Snapshot

logger = logging.getLogger(__name__)


class SnapshotArchive:
    """Append-only archive for message snapshots.

    Storage format: JSONL (one JSON object per line), append-only.
    Each line is a Snapshot serialized to JSON.
    """

    def __init__(self, storage_path: str | Path = "data/snapshots.jsonl"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, Snapshot] = {}  # id -> Snapshot, loaded on startup
        self._source_index: dict[str, str] = {}  # "source:source_id" -> snapshot_id
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing snapshots into memory index on startup."""
        if not self.storage_path.exists():
            return

        count = 0
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                snapshot = Snapshot(**data)
                self._index[snapshot.id] = snapshot
                key = f"{snapshot.source.value}:{snapshot.source_id}"
                self._source_index[key] = snapshot.id
                count += 1

        logger.info("Loaded %d snapshot(s) from %s", count, self.storage_path)

    def archive(self, raw: RawMessage) -> Snapshot:
        """Archive a raw message as an immutable snapshot.

        Returns the created Snapshot. If a snapshot with the same
        (source, source_id) already exists, returns the existing one (dedup).
        """
        key = f"{raw.source.value}:{raw.source_id}"
        if key in self._source_index:
            existing_id = self._source_index[key]
            logger.debug("Snapshot already exists for %s, returning existing", key)
            return self._index[existing_id]

        snapshot = Snapshot(
            source=raw.source,
            source_id=raw.source_id,
            content=raw.content,
            metadata={
                "sender": raw.sender,
                "sender_type": raw.sender_type.value,
                "subject": raw.subject,
                "received_at": raw.received_at.isoformat(),
                **raw.metadata,
            },
        )

        # Append to JSONL file — never overwrite
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(snapshot.model_dump_json() + "\n")

        # Update in-memory index
        self._index[snapshot.id] = snapshot
        self._source_index[key] = snapshot.id

        logger.info(
            "Archived snapshot %s (source=%s, source_id=%s)",
            snapshot.id,
            raw.source.value,
            raw.source_id,
        )
        return snapshot

    def get(self, snapshot_id: str) -> Snapshot | None:
        """Retrieve a snapshot by ID. Read-only."""
        return self._index.get(snapshot_id)

    def get_by_source(self, source: MessageSource, source_id: str) -> Snapshot | None:
        """Retrieve a snapshot by source reference. Read-only."""
        key = f"{source.value}:{source_id}"
        sid = self._source_index.get(key)
        return self._index.get(sid) if sid else None

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Snapshot]:
        """List snapshots in reverse chronological order. Read-only."""
        all_snapshots = sorted(
            self._index.values(),
            key=lambda s: s.snapshot_time,
            reverse=True,
        )
        return all_snapshots[offset : offset + limit]

    def count(self) -> int:
        return len(self._index)

    def verify_integrity(self, snapshot_id: str) -> bool:
        """Verify a snapshot's content hash matches its stored hash."""
        snapshot = self._index.get(snapshot_id)
        if not snapshot:
            return False
        import hashlib

        expected = hashlib.sha256(snapshot.content.encode()).hexdigest()
        return expected == snapshot.content_hash
