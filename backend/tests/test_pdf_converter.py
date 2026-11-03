import re
from collections.abc import Callable

import httpx
import jwt
import pytest

from app import pdf_converter
from app.core.config import Settings

SECRET = "onlyoffice-test-secret-32-bytes-long"
PDF = b"%PDF-1.7\nconverted"


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> Callable:
    settings = Settings(_env_file=None, onlyoffice_jwt_secret=SECRET)
    monkeypatch.setattr(pdf_converter, "get_settings", lambda: settings)
    client_class = httpx.Client

    def install(handler: Callable) -> None:
        monkeypatch.setattr(
            pdf_converter.httpx,
            "Client",
            lambda **kw: client_class(transport=httpx.MockTransport(handler), **kw),
        )

    return install


def test_upload_then_poll_signed_parameters_and_fresh_keys(service: Callable) -> None:
    requests = []
    payloads = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = request.read()
        token = re.search(rb'name="token"\r\n\r\n([^\r]+)', body)
        assert token
        payload = jwt.decode(token[1], SECRET, algorithms=["HS256"])
        payloads.append(payload)
        requests.append(body)
        assert request.url.path == "/converter/from-file"
        assert request.url.params["shardkey"] == payload["key"]
        assert payload["operation"] == "converter"
        assert payload["filetype"] == "docx" and payload["outputtype"] == "pdf"
        assert "url" not in payload and payload["async"] is True
        if len(requests) == 1:
            return httpx.Response(200, json={"endConvert": False, "percent": 25})
        return httpx.Response(200, content=PDF)

    service(handle)
    assert pdf_converter.convert_pdf(b"original-docx") == PDF
    assert b"original-docx" in requests[0]
    assert b'name="file"' not in requests[1]
    assert payloads[0] == payloads[1]
    assert pdf_converter.convert_pdf(b"original-docx") == PDF
    assert payloads[2]["key"] != payloads[0]["key"]


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (403, b"secret details", "鉴权失败"),
        (413, b"too large", "上传大小限制"),
        (503, b"secret details", "服务请求失败"),
        (302, b"", "服务请求失败"),
        (200, b'{"error":-8}', "鉴权失败"),
        (200, b'{"error":-3}', "转换失败"),
        (200, b'{"endConvert":true,"fileUrl":"http://other/secret"}', "有效的 PDF"),
        (200, b"<html>gateway</html>", "有效的 PDF"),
        (200, b"[]", "状态无效"),
    ],
)
def test_rejects_errors_without_leaking_response(
    service: Callable, status: int, body: bytes, message: str
) -> None:
    service(lambda request: httpx.Response(status, content=body))
    with pytest.raises(ValueError, match=message) as error:
        pdf_converter.convert_pdf(b"input")
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    ("error_type", "message"),
    [(httpx.ConnectError, "无法连接"), (httpx.ReadTimeout, "超时")],
)
def test_network_failures_are_actionable(service: Callable, error_type: type, message: str) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error_type("private connection details", request=request)

    service(fail)
    with pytest.raises(ValueError, match=message):
        pdf_converter.convert_pdf(b"input")


def test_polling_has_total_deadline(service: Callable, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    monkeypatch.setattr(pdf_converter.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(pdf_converter.time, "sleep", lambda seconds: now.__setitem__(0, 121.0))
    service(lambda request: httpx.Response(200, json={"endConvert": False}))
    with pytest.raises(ValueError, match="超时"):
        pdf_converter.convert_pdf(b"input")


def test_streamed_size_limit(service: Callable, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_converter, "MAX_PDF_BYTES", 10)
    service(lambda request: httpx.Response(200, content=PDF))
    with pytest.raises(ValueError, match="32 MB"):
        pdf_converter.convert_pdf(b"input")


def test_missing_secret_fails_before_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_converter, "get_settings", lambda: Settings(_env_file=None))
    with pytest.raises(ValueError, match="未配置 JWT"):
        pdf_converter.convert_pdf(b"input")
