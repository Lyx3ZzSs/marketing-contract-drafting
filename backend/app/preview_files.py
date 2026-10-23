"""Storage of expiring PDF artifacts; original templates are never written here."""

import re
from pathlib import Path
from typing import Literal

from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.storage import ObjectStorage

MAX_PDF_BYTES = 32 * 1024 * 1024
StorageBackend = Literal["local", "s3"]


def local_path(key: str) -> Path:
    if not re.fullmatch(r"document-previews/[0-9a-f]{32}\.pdf", key):
        raise ValueError("预览文件标识无效")
    return get_settings().preview_directory / key


def write_pdf(backend: str, key: str, data: bytes) -> None:
    if not data.startswith(b"%PDF-") or len(data) > MAX_PDF_BYTES:
        raise ValueError("转换结果无效或超过 32 MB 限制")
    path = local_path(key)
    if backend == "local":
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    elif backend == "s3":
        store = ObjectStorage()
        store.client().put_object(
            Bucket=store.settings.s3_bucket, Key=key, Body=data, ContentType="application/pdf"
        )
    else:
        raise ValueError("预览存储配置无效")


def read_pdf(backend: str, key: str) -> bytes:
    path = local_path(key)
    if backend == "local":
        data = path.read_bytes()
    elif backend == "s3":
        store = ObjectStorage()
        try:
            body = store.client().get_object(Bucket=store.settings.s3_bucket, Key=key)["Body"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise FileNotFoundError(key) from exc
            raise
        try:
            data = body.read(MAX_PDF_BYTES + 1)
        finally:
            body.close()
    else:
        raise ValueError("预览存储配置无效")
    if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        raise ValueError("预览文件无效，请重新生成")
    return data


def delete_pdf(backend: str, key: str) -> None:
    path = local_path(key)
    if backend == "local":
        path.unlink(missing_ok=True)
    elif backend == "s3":
        store = ObjectStorage()
        store.client().delete_object(Bucket=store.settings.s3_bucket, Key=key)
