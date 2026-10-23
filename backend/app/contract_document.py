"""Versioned, allowlisted OOXML bindings; the uploaded ZIP is never overwritten."""

import hashlib
import io
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from zipfile import ZipFile

from lxml import etree as ET

from app.contract_values import MaterialSummary
from app.station_names import KNOWN_TEMPLATE_SHA, WIND_COVER

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
BINDING_VERSION = "wind-purchase-v1"
# Manual clause editing is paused until business rules are confirmed.
MANUAL_EDITING_ENABLED = False


@dataclass(frozen=True)
class Binding:
    id: str
    paragraph: int
    runs: tuple[int, ...]
    original: str
    context: str
    source: str
    label: str


# Positions are scoped to the exact original SHA, never reused for a different document.
SOURCES = {
    4: ("cover_station", "封面场站名称"),
    6: ("product", "封面产品名称"),
    21: ("manual", "签订日期"),
    22: ("product", "合同标题产品名称"),
    44: ("software_name", "正文产品名称"),
    56: ("software_name", "硬件名称"),
    64: ("software_name", "软件及服务名称"),
    72: ("software_name", "配套软件名称"),
    82: ("software_name", "价格说明产品名称"),
    85: ("software_name", "乙方义务产品名称"),
    105: ("manual", "预付款比例"),
    107: ("manual", "到货款比例"),
    109: ("manual", "验收款比例"),
    111: ("manual", "质保金比例"),
}


def text(element: ET._Element) -> str:
    return (
        str(element.text or "")
        if element.tag == W + "t"
        else "".join(
            text(child) for child in element if child.tag not in (W + "del", W + "moveFrom")
        )
    )


def read_root(data: bytes) -> ET._Element:
    with ZipFile(io.BytesIO(data)) as archive:
        return ET.fromstring(
            archive.read("word/document.xml"),
            parser=ET.XMLParser(resolve_entities=False, no_network=True),
        )


def discover(root: ET._Element, supported: bool) -> list[Binding]:
    bindings = []
    for index, paragraph in enumerate(root.iter(W + "p")):
        runs = list(paragraph.iter(W + "r"))
        groups: list[list[int]] = []
        for position, run in enumerate(runs):
            highlight = run.find(W + "rPr/" + W + "highlight")
            if highlight is None or highlight.get(W + "val") != "yellow":
                continue
            if groups and groups[-1][-1] == position - 1:
                groups[-1].append(position)
            else:
                groups.append([position])
        for part, positions in enumerate(groups):
            original = "".join(text(runs[p]) for p in positions)
            if not original:
                continue
            source, label = (
                SOURCES.get(index, ("fixed", "保留原文")) if supported else ("fixed", "未配置字段")
            )
            if supported and index == 102:
                source, label = (
                    ("total_clause", "合同总额") if part == 0 else ("uppercase", "合同总额大写")
                )
            bindings.append(
                Binding(
                    f"p{index}-y{part}",
                    index,
                    tuple(positions),
                    original,
                    text(paragraph),
                    source,
                    label,
                )
            )
    return bindings


def revision(data: bytes, config: dict[str, bool] | None, cover: dict[str, str] | None) -> str:
    payload = [
        hashlib.sha256(data).hexdigest(),
        BINDING_VERSION,
        config or {},
        cover,
        MANUAL_EDITING_ENABLED,
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def field_catalog(
    data: bytes, config: dict[str, bool] | None, cover: dict[str, str] | None
) -> dict[str, Any]:
    supported = hashlib.sha256(data).hexdigest() == KNOWN_TEMPLATE_SHA
    bindings = discover(read_root(data), supported)
    return {
        "revision": revision(data, config, cover),
        "supported": supported,
        "profile": BINDING_VERSION if supported else None,
        "fields": [
            {
                "id": b.id,
                "label": b.label,
                "source": b.source,
                "original": b.original,
                "context": b.context,
                "editable": MANUAL_EDITING_ENABLED
                and b.source == "manual"
                and (config or {}).get(b.id, True),
                "configurable": MANUAL_EDITING_ENABLED and b.source == "manual",
            }
            for b in bindings
        ],
    }


def replace_run_text(run: ET._Element, value: str) -> None:
    for child in list(run):
        if child.tag != W + "rPr":
            run.remove(child)
    for index, line in enumerate(value.split("\n")):
        if index:
            ET.SubElement(run, W + "br")
        node = ET.SubElement(run, W + "t")
        node.set(XML_SPACE, "preserve")
        node.text = line


def replace_paragraph(paragraph: ET._Element, value: str) -> None:
    runs = list(paragraph.iter(W + "r"))
    if not runs:
        runs = [ET.SubElement(paragraph, W + "r")]
    replace_run_text(runs[0], value)
    for run in runs[1:]:
        replace_run_text(run, "")


def validate_manual(binding: Binding, value: str) -> None:
    if len(value) > 200 or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("可编辑字段最多 200 字，不能含控制字符")
    if binding.paragraph in (105, 107, 109, 111) and value.strip():
        if not re.fullmatch(r"(?:100(?:\.0{1,2})?|\d{1,2}(?:\.\d{1,2})?)%", value.strip()):
            raise ValueError(f"{binding.label}应为 0% 至 100%（最多两位小数）")


def build_document(
    data: bytes,
    config: dict[str, bool] | None,
    cover: dict[str, str] | None,
    contract_name: str,
    material: MaterialSummary | None,
    manual: dict[str, str],
) -> tuple[ET._Element, dict[ET._Element, dict[str, Any]]]:
    supported = hashlib.sha256(data).hexdigest() == KNOWN_TEMPLATE_SHA
    root = read_root(data)
    paragraphs = list(root.iter(W + "p"))
    bindings = discover(root, supported)
    allowed = {
        b.id: b
        for b in bindings
        if MANUAL_EDITING_ENABLED and b.source == "manual" and (config or {}).get(b.id, True)
    }
    if set(manual) - allowed.keys():
        raise ValueError("请求包含不可编辑字段或模板设置已变化，请重新加载")
    for key, value in manual.items():
        validate_manual(allowed[key], value)
    fields: dict[ET._Element, dict[str, Any]] = {}
    product = (cover or WIND_COVER)["product_line"]
    station = contract_name.strip()
    document_line = (cover or WIND_COVER)["document_line"]
    # The existing basic-info field stores a single-line title; also accept a
    # pasted three-line cover without duplicating the fixed product/type lines.
    for tail in (f"\n{product}\n{document_line}", product + document_line):
        if station.endswith(tail):
            station = station[: -len(tail)].strip()
            break
    if station and not station.endswith((cover or WIND_COVER)["station_suffix"]):
        station += (cover or WIND_COVER)["station_suffix"]
    values = {"cover_station": station, "product": product}
    if material:
        values.update(
            software_name=material.name,
            total_clause=f"{material.total}元，",
            uppercase=material.uppercase,
        )
    for binding in bindings:
        runs = list(paragraphs[binding.paragraph].iter(W + "r"))
        value = (
            manual.get(binding.id, binding.original)
            if binding.source == "manual"
            else (values.get(binding.source) or binding.original)
        )
        for offset, position in enumerate(binding.runs):
            replace_run_text(runs[position], value if offset == 0 else "")
        fields[runs[binding.runs[0]]] = {
            "id": binding.id,
            "label": binding.label,
            "value": value,
            "editable": binding.id in allowed,
        }
    if supported and material:
        table = list(root.iter(W + "tbl"))[1]
        rows = table.findall(W + "tr")
        for index, row in enumerate(rows[1:4]):
            cells = row.findall(W + "tc")
            for column, value in (
                (3, str(material.quantity)),
                (5, material.unit_prices[index].removesuffix(".00")),
                (6, material.row_totals[index].removesuffix(".00")),
                (7, material.remarks if index == 0 else ""),
            ):
                replace_paragraph(cells[column].findall(W + "p")[0], value)
            properties = cells[7].find(W + "tcPr")
            if properties is None:
                properties = ET.Element(W + "tcPr")
                cells[7].insert(0, properties)
            merge = ET.SubElement(properties, W + "vMerge")
            merge.set(W + "val", "restart" if index == 0 else "continue")
        replace_paragraph(
            paragraphs[81], f"人民币：{material.total}元（大写：{material.uppercase}）"
        )
    return root, fields


def preview_sections(
    root: ET._Element, fields: dict[ET._Element, dict[str, Any]], original: bytes | None = None
) -> list[dict[str, Any]]:
    """Safe structured view, no client-supplied HTML and no editable document container."""
    comments: dict[str, str] = {}
    if original:
        with ZipFile(io.BytesIO(original)) as archive:
            if "word/comments.xml" in archive.namelist():
                comment_root = ET.fromstring(
                    archive.read("word/comments.xml"),
                    parser=ET.XMLParser(resolve_entities=False, no_network=True),
                )
                comments = {str(c.get(W + "id")): text(c) for c in comment_root}

    def paragraph(element: ET._Element) -> dict[str, Any]:
        content = []
        for run in element.iter(W + "r"):
            if run in fields:
                content.append({"type": "contractField", "attrs": fields[run]})
                continue
            marks = []
            for word, name in (("b", "bold"), ("i", "italic"), ("u", "underline")):
                prop = run.find(W + "rPr/" + W + word)
                if prop is not None and prop.get(W + "val") not in ("0", "false", "none"):
                    marks.append(name)
            for child in run:
                if child.tag == W + "t" and child.text:
                    content.append({"type": "text", "text": child.text, "marks": marks})
                elif child.tag in (W + "br", W + "cr"):
                    content.append({"type": "hardBreak"})
        return {"type": "paragraph", "content": content}

    def table(element: ET._Element) -> dict[str, Any]:
        rows = []
        merged: dict[int, dict[str, Any]] = {}
        for row in element.findall(W + "tr"):
            cells = []
            column = 0
            for cell in row.findall(W + "tc"):
                span = cell.find(W + "tcPr/" + W + "gridSpan")
                colspan = int(span.get(W + "val", "1")) if span is not None else 1
                merge = cell.find(W + "tcPr/" + W + "vMerge")
                if merge is not None and merge.get(W + "val", "continue") != "restart":
                    if column in merged:
                        merged[column]["attrs"]["rowspan"] += 1
                else:
                    node = {
                        "type": "tableCell",
                        "attrs": {"colspan": colspan, "rowspan": 1},
                        "content": [paragraph(p) for p in cell.findall(W + "p")],
                    }
                    cells.append(node)
                    if merge is not None:
                        merged[column] = node
                    else:
                        merged.pop(column, None)
                column += colspan
            rows.append({"type": "tableRow", "content": cells})
        return {"type": "table", "content": rows}

    body = root.find(W + "body")
    assert body is not None
    sections: list[dict[str, Any]] = []
    for block in body:
        if block.tag not in (W + "p", W + "tbl"):
            continue
        label = text(block).strip()
        heading = block.tag == W + "p" and (
            label == "正文"
            or re.match(r"^(?:[一二三四五六七八九十百]+、|第[一二三四五六七八九十百\d]+条)", label)
        )
        signature = block.tag == W + "tbl" and all(t in label for t in ("甲方", "乙方", "盖章"))
        if not sections or heading or signature:
            title = (
                "封面"
                if not sections
                else "签署页"
                if signature
                else ("正文说明" if label == "正文" else label)
            )
            sections.append(
                {
                    "id": f"bound-{len(sections)}",
                    "title": title,
                    "document": {"type": "doc", "content": []},
                    "notes": [],
                }
            )
        node = paragraph(block) if block.tag == W + "p" else table(block)
        if heading:
            node["type"] = "heading"
        sections[-1]["document"]["content"].append(node)
        for marker in block.iter(W + "commentRangeStart"):
            key = str(marker.get(W + "id"))
            if key in comments:
                sections[-1]["notes"].append({"id": key, "text": comments[key], "anchor": label})
    return sections


def package_preview_document(original: bytes, root: ET._Element) -> bytes:
    """Remove yellow highlighting only from the PDF input, after field binding.

    The original bytes and bound tree remain unchanged. Explicit 'none' also
    overrides inherited highlighting; other colors and formatting are preserved.
    """
    output = io.BytesIO()
    with ZipFile(io.BytesIO(original)) as source, ZipFile(output, "w") as target:
        target.comment = source.comment
        for entry in source.infolist():
            data = source.read(entry.filename)
            document_part = entry.filename == "word/document.xml"
            if document_part or (
                entry.filename.startswith("word/") and entry.filename.endswith(".xml")
            ):
                tree = (
                    deepcopy(root)
                    if document_part
                    else ET.fromstring(
                        data, parser=ET.XMLParser(resolve_entities=False, no_network=True)
                    )
                )
                changed = False
                for highlight in tree.iter(W + "highlight"):
                    if highlight.get(W + "val") == "yellow":
                        highlight.set(W + "val", "none")
                        changed = True
                if document_part or changed:
                    data = ET.tostring(
                        tree, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
            target.writestr(entry, data)
    return output.getvalue()
