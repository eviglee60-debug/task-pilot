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
    # ── 国知局 (CNIPA) ───────────────────────────────────────────────────────
    # 注意：专利领域已取消15天宽限期，法定期限即deadline

    # -- 48小时 --
    DeadlineRule(
        name="cnipa_pre_injunction",
        description="诉前禁令：法院48小时内裁定",
        sender_types=[SenderType.CNIPA, SenderType.COURT],
        keywords=["诉前禁令", "责令停止", "行为保全"],
        default_delta=timedelta(hours=48),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_pre_evidence_preservation",
        description="诉前证据保全：法院48小时内裁定",
        sender_types=[SenderType.CNIPA, SenderType.COURT],
        keywords=["诉前证据保全"],
        default_delta=timedelta(hours=48),
        priority="urgent",
    ),

    # -- 15天 --
    DeadlineRule(
        name="cnipa_mail_presumption",
        description="邮寄送达推定：发文日起15日视为收到",
        sender_types=[SenderType.CNIPA],
        keywords=["邮寄送达", "推定送达"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_filing_fee",
        description="缴纳申请费：收到受理通知书15日内",
        sender_types=[SenderType.CNIPA],
        keywords=["申请费", "公布印刷费", "申请附加费", "优先权要求费"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_admin_litigation",
        description="专利侵权行政调处不服：收到通知15日内起诉",
        sender_types=[SenderType.CNIPA],
        keywords=["行政调处", "行政诉讼", "侵权纠纷"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_injunction_release",
        description="诉前禁令解除：措施之日起15日内不起诉则解除",
        sender_types=[SenderType.COURT],
        keywords=["禁令解除", "停止有关行为"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),

    # -- 1个月 --
    DeadlineRule(
        name="cnipa_service_by_publication",
        description="公告送达：公告之日起满1个月视为送达",
        sender_types=[SenderType.CNIPA],
        keywords=["公告送达"],
        default_delta=timedelta(days=30),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_invalidation_evidence",
        description="专利无效补充证据：提出请求1个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["无效宣告", "无效请求", "补充证据", "增加理由"],
        default_delta=timedelta(days=30),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_change_fee",
        description="著录事项变更费等：提出请求1个月内缴纳",
        sender_types=[SenderType.CNIPA],
        keywords=["著录事项变更", "评价报告请求费", "无效宣告请求费"],
        default_delta=timedelta(days=30),
        priority="high",
    ),

    # -- 2个月 --
    DeadlineRule(
        name="cnipa_oa_reply",
        description="审查意见答复（OA）：收到通知2个月内答复",
        sender_types=[SenderType.CNIPA],
        keywords=["审查意见", "审查意见通知书", "OA1", "OA2", "第次审查意见"],
        default_delta=timedelta(days=60),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_restore_rights",
        description="恢复权利请求：障碍消除2个月内，或收到通知2个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["恢复权利", "恢复期限", "办理恢复", "不可抗拒"],
        default_delta=timedelta(days=60),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_novelty_certificate",
        description="提交新颖性证明文件：申请日起2个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["新颖性", "国际展览会", "学术会议", "证明文件"],
        default_delta=timedelta(days=60),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_um_design_amend",
        description="实用新型/外观设计主动修改：申请日起2个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["主动修改", "实用新型修改", "外观设计修改"],
        default_delta=timedelta(days=60),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_registration",
        description="办理登记手续：收到授权通知2个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["办理登记", "登记手续", "授权通知", "授予专利权"],
        default_delta=timedelta(days=60),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_priority_fee",
        description="缴纳优先权要求费：进入日起2个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["优先权要求费", "进入日"],
        default_delta=timedelta(days=60),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_chinese_translation",
        description="提交中文译文：进入日起2个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["中文译文", "修改部分的中文"],
        default_delta=timedelta(days=60),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_pct_transfer",
        description="请求转交国际申请档案：收到通知2个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["转交文件", "国际局", "档案副本"],
        default_delta=timedelta(days=60),
        priority="high",
    ),

    # -- 3个月 --
    DeadlineRule(
        name="cnipa_priority_doc",
        description="提交优先权文件副本：申请时起3个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["优先权", "专利申请文件副本", "优先权文件"],
        default_delta=timedelta(days=90),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_invention_amend",
        description="发明专利主动修改：提实审请求时或收到实审通知书3个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["实质审查", "发明专利修改", "主动修改"],
        default_delta=timedelta(days=90),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_reexamination",
        description="请求复审：收到驳回通知3个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["复审", "驳回", "复审和无效审理"],
        default_delta=timedelta(days=90),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_administrative_action",
        description="对复审/无效决定不服起诉：收到通知3个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["不服", "起诉", "复审决定", "无效决定", "强制许可"],
        default_delta=timedelta(days=90),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_license_recordation",
        description="专利实施许可合同备案：合同生效3个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["许可备案", "实施许可", "许可合同"],
        default_delta=timedelta(days=90),
        priority="normal",
    ),
    DeadlineRule(
        name="cnipa_reward",
        description="发放发明人奖金：专利权公告3个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["奖金", "发明人", "设计人", "报酬"],
        default_delta=timedelta(days=90),
        priority="normal",
    ),
    DeadlineRule(
        name="cnipa_text_correction",
        description="国际申请文本更正：公布前或收到实审通知3个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["文本更正", "译文错误", "原始国际申请"],
        default_delta=timedelta(days=90),
        priority="high",
    ),

    # -- 4个月 --
    DeadlineRule(
        name="cnipa_security_review",
        description="保密审查：递交日起4个月内未收到通知可向外申请",
        sender_types=[SenderType.CNIPA],
        keywords=["保密审查", "国家安全", "重大利益"],
        default_delta=timedelta(days=120),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_biological_deposit",
        description="生物材料保藏证明：申请日起4个月内提交",
        sender_types=[SenderType.CNIPA],
        keywords=["生物材料", "保藏证明", "存活证明"],
        default_delta=timedelta(days=120),
        priority="high",
    ),

    # -- 6个月 --
    DeadlineRule(
        name="cnipa_novelty_grace",
        description="不丧失新颖性宽限：申请日前6个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["新颖性宽限", "不丧失新颖性"],
        default_delta=timedelta(days=180),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_design_priority",
        description="外观设计国际优先权：首次申请日起6个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["外观设计优先权", "外观设计国际"],
        default_delta=timedelta(days=180),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_annual_fee_surcharge",
        description="补缴年费+滞纳金：年费期满6个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["年费", "滞纳金", "补缴", "缴纳年费", "年费缴纳"],
        default_delta=timedelta(days=180),
        priority="urgent",
    ),

    # -- 12个月 --
    DeadlineRule(
        name="cnipa_invention_priority",
        description="发明/实用新型国际优先权：首次申请日起12个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["国际优先权", "发明优先权", "实用新型优先权"],
        default_delta=timedelta(days=365),
        priority="high",
    ),
    DeadlineRule(
        name="cnipa_domestic_priority",
        description="国内优先权：首次申请日起12个月内",
        sender_types=[SenderType.CNIPA],
        keywords=["国内优先权"],
        default_delta=timedelta(days=365),
        priority="high",
    ),

    # -- 18个月 --
    DeadlineRule(
        name="cnipa_publication",
        description="发明专利公布：申请日起满18个月",
        sender_types=[SenderType.CNIPA],
        keywords=["公布", "发明专利公布"],
        default_delta=timedelta(days=540),
        priority="normal",
    ),

    # -- 30/32个月 --
    DeadlineRule(
        name="cnipa_pct_national_phase",
        description="PCT进入中国国家阶段：优先权日起30个月内（宽限32个月）",
        sender_types=[SenderType.CNIPA],
        keywords=["进入中国", "国家阶段", "PCT", "进入日"],
        default_delta=timedelta(days=900),  # 30个月
        priority="urgent",
    ),

    # -- 3年 --
    DeadlineRule(
        name="cnipa_substantive_exam",
        description="实质审查请求：申请日起3年内",
        sender_types=[SenderType.CNIPA],
        keywords=["实质审查请求", "提实审"],
        default_delta=timedelta(days=1095),
        priority="high",
    ),

    # -- 通用（放在最后，作为兜底） --
    DeadlineRule(
        name="cnipa_official",
        description="国知局官方期限：15天（发文日+15天）",
        sender_types=[SenderType.CNIPA],
        keywords=["官方期限", "答复期限", "视为撤回", "驳回"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),
    DeadlineRule(
        name="cnipa_general",
        description="国知局其他通知",
        sender_types=[SenderType.CNIPA],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),

    # ── 商标局 (Trademark Office) ─────────────────────────────────────────────
    DeadlineRule(
        name="trademark_oa",
        description="商标审查意见答复",
        sender_types=[SenderType.TRADEMARK_OFFICE],
        keywords=["审查意见", "补正", "驳回复审"],
        default_delta=timedelta(days=30),
        priority="high",
    ),
    DeadlineRule(
        name="trademark_office_general",
        description="商标局其他通知",
        sender_types=[SenderType.TRADEMARK_OFFICE],
        default_delta=timedelta(days=15),
        priority="high",
    ),

    # ── 版权局 (Copyright Bureau) ─────────────────────────────────────────────
    DeadlineRule(
        name="copyright_notice",
        description="版权局通知",
        sender_types=[SenderType.COPYRIGHT_BUREAU],
        default_delta=timedelta(days=15),
        priority="high",
    ),

    # ── 法院 (Court) ─────────────────────────────────────────────────────────
    DeadlineRule(
        name="court_summons",
        description="法院传票/开庭通知",
        sender_types=[SenderType.COURT],
        keywords=["传票", "开庭", "开庭通知", "出庭"],
        default_delta=timedelta(days=7),
        priority="urgent",
    ),
    DeadlineRule(
        name="court_defense",
        description="法院答辩期限：收到起诉状后15天",
        sender_types=[SenderType.COURT],
        keywords=["答辩", "答辩状", "答辩期"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),
    DeadlineRule(
        name="court_evidence",
        description="法院举证期限",
        sender_types=[SenderType.COURT],
        keywords=["举证", "举证期限", "提交证据"],
        default_delta=timedelta(days=15),
        priority="high",
    ),
    DeadlineRule(
        name="court_appeal",
        description="上诉期限：判决送达后15天",
        sender_types=[SenderType.COURT],
        keywords=["上诉", "上诉期", "判决"],
        default_delta=timedelta(days=15),
        priority="urgent",
    ),
    DeadlineRule(
        name="court_filing",
        description="法院其他文件期限（从文件内容提取）",
        sender_types=[SenderType.COURT],
        default_delta=timedelta(days=10),
        priority="urgent",
    ),

    # ── 商标/版权 ────────────────────────────────────────────────────────────
    DeadlineRule(
        name="trademark_renewal",
        description="商标续展：到期前12个月内办理",
        keywords=["商标续展", "续展注册", "商标到期"],
        default_delta=timedelta(days=30),
        priority="high",
    ),
    DeadlineRule(
        name="trademark_opposition",
        description="商标异议：公告期内30天",
        keywords=["商标异议", "异议期"],
        default_delta=timedelta(days=30),
        priority="high",
    ),

    # ── 客户 ─────────────────────────────────────────────────────────────────
    DeadlineRule(
        name="client_deadline",
        description="客户指示的任务期限（从消息内容提取）",
        sender_types=[SenderType.CLIENT],
        default_delta=timedelta(days=7),
        priority="high",
    ),

    # ── 合同审查 ─────────────────────────────────────────────────────────────
    DeadlineRule(
        name="contract_review",
        description="合同审查",
        keywords=["合同审查", "合同审核", "审阅合同", "合同签署"],
        default_delta=timedelta(days=5),
        priority="normal",
    ),

    # ── 邮件 ─────────────────────────────────────────────────────────────────
    DeadlineRule(
        name="email_reply",
        description="邮件24小时内回复",
        sources=[MessageSource.EMAIL],
        default_delta=timedelta(hours=24),
        priority="high",
    ),

    # ── 内部/OA ──────────────────────────────────────────────────────────────
    DeadlineRule(
        name="oa_task",
        description="OA转达事项3天内处理",
        sender_types=[SenderType.OA],
        keywords=["OA", "转达", "通知"],
        default_delta=timedelta(days=3),
        priority="normal",
    ),
    DeadlineRule(
        name="internal_task",
        description="内部转发/指示",
        sender_types=[SenderType.INTERNAL],
        keywords=["转发", "协助", "安排", "指示"],
        default_delta=timedelta(days=3),
        priority="normal",
    ),

    # ── 默认 ─────────────────────────────────────────────────────────────────
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
