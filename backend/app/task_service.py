import uuid
from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Task, TaskEvent

TERMINAL = {"succeeded", "failed"}


def update_task(
    task_id: uuid.UUID,
    status: str,
    kind: str,
    payload: dict[str, Any],
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    # Lock per task: status and its event are committed atomically and ordered.
    with SessionLocal.begin() as session:
        task = session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None or task.status in TERMINAL:
            return
        task.status = status
        task.result = result
        task.error = error
        session.add(TaskEvent(task_id=task_id, kind=kind, payload={**payload, "status": status}))


def event_batch(task_id: uuid.UUID, after: int) -> tuple[list[dict[str, Any]], str]:
    with SessionLocal() as session:
        # Read status first: if it is terminal the subsequent event query sees its committed event.
        task = session.get(Task, task_id)
        if task is None:
            return [], "missing"
        rows = session.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id, TaskEvent.id > after)
            .order_by(TaskEvent.id)
            .limit(100)
        ).all()
        return [{"id": row.id, "event": row.kind, "data": row.payload} for row in rows], task.status
