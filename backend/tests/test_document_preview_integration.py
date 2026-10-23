"""Database/API lifecycle tests; conversion is injected, OA is never contacted."""

import io
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pikepdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from test_contract_drafts import source
from test_contract_drafts import template as template  # noqa: F401

from app.contract_drafts import catalog
from app.core.config import Settings
from app.db import SessionLocal
from app.main import app
from app.models import ContractTemplate, DocumentPreview, Task, TaskEvent
from app.preview_files import local_path
from app.preview_tasks import cleanup_preview, run_preview
from app.station_names import WIND_COVER

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="requires local PostgreSQL"),
]
client = TestClient(app)


@pytest.fixture
def contract(
    template: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[str, dict]]:
    ident = uuid.uuid4()
    monkeypatch.setattr("app.document_previews.run_preview.apply_async", lambda **kwargs: None)
    pdf = io.BytesIO()
    with pikepdf.Pdf.new() as document:
        document.add_blank_page()
        document.save(pdf)
    monkeypatch.setattr("app.preview_tasks.convert_pdf", lambda data: pdf.getvalue())
    monkeypatch.setattr(
        "app.preview_files.get_settings",
        lambda: Settings(_env_file=None, preview_directory=tmp_path),
    )
    monkeypatch.setattr("app.document_previews.get_settings", lambda: Settings(_env_file=None))
    with SessionLocal.begin() as session:
        model = ContractTemplate(
            id=ident,
            name="preview lifecycle test",
            original=template,
            source_file="test.docx",
            source_sha256=uuid.uuid4().hex * 2,
            sections=[],
            section_count=1,
            cover_config=WIND_COVER,
        )
        session.add(model)
        payload = {
            "revision": catalog(model)["revision"],
            "source": source().model_dump(mode="json"),
            "contract_name": "联调样本",
            "remarks": {},
            "fields": {},
        }
    yield str(ident), payload
    with SessionLocal.begin() as session:
        task_ids = list(
            session.scalars(
                select(DocumentPreview.task_id).where(DocumentPreview.template_id == ident)
            )
        )
        session.execute(delete(DocumentPreview).where(DocumentPreview.template_id == ident))
        session.execute(delete(Task).where(Task.id.in_(task_ids)))
        session.execute(delete(ContractTemplate).where(ContractTemplate.id == ident))


def test_deduplication_frozen_input_events_and_expiry(contract: tuple[str, dict]) -> None:
    ident, payload = contract
    url = f"/api/v1/templates/{ident}/document-previews"
    first = client.post(url, json=payload)
    assert first.status_code == 202, first.text
    preview = first.json()
    assert client.post(url, json=payload).json()["id"] == preview["id"]
    assert client.get(f"/api/v1/document-previews/{preview['id']}/file").status_code == 409
    assert client.get(f"/api/v1/document-previews/{preview['id']}/download").status_code == 409
    run_preview.run(preview["id"])
    assert client.get(f"/api/v1/document-previews/{preview['id']}").json()["status"] == "succeeded"
    pdf = client.get(f"/api/v1/document-previews/{preview['id']}/file")
    assert pdf.content.startswith(b"%PDF-")
    assert pdf.headers["content-disposition"].startswith("inline")
    download = client.get(f"/api/v1/document-previews/{preview['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")
    assert "filename*=UTF-8''" in download.headers["content-disposition"]
    with pikepdf.Pdf.open(io.BytesIO(download.content)) as document:
        assert document.is_encrypted and not document.allow.modify_other
    # Download permissions do not rewrite the cached preview file.
    assert client.get(f"/api/v1/document-previews/{preview['id']}/file").content == pdf.content
    assert client.post(url, json=payload).json()["id"] == preview["id"]
    assert "event: completed" in client.get(f"/api/v1/tasks/{preview['task_id']}/events").text
    with SessionLocal.begin() as session:
        row = session.get(DocumentPreview, uuid.UUID(preview["id"]))
        assert row is not None and row.source_docx is None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get(f"/api/v1/document-previews/{preview['id']}").status_code == 410
    assert client.get(f"/api/v1/document-previews/{preview['id']}/download").status_code == 410
    artifact_id = uuid.UUID(preview["id"])
    task_id = uuid.UUID(preview["task_id"])
    cleanup_preview(artifact_id, datetime.now(UTC))
    assert not local_path(f"document-previews/{artifact_id.hex}.pdf").exists()
    with SessionLocal() as session:
        assert session.get(DocumentPreview, artifact_id) is None
        assert session.get(Task, task_id) is None
        assert session.scalar(select(TaskEvent.id).where(TaskEvent.task_id == task_id)) is None
    assert client.post(url, json=payload).json()["id"] != preview["id"]
    changed = client.post(url, json={**payload, "contract_name": "另一名称"}).json()
    assert changed["id"] != preview["id"]


def test_conversion_failure_retry_and_stale_revision(
    contract: tuple[str, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    ident, payload = contract
    url = f"/api/v1/templates/{ident}/document-previews"
    assert client.post(url, json={**payload, "revision": "old"}).status_code == 409
    assert client.post(url, json={**payload, "source": None}).status_code == 422
    first = client.post(url, json=payload).json()

    def fail(data: bytes) -> bytes:
        raise ValueError("转换超时测试")

    monkeypatch.setattr("app.preview_tasks.convert_pdf", fail)
    run_preview.run(first["id"])
    state = client.get(f"/api/v1/document-previews/{first['id']}").json()
    assert state["status"] == "failed" and state["error"] == "转换超时测试"
    assert client.post(url, json=payload).json()["id"] != first["id"]


@pytest.mark.auth
def test_user_isolation_including_files_sse_and_cache(
    contract: tuple[str, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from cryptography.hazmat.primitives.asymmetric import rsa
    from test_auth import headers

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        "app.auth.jwks_client",
        lambda issuer: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
        ),
    )
    ident, payload = contract
    alice = headers(key, sub="alice")
    bob = headers(key, sub="bob")
    admin = headers(key, ["agent_admin"], sub="admin")
    create_url = f"/api/v1/templates/{ident}/document-previews"
    response = client.post(create_url, json=payload, headers=alice)
    assert response.status_code == 202, response.text
    first = response.json()
    own = client.post(create_url, json=payload, headers=alice).json()
    other = client.post(create_url, json=payload, headers=bob).json()
    assert first["id"] == own["id"] and first["id"] != other["id"]
    run_preview.run(first["id"])
    paths = [
        f"/api/v1/document-previews/{first['id']}",
        f"/api/v1/document-previews/{first['id']}/file",
        f"/api/v1/document-previews/{first['id']}/download",
        f"/api/v1/tasks/{first['task_id']}",
        f"/api/v1/tasks/{first['task_id']}/events",
    ]
    for path in paths:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=bob).status_code == 404
        assert client.get(path, headers=alice).status_code == 200
        assert client.get(path, headers=admin).status_code == 200
    stream = client.get(paths[-1], headers=alice).text
    last_id = max(int(line[4:]) for line in stream.splitlines() if line.startswith("id: "))
    assert (
        client.get(paths[-1], headers={**alice, "Last-Event-ID": str(last_id)}).status_code == 204
    )
    # No historical task is silently claimed by a logged-in visitor.
    with SessionLocal.begin() as session:
        task = session.get(Task, uuid.UUID(first["task_id"]))
        assert task is not None
        task.owner_sub = None
    assert client.get(paths[0], headers=alice).status_code == 404
    assert client.get(paths[0], headers=admin).status_code == 200
