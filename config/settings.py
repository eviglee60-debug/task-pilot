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

    # ── DingTalk ─────────────────────────────────────────────────────────────
    dingtalk_app_key: str = ""
    dingtalk_app_secret: str = ""

    # ── AI / LLM ─────────────────────────────────────────────────────────────
    llm_api_key: str = ""
    llm_base_url: str = "https://api.anthropic.com"
    llm_model: str = "claude-sonnet-4-20250514"

    # ── Polling ──────────────────────────────────────────────────────────────
    poll_interval_seconds: int = 300  # 5 minutes

    # ── Confirmation ─────────────────────────────────────────────────────────
    auto_confirm: bool = False  # If True, skip confirmation (NOT recommended)

    model_config = {"env_prefix": "TASK_PILOT_", "env_file": ".env"}
