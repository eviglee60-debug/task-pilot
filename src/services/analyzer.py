"""AI-powered message analyzer.

Uses an LLM to extract structured information from message snapshots:
- Action items and deadlines
- Sender classification
- Priority assessment
- Whether a response is required

The analyzer reads snapshots (read-only) and produces ExtractionResult.
It never modifies source data or snapshots.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx

from src.models.schemas import (
    ActionItem,
    ExtractionResult,
    SenderType,
    Snapshot,
)
from src.services.rules import RuleEngine

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """你是一个专业的待办事项提取助手。分析以下消息，提取结构化信息。

消息来源: {source}
发送者: {sender}
主题: {subject}
内容:
{content}

请以JSON格式返回以下信息:
{{
    "sender_type": "client|court|cnipa|internal|oa|unknown",
    "requires_response": true/false,
    "summary": "一句话摘要",
    "action_items": [
        {{
            "task": "具体待办事项",
            "deadline": "YYYY-MM-DDTHH:MM:SS 或 null",
            "priority": "low|normal|high|urgent",
            "category": "reply|filing|draft|review|payment|other"
        }}
    ]
}}

注意:
- 如果消息中提到了具体的截止日期，请提取出来
- 法院文件、国知局通知的期限通常很严格，标记为urgent
- 如果消息需要回复但没有明确截止日期，设deadline为null（系统会自动应用规则）
- 只返回JSON，不要其他文字"""


class MessageAnalyzer:
    """Analyzes message snapshots using LLM and rule engine."""

    def __init__(
        self,
        llm_api_key: str,
        llm_base_url: str = "https://api.anthropic.com",
        llm_model: str = "claude-sonnet-4-20250514",
        rule_engine: RuleEngine | None = None,
    ):
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.rule_engine = rule_engine or RuleEngine()

    async def analyze(self, snapshot: Snapshot) -> ExtractionResult:
        """Analyze a snapshot and extract structured information.

        Steps:
        1. Call LLM to extract action items and classify sender
        2. Apply deadline rules if no deadline was extracted
        3. Return ExtractionResult (does not persist anything)
        """
        # Step 1: LLM extraction
        llm_result = await self._call_llm(snapshot)

        # Step 2: Apply rules for missing deadlines
        sender_type = SenderType(llm_result.get("sender_type", "unknown"))
        source = snapshot.source
        content = snapshot.content

        action_items = []
        for item_data in llm_result.get("action_items", []):
            deadline = None
            if item_data.get("deadline"):
                try:
                    deadline = datetime.fromisoformat(item_data["deadline"])
                except (ValueError, TypeError):
                    pass

            # If no deadline extracted, apply rule engine
            if deadline is None:
                rule = self.rule_engine.match(sender_type, source, content)
                if rule:
                    received_at_str = snapshot.metadata.get("received_at")
                    received_at = (
                        datetime.fromisoformat(received_at_str)
                        if received_at_str
                        else snapshot.snapshot_time
                    )
                    deadline, _ = self.rule_engine.compute_deadline(
                        rule, extracted_deadline=None, received_at=received_at
                    )

            action_items.append(
                ActionItem(
                    task=item_data.get("task", ""),
                    deadline=deadline,
                    priority=item_data.get("priority", "normal"),
                    category=item_data.get("category", ""),
                )
            )

        return ExtractionResult(
            snapshot_id=snapshot.id,
            action_items=action_items,
            sender_type=sender_type,
            requires_response=llm_result.get("requires_response", False),
            summary=llm_result.get("summary", ""),
        )

    async def _call_llm(self, snapshot: Snapshot) -> dict:
        """Call LLM API for message analysis."""
        prompt = EXTRACTION_PROMPT.format(
            source=snapshot.source.value,
            sender=snapshot.metadata.get("sender", "unknown"),
            subject=snapshot.metadata.get("subject", ""),
            content=snapshot.content,
        )

        # Using Anthropic Messages API format
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.llm_base_url}/v1/messages",
                headers={
                    "x-api-key": self.llm_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.llm_model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

        # Extract text from Anthropic response
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        # Parse JSON from response (handle potential markdown code blocks)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
            return {
                "sender_type": "unknown",
                "requires_response": False,
                "summary": text[:200],
                "action_items": [],
            }
