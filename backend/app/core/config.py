from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env", extra="ignore"
    )

    app_env: Literal["development", "test"] = "development"
    log_level: str = "INFO"
    oidc_issuer: str = "http://10.8.6.32:18080/realms/company-dev"
    oidc_audience: str = "marketing-contract-drafting-api"
    oidc_web_client_id: str = "marketing-contract-drafting-web"
    oidc_clock_skew_seconds: int = Field(default=5, ge=0, le=30)
    oidc_frontend_url: str = "http://127.0.0.1:15173"
    database_url: str = (
        "postgresql+psycopg://contract:contract_dev@127.0.0.1:15432/contract_drafting"
    )
    redis_url: str = "redis://127.0.0.1:16379/0"
    sse_poll_seconds: float = Field(default=0.5, ge=0.05)
    sse_heartbeat_seconds: float = Field(default=10, ge=1)
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    s3_use_tls: bool = True
    s3_verify_tls: bool = True
    preview_storage: Literal["local", "s3"] = "local"
    preview_directory: Path = Path("/tmp/contract-previews")
    preview_ttl_hours: int = Field(default=24, ge=1, le=168)
    preview_timeout_seconds: int = Field(default=120, ge=10, le=120)
    preview_renderer_revision: str = "libreoffice-noto-cjk-v1"
    libreoffice_binary: str = "soffice"
    crm_mode: Literal["demo"] = "demo"
    llm_enabled: Literal[False] = False
    oa_host: str = ""
    oa_port: int = Field(default=3306, ge=1, le=65535)
    oa_database: str = ""
    oa_user: str = ""
    oa_password: SecretStr = SecretStr("")
    oa_connect_timeout: int = Field(default=3, ge=1, le=10)
    oa_query_timeout: int = Field(default=5, ge=1, le=15)

    @property
    def oa_configured(self) -> bool:
        return bool(
            self.oa_host
            and self.oa_database
            and self.oa_user
            and self.oa_password.get_secret_value()
        )

    @property
    def storage_configured(self) -> bool:
        return bool(
            self.s3_endpoint
            and self.s3_bucket
            and self.s3_access_key.get_secret_value()
            and self.s3_secret_key.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
