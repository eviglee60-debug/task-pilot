"""Deadline rule engine.

Rules define default deadlines for different message types and contexts.
The engine matches rules against extracted message metadata and applies
the appropriate deadline delta.

Rules are configurable via config/rules.yaml.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.models.schemas import DeadlineRule, MessageSource, SenderType

logger = logging.getLogger(__name__)

# ── Default rules (can be overridden via config file) ────────────────────────

DEFAULT_RULES: list[DeadlineRule] = [
    DeadlineRule(
        name="email_reply",
        description="邮件必须24小时内回复",
        sources=[MessageSource.EMAIL],
        default_delta=timedelta(hours=24),
        priority="high",
    ),
    DeadlineRule(
        name="oa_task",
        description="OA转达事项3天内处理",
        sender_types=[SenderType.OA],
        keywords=["OA", "转达", "通知"],
        default_delta=timedelta(days=3),
        priority="normal",
    ),
    DeadlineRule(
        name="cnipa_oa1_draft",
        description="中国OA1：2个月提示提供答复初稿",
        sender_types=[SenderType.CNIPA],
        keywords=["OA1", "第一次审查意见"],
        default_delta=timedelta(days=60),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_oa2_draft",
        description="中国OA2：1个月提示提供答复初稿",
        sender_types=[SenderType.CNIPA],
        keywords=["OA2", "第二次审查意见"],
        default_delta=timedelta(days=30),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_official",
        description="国知局官方期限：15天（发文日+15天）",
        sender_types=[SenderType.CNIPA],
        keywords=["官方期限", "答复期限", "补正"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),
    DeadlineRule(
        name="court_filing",
        description="法院文件规定的期限（从文件内容提取）",
        sender_types=[SenderType.COURT],
        priority="urgent",
    ),
    DeadlineRule(
        name="client_deadline",
        description="客户指示的任务期限（从消息内容提取）",
        sender_types=[SenderType.CLIENT],
        priority="high",
    ),
    DeadlineRule(
        name="default",
        description="默认规则：3天内处理",
        default_delta=timedelta(days=3),
        priority="normal",
    ),
]


class RuleEngine:
    """Matches messages against deadline rules and computes deadlines."""

    def __init__(self, rules: list[DeadlineRule] | None = None):
        self.rules = rules or DEFAULT_RULES

    def match(
        self,
        sender_type: SenderType,
        source: MessageSource,
        content: str,
    ) -> DeadlineRule | None:
        """Find the first matching rule for the given message attributes.

        Matching priority: sender_type + keywords > sender_type > source > default.
        """
        content_lower = content.lower()

        # Pass 1: sender_type + keyword match (most specific)
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.sender_types and sender_type not in rule.sender_types:
                continue
            if rule.keywords:
                if any(kw.lower() in content_lower for kw in rule.keywords):
                    return rule
                continue  # keywords specified but none matched

        # Pass 2: sender_type match (no keywords required)
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.sender_types and sender_type in rule.sender_types:
                if not rule.keywords:
                    return rule

        # Pass 3: source match
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.sources and source in rule.sources:
                if not rule.sender_types and not rule.keywords:
                    return rule

        # Pass 4: default
        for rule in self.rules:
            if rule.name == "default" and rule.enabled:
                return rule

        return None

    def compute_deadline(
        self,
        rule: DeadlineRule,
        extracted_deadline: datetime | None = None,
        received_at: datetime | None = None,
    ) -> tuple[datetime, str]:
        """Compute the deadline for a task.

        Returns:
            (deadline_datetime, source_description)
        """
        # If AI extracted a specific deadline from the message, use it
        if extracted_deadline:
            return extracted_deadline, "从消息内容中提取"

        # Otherwise apply the rule's default delta from message receipt time
        base = received_at or datetime.utcnow()
        deadline = base + rule.default_delta

        return deadline, f"规则 {rule.name}: {rule.description}"
