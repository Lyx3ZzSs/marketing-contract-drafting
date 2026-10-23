"""OIDC resource-server boundary; all business routes fail closed by default."""

import logging
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Annotated, Any

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from jwt import PyJWKClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BUSINESS_ROLES = frozenset({"agent_admin", "agent_manager", "agent_user"})
PUBLIC_PATHS = frozenset({"/api/v1/health/live", "/api/v1/auth/config"})
router = APIRouter(prefix="/api/v1/auth", tags=["统一认证"])


@dataclass(frozen=True)
class Principal:
    sub: str
    roles: frozenset[str]
    expires_at: int
    username: str = ""
    name: str = ""
    department_code: str = ""
    department_name: str = ""

    @property
    def is_admin(self) -> bool:
        return "agent_admin" in self.roles


def unauthorized(message: str = "登录凭据无效，请重新登录") -> HTTPException:
    return HTTPException(401, message, headers={"WWW-Authenticate": "Bearer"})


@lru_cache(maxsize=4)
def jwks_client(issuer: str) -> PyJWKClient:
    # Only trust discovery at the configured issuer, never a URL supplied by a token.
    response = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=5)
    response.raise_for_status()
    metadata = response.json()
    if metadata.get("issuer") != issuer:
        raise ValueError("OIDC discovery issuer mismatch")
    return PyJWKClient(metadata["jwks_uri"], timeout=5, lifespan=300)


def verify_token(token: str) -> Principal:
    settings = get_settings()
    try:
        client = jwks_client(settings.oidc_issuer)
        key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            leeway=settings.oidc_clock_skew_seconds,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        if not claims["sub"] or claims.get("typ") != "Bearer":
            raise unauthorized()
        resources = claims.get("resource_access", {})
        if not isinstance(resources, dict):
            raise unauthorized()
        access = resources.get(settings.oidc_audience, {})
        if not isinstance(access, dict):
            raise unauthorized()
        roles = access.get("roles", [])
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise unauthorized()
        return Principal(
            sub=claims["sub"],
            roles=frozenset(roles) & BUSINESS_ROLES,
            expires_at=int(claims["exp"]),
            username=str(claims.get("preferred_username") or ""),
            name=str(claims.get("name") or ""),
            department_code=str(claims.get("department_code") or ""),
            department_name=str(claims.get("department_name") or ""),
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, "统一认证服务暂时不可用，请稍后重试") from exc
    except jwt.ExpiredSignatureError as exc:
        raise unauthorized("登录已过期，请重新登录") from exc
    except jwt.ImmatureSignatureError as exc:
        raise unauthorized("认证服务时间不同步，请稍后重试或联系管理员") from exc
    except jwt.PyJWTError as exc:
        raise unauthorized() from exc
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "统一认证配置或公钥暂时不可用") from exc


def current_principal(request: Request) -> Principal:
    if hasattr(request.state, "principal"):
        principal: Principal = request.state.principal
        return principal
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 32768:
        raise unauthorized()
    try:
        principal = verify_token(token)
    except HTTPException as exc:
        if exc.status_code == 401:
            logger.warning(
                "Access token rejected",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "error_type": type(exc.__cause__).__name__
                    if exc.__cause__ is not None
                    else "InvalidBearerClaims",
                },
            )
        raise
    request.state.principal = principal
    return principal


CurrentUser = Annotated[Principal, Depends(current_principal)]


def require_access(request: Request) -> None:
    if request.url.path in PUBLIC_PATHS:
        return
    # Dependency overrides remain available to tests; production has no auth bypass switch.
    principal = current_principal(request)
    if not principal.roles & BUSINESS_ROLES:
        raise HTTPException(403, "当前账号未获营销合同起草系统访问权限")


def require_admin(user: CurrentUser) -> None:
    if not user.is_admin:
        raise HTTPException(403, "此操作仅限系统管理员")


def require_owner(owner_sub: str | None, user: Principal) -> None:
    # Legacy rows without an owner are admin-only; they are never assigned to the next visitor.
    if not user.is_admin and owner_sub != user.sub:
        raise HTTPException(404, "资源不存在或无权访问")


@router.get("/config")
def public_config() -> dict[str, str]:
    settings = get_settings()
    return {
        "authority": settings.oidc_issuer,
        "client_id": settings.oidc_web_client_id,
        "redirect_uri": f"{settings.oidc_frontend_url}/callback",
        "post_logout_redirect_uri": f"{settings.oidc_frontend_url}/",
    }


@router.get("/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return {**asdict(user), "roles": sorted(user.roles)}
