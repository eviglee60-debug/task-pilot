"""FastAPI application — wires all services together.

Startup:
1. Initialize storage (archive, audit log)
2. Initialize connectors (email, dingtalk, wechat)
3. Initialize services (analyzer, task manager, calendar)
4. Wire routers to services
5. Start background poller (if enabled)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config.settings import Settings
from src.connectors.dingtalk_connector import DingTalkConnector
from src.connectors.email_connector import EmailConnector
from src.routers import audit as audit_router
from src.routers import snapshots as snapshot_router
from src.routers import tasks as task_router
from src.services.analyzer import MessageAnalyzer
from src.services.archive import SnapshotArchive
from src.services.audit import AuditLog
from src.services.calendar import CalendarService
from src.services.rules import RuleEngine
from src.services.task_manager import TaskManager
from src.services.poller import MessagePoller

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = settings or Settings()

    # ── Storage ──────────────────────────────────────────────────────────────
    archive = SnapshotArchive(storage_path=settings.snapshot_path)
    audit = AuditLog(storage_path=settings.audit_path)

    # ── Connectors ───────────────────────────────────────────────────────────
    connectors = []
    if settings.ms_graph_token:
        email_conn = EmailConnector(
            access_token=settings.ms_graph_token,
            mailbox=settings.mailbox,
        )
        connectors.append(email_conn)
        logger.info("Email connector enabled (mailbox=%s)", settings.mailbox)

    if settings.dingtalk_app_key:
        dingtalk_conn = DingTalkConnector(
            app_key=settings.dingtalk_app_key,
            app_secret=settings.dingtalk_app_secret,
        )
        connectors.append(dingtalk_conn)
        logger.info("DingTalk connector enabled")

    if not connectors:
        logger.warning(
            "No connectors configured. Set TASK_PILOT_MS_GRAPH_TOKEN "
            "or TASK_PILOT_DINGTALK_APP_KEY in .env"
        )

    # ── Services ─────────────────────────────────────────────────────────────
    rule_engine = RuleEngine()

    analyzer = MessageAnalyzer(
        llm_api_key=settings.llm_api_key,
        llm_base_url=settings.llm_base_url,
        llm_model=settings.llm_model,
        rule_engine=rule_engine,
    )

    calendar = CalendarService(
        access_token=settings.ms_graph_token,
        calendar_id=settings.calendar_id,
    )

    task_manager = TaskManager(
        archive=archive,
        calendar=calendar,
        audit=audit,
    )

    poller = MessagePoller(
        connectors=connectors,
        archive=archive,
        analyzer=analyzer,
        task_manager=task_manager,
        audit=audit,
        poll_interval=settings.poll_interval_seconds,
    )

    # ── Lifespan ─────────────────────────────────────────────────────────────
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Task-pilot starting up...")
        if connectors:
            await poller.start()
            logger.info(
                "Background poller started (interval=%ds)",
                settings.poll_interval_seconds,
            )
        yield
        await poller.stop()
        logger.info("Task-pilot shutting down.")

    # ── App ──────────────────────────────────────────────────────────────────
    app = FastAPI(
        title="Task Pilot",
        description=(
            "自动从邮件、钉钉、微信中提取待办事项，经确认后写入Outlook日历。"
            "所有源数据只读访问，绝不修改或删除。"
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # Wire routers
    task_router.init_router(task_manager)
    snapshot_router.init_router(archive)
    audit_router.init_router(audit)

    app.include_router(task_router.router)
    app.include_router(snapshot_router.router)
    app.include_router(audit_router.router)

    @app.get("/health")
    async def health():
        connector_status = {}
        for conn in connectors:
            try:
                ok = await conn.health_check()
                connector_status[conn.source.value] = "ok" if ok else "error"
            except Exception:
                connector_status[conn.source.value] = "error"

        return {
            "status": "ok",
            "snapshots": archive.count(),
            "pending_tasks": len(task_manager.get_pending()),
            "connectors": connector_status,
        }

    return app


# Entry point for `python -m src.app`
app = create_app()
