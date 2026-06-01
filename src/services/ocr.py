"""Mistral OCR service for PDF and image text extraction.

Calls Mistral's /v1/ocr endpoint to extract text from scanned documents,
PDFs, and images. Returns structured markdown text.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class MistralOCR:
    """Extract text from PDF/image files using Mistral OCR API."""

    def __init__(self, api_key: str, ocr_url: str = "https://api.mistral.ai/v1/ocr"):
        self.api_key = api_key
        self.ocr_url = ocr_url

    def extract_text(self, file_path: str, max_pages: int = 10) -> str:
        """Extract text from a PDF or image file.

        Args:
            file_path: Path to the local file.
            max_pages: Max pages to process (PDF only).

        Returns:
            Extracted text as string, or empty string on failure.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            return self._ocr_pdf(file_path, max_pages)
        elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"):
            return self._ocr_image(file_path)
        else:
            logger.debug("Unsupported file type for OCR: %s", ext)
            return ""

    def _ocr_pdf(self, file_path: str, max_pages: int) -> str:
        """OCR a PDF document."""
        try:
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()

            # Mistral OCR accepts document as base64
            b64 = base64.b64encode(pdf_bytes).decode("utf-8")

            payload = {
                "model": "mistral-ocr-latest",
                "document": {
                    "type": "document_url",
                    "document_url": f"data:application/pdf;base64,{b64}",
                },
            }

            resp = httpx.post(
                self.ocr_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            # Mistral OCR returns pages with markdown text
            pages = data.get("pages", [])
            texts = []
            for i, page in enumerate(pages[:max_pages]):
                text = page.get("markdown", "") or page.get("text", "")
                if text:
                    texts.append(text.strip())

            result = "\n\n".join(texts)
            logger.info("OCR extracted %d chars from PDF (%d pages)", len(result), len(pages))
            return result[:10000]  # cap at 10k chars

        except httpx.HTTPStatusError as e:
            logger.error("Mistral OCR API error: %s %s", e.response.status_code, e.response.text[:200])
            return ""
        except Exception:
            logger.exception("Failed to OCR PDF: %s", file_path)
            return ""

    def _ocr_image(self, file_path: str) -> str:
        """OCR an image file."""
        try:
            with open(file_path, "rb") as f:
                img_bytes = f.read()

            ext = Path(file_path).suffix.lower().lstrip(".")
            mime_map = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "bmp": "image/bmp",
                "tiff": "image/tiff", "tif": "image/tiff",
                "webp": "image/webp",
            }
            mime = mime_map.get(ext, "image/png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")

            payload = {
                "model": "mistral-ocr-latest",
                "document": {
                    "type": "image_url",
                    "image_url": f"data:{mime};base64,{b64}",
                },
            }

            resp = httpx.post(
                self.ocr_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            pages = data.get("pages", [])
            texts = []
            for page in pages:
                text = page.get("markdown", "") or page.get("text", "")
                if text:
                    texts.append(text.strip())

            result = "\n\n".join(texts)
            logger.info("OCR extracted %d chars from image", len(result))
            return result[:5000]

        except httpx.HTTPStatusError as e:
            logger.error("Mistral OCR API error: %s %s", e.response.status_code, e.response.text[:200])
            return ""
        except Exception:
            logger.exception("Failed to OCR image: %s", file_path)
            return ""
