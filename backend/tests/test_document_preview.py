import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from lxml import etree as ET
from test_contract_drafts import source
from test_contract_drafts import template as template  # noqa: F401

from app.contract_document import W, package_preview_document, text
from app.contract_drafts import DraftInput, catalog, prepare_document, render_preview
from app.core.config import Settings
from app.models import ContractTemplate
from app.pdf_converter import convert_pdf
from app.preview_files import delete_pdf, read_pdf, write_pdf
from app.station_names import WIND_COVER


def test_shared_compilation_and_original_package_untouched(template: bytes) -> None:
    model = ContractTemplate(original=template, field_bindings=None, cover_config=WIND_COVER)
    payload = DraftInput(
        revision=catalog(model)["revision"],
        source=source(),
        contract_name="平山湖",
        remarks={"0": "共同备注"},
    )
    compiled = prepare_document(model, payload)
    original_catalog = catalog(model)
    assert not compiled.errors
    assert compiled.material is not None
    assert render_preview(model, payload)["material"]["total"] == compiled.material.total
    data = package_preview_document(template, compiled.root)
    with ZipFile(io.BytesIO(template)) as original, ZipFile(io.BytesIO(data)) as output:
        assert output.namelist() == original.namelist()
        for name in original.namelist():
            if name != "word/document.xml":
                assert output.read(name) == original.read(name)
        assert b"255000.00" in output.read("word/document.xml")
        preview_root = ET.fromstring(output.read("word/document.xml"))
        assert all(node.get(W + "val") != "yellow" for node in preview_root.iter(W + "highlight"))
    assert any(node.get(W + "val") == "yellow" for node in compiled.root.iter(W + "highlight"))
    assert catalog(model) == original_catalog
    assert text(list(compiled.root.iter(W + "p"))[4]) == "平山湖风电站"
    assert model.original == template


def test_preview_clears_yellow_in_styles_and_headers_without_changing_other_formatting() -> None:
    xml = (
        f'<w:document xmlns:w="{W[1:-1]}"><w:r><w:rPr>'
        '<w:highlight w:val="yellow"/><w:b/></w:rPr><w:t>原文</w:t></w:r>'
        '<w:r><w:rPr><w:highlight w:val="cyan"/></w:rPr><w:t>其他</w:t></w:r>'
        "</w:document>"
    ).encode()
    original = io.BytesIO()
    with ZipFile(original, "w") as archive:
        for name in ("word/document.xml", "word/styles.xml", "word/header1.xml"):
            archive.writestr(name, xml)
        archive.writestr("word/media/image.png", b"image unchanged")
    source_bytes = original.getvalue()
    result = package_preview_document(source_bytes, ET.fromstring(xml))
    with ZipFile(io.BytesIO(result)) as output:
        for name in ("word/document.xml", "word/styles.xml", "word/header1.xml"):
            tree = ET.fromstring(output.read(name))
            assert [node.get(W + "val") for node in tree.iter(W + "highlight")] == ["none", "cyan"]
            assert len(list(tree.iter(W + "b"))) == 1
            assert text(tree) == "原文其他"
        assert output.read("word/media/image.png") == b"image unchanged"
    with ZipFile(io.BytesIO(source_bytes)) as source_zip:
        assert source_zip.read("word/document.xml") == xml


def test_generation_preserves_validation_and_readonly_contract(template: bytes) -> None:
    model = ContractTemplate(original=template, field_bindings=None, cover_config=WIND_COVER)
    revision = catalog(model)["revision"]
    result = prepare_document(model, DraftInput(revision=revision))
    assert "请先按合同编号查询 OA 项目信息" in result.errors
    assert "请填写封面合同名称" in result.errors
    with pytest.raises(HTTPException) as stale:
        prepare_document(model, DraftInput(revision="stale"))
    assert stale.value.status_code == 409
    with pytest.raises(HTTPException) as readonly:
        prepare_document(model, DraftInput(revision=revision, fields={"p21-y0": "不允许"}))
    assert readonly.value.status_code == 422


def test_local_pdf_lifecycle_and_path_restrictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.preview_files.get_settings",
        lambda: Settings(_env_file=None, preview_directory=tmp_path),
    )
    key = "document-previews/" + "a" * 32 + ".pdf"
    data = b"%PDF-1.7\npreview"
    write_pdf("local", key, data)
    assert read_pdf("local", key) == data
    assert not list(tmp_path.rglob("*.tmp"))
    delete_pdf("local", key)
    delete_pdf("local", key)
    with pytest.raises(FileNotFoundError):
        read_pdf("local", key)
    with pytest.raises(ValueError):
        write_pdf("local", "../../other.pdf", data)
    with pytest.raises(ValueError):
        write_pdf("local", key, b"not-pdf")


def test_converter_missing_binary_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.pdf_converter.get_settings",
        lambda: Settings(_env_file=None, libreoffice_binary="/no-such-soffice"),
    )
    with pytest.raises(ValueError, match="未安装 LibreOffice"):
        convert_pdf(b"input")
