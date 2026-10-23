"""Automatic cover names with read-only reuse of previously confirmed aliases."""

import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ContractTemplate, StationAlias
from app.oa import project_summary, require_oa
from app.station_names import RULE_VERSION, group_stations, suggest_station

router = APIRouter(
    prefix="/api/v1/oa/contracts", tags=["封面名称"], dependencies=[Depends(require_oa)]
)
RecordId = Annotated[str, Path(pattern=r"^-?\d{1,19}$")]


class NameEntry(BaseModel):
    key: str
    station_code: str | None
    source_names: list[str]
    short_name: str
    status: str
    notes: list[str]
    revision: int
    can_remember: bool


class NameSuggestion(BaseModel):
    source_token: str
    cover_config: dict[str, str]
    entries: list[NameEntry]
    cover_lines: list[str]
    contract_name: str | None
    messages: list[str]
    rule_version: str = RULE_VERSION


def context(
    record_id: str, template_id: uuid.UUID, session: Session
) -> tuple[list[dict[str, Any]], dict[str, str], str]:
    summary = project_summary(record_id)
    template = session.get(ContractTemplate, template_id)
    if template is None:
        raise HTTPException(404, "模板已删除，请重新选择")
    if not template.cover_config:
        raise HTTPException(409, "当前模板未配置封面名称，请在模板管理中设置")
    config = template.cover_config
    if config["station_suffix"] != "风电站":
        raise HTTPException(409, "当前提取规则仅支持风电站模板，请手工填写合同名称")
    projects = [p.model_dump() for p in summary.projects]
    groups = group_stations(projects)
    if not groups:
        raise HTTPException(409, "该会签没有项目信息，请手工填写合同名称")
    source = {
        "record": summary.record.model_dump(),
        "template": str(template_id),
        "config": config,
        "projects": [
            {k: p[k] for k in ("id", "station_code", "station_name", "province_id")}
            for p in projects
        ],
    }
    token = hashlib.sha256(
        json.dumps(source, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return groups, config, token


def aliases_for(session: Session, groups: list[dict[str, Any]]) -> dict[str, StationAlias]:
    codes = sorted({g["station_code"] for g in groups if g["station_code"]})
    if not codes:
        return {}
    query = (
        select(StationAlias)
        .where(StationAlias.station_code.in_(codes))
        .order_by(StationAlias.station_code)
    )
    return {a.station_code: a for a in session.scalars(query)}


def build_suggestion(
    groups: list[dict[str, Any]],
    config: dict[str, str],
    token: str,
    aliases: dict[str, StationAlias],
) -> NameSuggestion:
    entries = []
    for group in groups:
        names = group["source_names"]
        alias = aliases.get(group["station_code"])
        can_remember = bool(
            group["station_code"] and len(names) == 1 and names[0] and len(group["provinces"]) == 1
        )
        status = "suggested"
        notes: list[str] = []
        if alias and alias.source_names == sorted(names) and can_remember:
            short_name, status = alias.short_name, "confirmed"
        else:
            if len(names) != 1 or len(group["provinces"]) != 1:
                short_name = ""
                notes.append("同一编码对应多个名称或省份，请核对；本次不保存映射")
                can_remember = False
            else:
                short_name, notes = suggest_station(names[0], group["provinces"][0])
            if alias:
                status = "source_changed"
                notes.insert(0, f"OA 原名称已变化；上次确认名称为“{alias.short_name}”，请重新核对")
            elif notes:
                status = "review"
        entries.append(
            NameEntry(
                key=group["key"],
                station_code=group["station_code"],
                source_names=names,
                short_name=short_name,
                status=status,
                notes=notes,
                revision=alias.revision if alias else 0,
                can_remember=can_remember,
            )
        )
    messages = []
    if len(entries) > 1:
        messages.append("涉及多个场站，请核对合并后的封面名称")
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.short_name:
            counts[entry.short_name] = counts.get(entry.short_name, 0) + 1
    for entry in entries:
        if counts.get(entry.short_name, 0) > 1:
            entry.notes.append("不同场站得到相同主体名，请补充区分信息，不自动合并")
            entry.status = "review"
    lines = compose([entry.short_name for entry in entries], config)
    return NameSuggestion(
        source_token=token,
        cover_config=config,
        entries=entries,
        cover_lines=lines,
        contract_name="".join(lines) if lines else None,
        messages=messages,
    )


def compose(names: list[str], config: dict[str, str]) -> list[str]:
    if not names or any(not n for n in names):
        return []
    first = "、".join(names) + config["station_suffix"]
    if len(first) > 3000:
        return []
    return [first, config["product_line"], config["document_line"]]


@router.get("/{record_id}/name-suggestions", response_model=NameSuggestion)
def suggestions(record_id: RecordId, template_id: uuid.UUID) -> NameSuggestion:
    with SessionLocal() as session:
        groups, config, token = context(record_id, template_id, session)
        return build_suggestion(groups, config, token, aliases_for(session, groups))
