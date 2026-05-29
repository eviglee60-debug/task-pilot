"""WeChat (微信) connector.

IMPORTANT: WeChat does not provide an official personal message API.
This connector is a placeholder with two possible strategies:

1. Enterprise WeChat (企业微信): Has official APIs for workspace messages.
2. Personal WeChat: Requires third-party libraries or message forwarding
   to a monitored account. Use with caution.

For production, prefer Enterprise WeChat or manual forwarding workflows.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.connectors.base import BaseConnector
from src.models.schemas import MessageSource, RawMessage

logger = logging.getLogger(__name__)


class WeChatConnector(BaseConnector):
    """Placeholder connector for WeChat messages.

    Strategy options:
    - Enterprise WeChat (recommended): use work.weixin.qq.com API
    - Personal WeChat: forward messages to a bot / monitored group
    """

    source = MessageSource.WECHAT

    def __init__(self, webhook_url: str | None = None):
        """
        Args:
            webhook_url: If using a webhook-based approach (e.g., messages
                         forwarded to an HTTP endpoint), provide the URL.
        """
        self.webhook_url = webhook_url

    async def fetch_new_messages(
        self, since: datetime | None = None, limit: int = 50
    ) -> list[RawMessage]:
        """Fetch WeChat messages.

        Currently not implemented. Choose one of these strategies:
        1. Enterprise WeChat: implement using qyapi.weixin.qq.com
        2. Webhook: receive forwarded messages via HTTP callback
        3. Manual: users forward messages to a monitored account
        """
        logger.warning(
            "WeChat connector not implemented. "
            "Consider: (1) Enterprise WeChat API, (2) webhook forwarding, "
            "(3) manual forwarding to a monitored group."
        )
        return []

    async def health_check(self) -> bool:
        return False  # Not implemented
