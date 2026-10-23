import hashlib
import io
from datetime import UTC, datetime
from decimal import Decimal
from zipfile import ZipFile

import pytest
from lxml import etree as ET

from app.contract_document import (
    SOURCES,
    W,
    build_document,
    field_catalog,
    preview_sections,
    read_root,
    text,
)
from app.contract_values import aggregate, uppercase_rmb
from app.oa import Candidate, Project, ProjectSummary
from app.station_names import WIND_COVER


def source(count: int = 3) -> ProjectSummary:
    return ProjectSummary(
        record=Candidate(id="1", serial_number="OA-1", status="1", initiated_at=None),
        station_names=["平山湖"],
        contract_name=None,
        amount=str(85000 * count),
        currency="CNY",
        currency_name="人民币",
        project_count=count,
        issues=[],
        warnings=[],
        retrieved_at=datetime.now(UTC),
        projects=[
            Project(
                id=str(i),
                project_code=None,
                project_name=None,
                station_name="平山湖",
                amount="85000",
                currency_id="cny",
                currency="CNY",
                currency_name="人民币",
                software_copyright_name="风电功率预测系统V1.0",
                hardware_amount="63600.00",
                software_service_amount="10900.00",
                other_software_service_amount="10500.00",
            )
            for i in range(count)
        ],
    )


def test_three_categories_and_shared_remarks() -> None:
    summary = aggregate(source(), {"0": "统一备注", "1": "统一备注", "2": "补充说明"})
    assert summary.quantity == 3
    assert summary.row_totals == ("190800.00", "32700.00", "31500.00")
    assert summary.total == "255000.00"
    assert summary.uppercase == "贰拾伍万伍仟圆整"
    assert summary.remarks == "统一备注\n补充说明"


def test_single_item_and_zero_negative_amounts() -> None:
    data = source(1)
    data.amount = "217000.00"
    data.projects[0].hardware_amount = "15000"
    data.projects[0].software_service_amount = "162000"
    data.projects[0].other_software_service_amount = "40000"
    assert aggregate(data, {}).uppercase == "贰拾壹万柒仟圆整"
    data.projects[0].hardware_amount = "-1.01"
    data.projects[0].software_service_amount = "0"
    data.projects[0].other_software_service_amount = "0"
    data.amount = "-1.01"
    assert aggregate(data, {}).total == "-1.01"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0", "零圆整"),
        ("0.01", "零圆零壹分"),
        ("10.10", "壹拾圆壹角"),
        ("10001", "壹万零壹圆整"),
        ("100100001.01", "壹亿零壹拾万零壹圆零壹分"),
        ("100000001", "壹亿零壹圆整"),
        ("-10.01", "负壹拾圆零壹分"),
    ],
)
def test_uppercase(value: str, expected: str) -> None:
    assert uppercase_rmb(Decimal(value)) == expected


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("hardware_amount", None, "缺失"),
        ("hardware_amount", "0", "单价不同"),
        ("hardware_amount", "63600.001", "两位"),
        ("hardware_amount", "NaN", "支持范围"),
        ("software_copyright_name", "不同软件", "名称不同"),
    ],
)
def test_incomplete_or_unequal_rows_fail(field: str, value: str | None, message: str) -> None:
    data = source()
    setattr(data.projects[0], field, value)
    with pytest.raises(ValueError, match=message):
        aggregate(data, {})


def test_sum_mismatch_and_foreign_remarks_fail() -> None:
    data = source()
    data.amount = "1"
    with pytest.raises(ValueError, match="不一致"):
        aggregate(data, {})
    with pytest.raises(ValueError, match="不属于"):
        aggregate(source(), {"unknown": "不应出现"})


@pytest.fixture
def template(monkeypatch: pytest.MonkeyPatch) -> bytes:
    """Small synthetic profile fixture with the same binding positions; no company data."""
    root = ET.Element(W + "document", nsmap={"w": W[1:-1]})
    body = ET.SubElement(root, W + "body")

    def paragraph(index: int, parent: ET._Element) -> None:
        p = ET.SubElement(parent, W + "p")
        r = ET.SubElement(p, W + "r")
        if index in SOURCES or index == 102:
            ET.SubElement(ET.SubElement(r, W + "rPr"), W + "highlight").set(W + "val", "yellow")
        ET.SubElement(r, W + "t").text = {
            4: "xxxxxx风电站",
            6: WIND_COVER["product_line"],
            43: "正文",
            45: "一、标的物",
        }.get(index, f"固定原文{index}")

    for i in range(14):
        paragraph(i, body)
    first = ET.SubElement(ET.SubElement(ET.SubElement(body, W + "tbl"), W + "tr"), W + "tc")
    for i in range(14, 22):
        paragraph(i, first)
    for i in range(22, 47):
        paragraph(i, body)
    table = ET.SubElement(body, W + "tbl")
    for row in range(4):
        tr = ET.SubElement(table, W + "tr")
        for col in range(8):
            paragraph(47 + row * 8 + col, ET.SubElement(tr, W + "tc"))
    tr = ET.SubElement(table, W + "tr")
    for i in range(79, 82):
        paragraph(i, ET.SubElement(tr, W + "tc"))
    for i in range(82, 113):
        paragraph(i, body)
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", ET.tostring(root))
        z.writestr("word/styles.xml", b"<unchanged/>")
    data = buffer.getvalue()
    monkeypatch.setattr(
        "app.contract_document.KNOWN_TEMPLATE_SHA", hashlib.sha256(data).hexdigest()
    )
    return data


def test_ooxml_updates_only_allowlisted_paragraphs_and_shared_cell(
    template: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.contract_document.MANUAL_EDITING_ENABLED", True)
    original = read_root(template)
    material = aggregate(source(), {"0": "一条备注"})
    root, fields = build_document(
        template,
        None,
        WIND_COVER,
        "平山湖风电站\n风电场功率预测系统V1.0\n采购合同",
        material,
        {"p21-y0": "2026年10月22日"},
    )
    old, new = list(original.iter(W + "p")), list(root.iter(W + "p"))
    allowed = set(SOURCES) | {102, 58, 60, 61, 62, 66, 68, 69, 70, 74, 76, 77, 78, 81}
    for i, (a, b) in enumerate(zip(old, new, strict=True)):
        if i not in allowed:
            assert ET.tostring(a) == ET.tostring(b), i
    assert text(new[4]) == "平山湖风电站"
    assert text(new[58]) == "3" and text(new[61]) == "190800"
    assert text(new[62]) == "一条备注" and text(new[70]) == "" and text(new[78]) == ""
    sections = preview_sections(root, fields)
    table = sections[2]["document"]["content"][2]
    assert table["content"][1]["content"][7]["attrs"]["rowspan"] == 3
    assert read_root(template) is not root


def test_revoked_unknown_fields_and_invalid_percent_rejected(
    template: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.contract_document.MANUAL_EDITING_ENABLED", True)
    for config, manual in [
        ({"p21-y0": False}, {"p21-y0": "x"}),
        (None, {"p0-y0": "编号"}),
        (None, {"p105-y0": "101%"}),
    ]:
        with pytest.raises(ValueError):
            build_document(template, config, WIND_COVER, "", None, manual)
    assert (
        field_catalog(template, None, WIND_COVER)["revision"]
        != field_catalog(template, {"p21-y0": False}, WIND_COVER)["revision"]
    )


@pytest.mark.parametrize(
    "name",
    [
        "平山湖",
        "平山湖风电站",
        "平山湖风电站风电场功率预测系统V1.0采购合同",
        "平山湖风电站\n风电场功率预测系统V1.0\n采购合同",
    ],
)
def test_cover_separates_existing_single_line_title(template: bytes, name: str) -> None:
    root, _ = build_document(template, None, WIND_COVER, name, None, {})
    assert text(list(root.iter(W + "p"))[4]) == "平山湖风电站"


def test_readonly_policy_preserves_manual_text_and_rejects_edits(template: bytes) -> None:
    config = {"p21-y0": True}
    catalog = field_catalog(template, config, WIND_COVER)
    assert all(not f["editable"] and not f["configurable"] for f in catalog["fields"])
    root, fields = build_document(
        template, config, WIND_COVER, "平山湖", aggregate(source(), {}), {}
    )
    assert all(not f["editable"] for f in fields.values())
    assert text(list(root.iter(W + "p"))[21]) == text(list(read_root(template).iter(W + "p"))[21])
    assert text(list(root.iter(W + "p"))[58]) == "3"
    with pytest.raises(ValueError, match="不可编辑"):
        build_document(template, config, WIND_COVER, "平山湖", None, {"p21-y0": "2026年10月22日"})
