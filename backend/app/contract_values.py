"""Pure contract calculations. OA rows stay distinct; only equal unit prices aggregate."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.oa import ProjectSummary

CENT = Decimal("0.01")
CATEGORY_FIELDS = ("hardware_amount", "software_service_amount", "other_software_service_amount")
CATEGORY_LABELS = ("硬件", "软件+服务", "其他软件+服务")


def money(value: str | None) -> Decimal:
    try:
        number = Decimal(value or "")
        if not number.is_finite() or abs(number) >= Decimal("1000000000000000"):
            raise ValueError("金额超出支持范围")
        if number != number.quantize(CENT):
            raise ValueError("金额不能超过两位小数")
        return number.quantize(CENT)
    except InvalidOperation as exc:
        raise ValueError("金额缺失或格式无效") from exc


def uppercase_rmb(value: Decimal) -> str:
    """Chinese financial numerals, exact cents, including zero and negative values."""
    value = money(str(value))
    digits = "零壹贰叁肆伍陆柒捌玖"

    def group(number: int) -> str:
        result = ""
        pending = False
        for index, power in enumerate((1000, 100, 10, 1)):
            digit, number = divmod(number, power)
            if digit:
                if pending and result:
                    result += "零"
                result += digits[digit] + ("仟", "佰", "拾", "")[index]
                pending = False
            elif result:
                pending = True
        return result

    cents = int(abs(value) * 100)
    integer, fraction = divmod(cents, 100)
    groups = []
    while integer:
        integer, part = divmod(integer, 10000)
        groups.append(part)
    text = ""
    pending_zero = False
    for index in range(len(groups) - 1, -1, -1):
        part = groups[index]
        if not part:
            pending_zero = bool(text)
            continue
        if text and (pending_zero or part < 1000):
            text += "零"
        text += group(part) + ("", "万", "亿", "万亿")[index]
        pending_zero = False
    text = (text or "零") + "圆"
    jiao, fen = divmod(fraction, 10)
    if jiao:
        text += digits[jiao] + "角"
    elif fen:
        text += "零"
    if fen:
        text += digits[fen] + "分"
    elif not fraction:
        text += "整"
    return ("负" if value < 0 else "") + text


@dataclass(frozen=True)
class MaterialSummary:
    name: str
    quantity: int
    unit_prices: tuple[str, ...]
    row_totals: tuple[str, ...]
    total: str
    uppercase: str
    remarks: str


def aggregate(source: ProjectSummary, remarks: dict[str, str]) -> MaterialSummary:
    if source.issues:
        raise ValueError("；".join(source.issues))
    rows = source.projects
    if not rows or len(rows) > 10000 or len({row.id for row in rows}) != len(rows):
        raise ValueError("项目明细为空、重复或超出数量限制，请重新查询")
    if set(remarks) - {row.id for row in rows}:
        raise ValueError("备注包含不属于本次查询的项目")
    names = {(row.software_copyright_name or "").strip() for row in rows}
    if "" in names:
        raise ValueError("存在缺失软著名称的标的，无法汇总")
    if len(names) != 1:
        raise ValueError("软著名称不同，不能汇总为同一组三类标的")
    prices, totals = [], []
    for field, label in zip(CATEGORY_FIELDS, CATEGORY_LABELS, strict=True):
        try:
            values = [money(getattr(row, field)) for row in rows]
        except ValueError as exc:
            raise ValueError(f"{label}：{exc}") from exc
        if len(set(values)) != 1:
            raise ValueError(f"{label}单价不同，不能合并或取平均，请核对 OA 明细")
        total = sum(values, Decimal("0.00"))
        prices.append(format(values[0], ".2f"))
        totals.append(format(total, ".2f"))
    total = sum((Decimal(t) for t in totals), Decimal("0.00"))
    # Never substitute the category sum for the authoritative OA contract total.
    if total != money(source.amount):
        raise ValueError(
            f"三类标的合计 {total:.2f} 元，与 OA 合同金额 {source.amount} 元不一致；"
            "请核对源数据后重新查询"
        )
    unique_remarks = dict.fromkeys(remarks.get(row.id, "").strip() for row in rows)
    return MaterialSummary(
        next(iter(names)),
        len(rows),
        tuple(prices),
        tuple(totals),
        format(total, ".2f"),
        uppercase_rmb(total),
        "\n".join(value for value in unique_remarks if value),
    )
