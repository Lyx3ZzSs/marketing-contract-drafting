from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.storage import ObjectStorage


def test_unconfigured_storage_does_not_connect() -> None:
    storage = ObjectStorage(Settings(_env_file=None))
    assert storage.check()["status"] == "unconfigured"
    assert storage.smoke_test()["status"] == "skipped"


@pytest.mark.parametrize("read_fails", [False, True])
def test_smoke_cleans_exact_uploaded_version(monkeypatch: Any, read_fails: bool) -> None:
    storage = ObjectStorage(
        Settings(
            _env_file=None,
            s3_endpoint="example.invalid",
            s3_bucket="test",
            s3_access_key="test",
            s3_secret_key="test",
        )
    )
    client = MagicMock()
    client.put_object.return_value = {"VersionId": "test-version"}
    if read_fails:
        client.get_object.side_effect = RuntimeError("read failed")
    else:
        client.get_object.return_value["Body"].read.return_value = "合同脚手架对象存储验证".encode()
    monkeypatch.setattr(storage, "client", lambda: client)
    if read_fails:
        with pytest.raises(RuntimeError):
            storage.smoke_test()
    else:
        assert storage.smoke_test()["status"] == "ok"
    key = client.put_object.call_args.kwargs["Key"]
    client.delete_object.assert_called_once_with(Bucket="test", Key=key, VersionId="test-version")
