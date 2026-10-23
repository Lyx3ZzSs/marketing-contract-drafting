"""Bounded DOCX body extraction. Never executes Word content or follows external links."""

import io
import re
from typing import Any
from xml.etree.ElementTree import Element
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_UPLOAD = 10 * 1024 * 1024
MAX_EXPANDED = 40 * 1024 * 1024


class TemplateParseError(ValueError):
    pass


def visible_text(element: Element) -> str:
    if element.tag in {
        W + t for t in ("pPr", "rPr", "tcPr", "trPr", "tblPr", "tblGrid", "del", "moveFrom")
    }:
        return ""
    if element.tag == W + "t":
        return element.text or ""
    if element.tag == W + "tab":
        return "\t"
    if element.tag in (W + "br", W + "cr"):
        return "\n" if element.get(W + "type", "textWrapping") == "textWrapping" else ""
    return "".join(visible_text(child) for child in element)


def paragraph(element: Element) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    deleted = {
        id(r) for d in element.iter() if d.tag in (W + "del", W + "moveFrom") for r in d.iter()
    }
    for run in element.iter(W + "r"):
        if id(run) in deleted:
            continue
        marks = []
        for word_name, tiptap_name in [("b", "bold"), ("i", "italic"), ("u", "underline")]:
            prop = run.find(W + "rPr/" + W + word_name)
            if prop is not None and prop.get(W + "val", "true") not in ("0", "false", "none"):
                marks.append({"type": tiptap_name})
        for index, line in enumerate(visible_text(run).split("\n")):
            if index:
                content.append({"type": "hardBreak"})
            if line:
                node: dict[str, Any] = {"type": "text", "text": line}
                if marks:
                    node["marks"] = marks
                content.append(node)
    return {"type": "paragraph", "content": content}


def table(element: Element) -> dict[str, Any]:
    rows = []
    expected_width = None
    for row in element.findall(W + "tr"):
        cells: list[dict[str, Any]] = []
        for cell in row.findall(W + "tc"):
            if cell.find(W + "tcPr/" + W + "vMerge") is not None:
                raise TemplateParseError("暂不支持纵向合并的表格，请拆分单元格后上传。")
            if cell.find(W + "tbl") is not None:
                raise TemplateParseError("暂不支持嵌套表格，请调整模板后上传。")
            span = cell.find(W + "tcPr/" + W + "gridSpan")
            colspan = int(span.get(W + "val", "1")) if span is not None else 1
            if not 1 <= colspan <= 50:
                raise TemplateParseError("表格列数超出支持范围。")
            cells.append(
                {
                    "type": "tableHeader"
                    if row.find(W + "trPr/" + W + "tblHeader") is not None
                    else "tableCell",
                    "attrs": {"colspan": colspan, "rowspan": 1},
                    "content": [paragraph(p) for p in cell.findall(W + "p")]
                    or [{"type": "paragraph"}],
                }
            )
        width = sum(c["attrs"]["colspan"] for c in cells)
        if not cells or (expected_width is not None and width != expected_width):
            raise TemplateParseError("表格行列结构不规则，请整理表格后上传。")
        expected_width = width
        rows.append({"type": "tableRow", "content": cells})
    if not rows:
        raise TemplateParseError("模板中包含空表格。")
    return {"type": "table", "content": rows}


def document_text(node: dict[str, Any]) -> str:
    if node["type"] == "text":
        return str(node["text"])
    if node["type"] == "hardBreak":
        return "\n"
    return "".join(document_text(child) for child in node.get("content", []))


def parse_docx(data: bytes) -> list[dict[str, Any]]:
    if not data or len(data) > MAX_UPLOAD:
        raise TemplateParseError("请上传非空且不超过 10 MB 的 DOCX 文件。")
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(e.file_size for e in entries) > MAX_EXPANDED:
                raise TemplateParseError("解压后的模板过大，请精简后上传。")
            if any(e.flag_bits & 1 for e in entries):
                raise TemplateParseError("不支持加密的 Word 文件。")
            if len({e.filename for e in entries}) != len(entries):
                raise TemplateParseError("文件包包含重复条目。")
            if any("vbaProject" in e.filename for e in entries):
                raise TemplateParseError("请上传不含宏的 DOCX 文件。")
            root = fromstring(archive.read("word/document.xml"))
            comments = {}
            if "word/comments.xml" in archive.namelist():
                comments = {
                    c.get(W + "id"): visible_text(c)
                    for c in fromstring(archive.read("word/comments.xml"))
                }
            styles = {}
            if "word/styles.xml" in archive.namelist():
                for style in fromstring(archive.read("word/styles.xml")):
                    label = style.find(W + "name")
                    if label is not None:
                        styles[style.get(W + "styleId")] = label.get(W + "val", "").lower()
    except TemplateParseError:
        raise
    except Exception as exc:
        raise TemplateParseError("无法读取 DOCX，请检查文件是否损坏或格式不正确。") from exc
    body = root.find(W + "body")
    if body is None:
        raise TemplateParseError("Word 文件没有正文。")
    blocks = list(body)
    start = next((i for i, b in enumerate(blocks) if visible_text(b).strip() == "正文"), 0)
    blocks = [b for b in blocks[start:] if b.tag != W + "sectPr"]
    if len(blocks) > 5000:
        raise TemplateParseError("模板段落过多，请拆分后上传。")
    for block in blocks:
        if any(
            e.tag
            in {
                W + t
                for t in (
                    "drawing",
                    "pict",
                    "object",
                    "altChunk",
                    "numPr",
                    "footnoteReference",
                    "endnoteReference",
                )
            }
            for e in block.iter()
        ):
            raise TemplateParseError(
                "正文含暂不支持的图片、对象、自动编号或脚注，请转换为文本后上传。原文件未保存。"
            )
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for block in blocks:
        text = visible_text(block)
        style = block.find(W + "pPr/" + W + "pStyle")
        style_name = styles.get(style.get(W + "val"), "") if style is not None else ""
        heading = (
            bool(text.strip())
            and block.tag == W + "p"
            and (
                text.strip() == "正文"
                or re.match(
                    r"^(?:[一二三四五六七八九十百]+、|第[一二三四五六七八九十百\d]+条)",
                    text.strip(),
                )
                or style_name in ("heading 1", "heading 2", "标题 1", "标题 2")
            )
        )
        signature = block.tag == W + "tbl" and "甲方" in text and "乙方" in text and "盖章" in text
        if heading or signature or current is None:
            title = (
                "签署页"
                if signature
                else ("正文说明" if text.strip() == "正文" or not heading else text.strip())
            )
            current = {
                "id": f"section-{len(sections) + 1}",
                "title": title[:200],
                "document": {"type": "doc", "content": []},
                "notes": [],
            }
            sections.append(current)
        if block.tag == W + "p":
            node = paragraph(block)
            if heading:
                node.update(type="heading", attrs={"level": 2})
        elif block.tag == W + "tbl":
            node = table(block)
        else:
            raise TemplateParseError("正文含暂不支持的内容结构，请转换为普通段落或表格后上传。")
        current["document"]["content"].append(node)
        for marker in block.iter(W + "commentRangeStart"):
            key = marker.get(W + "id")
            if key in comments:
                current["notes"].append({"id": key, "text": comments[key], "anchor": text})
    source_text = "".join(visible_text(b) for b in blocks)
    if not source_text.strip():
        raise TemplateParseError("模板正文为空。")
    if "".join(document_text(s["document"]) for s in sections) != source_text:
        raise TemplateParseError("正文完整性校验未通过，模板未保存。")
    return sections
