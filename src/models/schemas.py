"""Core data models for task-pilot.

All models are immutable after creation. Source data is never stored here —
only references (snapshot_id) to the append-only archive.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class MessageSource(str, Enum):
    EMAIL = "email"
    DINGTALK = "dingtalk"
    WECHAT = "wechat"


class SenderType(str, Enum):
    CLIENT = "client"
    COURT = "court"
    CNIPA = "cnipa"           # 国知局
    TRADEMARK_OFFICE = "trademark_office"  # 商标局
    COPYRIGHT_BUREAU = "copyright_bureau"  # 版权局
    INTERNAL = "internal"
    OA = "oa"
    UNKNOWN = "unknown"


class TaskStatus(str, Enum):
    PENDING = "pending"       # 待确认
    CONFIRMED = "confirmed"   # 已确认，已写入日历
    MODIFIED = "modified"     # 用户修改后写入
    IGNORED = "ignored"       # 用户忽略


class AuditAction(str, Enum):
    FETCH = "fetch"
    ARCHIVE = "archive"
    ANALYZE = "analyze"
    CONFIRM = "confirm"
    MODIFY = "modify"
    IGNORE = "ignore"
    CALENDAR_WRITE = "calendar_write"
    ERROR = "error"


# ── Source Message (transient, never persisted as-is) ────────────────────────

class RawMessage(BaseModel):
    """Represents a message fetched from a source. Never stored directly —
    only archived as a snapshot."""

    source: MessageSource
    source_id: str                   # 原始系统中的消息ID
    sender: str
    sender_type: SenderType = SenderType.UNKNOWN
    subject: str = ""
    content: str
    received_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Snapshot (append-only archive) ──────────────────────────────────────────

class Snapshot(BaseModel):
    """Immutable snapshot of a raw message. Stored in append-only log."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    source: MessageSource
    source_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    snapshot_time: datetime = Field(default_factory=datetime.utcnow)
    content_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            object.__setattr__(
                self, "content_hash",
                hashlib.sha256(self.content.encode()).hexdigest(),
            )


# ── AI Extraction Result ────────────────────────────────────────────────────

class ActionItem(BaseModel):
    """A single action item extracted from a message."""

    task: str
    deadline: datetime | None = None
    priority: str = "normal"         # low / normal / high / urgent
    category: str = ""               # e.g. "reply", "filing", "draft"


class ExtractionResult(BaseModel):
    """Structured output from AI analysis of a snapshot."""

    snapshot_id: str
    action_items: list[ActionItem] = Field(default_factory=list)
    sender_type: SenderType = SenderType.UNKNOWN
    requires_response: bool = False
    summary: str = ""
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


# ── Task Proposal (pending user confirmation) ───────────────────────────────

class TaskProposal(BaseModel):
    """A proposed calendar task awaiting user confirmation."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    snapshot_id: str
    title: str
    description: str = ""
    deadline: datetime | None = None
    priority: str = "normal"
    category: str = ""
    source: MessageSource
    sender: str = ""
    sender_type: SenderType = SenderType.UNKNOWN
    rule_applied: str = ""           # 命中的规则名称
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: datetime | None = None
    calendar_event_id: str | None = None


# ── Deadline Rule ────────────────────────────────────────────────────────────

class DeadlineRule(BaseModel):
    """Configurable deadline rule."""

    name: str
    description: str = ""
    sender_types: list[SenderType] = Field(default_factory=list)
    sources: list[MessageSource] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    default_delta: timedelta = timedelta(days=3)
    priority: str = "normal"
    enabled: bool = True


# ── Audit Log Entry ─────────────────────────────────────────────────────────

class AuditEntry(BaseModel):
    """Immutable audit log entry."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: AuditAction
    target_id: str = ""              # snapshot_id / task_id
    details: dict[str, Any] = Field(default_factory=dict)
    user: str = "system"
