"""Tests for Evidentia's typed and fail-closed configuration.

@skyhook-implements NFR-004
@skyhook-implements NFR-006
@skyhook-story STORY-009
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evidentia.config.settings import (
    ApiSettings,
    RuntimeEnvironment,
    WorkerSettings,
    load_api_settings,
    load_worker_settings,
)


def test_development_and_test_profiles_have_safe_defaults() -> None:
    """Allow local and test startup without embedding usable credentials.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    development = ApiSettings()
    test = WorkerSettings(environment=RuntimeEnvironment.TEST)

    assert development.environment is RuntimeEnvironment.DEVELOPMENT
    assert development.database.password is None
    assert development.storage.backend == "filesystem"
    assert test.environment is RuntimeEnvironment.TEST
    assert test.database.password is None


def test_nested_environment_file_loads_service_specific_settings(tmp_path: Path) -> None:
    """Load shared and service settings through the documented nested names.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    env_file = tmp_path / "evidentia.env"
    env_file.write_text(
        "\n".join(
            (
                "EVIDENTIA_ENVIRONMENT=test",
                "EVIDENTIA_DATABASE__HOST=database.internal",
                "EVIDENTIA_DATABASE__PORT=5544",
                "EVIDENTIA_DATABASE__SSLMODE=require",
                "EVIDENTIA_DATABASE__APPLICATION_NAME=evidentia-test",
                "EVIDENTIA_LOGGING__LEVEL=WARNING",
                "EVIDENTIA_LOGGING__JSON=true",
                "EVIDENTIA_STORAGE__ROOT=/tmp/evidentia-artifacts",
                "EVIDENTIA_API__PORT=8088",
                "EVIDENTIA_WORKER__SHUTDOWN_GRACE_SECONDS=45",
            )
        ),
        encoding="utf-8",
    )

    api = load_api_settings(env_file)
    worker = load_worker_settings(env_file)

    assert api.environment is RuntimeEnvironment.TEST
    assert api.database.host == "database.internal"
    assert api.database.port == 5544
    assert api.database.sslmode == "require"
    assert api.database.application_name == "evidentia-test"
    assert api.logging.level == "WARNING"
    assert api.logging.json_output is True
    assert api.storage.root == Path("/tmp/evidentia-artifacts")
    assert api.api.port == 8088
    assert worker.worker.shutdown_grace_seconds == 45


@pytest.mark.parametrize("settings_type", [ApiSettings, WorkerSettings])
def test_production_requires_database_secret(
    settings_type: type[ApiSettings] | type[WorkerSettings],
) -> None:
    """Fail closed when a production process has no database password.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    with pytest.raises(ValidationError, match="non-placeholder database password"):
        settings_type(environment=RuntimeEnvironment.PRODUCTION)


@pytest.mark.parametrize("placeholder", ["password", "change-me", "example", "  secret  "])
def test_production_rejects_placeholder_secrets(placeholder: str) -> None:
    """Reject common example values even when a production secret is present.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    with pytest.raises(ValidationError, match="non-placeholder database password"):
        ApiSettings(
            environment=RuntimeEnvironment.PRODUCTION,
            database={"password": placeholder},
        )


def test_production_secret_is_redacted_and_settings_are_frozen() -> None:
    """Keep accepted secret material out of representations and prevent mutation.

    @skyhook-implements NFR-004
    @skyhook-implements NFR-006
    @skyhook-story STORY-009
    """
    secret_value = "correct-horse-battery-staple"
    settings = ApiSettings(
        environment=RuntimeEnvironment.PRODUCTION,
        database={"password": secret_value},
    )

    assert secret_value not in repr(settings)
    assert secret_value not in settings.model_dump_json()
    with pytest.raises(ValidationError, match="frozen"):
        settings.environment = RuntimeEnvironment.TEST  # type: ignore[misc]


def test_production_api_disables_reload() -> None:
    """Reject development reload behavior in the production profile.

    @skyhook-implements NFR-004
    @skyhook-story STORY-009
    """
    with pytest.raises(ValidationError, match="reload must be disabled"):
        ApiSettings(
            environment=RuntimeEnvironment.PRODUCTION,
            database={"password": "a-unique-production-password"},
            api={"reload": True},
        )


def test_database_settings_reject_invalid_ssl_mode_and_application_name() -> None:
    """Keep connection policy explicit and observable without exposing secrets.

    @skyhook-implements NFR-004
    @skyhook-story 0VJ9SHA39TA291D8QXB0TQS3HQ
    """
    with pytest.raises(ValidationError):
        ApiSettings(database={"sslmode": "trust-everything"})
    with pytest.raises(ValidationError):
        ApiSettings(database={"application_name": ""})
