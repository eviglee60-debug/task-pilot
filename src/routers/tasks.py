"""API routes for task management and confirmation.

Endpoints:
- GET  /tasks/pending     — List pending task proposals
- GET  /tasks             — List all tasks (with optional status filter)
- POST /tasks/{id}/confirm — Confirm a task
- POST /tasks/{id}/modify  — Modify and confirm a task
- POST /tasks/{id}/ignore  — Ignore a task
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.schemas import TaskStatus

router = APIRouter(prefix="/tasks", tags=["tasks"])

# TaskManager is injected at app startup — this module holds a reference
_task_manager = None


def init_router(task_manager):
    """Called once at startup to wire in the TaskManager."""
    global _task_manager
    _task_manager = task_manager


class ModifyRequest(BaseModel):
    title: str | None = None
    deadline: datetime | None = None
    priority: str | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    deadline: datetime | None
    priority: str
    category: str
    source: str
    sender: str
    sender_type: str
    status: str
    created_at: datetime
    confirmed_at: datetime | None
    calendar_event_id: str | None


def _to_response(task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        deadline=task.deadline,
        priority=task.priority,
        category=task.category,
        source=task.source.value,
        sender=task.sender,
        sender_type=task.sender_type.value,
        status=task.status.value,
        created_at=task.created_at,
        confirmed_at=task.confirmed_at,
        calendar_event_id=task.calendar_event_id,
    )


@router.get("/pending", response_model=list[TaskResponse])
async def list_pending():
    """List all tasks awaiting user confirmation."""
    return [_to_response(t) for t in _task_manager.get_pending()]


@router.get("", response_model=list[TaskResponse])
async def list_tasks(status: str | None = None, limit: int = 50):
    """List all tasks, optionally filtered by status."""
    task_status = TaskStatus(status) if status else None
    return [_to_response(t) for t in _task_manager.get_all(status=task_status, limit=limit)]


@router.post("/{task_id}/confirm", response_model=TaskResponse)
async def confirm_task(task_id: str):
    """Confirm a pending task — writes it to Outlook calendar."""
    try:
        task = _task_manager.confirm(task_id)
        return _to_response(task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{task_id}/modify", response_model=TaskResponse)
async def modify_task(task_id: str, req: ModifyRequest):
    """Modify a pending task before confirming it."""
    try:
        task = _task_manager.modify_and_confirm(
            task_id,
            title=req.title,
            deadline=req.deadline,
            priority=req.priority,
        )
        return _to_response(task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{task_id}/ignore", response_model=TaskResponse)
async def ignore_task(task_id: str):
    """Ignore a pending task — it will not be added to the calendar."""
    try:
        task = _task_manager.ignore(task_id)
        return _to_response(task)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
