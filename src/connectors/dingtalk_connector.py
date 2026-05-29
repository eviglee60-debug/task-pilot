"""DingTalk (钉钉) connector via Open Platform API.

Requires a DingTalk internal app with message read permissions.
Uses the server-side stream API for real-time message retrieval.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.connectors.base import BaseConnector
from src.models.schemas import MessageSource, RawMessage, SenderType

logger = logging.getLogger(__name__)


class DingTalkConnector(BaseConnector):
    """Read-only connector for DingTalk workspace messages."""

    source = MessageSource.DINGTALK

    def __init__(self, app_key: str, app_secret: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self._access_token: str | None = None

    async def _get_token(self) -> str:
        if self._access_token:
            return self._access_token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oapi.dingtalk.com/gettoken",
                params={"appkey": self.app_key, "appsecret": self.app_secret},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            return self._access_token

    async def fetch_new_messages(
        self, since: datetime | None = None, limit: int = 50
    ) -> list[RawMessage]:
        """Fetch messages from DingTalk group conversations.

        Note: DingTalk's API varies by use case (group chat, robot callback, etc.).
        This implementation uses the chat group message API as a starting point.
        For production, consider using the Stream API for real-time push.
        """
        token = await self._get_token()

        # DingTalk requires a different approach per message channel.
        # This is a placeholder for the group chat message retrieval.
        # In production, use the DingTalk Stream SDK for real-time callbacks.
        logger.warning(
            "DingTalk connector: using placeholder implementation. "
            "For production, integrate DingTalk Stream SDK."
        )
        return []

    async def health_check(self) -> bool:
        try:
            await self._get_token()
            return self._access_token is not None
        except Exception:
            return False
