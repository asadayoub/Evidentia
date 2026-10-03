"""Typed and fail-closed settings for Evidentia processes.

@skyhook-implements NFR-004
@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class ApiRuntimeSettings(BaseModel):
    """API process binding and development behavior.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """

    model_config = ConfigDict(frozen=True)

    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = False


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
