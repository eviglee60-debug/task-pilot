"""Microsoft 365 / Exchange email connector via Microsoft Graph API.

Uses Mail.Read scope only — no write permissions requested.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from src.connectors.base import BaseConnector
from src.models.schemas import MessageSource, RawMessage, SenderType

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class EmailConnector(BaseConnector):
    """Read-only connector for Microsoft 365 / Exchange Online."""

    source = MessageSource.EMAIL

    def __init__(self, access_token: str, mailbox: str = "me"):
        self.access_token = access_token
        self.mailbox = mailbox

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    async def fetch_new_messages(
        self, since: datetime | None = None, limit: int = 50
    ) -> list[RawMessage]:
        if since is None:
            since = datetime.utcnow() - timedelta(hours=24)

        filter_str = f"receivedDateTime ge {since.isoformat()}Z"
        url = (
            f"{GRAPH_BASE}/users/{self.mailbox}/messages"
            f"?$filter={filter_str}"
            f"&$top={limit}"
            f"&$orderby=receivedDateTime desc"
            f"&$select=id,subject,from,receivedDateTime,bodyPreview,body"
        )

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()

        messages = []
        for item in data.get("value", []):
            sender_email = item.get("from", {}).get("emailAddress", {})
            messages.append(
                RawMessage(
                    source=MessageSource.EMAIL,
                    source_id=item["id"],
                    sender=sender_email.get("address", ""),
                    sender_type=self._classify_sender(sender_email.get("address", "")),
                    subject=item.get("subject", ""),
                    content=item.get("bodyPreview", ""),
                    received_at=datetime.fromisoformat(
                        item["receivedDateTime"].rstrip("Z")
                    ),
                    metadata={
                        "has_attachments": item.get("hasAttachments", False),
                        "importance": item.get("importance", "normal"),
                        "web_link": item.get("webLink", ""),
                    },
                )
            )

        logger.info("Fetched %d email(s) since %s", len(messages), since)
        return messages

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GRAPH_BASE}/users/{self.mailbox}?$select=id",
                    headers=self._headers(),
                    timeout=10,
                )
                return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _classify_sender(email: str) -> SenderType:
        """Simple heuristic classification. Override with domain config."""
        email_lower = email.lower()
        if any(k in email_lower for k in ("court", "fy.", "法院")):
            return SenderType.COURT
        if any(k in email_lower for k in ("cnipa", "国知局", "专利局")):
            return SenderType.CNIPA
        # Default: unknown, AI will refine later
        return SenderType.UNKNOWN
