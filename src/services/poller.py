"""Background message poller.

Periodically fetches new messages from all configured connectors,
archives them as snapshots, runs AI analysis, and creates task proposals.

CRITICAL: This service only READS from sources and WRITES to the local
          archive. It never modifies or deletes source data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from src.connectors.base import BaseConnector
from src.models.schemas import AuditAction
from src.services.analyzer import MessageAnalyzer
from src.services.archive import SnapshotArchive
from src.services.audit import AuditLog
from src.services.task_manager import TaskManager

logger = logging.getLogger(__name__)


class MessagePoller:
    """Polls connectors for new messages and processes them."""

    def __init__(
        self,
        connectors: list[BaseConnector],
        archive: SnapshotArchive,
        analyzer: MessageAnalyzer,
        task_manager: TaskManager,
        audit: AuditLog,
        poll_interval: int = 300,
    ):
        self.connectors = connectors
        self.archive = archive
        self.analyzer = analyzer
        self.task_manager = task_manager
        self.audit = audit
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_poll: dict[str, datetime] = {}

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Poller started with %d connector(s)", len(self.connectors))

    async def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Poller stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_once()
            except Exception:
                logger.exception("Error during poll cycle")
            await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> None:
        """Single poll cycle: fetch → archive → analyze → propose."""
        for connector in self.connectors:
            source_name = connector.source.value
            since = self._last_poll.get(source_name)  # None on first run → connector uses its own lookback

            try:
                # Step 1: Fetch (read-only)
                messages = await connector.fetch_new_messages(since=since)
                logger.info(
                    "[%s] Fetched %d new message(s)", source_name, len(messages)
                )

                for msg in messages:
                    # Step 1.5: Process attachments on demand (if connector supports it)
                    if msg.metadata.get("has_attachments") and hasattr(connector, "get_attachment_texts"):
                        att_texts = await connector.get_attachment_texts(msg.source_id)
                        if att_texts:
                            att_content = "\n\n".join(
                                f"[附件: {fname}]\n{text}" for fname, text in att_texts.items()
                            )
                            msg.content = msg.content + "\n\n" + att_content

                    # Step 2: Archive (append-only)
                    snapshot = self.archive.archive(msg)

                    self.audit.log(
                        AuditAction.ARCHIVE,
                        target_id=snapshot.id,
                        details={
                            "source": source_name,
                            "source_id": msg.source_id,
                        },
                    )

                    # Step 3: Analyze (read-only)
                    extraction = await self.analyzer.analyze(snapshot)

                    # Step 4: Create task proposals
                    if extraction.action_items:
                        proposals = self.task_manager.create_proposals(extraction)
                        logger.info(
                            "[%s] Created %d task proposal(s) from message %s",
                            source_name,
                            len(proposals),
                            msg.source_id,
                        )

                self._last_poll[source_name] = datetime.utcnow()

            except Exception:
                logger.exception("[%s] Error processing messages", source_name)

    async def poll_now(self, limit: int = 50) -> int:
        """Trigger an immediate poll cycle. Returns total new tasks created."""
        total = 0
        for connector in self.connectors:
            source_name = connector.source.value
            since = self._last_poll.get(source_name)

            messages = await connector.fetch_new_messages(since=since, limit=limit)
            logger.info("[%s] Fetched %d message(s)", source_name, len(messages))

            for msg in messages:
                # Process attachments on demand
                if msg.metadata.get("has_attachments") and hasattr(connector, "get_attachment_texts"):
                    att_texts = await connector.get_attachment_texts(msg.source_id)
                    if att_texts:
                        att_content = "\n\n".join(
                            f"[附件: {fname}]\n{text}" for fname, text in att_texts.items()
                        )
                        msg.content = msg.content + "\n\n" + att_content

                snapshot = self.archive.archive(msg)
                extraction = await self.analyzer.analyze(snapshot)
                if extraction.action_items:
                    proposals = self.task_manager.create_proposals(extraction)
                    total += len(proposals)

            self._last_poll[source_name] = datetime.utcnow()

        return total
