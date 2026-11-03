"""Local preview smoke: real Celery/Docs/storage, in-process API test identity, no OA calls."""

import argparse
import hashlib
import io
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pikepdf
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import Principal, current_principal, require_access
from app.contract_drafts import catalog
from app.db import SessionLocal
from app.main import app
from app.models import ContractTemplate, DocumentPreview, Task
from app.preview_files import delete_pdf
from app.station_names import WIND_COVER


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path, help="The supported procurement DOCX template")
    parser.add_argument("output", type=Path, help="Directory for test PDFs and evidence")
    args = parser.parse_args()
    original = args.template.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    ident, created = uuid.uuid4(), False
    owner = f"onlyoffice-smoke-{uuid.uuid4().hex}"
    started = time.monotonic()
    overrides = dict(app.dependency_overrides)
    try:
        with SessionLocal.begin() as session:
            model = session.scalar(
                select(ContractTemplate).where(ContractTemplate.source_sha256 == digest)
            )
            if model is None:
                model = ContractTemplate(
                    id=ident,
                    name="ONLYOFFICE 转换链路验收样本",
                    original=original,
                    source_file="smoke.docx",
                    source_sha256=digest,
                    sections=[],
                    section_count=1,
                    cover_config=WIND_COVER,
                )
                session.add(model)
                created = True
            ident = model.id
            revision = catalog(model)["revision"]
        # This identity exists only in this CLI's TestClient process, never in the live API.
        app.dependency_overrides[require_access] = lambda: None
        app.dependency_overrides[current_principal] = lambda: Principal(
            sub=owner, roles=frozenset({"agent_admin"}), expires_at=4102444800
        )
        source = {
            "record": {
                "id": "smoke",
                "serial_number": "SMOKE",
                "status": "1",
                "initiated_at": None,
            },
            "station_names": ["转换链路验收样本"],
            "contract_name": None,
            "amount": "85000.00",
            "currency": "CNY",
            "currency_name": "人民币",
            "project_count": 1,
            "issues": [],
            "warnings": [],
            "retrieved_at": datetime.now(UTC).isoformat(),
            "projects": [
                {
                    "id": "1",
                    "project_code": None,
                    "project_name": None,
                    "station_name": "转换链路验收样本",
                    "amount": "85000.00",
                    "currency_id": "cny",
                    "currency": "CNY",
                    "currency_name": "人民币",
                    "software_copyright_name": "风电功率预测系统V1.0",
                    "hardware_amount": "63600.00",
                    "software_service_amount": "10900.00",
                    "other_software_service_amount": "10500.00",
                }
            ],
        }
        payload = {"revision": revision, "source": source, "contract_name": "转换链路验收样本"}
        with TestClient(app) as client:
            url = f"/api/v1/templates/{ident}/document-previews"
            response = client.post(url, json=payload)
            assert response.status_code == 202, response.text
            preview = response.json()
            assert client.post(url, json=payload).json()["id"] == preview["id"]
            state_url = f"/api/v1/document-previews/{preview['id']}"
            while time.monotonic() - started < 150:
                state = client.get(state_url).json()
                if state["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.5)
            assert state["status"] == "succeeded", state
            elapsed = round(time.monotonic() - started, 3)
            inline = client.get(state_url + "/file")
            download = client.get(state_url + "/download")
            assert inline.status_code == download.status_code == 200
            assert inline.content.startswith(b"%PDF-")
            assert inline.headers["content-disposition"].startswith("inline")
            assert download.headers["content-disposition"].startswith("attachment;")
            with pikepdf.Pdf.open(io.BytesIO(inline.content)) as pdf:
                pages = len(pdf.pages)
                assert pages > 0
            with pikepdf.Pdf.open(io.BytesIO(download.content)) as pdf:
                assert len(pdf.pages) == pages
                assert pdf.is_encrypted and not pdf.allow.modify_other
            assert client.get(state_url + "/file").content == inline.content
            assert (
                "event: completed" in client.get(f"/api/v1/tasks/{preview['task_id']}/events").text
            )
            with SessionLocal() as session:
                row = session.get(DocumentPreview, uuid.UUID(preview["id"]))
                assert row is not None and row.source_docx is None
                model = session.get(ContractTemplate, ident)
                assert model is not None and model.original == original
            result = {
                "status": "passed",
                "pages": pages,
                "seconds": elapsed,
                "source_sha256": digest,
                "bytes": len(inline.content),
                "real_celery_worker": True,
                "real_onlyoffice": True,
                "api_auth": "in-process test identity; live API authentication unchanged",
                "checks": [
                    "field binding",
                    "queue",
                    "conversion",
                    "deduplication",
                    "storage",
                    "inline PDF",
                    "download permissions",
                    "SSE completed",
                    "source snapshot cleanup",
                    "original template unchanged",
                ],
            }
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "preview-smoke.pdf").write_bytes(inline.content)
            (args.output / "preview-smoke-download.pdf").write_bytes(download.content)
            (args.output / "preview-smoke.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            print(json.dumps(result, ensure_ascii=False))
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
        with SessionLocal.begin() as session:
            tasks = list(session.scalars(select(Task.id).where(Task.owner_sub == owner)))
            rows = list(
                session.scalars(select(DocumentPreview).where(DocumentPreview.task_id.in_(tasks)))
            )
            for row in rows:
                delete_pdf(row.storage_backend, f"document-previews/{row.id.hex}.pdf")
                session.delete(row)
            session.flush()
            session.execute(delete(Task).where(Task.id.in_(tasks)))
            if created:
                session.execute(delete(ContractTemplate).where(ContractTemplate.id == ident))


if __name__ == "__main__":
    main()
