"""Local Outlook connector via COM automation (win32com).

No OAuth, no network auth — uses the already-logged-in Outlook client.
Runs COM calls in a thread pool to avoid blocking the async event loop.

Supports reading attachments and extracting text from common formats.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from src.connectors.base import BaseConnector
from src.models.schemas import MessageSource, RawMessage, SenderType

logger = logging.getLogger(__name__)


class OutlookComConnector(BaseConnector):
    """Read-only connector for local Outlook via COM automation."""

    source = MessageSource.EMAIL

    def __init__(self, folder_name: str = "收件箱", max_attachments: int = 10,
                 lookback_days: int = 30, ocr_service=None):
        self.folder_name = folder_name
        self.max_attachments = max_attachments
        self.lookback_days = lookback_days
        self.ocr_service = ocr_service  # MistralOCR instance, optional

    async def get_attachment_texts(self, source_id: str, filenames: list[str] | None = None) -> dict[str, str]:
        """Process attachments for a specific email on demand.

        Args:
            source_id: The Outlook EntryID of the email.
            filenames: Optional list of filenames to process. None = all.

        Returns:
            Dict mapping filename to extracted text.
        """
        return await asyncio.to_thread(
            self._get_attachment_texts_sync, source_id, filenames
        )

    def _get_attachment_texts_sync(self, source_id: str, filenames: list[str] | None) -> dict[str, str]:
        """Synchronous attachment processing — runs in thread pool."""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            ns = outlook.GetNamespace("MAPI")

            try:
                item = ns.GetItemFromID(source_id)
            except Exception:
                logger.warning("Cannot find email with EntryID: %s", source_id)
                return {}

            results = {}
            att_count = item.Attachments.Count
            for i in range(1, min(att_count, self.max_attachments) + 1):
                att = item.Attachments.Item(i)
                fname = att.FileName or ""
                if filenames and fname not in filenames:
                    continue
                text = self._extract_attachment_text(att)
                if text:
                    results[fname] = text

            return results
        finally:
            pythoncom.CoUninitialize()

    async def fetch_new_messages(
        self, since: datetime | None = None, limit: int = 50
    ) -> list[RawMessage]:
        if since is None:
            since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            from datetime import timedelta
            since = since - timedelta(days=self.lookback_days)

        return await asyncio.to_thread(
            self._fetch_sync, since, limit
        )

    def _fetch_sync(self, since: datetime, limit: int) -> list[RawMessage]:
        """Synchronous COM call — runs in thread pool."""
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            ns = outlook.GetNamespace("MAPI")

            # Use default inbox (most reliable)
            inbox = ns.GetDefaultFolder(6)  # olFolderInbox
            logger.info("Using inbox: %s (%d items)", inbox.Name, inbox.Items.Count)

            # Filter by received time
            since_str = since.strftime("%m/%d/%Y %H:%M %p")
            filter_str = f"[ReceivedTime] >= '{since_str}'"
            try:
                items = inbox.Items.Restrict(filter_str)
            except Exception:
                logger.warning("Restrict filter failed, fetching all items")
                items = inbox.Items

            items.Sort("[ReceivedTime]", True)  # descending

            messages = []
            count = 0
            for item in items:
                if count >= limit:
                    break
                if item.Class != 43:  # olMail
                    continue
                try:
                    raw = self._convert_item(item)
                    messages.append(raw)
                    count += 1
                except Exception:
                    logger.exception("Failed to convert mail item")

            logger.info("Fetched %d email(s) from local Outlook since %s", len(messages), since)
            return messages
        finally:
            pythoncom.CoUninitialize()

    def _convert_item(self, item) -> RawMessage:
        """Convert an Outlook COM MailItem to RawMessage."""
        # NOTE: item.SenderEmailAddress hangs on some external emails (COM bug).
        # We extract sender from the body headers instead.
        sender_email = ""

        # Get body (prefer plain text, fallback to HTML stripped)
        content = ""
        try:
            content = item.Body or ""
        except Exception:
            pass
        if not content:
            try:
                import re
                html = item.HTMLBody or ""
                content = re.sub(r"<[^>]+>", "", html).strip()
            except Exception:
                content = ""

        # Extract sender email from body headers (since SenderEmailAddress can hang)
        if not sender_email and content:
            import re
            match = re.search(r'[\w.-]+@[\w.-]+\.\w+', content[:500])
            if match:
                sender_email = match.group()

        # Record attachment metadata (don't extract content during fetch — too slow)
        attachment_filenames = []
        att_count = 0
        try:
            att_count = item.Attachments.Count
            for i in range(1, min(att_count, self.max_attachments) + 1):
                att = item.Attachments.Item(i)
                attachment_filenames.append(att.FileName or f"attachment_{i}")
        except Exception:
            pass

        received_at = item.ReceivedTime
        if received_at:
            # COM returns naive datetime in local time
            received_at = received_at.replace(tzinfo=None)

        subject = ""
        try:
            subject = item.Subject or ""
        except Exception:
            pass

        has_attachments = att_count > 0

        importance = "normal"
        try:
            imp = item.Importance  # 0=low, 1=normal, 2=high
            importance = {0: "low", 1: "normal", 2: "high"}.get(imp, "normal")
        except Exception:
            pass

        entry_id = ""
        try:
            entry_id = item.EntryID or ""
        except Exception:
            pass

        return RawMessage(
            source=MessageSource.EMAIL,
            source_id=entry_id or str(id(item)),
            sender=sender_email,
            sender_type=self._classify_sender(sender_email),
            subject=subject,
            content=content,
            received_at=received_at or datetime.now(),
            metadata={
                "has_attachments": has_attachments,
                "importance": importance,
                "attachment_count": att_count,
                "attachment_filenames": attachment_filenames,
            },
        )

    def _extract_attachment_text(self, att) -> str:
        """Extract text content from an Outlook attachment."""
        filename = att.FileName or ""
        ext = Path(filename).suffix.lower()

        # Supported extensions
        text_exts = (".txt", ".csv", ".log", ".html", ".htm", ".eml", ".docx")
        ocr_exts = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

        if ext not in text_exts + ocr_exts:
            return ""

        tmp_path = None
        try:
            # Save to temp file
            tmp_dir = tempfile.mkdtemp(prefix="task_pilot_att_")
            tmp_path = os.path.join(tmp_dir, filename)
            att.SaveAsFile(tmp_path)

            if ext in (".txt", ".csv", ".log"):
                return Path(tmp_path).read_text(encoding="utf-8", errors="replace")[:5000]

            if ext in (".html", ".htm"):
                import re
                html = Path(tmp_path).read_text(encoding="utf-8", errors="replace")
                return re.sub(r"<[^>]+>", "", html).strip()[:5000]

            if ext == ".eml":
                import email
                from email import policy
                with open(tmp_path, "rb") as f:
                    msg = email.message_from_binary_file(f, policy=policy.default)
                body = msg.get_body(preferencelist=("plain", "html"))
                if body:
                    text = body.get_content()
                    if body.get_content_type() == "text/html":
                        import re
                        text = re.sub(r"<[^>]+>", "", text)
                    return text.strip()[:5000]

            if ext == ".docx":
                try:
                    from docx import Document
                    doc = Document(tmp_path)
                    return "\n".join(p.text for p in doc.paragraphs)[:5000]
                except ImportError:
                    logger.debug("python-docx not installed, skipping .docx attachment")
                    return ""

            if ext in (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"):
                # PDF and images: use Mistral OCR
                if self.ocr_service:
                    return self.ocr_service.extract_text(tmp_path)
                else:
                    logger.debug("OCR service not configured, skipping %s", ext)
                    return f"[{ext} 附件，未配置 OCR 服务]"

        except Exception:
            logger.exception("Failed to extract text from attachment %s", filename)
            return ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                    os.rmdir(os.path.dirname(tmp_path))
                except OSError:
                    pass

        return ""

    @staticmethod
    def _find_folder(ns, folder_name: str):
        """Search for a folder by name in all stores."""
        for store in ns.Stores:
            try:
                root = store.GetRootFolder()
                found = _search_folder_recursive(root, folder_name)
                if found:
                    return found
            except Exception:
                continue
        return None

    async def health_check(self) -> bool:
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                outlook = win32com.client.Dispatch("Outlook.Application")
                ns = outlook.GetNamespace("MAPI")
                ns.GetDefaultFolder(6)
                return True
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            return False

    @staticmethod
    def _classify_sender(email: str) -> SenderType:
        email_lower = email.lower()
        if any(k in email_lower for k in ("court", "fy.", "法院")):
            return SenderType.COURT
        if any(k in email_lower for k in ("cnipa", "国知局", "专利局")):
            return SenderType.CNIPA
        if any(k in email_lower for k in ("trademark", "商标", "sbj.", "cbirc")):
            return SenderType.TRADEMARK_OFFICE
        if any(k in email_lower for k in ("copyright", "版权", "ncac")):
            return SenderType.COPYRIGHT_BUREAU
        return SenderType.UNKNOWN


def _search_folder_recursive(folder, target_name: str, depth: int = 0):
    """Recursively search for a folder by name. Max depth 3."""
    if depth > 3:
        return None
    try:
        if folder.Name == target_name:
            return folder
    except Exception:
        return None
    try:
        for subfolder in folder.Folders:
            found = _search_folder_recursive(subfolder, target_name, depth + 1)
            if found:
                return found
    except Exception:
        pass
    return None
