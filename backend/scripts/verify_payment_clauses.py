"""Verify real OA data, template slots, API preview and local ONLYOFFICE conversion."""

import argparse
import hashlib
import json
import logging
import re
import subprocess
import time
import uuid
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from lxml import etree as ET
from sqlalchemy import delete, select

from app.auth import Principal, current_principal, require_access
from app.contract_document import PAYMENT_PARAGRAPHS, W, text
from app.contract_drafts import DraftInput, catalog, prepare_document
from app.db import SessionLocal
from app.main import app
from app.models import ContractTemplate, DocumentPreview, Task
from app.oa import lookup, project_summary
from app.preview_files import delete_pdf
from app.station_names import KNOWN_TEMPLATE_SHA


def visible(node: dict) -> str:
    return node.get("text", node.get("attrs", {}).get("value", "")) + "".join(
        visible(child) for child in node.get("content", [])
    )


def normalized(value: str) -> str:
    value = re.sub(r"共\s*\d+\s*页\s*第\s*\d+\s*页", "", value)
    return re.sub(r"\s+", "", value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oa-number", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    found = lookup(args.oa_number)
    assert len(found.candidates) == 1, "Expected one OA record for this verification"
    source = project_summary(found.candidates[0].id)
    assert not source.issues and source.projects
    with SessionLocal() as session:
        template = session.scalar(
            select(ContractTemplate).where(ContractTemplate.source_sha256 == KNOWN_TEMPLATE_SHA)
        )
        assert template is not None
        original = template.original
        session.expunge(template)
    payload = {
        "revision": catalog(template)["revision"],
        "source": source.model_dump(mode="json"),
        "contract_name": "、".join(source.station_names),
    }
    baseline = prepare_document(template, DraftInput.model_validate(payload))
    assert not baseline.errors
    cases = {
        "original-payments": [],
        "payments-advance-only": [{"id": "advance", "percentage": 100}],
        "payments-30-30-30-10": [
            {"id": stage, "percentage": percent}
            for stage, percent in zip(
                ("advance", "delivery", "acceptance", "warranty"), (30, 30, 30, 10), strict=True
            )
        ],
        "payments-90-10": [
            {"id": "acceptance", "percentage": 90},
            {"id": "warranty", "percentage": 10},
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "project_count": len(source.projects),
        "contract_total": source.amount,
        "cases": [],
    }
    owner = "payment-verification-" + uuid.uuid4().hex
    overrides = dict(app.dependency_overrides)
    app.dependency_overrides[require_access] = lambda: None
    app.dependency_overrides[current_principal] = lambda: Principal(
        sub=owner, roles=frozenset({"agent_admin"}), expires_at=4102444800
    )
    try:
        with TestClient(app) as client:
            logging.getLogger("app.main").setLevel(logging.WARNING)
            logging.getLogger("httpx2").setLevel(logging.WARNING)
            for name, ratios in cases.items():
                case = {**payload, "payment_terms": {source.projects[0].id: ratios}}
                compiled = prepare_document(template, DraftInput.model_validate(case))
                assert not compiled.errors
                old = list(baseline.root.iter(W + "p"))
                new = list(compiled.root.iter(W + "p"))
                active = {row["id"] for row in ratios}
                removed = {
                    index + offset
                    for index, stage in zip(
                        PAYMENT_PARAGRAPHS,
                        ("advance", "delivery", "acceptance", "warranty"),
                        strict=True,
                    )
                    if ratios and stage not in active
                    for offset in (0, 1)
                }
                retained = [(i, paragraph) for i, paragraph in enumerate(old) if i not in removed]
                current = dict(
                    (i, paragraph) for (i, _), paragraph in zip(retained, new, strict=True)
                )
                for (index, a), b in zip(retained, new, strict=True):
                    if index not in PAYMENT_PARAGRAPHS:
                        assert ET.tostring(a) == ET.tostring(b), index
                    else:
                        a, b = deepcopy(a), deepcopy(b)
                        for paragraph in (a, b):
                            for node in paragraph.iter(W + "t"):
                                node.text = None
                                node.attrib.clear()
                        assert ET.tostring(a) == ET.tostring(b), index
                paragraphs = [text(current[i]) for i in PAYMENT_PARAGRAPHS if i not in removed]
                terms = client.post(f"/api/v1/templates/{template.id}/preview", json=case)
                assert terms.status_code == 200 and not terms.json()["errors"], terms.text
                displayed = "".join(visible(s["document"]) for s in terms.json()["sections"])
                assert all(value in displayed for value in paragraphs)
                omitted_prefixes = [
                    text(old[i]).split("：")[0] for i in PAYMENT_PARAGRAPHS if i in removed
                ]
                assert all(value not in displayed for value in omitted_prefixes)
                start = time.monotonic()
                url = f"/api/v1/templates/{template.id}/document-previews"
                response = client.post(url, json=case)
                assert response.status_code == 202, response.text
                preview = response.json()
                state_url = f"/api/v1/document-previews/{preview['id']}"
                deadline = start + 120
                while time.monotonic() < deadline:
                    state = client.get(state_url).json()
                    if state["status"] in ("succeeded", "failed"):
                        break
                    time.sleep(0.5)
                assert state["status"] == "succeeded", state
                pdf = client.get(state_url + "/file")
                assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
                pdf_path = args.output / f"{name}.pdf"
                pdf_path.write_bytes(pdf.content)
                extracted = subprocess.check_output(
                    ["pdftotext", "-layout", str(pdf_path), "-"], text=True
                )
                assert all(normalized(value) in normalized(extracted) for value in paragraphs)
                assert all(
                    normalized(value) not in normalized(extracted) for value in omitted_prefixes
                )
                # Retained payment conditions must remain exactly the original wording.
                assert all(
                    normalized(text(current[i])) in normalized(extracted)
                    for i in (104, 106, 108, 110, 112)
                    if i not in removed
                )
                pages = extracted.split("\f")
                payment_pages = [
                    i
                    for i, content in enumerate(pages, 1)
                    if any(f"5.{n}" in content for n in range(1, 5))
                ]
                row = {
                    "name": name,
                    "seconds": round(time.monotonic() - start, 3),
                    "pages": len(pages) - 1,
                    "payment_pages": payment_pages,
                    "payment_paragraphs": paragraphs,
                    "pdf_sha256": hashlib.sha256(pdf.content).hexdigest(),
                    "only_payment_slots_and_omitted_nodes_changed": True,
                    "omitted_paragraph_indices": sorted(removed),
                    "run_and_paragraph_formatting_preserved": True,
                    "page_api_matches_pdf": True,
                }
                evidence["cases"].append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        with SessionLocal() as session:
            unchanged = session.get(ContractTemplate, template.id)
            assert unchanged is not None and unchanged.original == original
        (args.output / "verification.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
        with SessionLocal.begin() as session:
            tasks = list(session.scalars(select(Task.id).where(Task.owner_sub == owner)))
            for preview in session.scalars(
                select(DocumentPreview).where(DocumentPreview.task_id.in_(tasks))
            ):
                delete_pdf(preview.storage_backend, f"document-previews/{preview.id.hex}.pdf")
                session.delete(preview)
            session.flush()
            session.execute(delete(Task).where(Task.id.in_(tasks)))


if __name__ == "__main__":
    main()
