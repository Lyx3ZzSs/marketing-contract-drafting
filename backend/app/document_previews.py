"""Full-document preview API: immutable inputs, deduplication, and expiring files."""

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select, text

from app.auth import CurrentUser, Principal, require_owner
from app.contract_document import package_preview_document
from app.contract_drafts import DraftInput, check_revision, prepare_document, template_or_404
from app.core.config import get_settings
from app.db import SessionLocal
from app.models import ContractTemplate, DocumentPreview, Task, TaskEvent
from app.pdf_permissions import readonly_pdf
from app.preview_files import read_pdf
from app.preview_tasks import expire_stalled_task, run_preview
from app.task_service import update_task

router = APIRouter(prefix="/api/v1", tags=["完整合同预览"])


def preview_view(ident: uuid.UUID, user: Principal) -> dict[str, Any]:
    with SessionLocal() as session:
        artifact = session.get(DocumentPreview, ident)
        if artifact is not None:
            task = session.get(Task, artifact.task_id)
            require_owner(task.owner_sub if task else None, user)
        if artifact is None or artifact.expires_at <= datetime.now(UTC):
            raise HTTPException(410, "合同预览已过期，请重新生成")
        template = template_or_404(session.get(ContractTemplate, artifact.template_id))
        check_revision(template, artifact.revision)
        task_id = artifact.task_id
    expire_stalled_task(task_id)
    with SessionLocal() as session:
        artifact = session.get(DocumentPreview, ident)
        task = session.get(Task, task_id)
        if artifact is None or task is None:
            raise HTTPException(410, "合同预览已过期，请重新生成")
        return {
            "id": str(artifact.id),
            "task_id": str(task_id),
            "status": task.status,
            "revision": artifact.revision,
            "fingerprint": artifact.fingerprint,
            "title": artifact.title,
            "expires_at": artifact.expires_at.isoformat(),
            "error": task.error,
            "file_url": f"/api/v1/document-previews/{ident}/file"
            if task.status == "succeeded"
            else None,
        }


@router.post("/templates/{template_id}/document-previews", status_code=202)
def create_preview(
    template_id: uuid.UUID, data: DraftInput, request: Request, user: CurrentUser
) -> dict[str, Any]:
    settings = get_settings()
    if settings.preview_storage == "s3" and not settings.storage_configured:
        raise HTTPException(503, "预览存储 MinIO 未配置")
    with SessionLocal.begin() as session:
        template = template_or_404(session.get(ContractTemplate, template_id))
        document = prepare_document(template, data)
        if document.errors:
            raise HTTPException(422, "；".join(document.errors))
        docx = package_preview_document(template.original, document.root)
        record_id = data.source.record.id if data.source else ""
        cache_context = f"{user.sub}:{template_id}:{document.revision}:{record_id}"
        fingerprint = hashlib.sha256(
            docx + (cache_context + settings.preview_renderer_revision).encode()
        ).hexdigest()
        # A transaction-scoped lock collapses simultaneous requests for the same snapshot.
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(fingerprint[:15], 16)}
        )
        existing = session.scalar(
            select(DocumentPreview)
            .join(Task)
            .where(
                DocumentPreview.fingerprint == fingerprint,
                Task.owner_sub == user.sub,
                DocumentPreview.expires_at > datetime.now(UTC),
                Task.status.in_(["queued", "running", "succeeded"]),
            )
            .order_by(DocumentPreview.created_at.desc())
        )
        existing_task = session.get(Task, existing.task_id) if existing else None
        if (
            existing
            and existing_task
            and (
                existing.created_at > datetime.now(UTC) - timedelta(minutes=10)
                or existing_task.status == "succeeded"
            )
        ):
            ident, created = existing.id, False
        else:
            ident, task_id, created = uuid.uuid4(), uuid.uuid4(), True
            session.add(
                Task(
                    id=task_id,
                    owner_sub=user.sub,
                    status="queued",
                    input={"kind": "document_preview", "preview_id": str(ident)},
                    request_id=request.state.request_id,
                )
            )
            session.flush()
            session.add(
                DocumentPreview(
                    id=ident,
                    task_id=task_id,
                    template_id=template_id,
                    revision=document.revision,
                    fingerprint=fingerprint,
                    title=data.contract_name,
                    source_docx=docx,
                    storage_backend=settings.preview_storage,
                    expires_at=datetime.now(UTC) + timedelta(hours=settings.preview_ttl_hours),
                )
            )
            session.add(
                TaskEvent(
                    task_id=task_id,
                    kind="progress",
                    payload={"status": "queued", "progress": 0, "message": "等待生成合同预览"},
                )
            )
    if created:
        try:
            run_preview.apply_async(
                args=[str(ident)], task_id=str(task_id), retry=False, expires=600
            )
        except Exception:
            update_task(
                task_id,
                "failed",
                "failed",
                {"message": "预览任务入队失败，请重试"},
                error="预览任务入队失败，请重试",
            )
    return preview_view(ident, user)


@router.get("/document-previews/{preview_id}")
def get_preview(preview_id: uuid.UUID, user: CurrentUser) -> dict[str, Any]:
    return preview_view(preview_id, user)


def pdf_response(preview_id: uuid.UUID, user: Principal, *, download: bool) -> Response:
    view = preview_view(preview_id, user)
    if view["status"] != "succeeded":
        raise HTTPException(409, "合同预览尚未就绪")
    with SessionLocal() as session:
        artifact = session.get(DocumentPreview, preview_id)
        if artifact is None or not artifact.file_key:
            raise HTTPException(410, "预览文件已过期，请重新生成")
        backend, key = artifact.storage_backend, artifact.file_key
    try:
        data = read_pdf(backend, key)
    except FileNotFoundError:
        # Do not keep serving a cache record whose local file has disappeared.
        with SessionLocal.begin() as session:
            artifact = session.get(DocumentPreview, preview_id)
            if artifact:
                artifact.expires_at = datetime.now(UTC)
        raise HTTPException(410, "预览文件已失效，请重新生成") from None
    except Exception as exc:
        raise HTTPException(503, "预览文件暂时无法读取，请重试") from exc
    disposition = 'inline; filename="contract-preview.pdf"'
    if download:
        try:
            data = readonly_pdf(data)
        except Exception as exc:
            raise HTTPException(503, "只读 PDF 准备失败，请重试") from exc
        title = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', " ", view["title"])
        filename = (" ".join(title.split()).strip(" .")[:100] or "合同") + ".pdf"
        disposition = f"attachment; filename=contract.pdf; filename*=UTF-8''{quote(filename)}"
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/document-previews/{preview_id}/file")
def preview_file(preview_id: uuid.UUID, user: CurrentUser) -> Response:
    return pdf_response(preview_id, user, download=False)


@router.get("/document-previews/{preview_id}/download")
def download_preview(preview_id: uuid.UUID, user: CurrentUser) -> Response:
    return pdf_response(preview_id, user, download=True)
