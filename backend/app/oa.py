"""Contract lookup and deterministic RMB aggregation; no workflow/model invocation."""

import logging
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app import oa_repository as repository
from app.core.config import get_settings
from app.oa_enums import OA_CURRENCIES

logger = logging.getLogger(__name__)


def require_oa() -> None:
    if not get_settings().oa_configured:
        raise HTTPException(503, "OA 数据库未配置，请联系管理员")


router = APIRouter(
    prefix="/api/v1/oa/contracts", tags=["OA 合同取数"], dependencies=[Depends(require_oa)]
)


class Candidate(BaseModel):
    id: str
    serial_number: str
    status: str | None
    initiated_at: str | None


class LookupResult(BaseModel):
    contract_number: str
    candidates: list[Candidate]


class Project(BaseModel):
    id: str
    project_code: str | None
    project_name: str | None
    station_name: str | None
    station_code: str | None = None
    province_id: str | None = None
    amount: str | None
    currency_id: str | None
    currency: str | None
    currency_name: str | None
    software_copyright_name: str | None
    hardware_amount: str | None
    software_service_amount: str | None
    other_software_service_amount: str | None


class ProjectSummary(BaseModel):
    record: Candidate
    station_names: list[str]
    contract_name: str | None
    amount: str | None
    currency: str | None
    currency_name: str | None
    amount_currency: Literal["CNY"] = "CNY"
    project_count: int
    projects: list[Project]
    issues: list[str]
    warnings: list[str]
    retrieved_at: datetime


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def optional_amount(value: Decimal | None) -> str | None:
    return format(value, ".2f") if value is not None else None


def candidate(row: dict[str, Any]) -> Candidate:
    date = row["initiated_at"]
    return Candidate(
        id=str(row["id"]),
        serial_number=str(row["serial_number"] or ""),
        status=optional_text(row["status"]),
        initiated_at=date.isoformat() if date is not None else None,
    )


def summarize(main: dict[str, Any], rows: list[dict[str, Any]]) -> ProjectSummary:
    issues: list[str] = []
    warnings: list[str] = []
    stations: list[str] = []
    seen: set[str] = set()
    projects: list[Project] = []
    missing_names = missing_amounts = nonpositive = 0
    missing_currencies = 0
    unknown_currencies: set[str] = set()
    currencies: dict[str, str] = {}
    # DECIMAL(22,2) plus up to 10,000 rows must not use the default 28-digit context.
    with localcontext() as context:
        context.prec = 40
        total = Decimal("0.00")
        for row in rows:
            station = optional_text(row["station_name"])
            if not station:
                missing_names += 1
            elif station not in seen:
                seen.add(station)
                stations.append(station)
            amount = row["amount"]
            if amount is None:
                missing_amounts += 1
            else:
                total += amount
                nonpositive += amount <= 0
            currency_id = optional_text(row["currency_id"])
            currency = OA_CURRENCIES.get(currency_id) if currency_id is not None else None
            if currency_id is None:
                missing_currencies += 1
            elif currency is None:
                unknown_currencies.add(currency_id)
            else:
                currencies[currency[0]] = currency[1]
            projects.append(
                Project(
                    id=str(row["id"]),
                    project_code=optional_text(row["project_code"]),
                    project_name=optional_text(row["project_name"]),
                    station_name=station,
                    station_code=optional_text(row.get("station_code")),
                    province_id=optional_text(row.get("province_id")),
                    amount=format(amount, ".2f") if amount is not None else None,
                    currency_id=currency_id,
                    currency=currency[0] if currency else None,
                    currency_name=currency[1] if currency else None,
                    software_copyright_name=optional_text(row["software_copyright_name"]),
                    hardware_amount=optional_amount(row["hardware_amount"]),
                    software_service_amount=optional_amount(row["software_service_amount"]),
                    other_software_service_amount=optional_amount(
                        row["other_software_service_amount"]
                    ),
                )
            )
        total_text = format(total, ".2f")
    if not rows:
        issues.append("该会签没有项目信息")
    if missing_names:
        warnings.append(f"有 {missing_names} 条项目明细缺少场站名称，请核对封面名称")
    if missing_amounts:
        issues.append(f"有 {missing_amounts} 条项目明细缺少合同金额，无法生成完整合计")
    if missing_currencies:
        issues.append(f"有 {missing_currencies} 条项目明细未填写币种，请在 OA 中补充")
    if unknown_currencies:
        issues.append("存在未映射的币种 ID：" + "、".join(sorted(unknown_currencies)))
    if len(currencies) > 1:
        issues.append("项目明细包含多个币种（" + "、".join(currencies.values()) + "），请核对")
    resolved_currency = (
        next(iter(currencies.items()))
        if len(currencies) == 1 and not missing_currencies and not unknown_currencies
        else None
    )
    if nonpositive:
        warnings.append(f"有 {nonpositive} 条零金额或负金额明细，已按原值计入，请核对")
    return ProjectSummary(
        record=candidate(main),
        station_names=stations,
        contract_name=None,  # Cover naming is template-specific and has a separate endpoint.
        amount=total_text if rows and not missing_amounts else None,
        currency=resolved_currency[0] if resolved_currency else None,
        currency_name=resolved_currency[1] if resolved_currency else None,
        project_count=len(rows),
        projects=projects,
        issues=issues,
        warnings=warnings,
        retrieved_at=datetime.now(UTC),
    )


def database_error(exc: SQLAlchemyError) -> HTTPException:
    # Never log the DB exception text: it can contain connection/SQL parameters.
    logger.warning("OA read failed", extra={"error_type": type(exc).__name__})
    return HTTPException(503, "OA 查询失败或超时，请稍后重试；持续失败请联系管理员")


@router.get("/lookup", response_model=LookupResult)
def lookup(contract_number: Annotated[str, Query(min_length=1, max_length=255)]) -> LookupResult:
    number = contract_number.strip()
    if not number:
        raise HTTPException(422, "请输入合同编号（OA 流水号）")
    try:
        rows = repository.find_contracts(number)
    except SQLAlchemyError as exc:
        raise database_error(exc) from None
    if len(rows) > 100:
        raise HTTPException(409, "同一流水号匹配超过 100 条会签，请联系管理员核对数据")
    return LookupResult(contract_number=number, candidates=[candidate(row) for row in rows])


@router.get("/{record_id}/project-summary", response_model=ProjectSummary)
def project_summary(record_id: Annotated[str, Path(pattern=r"^-?\d{1,19}$")]) -> ProjectSummary:
    identifier = int(record_id)
    if not -(2**63) <= identifier < 2**63:
        raise HTTPException(422, "会签记录标识无效")
    try:
        main, rows = repository.read_projects(identifier)
    except SQLAlchemyError as exc:
        raise database_error(exc) from None
    if main is None:
        raise HTTPException(404, "会签记录不存在，请重新查询")
    if len(rows) > 10000:
        raise HTTPException(409, "项目明细超过 10000 条，未进行截断汇总，请联系管理员")
    return summarize(main, rows)
