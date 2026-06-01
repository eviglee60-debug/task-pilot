"""Application configuration.

Reads from environment variables with sensible defaults.
For production, use a .env file or secrets manager.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Task-pilot configuration."""

    # ── Storage ──────────────────────────────────────────────────────────────
    data_dir: str = "data"
    snapshot_file: str = "snapshots.jsonl"
    audit_file: str = "audit.jsonl"

    @property
    def snapshot_path(self) -> Path:
        return Path(self.data_dir) / self.snapshot_file

    @property
    def audit_path(self) -> Path:
        return Path(self.data_dir) / self.audit_file

    # ── Microsoft Graph (Email + Calendar) ───────────────────────────────────
    ms_graph_token: str = ""
    mailbox: str = "me"
    calendar_id: str = "calendar"

    # ── Local Outlook COM (替代 Graph API，无需 OAuth) ─────────────────────────
    use_outlook_com: bool = True           # 优先使用本地 Outlook COM
    outlook_folder: str = "收件箱"          # Outlook 文件夹名称
    outlook_calendar_name: str = ""        # 空=默认日历

    # ── DingTalk ─────────────────────────────────────────────────────────────
    dingtalk_app_key: str = ""
    dingtalk_app_secret: str = ""

    # ── AI / LLM (分析邮件内容，提取待办事项) ─────────────────────────────────
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimax.chat/v1"
    llm_model: str = "MiniMax-M2.7"
    llm_provider: str = "minimax"  # minimax | anthropic

    # ── Mistral OCR (PDF / 图片文字识别) ──────────────────────────────────────
    mistral_api_key: str = ""
    mistral_ocr_url: str = "https://api.mistral.ai/v1/ocr"

    # ── Polling ──────────────────────────────────────────────────────────────
    poll_interval_seconds: int = 300  # 5 minutes

    # ── Confirmation ─────────────────────────────────────────────────────────
    auto_confirm: bool = False  # If True, skip confirmation (NOT recommended)

    model_config = {"env_prefix": "TASK_PILOT_", "env_file": ".env"}
