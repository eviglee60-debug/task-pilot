"""API routes for snapshot archive (read-only).

Endpoints:
- GET /snapshots       — List archived snapshots
- GET /snapshots/{id}  — Get a specific snapshot
- GET /snapshots/{id}/verify — Verify snapshot integrity
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/snapshots", tags=["snapshots"])

_archive = None


def init_router(archive):
    global _archive
    _archive = archive


class SnapshotResponse(BaseModel):
    id: str
    source: str
    source_id: str
    content: str
    metadata: dict[str, Any]
    snapshot_time: datetime
    content_hash: str


@router.get("", response_model=list[SnapshotResponse])
async def list_snapshots(limit: int = 50, offset: int = 0):
    """List archived snapshots (read-only)."""
    snapshots = _archive.list_all(limit=limit, offset=offset)
    return [
        SnapshotResponse(
            id=s.id,
            source=s.source.value,
            source_id=s.source_id,
            content=s.content,
            metadata=s.metadata,
            snapshot_time=s.snapshot_time,
            content_hash=s.content_hash,
        )
        for s in snapshots
    ]


@router.get("/{snapshot_id}", response_model=SnapshotResponse)
async def get_snapshot(snapshot_id: str):
    """Get a specific snapshot by ID."""
    snapshot = _archive.get(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return SnapshotResponse(
        id=snapshot.id,
        source=snapshot.source.value,
        source_id=snapshot.source_id,
        content=snapshot.content,
        metadata=snapshot.metadata,
        snapshot_time=snapshot.snapshot_time,
        content_hash=snapshot.content_hash,
    )


@router.get("/{snapshot_id}/verify")
async def verify_snapshot(snapshot_id: str):
    """Verify a snapshot's content integrity."""
    valid = _archive.verify_integrity(snapshot_id)
    if not valid:
        raise HTTPException(status_code=404, detail="Snapshot not found or integrity check failed")
    return {"snapshot_id": snapshot_id, "integrity": "valid"}
