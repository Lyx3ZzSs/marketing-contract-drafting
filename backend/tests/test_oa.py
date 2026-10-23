from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import oa
from app.core.config import Settings
from app.main import app

MAIN = {
    "id": -9007199254740993,
    "serial_number": "OA-001",
    "status": "1",
    "initiated_at": date(2026, 10, 21),
}


def row(
    identifier: int,
    name: str | None,
    amount: str | None,
    currency_id: int | None = 4747488595539675173,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "station_name": name,
        "amount": Decimal(amount) if amount is not None else None,
        "project_code": None,
        "project_name": None,
        "currency_id": currency_id,
        "software_copyright_name": None,
        "hardware_amount": None,
        "software_service_amount": None,
        "other_software_service_amount": None,
    }


def test_exact_sum_preserves_all_rows_and_deduplicates_only_station_names() -> None:
    result = oa.summarize(
        MAIN,
        [
            row(1, " 场站甲 ", "99999999999999999999.99"),
            row(2, "场站甲", "99999999999999999999.99"),
            row(3, "场站乙", "-0.01"),
            row(4, "场站乙", "0.00"),
        ],
    )
    assert result.contract_name is None
    assert result.station_names == ["场站甲", "场站乙"]
    assert result.amount == "199999999999999999999.97"
    assert result.project_count == 4
    assert result.record.id == "-9007199254740993"
    assert result.projects[2].amount == "-0.01"
    assert result.warnings and not result.issues


@pytest.mark.parametrize(
    "rows,missing_name,missing_amount",
    [([], True, True), ([row(1, " ", "1")], True, False), ([row(1, "甲", None)], False, True)],
)
def test_incomplete_data_is_not_treated_as_zero(
    rows: list[dict[str, Any]], missing_name: bool, missing_amount: bool
) -> None:
    result = oa.summarize(MAIN, rows)
    assert result.issues or result.warnings
    assert result.contract_name is None
    assert (result.amount is None) == missing_amount


@pytest.fixture
def client() -> Any:
    app.dependency_overrides[oa.require_oa] = lambda: None
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_lookup_trims_input_and_returns_all_candidates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = []

    def find(number: str) -> list[dict[str, Any]]:
        seen.append(number)
        return [MAIN, {**MAIN, "id": 9007199254740993}]

    monkeypatch.setattr(oa.repository, "find_contracts", find)
    response = client.get("/api/v1/oa/contracts/lookup", params={"contract_number": " OA-001 "})
    assert response.status_code == 200
    assert seen == ["OA-001"]
    assert [item["id"] for item in response.json()["candidates"]] == [
        "-9007199254740993",
        "9007199254740993",
    ]
    assert (
        client.get("/api/v1/oa/contracts/lookup", params={"contract_number": " "}).status_code
        == 422
    )


def test_lookup_empty_and_over_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oa.repository, "find_contracts", lambda _: [])
    assert (
        client.get("/api/v1/oa/contracts/lookup?contract_number=missing").json()["candidates"] == []
    )
    monkeypatch.setattr(oa.repository, "find_contracts", lambda _: [MAIN] * 101)
    assert client.get("/api/v1/oa/contracts/lookup?contract_number=duplicate").status_code == 409


def test_summary_and_invalid_identifiers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oa.repository, "read_projects", lambda _: (MAIN, [row(1, "甲", "12.34")]))
    response = client.get("/api/v1/oa/contracts/-9007199254740993/project-summary")
    assert response.status_code == 200
    assert response.json()["amount"] == "12.34"
    for identifier in ("9223372036854775808", "1 OR 1=1"):
        assert client.get(f"/api/v1/oa/contracts/{identifier}/project-summary").status_code == 422
    monkeypatch.setattr(oa.repository, "read_projects", lambda _: (None, []))
    assert client.get("/api/v1/oa/contracts/1/project-summary").status_code == 404
    monkeypatch.setattr(
        oa.repository, "read_projects", lambda _: (MAIN, [row(1, "甲", "1")] * 10001)
    )
    assert client.get("/api/v1/oa/contracts/1/project-summary").status_code == 409


def test_database_errors_are_sanitized(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_: str) -> Any:
        raise OperationalError(
            "secret-sql", {"password": "secret-password"}, Exception("secret-host")
        )

    monkeypatch.setattr(oa.repository, "find_contracts", fail)
    response = client.get("/api/v1/oa/contracts/lookup?contract_number=OA-001")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert response.json()["error"]["request_id"]


def test_unconfigured_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oa, "get_settings", lambda: Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.get("/api/v1/oa/contracts/lookup?contract_number=OA-001")
    assert response.status_code == 503
    assert "未配置" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "identifier,code,name",
    [
        (4747488595539675173, "CNY", "人民币"),
        (-2224278840978685884, "USD", "美元"),
        (3869348003057256238, "EUR", "欧元"),
    ],
)
def test_currency_follows_enum_but_amount_remains_rmb(
    identifier: int, code: str, name: str
) -> None:
    result = oa.summarize(
        MAIN, [row(1, "甲", "12.34", identifier), row(2, "甲", "12.34", identifier)]
    )
    assert result.currency == code
    assert result.currency_name == name
    assert result.amount_currency == "CNY"
    assert result.amount == "24.68"
    assert result.projects[0].currency_id == str(identifier)
    assert result.projects[0].currency_name == name
    assert not result.issues


@pytest.mark.parametrize(
    "identifiers,message",
    [
        ([None], "未填写币种"),
        ([9007199254740993], "未映射的币种 ID：9007199254740993"),
        ([4747488595539675173, None], "未填写币种"),
        ([4747488595539675173, 9007199254740993], "未映射"),
        ([4747488595539675173, -2224278840978685884], "多个币种"),
    ],
)
def test_currency_is_never_guessed(identifiers: list[int | None], message: str) -> None:
    result = oa.summarize(
        MAIN, [row(i, "甲", "1.00", identifier) for i, identifier in enumerate(identifiers)]
    )
    assert result.currency is None
    assert result.currency_name is None
    assert any(message in issue for issue in result.issues)
    assert result.amount_currency == "CNY"


def test_contract_items_preserve_detail_order_precision_and_missing_values() -> None:
    rows = [
        {
            **row(-9007199254740993, "甲", "9.99"),
            "software_copyright_name": " 软著甲 ",
            "hardware_amount": Decimal("999999999999999999.99"),
            "software_service_amount": Decimal("0.00"),
            "other_software_service_amount": Decimal("-1.25"),
        },
        {**row(9007199254740993, "甲", "10.00"), "software_copyright_name": "软著甲"},
    ]
    result = oa.summarize(MAIN, rows)
    assert len(result.projects) == 2
    first, second = result.projects
    assert first.id == "-9007199254740993"
    assert second.id == "9007199254740993"
    assert first.software_copyright_name == second.software_copyright_name == "软著甲"
    assert first.hardware_amount == "999999999999999999.99"
    assert first.software_service_amount == "0.00"
    assert first.other_software_service_amount == "-1.25"
    assert second.hardware_amount is None
    assert second.software_service_amount is None
    assert second.other_software_service_amount is None
    assert result.amount == "19.99"  # Still uses field0385, not a sum of the component columns.
    assert not result.issues
