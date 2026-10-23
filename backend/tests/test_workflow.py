import pytest
from pydantic import ValidationError

from app.schemas import DemoTaskInput
from app.workflows import create_demo_graph


def test_graph_uses_explicit_demo_and_no_model() -> None:
    reports = []
    output = create_demo_graph(lambda progress, message: reports.append(progress)).invoke(
        {
            "document": {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "测试合同 & 项目"}]}
                ],
            },
        }
    )
    assert reports == [20, 55, 85]
    assert output["result"]["model_used"] is False
    assert output["result"]["project"]["source"] == "demo"
    assert output["result"]["excerpt"] == "测试合同 & 项目"


def test_empty_document_fails_in_worker_workflow() -> None:
    with pytest.raises(ValueError, match="请先输入"):
        create_demo_graph(lambda *_: None).invoke({"document": {"type": "doc"}})


def test_request_rejects_invalid_document_and_oversize() -> None:
    with pytest.raises(ValidationError):
        DemoTaskInput(document={"type": "paragraph"})
    with pytest.raises(ValidationError):
        DemoTaskInput(document={"type": "doc", "text": "文" * 100_000})
