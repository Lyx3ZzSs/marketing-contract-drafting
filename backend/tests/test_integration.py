import os
import time
import uuid
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Task

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("TEST_ACCESS_TOKEN"), reason="需提供真实管理员 Access Token"),
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="需显式启用真实服务联调"),
]
BASE = os.getenv("TEST_API_URL", "http://127.0.0.1:18400")


@pytest.fixture
def ids() -> Iterator[list[str]]:
    created: list[str] = []
    yield created
    with SessionLocal.begin() as session:
        for ident in created:
            session.execute(delete(Task).where(Task.id == uuid.UUID(ident)))


def wait_terminal(client: httpx.Client, task_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()
        if response.json()["status"] in {"succeeded", "failed"}:
            return response.json()
        time.sleep(0.2)
    pytest.fail("后台任务未在 30 秒内完成，请检查 worker")


@pytest.mark.parametrize("simulate_failure", [False, True])
def test_real_worker_events_and_resume(ids: list[str], simulate_failure: bool) -> None:
    with httpx.Client(
        base_url=BASE,
        timeout=20,
        headers={"Authorization": f"Bearer {os.environ['TEST_ACCESS_TOKEN']}"},
    ) as client:
        response = client.post(
            "/api/v1/demo/tasks",
            json={
                "document": {"type": "doc", "content": [{"type": "text", "text": "联调样本"}]},
                "simulate_failure": simulate_failure,
            },
        )
        assert response.status_code == 202, response.text
        ident = response.json()["id"]
        ids.append(ident)
        task = wait_terminal(client, ident)
        assert task["status"] == ("failed" if simulate_failure else "succeeded")
        response = client.get(f"/api/v1/tasks/{ident}/events")
        assert response.headers["content-type"].startswith("text/event-stream")
        event_ids = [
            int(line[4:]) for line in response.text.splitlines() if line.startswith("id: ")
        ]
        assert len(event_ids) >= 3
        assert event_ids == sorted(set(event_ids))
        assert f"event: {'failed' if simulate_failure else 'completed'}" in response.text
        replay = client.get(
            f"/api/v1/tasks/{ident}/events", headers={"Last-Event-ID": str(event_ids[1])}
        )
        replay_ids = [int(line[4:]) for line in replay.text.splitlines() if line.startswith("id: ")]
        assert replay_ids == event_ids[2:]
        assert (
            client.get(
                f"/api/v1/tasks/{ident}/events", headers={"Last-Event-ID": str(event_ids[-1])}
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/v1/tasks/{ident}/events", headers={"Last-Event-ID": "invalid"}
            ).status_code
            == 400
        )
        assert client.get(f"/api/v1/tasks/{uuid.uuid4()}").status_code == 404


def test_heartbeat_and_disconnect_preserve_task(ids: list[str]) -> None:
    ident = uuid.uuid4()
    ids.append(str(ident))
    with SessionLocal.begin() as session:
        session.add(Task(id=ident, status="queued", input={}, request_id="integration-heartbeat"))
    with httpx.Client(
        base_url=BASE,
        timeout=20,
        headers={"Authorization": f"Bearer {os.environ['TEST_ACCESS_TOKEN']}"},
    ) as client:
        with client.stream("GET", f"/api/v1/tasks/{ident}/events") as response:
            for line in response.iter_lines():
                if line == ": heartbeat":
                    break
        assert client.get(f"/api/v1/tasks/{ident}").json()["status"] == "queued"
