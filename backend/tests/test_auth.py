"""Real JWT validation and route policy, with a local RSA issuer fixture only."""

import time
import uuid
from datetime import datetime
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import Principal, require_owner
from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.auth
client = TestClient(app)


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        "app.auth.jwks_client",
        lambda issuer: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private.public_key())
        ),
    )
    return private


def token(key, roles=None, **overrides) -> str:
    settings = get_settings()
    claims = {
        "sub": "user-a",
        "iss": settings.oidc_issuer,
        "aud": ["another-app", settings.oidc_audience, "account"],
        "exp": int(time.time()) + 300,
        "typ": "Bearer",
        "preferred_username": "user",
        "resource_access": {
            settings.oidc_audience: {"roles": roles if roles is not None else ["agent_user"]}
        },
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


def headers(key, roles=None, **overrides):
    return {"Authorization": f"Bearer {token(key, roles, **overrides)}"}


def test_public_bootstrap_and_no_secret() -> None:
    assert client.get("/api/v1/health/live").status_code == 200
    config = client.get("/api/v1/auth/config")
    assert config.status_code == 200
    assert "secret" not in config.text.lower()
    assert config.json()["redirect_uri"] == "http://127.0.0.1:15173/callback"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/me",
        "/api/v1/templates",
        "/api/v1/oa/contracts/lookup?number=example",
        "/api/v1/health/ready",
        f"/api/v1/tasks/{uuid.uuid4()}",
        f"/api/v1/tasks/{uuid.uuid4()}/events",
        f"/api/v1/document-previews/{uuid.uuid4()}/file",
        f"/api/v1/document-previews/{uuid.uuid4()}/download",
    ],
)
def test_missing_token_fails_closed(path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["request_id"]


def test_audience_membership_roles_and_empty_departments(signing_key) -> None:
    for role in ["agent_user", "agent_manager", "agent_admin"]:
        response = client.get("/api/v1/auth/me", headers=headers(signing_key, [role]))
        assert response.status_code == 200
        assert response.json()["roles"] == [role]
        assert response.json()["sub"] == "user-a"
        assert response.json()["department_code"] == ""
    assert client.get("/api/v1/auth/me", headers=headers(signing_key, [])).status_code == 403
    assert (
        client.get(
            "/api/v1/auth/me",
            headers=headers(signing_key, resource_access={"other-api": {"roles": ["agent_admin"]}}),
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "https://wrong-issuer"},
        {"aud": ["other-api"]},
        {"exp": 1},
        {"sub": ""},
        {"typ": "ID"},
        {"nbf": 4102444800},
        {"resource_access": []},
        {"resource_access": {"marketing-contract-drafting-api": None}},
    ],
)
def test_invalid_claims_rejected(signing_key, override) -> None:
    assert (
        client.get("/api/v1/auth/me", headers=headers(signing_key, **override)).status_code == 401
    )


def test_forged_signature_and_unsigned_token(signing_key) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert client.get("/api/v1/auth/me", headers=headers(other)).status_code == 401
    unsigned = jwt.encode({"sub": "admin", "exp": 4102444800}, key=None, algorithm="none")
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {unsigned}"}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/templates"),
        ("DELETE", f"/api/v1/templates/{uuid.uuid4()}"),
        ("PUT", f"/api/v1/templates/{uuid.uuid4()}/cover-config"),
        ("PUT", f"/api/v1/templates/{uuid.uuid4()}/fields"),
        ("GET", f"/api/v1/templates/{uuid.uuid4()}/file"),
    ],
)
def test_template_management_is_admin_only(signing_key, method, path) -> None:
    for role in ["agent_user", "agent_manager"]:
        assert client.request(method, path, headers=headers(signing_key, [role])).status_code == 403


def test_owner_policy_including_unowned_legacy_rows() -> None:
    from fastapi import HTTPException

    user = Principal("alice", frozenset({"agent_user"}), 4102444800)
    require_owner("alice", user)
    for owner in ["bob", None]:
        with pytest.raises(HTTPException) as error:
            require_owner(owner, user)
        assert error.value.status_code == 404
    require_owner(None, Principal("admin", frozenset({"agent_admin"}), 4102444800))


@pytest.mark.parametrize(
    "temporal,status",
    [
        ({"iat": 2000000001}, 200),
        ({"iat": 2000000005, "nbf": 2000000005}, 200),
        ({"iat": 2000000006}, 401),
        ({"nbf": 2000000006}, 401),
        ({"exp": 1999999994}, 401),
    ],
)
def test_clock_skew_tolerance(signing_key, monkeypatch, temporal, status) -> None:
    request_headers = headers(signing_key, **{"exp": 2000000900, **temporal})
    # Freeze the verifier clock: a freshly issued token can arrive just before its iat.
    monkeypatch.setattr(
        "jwt.api_jwt.datetime",
        SimpleNamespace(now=lambda tz: datetime.fromtimestamp(2000000000, tz)),
    )
    response = client.get("/api/v1/auth/me", headers=request_headers)
    assert response.status_code == status


@pytest.mark.parametrize(
    "override,message,error_type",
    [
        ({"exp": 1}, "登录已过期，请重新登录", "ExpiredSignatureError"),
        (
            {"iat": 4102444800},
            "认证服务时间不同步，请稍后重试或联系管理员",
            "ImmatureSignatureError",
        ),
        ({"aud": "wrong-api"}, "登录凭据无效，请重新登录", "InvalidAudienceError"),
    ],
)
def test_rejection_reason_is_actionable_without_logging_token(
    signing_key, caplog, override, message, error_type
) -> None:
    request_headers = headers(signing_key, **override)
    response = client.get("/api/v1/auth/me", headers=request_headers)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == message
    record = next(r for r in caplog.records if r.getMessage() == "Access token rejected")
    assert record.error_type == error_type
    assert record.request_id == response.headers["x-request-id"]
    assert request_headers["Authorization"].removeprefix("Bearer ") not in caplog.text
