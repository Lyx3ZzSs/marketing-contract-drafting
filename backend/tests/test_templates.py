import io
import os
import uuid
from zipfile import ZipFile

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal
from app.main import app
from app.models import ContractTemplate
from app.template_parser import TemplateParseError, document_text, parse_docx

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def word(body: str, comments: str = "") -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
        )
        if comments:
            archive.writestr(
                "word/comments.xml", f'<w:comments xmlns:w="{W}">{comments}</w:comments>'
            )
    return output.getvalue()


def p(text: str) -> str:
    return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def test_preserves_sections_placeholders_comments_and_table_cells() -> None:
    body = p("正文") + p("一、标的物")
    body += (
        "<w:tbl><w:tr><w:tc>"
        + p("设备")
        + "</w:tc><w:tc>"
        + p("0.00 元")
        + "</w:tc></w:tr></w:tbl>"
    )
    body += (
        p("二、交付") + '<w:p><w:commentRangeStart w:id="1"/><w:r><w:t>日期：    年</w:t></w:r>'
        "<w:del><w:r><w:delText>删除文字</w:delText></w:r></w:del></w:p>"
    )
    sections = parse_docx(word(body, '<w:comment w:id="1">' + p("原批注") + "</w:comment>"))
    assert [s["title"] for s in sections] == ["正文说明", "一、标的物", "二、交付"]
    assert (
        "".join(document_text(s["document"]) for s in sections)
        == "正文一、标的物设备0.00 元二、交付日期：    年"
    )
    assert sections[2]["notes"][0]["text"] == "原批注"
    assert sections[1]["document"]["content"][1]["type"] == "table"


@pytest.mark.parametrize(
    "data",
    [
        b"not a zip",
        word(""),
        word("<w:p><w:r><w:drawing/></w:r></w:p>"),
        word("<w:p><w:pPr><w:numPr/></w:pPr><w:r><w:t>条款</w:t></w:r></w:p>"),
    ],
)
def test_invalid_or_unsupported_files_fail_explicitly(data: bytes) -> None:
    with pytest.raises(TemplateParseError):
        parse_docx(data)


def test_rejects_entity_expansion_and_invalid_upload_before_persistence() -> None:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", '<!DOCTYPE d [<!ENTITY a "entity">]><d>&a;</d>')
    with pytest.raises(TemplateParseError):
        parse_docx(output.getvalue())
    client = TestClient(app)
    assert client.post("/api/v1/templates?name=x&filename=x.txt", content=b"x").status_code == 422
    assert client.post("/api/v1/templates?name=x&filename=x.docx", content=b"x").status_code == 422


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("TEST_ACCESS_TOKEN"), reason="需提供真实管理员 Access Token")
@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="requires running API and PostgreSQL"
)
def test_upload_list_download_duplicate_and_delete() -> None:
    ids = []
    with httpx.Client(
        base_url="http://127.0.0.1:18400",
        timeout=15,
        headers={"Authorization": f"Bearer {os.environ['TEST_ACCESS_TOKEN']}"},
    ) as client:
        try:
            name = f"集成验证-{uuid.uuid4()}"
            original = word(p("一、验收") + p(name))
            uploaded = client.post(
                "/api/v1/templates",
                params={"name": name, "filename": "验证.docx"},
                content=original,
            )
            assert uploaded.status_code == 201, uploaded.text
            record = uploaded.json()
            ids.append(uuid.UUID(record["id"]))
            assert record["storage"] == "postgresql"
            assert any(t["id"] == record["id"] for t in client.get("/api/v1/templates").json())
            detail = client.get(f"/api/v1/templates/{record['id']}").json()
            assert name in document_text(detail["sections"][0]["document"])
            download = client.get(f"/api/v1/templates/{record['id']}/file")
            assert download.content == original
            assert "filename*=UTF-8''" in download.headers["content-disposition"]
            assert (
                client.post(
                    "/api/v1/templates",
                    params={"name": name, "filename": "验证.docx"},
                    content=original,
                ).status_code
                == 409
            )
            assert client.get(f"/api/v1/templates/{uuid.uuid4()}").status_code == 404
            removed = client.delete(f"/api/v1/templates/{record['id']}")
            assert removed.status_code == 200
            assert removed.json() == {"id": record["id"]}
            assert all(t["id"] != record["id"] for t in client.get("/api/v1/templates").json())
            assert client.get(f"/api/v1/templates/{record['id']}").status_code == 404
            assert client.get(f"/api/v1/templates/{record['id']}/file").status_code == 404
            assert client.delete(f"/api/v1/templates/{record['id']}").status_code == 404
        finally:
            with SessionLocal.begin() as session:
                session.execute(delete(ContractTemplate).where(ContractTemplate.id.in_(ids)))
