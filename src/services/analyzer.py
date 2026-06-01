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

EXTRACTION_PROMPT = """你是一个专业的法律/IP待办事项提取助手，专门处理中国法律和知识产权相关邮件。分析以下消息，提取结构化信息。

消息来源: {source}
发送者: {sender}
主题: {subject}
内容:
{content}

请以JSON格式返回以下信息:
{{
    "sender_type": "client|court|cnipa|trademark_office|copyright_bureau|internal|oa|unknown",
    "requires_response": true/false,
    "summary": "一句话摘要",
    "action_items": [
        {{
            "task": "具体待办事项（简明扼要，如：答复OA1审查意见、缴纳第XXX号专利年费、提交答辩状）",
            "deadline": "YYYY-MM-DDTHH:MM:SS 或 null",
            "priority": "low|normal|high|urgent",
            "category": "reply|filing|draft|review|payment|other"
        }}
    ]
}}

发送者分类规则:
- cnipa: 国家知识产权局、专利局、商标局（发件域名含cnipa.gov.cn、cnipa等）
- court: 法院、仲裁委（发件域名含court.gov.cn、fy.等）
- trademark_office: 商标局、商标评审委员会
- copyright_bureau: 版权局、著作权登记中心
- client: 客户、委托人（外部发件人，非官方机构）
- oa: OA系统自动转发的通知
- internal: 律所/公司内部同事
- unknown: 无法判断

时限提取规则（重要——专利领域已取消宽限期，法定期限即deadline）:

专利/国知局期限（从发文日或申请日起算）:
- 48小时: 诉前禁令裁定、诉前证据保全裁定
- 15天: 邮寄送达推定、收到受理通知后缴纳申请费、行政调处不服起诉、诉前禁令/保全解除
- 1个月: 公告送达、无效宣告补充证据、著录事项变更费等缴纳
- 2个月: 审查意见答复(OA)、恢复权利请求、办理登记手续、实用新型/外观设计主动修改、提交证明文件、优先权要求费、中文译文
- 3个月: 提交优先权文件副本、发明专利主动修改、请求复审、对复审/无效决定不服起诉、许可合同备案
- 4个月: 保密审查、生物材料保藏证明
- 6个月: 不丧失新颖性宽限、外观设计国际优先权、补缴年费+滞纳金
- 12个月: 发明/实用新型国际优先权、国内优先权
- 18个月: 发明专利公布
- 30个月(宽限32个月): PCT进入中国国家阶段
- 3年: 实质审查请求

法院/诉讼期限:
- 48小时: 诉前禁令、诉前证据保全
- 15天: 答辩期限、上诉期限、诉前措施解除
- 7天: 传票/开庭通知（提取开庭日期）
- 举证期限: 法院指定的届满日
- 2年: 专利侵权诉讼时效

其他:
- 专利年费: 提取具体到期日（期满6个月内可补缴+滞纳金）
- 商标续展: 提取到期日
- 商标异议: 公告日起30天
- 如果消息中没有提到具体日期，设deadline为null（系统会根据规则自动计算）

优先级判断:
- urgent: 48小时期限（诉前禁令/保全）、审查意见答复(OA)、恢复权利、办理登记、请求复审、行政诉讼、补缴年费滞纳金、PCT进入国家阶段、法院传票/判决/上诉
- high: 缴纳申请费、优先权文件、主动修改、实质审查请求、年费缴纳、客户指示、举证期限、商标异议
- normal: 许可备案、奖金发放、内部转发、合同审查、一般邮件回复
- low: 信息性通知、无需回复的抄送、发明专利公布

任务拆分:
- 一封邮件可能包含多个独立待办（如"答复OA+缴纳年费"），请分别提取为多个action_items
- 每个action_item应对应一个具体的可执行任务

只返回JSON，不要其他文字。"""


class MessageAnalyzer:
    """Analyzes message snapshots using LLM and rule engine."""

    def __init__(
        self,
        llm_api_key: str,
        llm_base_url: str = "https://api.minimax.chat/v1",
        llm_model: str = "MiniMax-M2.7",
        llm_provider: str = "minimax",
        rule_engine: RuleEngine | None = None,
    ):
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.llm_provider = llm_provider
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

        if self.llm_provider == "anthropic":
            text = await self._call_anthropic(prompt)
        else:
            text = await self._call_openai_compat(prompt)

        # Parse JSON from response (handle thinking tags and markdown code blocks)
        import re
        text = text.strip()

        # Remove <think>...</think> tags (some models return thinking content)
        text = re.sub(r"<think>[\s\S]*?</think>\s*", "", text).strip()

        # Remove markdown code block wrapper
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Extract JSON from response if there's extra text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match and json_match.group() != text:
            text = json_match.group()

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

    async def _call_openai_compat(self, prompt: str) -> str:
        """Call OpenAI-compatible API (Minimax, DeepSeek, etc.)."""
        url = f"{self.llm_base_url}/chat/completions"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
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

        return data["choices"][0]["message"]["content"]

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Messages API."""
        url = f"{self.llm_base_url}/messages"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
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

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]
        return text
