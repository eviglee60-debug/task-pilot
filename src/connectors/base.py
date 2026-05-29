"""Abstract base connector — read-only by design.

Subclasses MUST NOT implement any write/delete/modify methods.
The base class explicitly blocks them to prevent accidental misuse.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.models.schemas import MessageSource, RawMessage


class BaseConnector(ABC):
    """Read-only connector for external message sources."""

    source: MessageSource

    @abstractmethod
    async def fetch_new_messages(self, since: datetime | None = None) -> list[RawMessage]:
        """Fetch new messages since the given timestamp.

        Args:
            since: Only return messages received after this time.
                    If None, fetch the most recent messages (configurable limit).

        Returns:
            List of RawMessage objects. Never modifies or deletes source data.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the source is reachable and credentials are valid."""
        ...

    # ── Explicitly forbidden operations ──────────────────────────────────────

    async def delete(self, *args, **kwargs):
        raise PermissionError(
            f"[{self.source.value}] 禁止删除源数据。系统设计为只读访问。"
        )

    async def modify(self, *args, **kwargs):
        raise PermissionError(
            f"[{self.source.value}] 禁止修改源数据。系统设计为只读访问。"
        )

    async def send(self, *args, **kwargs):
        raise PermissionError(
            f"[{self.source.value}] 禁止向源系统发送消息。系统设计为只读访问。"
        )
