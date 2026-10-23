"""Preview task lifecycle and expiry recovery, separate from conversion and storage."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import DocumentPreview, Task
from app.pdf_converter import convert_pdf
from app.preview_files import delete_pdf, write_pdf
from app.task_service import TERMINAL, update_task
from app.worker import celery_app

logger = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=10)


def expire_stalled_task(task_id: uuid.UUID) -> None:
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        stale = (
            task
            and task.status not in TERMINAL
            and task.created_at < datetime.now(UTC) - STALE_AFTER
        )
    if stale:
        update_task(
            task_id,
            "failed",
            "failed",
            {"message": "预览任务超时，请重新生成"},
            error="预览任务超时，请重新生成",
        )


@celery_app.task(name="contract_drafting.preview", soft_time_limit=150, time_limit=180)
def run_preview(preview_id: str) -> None:
    ident = uuid.UUID(preview_id)
    with SessionLocal.begin() as session:
        artifact = session.get(DocumentPreview, ident)
        if artifact is None:
            return
        task_id = artifact.task_id
        task = session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None or task.status != "queued":
            return
        task.status = "running"  # Atomic claim: a duplicate delivery cannot render twice.
        docx, backend = artifact.source_docx, artifact.storage_backend
    key = f"document-previews/{ident.hex}.pdf"
    uploaded = False
    try:
        if docx is None:
            raise ValueError("预览输入已过期，请重新生成")
        update_task(task_id, "running", "progress", {"progress": 20, "message": "正在排版合同"})
        pdf = convert_pdf(docx)
        update_task(task_id, "running", "progress", {"progress": 85, "message": "正在准备预览"})
        write_pdf(backend, key, pdf)
        uploaded = True
        with SessionLocal.begin() as session:
            artifact = session.get(DocumentPreview, ident)
            task = session.get(Task, task_id)
            if artifact is None or task is None or task.status in TERMINAL:
                raise ValueError("预览任务已失效，请重新生成")
            artifact.file_key = key
        update_task(
            task_id,
            "succeeded",
            "completed",
            {"progress": 100, "message": "合同预览已就绪"},
            result={"preview_id": preview_id},
        )
    except Exception as exc:
        if uploaded:
            try:
                delete_pdf(backend, key)
            except Exception:
                logger.warning("preview cleanup deferred", extra={"task_id": str(task_id)})
        message = str(exc) if isinstance(exc, ValueError) else "合同预览生成失败，请重试"
        update_task(task_id, "failed", "failed", {"message": message}, error=message)
        logger.error(
            "preview failed", extra={"task_id": str(task_id), "error_type": type(exc).__name__}
        )
    finally:
        with SessionLocal.begin() as session:
            artifact = session.get(DocumentPreview, ident)
            if artifact:
                artifact.source_docx = None


def cleanup_preview(ident: uuid.UUID, now: datetime) -> None:
    with SessionLocal() as session:
        artifact = session.get(DocumentPreview, ident)
        if artifact is None:
            return
        task_id = artifact.task_id
    expire_stalled_task(task_id)
    with SessionLocal.begin() as session:
        artifact = session.get(DocumentPreview, ident)
        task = session.get(Task, task_id)
        if artifact is None or task is None or task.status not in TERMINAL:
            return
        artifact.source_docx = None
        if artifact.expires_at <= now or task.status == "failed":
            # Deterministic key also removes files left by an interrupted worker.
            delete_pdf(artifact.storage_backend, f"document-previews/{ident.hex}.pdf")
            artifact.file_key = None
        if artifact.expires_at <= now:
            session.delete(artifact)
            session.flush()
            session.delete(task)


@celery_app.task(name="contract_drafting.cleanup_previews")
def cleanup_previews() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as session:
        ids = list(session.scalars(select(DocumentPreview.id)))
    for ident in ids:
        try:
            cleanup_preview(ident, now)
        except Exception as exc:
            logger.error(
                "preview cleanup failed",
                extra={"preview_id": str(ident), "error_type": type(exc).__name__},
            )
