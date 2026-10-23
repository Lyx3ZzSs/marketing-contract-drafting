import uuid
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import Settings, get_settings


class ObjectStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def client(self) -> Any:
        if not self.settings.storage_configured:
            raise ValueError("MinIO 未配置")
        protocol = "https" if self.settings.s3_use_tls else "http"
        return boto3.client(
            "s3",
            endpoint_url=f"{protocol}://{self.settings.s3_endpoint}",
            region_name=self.settings.s3_region,
            aws_access_key_id=self.settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=self.settings.s3_secret_key.get_secret_value(),
            verify=self.settings.s3_verify_tls,
            config=Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"max_attempts": 0},
                s3={"addressing_style": "path"},
            ),
        )

    def check(self) -> dict[str, str]:
        if not self.settings.storage_configured:
            return {"status": "unconfigured", "message": "未配置公司 MinIO 测试 bucket"}
        self.client().head_bucket(Bucket=self.settings.s3_bucket)
        return {"status": "ok"}

    def smoke_test(self) -> dict[str, str]:
        if not self.settings.storage_configured:
            return {"status": "skipped", "message": "MinIO 未配置，上传下载未验证"}
        client = self.client()
        key = f"scaffold-smoke/{uuid.uuid4()}.txt"
        data = "合同脚手架对象存储验证".encode()
        version_id = None
        uploaded = False
        try:
            response = client.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=data)
            uploaded = True
            version_id = response.get("VersionId")
            args = {"Bucket": self.settings.s3_bucket, "Key": key}
            if version_id:
                args["VersionId"] = version_id
            body = client.get_object(**args)["Body"]
            try:
                if body.read() != data:
                    raise RuntimeError("对象存储读写结果不一致")
            finally:
                body.close()
        finally:
            if uploaded:
                args = {"Bucket": self.settings.s3_bucket, "Key": key}
                if version_id:
                    args["VersionId"] = version_id
                client.delete_object(**args)
        return {"status": "ok", "message": "上传、下载及测试对象清理完成"}
