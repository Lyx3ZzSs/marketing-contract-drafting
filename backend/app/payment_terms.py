"""One optional payment schedule per contract, calculated from confirmed item ratios."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contract_values import CENT, money, uppercase_rmb
from app.oa import ProjectSummary

STAGES = ("advance", "delivery", "acceptance", "warranty")


class PaymentRatio(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["advance", "delivery", "acceptance", "warranty"]
    percentage: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)


@dataclass(frozen=True)
class PaymentValue:
    percentage: str
    amount: str
    uppercase: str


def resolve_payments(
    source: ProjectSummary, by_project: dict[str, list[PaymentRatio]], total: str
) -> tuple[PaymentValue, ...] | None:
    if by_project.keys() - {project.id for project in source.projects}:
        raise ValueError("付款方式包含不属于当前合同的标的，请重新查询")
    schedule: dict[str, Decimal] | None = None
    first_index = 0
    for index, project in enumerate(source.projects, 1):
        terms = by_project.get(project.id, [])
        if not terms:
            continue
        ratios: dict[str, Decimal] = {term.id: term.percentage for term in terms}
        label = f"第 {index} 条合同标的（{project.software_copyright_name or '未填写'}）"
        if len(ratios) != len(terms):
            raise ValueError(f"{label}：付款节点不能重复")
        if sum(ratios.values(), Decimal(0)) != 100:
            raise ValueError(f"{label}：付款比例合计须为 100%")
        if schedule is not None and ratios != schedule:
            raise ValueError(f"第 {first_index} 条与{label}的付款比例不一致，请核对后预览合同")
        if schedule is None:
            schedule, first_index = ratios, index
    if schedule is None:
        return None

    contract_total = money(total)
    remaining = abs(contract_total)
    last = next(stage for stage in reversed(STAGES) if stage in schedule)
    result = []
    for stage in STAGES:
        ratio = schedule.get(stage, Decimal(0))
        if not ratio:
            amount = Decimal("0.00")
        elif stage == last:
            amount = remaining
        else:
            rounded = (abs(contract_total) * ratio / 100).quantize(CENT, rounding=ROUND_HALF_UP)
            # Very small contracts must not produce a negative final instalment.
            amount = min(rounded, remaining)
        remaining -= amount
        if contract_total < 0 and amount:
            amount = -amount
        result.append(
            PaymentValue(
                format(ratio, "f").rstrip("0").rstrip(".")
                if "." in format(ratio, "f")
                else format(ratio, "f"),
                format(amount, ".2f"),
                uppercase_rmb(amount),
            )
        )
    return tuple(result)
