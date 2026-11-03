"""ONLYOFFICE Docs 10 conversion with authenticated uploads and bounded polling."""

import json
import time
import uuid

import httpx
import jwt

from app.core.config import get_settings
from app.preview_files import MAX_PDF_BYTES


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("合同排版超时，请重试")
    return remaining


def convert_pdf(docx: bytes) -> bytes:
    settings = get_settings()
    secret = settings.onlyoffice_jwt_secret.get_secret_value()
    if not secret:
        raise ValueError("ONLYOFFICE 转换服务未配置 JWT 密钥")
    key = uuid.uuid4().hex
    params = {
        "operation": "converter",
        "async": True,
        "key": key,
        "filetype": "docx",
        "outputtype": "pdf",
        "title": "contract.docx",
        "exp": int(time.time()) + settings.preview_timeout_seconds + 30,
    }
    token = jwt.encode(params, secret, algorithm="HS256")
    endpoint = f"{str(settings.onlyoffice_url).rstrip('/')}/converter/from-file"
    deadline = time.monotonic() + settings.preview_timeout_seconds
    first = True
    try:
        # Never forward contracts/JWTs through ambient proxies or response redirects.
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            while True:
                files: dict[str, tuple[None, str] | tuple[str, bytes]] = {"token": (None, token)}
                if first:
                    files["file"] = ("contract.docx", docx)
                with client.stream(
                    "POST",
                    endpoint,
                    params={"shardkey": key},
                    files=files,
                    timeout=_remaining(deadline),
                ) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        _remaining(deadline)
                        content.extend(chunk)
                        if len(content) > MAX_PDF_BYTES:
                            raise ValueError("预览文件超过 32 MB 限制")
                _remaining(deadline)
                data = bytes(content)
                if data.startswith(b"%PDF-"):
                    return data
                try:
                    state = json.loads(data)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ValueError("ONLYOFFICE 未返回有效的 PDF 或转换状态") from exc
                if not isinstance(state, dict):
                    raise ValueError("ONLYOFFICE 返回的转换状态无效")
                if state.get("error") is not None:
                    # Do not expose remote response bodies, paths or tokens in task events.
                    if state["error"] == -8:
                        raise ValueError("ONLYOFFICE 鉴权失败，请检查 JWT 配置")
                    raise ValueError("合同 PDF 转换失败，请检查模板格式或 ONLYOFFICE 服务")
                if state.get("endConvert") is not False:
                    raise ValueError("ONLYOFFICE 未返回有效的 PDF 文件")
                first = False
                time.sleep(min(0.5, _remaining(deadline)))
    except httpx.TimeoutException as exc:
        raise ValueError("合同排版超时，请重试") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise ValueError("ONLYOFFICE 鉴权失败，请检查 JWT 配置") from exc
        if exc.response.status_code == 413:
            raise ValueError("合同文件超过 ONLYOFFICE 上传大小限制") from exc
        raise ValueError("ONLYOFFICE 转换服务请求失败，请稍后重试") from exc
    except httpx.RequestError as exc:
        raise ValueError("无法连接 ONLYOFFICE 转换服务，请检查服务地址与运行状态") from exc
