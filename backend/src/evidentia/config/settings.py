"""Typed and fail-closed settings for Evidentia processes.

@skyhook-implements NFR-004
@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from evidentia.modules.access.public import LoginIdentifier, TenantSlug

_PLACEHOLDER_SECRETS = frozenset(
    {
        "change-me",
        "changeme",
        "development-only",
        "example",
        "password",
        "replace-me",
        "secret",
    }
)


class RuntimeEnvironment(StrEnum):
    """Supported runtime validation profiles.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class DatabaseSettings(BaseModel):
    """Database connectivity values shared by API and worker processes.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """

    model_config = ConfigDict(frozen=True)

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    name: str = Field(default="evidentia", min_length=1)
    user: str = Field(default="evidentia", min_length=1)
    password: SecretStr | None = None
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    sslmode: Literal["disable", "prefer", "require", "verify-ca", "verify-full"] = "prefer"
    application_name: str = Field(default="evidentia", min_length=1, max_length=64)


class LoggingSettings(BaseModel):
    """Structured logging controls shared by independently runnable services.

    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """

    model_config = ConfigDict(frozen=True)

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_output: bool = Field(default=False, validation_alias="json", serialization_alias="json")


class StorageSettings(BaseModel):
    """Configuration for the supported local filesystem storage adapter.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """

    model_config = ConfigDict(frozen=True)

    backend: Literal["filesystem"] = "filesystem"
    root: Path = Path(".local/artifacts")


class IdentitySettings(BaseModel):
    """Local bootstrap identity values independent of persistence mechanics.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(frozen=True)

    bootstrap_login_identifier: str = "admin@localhost"
    bootstrap_display_name: str = Field(default="Local Administrator", min_length=1, max_length=200)
    bootstrap_tenant_slug: str = "local"
    bootstrap_tenant_name: str = Field(
        default="Local Evidentia Workspace", min_length=1, max_length=200
    )
    bootstrap_password: SecretStr | None = None

    @field_validator("bootstrap_login_identifier")
    @classmethod
    def normalize_bootstrap_login_identifier(cls, value: str) -> str:
        """Normalize and validate the configured local login identifier."""
        return LoginIdentifier(value).value

    @field_validator("bootstrap_tenant_slug")
    @classmethod
    def validate_bootstrap_tenant_slug(cls, value: str) -> str:
        """Validate the stable bootstrap tenant slug."""
        return TenantSlug(value).value

    @field_validator("bootstrap_display_name", "bootstrap_tenant_name")
    @classmethod
    def validate_display_text(cls, value: str) -> str:
        """Reject padding and control characters in bootstrap display values."""
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("bootstrap display values must not contain padding or controls")
        return value

    @field_validator("bootstrap_password")
    @classmethod
    def validate_bootstrap_password(cls, value: SecretStr | None) -> SecretStr | None:
        """Reject weak or placeholder bootstrap credentials when configured."""
        if value is None:
            return None
        secret = value.get_secret_value()
        if len(secret) < 16 or secret.strip().lower() in _PLACEHOLDER_SECRETS:
            raise ValueError(
                "bootstrap password must be a non-placeholder secret of 16+ characters"
            )
        return value


class SessionSettings(BaseModel):
    """Opaque browser-session lifetime, secret, and cookie policy.

    @skyhook-implements NFR-004
    @skyhook-story N1ZNPJWFZYPV0MVB8FP137GRJP
    """

    model_config = ConfigDict(frozen=True)

    secret: SecretStr | None = None
    idle_timeout_seconds: int = Field(default=1_800, ge=300, le=86_400)
    absolute_timeout_seconds: int = Field(default=43_200, ge=900, le=604_800)
    cookie_name: str = Field(default="evidentia_session", min_length=1, max_length=64)
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict"] = "lax"

    @field_validator("secret")
    @classmethod
    def validate_session_secret(cls, value: SecretStr | None) -> SecretStr | None:
        """Require minimum 256-bit-sized non-placeholder material when present."""
        if value is None:
            return None
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.strip().lower() in _PLACEHOLDER_SECRETS:
            raise ValueError("session secret must be a non-placeholder secret of 32+ characters")
        return value

    @field_validator("cookie_name")
    @classmethod
    def validate_cookie_name(cls, value: str) -> str:
        """Restrict cookie names to portable HTTP token characters."""
        if (
            not value.isascii()
            or not value[0].isalpha()
            or any(not (character.isalnum() or character in "_-") for character in value)
        ):
            raise ValueError("session cookie name must be a portable machine name")
        return value

    @model_validator(mode="after")
    def validate_session_lifetimes(self) -> Self:
        """Keep idle expiry bounded by the absolute session lifetime."""
        if self.idle_timeout_seconds > self.absolute_timeout_seconds:
            raise ValueError("session idle timeout cannot exceed absolute timeout")
        return self


class ApiRuntimeSettings(BaseModel):
    """API process binding and development behavior.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """

    model_config = ConfigDict(frozen=True)

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = False
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:5173",
    )

    @field_validator("allowed_origins")
    @classmethod
    def validate_allowed_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require explicit HTTP origins for credentialed browser requests."""
        if not value or len(set(value)) != len(value):
            raise ValueError("API allowed origins must be non-empty and unique")
        for origin in value:
            if origin == "*" or not origin.startswith(("http://", "https://")):
                raise ValueError("API allowed origins must be explicit HTTP origins")
            if origin.endswith("/") or any(character.isspace() for character in origin):
                raise ValueError("API allowed origins must not contain padding or trailing slashes")
        return value


class WorkerRuntimeSettings(BaseModel):
    """Worker process lifecycle controls independent of a queue provider.

    @skyhook-implements REQ-014
    @skyhook-story STORY-009
    """

    model_config = ConfigDict(frozen=True)

    shutdown_grace_seconds: float = Field(default=30.0, gt=0, le=300)


class ServiceSettings(BaseSettings):
    """Shared validated settings inherited by each service composition root.

    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="EVIDENTIA_",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    environment: RuntimeEnvironment = RuntimeEnvironment.DEVELOPMENT
    version: str = Field(default="0.1.0", min_length=1)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    identity: IdentitySettings = Field(default_factory=IdentitySettings)
    session: SessionSettings = Field(default_factory=SessionSettings)

    @model_validator(mode="after")
    def validate_environment_safety(self) -> Self:
        """Reject unsafe production secrets and development-only behavior.

        @skyhook-implements NFR-004
        @skyhook-story STORY-009
        """
        if self.environment is not RuntimeEnvironment.PRODUCTION:
            return self

        password = self.database.password
        if password is None or password.get_secret_value().strip().lower() in _PLACEHOLDER_SECRETS:
            raise ValueError("production requires a non-placeholder database password")
        if self.session.secret is None:
            raise ValueError("production requires a non-placeholder session secret")
        if not self.session.cookie_secure:
            raise ValueError("production requires secure session cookies")
        return self


class ApiSettings(ServiceSettings):
    """Complete validated settings for the API composition root.

    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """

    service: Literal["api"] = "api"
    api: ApiRuntimeSettings = Field(default_factory=ApiRuntimeSettings)

    @model_validator(mode="after")
    def reject_production_reload(self) -> Self:
        """Prevent development reload behavior in production.

        @skyhook-implements NFR-004
        @skyhook-story STORY-009
        """
        if self.environment is RuntimeEnvironment.PRODUCTION and self.api.reload:
            raise ValueError("API reload must be disabled in production")
        return self


class WorkerSettings(ServiceSettings):
    """Complete validated settings for the worker composition root.

    @skyhook-implements REQ-014
    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """

    service: Literal["worker"] = "worker"
    worker: WorkerRuntimeSettings = Field(default_factory=WorkerRuntimeSettings)


def load_api_settings(env_file: Path | None = None) -> ApiSettings:
    """Load a fresh API settings object from validated settings sources.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    return ApiSettings(_env_file=env_file)  # type: ignore[call-arg]


def load_worker_settings(env_file: Path | None = None) -> WorkerSettings:
    """Load a fresh worker settings object from validated settings sources.

    @skyhook-implements REQ-014
    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    return WorkerSettings(_env_file=env_file)  # type: ignore[call-arg]
