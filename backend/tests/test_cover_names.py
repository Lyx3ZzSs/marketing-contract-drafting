import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from test_oa import MAIN, row

from app import oa
from app.cover_names import build_suggestion
from app.db import SessionLocal
from app.main import app
from app.models import ContractTemplate, StationAlias
from app.station_names import WIND_COVER, group_stations, suggest_station


@pytest.mark.parametrize(
    "source,expected",
    [
        ("甘肃张掖市甘州区平山湖（中电建）风电场", "平山湖"),
        ("辽宁朝阳市凌源市宋杖子风电场", "宋杖子"),
        ("贵州黔东南苗族侗族自治州天柱县石洞风电场", "石洞"),
        ("河北保定市定州市高蓬（三期）风电场", "高蓬（三期）"),
        ("河北邯郸市成安县成安（2号）风电场", "成安（2号）"),
        ("辽宁鞍山市海城市双铺村风电风电场", "双铺村"),
        ("新疆吐鲁番地区吐鲁番市新翔风电场风电场", "新翔"),
        ("重庆重庆市丰都县回山坪（临时扩容）风电场", "回山坪（临时扩容）"),
    ],
)
def test_conservative_extraction(source: str, expected: str) -> None:
    assert suggest_station(source, None)[0] == expected


def test_uncertainty_is_not_silently_deleted() -> None:
    name, notes = suggest_station("四川凉山彝族自治州会理县稻香（白岩）风电场", None)
    assert name == "稻香（白岩）" and notes
    name, notes = suggest_station("河北唐山市乐亭县环港风电场", "wrong-province")
    assert name == "河北唐山市乐亭县环港" and notes
    for source in ("", "安徽宿州市灵璧县龙山光伏电站", "北京北京市朝阳区总部集团侧"):
        name, notes = suggest_station(source, None)
        assert name == "" and notes


def test_grouping_uses_codes_and_never_merges_different_codes_with_same_name() -> None:
    rows = [
        {"id": "1", "station_name": "甲风电场", "station_code": "A"},
        {"id": "2", "station_name": "甲风电场", "station_code": "A"},
        {"id": "3", "station_name": "甲风电场", "station_code": "B"},
        {"id": "4", "station_name": "乙风电场"},
        {"id": "5", "station_name": "乙风电场"},
        {"id": "6", "station_name": None},
        {"id": "7", "station_name": None},
    ]
    groups = group_stations(rows)
    assert len(groups) == 5
    result = build_suggestion(groups, WIND_COVER, "token", {})
    assert result.contract_name is None
    assert result.entries[0].status == result.entries[1].status == "review"
    assert "相同" in result.entries[0].notes[-1]
    assert not result.entries[2].can_remember


def test_confirmed_alias_reused_only_for_unchanged_source() -> None:
    alias = StationAlias(
        station_code="A", source_names=["甲风电场"], short_name="已确认甲", revision=3
    )
    groups = group_stations([{"id": "1", "station_name": "甲风电场", "station_code": "A"}])
    result = build_suggestion(groups, WIND_COVER, "t", {"A": alias})
    assert result.contract_name == "已确认甲风电站风电场功率预测系统V1.0采购合同"
    assert result.entries[0].status == "confirmed"
    groups[0]["source_names"] = ["甲二期风电场"]
    result = build_suggestion(groups, WIND_COVER, "t", {"A": alias})
    assert result.entries[0].short_name == "甲二期"
    assert result.entries[0].status == "source_changed"
    assert result.entries[0].revision == 3


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="requires migrated PostgreSQL")
def test_suggestions_reuse_existing_aliases_and_track_source_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_id = uuid.uuid4()
    code = f"test-{uuid.uuid4()}"
    projects = [{**row(1, "河北唐山市乐亭县环港风电场", "10"), "station_code": code}]
    monkeypatch.setattr(oa.repository, "read_projects", lambda _: (MAIN, projects))
    app.dependency_overrides[oa.require_oa] = lambda: None
    with SessionLocal.begin() as session:
        session.add(
            ContractTemplate(
                id=template_id,
                name="封面名称测试",
                source_file="test.docx",
                source_sha256=uuid.uuid4().hex,
                original=b"test",
                sections=[],
                section_count=0,
                cover_config=WIND_COVER,
            )
        )
    try:
        with TestClient(app) as client:
            base = "/api/v1/oa/contracts/1"

            def read() -> dict:
                response = client.get(
                    base + "/name-suggestions", params={"template_id": str(template_id)}
                )
                assert response.status_code == 200, response.text
                return response.json()

            assert read()["entries"][0]["short_name"] == "环港"
            with SessionLocal.begin() as session:
                session.add(
                    StationAlias(
                        station_code=code,
                        source_names=[projects[0]["station_name"]],
                        short_name="确认环港",
                        revision=1,
                    )
                )
            assert read()["entries"][0]["short_name"] == "确认环港"
            projects[0]["station_name"] = "河北唐山市乐亭县环港二期风电场"
            assert read()["entries"][0]["status"] == "source_changed"
            assert read()["entries"][0]["short_name"] == "环港二期"
            config = {**WIND_COVER, "document_line": "设备采购合同"}
            assert (
                client.put(f"/api/v1/templates/{template_id}/cover-config", json=config).status_code
                == 200
            )
            assert read()["contract_name"] == "环港二期风电站风电场功率预测系统V1.0设备采购合同"
            projects[0]["station_code"] = None
            assert read()["entries"][0]["status"] != "confirmed"
            # Missing OA names still permit valid financial data to be retrieved.
            projects[0]["station_name"] = None
            response = client.get(base + "/project-summary").json()
            assert response["amount"] == "10.00" and response["issues"] == []
    finally:
        app.dependency_overrides.clear()
        with SessionLocal.begin() as session:
            session.execute(delete(StationAlias).where(StationAlias.station_code == code))
            session.execute(delete(ContractTemplate).where(ContractTemplate.id == template_id))
