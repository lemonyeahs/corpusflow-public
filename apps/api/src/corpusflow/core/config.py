from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class ConfigurationError(RuntimeError):
    """Safe startup diagnostic; never include environment values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test"] = "development"
    database_url: SecretStr
    redis_url: SecretStr
    object_store_endpoint: str
    object_store_bucket: str = Field(min_length=3)
    object_store_access_key: SecretStr
    object_store_secret_key: SecretStr
    dependency_timeout: int = Field(default=2, ge=1, le=10)

    # M0 configuration contract; query/snapshot/export enforcement is implemented by M1 routers.
    training_center_data_dir: Path = Path(".local/training-center")
    training_center_snapshot_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    training_center_snapshot_max_per_workspace: int = Field(default=10, ge=1, le=100)
    training_center_max_records: int = Field(default=100000, ge=1, le=100000)
    training_center_max_bytes: int = Field(default=104857600, ge=1, le=104857600)

    llm_provider: Literal["disabled", "openai_compatible"] = "disabled"
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_workspaces: list[str] = Field(default_factory=list)
    llm_max_calls: int = Field(default=0, ge=0, le=10)
    llm_max_tokens: int = Field(default=512, ge=1, le=512)
    llm_timeout: int = Field(default=45, ge=1, le=60)

    @field_validator("llm_base_url")
    @classmethod
    def llm_endpoint(cls, value: str) -> str:
        from urllib.parse import urlsplit

        if not value:
            return value
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("Explicit HTTPS provider URL without credentials required")
        return value.rstrip("/")

    acquisition_hosts: list[str] = Field(default_factory=list)
    embedding_endpoint: str = ""
    embedding_timeout: int = Field(default=30, ge=1, le=60)
    embedding_retries: int = Field(default=1, ge=0, le=2)

    @field_validator("embedding_endpoint")
    @classmethod
    def local_embedding_only(cls, value: str) -> str:
        from urllib.parse import urlsplit

        if not value:
            return value
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname not in {"localhost", "127.0.0.1", "host.docker.internal"}
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("Only explicit local embedding endpoints are supported")
        return value

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("Invalid PostgreSQL URL") from None
        if url.drivername != "postgresql+psycopg":
            raise ValueError("PostgreSQL psycopg URL required")
        return value

    @field_validator("redis_url")
    @classmethod
    def redis_only(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("Redis URL required")
        return value

    @field_validator("object_store_endpoint")
    @classmethod
    def http_only(cls, value: str) -> str:
        from urllib.parse import urlsplit

        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username:
            raise ValueError("HTTP(S) endpoint without credentials required")
        return value

    @field_validator("object_store_access_key", "object_store_secret_key")
    @classmethod
    def no_placeholders(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value() or value.get_secret_value().startswith("CHANGE_ME"):
            raise ValueError("Replace placeholder with local generated credentials")
        return value


def load_settings() -> Settings:
    try:
        return Settings()
    except (ValidationError, ValueError) as exc:
        fields = (
            sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
            if isinstance(exc, ValidationError)
            else ["database_url"]
        )
        raise ConfigurationError("CONFIG_INVALID: check " + ", ".join(fields)) from None
