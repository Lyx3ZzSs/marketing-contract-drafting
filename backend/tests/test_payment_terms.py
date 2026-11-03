from copy import deepcopy
from decimal import Decimal

import pytest
from lxml import etree as ET
from pydantic import ValidationError
from test_contract_drafts import source
from test_contract_drafts import template as template  # noqa: F401

from app.contract_document import PAYMENT_PARAGRAPHS, W, build_document, preview_sections, text
from app.contract_drafts import DraftInput, catalog, prepare_document
from app.contract_values import aggregate
from app.models import ContractTemplate
from app.payment_terms import PaymentRatio, resolve_payments
from app.station_names import WIND_COVER


def ratios(values: tuple[str, ...] = ("30", "30", "30", "10")) -> list[PaymentRatio]:
    return [
        PaymentRatio.model_validate({"id": stage, "percentage": value})
        for stage, value in zip(
            ("advance", "delivery", "acceptance", "warranty"), values, strict=False
        )
        if Decimal(value)
    ]


def test_optional_consistent_ratios_and_exact_amounts() -> None:
    assert resolve_payments(source(), {}, "255000") is None
    assert resolve_payments(source(), {"0": []}, "255000") is None
    result = resolve_payments(
        source(), {"0": ratios(), "1": list(reversed(ratios())), "2": []}, "255000"
    )
    assert result is not None
    assert [row.amount for row in result] == ["76500.00"] * 3 + ["25500.00"]
    assert result[0].uppercase == "柒万陆仟伍佰圆整"
    single = resolve_payments(source(), {"2": ratios(("0", "0", "100", "0"))}, "255000")
    assert single is not None
    assert single[0].percentage == "0" and single[0].uppercase == "零圆整"
    assert single[2].amount == "255000.00"


@pytest.mark.parametrize("total", ["100.01", "0.01", "0.02", "0.00", "-0.02", "-100.01"])
def test_rounding_reconciles_to_total_without_negative_positive_instalments(total: str) -> None:
    result = resolve_payments(source(), {"0": ratios(("25", "25", "25", "25"))}, total)
    assert result is not None
    amounts = [Decimal(row.amount) for row in result]
    assert sum(amounts) == Decimal(total)
    assert all(amount >= 0 if Decimal(total) >= 0 else amount <= 0 for amount in amounts)
    if total == "100.01":
        assert amounts == [Decimal("25.00")] * 3 + [Decimal("25.01")]


@pytest.mark.parametrize("value", ["0", "-1", "100.01", "33.333", "NaN", "Infinity"])
def test_invalid_ratios_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        PaymentRatio.model_validate({"id": "advance", "percentage": value})


@pytest.mark.parametrize("case", ["total", "duplicate", "conflict", "foreign"])
def test_invalid_schedule_is_not_silently_used(case: str) -> None:
    payments = {"0": ratios()}
    if case == "total":
        payments["0"] = ratios(("20", "30", "30", "10"))
    elif case == "duplicate":
        payments["0"] = ratios(("50",)) * 2
    elif case == "conflict":
        payments["2"] = ratios(("100",))
    else:
        payments["foreign"] = ratios()
    with pytest.raises(ValueError):
        resolve_payments(source(), payments, "255000")


def test_only_twelve_slots_change_and_original_formatting_is_preserved(template: bytes) -> None:
    material = aggregate(source(), {})
    baseline, _ = build_document(template, None, WIND_COVER, "平山湖", material, {})
    payments = resolve_payments(source(), {"0": ratios()}, material.total)
    root, fields = build_document(template, None, WIND_COVER, "平山湖", material, {}, payments)
    before, after = list(baseline.iter(W + "p")), list(root.iter(W + "p"))
    for index, (old, new) in enumerate(zip(before, after, strict=True)):
        if index not in PAYMENT_PARAGRAPHS:
            assert ET.tostring(old) == ET.tostring(new), index
        else:
            old_structure, new_structure = deepcopy(old), deepcopy(new)
            for element in (old_structure, new_structure):
                for node in element.iter(W + "t"):
                    node.text = None
                    node.attrib.clear()
            assert ET.tostring(old_structure) == ET.tostring(new_structure)
    assert (
        text(after[105])
        == "5.1 预付款：合同总价30%，即人民币 76500.00元（大写：柒万陆仟伍佰圆整）。"
    )
    assert (
        text(after[111])
        == "5.4 质保金：合同总价的10%，即人民币 25500.00元（大写： 贰万伍仟伍佰圆整）。"
    )
    sections = preview_sections(root, fields)

    def visible(node: dict) -> str:
        return node.get("text", node.get("attrs", {}).get("value", "")) + "".join(
            visible(child) for child in node.get("content", [])
        )

    rendered = "".join(visible(section["document"]) for section in sections)
    assert text(after[105]) in rendered and text(after[111]) in rendered
    restored, _ = build_document(template, None, WIND_COVER, "平山湖", material, {}, None)
    assert ET.tostring(restored) == ET.tostring(baseline)


def test_conflicting_ratios_return_issues_without_filling_any_payment_slot(template: bytes) -> None:
    model = ContractTemplate(original=template, field_bindings=None, cover_config=WIND_COVER)
    data = DraftInput(revision=catalog(model)["revision"], source=source(), contract_name="平山湖")
    original = prepare_document(model, data)
    data.payment_terms = {"0": ratios(), "2": ratios(("100",))}
    result = prepare_document(model, data)
    assert "第 1 条" in result.errors[0] and "第 3 条" in result.errors[0]
    assert ET.tostring(result.root) == ET.tostring(original.root)


@pytest.mark.parametrize(
    "values",
    [
        ("100", "0", "0", "0"),
        ("0", "100", "0", "0"),
        ("0", "0", "100", "0"),
        ("0", "0", "0", "100"),
        ("0", "0", "90", "10"),
    ],
)
def test_only_selected_payment_nodes_and_their_conditions_remain(
    template: bytes, values: tuple[str, ...]
) -> None:
    material = aggregate(source(), {})
    baseline, _ = build_document(template, None, WIND_COVER, "平山湖", material, {})
    # A zero-valued instalment of a tiny contract is still an adopted node.
    payments = resolve_payments(source(), {"0": ratios(values)}, "0.00")
    root, fields = build_document(template, None, WIND_COVER, "平山湖", material, {}, payments)
    removed = {
        index + offset
        for index, value in zip(PAYMENT_PARAGRAPHS, values, strict=True)
        if value == "0"
        for offset in (0, 1)
    }
    before = list(baseline.iter(W + "p"))
    expected = [(i, p) for i, p in enumerate(before) if i not in removed]
    after = list(root.iter(W + "p"))
    assert len(after) == len(before) - len(removed)
    for (index, original), actual in zip(expected, after, strict=True):
        if index not in PAYMENT_PARAGRAPHS:
            assert ET.tostring(original) == ET.tostring(actual)
    rendered = text(root)
    for index, value in zip(PAYMENT_PARAGRAPHS, values, strict=True):
        prefix = text(before[index]).split("：")[0]
        assert (prefix in rendered) == (value != "0")
        assert (text(before[index + 1]) in rendered) == (value != "0")
    assert preview_sections(root, fields)
    restored, _ = build_document(template, None, WIND_COVER, "平山湖", material, {}, None)
    assert ET.tostring(restored) == ET.tostring(baseline)
