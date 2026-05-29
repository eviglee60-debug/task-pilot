"""API routes for audit log (read-only).

Endpoints:
- GET /audit — Query audit log entries
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.models.schemas import AuditAction

router = APIRouter(prefix="/audit", tags=["audit"])

_audit = None


def init_router(audit):
    global _audit
    _audit = audit


class AuditResponse(BaseModel):
    id: str
    timestamp: datetime
    action: str
    target_id: str
    details: dict[str, Any]
    user: str


@router.get("", response_model=list[AuditResponse])
async def query_audit(
    action: str | None = None,
    target_id: str | None = None,
    limit: int = 100,
):
    """Query audit log entries."""
    audit_action = AuditAction(action) if action else None
    entries = _audit.query(action=audit_action, target_id=target_id, limit=limit)
    return [
        AuditResponse(
            id=e.id,
            timestamp=e.timestamp,
            action=e.action.value,
            target_id=e.target_id,
            details=e.details,
            user=e.user,
        )
        for e in entries
    ]
