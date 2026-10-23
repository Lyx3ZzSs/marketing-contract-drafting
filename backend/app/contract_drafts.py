"""Stateless preview boundary. Only allowlisted edits are accepted from the browser."""

import uuid
from dataclasses import asdict, dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from lxml import etree as ET
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth import require_admin
from app.contract_document import build_document, field_catalog, preview_sections
from app.contract_values import MaterialSummary, aggregate
from app.db import SessionLocal
from app.models import ContractTemplate
from app.oa import ProjectSummary

router = APIRouter(prefix="/api/v1/templates", tags=["合同联动"])
ShortText = Annotated[str, Field(max_length=2000, pattern=r"^[^\x00-\x08\x0b\x0c\x0e-\x1f]*$")]


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(max_length=64)
    source: ProjectSummary | None = None
    contract_name: ShortText = ""
    remarks: dict[str, ShortText] = Field(default_factory=dict, max_length=10000)
    fields: dict[str, ShortText] = Field(default_factory=dict, max_length=100)


class FieldSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(max_length=64)
    editable: dict[str, bool] = Field(max_length=100)


def template_or_404(template: ContractTemplate | None) -> ContractTemplate:
    if template is None:
        raise HTTPException(404, "模板不存在")
    return template


def catalog(template: ContractTemplate) -> dict[str, Any]:
    return field_catalog(template.original, template.field_bindings, template.cover_config)


def check_revision(template: ContractTemplate, expected: str) -> dict[str, Any]:
    result = catalog(template)
    if expected != result["revision"]:
        raise HTTPException(409, "模板配置已变化，请重新加载条款")
    return result


@router.get("/{template_id}/fields")
def get_fields(template_id: uuid.UUID) -> dict[str, Any]:
    with SessionLocal() as session:
        return catalog(template_or_404(session.get(ContractTemplate, template_id)))


@router.put("/{template_id}/fields", dependencies=[Depends(require_admin)])
def configure_fields(template_id: uuid.UUID, data: FieldSettings) -> dict[str, Any]:
    with SessionLocal.begin() as session:
        template = template_or_404(
            session.scalar(
                select(ContractTemplate).where(ContractTemplate.id == template_id).with_for_update()
            )
        )
        current = check_revision(template, data.revision)
        allowed = {f["id"] for f in current["fields"] if f["configurable"]}
        if not allowed:
            raise HTTPException(422, "条款当前全部只读，暂不支持修改编辑权限")
        if set(data.editable) != allowed:
            raise HTTPException(422, "只能设置当前模板识别出的人工黄色字段")
        template.field_bindings = data.editable
        session.flush()
        return catalog(template)


@dataclass
class PreparedDocument:
    revision: str
    root: ET._Element
    fields: dict[ET._Element, dict[str, Any]]
    errors: list[str]
    material: MaterialSummary | None


def prepare_document(template: ContractTemplate, data: DraftInput) -> PreparedDocument:
    settings = check_revision(template, data.revision)
    errors = []
    material = None
    if not settings["supported"]:
        errors.append("此模板尚未配置标的物映射，请使用已适配的采购合同模板")
    elif data.source is None:
        errors.append("请先按合同编号查询 OA 项目信息")
    else:
        try:
            material = aggregate(data.source, data.remarks)
        except ValueError as exc:
            errors.append(str(exc))
    if not data.contract_name.strip():
        errors.append("请填写封面合同名称")
    try:
        root, fields = build_document(
            template.original,
            template.field_bindings,
            template.cover_config,
            data.contract_name,
            material,
            data.fields,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return PreparedDocument(settings["revision"], root, fields, errors, material)


def render_preview(template: ContractTemplate, data: DraftInput) -> dict[str, Any]:
    document = prepare_document(template, data)
    return {
        "revision": document.revision,
        "sections": preview_sections(document.root, document.fields, template.original),
        "errors": document.errors,
        "material": asdict(document.material) if document.material else None,
    }


@router.post("/{template_id}/preview")
def preview(template_id: uuid.UUID, data: DraftInput) -> dict[str, Any]:
    with SessionLocal() as session:
        template = template_or_404(session.get(ContractTemplate, template_id))
        return render_preview(template, data)
