import hashlib
import uuid
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.auth import require_admin
from app.db import SessionLocal
from app.models import ContractTemplate
from app.station_names import KNOWN_TEMPLATE_SHA, WIND_COVER
from app.template_parser import MAX_UPLOAD, TemplateParseError, parse_docx

router = APIRouter(prefix="/api/v1/templates", tags=["合同模板"])
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class CoverConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    station_suffix: str = Field(min_length=1, max_length=30, pattern=r"^[^\r\n\x00]+$")
    product_line: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n\x00]+$")
    document_line: str = Field(min_length=1, max_length=100, pattern=r"^[^\r\n\x00]+$")


def summary(template: ContractTemplate) -> dict[str, Any]:
    return {
        "id": str(template.id),
        "name": template.name,
        "sourceFile": template.source_file,
        "sourceSha256": template.source_sha256,
        "sectionCount": template.section_count,
        "createdAt": template.created_at.isoformat(),
        "storage": "postgresql",
        "coverConfig": template.cover_config,
    }


@router.get("")
def list_templates() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        return [
            summary(t)
            for t in session.scalars(
                select(ContractTemplate).order_by(
                    ContractTemplate.created_at.desc(), ContractTemplate.id
                )
            )
        ]


def persist_template(data: bytes, name: str, filename: str) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    try:
        sections = parse_docx(data)
    except (TemplateParseError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        with SessionLocal.begin() as session:
            template = ContractTemplate(
                name=name,
                source_file=filename,
                source_sha256=digest,
                original=data,
                sections=sections,
                section_count=len(sections),
                cover_config=dict(WIND_COVER) if digest == KNOWN_TEMPLATE_SHA else None,
            )
            session.add(template)
            session.flush()
            return {**summary(template), "sections": sections}
    except IntegrityError as exc:
        raise HTTPException(409, "相同文件已上传，请从模板列表中选择。") from exc


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
async def upload_template(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
    name: str = Query(min_length=1, max_length=200),
) -> dict[str, Any]:
    # Raw file body avoids buffering an unbounded multipart upload before size validation.
    if not filename.lower().endswith(".docx") or any(
        c in filename for c in ("/", "\\", "\r", "\n", "\x00")
    ):
        raise HTTPException(422, "请选择 .docx 文件，文件名不能包含路径或控制字符。")
    if not name.strip():
        raise HTTPException(422, "请填写模板名称。")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_UPLOAD:
            raise HTTPException(413, "模板文件不能超过 10 MB。")
        data.extend(chunk)
    return await run_in_threadpool(persist_template, bytes(data), name.strip(), filename)


@router.get("/{template_id}")
def get_template(template_id: uuid.UUID) -> dict[str, Any]:
    with SessionLocal() as session:
        template = session.get(ContractTemplate, template_id)
        if template is None:
            raise HTTPException(404, "模板不存在。")
        return {**summary(template), "sections": template.sections}


@router.put("/{template_id}/cover-config", dependencies=[Depends(require_admin)])
def configure_cover(template_id: uuid.UUID, config: CoverConfig) -> dict[str, Any]:
    with SessionLocal.begin() as session:
        template = session.get(ContractTemplate, template_id)
        if template is None:
            raise HTTPException(404, "模板不存在。")
        template.cover_config = config.model_dump()
        session.flush()
        return summary(template)


@router.delete("/{template_id}", dependencies=[Depends(require_admin)])
def delete_template(template_id: uuid.UUID) -> dict[str, str]:
    with SessionLocal.begin() as session:
        deleted_id = session.scalar(
            delete(ContractTemplate)
            .where(ContractTemplate.id == template_id)
            .returning(ContractTemplate.id)
        )
        if deleted_id is None:
            raise HTTPException(404, "模板不存在或已删除。")
    return {"id": str(deleted_id)}


@router.get("/{template_id}/file", dependencies=[Depends(require_admin)])
def download_template(template_id: uuid.UUID) -> Response:
    with SessionLocal() as session:
        template = session.get(ContractTemplate, template_id)
        if template is None:
            raise HTTPException(404, "模板不存在。")
        disposition = "attachment; filename*=UTF-8''" + quote(template.source_file, safe="")
        return Response(
            template.original,
            media_type=DOCX_TYPE,
            headers={
                "Content-Disposition": disposition,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
